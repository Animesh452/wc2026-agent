import json, re, os
from datetime import datetime


def extract_mcp_data(result):
    try:
        for content_item in result.content:
            text = content_item.text
            start = text.find('[')
            end = text.rfind(']') + 1
            if start != -1 and end > start:
                data = json.loads(text[start:end])
                if isinstance(data, list) and len(data) > 0:
                    return data
        return []
    except Exception as e:
        print(f"  extract error: {e}")
        return []


async def ensure_connected(session):
    pass


async def follow_team(session, user_id: str, team_name: str):
    await ensure_connected(session)
    try:
        result = await session.call_tool("update-many", {
            "database": "wc2026",
            "collection": "users",
            "filter": {"user_id": user_id},
            "update": {"$addToSet": {"followed_teams": team_name}},
            "upsert": True
        })
        print(f"  follow_team result: {result.content[0].text if result.content else 'no content'}")
        return f"Now following {team_name}"
    except Exception as e:
        print(f"  follow_team error: {e}")
        return f"Error following {team_name}: {e}"


async def get_followed_teams(session, user_id: str):
    result = await session.call_tool("find", {
        "database": "wc2026",
        "collection": "users",
        "filter": {"user_id": user_id},
        "limit": 1
    })
    docs = extract_mcp_data(result)
    if docs and isinstance(docs, list):
        return {"followed_teams": docs[0].get("followed_teams", [])}
    return {"followed_teams": []}


async def save_reminder(session, user_id: str, team: str, match_date: str, minutes_before: int = 60):
    await ensure_connected(session)
    try:
        result = await session.call_tool("insert-many", {
            "database": "wc2026",
            "collection": "reminders",
            "documents": [{
                "user_id": user_id,
                "team": team,
                "match_date": match_date,
                "minutes_before": minutes_before,
                "created_at": datetime.now().isoformat(),
                "sent": False
            }]
        })
        print(f"  save_reminder result: {result.content[0].text if result.content else 'no content'}")
        return f"Reminder set: {minutes_before} minutes before {team}'s match on {match_date}"
    except Exception as e:
        print(f"  save_reminder error: {e}")
        return f"Error saving reminder: {e}"


async def get_reminders(session, user_id: str):
    result = await session.call_tool("find", {
        "database": "wc2026",
        "collection": "reminders",
        "filter": {"user_id": user_id, "sent": False}
    })
    docs = extract_mcp_data(result)
    return {"reminders": docs if isinstance(docs, list) else []}