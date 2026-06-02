from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from agent import run_agent
from tools.mongodb_mcp import get_followed_teams, get_reminders
from dotenv import load_dotenv
import os, sys

load_dotenv()

mcp_session = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_session
    env = os.environ.copy()
    env["MDB_MCP_CONNECTION_STRING"] = os.getenv("MONGODB_URI")

    command = "mongodb-mcp-server.cmd" if sys.platform == "win32" else "mongodb-mcp-server"

    server_params = StdioServerParameters(
        command=command,
        args=[],
        env=env
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_session = session
            print("MCP session ready")
            yield

    mcp_session = None


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    user_id: str
    message: str


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html") as f:
        return f.read()


@app.post("/chat")
async def chat(request: ChatRequest):
    response = await run_agent(
        request.message,
        mcp_session=mcp_session,
        user_id=request.user_id
    )
    return {"response": response}


@app.get("/user/{user_id}/teams")
async def get_teams(user_id: str):
    result = await get_followed_teams(mcp_session, user_id)
    return result


@app.get("/user/{user_id}/reminders")
async def get_user_reminders(user_id: str):
    result = await get_reminders(mcp_session, user_id)
    return result