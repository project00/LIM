import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import uuid
from fastapi.testclient import TestClient
from settings_api import router, settings, DaemonSettings, Credential, save_settings
from fastapi import FastAPI

app = FastAPI()
app.include_router(router)
client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_settings(monkeypatch):
    """Resets credentials before each test."""
    original_creds = list(settings.credentials)
    settings.credentials = []
    yield
    settings.credentials = original_creds


def test_credential_creation_and_listing():
    # 1. Initially empty
    resp = client.get("/api/credentials")
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # 2. Add LLM cloud credential
    payload = {
        "name": "My Cloud LLM",
        "type": "llm_cloud",
        "enabled": True,
        "model": "gpt-4o",
        "api_key": "my-secret-key-12345",
        "api_base": "https://api.custom.com"
    }
    resp = client.post("/api/credentials", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"
    new_id = resp.json()["id"]
    assert new_id is not None

    # 3. List and verify masking
    resp = client.get("/api/credentials")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == new_id
    assert data[0]["name"] == "My Cloud LLM"
    assert data[0]["type"] == "llm_cloud"
    assert data[0]["enabled"] is True
    assert data[0]["api_key_masked"] == "••••••2345"


def test_credential_mutual_exclusivity():
    # Add LLM cloud (initially disabled)
    c1 = {
        "name": "Cloud LLM",
        "type": "llm_cloud",
        "enabled": False,
        "model": "gpt-4o",
        "api_key": "secret-cloud-key"
    }
    r1 = client.post("/api/credentials", json=c1)
    id1 = r1.json()["id"]

    # Add LLM Ollama (initially disabled)
    c2 = {
        "name": "Ollama LLM",
        "type": "llm_ollama",
        "enabled": False,
        "model": "llama3",
        "api_base": "http://localhost:11434"
    }
    r2 = client.post("/api/credentials", json=c2)
    id2 = r2.json()["id"]

    # Add Sketchfab (initially disabled)
    c3 = {
        "name": "Sketchfab 1",
        "type": "sketchfab",
        "enabled": False,
        "access_token": "sf-token-1"
    }
    r3 = client.post("/api/credentials", json=c3)
    id3 = r3.json()["id"]

    # Enable LLM cloud via PATCH
    resp = client.patch(f"/api/credentials/{id1}", json={"enabled": True})
    assert resp.status_code == 200

    # Check that only id1 is enabled
    creds = client.get("/api/credentials").json()
    assert next(c for c in creds if c["id"] == id1)["enabled"] is True
    assert next(c for c in creds if c["id"] == id2)["enabled"] is False

    # Enable LLM Ollama via PATCH
    resp = client.patch(f"/api/credentials/{id2}", json={"enabled": True})
    assert resp.status_code == 200

    # Enforces mutual exclusivity: id1 should be disabled now, id2 enabled
    creds = client.get("/api/credentials").json()
    assert next(c for c in creds if c["id"] == id1)["enabled"] is False
    assert next(c for c in creds if c["id"] == id2)["enabled"] is True

    # Enable Sketchfab via PATCH
    resp = client.patch(f"/api/credentials/{id3}", json={"enabled": True})
    assert resp.status_code == 200
    creds = client.get("/api/credentials").json()
    assert next(c for c in creds if c["id"] == id3)["enabled"] is True
    # LLM should remain enabled as it's a different type
    assert next(c for c in creds if c["id"] == id2)["enabled"] is True


def test_credential_deletion():
    payload = {
        "name": "Test Sketchfab",
        "type": "sketchfab",
        "access_token": "token-1234"
    }
    r = client.post("/api/credentials", json=payload)
    cred_id = r.json()["id"]

    # Delete
    resp = client.delete(f"/api/credentials/{cred_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify gone
    creds = client.get("/api/credentials").json()
    assert len(creds) == 0


import json

def test_get_outgoing_headers_llm_cloud():
    from local_bridge import get_outgoing_headers
    settings.credentials = [
        Credential(
            id="llm1",
            name="Cloud 1",
            type="llm_cloud",
            enabled=True,
            model="gpt-4o",
            api_key="key-abc-123",
            api_base="https://custom.com"
        )
    ]

    # concept_map needs LLM
    headers = get_outgoing_headers("concept_map", {})
    assert headers["X-LLM-Model"] == "gpt-4o"
    assert headers["X-LLM-API-Key"] == "key-abc-123"
    assert headers["X-LLM-API-Base"] == "https://custom.com"


def test_get_outgoing_headers_llm_ollama():
    from local_bridge import get_outgoing_headers
    settings.credentials = [
        Credential(
            id="llm2",
            name="Ollama 1",
            type="llm_ollama",
            enabled=True,
            model="ollama/mistral",
            api_base="http://localhost:11434"
        )
    ]

    # generate_quiz needs LLM
    headers = get_outgoing_headers("generate_quiz", {})
    assert headers["X-LLM-Model"] == "ollama/mistral"
    assert headers["X-LLM-API-Base"] == "http://localhost:11434"
    assert "X-LLM-API-Key" not in headers # Ollama should omit the key header entirely


def test_get_outgoing_headers_missing_llm_throws():
    from local_bridge import get_outgoing_headers, MissingCredentialsError
    settings.credentials = [] # no credentials

    with pytest.raises(MissingCredentialsError) as exc_info:
        get_outgoing_headers("concept_map", {})
    assert "Nessuna credenziale LLM" in str(exc_info.value)


def test_get_outgoing_headers_transcribe_audio_translation_optional():
    from local_bridge import get_outgoing_headers, MissingCredentialsError
    settings.credentials = []

    # transcribe_audio with target_language does NOT throw if no LLM credential, just returns empty headers
    headers = get_outgoing_headers("transcribe_audio", {"target_language": "en"})
    assert len(headers) == 0

    # transcribe_audio with target_language and active LLM gets headers
    settings.credentials = [
        Credential(
            id="llm1",
            name="Cloud 1",
            type="llm_cloud",
            enabled=True,
            model="gpt-4o",
            api_key="key-abc-123"
        )
    ]
    headers = get_outgoing_headers("transcribe_audio", {"target_language": "en"})
    assert headers["X-LLM-Model"] == "gpt-4o"
    assert headers["X-LLM-API-Key"] == "key-abc-123"


def test_get_outgoing_headers_sketchfab():
    from local_bridge import get_outgoing_headers, MissingCredentialsError
    settings.credentials = []

    # load_3d_model throws if no Sketchfab credential is enabled
    with pytest.raises(MissingCredentialsError) as exc_info:
        get_outgoing_headers("load_3d_model", {})
    assert "Nessuna credenziale Sketchfab" in str(exc_info.value)

    # Enable Sketchfab
    settings.credentials = [
        Credential(
            id="sf1",
            name="Sketch 1",
            type="sketchfab",
            enabled=True,
            access_token="sf-token-12345"
        )
    ]
    headers = get_outgoing_headers("load_3d_model", {})
    assert headers["X-Sketchfab-Token"] == "sf-token-12345"


def test_websocket_instant_missing_credentials_failure():
    from local_bridge import app as lb_app
    settings.credentials = [] # no credentials
    client_lb = TestClient(lb_app)

    with client_lb.websocket_connect("/ws") as websocket:
        websocket.send_text(json.dumps({
            "action": "concept_map",
            "data": {"topic": "cioccolato"}
        }))
        response = websocket.receive_json()
        assert response["type"] == "error"
        assert response["code"] == "MISSING_CREDENTIALS"
        assert "Nessuna credenziale LLM" in response["message"]
