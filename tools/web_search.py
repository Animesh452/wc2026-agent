from google.genai import types

from gemini_client import generate_with_retry

SEARCH_CONFIG = types.GenerateContentConfig(
    tools=[types.Tool(google_search=types.GoogleSearch())]
)


async def web_search(query: str) -> str:
    """Use Gemini's built-in Google Search grounding for current/news queries."""
    try:
        response = await generate_with_retry(query, SEARCH_CONFIG)
        text = " ".join(p.text for p in response.candidates[0].content.parts if p.text)
        return text or "No results found"
    except Exception as e:
        print(f"  web_search error: {e}")
        return f"Search error: {e}"


async def head_to_head(team_a: str, team_b: str) -> str:
    """Search for historical head-to-head record between two teams."""
    query = (
        f"What is the all-time head to head record between {team_a} and {team_b} "
        f"in international football? Include total wins for each side, draws, "
        f"notable matches, and their most recent meeting."
    )
    return await web_search(query)
