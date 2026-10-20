"""Build a static snapshot of every FIFA World Cup 2026 match from ESPN.

Run from the repo root:
    python -m scripts.snapshot_world_cup

Fetches ESPN's fifa.world scoreboard for every day of the tournament, parses
each match, validates it, and writes data/world_cup_2026.json. The file is only
written if exactly 104 matches pass validation, so a bad fetch can't overwrite
a good snapshot.
"""

import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
# One day of margin on each side: ESPN's ?dates= is a US Eastern date.
FETCH_START = date(2026, 6, 10)
FETCH_END = date(2026, 7, 20)
EXPECTED_MATCHES = 104
OUTPUT_PATH = Path("data/world_cup_2026.json")

# Every venue was in North America during DST; ESPN groups matchdays by US
# Eastern time (EDT, UTC-4) for the whole tournament.
EASTERN_OFFSET = timedelta(hours=-4)

STAGES = {
    "group-stage": "group",
    "round-of-32": "round_of_32",
    "round-of-16": "round_of_16",
    "quarterfinals": "quarterfinal",
    "semifinals": "semifinal",
    "3rd-place-match": "third_place",
    "final": "final",
}

DECIDED = {
    "STATUS_FULL_TIME": "regulation",
    "STATUS_FINAL_AET": "extra_time",
    "STATUS_FINAL_PEN": "penalties",
}


def parse_event(event: dict) -> dict:
    """Turn one ESPN scoreboard event into a snapshot match. Raises ValueError on anything unexpected."""
    event_id = event.get("id")
    comp = event["competitions"][0]

    slug = event["season"]["slug"]
    if slug not in STAGES:
        raise ValueError(f"event {event_id}: unknown stage slug {slug!r}")
    stage = STAGES[slug]

    status = comp["status"]["type"]
    if not status.get("completed"):
        raise ValueError(f"event {event_id}: match not completed ({status.get('name')})")
    if status["name"] not in DECIDED:
        raise ValueError(f"event {event_id}: unknown status {status['name']!r}")
    decided = DECIDED[status["name"]]

    sides = {}
    for competitor in comp["competitors"]:
        side = {
            "team": competitor["team"]["displayName"],
            "score": int(competitor["score"]),
        }
        if decided == "penalties":
            side["penalties"] = int(competitor["shootoutScore"])
        sides[competitor["homeAway"]] = (side, bool(competitor.get("winner")))
    if set(sides) != {"home", "away"}:
        raise ValueError(f"event {event_id}: expected home and away competitors, got {sorted(sides)}")
    (home, home_flag), (away, away_flag) = sides["home"], sides["away"]

    if home["score"] != away["score"]:
        winner = home["team"] if home["score"] > away["score"] else away["team"]
    elif decided == "penalties":
        if home["penalties"] == away["penalties"]:
            raise ValueError(f"event {event_id}: level shootout score")
        winner = home["team"] if home["penalties"] > away["penalties"] else away["team"]
    else:
        winner = None

    espn_winner = home["team"] if home_flag else away["team"] if away_flag else None
    if winner != espn_winner:
        raise ValueError(f"event {event_id}: computed winner {winner!r} disagrees with ESPN winner {espn_winner!r}")
    if stage != "group" and winner is None:
        raise ValueError(f"event {event_id}: knockout match without a winner")

    kickoff = datetime.strptime(event["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    group = (comp.get("group") or {}).get("abbreviation")
    venue = comp.get("venue") or {}

    return {
        "id": event_id,
        "date": (kickoff + EASTERN_OFFSET).date().isoformat(),
        "kickoff_utc": event["date"],
        "stage": stage,
        "group": group.removeprefix("Group ").strip() if group else None,
        "home": home,
        "away": away,
        "decided": decided,
        "winner": winner,
        "venue": venue.get("fullName"),
        "city": (venue.get("address") or {}).get("city"),
    }


def fetch_events() -> list[dict]:
    events = {}
    day = FETCH_START
    while day <= FETCH_END:
        r = requests.get(SCOREBOARD_URL, params={"dates": day.strftime("%Y%m%d")}, timeout=15)
        r.raise_for_status()
        day_events = r.json().get("events", [])
        for event in day_events:
            events[event["id"]] = event
        print(f"  {day}: {len(day_events)} events")
        day += timedelta(days=1)
    return list(events.values())


def main() -> None:
    events = fetch_events()
    matches = sorted((parse_event(e) for e in events), key=lambda m: (m["kickoff_utc"], m["id"]))

    print(f"\nMatches: {len(matches)}")
    for stage, count in Counter(m["stage"] for m in matches).items():
        print(f"  {stage}: {count}")
    print(f"  decided: {dict(Counter(m['decided'] for m in matches))}")

    if len(matches) != EXPECTED_MATCHES:
        print(f"\nExpected {EXPECTED_MATCHES} matches, got {len(matches)}. Not writing {OUTPUT_PATH}.")
        sys.exit(1)

    snapshot = {
        "source": SCOREBOARD_URL,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tournament": "FIFA World Cup 2026",
        "date_note": "date is the local US Eastern (UTC-4) date, as ESPN groups matchdays",
        "match_count": len(matches),
        "matches": matches,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
