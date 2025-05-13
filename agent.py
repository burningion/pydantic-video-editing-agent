from pydantic_ai import Agent
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import UsageLimits
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.mcp import MCPServerStdio

from videojungle import ApiClient

from pydantic import BaseModel, Field
from typing import List
from utils.tools import download 
import logfire
import os
import time

if not os.environ.get("VJ_API_KEY"):
    raise ValueError("VJ_API_KEY environment variable is not set.")

if not os.environ.get("SERPER_API_KEY"):
    raise ValueError("SERPER_API_KEY environment variable is not set.")

vj_api_key = os.environ["VJ_API_KEY"]
serper_api_key = os.environ["SERPER_API_KEY"]

logfire.configure()

vj = ApiClient(vj_api_key) # video jungle api client

vj_server = MCPServerStdio(  
    'uvx',
    args=[
        '-p', '3.11',
        '--from', 'video_editor_mcp@0.1.25',
        'video-editor-mcp'
    ],
    env={
        'VJ_API_KEY': vj_api_key,
    }
)

serper_server = MCPServerStdio(
    'uvx',
    args=[
        '-p', '3.11',
        'serper-mcp-server@latest',
    ],
    env={
        'SERPER_API_KEY': serper_api_key,
    }
)

class VideoItem(BaseModel):
    url: str
    title: str

class VideoList(BaseModel):
    videos: List[VideoItem] = Field(default_factory=list)
    
    def __init__(self, **data):
        # Handle the case where a single video is passed instead of a list
        if 'url' in data and 'title' in data:
            # If individual url/title fields are provided, convert to a list with one item
            videos_data = [{'url': data.pop('url'), 'title': data.pop('title')}]
            data['videos'] = videos_data
        super().__init__(**data)
    
    def add_video(self, url: str, title: str):
        """Add a video to the list"""
        self.videos.append(VideoItem(url=url, title=title))
    
    def __iter__(self):
        """Make the VideoList iterable"""
        return iter(self.videos)
    
    def __getitem__(self, index):
        """Allow indexing into the VideoList"""
        return self.videos[index]
    
    def __len__(self):
        """Return the number of videos"""
        return len(self.videos)

class VideoEdit(BaseModel):
    project_id: str
    edit_id: str

model = AnthropicModel("claude-3-7-sonnet-20250219")

edit_agent = Agent(
    model=model,
    system_prompt='You are an expert video editor. ' \
    'You can answer questions, download and analyze videos, and create rough video edits using a mix of projects and remote videos.' \
    'By default, if a project id is provided, you will use ONLY the assets in that project to create the edit. If no project id is provided,'
    'you will create a new project, and search videofiles to create an edit instead. For video assets in a project, you will use the type "user" instead of "videofile".',
    mcp_servers=[vj_server],
    output_type=VideoEdit,
    instrument=True,
)
search_agent = Agent(  
    model=model,
    system_prompt='You are an expert video sourcer. You find the best source videos for a given topic.', 
    mcp_servers=[vj_server, serper_server],
    output_type=VideoList,
    instrument=True,
)

async def main():
    async with search_agent.run_mcp_servers():
        print("Search Agent is running")
        result = await search_agent.run("can you search the web for the newest clips about nathan fielder? I'd like a list of 5 urls with video clips. it's may 13, 2025 by the way, and nathan is doing a show called 'the rehearsal'.",
                                        usage_limits=UsageLimits(request_limit=5))
        
    print(result)
    print("Creating a Video Jungle project with the found videos")
    project = vj.projects.create("Nathan Fielder Clips", description="Pydantic Agent Nathan Fielder Clips")

    successful_videos = 0
    failed_videos = []

    for video in result.output.videos:
        print(f"Processing video - Title: {video.title}, URL: {video.url}")
        # Create a safe filename by replacing problematic characters
        safe_title = video.title.replace('/', '-').replace('\\', '-')
        output_filename = f"{safe_title}.mp4"

        try:
            # Try to download the video
            print(f"Downloading {video.title}...")
            download_result = download(video.url, output_path=output_filename, format="best")

            # Check if file exists before uploading
            if os.path.exists(output_filename):
                print(f"Upload to Video Jungle: {video.title}")
                vj.assets.upload_asset(
                    name=video.title,
                    description=f"{video.title}",
                    project_id=project.id,
                    filename=output_filename,
                )
                successful_videos += 1
                # Optionally, you can delete the local file after uploading
                os.remove(output_filename)
            else:
                print(f"Error: Download failed or file not found for {video.title}")
                failed_videos.append(video.title)

        except Exception as e:
            print(f"Error processing {video.title}: {e}")
            failed_videos.append(video.title)
            continue  # Skip to the next video

    # Summary
    print(f"\nSummary: Successfully processed {successful_videos} videos")
    if failed_videos:
        print(f"Failed to process {len(failed_videos)} videos: {', '.join(failed_videos)}")
    time.sleep(10) # wait for analysis to finish
    # Next we can use the project info to generate a rough cut
    async with edit_agent.run_mcp_servers():
        print("Video Editing Agent is now running")
        result = await edit_agent.run(f"can you use the video assets in the project_id '{project.id}' to create a single edit incorporating all the videos? be sure to not render the final video, just create the edit. if any outdoor scenes, show them first.",
                                      )#usage_limits=UsageLimits(request_limit=3))
    print(result)
    # below is not necessary because open the edit in the browser is default behavior
    vj.edits.open_in_browser(project.id, result.output.edit_id)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())