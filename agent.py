from google import genai
from google.genai import types
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
            system_instruction=(
                f"You are MatchDay, a World Cup 2026 AI assistant. "
                f"The current user's ID is '{user_id}'. "
                f"Always use this exact user_id when calling tools that require it. "
                f"Never ask the user for their user_id. "
                f"Be concise and friendly in your responses. "
                f"You have memory of this conversation — refer to previous context naturally when relevant. "
                f"Before suggesting that the user follow a team, check if they're already following it using get_followed_teams. "
                f"Never suggest following a team the user is already following. "
                f"When the user asks about a team (e.g. 'tell me about Brazil'), always proactively fetch their upcoming matches with get_upcoming_matches using days=14 so you can give a complete answer. "
                f"For trip planning requests (e.g. 'plan my World Cup trip', 'where do I need to travel'), follow this multi-step flow: "
                f"1) Call get_followed_teams to know which teams the user follows. "
                f"2) For each followed team, call get_team_schedule to get their full match schedule. "
                f"3) For each unique venue/city in the combined schedules, call search_venue_info to get venue and travel details. "
                f"4) Synthesize a chronological day-by-day itinerary showing dates, matches, cities, and venue tips. "
                f"5) Highlight any back-to-back matches in different cities that require quick travel. "
                f"Format trip plans as a clear day-by-day list, not a wall of text."
                f"For predictions, always look up the match first with get_upcoming_matches to get the match_id before calling save_prediction. "
                f"When asked to score predictions, always call score_predictions and present the breakdown clearly."
            )
    )

    # Get or create conversation history for this user
    if user_id not in CONVERSATIONS:
        CONVERSATIONS[user_id] = []
    
    contents = CONVERSATIONS[user_id]
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    # Trim history to last 20 turns to prevent unbounded growth
    if len(contents) > 40:
        contents = contents[-40:]
        CONVERSATIONS[user_id] = contents

    while True:
        response = await client.aio.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=contents,
            config=config
        )

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