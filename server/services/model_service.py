"""
Model Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles searching, fetching, unzipping, and caching 3D models
    from Sketchfab's Download API. It fails fast on startup if the required
    SKETCHFAB_ACCESS_TOKEN environment variable is not configured. It filters models
    to prefer those explicitly marked downloadable and under a Creative Commons (CC)
    license. It caches models in the local file system (server/model_cache/<uid>/)
    and avoids repeated downloads.
"""

import logging
import os
import zipfile
import io
import shutil
import json
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


def extract_significant_words(query: str) -> list[str]:
    """
    Extracts significant words from the search query.
    Normalizes to lowercase, splits, and ignores common short stopwords.
    """
    stopwords = {
        "with", "and", "the", "for", "from", "con", "il", "la", "un", "una",
        "di", "del", "della", "dei", "degli", "da", "in", "su", "per", "tra",
        "fra", "le", "gli", "i", "a", "o", "e"
    }
    # Clean up punctuation slightly
    cleaned_query = query.replace("'", " ").replace('"', " ").replace("-", " ").replace("_", " ")
    words = cleaned_query.lower().split()

    significant = [w for w in words if w not in stopwords and len(w) >= 2]

    # If filtering removed all words, fallback to using all non-stop words (which doesn't include stopwords)
    if not significant:
        significant = [w for w in words if w not in stopwords]

    return significant


def is_cc_licensed(license_data: dict) -> bool:
    """
    Checks if the license is Creative Commons based on slug or key identifiers.
    Standard Sketchfab CC license slugs include: by, by-sa, by-nd, by-nc, by-nc-sa, by-nc-nd, cc0
    """
    if not license_data:
        return False
    slug = license_data.get("slug", "").lower()

    # Check common CC markers
    cc_slugs = ["by", "cc0", "share-alike", "attribution", "noncommercial"]
    if any(x in slug for x in cc_slugs):
        return True
    return False


def get_thumbnail_url(thumbnails_dict: dict) -> str | None:
    """
    Helper to extract a reasonably-sized thumbnail URL from Sketchfab thumbnails data structure.
    Prefers a width closest to 256px for a small grid card.
    """
    if not thumbnails_dict or "images" not in thumbnails_dict:
        return None
    images = thumbnails_dict.get("images", [])
    if not images:
        return None
    # Sort images by absolute difference from 256
    sorted_images = sorted(images, key=lambda x: abs(x.get("width", 0) - 256))
    if sorted_images:
        return sorted_images[0].get("url")
    return None


def search_3d_models(query: str, sketchfab_token: str) -> list[dict]:
    """
    Searches Sketchfab for candidates, filters for downloadable + CC models, and returns
    up to 8 candidates sorted by query match.

    Args:
        query: The search keyword (e.g. "molecola acqua H2O").
        sketchfab_token: The Sketchfab V3 API token to use.

    Returns:
        A list of up to 8 dicts containing candidates conforming to API contract:
        [
            {
                "uid": str,
                "name": str,
                "thumbnail_url": str | None,
                "author": str,
                "license": str
            }
        ]

    Raises:
        ValueError: if no candidates are found ("MODEL_NOT_FOUND").
        RuntimeError: if API call fails.
    """
    logger.info("Searching Sketchfab for 3D model candidates: '%s'", query)

    if not sketchfab_token:
        logger.error("Sketchfab access token is empty or missing.")
        raise RuntimeError("Sketchfab access token is not configured. Request cannot be processed.")

    search_url = "https://api.sketchfab.com/v3/models"
    params = {
        "q": query,
        "limit": 24
    }

    auth_headers = get_auth_headers(sketchfab_token)
    auth_header_val = auth_headers.get("Authorization", "")
    auth_present = "PRESENT" if auth_header_val.strip() else "EMPTY"

    logger.info(
        "Sending search query to Sketchfab. URL: '%s', query params: %s. Authorization header: %s",
        search_url,
        params,
        auth_present
    )

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(search_url, params=params, headers=auth_headers)

            logger.info("Received response from Sketchfab Search API. Status code: %d", response.status_code)

            if response.status_code != 200:
                logger.error(
                    "Sketchfab search failed distinctly with non-200 status code: %d. Error details: %s",
                    response.status_code,
                    response.text
                )
                raise RuntimeError(f"Sketchfab Search API failure (HTTP {response.status_code}): {response.text}")

            search_data = response.json()
    except httpx.HTTPError as e:
        logger.error("Network error during Sketchfab search: %s", e)
        raise RuntimeError(f"Impossibile connettersi a Sketchfab due to network error: {e}")

    raw_results = search_data.get("results", [])
    logger.info("Sketchfab search returned %d raw candidate results.", len(raw_results))

    if not raw_results:
        logger.warning("No Sketchfab search results for query: '%s'", query)
        raise ValueError(f"Nessun modello 3D trovato per la ricerca: '{query}'")

    # Hard filter for downloadable + CC candidates
    downloadable_cc_candidates = []
    for idx, model in enumerate(raw_results):
        m_name = model.get("name", "Modello Sconosciuto")
        m_uid = model.get("uid", "no-uid")
        is_dl = model.get("isDownloadable")
        license_info = model.get("license")
        is_cc = is_cc_licensed(license_info)

        logger.info(
            "Evaluating raw candidate #%d: Name='%s', UID='%s', isDownloadable=%s, is_cc=%s",
            idx + 1,
            m_name,
            m_uid,
            is_dl,
            is_cc
        )

        if not is_dl or not is_cc:
            logger.info("Candidate '%s' (UID: %s) rejected: not downloadable or not CC", m_name, m_uid)
            continue

        downloadable_cc_candidates.append(model)

    if not downloadable_cc_candidates:
        logger.warning("No Sketchfab search results passed the downloadable+CC filters for query: '%s'", query)
        raise ValueError(f"Nessun modello 3D trovato per la ricerca: '{query}'")

    # Sort preference: matching significant query words first, then the rest
    significant_words = extract_significant_words(query)
    logger.info("Significant words for query '%s': %s", query, significant_words)

    matching = []
    non_matching = []
    for model in downloadable_cc_candidates:
        m_name_lower = model.get("name", "Modello Sconosciuto").lower()
        if any(word in m_name_lower for word in significant_words):
            matching.append(model)
        else:
            non_matching.append(model)

    sorted_candidates = matching + non_matching
    results = []

    # Map to the API-contract candidate structure
    for model in sorted_candidates[:8]:
        uid = model.get("uid")
        name = model.get("name", "Modello 3D")
        author_info = model.get("user", {})
        author_name = author_info.get("displayName") or author_info.get("username") or "Autore sconosciuto"
        license_name = (model.get("license") or {}).get("fullName") or "CC Attribution"
        thumbnail_url = get_thumbnail_url(model.get("thumbnails"))

        results.append({
            "uid": uid,
            "name": name,
            "thumbnail_url": thumbnail_url,
            "author": author_name,
            "license": license_name
        })

    logger.info("Returned %d filtered and sorted candidates.", len(results))
    return results


def fetch_3d_model_by_uid(uid: str, sketchfab_token: str) -> dict:
    """
    Downloads, extracts, and caches a 3D model by its known UID, returning its metadata.

    Args:
        uid: The Sketchfab model UID.
        sketchfab_token: The Sketchfab V3 API token to use.

    Returns:
        Dictionary containing metadata:
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
    logger.info("Fetching 3D model details and downloading model for UID: '%s'", uid)

    if not sketchfab_token:
        logger.error("Sketchfab access token is empty or missing.")
        raise RuntimeError("Sketchfab access token is not configured. Request cannot be processed.")

    model_dir = os.path.join(CACHE_DIR, uid)
    gltf_file = os.path.join(model_dir, "scene.gltf")
    metadata_file = os.path.join(model_dir, "metadata.json")

    # Cache HIT: If already fully cached, reuse metadata and GLTF immediately
    if os.path.isdir(model_dir) and os.path.exists(gltf_file) and os.path.exists(metadata_file):
        logger.info("Cache HIT: Model %s is already cached locally with metadata.", uid)
        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load cached metadata.json: %s. Fetching details again.", e)

    # Cache MISS or metadata.json missing: Fetch model details from Sketchfab Model API
    model_detail_url = f"https://api.sketchfab.com/v3/models/{uid}"
    auth_headers = get_auth_headers(sketchfab_token)

    logger.info("Fetching model detail from URL: '%s'", model_detail_url)

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(model_detail_url, headers=auth_headers)

            logger.info("Received model details response. Status code: %d", response.status_code)

            if response.status_code != 200:
                logger.error(
                    "Sketchfab model detail failed with status code: %d. Error details: %s",
                    response.status_code,
                    response.text
                )
                raise RuntimeError(f"Sketchfab Model Detail API failure (HTTP {response.status_code}): {response.text}")

            model = response.json()
    except httpx.HTTPError as e:
        logger.error("Network error during Sketchfab model detail request: %s", e)
        raise RuntimeError(f"Impossibile connettersi a Sketchfab due to network error: {e}")

    name = model.get("name", "Modello 3D")
    author_info = model.get("user", {})
    author_name = author_info.get("displayName") or author_info.get("username") or "Autore sconosciuto"
    license_name = (model.get("license") or {}).get("fullName") or "CC Attribution"
    source_url = model.get("viewerUrl") or f"https://sketchfab.com/models/{uid}"

    # If the GLTF files are already unzipped/cached, skip downloading entirely
    if os.path.isdir(model_dir) and os.path.exists(gltf_file):
        logger.info("Cache HIT (GLTF files exist): Model %s is already cached locally. Rebuilding metadata.", uid)
    else:
        logger.info("Cache MISS: Downloading model %s from Sketchfab Download API.", uid)
        os.makedirs(model_dir, exist_ok=True)

        # Get temporary download link
        download_endpoint = f"https://api.sketchfab.com/v3/models/{uid}/download"
        logger.info("Requesting temporary download link from Sketchfab Download API: '%s'", download_endpoint)

        try:
            with httpx.Client(timeout=10.0) as client:
                dl_headers = get_auth_headers(sketchfab_token)
                download_resp = client.get(download_endpoint, headers=dl_headers)

                logger.info("Download link API response status: %d", download_resp.status_code)
                if download_resp.status_code != 200:
                    logger.error(
                        "Failed to request download for model %s: status code: %d - %s",
                        uid,
                        download_resp.status_code,
                        download_resp.text
                    )
                    raise RuntimeError(f"Sketchfab Download API failure (HTTP {download_resp.status_code}): {download_resp.text}")

                download_info = download_resp.json()
        except httpx.HTTPError as e:
            logger.error("Network error during Sketchfab download request: %s", e)
            raise RuntimeError(f"Impossibile richiedere il download a Sketchfab due to network error: {e}")

        gltf_info = download_info.get("gltf")
        if not gltf_info or not gltf_info.get("url"):
            logger.error("Sketchfab returned no glTF download URL: %s", download_info)
            raise RuntimeError("Nessun link di download glTF disponibile per questo modello.")

        download_archive_url = gltf_info["url"]
        logger.info("Resolved glTF download URL: '%s'", download_archive_url)

        # Download and extract the archive immediately
        logger.info("Downloading binary model ZIP archive from AWS S3 resolved URL...")
        try:
            with httpx.Client(timeout=30.0) as client:
                archive_resp = client.get(download_archive_url)
                logger.info("Archive download response status code: %d", archive_resp.status_code)
                if archive_resp.status_code != 200:
                    logger.error("Failed to download model archive from AWS S3. Status: %d", archive_resp.status_code)
                    raise RuntimeError(f"Download dell'archivio glTF fallito (HTTP {archive_resp.status_code}).")

                archive_bytes = archive_resp.content
        except httpx.HTTPError as e:
            logger.error("Network error during archive download: %s", e)
            raise RuntimeError(f"Errore di download dell'archivio glTF due to network error: {e}")

        # Extract unzipped archive directly to cache directory
        logger.info("Extracting ZIP archive (%d bytes) to cache directory: %s", len(archive_bytes), model_dir)
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
    res = {
        "uid": uid,
        "title": name,
        "model_url": stable_local_url,
        "attribution": {
            "author": author_name,
            "license": license_name,
            "source_url": source_url
        }
    }

    # Save to metadata.json in cached directory
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.warning("Failed to save metadata.json to server cache: %s", e)

    return res
