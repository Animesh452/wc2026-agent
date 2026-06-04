import os
from google import genai
from google.genai import types

_client = genai.Client(
    vertexai=True,
    project=os.getenv("GCP_PROJECT_ID"),
    location="global"
)


def web_search(query: str) -> str:
    """Use Gemini's built-in Google Search grounding for current/news queries."""
    try:
        response = _client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text = " ".join(p.text for p in response.candidates[0].content.parts if p.text)
        return text or "No results found"
    except Exception as e:
        print(f"  web_search error: {e}")
        return f"Search error: {e}"


def head_to_head(team_a: str, team_b: str) -> str:
    """Search for historical head-to-head record between two teams."""
    query = (
        f"What is the all-time head to head record between {team_a} and {team_b} "
        f"in international football? Include total wins for each side, draws, "
        f"notable matches, and their most recent meeting."
    )
    return web_search(query)