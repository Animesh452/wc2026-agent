from google.cloud import discoveryengine_v1 as discoveryengine
from google.cloud import storage as gcs_storage
from dotenv import load_dotenv
import os

load_dotenv()

def search_venue_info(query: str) -> str:
    search_client = discoveryengine.SearchServiceClient()
    gcs_client = gcs_storage.Client()

    serving_config = (
        f"projects/{os.getenv('GCP_PROJECT_ID')}/locations/{os.getenv('DISCOVERY_ENGINE_LOCATION')}"
        f"/collections/default_collection/engines/{os.getenv('DISCOVERY_ENGINE_ID')}"
        f"/servingConfigs/default_config"
    )

    request = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=query,
        page_size=2,
    )

    response = search_client.search(request)

    results = []
    for result in response.results:
        link = result.document.derived_struct_data.get("link", "")
        if link.startswith("gs://"):
            path = link[5:]
            bucket_name, blob_name = path.split("/", 1)
            blob = gcs_client.bucket(bucket_name).blob(blob_name)
            content = blob.download_as_text()
            results.append(content)

    if results:
        return "\n\n---\n\n".join(results)
    return "No venue information found for that query."