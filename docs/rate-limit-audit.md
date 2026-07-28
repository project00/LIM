# Rate Limiting & Reverse Proxy Audit

## 1. POST /api/v1/analyze Route Handler Signature & Decorators

Verbatim code from `server/main.py`:
```python
@app.post("/api/v1/analyze")
@limiter.limit(get_rate_limit)
async def analyze(request: Request, payload: Dict[str, Any], _auth: None = Depends(verify_api_key)) -> Dict[str, Any]:
```

- `@limiter.limit(...) decorator is applied to this route: YES`
- `request: Request parameter present: YES`

---

## 2. Slowapi Per-Route Configurable Limits Documentation Reference

According to slowapi's official documentation (e.g. on [GitHub](https://github.com/laurentS/slowapi)), configurable limits can be achieved by passing a **callable** (such as a function or lambda) directly to the `@limiter.limit` decorator. This callable is evaluated dynamically at runtime on every request. Slowapi requires that any rate-limited route handler accepts a `request: Request` parameter (or `websocket`) so that the limiter can extract the request context and apply key functions correctly.

---

## 3. Test Exercising Real Route Traffic Rate Limiting

Verbatim code of `test_rate_limiting_triggered_on_analyze` inside `server/tests/test_rate_limit.py` which executes real route traffic using FastAPI's `TestClient` to prove that the rate limit triggers dynamically:

```python
def test_rate_limiting_triggered_on_analyze() -> None:
    """
    Tests that POST /api/v1/analyze allows requests up to the configured limit,
    and returns HTTP 200 with a RATE_LIMITED payload on the exceeding request.
    """
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

## 4. HTTPS Server Block inside `nginx/nginx.conf`

Verbatim HTTPS server configuration from `nginx/nginx.conf`:
```nginx
    # HTTPS reverse proxy configuration
    server {
        listen 443 ssl;
        server_name localhost; # Replace with your school's actual domain name at deploy time

        # Placeholder paths for TLS certificate and key.
        # NOTE: These MUST be replaced with real, valid certificates (e.g. via certbot/Let's Encrypt) at deploy time!
        ssl_certificate /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;

        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        location / {
            proxy_pass http://mock-server:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # WebSocket support (for any potential proxying or future upgrades)
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
```

The certificate paths (`/etc/nginx/certs/fullchain.pem` and `/etc/nginx/certs/privkey.pem`) perfectly match the read-only volume mounted in `docker-compose.yml`:
```yaml
      - ./nginx/certs:/etc/nginx/certs:ro
```

---

## 5. Pyproject.toml Dependency Verification

`slowapi` is listed under the dependencies section in `server/pyproject.toml` specifically (and NOT `daemon/pyproject.toml`).

Verbatim dependency line from `server/pyproject.toml`:
```toml
slowapi = "^0.1.10"
```
