"""Shape the World Cup 2026 snapshot for the results page (/results).

Pure functions over the matches in data/world_cup_2026.json. The snapshot has
no bracket slots, so bracket order is derived from match winners: every team in
a round reached it by winning a match in the round before.
"""

KNOCKOUT_ROUNDS = ["round_of_32", "round_of_16", "quarterfinal", "semifinal", "final"]
ROUND_LABELS = {
    "round_of_32": "Round of 32",
    "round_of_16": "Round of 16",
    "quarterfinal": "Quarterfinals",
    "semifinal": "Semifinals",
    "final": "Final",
}


def _by_kickoff(matches: list[dict]) -> list[dict]:
    return sorted(matches, key=lambda m: (m["kickoff_utc"], m["id"]))


def bracket_order(matches: list[dict]) -> dict[str, list[dict]]:
    """Order each knockout round so the matches feeding a later-round match sit together.

    Walks back from the final: for each match, the earlier-round match won by
    the home team comes first, then the one won by the away team. Raises
    ValueError if the rounds don't form a consistent bracket.
    """
    by_stage = {stage: [m for m in matches if m["stage"] == stage] for stage in KNOCKOUT_ROUNDS}
    if len(by_stage["final"]) != 1:
        raise ValueError(f"expected 1 final, got {len(by_stage['final'])}")

    ordered = {"final": by_stage["final"]}
    for later, earlier in zip(reversed(KNOCKOUT_ROUNDS), reversed(KNOCKOUT_ROUNDS[:-1])):
        won_by = {}
        for m in by_stage[earlier]:
            if m["winner"] is None or m["winner"] in won_by:
                raise ValueError(f"{earlier}: missing or duplicate winner in match {m['id']}")
            won_by[m["winner"]] = m

        ordered[earlier] = []
        for m in ordered[later]:
            for side in ("home", "away"):
                team = m[side]["team"]
                if team not in won_by:
                    raise ValueError(f"{later}: {team} has no {earlier} win")
                ordered[earlier].append(won_by.pop(team))
        if won_by:
            raise ValueError(f"{earlier}: matches not leading to the {later}: {sorted(won_by)}")
    return ordered


def build_results_view(matches: list[dict]) -> dict:
    ordered = bracket_order(matches)
    final = ordered["final"][0]
    runner_up = final["away"]["team"] if final["winner"] == final["home"]["team"] else final["home"]["team"]

    third_place = [m for m in matches if m["stage"] == "third_place"]
    group_letters = sorted({m["group"] for m in matches if m["stage"] == "group"})

    return {
        "champion": final["winner"],
        "runner_up": runner_up,
        "rounds": [
            {"stage": stage, "label": ROUND_LABELS[stage], "matches": ordered[stage]}
            for stage in KNOCKOUT_ROUNDS
        ],
        "third_place": third_place[0] if third_place else None,
        "groups": [
            {
                "group": letter,
                "matches": _by_kickoff([m for m in matches if m["stage"] == "group" and m["group"] == letter]),
            }
            for letter in group_letters
        ],
    }
