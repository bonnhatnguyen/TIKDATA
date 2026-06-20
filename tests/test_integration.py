import pytest
import os
import asyncio
from fastapi.testclient import TestClient
from main import create_app, Settings

@pytest.mark.integration
@pytest.mark.skipif(os.getenv("TIKDATA_INTEGRATION_TESTS") != "1", reason="Integration tests disabled unless TIKDATA_INTEGRATION_TESTS=1")
def test_real_service_smoke():
    settings = Settings(
        tikdata_enable_dev_ui=False,
        viralforge_service_token="test_token_secret",
        tiktok_auto_token_enabled=True,
        tiktok_max_browser_concurrency=1,
        tiktok_browser_launch_timeout_ms=30000,
        tiktok_navigation_timeout_ms=30000,
        tiktok_sync_timeout_ms=60000,
        tiktok_profile_video_count=6
    )
    app = create_app(settings)
    
    client = TestClient(app)
    response = client.post(
        "/internal/profile/sync",
        json={"username": "tiktok"},
        headers={"X-ViralForge-Service-Token": "test_token_secret"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") in ("success", "fallback_required")

@pytest.mark.integration
@pytest.mark.skipif(os.getenv("TIKDATA_INTEGRATION_TESTS") != "1", reason="Integration tests disabled unless TIKDATA_INTEGRATION_TESTS=1")
def test_real_profile_sync_success():
    settings = Settings(
        tikdata_enable_dev_ui=False,
        viralforge_service_token="test_token_secret",
        tiktok_auto_token_enabled=True,
        tiktok_max_browser_concurrency=1,
        tiktok_browser_launch_timeout_ms=30000,
        tiktok_navigation_timeout_ms=30000,
        tiktok_sync_timeout_ms=60000,
        tiktok_profile_video_count=6
    )
    app = create_app(settings)
    
    client = TestClient(app)
    response = client.post(
        "/internal/profile/sync",
        json={"username": "tiktok"},
        headers={"X-ViralForge-Service-Token": "test_token_secret"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    if data.get("status") == "fallback_required":
        pytest.skip("TikTok blocked auto-token, skipping success test.")
        
    assert data["status"] == "success"
    assert "profile" in data
    assert data["profile"]["username"] == "tiktok"
    assert isinstance(data["videos"], list)
