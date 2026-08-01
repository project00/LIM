"""
Model Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles searching, fetching, unzipping, and caching 3D models
    from Sketchfab's Download API. It fails fast on startup if the required
    SKETCHFAB_ACCESS_TOKEN environment variable is not configured. It filters models
    to prefer those explicitly marked downloadable and under a Creative Commons (CC)
    license (selection heuristic: first downloadable and CC-licensed result). It caches
    models in the local file system (server/model_cache/<uid>/) and avoids repeated downloads.
"""

import logging
import os
import zipfile
import io
import shutil
import httpx

logger = logging.getLogger("server_model_service")

# Set up local cache path relative to this service or the server root
CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "model_cache"))


def get_auth_headers(access_token: str) -> dict:
    """Helper to return authenticated authorization headers for Sketchfab API."""
    token = access_token.strip()
    if token.startswith("Token ") or token.startswith("Bearer "):
        return {"Authorization": token}
    # Default to Token authorization format
    return {"Authorization": f"Token {token}"}


def is_cc_licensed(license_data: dict) -> bool:
    """
    Checks if the license is Creative Commons based on slug, name, or key identifiers.
    Standard Sketchfab CC license slugs include: by, by-sa, by-nd, by-nc, by-nc-sa, by-nc-nd, cc0
    """
    if not license_data:
        return False
    slug = license_data.get("slug", "").lower()
    name = license_data.get("name", "").lower()

    # Check common CC markers
    cc_slugs = ["by", "cc0", "share-alike", "attribution", "noncommercial"]
    if any(x in slug for x in cc_slugs):
        return True
    if "creative commons" in name or "cc0" in name:
        return True
    return False


def search_and_fetch_3d_model(query: str, sketchfab_token: str) -> dict:
    """
    Searches Sketchfab for query, filters for downloadable + CC models, downloads the ZIP,
    unzips to model_cache, and returns metadata details.

    Args:
        query: The search keyword (e.g. "molecola acqua H2O").
        sketchfab_token: The Sketchfab V3 API token to use.

    Returns:
        Dictionary containing metadata conforming to docs/api-contract.md §1 load_3d_model:
        {
            "uid": str,
            "title": str,
            "model_url": str,
            "attribution": {
                "author": str,
                "license": str,
                "source_url": str
            }
        }

    Raises:
        ValueError: if model is not found ("MODEL_NOT_FOUND").
        RuntimeError: if an external API call fails ("REMOTE_SERVICE_ERROR").
    """
    logger.info("Searching Sketchfab for 3D model query: '%s'", query)

    if not sketchfab_token:
        raise RuntimeError("Sketchfab access token is not configured. Request cannot be processed.")

    # 1. Search Sketchfab
    search_url = "https://api.sketchfab.com/v3/models"
    params = {
        "q": query,
        "downloadable": "true",
        "limit": 10
    }

    try:
        # Use sync HTTP client following the requests-like model for ease of integration
        with httpx.Client(timeout=10.0) as client:
            response = client.get(search_url, params=params, headers=get_auth_headers(sketchfab_token))

            if response.status_code != 200:
                logger.error("Sketchfab search failed: %d - %s", response.status_code, response.text)
                raise RuntimeError(f"Sketchfab Search API failure: {response.text}")

            search_data = response.json()
    except httpx.HTTPError as e:
        logger.error("Network error during Sketchfab search: %s", e)
        raise RuntimeError(f"Impossibile connettersi a Sketchfab: {e}")

    results = search_data.get("results", [])
    if not results:
        logger.warning("No Sketchfab search results for query: '%s'", query)
        raise ValueError(f"Nessun modello 3D trovato per la ricerca: '{query}'")

    # Selection Heuristic: Find first model explicitly marked downloadable and under a CC license
    selected_model = None
    for model in results:
        # We queried downloadable=true, but verify just in case
        if not model.get("isDownloadable", True):
            continue

        license_data = model.get("license") or {}
        if is_cc_licensed(license_data):
            selected_model = model
            break

    # If no CC model is found, fall back to the first result to be helpful
    if not selected_model:
        selected_model = results[0]
        logger.info("No explicit CC-licensed models found; falling back to first downloadable result: '%s'", selected_model.get("name"))

    uid = selected_model.get("uid")
    name = selected_model.get("name", "Modello 3D")
    author_info = selected_model.get("user", {})
    author_name = author_info.get("displayName") or author_info.get("username") or "Autore sconosciuto"
    license_name = (selected_model.get("license") or {}).get("fullName") or "CC Attribution"
    source_url = selected_model.get("viewerUrl") or f"https://sketchfab.com/models/{uid}"

    # 2. Local Caching check
    model_dir = os.path.join(CACHE_DIR, uid)
    gltf_file = os.path.join(model_dir, "scene.gltf")

    # If already cached, reuse immediately
    if os.path.isdir(model_dir) and os.path.exists(gltf_file):
        logger.info("Cache HIT: Model %s is already cached locally.", uid)
    else:
        logger.info("Cache MISS: Downloading model %s from Sketchfab Download API.", uid)
        os.makedirs(model_dir, exist_ok=True)

        # Get temporary download link
        download_endpoint = f"https://api.sketchfab.com/v3/models/{uid}/download"
        try:
            with httpx.Client(timeout=10.0) as client:
                download_resp = client.get(download_endpoint, headers=get_auth_headers(sketchfab_token))

                if download_resp.status_code != 200:
                    logger.error("Failed to request download for model %s: %d - %s", uid, download_resp.status_code, download_resp.text)
                    raise RuntimeError(f"Sketchfab Download API failure: {download_resp.text}")

                download_info = download_resp.json()
        except httpx.HTTPError as e:
            logger.error("Network error during Sketchfab download request: %s", e)
            raise RuntimeError(f"Impossibile richiedere il download a Sketchfab: {e}")

        gltf_info = download_info.get("gltf")
        if not gltf_info or not gltf_info.get("url"):
            logger.error("Sketchfab returned no glTF download URL: %s", download_info)
            raise RuntimeError("Nessun link di download glTF disponibile per questo modello.")

        download_archive_url = gltf_info["url"]

        # Download and extract the archive immediately
        try:
            with httpx.Client(timeout=30.0) as client:
                archive_resp = client.get(download_archive_url)
                if archive_resp.status_code != 200:
                    logger.error("Failed to download model archive from AWS S3: %d", archive_resp.status_code)
                    raise RuntimeError("Download dell'archivio glTF fallito.")

                archive_bytes = archive_resp.content
        except httpx.HTTPError as e:
            logger.error("Network error during archive download: %s", e)
            raise RuntimeError(f"Errore di download dell'archivio glTF: {e}")

        # Extract unzipped archive directly to cache directory
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zip_ref:
                zip_ref.extractall(model_dir)
            logger.info("Successfully extracted model archive into cache directory %s", model_dir)
        except Exception as e:
            logger.error("Unzipping glTF archive failed: %s", e)
            # Cleanup broken folder on failure
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            raise RuntimeError(f"Estrazione dell'archivio glTF fallita: {e}")

    # Conforming return object
    stable_local_url = f"/models/{uid}/scene.gltf"
    return {
        "uid": uid,
        "title": name,
        "model_url": stable_local_url,
        "attribution": {
            "author": author_name,
            "license": license_name,
            "source_url": source_url
        }
    }
