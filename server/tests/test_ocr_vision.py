from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from services.ocr_vision_service import generate_ocr_vision
from main import app

client = TestClient(app)


def test_ocr_vision_service_multimodal_payload():
    """Tests that ocr_vision_service formats the multimodal payload correctly for LiteLLM."""
    with patch("services.ocr_vision_service.litellm.completion") as mock_completion:
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "EXTRACTED TEXT FROM IMAGE"
        mock_completion.return_value = mock_resp

        res = generate_ocr_vision(
            image_base64="abc123base64",
            llm_model="gpt-4o",
            llm_api_key="api-key",
            llm_api_base="https://custom.api/v1",
        )

        assert res == "EXTRACTED TEXT FROM IMAGE"
        assert mock_completion.called
        kwargs = mock_completion.call_args[1]
        assert kwargs["model"] == "gpt-4o"
        assert kwargs["api_key"] == "api-key"
        assert kwargs["api_base"] == "https://custom.api/v1"

        messages = kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert len(messages[0]["content"]) == 2
        assert messages[0]["content"][0]["type"] == "text"
        assert (
            messages[0]["content"][0]["text"]
            == "trascrivi fedelmente il testo scritto in questa immagine, nient'altro"
        )
        assert messages[0]["content"][1]["type"] == "image_url"
        assert (
            messages[0]["content"][1]["image_url"]["url"]
            == "data:image/png;base64,abc123base64"
        )


def test_ocr_vision_analyze_endpoint_success():
    """Tests that /api/v1/analyze handles 'ocr_vision' action successfully with credentials."""
    with patch("main.generate_ocr_vision") as mock_ocr_vision:
        mock_ocr_vision.return_value = "HELLO FROM VISION LLM"

        headers = {
            "Authorization": "Bearer test_secret_token",
            "X-LLM-Model": "gpt-4o",
            "X-LLM-API-Key": "some-key",
        }
        payload = {
            "action": "ocr_vision",
            "data": {"image_base64": "my_image_b64_data"},
        }

        response = client.post("/api/v1/analyze", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "ocr"
        assert data["source"] == "remote_vision_llm"
        assert data["text"] == "HELLO FROM VISION LLM"


def test_ocr_vision_analyze_endpoint_missing_credentials():
    """Tests that /api/v1/analyze returns MISSING_CREDENTIALS for 'ocr_vision' if model is not set."""
    headers = {
        "Authorization": "Bearer test_secret_token",
    }
    payload = {"action": "ocr_vision", "data": {"image_base64": "my_image_b64_data"}}

    response = client.post("/api/v1/analyze", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "error"
    assert data["code"] == "MISSING_CREDENTIALS"
