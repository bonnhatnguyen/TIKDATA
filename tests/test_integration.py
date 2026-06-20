import pytest
import os
import asyncio
from fastapi.testclient import TestClient
from main import create_app, Settings

@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_tiktok_profile_sync():
    # This test hits real TikTok and uses Playwright
    # Require integration explicitly
    assert os.getenv("TIKDATA_INTEGRATION_TESTS") == "1", "Integration tests disabled unless TIKDATA_INTEGRATION_TESTS=1"

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
    
    # We use TestClient, which runs the event loop for the request
    client = TestClient(app)

    response = client.post(
        "/internal/profile/sync",
        json={"username": "tiktok"},
        headers={"X-ViralForge-Service-Token": "test_token_secret"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    if data.get("status") == "fallback_required":
        # Acceptable if TikTok blocks auto-token fetching
        assert data["code"] == "TIKTOK_BOOKMARK_REQUIRED"
    else:
        assert data["status"] == "success"
        assert "profile" in data
        assert data["profile"]["username"] == "tiktok"
        assert isinstance(data["videos"], list)
