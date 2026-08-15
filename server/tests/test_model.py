"""
Unit and Integration Tests for Sketchfab 3D Model Service (Phase 4).
"""

import sys
import os
import zipfile
import io
import shutil
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.model_service import (
    search_3d_models,
    fetch_3d_model_by_uid,
    score_relevance,
    CACHE_DIR,
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


# ------------------ Phase 4 Specific Tests (TEST 1 - TEST 10) ------------------


# TEST 1: First page contains at least 8 candidates valid.
@patch("httpx.Client.get")
def test_pagination_test1_enough_candidates_first_page(mock_get: MagicMock) -> None:
    """Tests that search stops after first page and requests max 8 results if first page has >= 8 valid candidates."""
    mock_results = []
    for i in range(10):
        mock_results.append(
            {
                "uid": f"uid_{i}",
                "name": f"Elephant Model {i}",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},  # CC BY
            }
        )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "next": "https://api.sketchfab.com/v3/models?cursor=next_page",
        "results": mock_results,
    }
    mock_get.return_value = mock_resp

    results = search_3d_models("elephant", "test-token")

    assert len(results) == 8  # Limit to MAX_RESULTS
    assert mock_get.call_count == 1  # Only single page fetched!


# TEST 2: First page contains less than 8 candidates valid and "next" exists.
@patch("httpx.Client.get")
def test_pagination_test2_insufficient_first_page_goes_to_second(
    mock_get: MagicMock,
) -> None:
    """Tests that search goes to second page if first page has < 8 valid candidates."""
    mock_page1 = MagicMock()
    mock_page1.status_code = 200
    mock_page1.json.return_value = {
        "next": "https://api.sketchfab.com/v3/models?cursor=page2",
        "results": [
            {
                "uid": "uid_1",
                "name": "Elephant CCBY",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            }
        ],
    }
    mock_page2 = MagicMock()
    mock_page2.status_code = 200
    mock_page2.json.return_value = {
        "next": None,
        "results": [
            {
                "uid": "uid_2",
                "name": "Elephant CC0",
                "isDownloadable": True,
                "license": {"uid": "7c23a1ba438d4306920229c12afcb5f9"},
            }
        ],
    }
    mock_get.side_effect = [mock_page1, mock_page2]

    results = search_3d_models("elephant", "test-token")
    assert len(results) == 2
    assert mock_get.call_count == 2  # Fetched page 1 and page 2


# TEST 3: The second page contains enough candidates.
@patch("httpx.Client.get")
def test_pagination_test3_stops_when_enough_accumulated(mock_get: MagicMock) -> None:
    """Tests that search stops at page 2 if page 1 + page 2 already has >= 8 candidates."""
    mock_page1 = MagicMock()
    mock_page1.status_code = 200
    mock_page1.json.return_value = {
        "next": "https://api.sketchfab.com/v3/models?cursor=page2",
        "results": [
            {
                "uid": f"p1_{i}",
                "name": "Elephant",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            }
            for i in range(4)
        ],
    }
    mock_page2 = MagicMock()
    mock_page2.status_code = 200
    mock_page2.json.return_value = {
        "next": "https://api.sketchfab.com/v3/models?cursor=page3",
        "results": [
            {
                "uid": f"p2_{i}",
                "name": "Elephant",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            }
            for i in range(5)
        ],
    }
    mock_page3 = MagicMock()

    mock_get.side_effect = [mock_page1, mock_page2, mock_page3]

    results = search_3d_models("elephant", "test-token")
    assert len(results) == 8  # exact limit
    assert mock_get.call_count == 2  # Did not request page 3!


# TEST 4: No next page.
@patch("httpx.Client.get")
def test_pagination_test4_no_next_page(mock_get: MagicMock) -> None:
    """Tests correct termination when next page is absent (None)."""
    mock_page1 = MagicMock()
    mock_page1.status_code = 200
    mock_page1.json.return_value = {
        "next": None,
        "results": [
            {
                "uid": "uid_1",
                "name": "Elephant",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            }
        ],
    }
    mock_get.return_value = mock_page1

    results = search_3d_models("elephant", "test-token")
    assert len(results) == 1
    assert mock_get.call_count == 1


# TEST 5: 'next' continues to exist for many pages.
@patch("httpx.Client.get")
def test_pagination_test5_max_search_pages_limit(mock_get: MagicMock) -> None:
    """Tests that pagination does not exceed MAX_SEARCH_PAGES (3)."""
    mock_pages = []
    for i in range(5):
        m = MagicMock()
        m.status_code = 200
        m.json.return_value = {
            "next": f"https://api.sketchfab.com/v3/models?cursor=page{i+2}",
            "results": [
                {
                    "uid": f"uid_{i}",
                    "name": "Elephant",
                    "isDownloadable": True,
                    "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
                }
            ],
        }
        mock_pages.append(m)

    mock_get.side_effect = mock_pages

    results = search_3d_models("elephant", "test-token")
    assert len(results) == 3  # 3 pages, 1 result each
    assert mock_get.call_count == 3  # Strictly bounded to MAX_SEARCH_PAGES = 3!


# TEST 6: Same UID present in multiple pages.
@patch("httpx.Client.get")
def test_pagination_test6_deduplication_by_uid(mock_get: MagicMock) -> None:
    """Tests that candidates with the same UID appearing on different pages are deduplicated."""
    mock_page1 = MagicMock()
    mock_page1.status_code = 200
    mock_page1.json.return_value = {
        "next": "https://api.sketchfab.com/v3/models?cursor=page2",
        "results": [
            {
                "uid": "duplicate_uid",
                "name": "Elephant P1",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            }
        ],
    }
    mock_page2 = MagicMock()
    mock_page2.status_code = 200
    mock_page2.json.return_value = {
        "next": None,
        "results": [
            {
                "uid": "duplicate_uid",
                "name": "Elephant P2",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            }
        ],
    }
    mock_get.side_effect = [mock_page1, mock_page2]

    results = search_3d_models("elephant", "test-token")
    assert len(results) == 1
    assert results[0]["uid"] == "duplicate_uid"
    assert results[0]["name"] == "Elephant P1"  # Kept first occurrence


# TEST 7: Ranking.
@patch("httpx.Client.get")
def test_ranking_test7_prioritizes_query_match_over_unrelated(
    mock_get: MagicMock,
) -> None:
    """Tests that candidates matching the query keyword are prioritized over unrelated ones (Charger)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "next": None,
        "results": [
            {
                "uid": "uid_charger",
                "name": "Charger Model",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            },
            {
                "uid": "uid_elephant_exact",
                "name": "Elephant",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            },
            {
                "uid": "uid_african_elephant",
                "name": "African Elephant",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            },
            {
                "uid": "uid_elephant_model",
                "name": "Elephant Model Design",
                "isDownloadable": True,
                "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
            },
        ],
    }
    mock_get.return_value = mock_resp

    results = search_3d_models("elephant", "test-token")
    assert len(results) == 4

    # Expected order:
    # 1. Exact Match: "Elephant" (score 100)
    # 2. Starts with: "Elephant Model Design" (score 50 + 10 = 60)
    # 3. Contains: "African Elephant" (score 30 + 10 = 40)
    # 4. No keyword match: "Charger Model" (score 0)
    assert results[0]["uid"] == "uid_elephant_exact"
    assert results[1]["uid"] == "uid_elephant_model"
    assert results[2]["uid"] == "uid_african_elephant"
    assert results[3]["uid"] == "uid_charger"


# TEST 8: Query case insensitive.
def test_ranking_test8_case_insensitive() -> None:
    """Verifies score_relevance behaves case-insensitively."""
    score_upper = score_relevance("African Elephant", "ELEPHANT")
    score_lower = score_relevance("African Elephant", "elephant")
    assert score_upper == score_lower
    assert score_upper > 0.0


# TEST 9: Query multi-word.
def test_ranking_test9_multi_word_tokenization() -> None:
    """Verifies relevance scoring with multi-word token overlap."""
    score_full = score_relevance("African Elephant Toy", "african elephant")
    score_half = score_relevance("African Lion Toy", "african elephant")
    # Score for 'African Elephant Toy' should be higher because of higher token overlap
    assert score_full > score_half


# TEST 10: Regression of downloadable=true and license resolver.
@patch("httpx.Client.get")
def test_regression_test10_downloadable_and_license_resolver(
    mock_get: MagicMock,
) -> None:
    """Verifies that downloadable=true is set in params and license resolver maps properly."""
    mock_search_resp = MagicMock()
    mock_search_resp.status_code = 200
    mock_search_resp.json.return_value = {
        "next": None,
        "results": [
            {
                "uid": "elephant_reg_123",
                "name": "Elephant Reg",
                "isDownloadable": True,
                "license": {
                    "uid": "322a749bcfa841b29dff1e8a1bb74b0b",
                    "label": "CC Attribution",
                },
            }
        ],
    }
    mock_get.return_value = mock_search_resp

    results = search_3d_models("elephant", "test-token")
    assert len(results) == 1
    assert results[0]["license_info"]["recognized"] is True
    assert results[0]["license"] == "CC BY"


# ------------------ Preservation of original/caching tests ------------------


@patch("httpx.stream")
@patch("httpx.Client.get")
def test_fetch_3d_model_by_uid_cache_miss_success(
    mock_get: MagicMock, mock_stream: MagicMock
) -> None:
    """Tests download, extraction, and caching logic of fetch_3d_model_by_uid on cache miss."""
    mock_detail_resp = MagicMock()
    mock_detail_resp.status_code = 200
    mock_detail_resp.json.return_value = {
        "uid": "model_uid_123",
        "name": "Water Molecule H2O",
        "viewerUrl": "https://sketchfab.com/models/model_uid_123",
        "user": {"username": "science_creator", "displayName": "Science Creator"},
        "license": {"slug": "by", "fullName": "CC Attribution"},
    }

    mock_download_resp = MagicMock()
    mock_download_resp.status_code = 200
    mock_download_resp.json.return_value = {
        "gltf": {"url": "https://s3.amazonaws.com/sketchfab/archives/gltf.zip"}
    }

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = MagicMock(
        status_code=200, iter_bytes=lambda chunk_size: [create_dummy_zip_bytes()]
    )
    mock_stream.return_value = mock_stream_ctx

    mock_get.side_effect = [mock_detail_resp, mock_download_resp]

    metadata = fetch_3d_model_by_uid("model_uid_123", "test-sketchfab-token")

    assert metadata["uid"] == "model_uid_123"
    assert metadata["title"] == "Water Molecule H2O"
    assert metadata["model_url"] == "/models/model_uid_123/scene.gltf"
    assert metadata["attribution"]["author"] == "Science Creator"

    # Verify folder was extracted and scene.gltf cached for the correct UID
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
            "source_url": "https://sketchfab.com/models/model_uid_123",
        },
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
            "license": "CC BY",
            "is_downloadable": True,
            "model_url": "https://sketchfab.com/models/model_1",
            "license_info": {
                "recognized": True,
                "license": "CC BY",
                "license_url": "http://creativecommons.org/licenses/by/4.0/",
                "attribution_required": True,
            },
        }
    ]

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-Sketchfab-Token": "test-sketchfab-token",
    }
    payload = {"action": "search_3d_models", "data": {"query": "H2O"}}

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
            "source_url": "https://sketchfab.com/models/model_uid_abc",
        },
    }

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-Sketchfab-Token": "test-sketchfab-token",
    }
    payload = {"action": "select_3d_model", "data": {"uid": "model_uid_abc"}}

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "model_3d"
    assert data["source"] == "remote_index"
    assert data["model_url"] == "/models/model_uid_abc/scene.gltf"


@patch("main.fetch_3d_model_by_uid")
def test_api_select_3d_model_with_query_propagation(mock_fetch: MagicMock) -> None:
    """Fase 6B.2: Tests POST /api/v1/analyze passes the search query to fetch_3d_model_by_uid."""
    mock_fetch.return_value = {
        "uid": "model_uid_abc",
        "title": "Selected Model",
        "model_url": "/models/model_uid_abc/scene.gltf",
        "attribution": {
            "author": "Creator display",
            "license": "CC Attribution",
            "source_url": "https://sketchfab.com/models/model_uid_abc",
        },
    }

    client = TestClient(app)
    headers = {
        "Authorization": "Bearer test_secret_token",
        "X-Sketchfab-Token": "test-sketchfab-token",
    }
    payload = {
        "action": "select_3d_model",
        "data": {"uid": "model_uid_abc", "query": "chair"},
    }

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    mock_fetch.assert_called_once_with(
        "model_uid_abc", "test-sketchfab-token", query="chair"
    )
    assert data["label"] == "Selected Model"
    assert data["attribution"]["author"] == "Creator display"


def test_api_search_3d_models_missing_credentials() -> None:
    """Tests POST /api/v1/analyze returns MISSING_CREDENTIALS error if X-Sketchfab-Token is absent on search."""
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {"action": "search_3d_models", "data": {"query": "H2O"}}

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
    payload = {"action": "select_3d_model", "data": {"uid": "model_uid_123"}}

    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200

    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "MISSING_CREDENTIALS"
    assert data["action"] == "select_3d_model"


# ------------------ Fase 6B High-Security Download & ZIP Tests ------------------


def test_fetch_3d_model_unauthenticated() -> None:
    """Fase 6B: Checks that fetch_3d_model_by_uid raises RuntimeError on missing token."""
    with pytest.raises(RuntimeError, match="Sketchfab access token is not configured"):
        fetch_3d_model_by_uid("uid_123", "")


@patch("httpx.Client.get")
def test_fetch_3d_model_non_downloadable(mock_get: MagicMock) -> None:
    """Fase 6B: Mocks a model with isDownloadable=False, verifying it is rejected."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "uid": "uid_not_dl",
        "name": "Non-Downloadable Model",
        "isDownloadable": False,
        "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
    }
    mock_get.return_value = mock_resp

    with pytest.raises(ValueError, match="MODEL_NOT_DOWNLOADABLE"):
        fetch_3d_model_by_uid("uid_not_dl", "test-token")


@patch("httpx.Client.get")
def test_fetch_3d_model_unrecognized_license(mock_get: MagicMock) -> None:
    """Fase 6B: Mocks a model with unrecognized license payload, verifying rejection."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "uid": "uid_bad_lic",
        "name": "Model with Bad License",
        "isDownloadable": True,
        "license": {"uid": "unknown_lic_uid_xyz"},
    }
    mock_get.return_value = mock_resp

    with pytest.raises(ValueError, match="LICENSE_NOT_RECOGNIZED"):
        fetch_3d_model_by_uid("uid_bad_lic", "test-token")


def build_unsafe_zip_bytes(
    filenames_attr_list: list[tuple[str, bytes | None]],
) -> bytes:
    """Helper to compile a custom ZIP archive in-memory with optional binary attributes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zip_ref:
        for fname, external_attr in filenames_attr_list:
            info = zipfile.ZipInfo(fname)
            if external_attr is not None:
                # Set external attributes (e.g. for symlinks)
                # UNIX symlink attributes is 0xA0000000 (represented as integer)
                info.external_attr = int.from_bytes(external_attr, sys.byteorder)
            zip_ref.writestr(info, "evil file payload")
    return buf.getvalue()


@patch("httpx.Client.get")
@patch("httpx.stream")
def test_zip_slip_traversal_attack(mock_stream: MagicMock, mock_get: MagicMock) -> None:
    """Fase 6B: Mocks Zip Slip path traversal and verifies it is rejected and directory cleaned up."""
    # Model details
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "uid_slip_traversal",
        "name": "Traversal Model",
        "isDownloadable": True,
        "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
    }
    mock_get.return_value = mock_detail

    # Download URL response
    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {
        "gltf": {"url": "https://aws.s3/zip_slip_traversal.zip"}
    }

    # Stream S3 ZIP bytes
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = MagicMock(
        status_code=200,
        iter_bytes=lambda chunk_size: [
            build_unsafe_zip_bytes([("../../evil_traversal.txt", None)])
        ],
    )
    mock_stream.return_value = mock_stream_ctx

    with patch("httpx.Client.get", side_effect=[mock_detail, mock_download]):
        with pytest.raises(ValueError, match="UNSAFE_ARCHIVE_PATH"):
            fetch_3d_model_by_uid("uid_slip_traversal", "test-token")

    # Assert cache folder was safely cleaned up and deleted on failure
    assert not os.path.exists(os.path.join(CACHE_DIR, "uid_slip_traversal"))


@patch("httpx.Client.get")
@patch("httpx.stream")
def test_zip_slip_absolute_path_attack(
    mock_stream: MagicMock, mock_get: MagicMock
) -> None:
    """Fase 6B: Mocks Zip Slip absolute path and verifies it is rejected."""
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "uid_slip_abs",
        "name": "Absolute Model",
        "isDownloadable": True,
        "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
    }
    mock_get.return_value = mock_detail

    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {
        "gltf": {"url": "https://aws.s3/zip_slip_abs.zip"}
    }

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = MagicMock(
        status_code=200,
        iter_bytes=lambda chunk_size: [build_unsafe_zip_bytes([("/etc/passwd", None)])],
    )
    mock_stream.return_value = mock_stream_ctx

    with patch("httpx.Client.get", side_effect=[mock_detail, mock_download]):
        with pytest.raises(ValueError, match="UNSAFE_ARCHIVE_PATH"):
            fetch_3d_model_by_uid("uid_slip_abs", "test-token")


@patch("httpx.Client.get")
@patch("httpx.stream")
def test_zip_slip_windows_drive_attack(
    mock_stream: MagicMock, mock_get: MagicMock
) -> None:
    """Fase 6B: Mocks Zip Slip Windows drive letter path and verifies it is rejected."""
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "uid_slip_win",
        "name": "Windows Model",
        "isDownloadable": True,
        "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
    }
    mock_get.return_value = mock_detail

    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {
        "gltf": {"url": "https://aws.s3/zip_slip_win.zip"}
    }

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = MagicMock(
        status_code=200,
        iter_bytes=lambda chunk_size: [
            build_unsafe_zip_bytes([("C:\\Windows\\system.ini", None)])
        ],
    )
    mock_stream.return_value = mock_stream_ctx

    with patch("httpx.Client.get", side_effect=[mock_detail, mock_download]):
        with pytest.raises(ValueError, match="UNSAFE_ARCHIVE_PATH"):
            fetch_3d_model_by_uid("uid_slip_win", "test-token")


@patch("httpx.Client.get")
@patch("httpx.stream")
def test_zip_slip_symlink_attack(mock_stream: MagicMock, mock_get: MagicMock) -> None:
    """Fase 6B: Mocks Zip with symlink entry and verifies it is rejected."""
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "uid_slip_sym",
        "name": "Symlink Model",
        "isDownloadable": True,
        "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
    }
    mock_get.return_value = mock_detail

    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {
        "gltf": {"url": "https://aws.s3/zip_slip_sym.zip"}
    }

    # external_attr for symlink is 0xA0000000 in UNIX (hex) -> 2684354560
    sym_attr = (2684354560).to_bytes(4, sys.byteorder)

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = MagicMock(
        status_code=200,
        iter_bytes=lambda chunk_size: [
            build_unsafe_zip_bytes([("sym_entry", sym_attr)])
        ],
    )
    mock_stream.return_value = mock_stream_ctx

    with patch("httpx.Client.get", side_effect=[mock_detail, mock_download]):
        with pytest.raises(ValueError, match="UNSAFE_ARCHIVE_PATH"):
            fetch_3d_model_by_uid("uid_slip_sym", "test-token")


@patch("httpx.Client.get")
@patch("httpx.stream")
def test_archive_download_limit_exceeded(
    mock_stream: MagicMock, mock_get: MagicMock
) -> None:
    """Fase 6B: Verifies archive exceeding MAX_DOWNLOAD_SIZE (50MB) is aborted during stream."""
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "uid_large_dl",
        "name": "Large Download Model",
        "isDownloadable": True,
        "license": {"uid": "322a749bcfa841b29dff1e8a1bb74b0b"},
    }
    mock_get.return_value = mock_detail

    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {"gltf": {"url": "https://aws.s3/large.zip"}}

    # Return a giga-chunk of bytes to force size violation immediately
    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = MagicMock(
        status_code=200, iter_bytes=lambda chunk_size: [b"x" * (50 * 1024 * 1024 + 1)]
    )
    mock_stream.return_value = mock_stream_ctx

    with patch("httpx.Client.get", side_effect=[mock_detail, mock_download]):
        with pytest.raises(ValueError, match="ARCHIVE_TOO_LARGE"):
            fetch_3d_model_by_uid("uid_large_dl", "test-token")


@patch("httpx.Client.get")
@patch("httpx.stream")
def test_metadata_and_attribution_file_creation(
    mock_stream: MagicMock, mock_get: MagicMock
) -> None:
    """Fase 6B: Verifies that metadata.json, sf_attribution.json, and ATTRIBUTION.txt are properly written on success."""
    mock_detail = MagicMock()
    mock_detail.status_code = 200
    mock_detail.json.return_value = {
        "uid": "uid_success_att",
        "name": "Compliant CC BY Model",
        "isDownloadable": True,
        "viewerUrl": "https://sketchfab.com/models/uid_success_att",
        "user": {"username": "science_prof", "displayName": "Science Professor"},
        "license": {
            "uid": "322a749bcfa841b29dff1e8a1bb74b0b",
            "label": "CC Attribution",
        },
    }
    mock_get.return_value = mock_detail

    mock_download = MagicMock()
    mock_download.status_code = 200
    mock_download.json.return_value = {"gltf": {"url": "https://aws.s3/success.zip"}}

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__.return_value = MagicMock(
        status_code=200,
        iter_bytes=lambda chunk_size: [build_unsafe_zip_bytes([("scene.gltf", None)])],
    )
    mock_stream.return_value = mock_stream_ctx

    with patch("httpx.Client.get", side_effect=[mock_detail, mock_download]):
        fetch_3d_model_by_uid("uid_success_att", "test-token", query="chair")

    # Assert model was extracted successfully
    model_dir = os.path.join(CACHE_DIR, "uid_success_att")
    assert os.path.exists(os.path.join(model_dir, "scene.gltf"))

    # Assert metadata.json was created correctly (Fase 6B.2)
    metadata_path = os.path.join(model_dir, "metadata.json")
    assert os.path.exists(metadata_path)
    with open(metadata_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["source"] == "Sketchfab"
    assert meta["model_uid"] == "uid_success_att"
    assert meta["model_name"] == "Compliant CC BY Model"
    assert meta["model_url"] == "https://sketchfab.com/models/uid_success_att"
    assert meta["downloaded_asset"] == "scene.gltf"
    assert meta["search_query"] == "chair"
    assert meta["author"] == "Science Professor"
    assert meta["license"] == "CC BY"
    assert meta["attribution_required"] is True

    # Assert sf_attribution.json was created correctly
    sf_path = os.path.join(model_dir, "sf_attribution.json")
    assert os.path.exists(sf_path)
    with open(sf_path, "r", encoding="utf-8") as f:
        sf_att = json.load(f)
    assert sf_att["source"] == "Sketchfab"
    assert sf_att["model_uid"] == "uid_success_att"
    assert sf_att["author"] == "Science Professor"
    assert sf_att["license"] == "CC BY"
    assert sf_att["model_url"] == "https://sketchfab.com/models/uid_success_att"

    # Assert ATTRIBUTION.txt was created correctly
    txt_path = os.path.join(model_dir, "ATTRIBUTION.txt")
    assert os.path.exists(txt_path)
    with open(txt_path, "r", encoding="utf-8") as f:
        txt = f.read()
    assert "Model: Compliant CC BY Model" in txt
    assert "Author: Science Professor" in txt
    assert "Source: Sketchfab" in txt
    assert "License: CC BY" in txt
    assert "Attribution required: YES" in txt
