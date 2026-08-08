import sys
import os
import json
import logging
import httpx

# Ensure server folder is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configure logging to console
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

import services.model_service as model_service

# Mock get_auth_headers to return empty headers so public search succeeds
def mock_get_auth_headers(access_token: str) -> dict:
    return {}

model_service.get_auth_headers = mock_get_auth_headers

def main():
    print("=================== DAEMON/SERVER DIAGNOSTICS ===================")

    # 1. Direct fetch to get the full raw JSON of the first 3 results
    search_url = "https://api.sketchfab.com/v3/models"
    params = {
        "q": "h2O",
        "downloadable": "true",
        "limit": 24
    }

    print("\n--- [DIRECT PUBLIC SEARCH API CALL] ---")
    with httpx.Client(timeout=10.0) as client:
        response = client.get(search_url, params=params)
        resolved_url = str(response.request.url)
        print(f"FULLY RESOLVED OUTGOING URL: {resolved_url}")

        search_data = response.json()

        # 2. Extract and log top-level metadata
        top_level_metadata = {k: v for k, v in search_data.items() if k != "results"}
        print("\n--- [TOP-LEVEL METADATA] ---")
        print(json.dumps(top_level_metadata, indent=4))

        # 3. Print first 3 results in full (not truncated)
        results = search_data.get("results", [])
        print(f"\n--- [RAW JSON FOR FIRST 3 RESULTS (Total results in batch: {len(results)})] ---")
        first_3 = results[:3]
        print(json.dumps(first_3, indent=4))

    # 4. Trigger model_service's search_and_fetch_3d_model to verify our custom logging works
    print("\n--- [TRIGGERING SERVICES.MODEL_SERVICE PIPELINE] ---")
    try:
        # We pass a dummy token to pass the internal validation, but get_auth_headers is mocked to empty dict
        model_service.search_and_fetch_3d_model("h2O", "dummy_token_to_bypass")
        print("\nService pipeline execution completed successfully.")
    except Exception as e:
        print(f"\nService pipeline stopped/completed: {e}")

if __name__ == "__main__":
    main()
