# Sketchfab Authentication and Quiz Validator Audit

## 1. get_auth_headers() in server/services/model_service.py
```python
def get_auth_headers() -> dict:
    """Helper to return authenticated authorization headers for Sketchfab API."""
    token = SKETCHFAB_ACCESS_TOKEN.strip()
    if token.startswith("Token ") or token.startswith("Bearer "):
        return {"Authorization": token}
    # Default to Token authorization format
    return {"Authorization": f"Token {token}"}
```

## 2. Sketchfab Developer Documentation
Source URL: https://docs.sketchfab.com/data-api/v3/index.html#!/collections

Direct Quote:
"Some endpoints require users to be authenticated. Users can log in with OAuth2 (preferred), or an API Token. When an endpoint requires authentication, you need to send an extra HTTP header: for OAuth2: Authorization: Bearer {INSERT_OAUTH_ACCESS_TOKEN_HERE}; for API Token: Authorization: Token {INSERT_API_TOKEN_HERE}."

## 3. quiz_validator.py Options Count Check
server/services/quiz_validator.py
```python
        # Options validation
        options = item.get("options")
        if not isinstance(options, list):
            raise InvalidQuizError(f"La domanda all'indice {idx} non ha un'opzione di tipo lista.")

        if len(options) < 2:
            raise InvalidQuizError(
                f"La domanda all'indice {idx} deve avere almeno 2 opzioni (trovate {len(options)})."
            )
```
The check is present in the code.
