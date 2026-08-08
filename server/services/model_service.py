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
        logger.error("Sketchfab access token is empty or missing.")
        raise RuntimeError("Sketchfab access token is not configured. Request cannot be processed.")

    # 1. Search Sketchfab
    search_url = "https://api.sketchfab.com/v3/models"
    # Increased limit parameter to 24 (reasonable increase from 10 to give a larger candidate pool)
    params = {
        "q": query,
        "downloadable": "true",
        "limit": 24
    }

    # Redact token, but explicitly log if Authorization header is present/empty
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
        # Use sync HTTP client following the requests-like model for ease of integration
        with httpx.Client(timeout=10.0) as client:
            response = client.get(search_url, params=params, headers=auth_headers)

            logger.info("Received response from Sketchfab Search API. Status code: %d", response.status_code)
            logger.info("RESOLVED OUTGOING URL: %s", str(response.request.url))

            if response.status_code != 200:
                logger.error(
                    "Sketchfab search failed distinctly with non-200 status code: %d. Error details: %s",
                    response.status_code,
                    response.text
                )
                raise RuntimeError(f"Sketchfab Search API failure (HTTP {response.status_code}): {response.text}")

            import json
            search_data = response.json()
            logger.info("RAW JSON RESPONSE BODY (TRUNCATED): %s", json.dumps(search_data)[:3000])

            # Check and log top-level metadata about total match count or applied filters / pagination / cursor
            metadata_keys = {k: v for k, v in search_data.items() if k != "results"}
            logger.info("TOP-LEVEL METADATA: %s", json.dumps(metadata_keys))
    except httpx.HTTPError as e:
        logger.error("Network error during Sketchfab search: %s", e)
        raise RuntimeError(f"Impossibile connettersi a Sketchfab due to network error: {e}")

    raw_results = search_data.get("results", [])
    logger.info("Sketchfab search returned %d raw candidate results.", len(raw_results))

    if not raw_results:
        logger.warning("No Sketchfab search results for query: '%s'", query)
        raise ValueError(f"Nessun modello 3D trovato per la ricerca: '{query}'")

    significant_words = extract_significant_words(query)
    logger.info("Significant words for query '%s': %s", query, significant_words)

    # Pre-filter: collect all models that are explicitly downloadable and CC-licensed
    downloadable_cc_candidates = []
    for idx, model in enumerate(raw_results):
        m_name = model.get("name", "Modello Sconosciuto")
        m_uid = model.get("uid", "no-uid")
        is_dl = model.get("isDownloadable")
        license_data = model.get("license") or {}
        lic_slug = license_data.get("slug", "no-slug")
        is_cc = is_cc_licensed(license_data)

        logger.info(
            "Evaluating raw candidate #%d: Name='%s', UID='%s', isDownloadable=%s, license_slug='%s'",
            idx + 1,
            m_name,
            m_uid,
            is_dl,
            lic_slug
        )

        if not is_dl:
            logger.info("Candidate '%s' (UID: %s) rejected: not downloadable", m_name, m_uid)
            continue

        if not is_cc:
            logger.info("Candidate '%s' (UID: %s) rejected: not CC", m_name, m_uid)
            continue

        downloadable_cc_candidates.append(model)

    if not downloadable_cc_candidates:
        logger.warning("No Sketchfab search results passed the downloadable and CC filter for query: '%s'", query)
        raise ValueError(f"Nessun modello 3D trovato per la ricerca: '{query}'")

    selected_model = None

    # Pass 1: find first model in downloadable_cc_candidates whose name contains at least one significant query word
    for model in downloadable_cc_candidates:
        m_name = model.get("name", "Modello Sconosciuto")
        m_uid = model.get("uid", "no-uid")
        model_name_lower = m_name.lower()

        if any(word in model_name_lower for word in significant_words):
            logger.info("Pass 1 match: Candidate '%s' (UID: %s) contains significant query word(s) %s", m_name, m_uid, significant_words)
            selected_model = model
            break
        else:
            logger.info("Pass 1 skip: Candidate '%s' (UID: %s) does not match significant query words %s", m_name, m_uid, significant_words)

    # Pass 2: Fallback to the first downloadable + CC candidate if Pass 1 found nothing
    if not selected_model:
        fallback_cand = downloadable_cc_candidates[0]
        fallback_name = fallback_cand.get("name", "Modello Sconosciuto")
        fallback_uid = fallback_cand.get("uid", "no-uid")
        logger.warning(
            "Nessuna corrispondenza esatta sul nome per '%s' — uso il primo risultato scaricabile/CC come fallback: '%s' (uid=%s)",
            query,
            fallback_name,
            fallback_uid
        )
        selected_model = fallback_cand

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
        logger.info("Requesting temporary download link from Sketchfab Download API: '%s'", download_endpoint)

        try:
            with httpx.Client(timeout=10.0) as client:
                dl_headers = get_auth_headers(sketchfab_token)
                dl_auth_present = "PRESENT" if dl_headers.get("Authorization", "").strip() else "EMPTY"
                logger.info("Sending download request with Auth header: %s", dl_auth_present)

                download_resp = client.get(download_endpoint, headers=dl_headers)

                logger.info("Download link API response status: %d", download_resp.status_code)
                if download_resp.status_code != 200:
                    logger.error(
                        "Failed to request download for model %s: distinctly non-200 status code: %d - %s",
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
