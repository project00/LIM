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

# Configuration Constants
MAX_SEARCH_PAGES = 3
MAX_RESULTS = 8

# Centralized License Registry for supported Creative Commons licenses
CC_LICENSE_REGISTRY = {
    "322a749bcfa841b29dff1e8a1bb74b0b": {
        "canonical_name": "CC BY",
        "sketchfab_uid": "322a749bcfa841b29dff1e8a1bb74b0b",
        "slug": "by",
        "label": "CC Attribution",
        "fullName": "Creative Commons Attribution",
        "license_url": "http://creativecommons.org/licenses/by/4.0/",
        "attribution_required": True
    },
    "b9ddc40b93e34cdca1fc152f39b9f375": {
        "canonical_name": "CC BY-SA",
        "sketchfab_uid": "b9ddc40b93e34cdca1fc152f39b9f375",
        "slug": "by-sa",
        "label": "CC Attribution-ShareAlike",
        "fullName": "Creative Commons Attribution-ShareAlike",
        "license_url": "http://creativecommons.org/licenses/by-sa/4.0/",
        "attribution_required": True
    },
    "72360ff1740d419791934298b8b6d270": {
        "canonical_name": "CC BY-ND",
        "sketchfab_uid": "72360ff1740d419791934298b8b6d270",
        "slug": "by-nd",
        "label": "CC Attribution-NoDerivs",
        "fullName": "Creative Commons Attribution-NoDerivs",
        "license_url": "http://creativecommons.org/licenses/by-nd/4.0/",
        "attribution_required": True
    },
    "bbfe3f7dbcdd4122b966b85b9786a989": {
        "canonical_name": "CC BY-NC",
        "sketchfab_uid": "bbfe3f7dbcdd4122b966b85b9786a989",
        "slug": "by-nc",
        "label": "CC Attribution-NonCommercial",
        "fullName": "Creative Commons Attribution-NonCommercial",
        "license_url": "http://creativecommons.org/licenses/by-nc/4.0/",
        "attribution_required": True
    },
    "2628dbe5140a4e9592126c8df566c0b7": {
        "canonical_name": "CC BY-NC-SA",
        "sketchfab_uid": "2628dbe5140a4e9592126c8df566c0b7",
        "slug": "by-nc-sa",
        "label": "CC Attribution-NonCommercial-ShareAlike",
        "fullName": "CC Attribution-NonCommercial-ShareAlike",
        "license_url": "http://creativecommons.org/licenses/by-nc-sa/4.0/",
        "attribution_required": True
    },
    "34b725081a6a4184957efaec2cb84ed3": {
        "canonical_name": "CC BY-NC-ND",
        "sketchfab_uid": "34b725081a6a4184957efaec2cb84ed3",
        "slug": "by-nc-nd",
        "label": "CC Attribution-NonCommercial-NoDerivs",
        "fullName": "CC Attribution-NonCommercial-NoDerivs",
        "license_url": "http://creativecommons.org/licenses/by-nc-nd/4.0/",
        "attribution_required": True
    },
    "7c23a1ba438d4306920229c12afcb5f9": {
        "canonical_name": "CC0",
        "sketchfab_uid": "7c23a1ba438d4306920229c12afcb5f9",
        "slug": "cc0",
        "label": "CC0 Public Domain",
        "fullName": "CC0 Public Domain",
        "license_url": "http://creativecommons.org/publicdomain/zero/1.0/",
        "attribution_required": False
    }
}


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


def resolve_license(license_data: dict | None) -> dict:
    """
    Resolves standard Creative Commons license info using:
    1. UID
    2. slug (if present)
    3. label
    4. fullName (if present)

    Returns:
        {
            "recognized": bool,
            "license": str | None (canonical_name),
            "license_url": str | None,
            "attribution_required": bool | None
        }
    """
    if not license_data:
        return {
            "recognized": False,
            "license": None,
            "license_url": None,
            "attribution_required": None
        }

    # 1. Match by UID
    uid = license_data.get("uid")
    if uid and uid in CC_LICENSE_REGISTRY:
        reg = CC_LICENSE_REGISTRY[uid]
        return {
            "recognized": True,
            "license": reg["canonical_name"],
            "license_url": reg["license_url"],
            "attribution_required": reg["attribution_required"]
        }

    # 2. Match by slug (if present)
    slug = license_data.get("slug", "").lower() if license_data.get("slug") else ""
    if slug:
        for reg in CC_LICENSE_REGISTRY.values():
            if reg.get("slug") == slug:
                return {
                    "recognized": True,
                    "license": reg["canonical_name"],
                    "license_url": reg["license_url"],
                    "attribution_required": reg["attribution_required"]
                }

    # 3. Match by label
    label = license_data.get("label", "").lower() if license_data.get("label") else ""
    if label:
        for reg in CC_LICENSE_REGISTRY.values():
            if reg["label"].lower() == label:
                return {
                    "recognized": True,
                    "license": reg["canonical_name"],
                    "license_url": reg["license_url"],
                    "attribution_required": reg["attribution_required"]
                }

    # 4. Match by fullName (if present)
    fullName = license_data.get("fullName", "").lower() if license_data.get("fullName") else ""
    if fullName:
        for reg in CC_LICENSE_REGISTRY.values():
            if reg.get("fullName", "").lower() == fullName:
                return {
                    "recognized": True,
                    "license": reg["canonical_name"],
                    "license_url": reg["license_url"],
                    "attribution_required": reg["attribution_required"]
                }

    return {
        "recognized": False,
        "license": None,
        "license_url": None,
        "attribution_required": None
    }


def is_cc_licensed(license_data: dict) -> bool:
    """
    Checks if the license is Creative Commons.
    Kept for backward compatibility.
    """
    res = resolve_license(license_data)
    return res["recognized"]


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


def score_relevance(name: str, query: str) -> float:
    """
    Computes a deterministic search relevance score based on:
    1. Exact name match (100.0)
    2. Name starts with query (50.0)
    3. Query in name (30.0)
    4. Token overlap (10.0 per overlapping token)
    """
    name_clean = name.strip().lower()
    query_clean = query.strip().lower()

    if not name_clean or not query_clean:
        return 0.0

    if name_clean == query_clean:
        return 100.0

    score = 0.0
    if name_clean.startswith(query_clean):
        score += 50.0
    elif query_clean in name_clean:
        score += 30.0

    # Token overlap match
    # Clean up common separators to split into clean tokens
    separators = ["'", '"', "-", "_", "/", ",", ".", "(", ")"]
    name_temp = name_clean
    query_temp = query_clean
    for sep in separators:
        name_temp = name_temp.replace(sep, " ")
        query_temp = query_temp.replace(sep, " ")

    name_tokens = set(name_temp.split())
    query_tokens = set(query_temp.split())

    overlap = name_tokens.intersection(query_tokens)
    score += len(overlap) * 10.0

    return score


def search_3d_models(query: str, sketchfab_token: str) -> list[dict]:
    """
    Searches Sketchfab for candidates, filters for downloadable + CC models, and returns
    up to 8 candidates sorted by deterministic relevance match.
    """
    logger.info("Searching Sketchfab for 3D model candidates: '%s'", query)

    if not sketchfab_token:
        logger.error("Sketchfab access token is empty or missing.")
        raise RuntimeError("Sketchfab access token is not configured. Request cannot be processed.")

    search_url = "https://api.sketchfab.com/v3/models"
    params = {
        "q": query,
        "limit": 24,
        "downloadable": "true"  # Official filtering parameter for downloadable models only
    }

    auth_headers = get_auth_headers(sketchfab_token)

    eligible_pool = []
    seen_uids = set()
    pages_fetched = 0
    next_url = search_url

    # Bounded pagination loop
    while next_url and pages_fetched < MAX_SEARCH_PAGES:
        # Check if we already have enough results (>= MAX_RESULTS) to stop fetching early
        if len(eligible_pool) >= MAX_RESULTS:
            break

        pages_fetched += 1
        logger.info("Fetching Sketchfab search page %d", pages_fetched)

        try:
            with httpx.Client(timeout=10.0) as client:
                if next_url == search_url:
                    response = client.get(search_url, params=params, headers=auth_headers)
                else:
                    response = client.get(next_url, headers=auth_headers)

                if response.status_code != 200:
                    logger.error("Sketchfab search failed on page %d (HTTP %d)", pages_fetched, response.status_code)
                    if pages_fetched == 1:
                        raise RuntimeError(f"Sketchfab Search API failure (HTTP {response.status_code}): {response.text}")
                    else:
                        break

                search_data = response.json()
        except httpx.HTTPError as e:
            logger.error("Network error during Sketchfab search page %d: %s", pages_fetched, e)
            if pages_fetched == 1:
                raise RuntimeError(f"Impossibile connettersi a Sketchfab due to network error: {e}")
            else:
                break

        raw_results = search_data.get("results", [])

        logger.info(
            "Sketchfab search: query=%s page=%d raw=%d eligible=%d",
            query,
            pages_fetched,
            len(raw_results),
            len(raw_results)
        )

        for model in raw_results:
            uid = model.get("uid")
            if not uid or uid in seen_uids:
                continue

            # Check downloadable
            is_dl = model.get("isDownloadable")
            is_downloadable = bool(is_dl)
            if is_dl is False:
                logger.info("Candidate '%s' (UID: %s) rejected: reason=not_downloadable", model.get("name"), uid)
                continue

            # Check license
            license_info = model.get("license")
            resolved = resolve_license(license_info)
            if not resolved["recognized"]:
                logger.info("Candidate '%s' (UID: %s) rejected: reason=unrecognized_license", model.get("name"), uid)
                continue

            m_name = model.get("name", "Modello Sconosciuto")
            logger.info(
                "Sketchfab candidate: name=%s uid=%s downloadable=%s license=%s license_recognized=True",
                m_name,
                uid,
                is_downloadable,
                resolved["license"]
            )

            seen_uids.add(uid)
            model["_resolved_license"] = resolved
            eligible_pool.append(model)

        next_url = search_data.get("next")

    logger.info(
        "Sketchfab search completed: query=%s pages_fetched=%d raw_results=%d eligible_results=%d returned_results=%d",
        query,
        pages_fetched,
        pages_fetched * 24,
        len(eligible_pool),
        min(len(eligible_pool), MAX_RESULTS)
    )

    if not eligible_pool:
        logger.warning("No Sketchfab search results passed the downloadable+CC filters for query: '%s'", query)
        raise ValueError(f"Nessun modello 3D trovato per la ricerca: '{query}'")

    # Score each candidate for deterministic ranking
    for model in eligible_pool:
        m_name = model.get("name", "")
        model["_relevance_score"] = score_relevance(m_name, query)

    # Sort descending by score. Since Python's sorting is stable, candidates with the same
    # relevance score will naturally maintain their original position of appearance.
    sorted_pool = sorted(eligible_pool, key=lambda x: x["_relevance_score"], reverse=True)

    results = []
    # Map to the API-contract candidate structure
    for model in sorted_pool[:MAX_RESULTS]:
        uid = model.get("uid")
        name = model.get("name", "Modello 3D")
        author_info = model.get("user", {})
        author_name = author_info.get("displayName") or author_info.get("username") or "Autore sconosciuto"

        resolved = model.get("_resolved_license")
        license_name = resolved["license"] if resolved else "CC BY"
        thumbnail_url = get_thumbnail_url(model.get("thumbnails"))

        results.append({
            "uid": uid,
            "name": name,
            "thumbnail_url": thumbnail_url,
            "author": author_name,
            "license": license_name,
            "is_downloadable": True,
            "model_url": model.get("viewerUrl") or f"https://sketchfab.com/models/{uid}",
            "license_info": resolved,
            "search_relevance": model.get("_relevance_score", 0.0)
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
