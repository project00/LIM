"""
Unit and Integration Tests for Sketchfab 3D Model Service.

Design Note:
    This module tests the model search, details retrieval, local glTF caching,
    unzipping, and E2E API routing for search_3d_models and select_3d_model actions.
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
    resolve_license,
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


# ------------------ Phase 2 Specific Tests (Test 1 - Test 8) ------------------

# Test 1 — CC BY
def test_resolve_license_cc_by() -> None:
    """Tests resolution of CC BY license from UID and label."""
    input_data = {
        "uid": "322a749bcfa841b29dff1e8a1bb74b0b",
        "label": "CC Attribution"
    }
    res = resolve_license(input_data)
    assert res["recognized"] is True
    assert res["license"] == "CC BY"
    assert res["attribution_required"] is True
    assert "by/4.0" in res["license_url"]


# Test 2 — CC0
def test_resolve_license_cc0() -> None:
    """Tests resolution of CC0 Public Domain license from CC0 UID."""
    input_data = {
        "uid": "7c23a1ba438d4306920229c12afcb5f9",
        "label": "CC0 Public Domain"
    }
    res = resolve_license(input_data)
    assert res["recognized"] is True
    assert res["license"] == "CC0"
    assert res["attribution_required"] is False
    assert "zero/1.0" in res["license_url"]


# Test 3 — licenza sconosciuta
def test_resolve_license_unknown() -> None:
    """Tests that an unknown license is not recognized as Creative Commons."""
    input_data = {
        "uid": "unknown-uid",
        "label": "Unknown License"
    }
    res = resolve_license(input_data)
    assert res["recognized"] is False
    assert res["license"] is None
    assert res["attribution_required"] is None


# Test 4 — slug presente
def test_resolve_license_slug_present() -> None:
    """Tests that a payload possessing 'slug' continues to be recognized."""
    input_data = {
        "slug": "by-nc-sa",
        "fullName": "Creative Commons Attribution-NonCommercial-ShareAlike"
    }
    res = resolve_license(input_data)
    assert res["recognized"] is True
    assert res["license"] == "CC BY-NC-SA"
    assert res["attribution_required"] is True


# Test 5 & 6 — downloadable and non-downloadable candidates
@patch("httpx.Client.get")
def test_search_3d_models_downloadable_and_non_downloadable(mock_get: MagicMock) -> None:
    """Tests that candidates with 'isDownloadable': true are parsed correctly, while 'isDownloadable': false are excluded."""
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "model_dl_cc",
                "name": "Downloadable Elephant",
                "isDownloadable": True,
                "license": {
                    "uid": "322a749bcfa841b29dff1e8a1bb74b0b",
                    "label": "CC Attribution"
                }
            },
            {
                "uid": "model_non_dl_cc",
                "name": "Non-downloadable Elephant",
                "isDownloadable": False,
                "license": {
                    "uid": "322a749bcfa841b29dff1e8a1bb74b0b",
                    "label": "CC Attribution"
                }
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    results = search_3d_models("ELEPHANT", "test-token")
    assert len(results) == 1
    assert results[0]["uid"] == "model_dl_cc"
    assert results[0]["is_downloadable"] is True


# Test 7 — Search API parameters
@patch("httpx.Client.get")
def test_search_api_parameters_contain_downloadable_filter(mock_get: MagicMock) -> None:
    """Tests that search query URL parameters contain downloadable=true."""
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "model_uid_123",
                "name": "Elephant CC BY",
                "isDownloadable": True,
                "license": {
                    "uid": "322a749bcfa841b29dff1e8a1bb74b0b"
                }
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    search_3d_models("elephant", "test-token")

    _, first_call_kwargs = mock_get.call_args_list[0]
    sent_params = first_call_kwargs.get("params", {})
    assert sent_params.get("q") == "elephant"
    assert sent_params.get("downloadable") == "true"


# Test 8 — regressione del bug (payload reale ELEPHANT)
@patch("httpx.Client.get")
def test_bug_regression_reale_elephant_payload(mock_get: MagicMock) -> None:
    """
    Creates a fixture representing exactly the payload that caused the issue:
    'isDownloadable' is true, and license ommits 'slug' but contains 'uid' and 'label'.
    Verifies that the candidate passes the filter and is successfully recognized.
    """
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "elephant_real_bug_uid",
                "name": "Real African Elephant",
                "isDownloadable": True,
                "license": {
                    "uid": "322a749bcfa841b29dff1e8a1bb74b0b",
                    "label": "CC Attribution"
                    # "slug" IS OMITTED as in the actual raw response
                },
                "thumbnails": {
                    "images": [
                        {"url": "elephant_thumb.jpg", "width": 256}
                    ]
                }
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    results = search_3d_models("elephant", "test-token")
    assert len(results) == 1
    assert results[0]["uid"] == "elephant_real_bug_uid"
    assert results[0]["license"] == "CC BY"
    assert results[0]["is_downloadable"] is True
    assert results[0]["license_info"]["recognized"] is True


# ------------------ search_3d_models tests ------------------

@patch("httpx.Client.get")
def test_search_3d_models_success(mock_get: MagicMock) -> None:
    """Tests that search_3d_models performs search, filters to downloadable+CC and returns candidate dictionaries with thumbnails closest to 256px."""
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
                    "uid": "322a749bcfa841b29dff1e8a1bb74b0b",
                    "fullName": "CC Attribution"
                },
                "thumbnails": {
                    "images": [
                        {"url": "large.jpg", "width": 1024, "height": 576},
                        {"url": "medium.jpg", "width": 256, "height": 144},
                        {"url": "small.jpg", "width": 64, "height": 36}
                    ]
                }
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    results = search_3d_models("H2O", "test-sketchfab-token")

    # Assert correct parameters passed to API search (no downloadable param inside search query per standard)
    _, first_call_kwargs = mock_get.call_args_list[0]
    assert first_call_kwargs.get("params", {}).get("q") == "H2O"
    assert first_call_kwargs.get("params", {}).get("downloadable") == "true"

    assert len(results) == 1
    assert results[0]["uid"] == "model_uid_123"
    assert results[0]["name"] == "Water Molecule H2O"
    assert results[0]["thumbnail_url"] == "medium.jpg" # Closest to 256px
    assert results[0]["author"] == "Science Creator"
    assert results[0]["license"] == "CC BY"


@patch("httpx.Client.get")
def test_search_3d_models_relevance_sorting(mock_get: MagicMock) -> None:
    """Tests relevance-sorting where matching significant word comes first, but non-matching is NOT rejected (reordered lower)."""
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "villa_uid_999",
                "name": "Luxury Modern Villa with Pool",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b", "fullName": "CC Attribution"},
                "thumbnails": {"images": [{"url": "villa.jpg", "width": 256}]}
            },
            {
                "uid": "h2o_uid_111",
                "name": "Water Molecule (H2O)",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b", "fullName": "CC Attribution"},
                "thumbnails": {"images": [{"url": "h2o.jpg", "width": 256}]}
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    results = search_3d_models("H2O", "test-sketchfab-token")

    # We expect 2 results: H2O is relevance-sorted first (matches significant word), then Villa is sorted second.
    assert len(results) == 2
    assert results[0]["uid"] == "h2o_uid_111"
    assert results[1]["uid"] == "villa_uid_999"


@patch("httpx.Client.get")
def test_search_no_results_or_filters_raises_value_error(mock_get: MagicMock) -> None:
    """Tests that if search returns no results or none pass downloadable+CC filters, ValueError is raised."""
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "results": [
            {
                "uid": "non_dl_uid",
                "name": "Non downloadable model",
                "isDownloadable": False,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"}
            },
            {
                "uid": "non_cc_uid",
                "name": "Non CC licensed model",
                "isDownloadable": True,
                "license": {"uid": "commercial-standard-uid"} # No CC
            }
        ]
    }
    mock_get.return_value = mock_search_resp

    with pytest.raises(ValueError, match="Nessun modello 3D trovato"):
        search_3d_models("query", "test-sketchfab-token")


# ------------------ fetch_3d_model_by_uid tests ------------------

@patch("httpx.Client.get")
def test_fetch_3d_model_by_uid_cache_miss_success(mock_get: MagicMock) -> None:
    """Tests download, extraction, and caching logic of fetch_3d_model_by_uid on cache miss."""
    # 1. Setup mock model details API response
    mock_detail_resp = MagicMock()
    mock_detail_resp.status_code = 200
    mock_detail_resp.json.return_value = {
        "uid": "model_uid_123",
        "name": "Water Molecule H2O",
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

    # 2. Setup mock download link response
    mock_download_resp = MagicMock()
    mock_download_resp.status_code = 200
    mock_download_resp.json.return_value = {
        "gltf": {
            "url": "https://s3.amazonaws.com/sketchfab/archives/gltf.zip"
        }
    }

    # 3. Setup mock zip archive response
    mock_archive_resp = MagicMock()
    mock_archive_resp.status_code = 200
    mock_archive_resp.content = create_dummy_zip_bytes()

    mock_get.side_effect = [mock_detail_resp, mock_download_resp, mock_archive_resp]

    metadata = fetch_3d_model_by_uid("model_uid_123", "test-sketchfab-token")

    assert metadata["uid"] == "model_uid_123"
    assert metadata["title"] == "Water Molecule H2O"
    assert metadata["model_url"] == "/models/model_uid_123/scene.gltf"
    assert metadata["attribution"]["author"] == "Science Creator"

    # Verify extracted cache and metadata.json
    assert os.path.exists(os.path.join(CACHE_DIR, "model_uid_123", "scene.gltf"))
    assert os.path.exists(os.path.join(CACHE_DIR, "model_uid_123", "metadata.json"))


@patch("httpx.Client.get")
def test_fetch_3d_model_by_uid_cache_hit_skips_download(mock_get: MagicMock) -> None:
    """Tests that fetch_3d_model_by_uid reads directly from server-side cache and skips all network requests on cache hit."""
    model_dir = os.path.join(CACHE_DIR, "model_uid_123")
    os.makedirs(model_dir, exist_ok=True)
    with open(os.path.join(model_dir, "scene.gltf"), "w") as f:
        f.write("{'info': 'manually cached gltf'}")

    cached_metadata = {
        "uid": "model_uid_123",
        "title": "Cached Water Molecule",
        "model_url": "/models/model_uid_123/scene.gltf",
        "attribution": {
            "author": "Cached Science Creator",
            "license": "CC Attribution",
            "source_url": "https://sketchfab.com/models/model_uid_123"
        }
    }
    with open(os.path.join(model_dir, "metadata.json"), "w") as f:
        import json
        json.dump(cached_metadata, f)

    metadata = fetch_3d_model_by_uid("model_uid_123", "test-sketchfab-token")

    # Assert returned details are exactly as cached
    assert metadata["title"] == "Cached Water Molecule"
    assert metadata["attribution"]["author"] == "Cached Science Creator"

    # Verify no HTTP calls made
    assert mock_get.call_count == 0


# ------------------ End-to-End API Routing Tests ------------------

@patch("main.search_3d_models")
def test_api_search_3d_models_success(mock_search: MagicMock) -> None:
    """Tests POST /api/v1/analyze for action 'search_3d_models' returns list of candidates."""
    mock_search.return_value = [
        {
            "uid": "model_1",
            "name": "Model 1",
            "thumbnail_url": "thumb1.jpg",
            "author": "Author 1",
            "license": "CC BY"
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
            "query": "H2O"
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
