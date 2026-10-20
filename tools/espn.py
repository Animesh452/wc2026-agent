import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"


TEAM_ALIASES = {
    "usa": "United States",
    "u.s.a.": "United States",
    "us": "United States",
    "america": "United States",
    "uk": "England",
    "britain": "England",
    "great britain": "England",
    "south korea": "South Korea",
    "korea": "South Korea",
    "korea republic": "South Korea",
    "ivory coast": "Ivory Coast",
    "côte d'ivoire": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "turkey": "Türkiye",
    "czech republic": "Czechia",
    "uae": "United Arab Emirates",
    "dr congo": "Congo DR",
    "congo dr": "Congo DR",
    "democratic republic of the congo": "Congo DR",
    "bosnia": "Bosnia-Herzegovina",
    "bosnia and herzegovina": "Bosnia-Herzegovina",
    "cabo verde": "Cape Verde",
    "holland": "Netherlands",
    "ir iran": "Iran",
}


def normalize_team(team: str) -> str:
    if not team:
        return team
    return TEAM_ALIASES.get(team.lower().strip(), team)


def get_upcoming_matches(team=None, days=14):
    if team:
        team = normalize_team(team)

    dates = [(datetime.now() + timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]

    def fetch_day(date):
        try:
            r = requests.get(f"{BASE_URL}/scoreboard", params={"dates": date}, timeout=8)
            return r.json().get("events", [])
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=days) as executor:
        futures = {executor.submit(fetch_day, date): date for date in dates}
        all_events = []
        for future in concurrent.futures.as_completed(futures):
            all_events.extend(future.result())

    all_matches = []
    for e in all_events:
        comp = e.get("competitions", [{}])[0]
        teams = [c.get("team", {}).get("displayName", "")
                 for c in comp.get("competitors", [])]
        match = {
            "id": e.get("id"),
            "name": e.get("name"),
            "date": e.get("date"),
            "status": e.get("status", {}).get("type", {}).get("description"),
            "teams": teams,
            "venue": comp.get("venue", {}).get("fullName", "TBD")
        }
        if team:
            if any(team.lower() in t.lower() for t in teams):
                all_matches.append(match)
        else:
            all_matches.append(match)

    all_matches.sort(key=lambda x: x.get("date", ""))
    return all_matches if all_matches else f"No upcoming matches found for {team or 'any team'}"


def get_recent_results(team, n=5):
    if team:
        team = normalize_team(team)    
    results = []
    for i in range(1, 15):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            r = requests.get(f"{BASE_URL}/scoreboard", params={"dates": date}, timeout=10)
            events = r.json().get("events", [])
            for e in events:
                comp = e.get("competitions", [{}])[0]
                competitors = comp.get("competitors", [])
                teams = [c.get("team", {}).get("displayName", "") for c in competitors]
                if any(team.lower() in t.lower() for t in teams):
                    scores = {c.get("team", {}).get("displayName"): c.get("score", "?")
                              for c in competitors}
                    results.append({
                        "date": e.get("date"),
                        "name": e.get("name"),
                        "scores": scores,
                        "status": e.get("status", {}).get("type", {}).get("description")
                    })
        except Exception:
            continue
        if len(results) >= n:
            break
    return results if results else f"No recent results found for {team}"


def get_group_standings(group=None):
    try:
        r = requests.get(f"{BASE_URL}/standings", timeout=10)
        data = r.json()
        groups = data.get("standings", {}).get("entries", [])
        if group:
            groups = [g for g in groups if group.upper() in g.get("group", "").upper()]
        result = []
        for entry in groups[:20]:
            result.append({
                "team": entry.get("team", {}).get("displayName"),
                "group": entry.get("group"),
                "played": entry.get("stats", [{}])[0].get("value", 0),
                "points": next((s.get("value") for s in entry.get("stats", []) 
                               if s.get("name") == "points"), 0)
            })
        return result if result else "Standings not available yet"
    except Exception as e:
        return f"Could not fetch standings: {str(e)}"


def get_team_info(team):
    if team:
        team = normalize_team(team)
    try:
        r = requests.get(f"{BASE_URL}/teams", timeout=10)
        teams = r.json().get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
        for t in teams:
            t_data = t.get("team", {})
            if team.lower() in t_data.get("displayName", "").lower():
                return {
                    "name": t_data.get("displayName"),
                    "abbreviation": t_data.get("abbreviation"),
                    "color": t_data.get("color"),
                    "logo": t_data.get("logos", [{}])[0].get("href")
                }
        return f"Team '{team}' not found"
    except Exception as e:
        return f"Could not fetch team info: {str(e)}"
    
def get_team_schedule(team: str, days: int = 45):
    matches = get_upcoming_matches(team=team, days=days)
    print(f"  get_team_schedule({team}, days={days}) raw result: {matches if isinstance(matches, str) else f'{len(matches)} matches'}")
    if isinstance(matches, str):
        return matches
    
    schedule = []
    for m in matches:
        schedule.append({
            "date": m.get("date"),
            "match": m.get("name"),
            "venue": m.get("venue"),
            "match_id": m.get("id")
        })
    return {"team": team, "matches": schedule, "total": len(schedule)}