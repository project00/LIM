# Rate Limit Test Audit

## 1. Literal Body of `get_rate_limit()` Callable

Verbatim code from `server/main.py`:
```python
def get_rate_limit(*args, **kwargs) -> str:
    """
    Returns the rate limit dynamically from the environment variable.
    """
    limit_val = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    return f"{limit_val}/minute"
```

The callable successfully reads `RATE_LIMIT_PER_MINUTE` and formats it as a valid slowapi limit string (e.g. `f"{limit_val}/minute"`).

---

## 2. Environment Overrides & Limiter State Reset Fixtures/Hooks

The test suite in `server/tests/test_rate_limit.py` implements the following hooks and functions to reset the limiter's internal state and safely manage the dynamic `RATE_LIMIT_PER_MINUTE` environment override across test functions:

### Verbatim Hooks in `server/tests/test_rate_limit.py`:
```python
def setup_module():
    """Sets up the environment variable and resets the limiter for this test module."""
    global original_rate_limit
    original_rate_limit = os.environ.get("RATE_LIMIT_PER_MINUTE")
    os.environ["RATE_LIMIT_PER_MINUTE"] = "2"
    limiter.reset()


def teardown_module():
    """Restores the environment variable and resets the limiter to avoid affecting other tests."""
    global original_rate_limit
    if original_rate_limit is None:
        if "RATE_LIMIT_PER_MINUTE" in os.environ:
            del os.environ["RATE_LIMIT_PER_MINUTE"]
    else:
        os.environ["RATE_LIMIT_PER_MINUTE"] = original_rate_limit
    limiter.reset()


def setup_function():
    """Resets the rate limiter storage before each test to ensure a clean slate."""
    limiter.reset()
```

---

## 3. Slowapi Limiter State Persistence Between Tests

According to slowapi's architecture, the `Limiter` stores rate-limiting request histories (timestamps of hits) in its **storage** backend (by default, an in-memory dictionary-based storage `MemoryStorage`).

Because this storage is bound to the global `Limiter` instance and the same ASGI `FastAPI` application instance is reused across the entire pytest test session, **slowapi's rate-limiting counters do NOT reset automatically between pytest test functions.**

The request history persists for the whole test session unless explicitly cleared. Therefore, calling `limiter.reset()` (or `setup_function` resetting the storage) is strictly necessary to prevent rate-limiting data from leaking from one test to another and causing intermittent test suite failures.

---

## 4. Explicit, Deterministic Integration Test

Below is the verbatim code for the fully deterministic version of `test_rate_limiting_triggered_on_analyze` inside `server/tests/test_rate_limit.py` that utilizes pytest's `monkeypatch` fixture to safely override `RATE_LIMIT_PER_MINUTE` specifically for this test, resets the limiter at the start, and validates the exact HTTP 200 response structure:

```python
def test_rate_limiting_triggered_on_analyze(monkeypatch) -> None:
    """
    Tests that POST /api/v1/analyze allows requests up to the configured limit,
    and returns HTTP 200 with a RATE_LIMITED payload on the exceeding request.
    """
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    limiter.reset()

    client = TestClient(app)
    headers = {"Authorization": "Bearer test_secret_token"}
    payload = {"action": "concept_map_test", "data": {"topic": "biology"}}

    # First request: Allowed
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("type") != "error"

    # Second request: Allowed
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("type") != "error"

    # Third request: Rate limited
    resp = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "error"
    assert data["code"] == "RATE_LIMITED"
    assert data["action"] == "concept_map_test"
    assert "Rate limit exceeded" in data["message"]
```

---

## 5. Full Test Suite Run & Pass Counts

To verify that all tests pass deterministically and no session pollution occurs, the full test suite was executed from the `server` directory.

### Literal Pytest Command:
```bash
cd server && poetry run pytest
```

### Summary of Pass/Fail Counts:
```
============================== 52 passed in 6.65s ==============================
```
- **Passed:** 52
- **Failed:** 0
- **Total:** 52
