import asyncio, random
from google import genai
from google.genai import types, errors
from tools.espn import (
    get_upcoming_matches, get_recent_results,
    get_group_standings, get_team_info, get_team_schedule
)
from tools.mongodb_mcp import (
    follow_team, get_followed_teams,
    save_reminder, get_reminders,
    delete_reminders_for_team, delete_all_reminders, unfollow_team
)
from tools.predictions import (
    save_prediction, get_predictions, delete_prediction,
    score_predictions, get_leaderboard
)
from tools.venues import search_venue_info
from tools.web_search import web_search, head_to_head
from tools.world_cup import get_world_cup_results, STAGE_FILTERS
from dotenv import load_dotenv
from datetime import datetime, timezone
from pathlib import Path
import os, json

load_dotenv()

SYSTEM_INSTRUCTION_PATH = Path(__file__).parent / "prompts" / "system_instruction.md"
SYSTEM_INSTRUCTION_TEMPLATE = SYSTEM_INSTRUCTION_PATH.read_text(encoding="utf-8")
for placeholder in ("{{user_id}}", "{{today}}"):
    if placeholder not in SYSTEM_INSTRUCTION_TEMPLATE:
        raise RuntimeError(f"{SYSTEM_INSTRUCTION_PATH} is missing the {placeholder} placeholder")


def build_system_instruction(user_id: str) -> str:
    """Fill the system instruction template with today's UTC date and the user ID."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d (%A)")
    return (
        SYSTEM_INSTRUCTION_TEMPLATE
        .replace("{{today}}", today)
        .replace("{{user_id}}", user_id)
    )

client = genai.Client(
    vertexai=True,
    project=os.getenv("GCP_PROJECT_ID"),
    location="global"
)


MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
RETRYABLE_CODES = {429, 500, 503}


async def generate_with_retry(contents, config, max_attempts=4):
    for attempt in range(1, max_attempts + 1):
        try:
            return await client.aio.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
        except errors.APIError as e:
            if e.code not in RETRYABLE_CODES or attempt == max_attempts:
                raise
            delay = (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"  Gemini {e.code}, retrying in {delay:.1f}s (attempt {attempt}/{max_attempts})")
            await asyncio.sleep(delay)


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
        name="get_world_cup_results",
        description=(
            "Results of the completed FIFA World Cup 2026 (June 11 to July 19, 2026): all 104 matches "
            "with date, stage, score, extra time or penalties, winner, and venue. With a team, also "
            "returns how far that team got. Use for who won the World Cup (stage='final'), how a team "
            "did (team='Brazil'), a round's results, or the knockout path (stage='knockout'). "
            "Prefer filtering by team or stage over fetching everything. "
            "Not for goal scorers, player stats, lineups, or group standings: use web_search for those. "
            "Not for upcoming fixtures."
        ),
        parameters={
            "type": "object",
            "properties": {
                "team": {"type": "string", "description": "National team name, e.g. 'Brazil', 'United States' (optional)"},
                "stage": {
                    "type": "string",
                    "enum": STAGE_FILTERS,
                    "description": "Stage filter (optional). 'knockout' means every match after the group stage.",
                },
            },
        }
    ),
    types.FunctionDeclaration(
        name="follow_team",
        description="Save a team to the user's followed teams list.",
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
    types.FunctionDeclaration(
        name="search_venue_info",
        description="Search for information about World Cup 2026 host city venues, fan zones, transport, and local tips.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query about a venue or host city"}
            },
            "required": ["query"]
        }
    ),
    types.FunctionDeclaration(
        name="get_team_schedule",
        description="Get a team's full schedule with dates and venues, useful for trip planning. Returns matches over a longer time window.",
        parameters={
            "type": "object",
            "properties": {
                "team": {"type": "string", "description": "Team name"},
                "days": {"type": "integer", "description": "Days ahead to look (default 45 for full group stage)"}
            },
            "required": ["team"]
        }
    ),
    types.FunctionDeclaration(
        name="save_reminder",
        description="Save a match reminder for a user. Optionally include an email to receive a notification.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "team": {"type": "string", "description": "Team to set reminder for"},
                "match_date": {"type": "string", "description": "Date/time of the match"},
                "minutes_before": {"type": "integer", "description": "Minutes before match to remind (default 60)"},
                "email": {"type": "string", "description": "Email address to send the reminder to (optional)"}
            },
            "required": ["user_id", "team", "match_date"]
        }
    ),
    types.FunctionDeclaration(
        name="delete_reminders_for_team",
        description="Delete all reminders for a specific team.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "team": {"type": "string", "description": "Team name whose reminders should be deleted"}
            },
            "required": ["user_id", "team"]
        }
    ),
    types.FunctionDeclaration(
        name="delete_all_reminders",
        description="Delete all of a user's reminders. Can optionally exclude specific teams (e.g. delete all except Brazil).",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "except_teams": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of team names whose reminders should be kept"
                }
            },
            "required": ["user_id"]
        }
    ),
    types.FunctionDeclaration(
        name="unfollow_team",
        description="Remove a team from the user's followed teams list.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "The user's ID"},
                "team_name": {"type": "string", "description": "Team to unfollow"}
            },
            "required": ["user_id", "team_name"]
        }
    ),
    types.FunctionDeclaration(
    name="save_prediction",
    description="Save a user's prediction for a specific World Cup match. Requires match_id, both team names, predicted scores, and ideally the match date.",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "match_id": {"type": "string", "description": "ESPN match ID — get this from get_upcoming_matches"},
            "home_team": {"type": "string"},
            "away_team": {"type": "string"},
            "predicted_home_score": {"type": "integer"},
            "predicted_away_score": {"type": "integer"},
            "match_date": {"type": "string", "description": "ISO date of the match (optional)"}
        },
        "required": ["user_id", "match_id", "home_team", "away_team", "predicted_home_score", "predicted_away_score"]
    }
    ),
    types.FunctionDeclaration(
        name="get_predictions",
        description="Get a user's match predictions. Optionally filter by status: 'all', 'pending', or 'completed'.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "status": {"type": "string", "description": "Filter: 'all' (default), 'pending', or 'completed'"}
            },
            "required": ["user_id"]
        }
    ),
    types.FunctionDeclaration(
        name="delete_prediction",
        description="Delete a user's prediction for a specific match.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "match_id": {"type": "string"}
            },
            "required": ["user_id", "match_id"]
        }
    ),
    types.FunctionDeclaration(
        name="score_predictions",
        description="Fetch actual match results from ESPN and score the user's pending predictions. Returns a breakdown of points earned (3 for exact score, 1 for correct winner, 0 for wrong).",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string"}
            },
            "required": ["user_id"]
        }
    ),
    types.FunctionDeclaration(
        name="get_leaderboard",
        description="Get the top users ranked by total prediction points across all users.",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of top users to return (default 10)"}
            }
        }
    ),
    types.FunctionDeclaration(
        name="web_search",
        description="Search the web for current information not available in other tools. Use for news, injuries, recent events, transfer rumors, or anything time-sensitive.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"]
        }
    ),
    types.FunctionDeclaration(
        name="head_to_head",
        description="Get historical head-to-head record between two football teams.",
        parameters={
            "type": "object",
            "properties": {
                "team_a": {"type": "string"},
                "team_b": {"type": "string"}
            },
            "required": ["team_a", "team_b"]
        }
    ),
]

SYNC_TOOLS = {
    "get_upcoming_matches": get_upcoming_matches,
    "get_recent_results": get_recent_results,
    "get_group_standings": get_group_standings,
    "get_team_info": get_team_info,
    "search_venue_info": search_venue_info,
    "get_team_schedule": get_team_schedule,
    "web_search": web_search,
    "head_to_head": head_to_head,
    "get_world_cup_results": get_world_cup_results,
}

ASYNC_TOOLS = {
    "follow_team": follow_team,
    "get_followed_teams": get_followed_teams,
    "save_reminder": save_reminder,
    "get_reminders": get_reminders,
    "delete_reminders_for_team": delete_reminders_for_team,
    "delete_all_reminders": delete_all_reminders,
    "unfollow_team": unfollow_team,
    "save_prediction": save_prediction,
    "get_predictions": get_predictions,
    "delete_prediction": delete_prediction,
    "score_predictions": score_predictions,
    "get_leaderboard": get_leaderboard,
}


# Conversation history per user, kept in memory
CONVERSATIONS = {}

async def run_agent(user_message: str, mcp_session=None, user_id: str = "default_user"):
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
        system_instruction=build_system_instruction(user_id)
    )

    # Get or create conversation history for this user
    if user_id not in CONVERSATIONS:
        CONVERSATIONS[user_id] = []

    # Trim before adding the new turn
    if len(CONVERSATIONS[user_id]) > 40:
        CONVERSATIONS[user_id] = CONVERSATIONS[user_id][-40:]

    contents = CONVERSATIONS[user_id]
    start_len = len(contents)
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    try:
        while True:
            response = await generate_with_retry(contents, config)

            candidate = response.candidates[0]
            function_calls = [p for p in candidate.content.parts if p.function_call]

            if not function_calls:
                text = " ".join(p.text for p in candidate.content.parts if p.text)
                contents.append(candidate.content)
                return text

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
    
    except Exception:
        del contents[start_len:]  # roll back the failed turn
        raise