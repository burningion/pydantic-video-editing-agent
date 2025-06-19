from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.mcp import MCPServerStdio
import logfire
import os

if not os.environ.get("VJ_API_KEY"):
    raise ValueError("VJ_API_KEY environment variable is not set.")

if not os.environ.get("SERPER_API_KEY"):
    raise ValueError("SERPER_API_KEY environment variable is not set.")

vj_api_key = os.environ["VJ_API_KEY"]
serper_api_key = os.environ["SERPER_API_KEY"] 
logfire.configure()

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
vj_server = MCPServerStdio(  
    'uvx',
    args=[
        '-p', '3.11',
        '--from', 'video_editor_mcp@latest',
        'video-editor-mcp'
    ],
    env={
        'VJ_API_KEY': vj_api_key,
    },
    timeout=30
)


model = AnthropicModel("claude-sonnet-4-20250514")

agent = Agent(  
    model=model,
    system_prompt='You are an expert video editor. ' \
    'You can answer questions, download and analyze videos, and create rough video edits using remote videos.',  
    mcp_servers=[vj_server],
    instrument=True,
)
async def main():
    async with agent.run_mcp_servers():
        print("Agent is running")
        result = await agent.run("can you search my videos for all skateboarding clips? Id like a summary and list of all of them.")  
    print(result.output)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())