# Sprint 7 Batch 1 Audit

## 1. Task 27a/27b overlap — dead code check

### Quiz Button lessonLog-to-lesson_context Logic inside `widget/index.html`
```javascript
        function triggerQuiz() {
            if (lessonLog.length === 0) {
                const toast = document.getElementById("toast-banner");
                if (toast) {
                    toast.innerText = "Nessun contenuto da riassumere ancora";
                    toast.style.display = "block";
                    setTimeout(() => { toast.style.display = "none"; }, 5000);
                }
                return;
            }

            if (ws && ws.readyState === WebSocket.OPEN) {
                const contextText = lessonLog.map(entry => entry.content).join("\n");
                ws.send(JSON.stringify({
                    action: "generate_quiz",
                    data: {
                        lesson_context: contextText,
                        num_questions: 4
                    }
                }));
            }
        }
```

Exactly one implementation of this logic exists, no duplicate/leftover version from an earlier draft: YES

---

## 2. Task 28 — Rate limiting

### Slowapi Limiter Registration and custom `key_func` inside `server/main.py`
```python
def get_bearer_token(request: Request) -> str:
    """
    Key function for rate limiting that extracts the Authorization Bearer token.
    Falls back to remote address if missing or malformed.
    """
    authorization = request.headers.get("Authorization") or request.headers.get("authorization")
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    return get_remote_address(request)


limiter = Limiter(key_func=get_bearer_token)
app.state.limiter = limiter
```

### Custom Exception Handler for `RateLimitExceeded` inside `server/main.py`
```python
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom exception handler for rate limits that returns an application error payload
    with HTTP 200, matching the local bridge raise_for_status expectations.
    """
    try:
        payload = await request.json()
        action = payload.get("action", "unknown")
    except Exception:
        action = "unknown"

    limit_val = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    logger.warning("Rate limit exceeded for action: %s", action)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "type": "error",
            "code": "RATE_LIMITED",
            "action": action,
            "message": f"Rate limit exceeded: maximum {limit_val} requests per minute are allowed."
        }
    )
```

Rate-limited response is HTTP 200 with body {'type':'error','code':'RATE_LIMITED',...}: YES

### Reading Rate Limit Value inside `server/main.py`
```python
    limit_val = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
```

Read from env var RATE_LIMIT_PER_MINUTE with a documented default, not hardcoded: YES

### Excluded Endpoint GET `/health` inside `server/main.py`
```python
@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Health check endpoint. Unauthenticated.

    Returns:
        A dictionary with status "ok".
    """
    logger.info("Health check endpoint queried.")
    return {"status": "ok"}
```

GET /health is excluded from rate limiting: YES

---

## 3. Task 29 — Nginx/TLS

### FastAPI `mock-server` service definition in `docker-compose.yml`
```yaml
  mock-server:
    build:
      context: ./server
      dockerfile: Dockerfile
    container_name: lim_ai_mock_server
    # Port 8000 is not exposed directly for security (TLS terminated by Nginx reverse proxy)
    environment:
      - PYTHONUNBUFFERED=1
      - API_KEY=${API_KEY}
      - LLM_MODEL=${LLM_MODEL}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_API_BASE=${LLM_API_BASE}
    restart: unless-stopped
```

No 'ports:' mapping exposing the FastAPI server directly to the host: YES

### `nginx` service definition in `docker-compose.yml`
```yaml
  nginx:
    image: nginx:alpine
    container_name: lim_ai_nginx_proxy
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
    depends_on:
      - mock-server
    restart: unless-stopped
```

### `proxy_pass` inside `nginx/nginx.conf`
```nginx
            proxy_pass http://mock-server:8000;
```

### HTTP->HTTPS Redirect Block inside `nginx/nginx.conf`
```nginx
    # Redirect HTTP traffic to HTTPS
    server {
        listen 80;
        server_name localhost; # Replace with your school's actual domain name at deploy time

        location / {
            return 301 https://$host$request_uri;
        }
    }
```

### Verification of Manual Certificate Requirements inside `docs/deployment.md`
The document `docs/deployment.md` explicitly states:
> `**This step cannot be automated by Jules (the AI assistant) or any pre-packaged script because it requires a real, registered domain name that you own and have DNS control over.**`
