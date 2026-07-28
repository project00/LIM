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
from typing import Any, Dict
from fastapi import FastAPI, Depends, Header, HTTPException, status, Request
from fastapi.responses import JSONResponse
import openai
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Configure logging using standard logging library as per AGENTS.md philosophy
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mock_remote_server")

# Retrieve the shared secret from environment variables
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    # Fail to start immediately with a clear error if it's not configured
    raise RuntimeError("API_KEY environment variable is not configured. Server startup aborted.")

# Import the graph service and validation errors (will also validate LLM_MODEL is configured at startup)
from services.graph_service import generate_concept_map  # noqa: E402
from services.mermaid_validator import InvalidMermaidError  # noqa: E402
from services.stt_service import transcribe_audio  # noqa: E402
from services.translate_service import translate_text  # noqa: E402
from services.quiz_service import generate_quiz  # noqa: E402
from services.quiz_validator import InvalidQuizError  # noqa: E402
from services.model_service import search_and_fetch_3d_model  # noqa: E402
from services.summary_service import generate_summary  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

app = FastAPI(
    title="LIM-AI Copilot Mock Remote Server",
    description="Mock remote server for development verification and API routing with authentication",
    version="1.0.0"
)

def get_rate_limit(*args, **kwargs) -> str:
    """
    Returns the rate limit dynamically from the environment variable.
    """
    limit_val = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    return f"{limit_val}/minute"


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
            detail="Invalid or missing API key"
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("Access denied: Authorization header format must be Bearer <token>.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
        )

    token = parts[1]
    if token != API_KEY:
        logger.warning("Access denied: Provided API key token does not match the configured secret.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key"
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


@app.post("/api/v1/analyze")
@limiter.limit(get_rate_limit)
async def analyze(request: Request, payload: Dict[str, Any], _auth: None = Depends(verify_api_key)) -> Dict[str, Any]:
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

    if action == "concept_map":
        data_obj = payload.get("data") or {}
        topic = data_obj.get("topic")
        if not topic:
            raise HTTPException(
                status_code=400,
                detail="Missing 'topic' field inside 'data' for 'concept_map' action"
            )
        language = data_obj.get("language", "it")

        try:
            # Call the real concept map generator using LiteLLM
            mermaid_code = generate_concept_map(topic, language)

            return {
                "type": "concept_map",
                "source": "remote_llm",
                "mermaid_code": mermaid_code
            }
        except InvalidMermaidError as e:
            logger.warning("Mermaid validation error occurred: %s", e)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "concept_map",
                "message": str(e)
            }

    elif action == "load_3d_model":
        data_obj = payload.get("data") or {}
        query = data_obj.get("query")
        if not query:
            raise HTTPException(
                status_code=400,
                detail="Missing 'query' field inside 'data' for 'load_3d_model' action"
            )

        try:
            model_metadata = search_and_fetch_3d_model(query)
            return {
                "type": "model_3d",
                "source": "remote_index",
                "model_url": model_metadata["model_url"],
                "label": model_metadata["title"],
                "attribution": model_metadata["attribution"]
            }
        except ValueError as e:
            logger.warning("3D model not found for query '%s': %s", query, e)
            return {
                "type": "error",
                "code": "MODEL_NOT_FOUND",
                "action": "load_3d_model",
                "message": str(e)
            }
        except Exception as e:
            logger.error("Sketchfab download or service error: %s", e, exc_info=True)
            return {
                "type": "error",
                "code": "REMOTE_SERVICE_ERROR",
                "action": "load_3d_model",
                "message": f"Errore del servizio Sketchfab o download fallito: {str(e)}"
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
            questions = generate_quiz(lesson_context, num_questions)
            return {
                "type": "quiz",
                "source": "remote_llm",
                "questions": questions
            }
        except InvalidQuizError as e:
            logger.warning("Quiz validation error occurred: %s", e)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "generate_quiz",
                "message": str(e)
            }
        except Exception as e:
            logger.error("LLM provider or unexpected error during quiz generation: %s", e, exc_info=True)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "generate_quiz",
                "message": f"Errore del servizio LLM o output non valido: {str(e)}"
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
                )
            )

        try:
            # Transcribe audio using the STT service
            text = transcribe_audio(
                audio_base64=audio_base64,
                sample_rate=int(sample_rate),
                encoding=str(encoding)
            )

            target_language = data_obj.get("target_language")
            translated_text = None
            if target_language:
                try:
                    translated_text = translate_text(text, str(target_language))
                except openai.OpenAIError as e:
                    logger.error(
                        f"Translation failed due to LLM provider error: {e}",
                        exc_info=True
                    )

            return {
                "type": "transcription",
                "source": "remote_stt",
                "text": text,
                "translated_text": translated_text
            }
        except ValueError as e:
            logger.warning("Validation error during audio transcription: %s", e)
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Internal error during audio transcription: %s", e)
            raise HTTPException(status_code=500, detail="Internal server error during transcription")

    elif action == "generate_summary":
        data_obj = payload.get("data") or {}
        lesson_log = data_obj.get("lesson_log", [])

        if not lesson_log:
            return {
                "type": "error",
                "code": "EMPTY_LESSON_LOG",
                "action": "generate_summary",
                "message": "Nessun contenuto da riassumere ancora"
            }

        try:
            summary_text = generate_summary(lesson_log)
            return {
                "type": "summary",
                "source": "remote_llm",
                "summary": summary_text
            }
        except Exception as e:
            logger.error("LLM provider or unexpected error during summary generation: %s", e, exc_info=True)
            return {
                "type": "error",
                "code": "INVALID_LLM_OUTPUT",
                "action": "generate_summary",
                "message": f"Errore del servizio LLM o output non valido: {str(e)}"
            }

    # Mirror back the payload with augmented metadata for non-implemented remote actions
    response_data = dict(payload)
    response_data["source"] = "mock_server"

    logger.info("Responding with mock payload including source field.")
    return response_data
