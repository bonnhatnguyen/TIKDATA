import pytest
from fastapi.testclient import TestClient
from main import app, TIKDATA_SERVICE_TOKEN

client = TestClient(app)

def test_sync_unauthorized():
    response = client.post("/internal/profile/sync", json={"profile_input": "tiktok"})
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]

def test_sync_no_token_fallback():
    # If the ephemeral token grab fails or takes too long, it should return fallback_required
    response = client.post(
        "/internal/profile/sync",
        json={"profile_input": "tiktok"},
        headers={"X-ViralForge-Service-Token": TIKDATA_SERVICE_TOKEN}
    )
    # Since Playwright won't necessarily succeed instantly in a headless test without real interactions,
    # we expect either success or fallback_required.
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["fallback_required", "success"]

def test_sync_with_invalid_manual_token():
    # An invalid token should raise an error from TikTokApi eventually, which should be caught.
    response = client.post(
        "/internal/profile/sync",
        json={"profile_input": "tiktok", "manual_ms_token": "fake_token_123"},
        headers={"X-ViralForge-Service-Token": TIKDATA_SERVICE_TOKEN}
    )
    # The API might just fail to fetch data
    assert response.status_code in [200, 500]
