import argparse
import os
from pathlib import PurePosixPath

from dotenv import load_dotenv
from google.cloud import discoveryengine_v1 as de

load_dotenv()

DEFAULT_QUERIES = [
    "metlife",
    "metlife transit",
    "how to reach metlife",
    "arlington",
    "arlington texas",
    "how to reach arlington",
]

parser = argparse.ArgumentParser()
parser.add_argument("queries", nargs="*")
parser.add_argument("--threshold", choices=["LOWEST", "LOW", "MEDIUM", "HIGH"])
parser.add_argument("--expand", action="store_true")
args = parser.parse_args()

serving_config = (
    f"projects/{os.getenv('GCP_PROJECT_ID')}/locations/{os.getenv('DISCOVERY_ENGINE_LOCATION')}"
    f"/collections/default_collection/engines/{os.getenv('DISCOVERY_ENGINE_ID')}"
    f"/servingConfigs/default_config"
)
client = de.SearchServiceClient()

print(f"threshold={args.threshold or 'default'}  expand={args.expand}\n")
for q in args.queries or DEFAULT_QUERIES:
    kwargs = {"serving_config": serving_config, "query": q, "page_size": 5}
    if args.threshold:
        kwargs["relevance_threshold"] = de.SearchRequest.RelevanceThreshold[args.threshold]
    if args.expand:
        kwargs["query_expansion_spec"] = de.SearchRequest.QueryExpansionSpec(
            condition=de.SearchRequest.QueryExpansionSpec.Condition.AUTO
        )
    resp = client.search(de.SearchRequest(**kwargs))
    stems = [PurePosixPath(r.document.derived_struct_data.get("link", "")).stem for r in resp.results]
    print(f"{q!r:30} -> {stems}")