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
import random

if not os.environ.get("VJ_API_KEY"):
    raise ValueError("VJ_API_KEY environment variable is not set.")

if not os.environ.get("SERPER_API_KEY"):
    raise ValueError("SERPER_API_KEY environment variable is not set.")

vj_api_key = os.environ["VJ_API_KEY"]
serper_api_key = os.environ["SERPER_API_KEY"]

logfire.configure()
logfire.instrument_openai()

vj = ApiClient(vj_api_key) # video jungle api client

vj_server = MCPServerStdio(  
    'uvx',
    args=[
        '-p', '3.11',
        '--from', 'video_editor_mcp@0.1.33',
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

class ClipParameters(BaseModel):
    clip_topics: List[str]
    latest_episode_topic: str

class VideoItem(BaseModel):
    url: str
    title: str

class VideoList(BaseModel):
    videos: List[VideoItem] = Field(default_factory=list)

class VideoEdit(BaseModel):
    project_id: str
    edit_id: str

def search_and_render_audio():
    # Let's search the web for some up to date Nathan Fielder episode topics / controversies
    # and generate paramters for our prompt
    workflow_client = Anthropic()
    client = instructor.from_anthropic(workflow_client)  # Initialize the instructor with Anthropic client
    
    search_prompt = """
    I'm trying to come up with an interesting spoken dialogue prompt about nathan fielder's the rehearsal season 2. 
    can you help me come up with ideas for what might be interesting? you can search the web to get up to date info.
    don't give me a summary of the show, or the show as a topic. instead just give me a list of topics or controversies that might be interesting to discuss.
    the latest episode topic should be a paragraph or two about the latest episode, and the clip topics should be a list of 5-10 topics that are interesting to discuss.
    """

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": search_prompt,
            }
        ],
        tools=[{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 5
        }],
        response_model=ClipParameters,
    )

    print(f"latest episode topic: {resp.latest_episode_topic}")
    print("clip topics: ")
    for topic in resp.clip_topics:
        print(f"- {topic}")

    # First, let's list the types of generative media we can create
    # on video jungle (e.g. prompt-to-video, prompt-to-speech, etc.)
    # This will list all the generative media options available in your account
    generative_media = vj.scripts.list_options()

    print("Generative media options:")
    for media in generative_media:
        print(f"- {media.key}: {media.description}")

    # For this example, we'll use the key for generating a voiceover
    # (Would otherwise be media.key) from our list above
    script_key = "prompt-to-speech" 

    # A prompt is used to describe the generative task you want to perform
    prompt = vj.prompts.generate(task="You are a 'The Rehearsal' episode analyzer, diving deep into meta idea to discuss. You aim for 30 second long read script concept that is funny and insightful. You should make the viewer reflect on the themes of the show.",
                                parameters=["clip topic", "latest episode topic"])

    # Now we can create a project to hold our generated media
    project = vj.projects.create(name="Nathan Fielder Clips", description="Clips from Nathan Fielder episodes", prompt_id=prompt.id, generation_method=script_key)
    # Grab the script ID from the project for prompt-to-speech generation
    script_id = project.scripts[0].id
    print(f"Created project: {project.name} with ID: {project.id} and script ID: {script_id}")

    # Pick a random topic from the list of clip topics
    topic = random.choice(resp.clip_topics)
    print(f"Selected topic: {topic}")
    # We can now generate a prompt-to-speech asset:
    audio = vj.projects.generate(script_id=script_id, 
                                project_id=project.id,
                                parameters={"clip topic": topic,
                                            "latest episode topic": resp.latest_episode_topic})
    print(f"Generated voiceover from topics with asset id: {audio['asset_id']}")
    return (project.id, audio['asset_id'])

# for flash preview
cheap_model = GeminiModel("gemini-2.5-flash-preview-05-20")
# for pro preview
#model = GeminiModel("gemini-2.5-pro-preview-05-06")
good_model = AnthropicModel("claude-sonnet-4-20250514")

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

async def async_main(project_id: Optional[str] = None, asset_id: Optional[str] = None):
    
    if project_id:
        
        # Use existing project TODO: not implemented yet
        print(f"Using existing project ID: {project_id}")
        project = vj.projects.get(project_id)
        print(f"Project name: {project.name}")
        async with edit_agent.run_mcp_servers():
            asset = vj.assets.get(asset_id)
            asset_length = asset.create_parameters['metadata']['duration_seconds']
            print("Video Editing Agent is now running")
            result = await edit_agent.run(f"""can you use the video assets in the project_id '{project.id}' to create a
                                      single edit incorporating all the assets that are videos in there? use the audio asset with id '{asset_id}' as the voiceover for the edit. it should have a start time of 0 and an end time of {asset_length} seconds.
                                      be sure to not render the final video, just create the edit. if there are any outdoor scenes,
                                      show them first. also, only use the assets in the project in the edit. you should grab 
                                      two asset's info from the project at a time, and use multiple requests from the get-project-assets 
                                      tool if you use it if necessary. only show each video once in the edit. remember, each asset in the edit should have a start_time and an end_time where something interesting happens,
                                      and the total duration of these start_time and stop_time added together for the video edits should match the asset's duration, {asset_length} seconds.
                                      think hard about when to start and stop each video asset in the edit, and how to make it flow well with the voiceover. MAKE SURE TO DOUBLE CHECK THAT THE TOTAL DURATION OF THE VIDEO EDIT IS THE SAME AS THE VOICEOVER DURATION WHICH IS {asset_length} SECONDS. 
                                      BE SURE TO SET ALL VIDEO ASSET's audio_level TO 0 so that the voiceover is the only audio in the edit. 
                                      remember, you MUST use the AUDIO asset in the project as the voiceover for the edit, and you can UPDATE the EDIT if you need to.""",
                                        usage_limits=UsageLimits(request_limit=10))
        print(f"resultant project is: {result.output.project_id} and {result.output.edit_id}")
        return
    else:
        # Create new project with videos

        successful_videos = 0
        failed_videos = []
        processed_urls = set()  # Keep track of URLs we've already tried
        search_attempts = 0
        max_search_attempts = 5  # Maximum number of search attempts
        project_id, audio_asset_id = search_and_render_audio()
        project = vj.projects.get(project_id)
        while successful_videos < 5 and search_attempts < max_search_attempts:
            search_attempts += 1
            
            # Request more videos than needed to account for failures
            videos_to_request = 8 if search_attempts == 1 else 10
            
            async with search_agent.run_mcp_servers():
                print(f"\nSearch attempt {search_attempts}: Searching for Nathan Fielder clips...")
                search_query = f"can you search the web for the newest clips about nathan fielder? I'd like a list of {videos_to_request} urls with video clips. it's may 30, 2025 by the way, and nathan is doing a show called 'the rehearsal'."
                if search_attempts > 1:
                    search_query += " Please find different clips than before."
                
                result = await search_agent.run(search_query, usage_limits=UsageLimits(request_limit=5))
            
            print(f"Found {len(result.output.videos)} videos in search attempt {search_attempts}")
            
            for video in result.output.videos:
                # Skip if we've already tried this URL
                if video.url in processed_urls:
                    print(f"Skipping already processed URL: {video.url}")
                    continue
                
                processed_urls.add(video.url)
                
                # Stop if we have enough videos
                if successful_videos >= 5:
                    break
                
                print(f"Processing video - Title: {video.title}, URL: {video.url}")
                # Create a safe filename by replacing problematic characters
                safe_title = video.title.replace('/', '-').replace('\\', '-')
                output_filename = f"{safe_title}.mp4"

                try:
                    # Try to download the video
                    print(f"Downloading {video.title}...")
                    download(video.url, output_path=output_filename, format="best")

                    # Check if file exists before uploading
                    if os.path.exists(output_filename):
                        print(f"Upload to Video Jungle: {video.title}")
                        project.upload_asset(
                            name=video.title,
                            description=f"Agent downloaded video: {video.title}",
                            filename=output_filename,
                        )
                        successful_videos += 1
                        print(f"Successfully uploaded video {successful_videos}/5")
                        # Optionally, you can delete the local file after uploading
                        os.remove(output_filename)
                    else:
                        print(f"Error: Download failed or file not found for {video.title}")
                        failed_videos.append(video.title)

                except Exception as e:
                    # Only print error message if it's not empty
                    if str(e):
                        print(f"Error processing {video.title}: {e}")
                    else:
                        print(f"Error processing {video.title}")
                    failed_videos.append(video.title)
                    continue  # Skip to the next video

        # Summary
        print(f"\nFinal Summary: Successfully processed {successful_videos} videos after {search_attempts} search attempts")
        if failed_videos:
            print(f"Failed to process {len(failed_videos)} videos: {', '.join(failed_videos)}")
        
        if successful_videos < 5:
            print(f"\nWarning: Only managed to download {successful_videos} videos after {search_attempts} attempts")
        
        time.sleep(45) # wait 45 seconds for analysis to finish (we'll make this precise later)
    # Next we can use the project info to generate a rough cut
    
    async with edit_agent.run_mcp_servers():
        print("Video Editing Agent is now running")
        asset = vj.assets.get(audio_asset_id)
        asset_length = asset.create_parameters['metadata']['duration_seconds']
        result = await edit_agent.run(f"""can you use the video assets in the project_id '{project.id}' to create a
                                      single edit incorporating all the assets that are videos in there? use the audio asset with id '{audio_asset_id}' as the voiceover for the edit. it should have a start time of 0 and an end time of {asset_length} seconds.
                                      be sure to not render the final video, just create the edit. if there are any outdoor scenes,
                                      show them first. also, only use the assets in the project in the edit. you should grab 
                                      two asset's info from the project at a time, and use multiple requests from the get-project-assets 
                                      tool if you use it if necessary. only show each video once in the edit. remember, each asset in the edit should have a start_time and an end_time where something interesting happens,
                                      and the total duration of these start_time and stop_time added together for the video edits should match the asset's duration, {asset_length} seconds.
                                      think hard about when to start and stop each video asset in the edit, and how to make it flow well with the voiceover. MAKE SURE TO DOUBLE CHECK THAT THE TOTAL DURATION OF THE VIDEO EDIT IS THE SAME AS THE VOICEOVER DURATION WHICH IS {asset_length} SECONDS. 
                                      BE SURE TO SET ALL VIDEO ASSET's audio_level TO 0 so that the voiceover is the only audio in the edit. 
                                      remember, you MUST use the AUDIO asset in the project as the voiceover for the edit, and you can UPDATE the EDIT if you need to. """,
                                      usage_limits=UsageLimits(request_limit=14))
    print(f"resultant project is: {result.output.project_id} and {result.output.edit_id}")
    # below is not necessary because open the edit in the browser is default behavior
    # vj.edits.open_in_browser(project.id, result.output.edit_id)

@click.command()
@click.option('--project-id', '-p', help='Existing project ID to use instead of creating a new one')
@click.option('--asset-id', '-a', help='Audio asset ID to use for the edit')
def main(project_id: Optional[str] = None, asset_id: Optional[str] = None):
    import asyncio
    asyncio.run(async_main(project_id, asset_id))

if __name__ == "__main__":
    main()