import sys
from tools.venues import retrieve_venue_docs

DEFAULT_QUERIES = [
    "metlife",
    "metlife transit",
    "reach metlife",
    "how to reach metlife",
    "arlington",
    "how to reach arlington",
]

queries = sys.argv[1:] or DEFAULT_QUERIES
for q in queries:
    stems = [d["stem"] for d in retrieve_venue_docs(q)]
    print(f"{q!r:35} -> {stems}")