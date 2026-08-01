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
