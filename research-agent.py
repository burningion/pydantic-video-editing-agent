from videojungle import ApiClient

from typing import List, Optional
import instructor
from anthropic import Anthropic # Assumes you've set your API key as an environment variable

from pydantic import BaseModel, Field
import logfire
import os
import time
import click
import re

if not os.environ.get("VJ_API_KEY"):
    raise ValueError("VJ_API_KEY environment variable is not set.")

vj_api_key = os.environ["VJ_API_KEY"]

logfire.configure()
logfire.instrument_openai()
logfire.instrument_anthropic()

vj = ApiClient(vj_api_key) # video jungle api client

class ResearchTopic(BaseModel):
    heading: str
    content: str
    previous_heading: Optional[str] = None
    next_heading: Optional[str] = None



class VoiceOverScript(BaseModel):
    script: str
    duration_estimate: str

def parse_markdown_by_headings(file_path: str) -> List[ResearchTopic]:
    """Parse a markdown file and split it by headings into topics."""
    topics = []
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Split by any heading (# or ##)
        sections = re.split(r'^(#{1,6}\s+.+)$', content, flags=re.MULTILINE)
        
        # Process sections
        current_heading = None
        current_content = []
        found_first_heading = False
        
        for i, section in enumerate(sections):
            if section.strip():
                # Check if this is a heading
                if re.match(r'^#{1,6}\s+', section):
                    found_first_heading = True
                    # Save previous section if it has content and a heading
                    if current_heading and current_content:
                        content_text = '\n'.join(current_content).strip()
                        # Check if the content has actual text (not just links/references)
                        if has_meaningful_content(content_text):
                            topics.append(ResearchTopic(
                                heading=current_heading,
                                content=content_text
                            ))
                    # Start new section
                    current_heading = section.strip().lstrip('#').strip()
                    current_content = []
                else:
                    # Only add content if we've found the first heading
                    if found_first_heading:
                        current_content.append(section.strip())
        
        # Don't forget the last section
        if current_heading and current_content:
            content_text = '\n'.join(current_content).strip()
            if has_meaningful_content(content_text):
                topics.append(ResearchTopic(
                    heading=current_heading,
                    content=content_text
                ))
    
    except FileNotFoundError:
        print(f"Warning: File {file_path} not found")
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
    
    return topics

def has_meaningful_content(content: str) -> bool:
    """Check if content has meaningful text beyond just references and links."""
    if not content:
        return False
    
    # Remove common reference patterns
    cleaned = content
    # Remove bullet points with just links
    cleaned = re.sub(r'^\s*[•\-\*]\s*.*https?://.*$', '', cleaned, flags=re.MULTILINE)
    # Remove lines that are just "Available at: URL"
    cleaned = re.sub(r'^\s*Available at:\s*https?://.*$', '', cleaned, flags=re.MULTILINE)
    # Remove lines that are just citations with years
    cleaned = re.sub(r'^\s*.*\(\d{4}\)\.?\s*$', '', cleaned, flags=re.MULTILINE)
    # Remove lines that are just case names
    cleaned = re.sub(r'^\s*\w+\s+v\.\s+\w+.*\(\d{4}\).*$', '', cleaned, flags=re.MULTILINE)
    
    # Check if there's any substantial text left
    remaining_text = cleaned.strip()
    
    # Must have at least 50 characters of meaningful text
    return len(remaining_text) > 50

def load_research_materials() -> List[ResearchTopic]:
    """Load and parse research materials from markdown files."""
    all_topics = []
    
    # Find all markdown files in the current directory
    markdown_files = [f for f in os.listdir('.') if f.endswith('.md') and f not in ['README.md', 'CLAUDE.md']]
    
    print(f"Found {len(markdown_files)} markdown files to process")
    
    for file in markdown_files:
        print(f"  - Processing {file}")
        topics = parse_markdown_by_headings(file)
        all_topics.extend(topics)
    
    # Add previous and next heading context
    for i, topic in enumerate(all_topics):
        if i > 0:
            topic.previous_heading = all_topics[i-1].heading
        if i < len(all_topics) - 1:
            topic.next_heading = all_topics[i+1].heading
    
    return all_topics

def generate_voice_overlay_script(topic: ResearchTopic) -> VoiceOverScript:
    """Generate a voice overlay script for a single topic."""
    workflow_client = Anthropic()
    client = instructor.from_anthropic(workflow_client)
    
    # Build context information
    context_info = ""
    if topic.previous_heading:
        context_info += f"\nPrevious topic: {topic.previous_heading}"
    if topic.next_heading:
        context_info += f"\nNext topic: {topic.next_heading}"
    
    prompt = f"""
    You are creating a compelling voice-over script based on the following research topic. 
    The script must be engaging, informative, and suitable for a video that's under 50 seconds long.
    
    Topic: {topic.heading}
    Content: {topic.content}
    {context_info}
    
    Create a script that:
    - Focuses specifically on this topic
    - Uses the active voice
    - Maintains as many facts as possible from the content
    - Has a compelling hook at the beginning
    - Speaks in concrete terms, no picture this, etc.
    - Flows naturally when spoken aloud
    - Is educational but also engaging
    - Must be readable in under 50 seconds
    {f"- If there's a previous topic, briefly connect from it" if topic.previous_heading else ""}
    {f"- IMPORTANT: End with a cliffhanger or teaser that creates curiosity about '{topic.next_heading}'" if topic.next_heading else "- End with a strong conclusion since this is the final topic"}
    """
    
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        response_model=VoiceOverScript,
    )
    
    return resp


async def async_main(generate_audio: bool, download_video: bool, topic_index: Optional[int] = None):
    """Main async function that runs the research agent."""
    
    # Load research materials
    print("Loading research materials...")
    topics = load_research_materials()
    
    print(f"\nFound {len(topics)} topics:")
    for i, topic in enumerate(topics[:20]):  # Show first 20 topics
        print(f"  {i+1}. {topic.heading}")
    
    if len(topics) > 20:
        print(f"  ... and {len(topics) - 20} more topics")
    
    # Select topic to process
    if topic_index is not None:
        if 0 <= topic_index < len(topics):
            selected_topic = topics[topic_index]
            print(f"\nProcessing topic {topic_index + 1}: {selected_topic.heading}")
        else:
            print(f"Error: Topic index {topic_index + 1} is out of range (1-{len(topics)})")
            return
    else:
        # Let user choose or process all
        print("\nNo topic specified. Use --topic N to select a specific topic.")
        if len(topics) > 0:
            selected_topic = topics[0]
            print(f"Processing first topic: {selected_topic.heading}")
        else:
            print("No topics found to process.")
            return
    
    # Generate voice overlay script for selected topic
    print(f"\nGenerating voice overlay script for: {selected_topic.heading}...")
    if selected_topic.previous_heading:
        print(f"  Previous: {selected_topic.previous_heading}")
    if selected_topic.next_heading:
        print(f"  Next: {selected_topic.next_heading}")
    
    voice_script = generate_voice_overlay_script(selected_topic)
    
    print(f"\n=== Voice Overlay Script ===")
    print(f"Topic: {selected_topic.heading}")
    print(f"Duration estimate: {voice_script.duration_estimate}")
    print(f"\nScript:\n{voice_script.script}")
    print("===========================\n")
    
    project_id = None
    audio_asset_id = None
    
    # Optionally generate video on Video Jungle
    if generate_audio:
        print("Generating video on Video Jungle...")
        
        # Create project with topic-specific name
        project_name = f"Educational Video: {selected_topic.heading[:50]}"
        project = vj.projects.create(
            name=project_name, 
            description=f"Educational video about {selected_topic.heading}",
            generation_method="prompt-to-video"
        )
        
        script_id = project.scripts[0].id
        print(f"Created project: {project.name} with ID: {project.id}")
        
        # Generate video
        video = vj.projects.generate_from_prompt(
            project_id=project.id,
            script_id=script_id,
            prompt=voice_script.script,
        )
        
        print(f"Generated video with asset id: {video['asset_id']}")
        project_id = project.id
        audio_asset_id = video['asset_id']
    
    # Download the generated video if requested
    if download_video and audio_asset_id:
        print("\nWaiting for video generation to complete...")
        time.sleep(30)  # Wait for generation
        
        filename = f"{selected_topic.heading.replace('/', '-').replace(' ', '_')[:50]}_video.mp4"
        
        print(f"Downloading generated video as: {filename}")
        vj.assets.download(audio_asset_id, filename=filename)
        print(f"Video downloaded successfully!")

@click.command()
@click.option('--generate-video', '-g', is_flag=True, help='Generate video with still images on Video Jungle')
@click.option('--download', '-d', is_flag=True, help='Download the generated video')
@click.option('--topic', '-t', type=int, help='Topic index to process (1-based). If not specified, processes the first topic.')
def main(generate_video: bool, download: bool, topic: Optional[int]):
    """Research agent that loads markdown documents and generates educational videos for individual topics."""
    import asyncio
    # Convert to 0-based index if provided
    topic_index = topic - 1 if topic else None
    asyncio.run(async_main(generate_video, download, topic_index))

if __name__ == "__main__":
    main()



