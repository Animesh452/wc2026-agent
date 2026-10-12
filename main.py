from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from agent import run_agent
from tools.mongodb_mcp import get_followed_teams, get_reminders
from tools.reminder_worker import reminder_worker
from dotenv import load_dotenv
import os, sys, asyncio

load_dotenv()

mcp_session = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mcp_session

    command = "mongodb-mcp-server.cmd" if sys.platform == "win32" else "mongodb-mcp-server"

    env = os.environ.copy()
    mongodb_uri = os.getenv("MONGODB_URI", "").strip()
    print(f"MongoDB URI present: {bool(mongodb_uri)}")
    print(f"MongoDB URI preview: {mongodb_uri[:30]}...{mongodb_uri[-10:]}")
    
    # Force pass to both variables the server checks for
    env["MDB_MCP_CONNECTION_STRING"] = mongodb_uri
    env["MONGODB_URI"] = mongodb_uri

    # FIX HERE: Remove the args list completely so it falls back to your clean env configuration
    server_params = StdioServerParameters(
        command=command,
        args=[],  # Empty list bypasses the deprecated argument logic completely
        env=env
    )

    mcp_ready = asyncio.Event()

    async def start_mcp():
        global mcp_session
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    mcp_session = session
                    print("MCP session ready")
                    mcp_ready.set()
                    await asyncio.sleep(float('inf'))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"MCP error: {e}")
            mcp_ready.set()

    task = asyncio.create_task(start_mcp())
    await mcp_ready.wait()

    # Start background reminder worker
    worker_task = asyncio.create_task(reminder_worker())
    print("Reminder worker started")

    yield

    worker_task.cancel()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    finally:
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
    try:
        response = await run_agent(
            request.message,
            mcp_session=mcp_session,
            user_id=request.user_id
        )
    except Exception as e:
        print(f"  /chat failed: {e}")
        response = "I'm having trouble reaching my AI backend right now. Please try again in a moment."
    return {"response": response}


@app.get("/user/{user_id}/teams")
async def get_teams(user_id: str):
    result = await get_followed_teams(mcp_session, user_id)
    return result


@app.get("/user/{user_id}/reminders")
async def get_user_reminders(user_id: str):
    result = await get_reminders(mcp_session, user_id)
    return result

@app.delete("/user/{user_id}/conversation")
async def clear_conversation(user_id: str):
    from agent import CONVERSATIONS
    CONVERSATIONS.pop(user_id, None)
    return {"cleared": True}

@app.get("/bracket", response_class=HTMLResponse)
async def bracket():
    with open("static/bracket.html") as f:
        return f.read()


@app.get("/api/bracket-data")
async def bracket_data():
    from tools.espn import get_upcoming_matches
    matches = get_upcoming_matches(days=40)
    if isinstance(matches, str):
        return {"matches": []}
    
    grouped = {}
    for m in matches:
        date_key = m.get("date", "")[:10]
        if date_key not in grouped:
            grouped[date_key] = []
        grouped[date_key].append(m)
    
    return {"matches": matches, "by_date": grouped}