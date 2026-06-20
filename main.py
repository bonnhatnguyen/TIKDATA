from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, SecretStr
from typing import Optional, List, Dict, Any
from TikTokApi import TikTokApi
from playwright.async_api import async_playwright
import asyncio
import os
import hmac

TIKDATA_ENABLE_DEV_UI = os.getenv("TIKDATA_ENABLE_DEV_UI", "false").lower() == "true"

app = FastAPI(
    docs_url="/docs" if TIKDATA_ENABLE_DEV_UI else None,
    redoc_url="/redoc" if TIKDATA_ENABLE_DEV_UI else None,
    openapi_url="/openapi.json" if TIKDATA_ENABLE_DEV_UI else None,
)

# Verify service token
TIKDATA_SERVICE_TOKEN = os.getenv("VIRALFORGE_SERVICE_TOKEN", "dev_secret_token_123").encode("utf-8")

class ProfileSyncRequest(BaseModel):
    username: str
    manual_ms_token: Optional[SecretStr] = None

async def acquire_ephemeral_ms_token() -> Optional[str]:
    """Attempt to quietly acquire an msToken if one is not provided."""
    ms_token = None
    try:
        async with async_playwright() as p:
            # Must run headless
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                await page.goto("https://www.tiktok.com", wait_until="commit", timeout=15000)
                await asyncio.sleep(3)
                cookies = await context.cookies()
                for cookie in cookies:
                    if cookie["name"] == "msToken":
                        ms_token = cookie["value"]
                        break
            finally:
                await context.close()
                await browser.close()
    except Exception:
        # Do not log raw playwright exceptions that leak proxy details or selectors
        pass
    return ms_token

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
    if not hmac.compare_digest(received_token, TIKDATA_SERVICE_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized service token")

    ms_token = req.manual_ms_token.get_secret_value() if req.manual_ms_token else None
    
    # 1. Acquire token
    if not ms_token:
        ms_token = await acquire_ephemeral_ms_token()
        
    if not ms_token:
        # Fallback required
        return JSONResponse(status_code=200, content={
            "status": "fallback_required",
            "code": "TIKTOK_BOOKMARK_REQUIRED",
            "message": "Automatic TikTok connection is unavailable."
        })

    # 2. Fetch data
    try:
        async with TikTokApi() as api:
            await api.create_sessions(
                ms_tokens=[ms_token],
                num_sessions=1,
                sleep_after=1,
                browser=os.getenv("TIKTOK_BROWSER", "chromium")
            )
            
            username = req.username
            
            user = api.user(username)
            user_info = await user.info()
            
            if "userInfo" not in user_info:
                return JSONResponse(status_code=400, content={
                    "status": "error",
                    "code": "TIKTOK_PROFILE_NOT_FOUND",
                    "message": "The requested TikTok profile could not be found."
                })

            tiktok_user = user_info["userInfo"].get("user", {})
            tiktok_stats = user_info["userInfo"].get("stats", {})

            normalized_profile = {
                "username": tiktok_user.get("uniqueId"),
                "displayName": tiktok_user.get("nickname"),
                "bio": tiktok_user.get("signature"),
                "avatarUrl": tiktok_user.get("avatarMedium") or tiktok_user.get("avatarLarger"),
                "profileUrl": f"https://www.tiktok.com/@{tiktok_user.get('uniqueId')}",
                "verified": tiktok_user.get("verified", False),
                "followerCount": str(tiktok_stats.get("followerCount", 0)),
                "followingCount": str(tiktok_stats.get("followingCount", 0)),
                "likeCount": str(tiktok_stats.get("heartCount", 0)),
                "videoCount": str(tiktok_stats.get("videoCount", 0)),
            }

            videos = []
            try:
                # Fetch 6 latest public videos
                async for video in user.videos(count=int(os.getenv("TIKTOK_PROFILE_VIDEO_COUNT", "6"))):
                    v_dict = video.as_dict
                    v_item = v_dict.get("itemStruct", v_dict)
                    
                    videos.append({
                        "id": v_item.get("id"),
                        "description": v_item.get("desc", ""),
                        "coverUrl": v_item.get("video", {}).get("cover", ""),
                        "webUrl": f"https://www.tiktok.com/@{username}/video/{v_item.get('id')}",
                        "viewCount": str(v_item.get("stats", {}).get("playCount", 0)),
                        "likeCount": str(v_item.get("stats", {}).get("diggCount", 0)),
                        "commentCount": str(v_item.get("stats", {}).get("commentCount", 0)),
                        "shareCount": str(v_item.get("stats", {}).get("shareCount", 0)),
                        "createdAt": str(v_item.get("createTime", ""))
                    })
            except Exception:
                pass # Silently fail video fetch if profile is private/empty but user is valid

            return {
                "status": "success",
                "profile": normalized_profile,
                "videos": videos
            }
            
    except Exception:
        return JSONResponse(status_code=502, content={
            "status": "error",
            "code": "TIKTOK_UPSTREAM_UNAVAILABLE",
            "message": "TikTok is temporarily unavailable."
        })
    finally:
        # Clear sensitive variables from memory
        ms_token = None
        req.manual_ms_token = None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
