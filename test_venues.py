from tools.venues import search_venue_info

tests = [
    "fan zone in Miami",
    "how to get to AT&T Stadium Dallas",
    "altitude warning Mexico City",
    "World Cup 2026 final venue",
]

for query in tests:
    print(f"\nQuery: {query}")
    print(f"Answer: {search_venue_info(query)}")