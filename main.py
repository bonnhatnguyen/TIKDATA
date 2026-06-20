import re
import os
import hmac
import asyncio
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, SecretStr, constr, validator, ConfigDict
from dataclasses import dataclass
from typing import Optional
from TikTokApi import TikTokApi
from playwright.async_api import async_playwright

@dataclass
class Settings:
    tikdata_enable_dev_ui: bool = False
    viralforge_service_token: str = ""
    tiktok_auto_token_enabled: bool = True
    tiktok_max_browser_concurrency: int = 2
    tiktok_browser_launch_timeout_ms: int = 15000
    tiktok_navigation_timeout_ms: int = 15000
    tiktok_sync_timeout_ms: int = 30000
    tiktok_profile_video_count: int = 6

    def __post_init__(self):
        if not self.viralforge_service_token or not self.viralforge_service_token.strip():
            raise ValueError("Service token must not be empty or whitespace-only")
        if self.tiktok_max_browser_concurrency < 1 or self.tiktok_max_browser_concurrency > 20:
            raise ValueError("Browser concurrency must be between 1 and 20")
        if self.tiktok_browser_launch_timeout_ms < 5000:
            raise ValueError("Browser launch timeout must be at least 5000ms")
        if self.tiktok_navigation_timeout_ms < 5000:
            raise ValueError("Navigation timeout must be at least 5000ms")
        if self.tiktok_sync_timeout_ms < 5000:
            raise ValueError("Sync timeout must be at least 5000ms")
        if self.tiktok_profile_video_count < 1 or self.tiktok_profile_video_count > 12:
            raise ValueError("Video count must be between 1 and 12")

    @classmethod
    def from_env(cls):
        token_env = os.getenv("VIRALFORGE_SERVICE_TOKEN")
        if not token_env:
            raise RuntimeError("VIRALFORGE_SERVICE_TOKEN environment variable is strictly required.")
        return cls(
            tikdata_enable_dev_ui=os.getenv("TIKDATA_ENABLE_DEV_UI", "false").lower() == "true",
            viralforge_service_token=token_env,
            tiktok_auto_token_enabled=os.getenv("TIKTOK_AUTO_TOKEN_ENABLED", "true").lower() == "true",
            tiktok_max_browser_concurrency=int(os.getenv("TIKTOK_MAX_BROWSER_CONCURRENCY", "2")),
            tiktok_browser_launch_timeout_ms=int(os.getenv("TIKTOK_BROWSER_LAUNCH_TIMEOUT_MS", "15000")),
            tiktok_navigation_timeout_ms=int(os.getenv("TIKTOK_NAVIGATION_TIMEOUT_MS", "15000")),
            tiktok_sync_timeout_ms=int(os.getenv("TIKTOK_SYNC_TIMEOUT_MS", "30000")),
            tiktok_profile_video_count=int(os.getenv("TIKTOK_PROFILE_VIDEO_COUNT", "6")),
        )

class ProfileSyncRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: constr(min_length=1, max_length=24, strip_whitespace=True)
    manual_ms_token: Optional[SecretStr] = None

    @validator('username')
    def validate_username(cls, v):
        if 'http' in v.lower() or 'tiktok.com' in v.lower():
            raise ValueError('Username must not be a URL')
        if v.startswith('@'):
            raise ValueError('Username must not contain @ prefix')
        if not re.match(r'^[a-zA-Z0-9_.]+$', v):
            raise ValueError('Username contains invalid characters')
        return v

def create_app_from_env() -> FastAPI:
    return create_app(Settings.from_env())

def create_app(settings: Settings) -> FastAPI:

    app = FastAPI(
        docs_url="/docs" if settings.tikdata_enable_dev_ui else None,
        redoc_url="/redoc" if settings.tikdata_enable_dev_ui else None,
        openapi_url="/openapi.json" if settings.tikdata_enable_dev_ui else None,
    )

    _service_token = settings.viralforge_service_token.encode("utf-8")
    browser_semaphore = asyncio.Semaphore(settings.tiktok_max_browser_concurrency)

    async def acquire_ephemeral_ms_token() -> Optional[str]:
        if not settings.tiktok_auto_token_enabled:
            return None
            
        ms_token = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, timeout=settings.tiktok_browser_launch_timeout_ms)
                context = await browser.new_context()
                page = await context.new_page()
                try:
                    await page.goto("https://www.tiktok.com", wait_until="commit", timeout=settings.tiktok_navigation_timeout_ms)
                    await asyncio.sleep(2)
                    cookies = await context.cookies()
                    for cookie in cookies:
                        if cookie["name"] == "msToken":
                            ms_token = cookie["value"]
                            break
                finally:
                    await context.close()
                    await browser.close()
        except Exception:
            pass
        return ms_token

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import logging
        import uuid
        req_id = str(uuid.uuid4())
        logging.error(f"[{req_id}] request_path={request.url.path} stable_error_code=INTERNAL_ERROR")
        if isinstance(exc, HTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "code": "INTERNAL_ERROR"}
        )

    @app.get("/healthz")
    async def healthz():
        return {
            "ok": True,
            "service": "tiktok-data-service"
        }

    @app.post("/internal/profile/sync")
    async def sync_profile(
        req: ProfileSyncRequest,
        x_viralforge_service_token: str = Header(None)
    ):
        if not x_viralforge_service_token:
            raise HTTPException(status_code=401, detail="Missing service token")
            
        received_token = x_viralforge_service_token.encode("utf-8")
        if not hmac.compare_digest(received_token, _service_token):
            raise HTTPException(status_code=401, detail="Unauthorized service token")

        ms_token = req.manual_ms_token.get_secret_value() if req.manual_ms_token else None
        
        async def perform_sync():
            nonlocal ms_token
            async with browser_semaphore:
                if not ms_token:
                    ms_token = await acquire_ephemeral_ms_token()
                    
                if not ms_token:
                    return JSONResponse(status_code=200, content={
                        "status": "fallback_required",
                        "code": "TIKTOK_BOOKMARK_REQUIRED",
                        "message": "Automatic TikTok connection is unavailable."
                    })

                async with TikTokApi() as api:
                    await api.create_sessions(
                        ms_tokens=[ms_token],
                        num_sessions=1,
                        sleep_after=1,
                        browser=os.getenv("TIKTOK_BROWSER", "chromium")
                    )
                    
                    user = api.user(req.username)
                    user_info = await user.info()
                    
                    if "userInfo" not in user_info:
                        return JSONResponse(status_code=400, content={
                            "status": "error",
                            "message": "Could not find TikTok profile."
                        })
                        
                    stats = user_info["userInfo"].get("stats", {})
                    user_data = user_info["userInfo"].get("user", {})
                    
                    normalized_profile = {
                        "username": user_data.get("uniqueId", req.username),
                        "displayName": user_data.get("nickname"),
                        "bio": user_data.get("signature"),
                        "avatarUrl": user_data.get("avatarLarger") or user_data.get("avatarMedium") or user_data.get("avatarThumb"),
                        "profileUrl": f"https://www.tiktok.com/@{user_data.get('uniqueId', req.username)}",
                        "isTikTokVerified": bool(user_data.get("verified", False)),
                        "followerCount": str(stats.get("followerCount", 0)),
                        "followingCount": str(stats.get("followingCount", 0)),
                        "likeCount": str(stats.get("heartCount", 0)),
                        "videoCount": str(stats.get("videoCount", 0)),
                    }
                    
                    normalized_videos = []
                    try:
                        videos = []
                        async for video in user.videos(count=settings.tiktok_profile_video_count):
                            videos.append(video.as_dict)
                            if len(videos) >= settings.tiktok_profile_video_count:
                                break
                                
                        for v in videos:
                            v_stats = v.get("stats", {})
                            normalized_videos.append({
                                "id": v.get("id"),
                                "description": v.get("desc", ""),
                                "coverUrl": v.get("video", {}).get("cover", ""),
                                "webUrl": f"https://www.tiktok.com/@{req.username}/video/{v.get('id')}",
                                "viewCount": str(v_stats.get("playCount", 0)),
                                "likeCount": str(v_stats.get("diggCount", 0)),
                                "commentCount": str(v_stats.get("commentCount", 0)),
                                "shareCount": str(v_stats.get("shareCount", 0)),
                                "createdAt": None
                            })
                    except Exception:
                        pass
                        
                    return JSONResponse(status_code=200, content={
                        "status": "success",
                        "profile": normalized_profile,
                        "videos": normalized_videos
                    })

        try:
            return await asyncio.wait_for(perform_sync(), timeout=settings.tiktok_sync_timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Upstream synchronization timeout")

    return app

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:create_app_from_env", host="127.0.0.1", port=port, reload=True, factory=True)
