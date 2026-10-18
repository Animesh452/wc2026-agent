New fn retrieve_venue_docs encountered a classic RAG failure mode: a document that shares vocabulary with the query outranks the one that actually answers it, here because of historical rather than current content.
Query: Which stadium hosts the world cup finals?
1 {'stem': 'world_cup_2026_overview', 'link': 'gs://matchday-venue-docs-511216/world_cup_2026_overview.txt'}
2 {'stem': 'estadio_azteca', 'link': 'gs://matchday-venue-docs-511216/estadio_azteca.txt'}
3 {'stem': 'metlife_stadium', 'link': 'gs://matchday-venue-docs-511216/metlife_stadium.txt'}
4 {'stem': 'sofi_stadium', 'link': 'gs://matchday-venue-docs-511216/sofi_stadium.txt'}
5 {'stem': 'bc_place', 'link': 'gs://matchday-venue-docs-511216/bc_place.txt'}

**Why Azteca beat MetLife**: the Azteca doc talks about hosting the 1970 and 1986 World Cup Finals, so it overlaps heavily with "World Cup final" even though it's about history, not 2026. MetLife's doc only says "Final match venue" once. Meanwhile the overview ranked first, and it does answer the question directly ("Final: July 19, 2026 at MetLife Stadium"). So the agent still gets a correct answer from the top 2, just not via the doc you'd expect.