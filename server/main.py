"""
Mock Remote Server for LIM-AI Copilot.

Design Note:
    This module implements a minimal, stateless mock remote server. It stands in
    for the real cloud GPU server during initial integration and offline testing phases.
    The goal is to provide reliable, highly performant REST endpoints that mimic the
    production contract. All endpoints use modern FastAPI ASGI structures with strict PEP 484
    type annotations. Logging is handled via standard library logging module. No DI/IoC
    frameworks are used, ensuring grep-ability and maximum simplicity.
"""

import logging
import os
import contextvars
import secrets
import time
from typing import Any, Dict
from fastapi import FastAPI, Depends, Header, HTTPException, status, Request
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
import openai
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Configure logging using standard logging library as per AGENTS.md philosophy
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mock_remote_server")

# Retrieve the shared secret from environment variables
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    # Fail to start immediately with a clear error if it's not configured
    raise RuntimeError(
        "API_KEY environment variable is not configured. Server startup aborted."
    )

# Import the graph service and validation errors (will also validate LLM_MODEL is configured at startup)
from services.graph_service import generate_concept_map  # noqa: E402
from services.mermaid_validator import InvalidMermaidError  # noqa: E402
from services.stt_service import transcribe_audio  # noqa: E402
from services.translate_service import translate_text  # noqa: E402
from services.quiz_service import generate_quiz  # noqa: E402
from services.quiz_validator import InvalidQuizError  # noqa: E402
from services.model_service import search_3d_models, fetch_3d_model_by_uid  # noqa: E402
from services.summary_service import generate_summary  # noqa: E402
from services.ocr_vision_service import generate_ocr_vision  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

current_request = contextvars.ContextVar("current_request", default=None)

# Threat-safe global in-memory state and session dictionaries for Sketchfab OAuth2 (Fase 6A)
OAUTH_STATES: Dict[str, dict] = {}
SESSIONS: Dict[str, dict] = {}

app = FastAPI(
    title="LIM-AI Copilot Mock Remote Server",
    description="Mock remote server for development verification and API routing with authentication",
    version="1.0.0",
)


@app.middleware("http")
async def body_parser_middleware(request: Request, call_next):
    action = None
    if request.method == "POST":
        try:
            body = await request.json()
            action = body.get("action")
        except Exception:
            pass
    request.state.action = action

    token = current_request.set(request)
    try:
        response = await call_next(request)
    finally:
        current_request.reset(token)
    return response


def get_rate_limit(*args, **kwargs) -> str:
    """
    Returns the rate limit dynamically, being action-aware.
    transcribe_audio receives a higher rate limit (default 90).
    """
    req = current_request.get()
    action = getattr(req.state, "action", None) if req else None

    if action == "transcribe_audio":
        limit_val = int(os.getenv("RATE_LIMIT_TRANSCRIBE_PER_MINUTE", "90"))
    else:
        limit_val = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))

    return f"{limit_val}/minute"


def get_bearer_token(request: Request) -> str:
    """
    Key function for rate limiting that extracts the Authorization Bearer token.
    Falls back to remote address if missing or malformed.
    """
    authorization = request.headers.get("Authorization") or request.headers.get(
        "authorization"
    )
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    return get_remote_address(request)


limiter = Limiter(key_func=get_bearer_token)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
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
            "message": f"Rate limit exceeded: maximum {limit_val} requests per minute are allowed.",
        },
    )


# Serve the persistent local 3D models directory under /models
os.makedirs("model_cache", exist_ok=True)
app.mount("/models", StaticFiles(directory="model_cache"), name="models")


async def verify_api_key(authorization: str = Header(default=None)) -> None:
    """
    Dependency to verify that the Authorization header matches Bearer <token>.

    Args:
        authorization: The Authorization header parsed from the request.

    Raises:
        HTTPException: 401 Unauthorized if missing or invalid.
    """
    if not authorization:
        logger.warning("Access denied: Authorization header is missing.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning(
            "Access denied: Authorization header format must be Bearer <token>."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )

    token = parts[1]
    if token != API_KEY:
        logger.warning(
            "Access denied: Provided API key token does not match the configured secret."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


@app.get("/")
async def root() -> Dict[str, str]:
    """
    Root scaffolding endpoint.

    Returns:
        A dictionary with the scaffolding status.
    """
    logger.info("Scaffolding root endpoint queried.")
    return {"status": "scaffolding"}


@app.get("/health")
async def health() -> Dict[str, str]:
    """
    Health check endpoint. Unauthenticated.

    Returns:
        A dictionary with status "ok".
    """
    logger.info("Health check endpoint queried.")
    return {"status": "ok"}


@app.get("/api/v1/sketchfab/login")
async def sketchfab_login(session_id: str) -> RedirectResponse:
    """
    Fase 6A: Sketchfab OAuth2 Login Redirection.
    Generates a cryptographically secure state parameter, maps it to the
    session_id, stores it in OAUTH_STATES with a timestamp, and redirects the
    user to Sketchfab's authorization endpoint.
    """
    if not session_id or not session_id.strip():
        logger.warning("Sketchfab login requested without a valid session_id.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required 'session_id' parameter.",
        )

    client_id = os.getenv("SKETCHFAB_CLIENT_ID")
    redirect_uri = os.getenv("SKETCHFAB_REDIRECT_URI")

    if not client_id or not redirect_uri:
        logger.error("Sketchfab OAuth credentials are not configured on the server.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sketchfab OAuth is not configured on this server.",
        )

    # Generate a cryptographically secure 256-bit state string
    state = secrets.token_urlsafe(32)
    OAUTH_STATES[state] = {"session_id": session_id, "created_at": time.time()}

    logger.info(
        "Sketchfab OAuth login triggered: session_id=%s generated state=%s",
        session_id,
        state,
    )

    auth_url = (
        f"https://sketchfab.com/oauth2/authorize/?"
        f"response_type=code&"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"state={state}"
    )
    return RedirectResponse(
        url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


@app.get("/api/v1/sketchfab/callback", response_class=HTMLResponse)
async def sketchfab_callback(code: str = None, state: str = None) -> HTMLResponse:
    """
    Fase 6A: Sketchfab OAuth2 Callback Endpoint.
    1. Validates dynamic state CSRF parameter.
    2. Securely exchanges authorization code for tokens server-side.
    3. Retrieves and parses user profile to link to the LIM session.
    4. Returns a beautifully-styled, dark-themed success confirmation webpage.
    """
    import httpx
    from fastapi.responses import HTMLResponse

    if not code or not state:
        logger.warning("Callback received with missing code or state parameters.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required OAuth callback parameters (code and state).",
        )

    # 1. State/CSRF validation
    if state not in OAUTH_STATES:
        logger.warning(
            "OAuth callback rejected: invalid or non-existent state: %s", state
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unrecognized state parameter.",
        )

    state_info = OAUTH_STATES.pop(
        state
    )  # Pop strictly to prevent reuse (replay attack prevention)
    session_id = state_info["session_id"]
    created_at = state_info["created_at"]

    # Check temporal expiration limit (10 minutes = 600s)
    if time.time() - created_at > 600.0:
        logger.warning(
            "OAuth callback rejected: state temporal limit exceeded (expired)."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="State parameter expired. Please try logging in again.",
        )

    client_id = os.getenv("SKETCHFAB_CLIENT_ID")
    client_secret = os.getenv("SKETCHFAB_CLIENT_SECRET")
    redirect_uri = os.getenv("SKETCHFAB_REDIRECT_URI")

    if not client_id or not client_secret or not redirect_uri:
        logger.error("Sketchfab OAuth server-side variables are misconfigured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sketchfab OAuth server settings are incomplete.",
        )

    # 2. Server-side POST token exchange
    token_url = "https://sketchfab.com/oauth2/token/"
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }

    logger.info(
        "Exchanging auth code for tokens with Sketchfab (session_id=%s)...", session_id
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if resp.status_code != 200:
                logger.error(
                    "Sketchfab token exchange failed with HTTP %d: %s",
                    resp.status_code,
                    resp.text,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Token exchange failed: Sketchfab API returned status {resp.status_code}.",
                )

            token_data = resp.json()
    except httpx.HTTPError as e:
        logger.error("Network error during Sketchfab token exchange: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Network error during token exchange: {str(e)}",
        )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in") or 2592000  # Default to 30 days

    if not access_token:
        logger.error("Access token missing in Sketchfab response.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve a valid access token.",
        )

    # 3. Retrieve user profile info from /v3/me
    profile_url = "https://api.sketchfab.com/v3/me"
    logger.info("Fetching Sketchfab user profile details...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            p_resp = await client.get(
                profile_url, headers={"Authorization": f"Bearer {access_token}"}
            )

            if p_resp.status_code != 200:
                logger.error(
                    "Failed to fetch Sketchfab profile: HTTP %d: %s",
                    p_resp.status_code,
                    p_resp.text,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to retrieve user profile from Sketchfab.",
                )

            profile_data = p_resp.json()
    except httpx.HTTPError as e:
        logger.error("Network error during profile retrieval: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Network error during profile retrieval: {str(e)}",
        )

    username = profile_data.get("username") or "sketchfab_user"
    display_name = profile_data.get("displayName") or username

    # Save session details securely server-side
    SESSIONS[session_id] = {
        "username": username,
        "displayName": display_name,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + expires_in,
    }

    logger.info(
        "Successfully established authenticated session for user '%s' (%s)",
        username,
        session_id,
    )

    # 4. Return clean, beautifully-styled, dark-themed success confirmation page
    html_content = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Collegamento Sketchfab Completato</title>
        <style>
            body {{
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                text-align: center;
            }}
            .container {{
                background: #242535;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
                border: 1px solid #45475a;
                max-width: 500px;
                width: 90%;
            }}
            h1 {{
                color: #a6e3a1;
                font-size: 24px;
                margin-top: 0;
            }}
            p {{
                font-size: 15px;
                line-height: 1.6;
                color: #bac2de;
            }}
            .user-info {{
                background-color: #11111b;
                padding: 10px;
                border-radius: 6px;
                margin: 20px 0;
                font-weight: bold;
                color: #f9e2af;
                border: 1px solid #313244;
            }}
            button {{
                background-color: #a6e3a1;
                color: #11111b;
                border: none;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
                cursor: pointer;
                transition: background 0.2s, transform 0.1s;
            }}
            button:hover {{
                background-color: #94e2d5;
                transform: scale(1.02);
            }}
            button:active {{
                transform: scale(0.98);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✓ Autenticazione Completata!</h1>
            <p>Il tuo account Sketchfab è stato collegato con successo alla LIM Copilot.</p>
            <div class="user-info">
                Benvenuto, {display_name} (@{username})
            </div>
            <p>Puoi ora chiudere in sicurezza questa finestra e tornare alla lavagna per completare il download del modello 3D.</p>
            <button onclick="window.close()" style="margin-top: 15px;">Chiudi Finestra</button>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)


@app.get("/api/v1/sketchfab/status")
async def sketchfab_status(request: Request) -> Dict[str, Any]:
    """
    Fase 6A: Sketchfab Authentication Status Endpoint.
    Checks if a server-side session is established for the given session_id passed
    via 'X-Sketchfab-Session-Id' header. Does not expose access_tokens or credentials.
    """
    session_id = request.headers.get("X-Sketchfab-Session-Id") or request.headers.get(
        "x-sketchfab-session-id"
    )
    if not session_id:
        return {"authenticated": False, "message": "Missing session ID."}

    session = SESSIONS.get(session_id)
    if not session:
        return {"authenticated": False}

    # Verify if token has expired
    if time.time() > session.get("expires_at", 0):
        # Session expired, clean up server-side
        SESSIONS.pop(session_id, None)
        return {"authenticated": False, "message": "Session expired."}

    return {
        "authenticated": True,
        "username": session.get("username"),
        "displayName": session.get("displayName"),
    }


@app.post("/api/v1/sketchfab/logout")
async def sketchfab_logout(request: Request) -> Dict[str, Any]:
    """
    Fase 6A: Sketchfab Logout Endpoint.
    Clears the server-side OAuth session for the specified session_id.
    """
    session_id = request.headers.get("X-Sketchfab-Session-Id") or request.headers.get(
        "x-sketchfab-session-id"
    )
    if session_id and session_id in SESSIONS:
        SESSIONS.pop(session_id, None)
        logger.info(
            "Successfully logged out session_id=%s from Sketchfab OAuth.", session_id
        )
    return {"status": "logged_out"}


@app.post("/api/v1/analyze")
@limiter.limit(get_rate_limit)
async def analyze(
    request: Request, payload: Dict[str, Any], _auth: None = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Mock analyze endpoint that echoes back request payloads with added metadata.
    Requires dynamic bearer token verification.

    If the requested action is 'concept_map', generates a real concept map
    using LiteLLM.

    Args:
        payload: Arbitrary JSON data representing the requested action.
        _auth: Injected authentication dependency.

    Returns:
        The exact request payload processed or augmented with "source" metadata.
    """
    action = payload.get("action")
    logger.info("Authenticated analyze request with payload action: %s", action)

    # Extract X-LLM-Model / X-LLM-API-Key / X-LLM-API-Base / X-Sketchfab-Token from headers
    x_model = request.headers.get("X-LLM-Model") or request.headers.get("x-llm-model")
    x_key = request.headers.get("X-LLM-API-Key") or request.headers.get("x-llm-api-key")
    x_base = request.headers.get("X-LLM-API-Base") or request.headers.get(
        "x-llm-api-base"
    )
    x_sf_token = request.headers.get("X-Sketchfab-Token") or request.headers.get(
        "x-sketchfab-token"
    )

    # Missing credentials check for concept_map, generate_quiz, generate_summary, ocr_vision
    if (
        action in ("concept_map", "generate_quiz", "generate_summary", "ocr_vision")
        and not x_model
    ):
        return {
            "type": "error",
            "code": "MISSING_CREDENTIALS",
            "action": action,
            "message": "Nessuna credenziale LLM configurata e abilitata. Vai su /setup per aggiungerne una.",
        }

    # Extract credentials from payload if present (keeping compatibility)
    credentials = payload.get("credentials") or {}
    if x_sf_token:
        if "sketchfab" not in credentials:
            credentials["sketchfab"] = {}
        credentials["sketchfab"]["access_token"] = x_sf_token

    if action == "concept_map":
        data_obj = payload.get("data") or {}
        topic = data_obj.get("topic")
        if not topic:
            raise HTTPException(
                status_code=400,
                detail="Missing 'topic' field inside 'data' for 'concept_map' action",
            )
        language = data_obj.get("language", "it")

        try:
            # Call the real concept map generator using LiteLLM with explicit credentials
            mermaid_code = generate_concept_map(topic, language, x_model, x_key, x_base)

            return {
                "type": "concept_map",
                "source": "remote_llm",
                "mermaid_code": mermaid_code,
            }
        except InvalidMermaidError as e:
            logger.warning("Mermaid validation error occurred: %s", e)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "concept_map",
                "message": str(e),
            }

    elif action == "search_3d_models":
        if not x_sf_token:
            return {
                "type": "error",
                "code": "MISSING_CREDENTIALS",
                "action": action,
                "message": "Nessuna credenziale Sketchfab configurata e abilitata. Vai su /setup per aggiungerne una.",
            }

        data_obj = payload.get("data") or {}
        query = data_obj.get("query")
        if not query:
            raise HTTPException(
                status_code=400,
                detail="Missing 'query' field inside 'data' for 'search_3d_models' action",
            )

        try:
            results = search_3d_models(query, x_sf_token)
            return {
                "type": "model_search_results",
                "source": "remote_index",
                "results": results,
            }
        except ValueError as e:
            logger.warning("3D model search not found for query '%s': %s", query, e)
            return {
                "type": "error",
                "code": "MODEL_NOT_FOUND",
                "action": "search_3d_models",
                "message": str(e),
            }
        except Exception as e:
            logger.error("Sketchfab search error: %s", e, exc_info=True)
            return {
                "type": "error",
                "code": "REMOTE_SERVICE_ERROR",
                "action": "search_3d_models",
                "message": f"Errore del servizio Sketchfab: {str(e)}",
            }

    elif action == "select_3d_model":
        if not x_sf_token:
            return {
                "type": "error",
                "code": "MISSING_CREDENTIALS",
                "action": action,
                "message": "Nessuna credenziale Sketchfab configurata e abilitata. Vai su /setup per aggiungerne una.",
            }

        data_obj = payload.get("data") or {}
        uid = data_obj.get("uid")
        if not uid:
            raise HTTPException(
                status_code=400,
                detail="Missing 'uid' field inside 'data' for 'select_3d_model' action",
            )

        try:
            model_metadata = fetch_3d_model_by_uid(uid, x_sf_token)
            return {
                "type": "model_3d",
                "source": "remote_index",
                "model_url": model_metadata["model_url"],
                "label": model_metadata["title"],
                "attribution": model_metadata["attribution"],
            }
        except ValueError as e:
            logger.warning("3D model not found for uid '%s': %s", uid, e)
            return {
                "type": "error",
                "code": "MODEL_NOT_FOUND",
                "action": "select_3d_model",
                "message": str(e),
            }
        except Exception as e:
            logger.error("Sketchfab download or service error: %s", e, exc_info=True)
            return {
                "type": "error",
                "code": "REMOTE_SERVICE_ERROR",
                "action": "select_3d_model",
                "message": f"Errore del servizio Sketchfab o download fallito: {str(e)}",
            }

    elif action == "generate_quiz":
        data_obj = payload.get("data") or {}
        lesson_context = data_obj.get("lesson_context", "")
        num_questions_val = data_obj.get("num_questions")

        # Set fallback/default if not provided or invalid
        num_questions = 4
        if num_questions_val is not None:
            try:
                num_questions = int(num_questions_val)
            except (ValueError, TypeError):
                num_questions = 4

        try:
            questions = generate_quiz(
                lesson_context, num_questions, x_model, x_key, x_base
            )
            return {"type": "quiz", "source": "remote_llm", "questions": questions}
        except InvalidQuizError as e:
            logger.warning("Quiz validation error occurred: %s", e)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "generate_quiz",
                "message": str(e),
            }
        except Exception as e:
            logger.error(
                "LLM provider or unexpected error during quiz generation: %s",
                e,
                exc_info=True,
            )
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "generate_quiz",
                "message": f"Errore del servizio LLM o output non valido: {str(e)}",
            }

    elif action == "transcribe_audio":
        data_obj = payload.get("data") or {}
        audio_base64 = data_obj.get("audio_base64")
        sample_rate = data_obj.get("sample_rate")
        encoding = data_obj.get("encoding")

        if not audio_base64 or sample_rate is None or not encoding:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Missing required fields ('audio_base64', 'sample_rate', 'encoding') "
                    "inside 'data' for 'transcribe_audio' action"
                ),
            )

        try:
            # Transcribe audio using the STT service
            text, lang_prob = transcribe_audio(
                audio_base64=audio_base64,
                sample_rate=int(sample_rate),
                encoding=str(encoding),
            )

            target_language = data_obj.get("target_language")
            translated_text = None
            if target_language:
                # Retrieve custom confidence threshold from environment variables (default 0.5)
                conf_threshold_str = os.getenv(
                    "STT_LANGUAGE_CONFIDENCE_THRESHOLD", "0.5"
                )
                try:
                    conf_threshold = float(conf_threshold_str)
                except ValueError:
                    conf_threshold = 0.5

                if lang_prob < conf_threshold:
                    logger.info(
                        "Traduzione saltata: rilevamento lingua a bassa confidenza (prob=%.2f)",
                        lang_prob,
                    )
                elif x_model:
                    try:
                        translated_text = translate_text(
                            text, str(target_language), x_model, x_key, x_base
                        )
                    except openai.OpenAIError as e:
                        logger.error(
                            f"Translation failed due to LLM provider error: {e}",
                            exc_info=True,
                        )
                else:
                    logger.info("Translation skipped: X-LLM-Model header is missing.")

            return {
                "type": "transcription",
                "source": "remote_stt",
                "text": text,
                "translated_text": translated_text,
            }
        except ValueError as e:
            logger.warning("Validation error during audio transcription: %s", e)
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Internal error during audio transcription: %s", e)
            raise HTTPException(
                status_code=500, detail="Internal server error during transcription"
            )

    elif action == "ocr_vision":
        data_obj = payload.get("data") or {}
        image_base64 = data_obj.get("image_base64")
        if not image_base64:
            raise HTTPException(
                status_code=400,
                detail="Missing 'image_base64' field inside 'data' for 'ocr_vision' action",
            )

        try:
            ocr_text = generate_ocr_vision(image_base64, x_model, x_key, x_base)
            return {"type": "ocr", "source": "remote_vision_llm", "text": ocr_text}
        except Exception as e:
            logger.error("Vision OCR service error: %s", e, exc_info=True)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "ocr_vision",
                "message": f"Errore del servizio LLM o output non valido: {str(e)}",
            }

    elif action == "generate_summary":
        data_obj = payload.get("data") or {}
        lesson_log = data_obj.get("lesson_log", [])

        if not lesson_log:
            return {
                "type": "error",
                "code": "EMPTY_LESSON_LOG",
                "action": "generate_summary",
                "message": "Nessun contenuto da riassumere ancora",
            }

        try:
            summary_text = generate_summary(lesson_log, x_model, x_key, x_base)
            return {"type": "summary", "source": "remote_llm", "summary": summary_text}
        except Exception as e:
            logger.error(
                "LLM provider or unexpected error during summary generation: %s",
                e,
                exc_info=True,
            )
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "generate_summary",
                "message": f"Errore del servizio LLM o output non valido: {str(e)}",
            }

    # Mirror back the payload with augmented metadata for non-implemented remote actions
    response_data = dict(payload)
    response_data["source"] = "mock_server"

    logger.info("Responding with mock payload including source field.")
    return response_data
