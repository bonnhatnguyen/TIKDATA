from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from TikTokApi import TikTokApi
from playwright.async_api import async_playwright
import asyncio
import os

app = FastAPI()

# Verify service token
TIKDATA_SERVICE_TOKEN = os.getenv("TIKDATA_SERVICE_TOKEN", "dev_secret_token_123")

class SyncProfileRequest(BaseModel):
    profile_input: str
    manual_ms_token: Optional[str] = None

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
    except Exception as e:
        print(f"[TIKDATA] Failed automatic msToken acquisition: {e}")
    return ms_token

@app.post("/internal/profile/sync")
async def sync_profile(
    req: SyncProfileRequest,
    x_viralforge_service_token: str = Header(None)
):
    if x_viralforge_service_token != TIKDATA_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized service token")

    ms_token = req.manual_ms_token
    
    # 1. Acquire token
    if not ms_token:
        ms_token = await acquire_ephemeral_ms_token()
        
    if not ms_token:
        # Fallback required
        return {
            "status": "fallback_required",
            "code": "TIKTOK_BOOKMARK_REQUIRED",
            "message": "Automatic TikTok connection is unavailable. Please use the manual bookmark method."
        }

    # 2. Fetch data
    try:
        async with TikTokApi() as api:
            await api.create_sessions(
                ms_tokens=[ms_token],
                num_sessions=1,
                sleep_after=1,
                browser=os.getenv("TIKTOK_BROWSER", "chromium")
            )
            
            username = req.profile_input
            
            user = api.user(username)
            user_info = await user.info()
            
            if "userInfo" not in user_info:
                raise Exception("Invalid profile data returned from TikTok API")

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
                async for video in user.videos(count=6):
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
            except Exception as ve:
                print(f"[TIKDATA] Could not fetch videos for {username}: {ve}")

            return {
                "status": "success",
                "profile": normalized_profile,
                "videos": videos,
                "syncedAt": str(asyncio.get_event_loop().time()) # Or use standard datetime string from client
            }
            
    except Exception as e:
        print(f"[TIKDATA] Profile sync failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch TikTok data")
    finally:
        # Clear sensitive variables from memory
        ms_token = None
        req.manual_ms_token = None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
