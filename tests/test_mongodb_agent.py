import asyncio, sys, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from agent import run_agent
from dotenv import load_dotenv

load_dotenv()

async def main():
    env = os.environ.copy()
    env["MDB_MCP_CONNECTION_STRING"] = os.getenv("MONGODB_URI")

    # Windows needs .cmd extension for globally installed npm packages
    command = "mongodb-mcp-server.cmd" if sys.platform == "win32" else "mongodb-mcp-server"

    server_params = StdioServerParameters(
        command=command,
        args=[],
        env=env
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP session ready\n")

            tests = [
                "Follow Brazil for me",
                "What teams am I following?",
                "Remind me 1 hour before Brazil's next match on June 18 2026",
                "Show me my reminders",
            ]

            for message in tests:
                print(f"\n{'='*50}")
                print(f"Query: {message}")
                print(f"{'='*50}")
                result = await run_agent(message, mcp_session=session, user_id="test_user")
                print(f"Answer: {result}")

asyncio.run(main())