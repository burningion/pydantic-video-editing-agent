
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.mcp import MCPServerStdio

from pydantic import BaseModel, Field
from typing import List
from utils.tools import download, extract_info
import logfire
import os

if not os.environ.get("VJ_API_KEY"):
    raise ValueError("VJ_API_KEY environment variable is not set.")

if not os.environ.get("SERPER_API_KEY"):
    raise ValueError("SERPER_API_KEY environment variable is not set.")

vj_api_key = os.environ["VJ_API_KEY"]
serper_api_key = os.environ["SERPER_API_KEY"]

logfire.configure()

vj_server = MCPServerStdio(  
    'uvx',
    args=[
        '-p', '3.11',
        '--from', 'video_editor_mcp@latest',
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

model = AnthropicModel("claude-3-7-sonnet-20250219")

agent = Agent(  
    model=model,
    system_prompt='You are an expert video editor. ' \
    'You can answer questions, download and analyze videos, and create rough video edits using remote videos.',  
    mcp_servers=[vj_server, serper_server],
    output_type=VideoList,
    instrument=True,
)

async def main():
    async with agent.run_mcp_servers():
        print("Agent is running")
        result = await agent.run("can you search the web for the newest clips about nathan fielder? I'd like a list of 5 urls with video clips")  
    print(result)

    for video in result.output.videos:
        print(f"Title: {video.title}, URL: {video.url}")
        # Download the video
        download(video.url, output_path="downloads", format="best")
        # Extract info from the video
        info = extract_info(video.url)
        print(f"Video Info: {info}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())