"""World Cup 2026 results from the static snapshot in data/world_cup_2026.json.

The tournament is over, so results come from a snapshot built by
scripts/snapshot_world_cup.py rather than runtime ESPN calls.
"""

import json
import unicodedata
from pathlib import Path

from tools.espn import normalize_team

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "data" / "world_cup_2026.json"

STAGE_LABELS = {
    "group": "Group stage",
    "round_of_32": "Round of 32",
    "round_of_16": "Round of 16",
    "quarterfinal": "Quarterfinal",
    "semifinal": "Semifinal",
    "third_place": "Third-place match",
    "final": "Final",
}
STAGE_FILTERS = list(STAGE_LABELS) + ["knockout"]

_matches_cache = None


def load_matches() -> list[dict]:
    global _matches_cache
    if _matches_cache is None:
        with SNAPSHOT_PATH.open(encoding="utf-8") as f:
            _matches_cache = json.load(f)["matches"]
    return _matches_cache


def _fold(name: str) -> str:
    """Case- and accent-insensitive key, so 'turkiye' matches 'Türkiye'."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def resolve_team(matches: list[dict], team: str) -> str | None:
    """Return the snapshot's spelling of team, or None if it didn't play."""
    key = _fold(normalize_team(team))
    for m in matches:
        for side in ("home", "away"):
            if _fold(m[side]["team"]) == key:
                return m[side]["team"]
    return None


def filter_matches(matches: list[dict], team: str | None = None, stage: str | None = None) -> list[dict]:
    """Filter by exact team name (already resolved) and/or stage, including 'knockout'."""
    result = matches
    if team:
        result = [m for m in result if team in (m["home"]["team"], m["away"]["team"])]
    if stage == "knockout":
        result = [m for m in result if m["stage"] != "group"]
    elif stage:
        result = [m for m in result if m["stage"] == stage]
    return result


def format_match(m: dict) -> str:
    stage = f"Group {m['group']}" if m["stage"] == "group" else STAGE_LABELS[m["stage"]]
    home, away = m["home"], m["away"]
    score = f"{home['team']} {home['score']}-{away['score']} {away['team']}"
    if m["decided"] == "penalties":
        winner = home if m["winner"] == home["team"] else away
        loser = away if winner is home else home
        score += f" ({m['winner']} won {winner['penalties']}-{loser['penalties']} on penalties)"
    elif m["decided"] == "extra_time":
        score += " (after extra time)"
    elif m["winner"] is None:
        score += " (draw)"
    return f"{m['date']} | {stage} | {score} | {m['venue']}, {m['city']}"


def team_summary(matches: list[dict], team: str) -> str | None:
    """How far team got, derived from its knockout matches (not group tables)."""
    knockout = sorted(
        (m for m in filter_matches(matches, team=team) if m["stage"] != "group"),
        key=lambda m: m["kickoff_utc"],
    )
    if not knockout:
        return f"{team}: eliminated in the group stage"
    last = knockout[-1]
    opponent = last["away"]["team"] if last["home"]["team"] == team else last["home"]["team"]
    won = last["winner"] == team
    if last["stage"] == "final":
        return f"{team}: champion, beat {opponent} in the final" if won else f"{team}: runner-up, lost to {opponent} in the final"
    if last["stage"] == "third_place":
        return f"{team}: third place, beat {opponent} in the third-place match" if won else f"{team}: fourth place, lost to {opponent} in the third-place match"
    if not won:
        return f"{team}: eliminated in the {STAGE_LABELS[last['stage']].lower()} by {opponent}"
    return None


def get_world_cup_results(team: str = None, stage: str = None):
    """World Cup 2026 match results, optionally filtered by team and/or stage."""
    if stage and stage not in STAGE_FILTERS:
        return f"Invalid stage '{stage}'. Use one of: {', '.join(STAGE_FILTERS)}"
    try:
        matches = load_matches()
    except Exception as e:
        print(f"  get_world_cup_results error: {e}")
        return f"Could not load World Cup results: {e}"

    resolved = None
    if team:
        resolved = resolve_team(matches, team)
        if resolved is None:
            teams = sorted({m[side]["team"] for m in matches for side in ("home", "away")})
            return {
                "matches": [],
                "count": 0,
                "note": f"{team} did not play at World Cup 2026. Teams that played: {', '.join(teams)}",
            }

    selected = sorted(filter_matches(matches, team=resolved, stage=stage), key=lambda m: m["kickoff_utc"])
    result = {"matches": [format_match(m) for m in selected], "count": len(selected)}
    if resolved:
        summary = team_summary(matches, resolved)
        if summary:
            result["team_summary"] = summary
    return result
