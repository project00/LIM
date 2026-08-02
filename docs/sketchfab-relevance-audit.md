# Sketchfab Relevance Audit

This document preserves the verbatim code changes made to address the Sketchfab 3D model search relevance bug.

---

## 1. Verbatim Relevance-Filtering Code in `server/services/model_service.py`

Below is the literal `extract_significant_words` function, including the stopword list, how significant terms are extracted from the query, and the exact check against each candidate's name.

```python
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

    # If filtering removed all words, fallback to using all non-stop words
    if not significant:
        significant = [w for w in words if w not in stopwords]
    # If still empty, fallback to the entire word list
    if not significant:
        significant = words

    return significant
```

### Filtering in Search Call

Within `search_and_fetch_3d_model`, the loop checks names against significant words using `any()` as shown below:

```python
    significant_words = extract_significant_words(query)
    logger.info("Significant words for query '%s': %s", query, significant_words)

    # Selection Heuristic: Find first model explicitly marked downloadable, CC-licensed, and matching the name-relevance filter
    selected_model = None
    for model in results:
        # We queried downloadable=true, but verify just in case
        if not model.get("isDownloadable", True):
            continue

        license_data = model.get("license") or {}
        if not is_cc_licensed(license_data):
            continue

        model_name = model.get("name", "").lower()
        if not any(word in model_name for word in significant_words):
            logger.info("Rejecting model '%s' because name does not contain any query significant words: %s", model.get("name"), significant_words)
            continue

        selected_model = model
        break
```

### Analysis of Empty Significant Words Check
If the `significant_words` list is empty (e.g., if the user searches for empty spaces, punctuation, or nothing remains), `any(word in model_name for word in [])` evaluates to `False`. Thus, the loop correctly rejects everything instead of accidentally passing everything.

---

## 2. Fallback Removal Code Verification

The old fallback mechanism (which downloaded the first result `selected_model = results[0]` regardless of license or relevance) has been completely removed. It is replaced strictly by:

```python
    # If no result passes both relevance filter AND downloadable/CC filter, return MODEL_NOT_FOUND
    if not selected_model:
        logger.warning("No Sketchfab search results passed both the downloadable/CC filter and the name relevance filter for query: '%s'", query)
        raise ValueError(f"Nessun modello 3D trovato per la ricerca: '{query}'")
```

There are no other paths that can bypass this. If no model qualifies, the execution raises `ValueError` immediately.

---

## 3. Verbatim "H2O" Bug Scenario Mock Test

This is the exact unit test from `server/tests/test_model.py` that mocks the "h2o" bug (featuring an irrelevant larger villa result matching a coincidental "H2O" tag under the hood, and a relevant H2O molecule result).

```python
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
```

---

## 4. Verbatim `MODEL_NOT_FOUND` Verification Tests

The unit test below ensures that if no result matches both the relevance filter and the downloadable/CC filters, the function raises a `ValueError` with the expected text (which the server API catches and converts to the `MODEL_NOT_FOUND` error response code/shape from `docs/api-contract.md`).

```python
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
```

The server API routing layer catches this `ValueError` and converts it into the exact `MODEL_NOT_FOUND` JSON error shape specified in `docs/api-contract.md`, tested end-to-end here:

```python
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
```
This preserves the exact contract `/api/v1/analyze` status code 200 error response payload shape.
