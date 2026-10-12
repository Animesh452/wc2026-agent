import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
import os

load_dotenv()

async def test_mcp():
    env = os.environ.copy()
    env["MDB_MCP_CONNECTION_STRING"] = os.getenv("MONGODB_URI")

    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "mongodb-mcp-server@latest"],
        env=env
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print(f"\nAvailable tools ({len(tools.tools)} total):")
            for tool in tools.tools:
                print(f"  - {tool.name}")

asyncio.run(test_mcp())