# Test Notes — MatchDay

## Pass 1 — Smoke Test (June 5)

### Status
All 15 features functional. No broken behavior.

### Observations
- Head-to-head query takes 15-20s (acceptable — grounded search does 2 internal model calls)
- Trip planner ran fast because user was only following one team
- Leaderboard correctly differentiated between scored entries and the current user's pending predictions
- Bracket page renders correctly

### Items to verify
- Brazil vs Morocco home/away assignment: ✅ verified correct (Brazil home per ESPN)
- More recent A-G head-to-head data: confirmed accurate (last friendly Oct 2019)
- Session memory clears correctly when prompts shift to unrelated topics (Session A → B without page refresh, no bleed observed)

### Known limitations (acceptable for demo)
- Group standings empty until tournament starts (correct behavior)
- ESPN match data won't have actual results until June 11


## Pass 2 — Realistic User Flows
All 4 sessions clean.

### Strong behaviors observed
- Session A: prediction overwrite worked correctly, sidebar updates instant
- Session B: follow + unfollow same team in one session worked
- Session C: sequential multi-match predictions without restating context
- Session D: agent inferred England from "London" context, two-venue comparison required parallel RAG calls

### Minor wording observation
- Unranked leaderboard response could acknowledge pending predictions more accurately

## Pass 3 — Edge Cases

### Issues found
1. Wakanda follow: agent acknowledged team isn't in FIFA but still saved it. Should validate against real teams before save_follow.
2. Rapid-fire follows: intermediate responses claimed extra teams were already added. Final state correct but messages misleading.
3. Date parsing for "5pm on the 13th": interpreted as offset from kickoff rather than literal 5pm.
4. Tokyo weather: agent fabricated weather data instead of declining. Should refuse out-of-scope info.
5. Which teams should I follow: Stale parametric knowledge, where the model confidently states facts from its training data that may no longer be true. Then commit and deploy as planned.

### Defense-in-depth confirmed
- Prompt injection ("ignore previous instructions") blocked correctly
- Multi-user isolation: switching user IDs correctly shows empty state
- Past-date predictions politely refused
- Non-existent fixtures (Argentina vs Morocco) caught with helpful redirect

### Fixes applied
- Wakanda follow validation: ✅ fixed via system instruction (verify team exists before saving)
- Out-of-scope refusal (weather): ✅ fixed via system instruction (refuse fabrication, redirect)