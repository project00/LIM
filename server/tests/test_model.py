"""
Unit and Integration Tests for Sketchfab 3D Model Service.

Design Note:
    This module tests the model search, details retrieval, local glTF caching,
    unzipping, security validations, and E2E API routing.
    It mocks all external HTTP requests to Sketchfab's endpoints using standard mock decorators.
"""

import sys
import os
import zipfile
import io
import shutil
import pytest
import httpx
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.model_service import (
    search_3d_models,
    fetch_3d_model_by_uid,
    extract_significant_words,
    get_license_info,
    is_cc_licensed,
    CACHE_DIR
)
from main import app


@pytest.fixture(autouse=True)
def clean_cache_dir() -> None:
    """Ensures test runs start with a clean or isolated cache folder to avoid state leakage."""
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
    os.makedirs(CACHE_DIR, exist_ok=True)
    yield
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)


def create_dummy_zip_bytes() -> bytes:
    """Helper to create dummy in-memory ZIP archive bytes containing a scene.gltf file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zip_ref:
        zip_ref.writestr("scene.gltf", "{'info': 'dummy glTF file'}")
        zip_ref.writestr("scene.bin", b"\x00\x01\x02")
    return buf.getvalue()


def create_unsafe_zip_bytes_slip() -> bytes:
    """Helper to create unsafe ZIP archive bytes demonstrating path traversal (Zip Slip)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zip_ref:
        # File pointing outside the output folder
        zip_ref.writestr("../unsafe_file.txt", "unsafe content")
    return buf.getvalue()


# 1. Normalizzazione Search API Test
def test_extract_significant_words() -> None:
    """Tests normalization and significant words extraction."""
    words = extract_significant_words("L'elefante con un grande cappello-rosso")
    # Expected significant words (lowercased, punctuation-cleaned, stopwords ignored, length >= 2)
    assert "elefante" in words
    assert "grande" in words
    assert "cappello" in words
    assert "rosso" in words
    assert "con" not in words
    assert "un" not in words


# 2-5. CC License Mapping Tests (CC0, CC BY, CC BY-NC, unrecognized, missing)
def test_get_license_info_mapping() -> None:
    """Tests license retrieval using get_license_info by uid, slug, label, or fullName."""
    # CC BY by UID
    by_info = get_license_info({"uid": "322a749bcfa841b29dff1e8a1bb74b0b"})
    assert by_info is not None
    assert by_info["slug"] == "by"
    assert by_info["attribution_required"] is True
    assert by_info["commercial_use"] is True

    # CC BY-NC by slug
    nc_info = get_license_info({"slug": "by-nc"})
    assert nc_info is not None
    assert nc_info["slug"] == "by-nc"
    assert nc_info["commercial_use"] is False

    # CC0 by label
    cc0_info = get_license_info({"label": "CC0 Public Domain"})
    assert cc0_info is not None
    assert cc0_info["slug"] == "cc0"
    assert cc0_info["attribution_required"] is False

    # Unrecognized license
    unrec = get_license_info({"uid": "invalid-uid", "slug": "commercial-standard"})
    assert unrec is None

    # Missing license
    assert get_license_info(None) is None


def test_is_cc_licensed() -> None:
    """Tests is_cc_licensed helper."""
    assert is_cc_licensed({"uid": "322a749bcfa841b29dff1e8a1bb74b0b"}) is True  # CC BY
    assert is_cc_licensed({"uid": "7c23a1ba438d4306920229c12afcb5f9"}) is True  # CC0
    assert is_cc_licensed({"slug": "by-nc-nd"}) is True                        # CC BY-NC-ND
    assert is_cc_licensed({"slug": "free-st"}) is False                         # Free Standard (non-CC)
    assert is_cc_licensed({}) is False


# 6-8. Error handling on Search (401, 403)
@patch("httpx.Client.get")
def test_search_3d_models_401(mock_get: MagicMock) -> None:
    """Tests that a 401 response from Search API raises an appropriate RuntimeError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_get.return_value = mock_resp

    with pytest.raises(RuntimeError, match="Autenticazione Sketchfab fallita"):
        search_3d_models("ELEPHANT", "test-token")


@patch("httpx.Client.get")
def test_search_3d_models_403(mock_get: MagicMock) -> None:
    """Tests that a 403 response from Search API raises an appropriate RuntimeError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_get.return_value = mock_resp

    with pytest.raises(RuntimeError, match="Accesso vietato alla ricerca"):
        search_3d_models("ELEPHANT", "test-token")


# 9-10. Error handling on Fetch (401, 403)
@patch("httpx.Client.get")
def test_fetch_3d_model_401(mock_get: MagicMock) -> None:
    """Tests that 401 on fetch_3d_model_by_uid raises correct error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_get.return_value = mock_resp

    with pytest.raises(RuntimeError, match="Autenticazione Sketchfab fallita"):
        fetch_3d_model_by_uid("uid123", "test-token")


@patch("httpx.Client.get")
def test_fetch_3d_model_403(mock_get: MagicMock) -> None:
    """Tests that 403 on fetch_3d_model_by_uid raises correct error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    mock_get.return_value = mock_resp

    with pytest.raises(RuntimeError, match="Accesso vietato a questo modello"):
        fetch_3d_model_by_uid("uid123", "test-token")


# 11-13. Download & ZIP Edge cases (Missing Download URL, Expired URL, Path Traversal / Zip Slip)
@patch("httpx.Client.get")
def test_fetch_download_url_missing(mock_get: MagicMock) -> None:
    """Tests when temporary download URL is missing from Sketchfab response."""
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "uid123", "name": "Elephant", "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"}
    }
    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {}  # Empty gltf info

    mock_get.side_effect = [mock_detail, mock_download]

    with pytest.raises(RuntimeError, match="Nessun link di download glTF disponibile"):
        fetch_3d_model_by_uid("uid123", "test-token")


@patch("httpx.Client.get")
def test_fetch_temporary_url_expired(mock_get: MagicMock) -> None:
    """Tests when temporary URL has expired (AWS returns 403 or 400)."""
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "uid123", "name": "Elephant", "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"}
    }
    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {"gltf": {"url": "https://temp-s3-url.com/model.zip"}}
    mock_aws = MagicMock()
    mock_aws.status_code = 403  # Expired URL

    mock_get.side_effect = [mock_detail, mock_download, mock_aws]

    with pytest.raises(RuntimeError, match="Il link temporaneo per scaricare il modello è scaduto"):
        fetch_3d_model_by_uid("uid123", "test-token")


@patch("httpx.Client.get")
def test_fetch_zip_path_traversal_slip(mock_get: MagicMock) -> None:
    """Tests Zip Slip path traversal protection."""
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "uid123", "name": "Elephant", "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"}
    }
    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {"gltf": {"url": "https://temp-s3-url.com/model.zip"}}
    mock_aws = MagicMock()
    mock_aws.status_code = 200
    mock_aws.content = create_unsafe_zip_bytes_slip()

    mock_get.side_effect = [mock_detail, mock_download, mock_aws]

    with pytest.raises(RuntimeError, match="Tentativo di Zip Slip / Path Traversal rilevato"):
        fetch_3d_model_by_uid("uid123", "test-token")


# 14. Missing Token check
def test_missing_tokens_raises() -> None:
    """Tests that search and select raise if sketchfab_token is missing or empty."""
    with pytest.raises(RuntimeError, match="Sketchfab access token is not configured"):
        search_3d_models("ELEPHANT", "")

    with pytest.raises(RuntimeError, match="Sketchfab access token is not configured"):
        fetch_3d_model_by_uid("uid123", "")


# 15. Pagination search check
@patch("httpx.Client.get")
def test_paginated_search_success(mock_get: MagicMock) -> None:
    """Tests robust multi-page / cursor pagination on Sketchfab search."""
    # First page returns a non-CC model and a "next" page URL
    mock_page1 = MagicMock()
    mock_page1.status_code = 200
    mock_page1.json.return_value = {
        "next": "https://api.sketchfab.com/v3/models?cursor=abc",
        "results": [
            {
                "uid": "model_non_cc",
                "name": "Non-CC Elephant",
                "isDownloadable": True,
                "license": {"uid": "72eb2b1960364637901eacce19283624"}  # Free standard, non-CC
            }
        ]
    }

    # Second page returns a CC model
    mock_page2 = MagicMock()
    mock_page2.status_code = 200
    mock_page2.json.return_value = {
        "next": None,
        "results": [
            {
                "uid": "model_cc_elephant",
                "name": "CC-BY Elephant",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},  # CC BY
                "thumbnails": {"images": [{"url": "thumb.jpg", "width": 256}]}
            }
        ]
    }

    mock_get.side_effect = [mock_page1, mock_page2]

    results = search_3d_models("ELEPHANT", "test-token")
    assert len(results) == 1
    assert results[0]["uid"] == "model_cc_elephant"
    assert results[0]["name"] == "CC-BY Elephant"


# 16. Elephant Query logic check
@patch("httpx.Client.get")
def test_query_elephant_success(mock_get: MagicMock) -> None:
    """Tests ELEPHANT query success where search returns 'license' omitting 'slug'."""
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "elephant_uid_123",
                "name": "African Elephant (CC-BY)",
                "isDownloadable": True,
                "viewerUrl": "https://sketchfab.com/models/elephant_uid_123",
                "user": {
                    "username": "animal_artist",
                    "displayName": "Animal Artist"
                },
                "license": {
                    "uid": "322a749bcfa841b29dff1e8a1bb74b0b",
                    "label": "CC Attribution"
                    # "slug" IS OMITTED as per real Search API!
                },
                "thumbnails": {
                    "images": [
                        {"url": "thumb_256.jpg", "width": 256, "height": 144}
                    ]
                }
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    results = search_3d_models("ELEPHANT", "test-token")
    assert len(results) == 1
    assert results[0]["uid"] == "elephant_uid_123"
    assert results[0]["name"] == "African Elephant (CC-BY)"
    assert results[0]["license_info"]["license"] == "by"


# 17. Mocked E2E Integration Flow Test
@patch("httpx.Client.get")
def test_integration_flow_mocked(mock_get: MagicMock) -> None:
    """
    Mocked E2E integration test:
    search -> filter -> license -> download request -> temporary URL -> archive extraction.
    """
    # 1. Search response with downloadable CC model
    mock_search = MagicMock()
    mock_search.status_code = 200
    mock_search.json.return_value = {
        "results": [
            {
                "uid": "e2e_model_999",
                "name": "E2E African Elephant",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
                "thumbnails": {"images": [{"url": "thumb.jpg", "width": 256}]}
            }
        ]
    }

    # 2. Detail model response
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "e2e_model_999",
        "name": "E2E African Elephant",
        "viewerUrl": "https://sketchfab.com/models/e2e_model_999",
        "user": {"username": "artist_e2e", "displayName": "Artist E2E"},
        "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"}
    }

    # 3. Download link response
    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {
        "gltf": {"url": "https://s3.amazonaws.com/sketchfab/archives/e2e_gltf.zip"}
    }

    # 4. ZIP archive bytes download response
    mock_archive = MagicMock()
    mock_archive.status_code = 200
    mock_archive.content = create_dummy_zip_bytes()

    mock_get.side_effect = [mock_search, mock_detail, mock_download, mock_archive]

    # Run search
    search_results = search_3d_models("ELEPHANT", "test-token")
    assert len(search_results) == 1
    assert search_results[0]["uid"] == "e2e_model_999"

    # Run fetch/download
    metadata = fetch_3d_model_by_uid("e2e_model_999", "test-token")
    assert metadata["uid"] == "e2e_model_999"
    assert metadata["title"] == "E2E African Elephant"
    assert metadata["model_url"] == "/models/e2e_model_999/scene.gltf"

    # Verify zip extraction and attribution files
    assert os.path.exists(os.path.join(CACHE_DIR, "e2e_model_999", "scene.gltf"))
    assert os.path.exists(os.path.join(CACHE_DIR, "e2e_model_999", "metadata.json"))
    assert os.path.exists(os.path.join(CACHE_DIR, "e2e_model_999", "sf_attribution.json"))


# ------------------ End-to-End API Routing Tests (re-validated) ------------------

@patch("main.search_3d_models")
def test_api_search_3d_models_success(mock_search: MagicMock) -> None:
    """Tests POST /api/v1/analyze for action 'search_3d_models' returns list of candidates."""
    mock_search.return_value = [
        {
            "uid": "model_1",
            "name": "Model 1",
            "thumbnail_url": "thumb1.jpg",
            "author": "Author 1",
            "license": "CC-BY",
            "is_downloadable": True,
            "model_url": "https://sketchfab.com/models/model_1",
            "license_info": {
                "license": "by",
                "license_label": "CC Attribution",
                "license_url": "http://creativecommons.org/licenses/by/4.0/",
                "creator": "Author 1",
                "creator_url": "https://sketchfab.com/author1",
                "source_url": "https://sketchfab.com/models/model_1",
                "attribution_required": True,
                "commercial_use": True,
                "derivatives_allowed": True
            }
        }
    ]

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-Sketchfab-Token": "test-sketchfab-token"
    }
    payload = {
        "action": "search_3d_models",
        "data": {
            "query": "ELEPHANT"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "model_search_results"
    assert data["source"] == "remote_index"
    assert len(data["results"]) == 1
    assert data["results"][0]["uid"] == "model_1"


@patch("main.fetch_3d_model_by_uid")
def test_api_select_3d_model_success(mock_fetch: MagicMock) -> None:
    """Tests POST /api/v1/analyze for action 'select_3d_model' returns stable glTF model URL."""
    mock_fetch.return_value = {
        "uid": "model_uid_abc",
        "title": "Selected Model",
        "model_url": "/models/model_uid_abc/scene.gltf",
        "attribution": {
            "author": "Creator display",
            "license": "CC Attribution",
            "source_url": "https://sketchfab.com/models/model_uid_abc"
        },
        "license_info": {
            "license": "by",
            "license_label": "CC Attribution"
        }
    }

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-Sketchfab-Token": "test-sketchfab-token"
    }
    payload = {
        "action": "select_3d_model",
        "data": {
            "uid": "model_uid_abc"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "model_3d"
    assert data["source"] == "remote_index"
    assert data["model_url"] == "/models/model_uid_abc/scene.gltf"
    assert data["label"] == "Selected Model"
    assert data["attribution"]["author"] == "Creator display"


def test_api_search_3d_models_missing_credentials() -> None:
    """Tests POST /api/v1/analyze returns MISSING_CREDENTIALS error if X-Sketchfab-Token is absent on search."""
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {
        "action": "search_3d_models",
        "data": {
            "query": "H2O"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "MISSING_CREDENTIALS"
    assert data["action"] == "search_3d_models"


def test_api_select_3d_model_missing_credentials() -> None:
    """Tests POST /api/v1/analyze returns MISSING_CREDENTIALS error if X-Sketchfab-Token is absent on select."""
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {
        "action": "select_3d_model",
        "data": {
            "uid": "model_uid_123"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "MISSING_CREDENTIALS"
    assert data["action"] == "select_3d_model"
