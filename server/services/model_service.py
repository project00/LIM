"""
Model Service for LIM-AI Copilot Remote Server.

Design Note:
    This module handles searching, fetching, unzipping, and caching 3D models
    from Sketchfab's Download API. It filters models to prefer those explicitly
    marked downloadable and under a Creative Commons (CC) license for educational use.
    It caches models in the local file system (server/model_cache/<uid>/) and avoids
    repeated downloads.
"""

import logging
import os
import zipfile
import io
import shutil
import json
import httpx
import datetime
import time

logger = logging.getLogger("server_model_service")

# Set up local cache path relative to this service or the server root
CACHE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "model_cache"))

# Standard Sketchfab CC licenses information
LICENSES_INFO = {
    "322a749bcfa841b29dff1e8a1bb74b0b": {
        "slug": "by",
        "label": "CC Attribution",
        "fullName": "Creative Commons Attribution",
        "url": "http://creativecommons.org/licenses/by/4.0/",
        "attribution_required": True,
        "commercial_use": True,
        "derivatives_allowed": True
    },
    "b9ddc40b93e34cdca1fc152f39b9f375": {
        "slug": "by-sa",
        "label": "CC Attribution-ShareAlike",
        "fullName": "Creative Commons Attribution-ShareAlike",
        "url": "http://creativecommons.org/licenses/by-sa/4.0/",
        "attribution_required": True,
        "commercial_use": True,
        "derivatives_allowed": True
    },
    "72360ff1740d419791934298b8b6d270": {
        "slug": "by-nd",
        "label": "CC Attribution-NoDerivs",
        "fullName": "Creative Commons Attribution-NoDerivs",
        "url": "http://creativecommons.org/licenses/by-nd/4.0/",
        "attribution_required": True,
        "commercial_use": True,
        "derivatives_allowed": False
    },
    "bbfe3f7dbcdd4122b966b85b9786a989": {
        "slug": "by-nc",
        "label": "CC Attribution-NonCommercial",
        "fullName": "Creative Commons Attribution-NonCommercial",
        "url": "http://creativecommons.org/licenses/by-nc/4.0/",
        "attribution_required": True,
        "commercial_use": False,
        "derivatives_allowed": True
    },
    "2628dbe5140a4e9592126c8df566c0b7": {
        "slug": "by-nc-sa",
        "label": "CC Attribution-NonCommercial-ShareAlike",
        "fullName": "Creative Commons Attribution-NonCommercial-ShareAlike",
        "url": "http://creativecommons.org/licenses/by-nc-sa/4.0/",
        "attribution_required": True,
        "commercial_use": False,
        "derivatives_allowed": True
    },
    "34b725081a6a4184957efaec2cb84ed3": {
        "slug": "by-nc-nd",
        "label": "CC Attribution-NonCommercial-NoDerivs",
        "fullName": "Creative Commons Attribution-NonCommercial-NoDerivs",
        "url": "http://creativecommons.org/licenses/by-nc-nd/4.0/",
        "attribution_required": True,
        "commercial_use": False,
        "derivatives_allowed": False
    },
    "7c23a1ba438d4306920229c12afcb5f9": {
        "slug": "cc0",
        "label": "CC0 Public Domain",
        "fullName": "CC0 Public Domain",
        "url": "http://creativecommons.org/publicdomain/zero/1.0/",
        "attribution_required": False,
        "commercial_use": True,
        "derivatives_allowed": True
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


def get_license_info(license_data: dict | None) -> dict | None:
    """
    Resolves standard Sketchfab license info using uid, slug, label, or fullName.
    """
    if not license_data:
        return None

    uid = license_data.get("uid")
    if uid and uid in LICENSES_INFO:
        return LICENSES_INFO[uid]

    slug = license_data.get("slug", "").lower()
    if slug:
        for k, v in LICENSES_INFO.items():
            if v["slug"] == slug:
                return v

    label = license_data.get("label", "").lower()
    if label:
        # Exact match first
        for k, v in LICENSES_INFO.items():
            if v["label"].lower() == label:
                return v
        # Substring match next
        for k, v in LICENSES_INFO.items():
            if label in v["label"].lower() or v["label"].lower() in label:
                return v

    fullName = license_data.get("fullName", "").lower()
    if fullName:
        # Exact match first
        for k, v in LICENSES_INFO.items():
            if v["fullName"].lower() == fullName:
                return v
        # Substring match next
        for k, v in LICENSES_INFO.items():
            if fullName in v["fullName"].lower() or v["fullName"].lower() in fullName:
                return v

    return None


def is_cc_licensed(license_data: dict) -> bool:
    """
    Checks if the license is Creative Commons.
    """
    return get_license_info(license_data) is not None


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
    up to 8 candidates sorted by query match, using a paginated loop for robust search results.
    """
    logger.info("Searching Sketchfab for 3D model candidates: '%s'", query)

    if not sketchfab_token:
        logger.error("Sketchfab access token is empty or missing.")
        raise RuntimeError("Sketchfab access token is not configured. Request cannot be processed.")

    # Search constants for robust paginated retrieval
    MAX_ELIGIBLE = 8
    MAX_PAGES = 5
    MAX_CANDIDATES = 100
    REQUEST_TIMEOUT = 10.0

    eligible_models = []
    candidates_count = 0

    search_url = "https://api.sketchfab.com/v3/models"
    params = {
        "q": query,
        "limit": 24,
        "downloadable": "true"  # Official downloadable filtering parameter
    }

    auth_headers = get_auth_headers(sketchfab_token)
    next_url = search_url

    for page in range(MAX_PAGES):
        if len(eligible_models) >= MAX_ELIGIBLE or candidates_count >= MAX_CANDIDATES:
            break

        logger.info("Sending search query to Sketchfab page %d. URL: '%s'", page + 1, next_url)

        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                if next_url == search_url:
                    response = client.get(search_url, params=params, headers=auth_headers)
                else:
                    response = client.get(next_url, headers=auth_headers)

                logger.info("Received response from Sketchfab Search API page %d. Status code: %d", page + 1, response.status_code)

                if response.status_code == 401:
                    logger.error("Sketchfab search failed: HTTP 401 Unauthorized")
                    raise RuntimeError("Autenticazione Sketchfab fallita: token non valido o scaduto.")
                elif response.status_code == 403:
                    logger.error("Sketchfab search failed: HTTP 403 Forbidden")
                    raise RuntimeError("Accesso vietato alla ricerca Sketchfab (HTTP 403).")
                elif response.status_code == 429:
                    logger.error("Sketchfab search failed: HTTP 429 Rate Limit")
                    raise RuntimeError("Limite di richieste (rate limit) di Sketchfab superato.")
                elif response.status_code != 200:
                    logger.error("Sketchfab search failed with non-200 status code: %d. Error details: %s", response.status_code, response.text)
                    raise RuntimeError(f"Sketchfab Search API failure (HTTP {response.status_code}): {response.text}")

                search_data = response.json()
        except httpx.HTTPError as e:
            logger.error("Network error during Sketchfab search page %d: %s", page + 1, e)
            if page == 0:
                raise RuntimeError(f"Impossibile connettersi a Sketchfab due to network error: {e}")
            else:
                break

        raw_results = search_data.get("results", [])
        logger.info("Page %d returned %d raw candidates.", page + 1, len(raw_results))

        if not raw_results and page == 0:
            logger.warning("No Sketchfab search results for query: '%s'", query)
            raise ValueError(f"Nessun modello 3D trovato per la ricerca: '{query}'")

        for idx, model in enumerate(raw_results):
            candidates_count += 1
            m_name = model.get("name", "Modello Sconosciuto")
            m_uid = model.get("uid", "no-uid")
            is_dl = model.get("isDownloadable")

            # Validate downloadability (default to True because downloadable=true is set on query)
            if is_dl is False:
                logger.info("Candidate '%s' (UID: %s) rejected: not downloadable", m_name, m_uid)
                continue

            license_info = model.get("license")
            lic_info = get_license_info(license_info)

            if not lic_info:
                logger.info("Candidate '%s' (UID: %s) rejected: license not compatible or undetermined with educational policy", m_name, m_uid)
                continue

            logger.info("Candidate '%s' (UID: %s) downloadable and CC-licensed -> eligible", m_name, m_uid)
            if not any(m.get("uid") == m_uid for m in eligible_models):
                eligible_models.append(model)

        next_url = search_data.get("next")
        if not next_url:
            break

        time.sleep(0.1)

    if not eligible_models:
        logger.warning("No Sketchfab search results passed the downloadable+CC filters for query: '%s'", query)
        raise ValueError(f"Nessun modello 3D trovato per la ricerca: '{query}'")

    # Sort preference: matching significant query words first, then the rest
    significant_words = extract_significant_words(query)
    logger.info("Significant words for query '%s': %s", query, significant_words)

    matching = []
    non_matching = []
    for model in eligible_models:
        m_name_lower = model.get("name", "Modello Sconosciuto").lower()
        if any(word in m_name_lower for word in significant_words):
            matching.append(model)
        else:
            non_matching.append(model)

    sorted_candidates = matching + non_matching
    results = []

    # Map to the API-contract candidate structure with detailed license metadata
    for model in sorted_candidates[:8]:
        uid = model.get("uid")
        name = model.get("name", "Modello 3D")
        author_info = model.get("user", {})
        author_name = author_info.get("displayName") or author_info.get("username") or "Autore sconosciuto"
        license_info = model.get("license")
        lic_info = get_license_info(license_info)
        license_name = lic_info["fullName"] if lic_info else ((model.get("license") or {}).get("fullName") or "CC Attribution")
        thumbnail_url = get_thumbnail_url(model.get("thumbnails"))

        results.append({
            "uid": uid,
            "name": name,
            "thumbnail_url": thumbnail_url,
            "author": author_name,
            "license": license_name,
            "is_downloadable": True,
            "model_url": model.get("viewerUrl") or f"https://sketchfab.com/models/{uid}",
            "license_info": {
                "license": lic_info["slug"] if lic_info else "by",
                "license_label": lic_info["label"] if lic_info else "CC Attribution",
                "license_url": lic_info["url"] if lic_info else "http://creativecommons.org/licenses/by/4.0/",
                "creator": author_name,
                "creator_url": author_info.get("profileUrl") or f"https://sketchfab.com/{author_info.get('username', '')}",
                "source_url": model.get("viewerUrl") or f"https://sketchfab.com/models/{uid}",
                "attribution_required": lic_info["attribution_required"] if lic_info else True,
                "commercial_use": lic_info["commercial_use"] if lic_info else True,
                "derivatives_allowed": lic_info["derivatives_allowed"] if lic_info else True
            }
        })

    logger.info("Returned %d filtered and sorted candidates.", len(results))
    return results


def fetch_3d_model_by_uid(uid: str, sketchfab_token: str) -> dict:
    """
    Downloads, extracts, and caches a 3D model by its known UID, returning its metadata.
    Enforces security limits and ZIP Slip prevention.
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

            if response.status_code == 401:
                logger.error("Sketchfab authentication failed: HTTP 401")
                raise RuntimeError("Autenticazione Sketchfab fallita: token non valido o scaduto.")
            elif response.status_code == 403:
                logger.error("Sketchfab access forbidden: HTTP 403")
                raise RuntimeError("Accesso vietato a questo modello Sketchfab (HTTP 403).")
            elif response.status_code == 404:
                logger.error("Sketchfab model not found: HTTP 404")
                raise ValueError("Modello Sketchfab non trovato (HTTP 404).")
            elif response.status_code == 429:
                logger.error("Sketchfab rate limit reached: HTTP 429")
                raise RuntimeError("Limite di richieste (rate limit) di Sketchfab superato.")
            elif response.status_code != 200:
                logger.error("Sketchfab model detail failed with status code: %d. Error details: %s", response.status_code, response.text)
                raise RuntimeError(f"Sketchfab Model Detail API failure (HTTP {response.status_code}).")

            model = response.json()
    except httpx.HTTPError as e:
        logger.error("Network error during Sketchfab model detail request: %s", e)
        raise RuntimeError(f"Impossibile connettersi a Sketchfab due to network error: {e}")

    # Enforce license existence and CC criteria
    license_info = model.get("license")
    if not license_info:
        raise RuntimeError("Impossibile scaricare: il modello non ha una licenza associata.")

    lic_info = get_license_info(license_info)
    if not lic_info:
        raise RuntimeError("Impossibile scaricare: licenza del modello non compatibile con l'uso scolastico o non riconosciuta.")

    name = model.get("name", "Modello 3D")
    author_info = model.get("user", {})
    author_name = author_info.get("displayName") or author_info.get("username") or "Autore sconosciuto"
    license_name = lic_info["fullName"]
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
                if download_resp.status_code == 401:
                    logger.error("Sketchfab download auth failed: HTTP 401")
                    raise RuntimeError("Autenticazione fallita per il download del modello: token non valido o scaduto.")
                elif download_resp.status_code == 403:
                    logger.error("Sketchfab download forbidden: HTTP 403")
                    raise RuntimeError("Il download di questo modello non è consentito (HTTP 403).")
                elif download_resp.status_code == 404:
                    logger.error("Sketchfab download endpoint returned HTTP 404")
                    raise RuntimeError("Il modello o l'endpoint di download non è stato trovato (HTTP 404).")
                elif download_resp.status_code == 429:
                    logger.error("Sketchfab download rate limit reached: HTTP 429")
                    raise RuntimeError("Limite di richieste di download superato per Sketchfab (HTTP 429).")
                elif download_resp.status_code != 200:
                    logger.error("Failed to request download for model %s: status code: %d - %s", uid, download_resp.status_code, download_resp.text)
                    raise RuntimeError(f"Errore nella richiesta di download a Sketchfab (HTTP {download_resp.status_code}).")

                download_info = download_resp.json()
        except httpx.HTTPError as e:
            logger.error("Network error during Sketchfab download request: %s", e)
            raise RuntimeError(f"Impossibile richiedere il download a Sketchfab due to network error: {e}")

        gltf_info = download_info.get("gltf")
        if not gltf_info or not gltf_info.get("url"):
            logger.error("Sketchfab returned no glTF download URL: %s", download_info)
            raise RuntimeError("Nessun link di download glTF disponibile per questo modello (modello non scaricabile).")

        download_archive_url = gltf_info["url"]
        logger.info("Resolved glTF download URL successfully (masked for security).")

        # Download and extract the archive immediately
        logger.info("Downloading binary model ZIP archive from AWS S3 resolved URL...")
        try:
            with httpx.Client(timeout=30.0) as client:
                archive_resp = client.get(download_archive_url)
                logger.info("Archive download response status code: %d", archive_resp.status_code)
                if archive_resp.status_code in (400, 403):
                    logger.error("Temporary download URL has expired: %d", archive_resp.status_code)
                    raise RuntimeError("Il link temporaneo per scaricare il modello è scaduto. Riprova.")
                elif archive_resp.status_code != 200:
                    logger.error("Failed to download model archive from AWS S3. Status: %d", archive_resp.status_code)
                    raise RuntimeError(f"Download dell'archivio glTF fallito (HTTP {archive_resp.status_code}).")

                archive_bytes = archive_resp.content
        except httpx.HTTPError as e:
            logger.error("Network error during archive download: %s", e)
            raise RuntimeError(f"Errore di download dell'archivio glTF due to network error: {e}")

        # Extract unzipped archive directly to cache directory with robust Zip Slip & size validation
        logger.info("Extracting ZIP archive (%d bytes) to cache directory: %s", len(archive_bytes), model_dir)
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zip_ref:
                # Zip Slip Protection & safety limits
                total_size = 0
                max_allowed_size = 100 * 1024 * 1024  # 100 MB limit
                max_allowed_files = 100

                file_count = len(zip_ref.infolist())
                if file_count > max_allowed_files:
                    raise RuntimeError(f"Numero di file nell'archivio supera il limite massimo consentito ({max_allowed_files}).")

                for member in zip_ref.infolist():
                    # Zip Slip check
                    target_path = os.path.abspath(os.path.join(model_dir, member.filename))
                    if not target_path.startswith(os.path.abspath(model_dir)):
                        raise RuntimeError(f"Tentativo di Zip Slip / Path Traversal rilevato per il file: {member.filename}")

                    total_size += member.file_size
                    if total_size > max_allowed_size:
                        raise RuntimeError(f"Dimensione decompressa totale supera il limite consentito ({max_allowed_size} bytes).")

                zip_ref.extractall(model_dir)
            logger.info("Successfully extracted model archive into cache directory %s", model_dir)
        except Exception as e:
            logger.error("Unzipping glTF archive failed: %s", e)
            # Cleanup broken folder on failure
            if os.path.exists(model_dir):
                shutil.rmtree(model_dir)
            raise RuntimeError(f"Estrazione dell'archivio glTF fallita o archivio corrotto: {e}")

    # Conforming return object
    stable_local_url = f"/models/{uid}/scene.gltf"
    download_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    lic_url = lic_info["url"] if lic_info else "http://creativecommons.org/licenses/"

    lic_details = {
        "license": lic_info["slug"],
        "license_label": lic_info["label"],
        "license_url": lic_info["url"],
        "creator": author_name,
        "creator_url": author_info.get("profileUrl") or f"https://sketchfab.com/{author_info.get('username', '')}",
        "source_url": source_url,
        "attribution_required": lic_info["attribution_required"],
        "commercial_use": lic_info["commercial_use"],
        "derivatives_allowed": lic_info["derivatives_allowed"]
    }

    res = {
        "uid": uid,
        "title": name,
        "model_url": stable_local_url,
        "attribution": {
            "author": author_name,
            "license": license_name,
            "source_url": source_url,
            "license_url": lic_url,
            "downloaded_at": download_time,
            "source": "Sketchfab"
        },
        "license_info": lic_details
    }

    # Save to both metadata.json and sf_attribution.json in cached directory
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=4)

        attribution_file = os.path.join(model_dir, "sf_attribution.json")
        with open(attribution_file, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.warning("Failed to save metadata/attribution files: %s", e)

    return res
