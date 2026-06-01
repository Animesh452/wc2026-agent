from google import genai
from google.genai import types
from tools.espn import (
    get_upcoming_matches, get_recent_results,
    get_group_standings, get_team_info
)
from dotenv import load_dotenv
import os, json

load_dotenv()

client = genai.Client(
    vertexai=True,
    project=os.getenv("GCP_PROJECT_ID"),
    location="global"
)

# Tool implementations map
TOOL_IMPLEMENTATIONS = {
    "get_upcoming_matches": get_upcoming_matches,
    "get_recent_results": get_recent_results,
    "get_group_standings": get_group_standings,
    "get_team_info": get_team_info,
}

# Tool declarations for Gemini
TOOLS = [types.Tool(function_declarations=[
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
                "group": {"type": "string", "description": "Group letter e.g. 'A', 'B' (optional)"}
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
])]

CONFIG = types.GenerateContentConfig(tools=TOOLS)


def run_agent(user_message):
    contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]

    while True:
        response = client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=contents,
            config=CONFIG
        )

        candidate = response.candidates[0]
        function_calls = [p for p in candidate.content.parts if p.function_call]

        if not function_calls:
            text = " ".join(p.text for p in candidate.content.parts if p.text)
            return text

        # Append model turn
        contents.append(candidate.content)

        # Execute tools and collect responses
        fn_response_parts = []
        for part in function_calls:
            fc = part.function_call
            print(f"  → calling {fc.name}({dict(fc.args)})")
            func = TOOL_IMPLEMENTATIONS.get(fc.name)
            result = func(**dict(fc.args)) if func else "Tool not found"
            fn_response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response={"result": json.dumps(result, default=str)}
                    )
                )
            )

        # Append tool results
        contents.append(types.Content(role="user", parts=fn_response_parts))