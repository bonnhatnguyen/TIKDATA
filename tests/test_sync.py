import pytest
import os
from fastapi.testclient import TestClient
from main import app, TIKDATA_SERVICE_TOKEN, ProfileSyncRequest
from pydantic import SecretStr

# Enable DEV UI during tests just so it doesn't crash if tests rely on defaults
os.environ["TIKDATA_ENABLE_DEV_UI"] = "false"

client = TestClient(app)
token_decoded = TIKDATA_SERVICE_TOKEN.decode("utf-8")

def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "tiktok-data-service"}

def test_docs_hidden_in_prod():
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404

def test_legacy_endpoints_unavailable():
    assert client.get("/api/get_ms_token").status_code == 404
    assert client.post("/api/login_and_sync").status_code == 404
    assert client.post("/api/sync_manual").status_code == 404

def test_sync_unauthorized():
    response = client.post("/internal/profile/sync", json={"username": "tiktok"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing service token"

    response = client.post(
        "/internal/profile/sync", 
        json={"username": "tiktok"},
        headers={"X-ViralForge-Service-Token": "wrong_token_here"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized service token"

def test_secret_str_redaction():
    # Prove that SecretStr representation is redacted
    req = ProfileSyncRequest(username="test", manual_ms_token="SECRET_TOKEN_123")
    assert "SECRET_TOKEN_123" not in repr(req)
    assert "SECRET_TOKEN_123" not in req.model_dump_json()

def test_sync_no_token_fallback():
    # Since Playwright won't necessarily succeed instantly, it returns fallback or 502
    response = client.post(
        "/internal/profile/sync",
        json={"username": "tiktok"},
        headers={"X-ViralForge-Service-Token": token_decoded}
    )
    data = response.json()
    assert response.status_code in [200, 502]
    if response.status_code == 200:
        assert data["status"] in ["fallback_required", "success", "error"]

def test_unique_sentinel_token_absence():
    SENTINEL = "UNIQUE_SENTINEL_TOKEN_9999_NEVER_LOGGED"
    response = client.post(
        "/internal/profile/sync",
        json={"username": "tiktok", "manual_ms_token": SENTINEL},
        headers={"X-ViralForge-Service-Token": token_decoded}
    )
    
    # Ensure sentinel doesn't appear in the response body
    body_str = response.text
    assert SENTINEL not in body_str
    
    # Status should be 502 unavailable or 400 not found (because sentinel is invalid token)
    assert response.status_code in [502, 400]
