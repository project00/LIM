"""
Unit and Integration Tests for Sketchfab 3D Model Service.

Design Note:
    This module tests the model search, local glTF caching, unzipping, and API routing.
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

from services.model_service import search_and_fetch_3d_model, CACHE_DIR
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


@patch("httpx.Client.get")
def test_search_and_fetch_3d_model_cache_miss_success(mock_get: MagicMock) -> None:
    """Tests a full cache-miss download pipeline: search model, request download link, download zip, unzip and serve."""

    # 1. Setup mock search response (index 0)
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "model_uid_123",
                "name": "Water Molecule H2O",
                "isDownloadable": True,
                "viewerUrl": "https://sketchfab.com/models/model_uid_123",
                "user": {
                    "username": "science_creator",
                    "displayName": "Science Creator"
                },
                "license": {
                    "slug": "by",
                    "fullName": "CC Attribution"
                }
            }
        ]
    }

    # 2. Setup mock download link response (index 1)
    mock_download_resp = MagicMock()
    mock_download_resp.status_code = 200
    mock_download_resp.json.return_value = {
        "gltf": {
            "url": "https://s3.amazonaws.com/sketchfab/archives/gltf.zip",
            "size": 1024,
            "expires": 300
        }
    }

    # 3. Setup mock zip archive response (index 2)
    mock_archive_resp = MagicMock()
    mock_archive_resp.status_code = 200
    mock_archive_resp.content = create_dummy_zip_bytes()

    # Assign side effects sequentially to mock_get
    mock_get.side_effect = [mock_search_resp, mock_download_resp, mock_archive_resp]

    # Run the service with explicit sketchfab_token argument
    metadata = search_and_fetch_3d_model("H2O", "test-sketchfab-token")

    # Assert correct metadata returned
    assert metadata["uid"] == "model_uid_123"
    assert metadata["title"] == "Water Molecule H2O"
    assert metadata["model_url"] == "/models/model_uid_123/scene.gltf"
    assert metadata["attribution"]["author"] == "Science Creator"
    assert metadata["attribution"]["license"] == "CC Attribution"
    assert metadata["attribution"]["source_url"] == "https://sketchfab.com/models/model_uid_123"

    # Verify folder was extracted and scene.gltf cached
    cached_gltf = os.path.join(CACHE_DIR, "model_uid_123", "scene.gltf")
    assert os.path.exists(cached_gltf)

    # Check total HTTP calls: 1. search, 2. download link, 3. archive download
    assert mock_get.call_count == 3


@patch("httpx.Client.get")
def test_search_and_fetch_3d_model_cache_hit_skips_download(mock_get: MagicMock) -> None:
    """Tests that on a cache hit, the service skips the download steps entirely and returns metadata from the search."""

    # 1. Pre-populate cache folder manually
    model_dir = os.path.join(CACHE_DIR, "model_uid_123")
    os.makedirs(model_dir, exist_ok=True)
    with open(os.path.join(model_dir, "scene.gltf"), "w") as f:
        f.write("{'info': 'manually cached gltf'}")

    # 2. Setup mock search response (the only HTTP call needed!)
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "model_uid_123",
                "name": "Water Molecule H2O",
                "isDownloadable": True,
                "viewerUrl": "https://sketchfab.com/models/model_uid_123",
                "user": {
                    "username": "science_creator",
                    "displayName": "Science Creator"
                },
                "license": {
                    "slug": "by",
                    "fullName": "CC Attribution"
                }
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    # Run service with explicit sketchfab_token argument
    metadata = search_and_fetch_3d_model("H2O", "test-sketchfab-token")

    # Assert metadata
    assert metadata["uid"] == "model_uid_123"
    assert metadata["model_url"] == "/models/model_uid_123/scene.gltf"

    # Verify ONLY the search GET was made (no download, no archive GET)
    assert mock_get.call_count == 1


@patch("httpx.Client.get")
def test_search_no_results_raises_value_error(mock_get: MagicMock) -> None:
    """Tests that if search returns empty results, a ValueError (MODEL_NOT_FOUND) is raised."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": []
    }
    mock_get.return_value = mock_resp

    with pytest.raises(ValueError, match="Nessun modello 3D trovato"):
        search_and_fetch_3d_model("impossible_search_query_123", "test-sketchfab-token")


@patch("httpx.Client.get")
def test_search_api_failure_raises_runtime_error(mock_get: MagicMock) -> None:
    """Tests that if the search API returns a non-200 failure status, a RuntimeError is raised."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error from Sketchfab"
    mock_get.return_value = mock_resp

    with pytest.raises(RuntimeError, match="Sketchfab Search API failure"):
        search_and_fetch_3d_model("H2O", "test-sketchfab-token")


# ------------------ API End-to-End Routing Tests ------------------

@patch("litellm.completion")
@patch("httpx.Client.get")
def test_api_load_3d_model_success(mock_sketchfab_get: MagicMock, mock_llm: MagicMock) -> None:
    """Tests POST /api/v1/analyze for action 'load_3d_model' returns model metadata on success."""

    # Pre-populate cache folder manually to keep test simple (1 search call only)
    model_dir = os.path.join(CACHE_DIR, "model_uid_abc")
    os.makedirs(model_dir, exist_ok=True)
    with open(os.path.join(model_dir, "scene.gltf"), "w") as f:
        f.write("{'info': 'cached'}")

    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "model_uid_abc",
                "name": "Water Molecule H2O",
                "isDownloadable": True,
                "viewerUrl": "https://sketchfab.com/models/model_uid_abc",
                "user": {
                    "username": "creator",
                    "displayName": "Creator display"
                },
                "license": {
                    "slug": "by",
                    "fullName": "CC Attribution"
                }
            }
        ]
    }
    mock_sketchfab_get.return_value = mock_search_resp

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-Sketchfab-Token": "test-sketchfab-token"
    }
    payload = {
        "action": "load_3d_model",
        "data": {
            "query": "H2O"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "model_3d"
    assert data["source"] == "remote_index"
    assert data["model_url"] == "/models/model_uid_abc/scene.gltf"
    assert data["label"] == "Water Molecule H2O"
    assert data["attribution"]["author"] == "Creator display"


def test_api_load_3d_model_missing_credentials() -> None:
    """Tests POST /api/v1/analyze returns MISSING_CREDENTIALS error shape if X-Sketchfab-Token is absent."""
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"} # No X-Sketchfab-Token!
    payload = {
        "action": "load_3d_model",
        "data": {
            "query": "H2O"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "MISSING_CREDENTIALS"
    assert data["action"] == "load_3d_model"
    assert "Nessuna credenziale Sketchfab" in data["message"]


@patch("httpx.Client.get")
def test_api_load_3d_model_not_found(mock_sketchfab_get: MagicMock) -> None:
    """Tests POST /api/v1/analyze returns MODEL_NOT_FOUND error shape on search miss."""
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": []
    }
    mock_sketchfab_get.return_value = mock_search_resp

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-Sketchfab-Token": "test-sketchfab-token"
    }
    payload = {
        "action": "load_3d_model",
        "data": {
            "query": "non_existent_model"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "MODEL_NOT_FOUND"
    assert data["action"] == "load_3d_model"
    assert "Nessun modello 3D trovato" in data["message"]


@patch("httpx.Client.get")
def test_api_load_3d_model_remote_service_error(mock_sketchfab_get: MagicMock) -> None:
    """Tests POST /api/v1/analyze returns REMOTE_SERVICE_ERROR error shape on API/download failure."""
    mock_sketchfab_get.side_effect = httpx.ConnectError("Connection timed out to Sketchfab")

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-Sketchfab-Token": "test-sketchfab-token"
    }
    payload = {
        "action": "load_3d_model",
        "data": {
            "query": "H2O"
        }
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "REMOTE_SERVICE_ERROR"
    assert data["action"] == "load_3d_model"
    assert "Impossibile connettersi a Sketchfab" in data["message"]


@patch("httpx.Client.get")
def test_search_relevance_h2o_bug_resolved(mock_get: MagicMock) -> None:
    """Tests that the h2o bug is resolved by selecting the relevant model and filtering out the irrelevant villa."""
    # 1. Setup mock search response with an irrelevant first match and a relevant second match
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "villa_uid_999",
                "name": "Luxury Modern Villa with Pool",
                "isDownloadable": True,
                "viewerUrl": "https://sketchfab.com/models/villa_uid_999",
                "user": {
                    "username": "architect",
                    "displayName": "Architect Pro"
                },
                "license": {
                    "slug": "by",
                    "fullName": "CC Attribution"
                }
            },
            {
                "uid": "h2o_uid_111",
                "name": "Water Molecule (H2O)",
                "isDownloadable": True,
                "viewerUrl": "https://sketchfab.com/models/h2o_uid_111",
                "user": {
                    "username": "science_lab",
                    "displayName": "Science Lab"
                },
                "license": {
                    "slug": "by",
                    "fullName": "CC Attribution"
                }
            }
        ]
    }

    # 2. Setup mock download link response (for h2o_uid_111)
    mock_download_resp = MagicMock()
    mock_download_resp.status_code = 200
    mock_download_resp.json.return_value = {
        "gltf": {
            "url": "https://s3.amazonaws.com/sketchfab/archives/h2o_gltf.zip",
            "size": 2048,
            "expires": 300
        }
    }

    # 3. Setup mock zip archive response
    mock_archive_resp = MagicMock()
    mock_archive_resp.status_code = 200
    mock_archive_resp.content = create_dummy_zip_bytes()

    # Assign side effects to mock_get
    mock_get.side_effect = [mock_search_resp, mock_download_resp, mock_archive_resp]

    # Run the service for query "H2O"
    metadata = search_and_fetch_3d_model("H2O", "test-sketchfab-token")

    # Assert that the genuinely relevant H2O model was selected, not the villa
    assert metadata["uid"] == "h2o_uid_111"
    assert metadata["title"] == "Water Molecule (H2O)"
    assert metadata["model_url"] == "/models/h2o_uid_111/scene.gltf"

    # Verify folder was extracted and scene.gltf cached for the correct UID
    cached_gltf = os.path.join(CACHE_DIR, "h2o_uid_111", "scene.gltf")
    assert os.path.exists(cached_gltf)
    assert not os.path.exists(os.path.join(CACHE_DIR, "villa_uid_999"))


@patch("httpx.Client.get")
def test_search_relevance_no_matches_raises_error(mock_get: MagicMock) -> None:
    """Tests that if no result matches both the relevance filter and downloadable/CC filters, we raise a ValueError."""
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "villa_uid_999",
                "name": "Luxury Modern Villa with Pool",
                "isDownloadable": True,
                "viewerUrl": "https://sketchfab.com/models/villa_uid_999",
                "user": {
                    "username": "architect",
                    "displayName": "Architect Pro"
                },
                "license": {
                    "slug": "by",
                    "fullName": "CC Attribution"
                }
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    with pytest.raises(ValueError, match="Nessun modello 3D trovato per la ricerca"):
        search_and_fetch_3d_model("H2O", "test-sketchfab-token")


@patch("httpx.Client.get")
def test_search_all_stopwords_query_raises_error(mock_get: MagicMock) -> None:
    """Tests that a query composed entirely of stopwords (like "la il") returns MODEL_NOT_FOUND (ValueError) and doesn't match spuriously."""
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "villa_uid_999",
                "name": "Luxury Modern Villa with Pool",
                "isDownloadable": True,
                "viewerUrl": "https://sketchfab.com/models/villa_uid_999",
                "user": {
                    "username": "architect",
                    "displayName": "Architect Pro"
                },
                "license": {
                    "slug": "by",
                    "fullName": "CC Attribution"
                }
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    # "la il" are both in the stopwords set. Should return MODEL_NOT_FOUND (ValueError)
    with pytest.raises(ValueError, match="Nessun modello 3D trovato per la ricerca"):
        search_and_fetch_3d_model("la il", "test-sketchfab-token")
