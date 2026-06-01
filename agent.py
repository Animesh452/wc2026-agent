from google import genai
from google.genai import types
from tools.espn import (
    get_upcoming_matches, get_recent_results,
    get_group_standings, get_team_info
)
from tools.mongodb_mcp import (
    follow_team, get_followed_teams,
    save_reminder, get_reminders
)
from dotenv import load_dotenv
import os, json

load_dotenv()

client = genai.Client(
    vertexai=True,
    project=os.getenv("GCP_PROJECT_ID"),
    location="global"
)

TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_upcoming_matches",
        description="Get upcoming World Cup 2026 matches. Optionally filter by team name.",
        parameters={
            "type": "object",
            "properties": {
                "team": {"type": "string", "description": "Team name to filter by (optional)"},
                "days": {"type": "integer", "description": "Number of days ahead to look (default 7)"}
            }
        }
    ),
    types.FunctionDeclaration(
        name="get_recent_results",
        description="Get recent World Cup 2026 match results for a specific team.",
        parameters={
            "type": "object",
            "properties": {
                "team": {"type": "string", "description": "Team name"},
                "n": {"type": "integer", "description": "Number of results to return (default 5)"}
            },
            "required": ["team"]
        }
    ),
    types.FunctionDeclaration(
        name="get_group_standings",
        description="Get current World Cup 2026 group stage standings.",
        parameters={
            "type": "object",
            "properties": {
                "group": {"type": "string", "description": "Group letter e.g. A, B (optional)"}
            }
        }
    ),
    types.FunctionDeclaration(
        name="get_team_info",
        description="Get information about a World Cup 2026 team.",
        parameters={
            "type": "object",
            "properties": {
                "team": {"type": "string", "description": "Team name"}
            },
            "required": ["team"]
        }
    ),
    types.FunctionDeclaration(
        name="follow_team",
        description="Save a team to the user's followed teams list. Use when user says they want to follow or track a team.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "team_name": {"type": "string", "description": "Name of the team to follow"}
            },
            "required": ["user_id", "team_name"]
        }
    ),
    types.FunctionDeclaration(
        name="get_followed_teams",
        description="Get the list of teams a user is currently following.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"}
            },
            "required": ["user_id"]
        }
    ),
    types.FunctionDeclaration(
        name="save_reminder",
        description="Save a match reminder for a user. Use when user wants to be reminded before a match.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "team": {"type": "string", "description": "Team to set reminder for"},
                "match_date": {"type": "string", "description": "Date/time of the match"},
                "minutes_before": {"type": "integer", "description": "Minutes before match to remind (default 60)"}
            },
            "required": ["user_id", "team", "match_date"]
        }
    ),
    types.FunctionDeclaration(
        name="get_reminders",
        description="Get all upcoming reminders for a user.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"}
            },
            "required": ["user_id"]
        }
    ),
]

# Sync tools execute locally
SYNC_TOOLS = {
    "get_upcoming_matches": get_upcoming_matches,
    "get_recent_results": get_recent_results,
    "get_group_standings": get_group_standings,
    "get_team_info": get_team_info,
}

# Async tools go through MCP session
ASYNC_TOOLS = {
    "follow_team": follow_team,
    "get_followed_teams": get_followed_teams,
    "save_reminder": save_reminder,
    "get_reminders": get_reminders,
}


async def run_agent(user_message: str, mcp_session=None, user_id: str = "default_user"):
    # Create config here so system instruction includes the actual user_id
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
        system_instruction=(
            f"You are MatchDay, a World Cup 2026 AI assistant. "
            f"The current user's ID is '{user_id}'. "
            f"Always use this exact user_id when calling tools that require it. "
            f"Never ask the user for their user_id."
        )
    )

    contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]

    while True:
        # Using async Gemini client since we're in async context
        response = await client.aio.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=contents,
            config=config
        )

        candidate = response.candidates[0]
        function_calls = [p for p in candidate.content.parts if p.function_call]

        if not function_calls:
            return " ".join(p.text for p in candidate.content.parts if p.text)

        contents.append(candidate.content)

        fn_response_parts = []
        for part in function_calls:
            fc = part.function_call
            args = dict(fc.args)
            print(f"  → calling {fc.name}({args})")

            if fc.name in SYNC_TOOLS:
                result = SYNC_TOOLS[fc.name](**args)
            elif fc.name in ASYNC_TOOLS and mcp_session:
                result = await ASYNC_TOOLS[fc.name](mcp_session, **args)
            else:
                result = f"Tool {fc.name} not available"

            fn_response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response={"result": json.dumps(result, default=str)}
                    )
                )
            )

        contents.append(types.Content(role="user", parts=fn_response_parts))