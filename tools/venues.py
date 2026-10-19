from google.cloud import discoveryengine_v1 as discoveryengine
from google.cloud import storage as gcs_storage
from dotenv import load_dotenv
from pathlib import PurePosixPath
import os

load_dotenv()

def retrieve_venue_docs(query: str, k: int = 5, relevance_threshold: str | None = None) -> list[dict]:
    """Return the top-k Discovery Engine results for query, ranked best-first.

    Each entry is {"stem": ..., "link": ...}. Results without a gs:// link are
    kept as {"stem": None, "link": ""} so ranks stay aligned with the search.
    relevance_threshold is a SearchRequest.RelevanceThreshold name (e.g. "LOW");
    when None, the field is not set and the API default applies.
    Does not catch exceptions: an API failure raises rather than looking like
    an empty result.
    """
    search_client = discoveryengine.SearchServiceClient()

    serving_config = (
        f"projects/{os.getenv('GCP_PROJECT_ID')}/locations/{os.getenv('DISCOVERY_ENGINE_LOCATION')}"
        f"/collections/default_collection/engines/{os.getenv('DISCOVERY_ENGINE_ID')}"
        f"/servingConfigs/default_config"
    )

    request_kwargs = {
        "serving_config": serving_config,
        "query": query,
        "page_size": k,
    }
    if relevance_threshold is not None:
        request_kwargs["relevance_threshold"] = discoveryengine.SearchRequest.RelevanceThreshold[relevance_threshold]
    request = discoveryengine.SearchRequest(**request_kwargs)

    response = search_client.search(request)

    docs = []
    for result in list(response.results)[:k]:
        link = result.document.derived_struct_data.get("link", "")
        if link.startswith("gs://"):
            docs.append({"stem": PurePosixPath(link[5:]).stem, "link": link})
        else:
            docs.append({"stem": None, "link": ""})
    return docs

def search_venue_info(query: str) -> str:
    try:
        # LOWEST chosen from the relevance threshold sweep in docs/EVALUATION.md:
        # the default threshold discarded correct results for short queries.
        docs = retrieve_venue_docs(query, k=2, relevance_threshold="LOWEST")
        gcs_client = gcs_storage.Client()

        results = []
        for doc in docs:
            if not doc["link"]:
                continue
            bucket_name, blob_name = doc["link"][5:].split("/", 1)
            blob = gcs_client.bucket(bucket_name).blob(blob_name)
            results.append(blob.download_as_text())

        if results:
            return "\n\n---\n\n".join(results)
        return "No venue information found for that query."
    except Exception as e:
        return f"Failed to search venue info: {e}"
