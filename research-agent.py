from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.mcp import MCPServerStdio

from videojungle import ApiClient

from typing import List, Optional
import instructor
from anthropic import Anthropic # Assumes you've set your API key as an environment variable

from pydantic import BaseModel, Field
from utils.tools import download 
import logfire
import os
import time
import click
import re

if not os.environ.get("VJ_API_KEY"):
    raise ValueError("VJ_API_KEY environment variable is not set.")

if not os.environ.get("SERPER_API_KEY"):
    raise ValueError("SERPER_API_KEY environment variable is not set.")

vj_api_key = os.environ["VJ_API_KEY"]
serper_api_key = os.environ["SERPER_API_KEY"]

logfire.configure()
logfire.instrument_openai()
logfire.instrument_anthropic()

vj = ApiClient(vj_api_key) # video jungle api client

vj_server = MCPServerStdio(  
    'uvx',
    args=[
        '-p', '3.11',
        '--from', 'video_editor_mcp@0.1.36',
        'video-editor-mcp'
    ],
    env={
        'VJ_API_KEY': vj_api_key,
    },
    timeout=30
)

serper_server = MCPServerStdio(
    'uvx',
    args=[
        '-p', '3.11',
        'serper-mcp-server@latest',
    ],
    env={
        'SERPER_API_KEY': serper_api_key,
    },
    timeout=30
)

class ResearchTopic(BaseModel):
    heading: str
    content: str
    previous_heading: Optional[str] = None
    next_heading: Optional[str] = None


class VideoItem(BaseModel):
    url: str
    title: str

class VideoList(BaseModel):
    videos: List[VideoItem] = Field(default_factory=list)

class VideoEdit(BaseModel):
    project_id: str
    edit_id: str

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

# Define models for agents
cheap_model = GeminiModel("gemini-2.5-flash-preview-05-20")
good_model = AnthropicModel("claude-sonnet-4-20250514")

# Define agents
edit_agent = Agent(
    model=good_model,
    instructions='You are an expert video editor, creating fast paced, interesting video edits for social media. ' \
    'You can answer questions, download and analyze videos, and create rough video edits using a mix of project assets and remote videos.' \
    'By default, if a project id is provided, you will use ONLY the assets in that project to create the edit. If no project id is provided,'
    'you will create a new project, and search videofiles to create an edit instead. For video assets in a project, you will use the type "user" instead of "videofile".' \
    'if you are doing a voice over, you will use the audio asset in the project as the voiceover for the edit, and set the video asset\'s audio level to 0 so that the voiceover is the only audio in the edit. ',
    mcp_servers=[vj_server],
    output_type=VideoEdit,
    instrument=True,
)

search_agent = Agent(  
    model=cheap_model,
    instructions='You are an expert video sourcer. You find the best source videos for a given topic.', 
    mcp_servers=[vj_server, serper_server],
    output_type=VideoList,
    instrument=True,
)

async def async_main(generate_audio: bool, search_for_videos: bool, topic_index: Optional[int] = None):
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
    
    # Optionally generate audio
    if generate_audio:
        print("Generating audio voiceover on Video Jungle...")
        
        # Create a prompt for the voice generation
        prompt = vj.prompts.generate(
            task="You are narrating an educational video. Read the script in an engaging, clear manner suitable for a general audience.",
            parameters=["script"]
        )
        
        # Create project with topic-specific name
        project_name = f"Educational Video: {selected_topic.heading[:50]}"
        project = vj.projects.create(
            name=project_name, 
            description=f"Educational video about {selected_topic.heading}", 
            prompt_id=prompt.id, 
            generation_method="prompt-to-speech"
        )
        
        script_id = project.scripts[0].id
        print(f"Created project: {project.name} with ID: {project.id}")
        
        # Generate audio
        audio = vj.projects.generate(
            script_id=script_id, 
            project_id=project.id,
            parameters={"script": voice_script.script}
        )
        
        print(f"Generated voiceover with asset id: {audio['asset_id']}")
        project_id = project.id
        audio_asset_id = audio['asset_id']
    
    # Search for and download videos if requested
    if search_for_videos and project_id:
        successful_videos = 0
        failed_videos = []
        processed_urls = set()
        search_attempts = 0
        max_search_attempts = 3
        
        project = vj.projects.get(project_id)
        
        while successful_videos < 5 and search_attempts < max_search_attempts:
            search_attempts += 1
            videos_to_request = 8 if search_attempts == 1 else 10
            
            async with search_agent.run_mcp_servers():
                print(f"\nSearch attempt {search_attempts}: Searching for videos related to '{selected_topic.heading}'...")
                search_query = f"can you search the web for videos about {selected_topic.heading}? I'd like a list of {videos_to_request} urls with video clips. Focus on educational content, news reports, or relevant visual content. The topic context is: {selected_topic.content[:200]}..."
                
                result = await search_agent.run(search_query, usage_limits=UsageLimits(request_limit=5))
            
            print(f"Found {len(result.output.videos)} videos in search attempt {search_attempts}")
            
            for video in result.output.videos:
                if video.url in processed_urls:
                    print(f"Skipping already processed URL: {video.url}")
                    continue
                
                processed_urls.add(video.url)
                
                if successful_videos >= 5:
                    break
                
                print(f"Processing video - Title: {video.title}, URL: {video.url}")
                safe_title = video.title.replace('/', '-').replace('\\', '-')
                output_filename = f"{safe_title}.mp4"
                
                try:
                    print(f"Downloading {video.title}...")
                    download(video.url, output_path=output_filename, format="best")
                    
                    if os.path.exists(output_filename):
                        print(f"Upload to Video Jungle: {video.title}")
                        project.upload_asset(
                            name=video.title,
                            description=f"Video related to {selected_topic.heading}: {video.title}",
                            filename=output_filename,
                        )
                        successful_videos += 1
                        print(f"Successfully uploaded video {successful_videos}/5")
                        os.remove(output_filename)
                    else:
                        print(f"Error: Download failed or file not found for {video.title}")
                        failed_videos.append(video.title)
                        
                except Exception as e:
                    if str(e):
                        print(f"Error processing {video.title}: {e}")
                    else:
                        print(f"Error processing {video.title}")
                    failed_videos.append(video.title)
                    continue
        
        print(f"\nFinal Summary: Successfully processed {successful_videos} videos after {search_attempts} search attempts")
        
        if successful_videos > 0:
            time.sleep(45)  # Wait for analysis
            
            # Create an edit with the videos and audio
            async with edit_agent.run_mcp_servers():
                print("\nVideo Editing Agent is now running")
                asset = vj.assets.get(audio_asset_id)
                asset_length = asset.create_parameters['metadata']['duration_seconds']
                
                result = await edit_agent.run(
                    f"""Create a compelling edit about '{selected_topic.heading}' using the video assets in project_id '{project_id}'. 
                    Use the audio asset with id '{audio_asset_id}' as the voiceover (start: 0, end: {asset_length} seconds).
                    Important:
                    - Set all video assets' audio_level to 0 (mute them)
                    - Match the total video duration to the voiceover duration ({asset_length} seconds)
                    - Create smooth transitions between clips
                    - Focus on visually interesting or relevant moments in each video
                    - Do not render the final video, just create the edit
                    - Use multiple requests to get-project-assets if needed (grab 2 assets at a time)""",
                    usage_limits=UsageLimits(request_limit=14)
                )
                
                print(f"\nEdit created successfully!")
                print(f"Project ID: {result.output.project_id}")
                print(f"Edit ID: {result.output.edit_id}")
                
                # Download the edit
                vj.edits.download_edit_render(
                    project_id=result.output.project_id,
                    edit_id=result.output.edit_id,
                    filename=f"{selected_topic.heading.replace('/', '-').replace(' ', '_')[:50]}_edit.mp4"
                )

@click.command()
@click.option('--generate-audio', '-a', is_flag=True, help='Generate audio voiceover using Video Jungle')
@click.option('--search-videos', '-s', is_flag=True, help='Search for and download related videos, then create an edit')
@click.option('--topic', '-t', type=int, help='Topic index to process (1-based). If not specified, processes the first topic.')
def main(generate_audio: bool, search_videos: bool, topic: Optional[int]):
    """Research agent that loads markdown documents and generates voice overlay scripts for individual topics."""
    import asyncio
    # Convert to 0-based index if provided
    topic_index = topic - 1 if topic else None
    asyncio.run(async_main(generate_audio, search_videos, topic_index))

if __name__ == "__main__":
    main()



