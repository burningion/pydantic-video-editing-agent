from pydantic_ai import Agent
from pydantic_ai.models.gemini import GeminiModel
from pydantic_ai.mcp import MCPServerStdio

from videojungle import ApiClient, VideoEditCreate, VideoEditAsset, VideoEditAudioAsset, VideoAudioLevel

from typing import List, Dict, Tuple, Optional
import instructor
from openai import OpenAI

from pydantic import BaseModel, Field
from utils.tools import download
import logfire
import os
import time
import click
import re
import json
from datetime import datetime

if not os.environ.get("VJ_API_KEY"):
    raise ValueError("VJ_API_KEY environment variable is not set.")

if not os.environ.get("SERPER_API_KEY"):
    raise ValueError("SERPER_API_KEY environment variable is not set.")

vj_api_key = os.environ["VJ_API_KEY"]
serper_api_key = os.environ["SERPER_API_KEY"]

logfire.configure()
logfire.instrument_openai()

vj = ApiClient(vj_api_key)  # video jungle api client

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


class VideoItem(BaseModel):
    url: str
    title: str
    relevance_score: float = Field(default=0.0, description="Relevance score from 0-1 based on match to beat description")
    relevance_reason: str = Field(default="", description="Brief explanation of relevance")


class VideoList(BaseModel):
    videos: List[VideoItem] = Field(default_factory=list)


class Beat(BaseModel):
    beat_number: int
    duration_seconds: int
    scene_description: str
    search_terms: List[str]


class VideoBeats(BaseModel):
    beats: List[Beat]


class BeatWithAssets(BaseModel):
    beat: Beat
    video_asset_id: Optional[str] = None
    audio_asset_id: Optional[str] = None
    video_source: Optional[str] = None  # 'vj_library', 'project', 'downloaded'


def parse_markdown_sections(file_path: str, skip_intro: bool = True) -> List[Tuple[str, str]]:
    """Parse markdown file and extract heading-content pairs."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by ## headings (h2 level)
    sections = re.split(r'^## ', content, flags=re.MULTILINE)[1:]  # Skip content before first heading
    
    heading_content_pairs = []
    for section in sections:
        lines = section.strip().split('\n', 1)
        heading = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else ""
        
        # Skip introduction and references sections
        if skip_intro and heading.lower() in ['introduction', 'references']:
            continue
            
        heading_content_pairs.append((heading, content))
    
    return heading_content_pairs


def generate_video_beats(sections: List[Tuple[str, str]], model: str = "o3-mini") -> VideoBeats:
    """Use specified model to generate video beats from research sections."""
    client = OpenAI()
    instructor_client = instructor.from_openai(client)
    
    # Prepare the content for analysis
    research_content = "Research Document Sections:\n\n"
    for heading, content in sections:
        research_content += f"## {heading}\n{content[:800]}...\n\n"  # Truncate long sections
    
    beats_prompt = f"""
    Create a series of video beats (short scenes) that tell the story from this research document.
    Each beat should be 5-10 seconds long and focus on a specific visual moment.
    The beats should flow together to create a cohesive narrative.
    
    For each beat, provide:
    1. A beat number (sequential)
    2. Duration in seconds (5-10)
    3. A cinematic scene description that captures a specific moment
    4. 2-3 specific search terms to find relevant video clips
    
    Create approximately 6-10 beats that cover the key themes and moments from the research.
    Focus on visual storytelling - describe what the viewer will see.
    
    {research_content}
    """
    
    response = instructor_client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are an expert documentary filmmaker who creates compelling visual narratives from research content. Create specific, cinematic beat descriptions that tell a visual story."
            },
            {
                "role": "user",
                "content": beats_prompt
            }
        ],
        response_model=VideoBeats
    )
    
    return response


def generate_voiceover_from_research(sections: List[Tuple[str, str]], project_id: str, script_id: str) -> Optional[Tuple[str, float]]:
    """Generate a 30-second voiceover from research text."""
    # Compile key points from research sections
    research_summary = "Create a compelling 30-second documentary narration based on this research:\n\n"
    
    for heading, content in sections[:3]:  # Use first 3 sections for brevity
        # Extract first paragraph or key points
        first_para = content.split('\n\n')[0] if content else ""
        research_summary += f"{heading}: {first_para[:200]}...\n\n"
    
    research_summary += "\nIMPORTANT: This narration must be exactly 30 seconds when read at a natural pace. Make it engaging, cinematic, and focus on the most compelling aspects of the story."
    
    try:
        print("  Generating voiceover from research text...")
        audio = vj.projects.generate(
            script_id=script_id,
            project_id=project_id,
            parameters={
                "script": research_summary,
                "context": "30-second documentary narration"
            }
        )
        
        # Wait for audio generation to complete and get asset info
        time.sleep(5)
        
        # Get the audio asset to check duration
        try:
            project = vj.projects.get(project_id)
            audio_asset = next((a for a in project.assets if str(a.id) == audio['asset_id']), None)
            if audio_asset and hasattr(audio_asset, 'duration'):
                duration = audio_asset.duration
            else:
                duration = 30.0  # Default to 30 seconds
        except:
            duration = 30.0
            
        return audio['asset_id'], duration
    except Exception as e:
        print(f"  Voiceover generation error: {str(e)[:100]}")
        return None


async def search_vj_library(search_terms: List[str], scene_description: str = "") -> Optional[Dict]:
    """Search Video Jungle library for matching videos."""
    # Try different search strategies
    search_queries = []
    
    # 1. Individual search terms
    search_queries.extend(search_terms)
    
    # 2. Combined search terms
    if len(search_terms) > 1:
        search_queries.append(" ".join(search_terms))
    
    # 3. Keywords from scene description
    if scene_description:
        # Extract key nouns/phrases from description
        keywords = [word for word in scene_description.split() 
                   if len(word) > 4 and word.lower() not in ['with', 'from', 'that', 'this', 'have', 'been']]
        search_queries.extend(keywords[:3])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_queries = []
    for q in search_queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            unique_queries.append(q)
    
    # Search with each query
    for query in unique_queries:
        try:
            # Use video_files.search to search the VJ library
            results = vj.video_files.search(query=query, limit=10)
            if results and len(results) > 0:
                # Return the first good match
                for result in results:
                    # Each result should have an 'id' field
                    if 'id' in result:
                        return {
                            'id': result['id'],
                            'name': result.get('name', result.get('filename', '')),
                            'source': 'vj_library',
                            'matched_query': query
                        }
        except Exception as e:
            print(f"    VJ search error for '{query}': {str(e)[:50]}")
    return None


async def search_project_assets(project_id: str, search_terms: List[str], scene_description: str = "") -> Optional[Dict]:
    """Search project assets for matching videos."""
    try:
        project = vj.projects.get(project_id)
        assets = project.assets
        
        # Create search queries
        search_queries = [term.lower() for term in search_terms]
        
        # Add keywords from scene description
        if scene_description:
            keywords = [word.lower() for word in scene_description.split() 
                       if len(word) > 4 and word.lower() not in ['with', 'from', 'that', 'this', 'have', 'been']]
            search_queries.extend(keywords[:3])
        
        # Search through project assets
        for asset in assets:
            # Asset is an object, not a dict
            if hasattr(asset, 'asset_type') and asset.asset_type == 'user':
                asset_name = (asset.keyname or '').lower()
                asset_desc = (getattr(asset, 'description', '') or '').lower()
                
                # Check both name and description
                for query in search_queries:
                    if query in asset_name or query in asset_desc:
                        return {
                            'id': asset.id,
                            'name': asset.keyname,
                            'source': 'project',
                            'matched_query': query
                        }
    except Exception as e:
        print(f"    Project search error: {str(e)[:50]}")
    return None


async def search_for_videos_with_serper(search_query: str, scene_description: str) -> VideoList:
    """Search for videos using Serper via MCP and Claude with relevance ranking."""
    # Create a search agent with Serper and VJ MCP servers
    search_agent = Agent(
        model=GeminiModel("gemini-2.5-pro"),
        mcp_servers=[serper_server, vj_server],
        instructions="""You are an expert video sourcer and relevance analyst. Use the Serper search tool to find relevant video content.
        You also have access to Video Jungle tools to search existing video libraries.
        Focus on finding actual video URLs from platforms like YouTube, Vimeo, Dailymotion, etc.
        
        CRITICAL: For each video found, you MUST:
        1. Analyze how well the video title/description matches the scene requirements
        2. Assign a relevance_score from 0.0 to 1.0 based on:
           - 0.8-1.0: Excellent match - video clearly depicts the described scene
           - 0.6-0.8: Good match - video contains relevant elements
           - 0.4-0.6: Moderate match - somewhat related but missing key elements
           - 0.2-0.4: Poor match - only tangentially related
           - 0.0-0.2: Very poor match - barely related or wrong context
        3. Provide a brief relevance_reason explaining the score
        4. Sort results by relevance_score in descending order
        
        Only include videos with relevance_score >= 0.5 in your final results.""",
        output_type=VideoList,
    )
    
    search_prompt = f"""
    Search for video clips that match this specific scene:
    
    Scene description: {scene_description}
    Search terms: {search_query}
    
    IMPORTANT: You must find videos that actually depict or relate to "{scene_description}".
    
    For each video:
    1. Search using the provided terms and variations
    2. Evaluate how well each result matches the scene description
    3. Score each video's relevance (0.0-1.0)
    4. Only return videos with relevance >= 0.5
    5. Sort by relevance score (highest first)
    
    Return 5-10 highly relevant videos that truly match the scene requirements.
    """
    
    try:
        async with search_agent.run_mcp_servers():
            result = await search_agent.run(search_prompt)
            return result.output
            
    except Exception as e:
        print(f"    Search error: {str(e)[:100]}")
        return VideoList(videos=[])


async def search_and_download_for_beat(beat: Beat, project: any) -> Optional[str]:
    """Search web and download video for a specific beat."""
    print(f"\n  Searching web for Beat {beat.beat_number} videos...")
    print(f"  Scene: {beat.scene_description[:80]}...")
    
    # Combine search terms into a query
    search_query = " OR ".join(beat.search_terms[:2])
    
    try:
        # Use Serper search with relevance scoring
        result = await search_for_videos_with_serper(search_query, beat.scene_description)
        
        if not result.videos:
            print("    No relevant videos found (all scored < 0.5)")
            return None
        
        # Sort by relevance score (should already be sorted, but ensure)
        sorted_videos = sorted(result.videos, key=lambda v: v.relevance_score, reverse=True)
        
        # Try videos in order of relevance
        for i, video in enumerate(sorted_videos[:5]):
            print(f"    Attempt {i+1}: {video.title[:50]}... (relevance: {video.relevance_score:.2f})")
            if video.relevance_reason:
                print(f"      Reason: {video.relevance_reason[:80]}...")
            
            safe_title = video.title.replace('/', '-').replace('\\', '-')[:40]
            output_filename = f"beat_{beat.beat_number}_{safe_title}.mp4"
            
            # Try downloading with retries
            for retry in range(2):  # 2 attempts per video
                try:
                    download(video.url, output_path=output_filename)
                    
                    if os.path.exists(output_filename) and os.path.getsize(output_filename) > 1000:  # Check file exists and is not empty
                        # Upload to project
                        asset = project.upload_asset(
                            name=f"Beat {beat.beat_number}: {video.title}"[:100],
                            description=f"Beat {beat.beat_number} - {beat.scene_description[:150]} (relevance: {video.relevance_score:.2f})",
                            filename=output_filename,
                        )
                        os.remove(output_filename)
                        print(f"    Uploaded successfully (relevance score: {video.relevance_score:.2f})")
                        return asset.id
                    else:
                        if os.path.exists(output_filename):
                            os.remove(output_filename)
                        print(f"    Empty or invalid file, trying next...")
                        break
                        
                except Exception as e:
                    print(f"    Download attempt {retry+1} failed: {str(e)[:50]}")
                    if os.path.exists(output_filename):
                        os.remove(output_filename)
                    if retry == 0:
                        print(f"    Retrying...")
                        time.sleep(2)
                    else:
                        print(f"    Moving to next video...")
                        break
                
    except Exception as e:
        print(f"  Search error: {str(e)[:100]}")
    
    return None


async def find_or_create_video_for_beat(beat: Beat, project: any) -> BeatWithAssets:
    """Find existing video or download new one for a beat."""
    beat_with_assets = BeatWithAssets(beat=beat)
    
    print(f"\nProcessing Beat {beat.beat_number}: {beat.scene_description[:60]}...")
    
    # 1. Search Video Jungle library first
    print("  Checking Video Jungle library...")
    vj_result = await search_vj_library(beat.search_terms, beat.scene_description)
    if vj_result:
        beat_with_assets.video_asset_id = vj_result['id']
        beat_with_assets.video_source = 'vj_library'
        print(f"  Found in VJ library: {vj_result['name'][:60]} (matched: {vj_result.get('matched_query', '')})")
        return beat_with_assets
    
    # 2. Search project assets
    print("  Checking project assets...")
    project_result = await search_project_assets(project.id, beat.search_terms, beat.scene_description)
    if project_result:
        beat_with_assets.video_asset_id = project_result['id']
        beat_with_assets.video_source = 'project'
        print(f"  Found in project: {project_result['name'][:60]} (matched: {project_result.get('matched_query', '')})")
        return beat_with_assets
    
    # 3. Search and download from web
    print("  Not found locally, searching web...")
    downloaded_asset_id = await search_and_download_for_beat(beat, project)
    if downloaded_asset_id:
        beat_with_assets.video_asset_id = downloaded_asset_id
        beat_with_assets.video_source = 'downloaded'
        print("Downloaded and uploaded new video")
    else:
        print("Could not find suitable video for this beat")
    
    return beat_with_assets


def create_edit_from_beats(project_id: str, beats_with_assets: List[BeatWithAssets], voiceover_id: str, audio_duration: float):
    """Create a video edit from the collected beats matching audio duration."""
    # Calculate time per beat based on audio duration
    total_beats = len([b for b in beats_with_assets if b.video_asset_id])
    if total_beats == 0:
        return None
        
    time_per_beat = audio_duration / total_beats
    
    # Prepare video sequence
    video_sequence = []
    current_time = 0
    
    for beat_data in beats_with_assets:
        if beat_data.video_asset_id:
            # Convert seconds to time format (HH:MM:SS.mmm)
            start_time = f"00:00:{current_time:06.3f}"
            end_time = f"00:00:{current_time + time_per_beat:06.3f}"
            
            # Determine asset type based on source
            if beat_data.video_source == 'vj_library':
                asset_type = "videofile"
            else:
                asset_type = "asset"
            
            video_asset = VideoEditAsset(
                video_id=beat_data.video_asset_id,  # Pass as string, not UUID
                type=asset_type,
                video_start_time=start_time,
                video_end_time=end_time,
                audio_levels=[VideoAudioLevel(audio_level=0.5, start_time=start_time, end_time=end_time)]
            )
            video_sequence.append(video_asset)
            current_time += time_per_beat
    
    # Prepare audio overlay
    audio_overlays = []
    if voiceover_id:
        audio_end_time = f"00:00:{audio_duration:06.3f}"
        audio_overlay = VideoEditAudioAsset(
            audio_id=voiceover_id,  # Pass as string, not UUID
            type="voiceover",
            audio_start_time="00:00:00.000",
            audio_end_time=audio_end_time,
            audio_levels=[VideoAudioLevel(audio_level=1.0, start_time="00:00:00.000", end_time=audio_end_time)]
        )
        audio_overlays.append(audio_overlay)
    
    # Create edit configuration
    edit_config = VideoEditCreate(
        name=f"Documentary Edit - {datetime.now().strftime('%Y%m%d_%H%M%S')}",
        description="Documentary video created from research",
        video_edit_version="v1",
        video_output_format="mp4",
        video_output_resolution="1920x1080",
        video_output_fps=30.0,
        video_output_filename=f"documentary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
        skip_rendering=False,
        video_series_sequential=video_sequence,
        audio_overlay=audio_overlays,
        subtitles=True
    )
    
    # Create the edit using the fixed API method
    try:
        edit = vj.projects.create_edit(project_id, edit_config)
        return edit
    except Exception as e:
        print(f"Edit creation error: {str(e)}")
        return None


async def async_main(markdown_file: str, project_id: Optional[str], model: str = "o3-mini"):
    """Process a markdown research file and create a video documentary."""
    # Parse markdown sections (skip introduction)
    print(f"Parsing markdown file: {markdown_file}")
    sections = parse_markdown_sections(markdown_file, skip_intro=True)
    print(f"  Found {len(sections)} sections to process")
    
    # Get or create Video Jungle project
    if project_id:
        print(f"\nUsing existing Video Jungle project: {project_id}")
        try:
            project = vj.projects.get(project_id)
            print(f"  Found project: {project.name}")
            # Get the first script ID from the existing project
            if project.scripts and len(project.scripts) > 0:
                script_id = project.scripts[0].id
            else:
                print("  Warning: No scripts found in project, creating new prompt...")
                prompt = vj.prompts.generate(
                    task="You are creating cinematic documentary narration. The tone should be engaging, dramatic, and professional.",
                    parameters=["script", "context"]
                )
                # Update project with new prompt
                project = vj.projects.update(
                    project_id,
                    prompt_id=prompt.id,
                    generation_method="prompt-to-speech"
                )
                script_id = project.scripts[0].id
        except Exception as e:
            print(f"  Error getting project: {str(e)}")
            print("  Creating new project instead...")
            project_id = None
    
    if not project_id:
        print(f"\nCreating new Video Jungle project...")
        project_name = f"Documentary: {os.path.basename(markdown_file).replace('.md', '')}"
        
        # Create prompt for voiceover generation
        prompt = vj.prompts.generate(
            task="You are creating cinematic documentary narration. The tone should be engaging, dramatic, and professional.",
            parameters=["script", "context"]
        )
        
        # Create project
        project = vj.projects.create(
            name=project_name,
            description=f"Documentary video from research: {markdown_file}",
            prompt_id=prompt.id,
            generation_method="prompt-to-speech"
        )
        
        script_id = project.scripts[0].id
        print(f"  Created project: {project.name} (ID: {project.id})")
    
    # Generate voiceover first from research text
    print("\nGenerating 30-second voiceover from research...")
    voiceover_result = generate_voiceover_from_research(sections, project.id, script_id)
    if not voiceover_result:
        print("  Failed to generate voiceover")
        return
    
    voiceover_id, audio_duration = voiceover_result
    print(f"  Generated voiceover (duration: {audio_duration:.1f}s)")
    
    # Now generate video beats
    print(f"\nGenerating video beats using {model}...")
    video_beats = generate_video_beats(sections, model=model)
    print(f"  Generated {len(video_beats.beats)} beats")
    
    # Process each beat
    print("\nProcessing video beats...")
    beats_with_assets = []
    
    for beat in video_beats.beats:
        beat_data = await find_or_create_video_for_beat(beat, project)
        beats_with_assets.append(beat_data)
    
    # Wait for video analysis
    print("\nWaiting for video analysis to complete...")
    time.sleep(30)
    
    # Create final edit matching audio duration
    print("\nCreating final edit...")
    edit = create_edit_from_beats(project.id, beats_with_assets, voiceover_id, audio_duration)
    
    # Summary
    successful_beats = sum(1 for b in beats_with_assets if b.video_asset_id is not None)
    print(f"\nDocumentary creation complete!")
    print(f"  Found videos for {successful_beats}/{len(video_beats.beats)} beats")
    print(f"  Voiceover duration: {audio_duration:.1f} seconds")
    print(f"  Project ID: {project.id}")
    print(f"  Project URL: https://app.video-jungle.com/projects/{project.id}")
    
    # Save edit configuration in video edit JSON spec format
    # Calculate time segments for each beat
    beats_with_video = [b for b in beats_with_assets if b.video_asset_id]
    time_per_beat = audio_duration / len(beats_with_video) if beats_with_video else 0
    current_time = 0
    
    # Build video_series_sequential array
    video_series_sequential = []
    for b in beats_with_assets:
        if b.video_asset_id:
            start_time = f"00:00:{current_time:06.3f}"
            end_time = f"00:00:{current_time + time_per_beat:06.3f}"
            
            video_clip = {
                "video_id": b.video_asset_id,
                "video_start_time": start_time,
                "video_end_time": end_time,
                "type": "videofile" if b.video_source == "vj_library" else "asset",
                "audio_levels": [
                    {
                        "audio_level": "0.5",
                        "start_time": start_time,
                        "end_time": end_time
                    }
                ]
            }
            video_series_sequential.append(video_clip)
            current_time += time_per_beat
    
    # Build audio_overlay array for voiceover
    audio_overlay = []
    if voiceover_id:
        audio_overlay.append({
            "audio_id": voiceover_id,
            "type": "voiceover",
            "audio_start_time": "00:00:00.000",
            "audio_end_time": f"00:00:{audio_duration:06.3f}",
            "audio_levels": [
                {
                    "audio_level": "1.0",
                    "start_time": "00:00:00.000",
                    "end_time": f"00:00:{audio_duration:06.3f}"
                }
            ]
        })
    
    # Create output in video edit spec format
    edit_spec = {
        "video_edit_version": "1.0",
        "video_output_format": "mp4",
        "video_output_resolution": "1920x1080",
        "video_output_fps": 30.0,
        "edit_name": f"documentary-{project.id}",
        "video_output_filename": f"documentary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
        "audio_overlay": audio_overlay,
        "video_series_sequential": video_series_sequential,
        "metadata": {
            "project_id": project.id,
            "project_url": f"https://app.video-jungle.com/project/{project.id}",
            "total_duration": audio_duration,
            "beats_with_video": len(beats_with_video),
            "total_beats": len(beats_with_assets),
            "missing_beats": [
                {
                    "beat_number": b.beat.beat_number,
                    "description": b.beat.scene_description,
                    "search_terms": b.beat.search_terms
                }
                for b in beats_with_assets if not b.video_asset_id
            ]
        }
    }
    
    output_file = f"edit_{project.id}.json"
    with open(output_file, 'w') as f:
        json.dump(edit_spec, f, indent=2)
    print(f"  Saved edit spec to: {output_file}")


@click.command()
@click.option('--markdown-file', '-m', required=True, help='Path to the markdown research file')
@click.option('--project-id', '-p', default=None, help='Existing Video Jungle project ID to use (if not provided, creates a new project)')
@click.option('--model', '-o', default='o3-mini', help='Model to use for beat generation (default: o3-mini)')
def main(markdown_file: str, project_id: str, model: str):
    """Process a markdown research file and create a video documentary with beats."""
    import asyncio
    asyncio.run(async_main(markdown_file, project_id, model))


if __name__ == "__main__":
    main()