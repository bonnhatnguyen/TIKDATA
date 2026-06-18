from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from TikTokApi import TikTokApi
from playwright.async_api import async_playwright
from pydantic import BaseModel
from typing import Optional
import re, os, asyncio, json

# Global state: store the latest synced TikTok session
_synced_session: dict = {}

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

# ─────────────────────────────────────
# Helper: build a session
# ─────────────────────────────────────
async def make_session(api: TikTokApi, ms_token: str | None):
    await api.create_sessions(
        ms_tokens=[ms_token] if ms_token else None,
        num_sessions=1,
        sleep_after=3,
        browser=os.getenv("TIKTOK_BROWSER", "chromium"),
    )

# ─────────────────────────────────────
# Auto-fetch ms_token via Playwright
# ─────────────────────────────────────
@app.get("/api/get_ms_token")
async def fetch_ms_token_quick():
    """Lấy ms_token nhanh không cần login (ẩn danh - có thể bị giới hạn)"""
    try:
        ms_token = None
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto("https://www.tiktok.com", wait_until="commit")
            await asyncio.sleep(3)
            cookies = await context.cookies()
            for cookie in cookies:
                if cookie["name"] == "msToken":
                    ms_token = cookie["value"]
                    break
            await browser.close()
        if ms_token:
            return {"status": "success", "ms_token": ms_token}
        return {"status": "error", "detail": "Không tìm thấy msToken."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/login_and_sync")
async def login_and_sync():
    """
    Mở cửa sổ trình duyệt TikTok thật để người dùng đăng nhập.
    Sau khi đăng nhập thành công:
    - Lấy msToken từ cookies
    - Tự động điều hướng đến /me để phát hiện username của chính họ
    - Trả về { ms_token, tiktok_username, user_info }
    """
    try:
        result = {}
        async with async_playwright() as p:
            # Mở browser CÓ giao diện (headless=False) để người dùng tương tác
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--start-maximized"]
            )
            context = await browser.new_context(no_viewport=True)
            page = await context.new_page()

            # Đến trang đăng nhập
            await page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")

            # Chờ tối đa 3 phút để người dùng đăng nhập
            # Phát hiện đăng nhập thành công khi cookie sid_tt xuất hiện
            print("[TikTok Sync] Waiting for user to login...")
            logged_in = False
            for _ in range(180):  # 180 * 1s = 3 phút
                await asyncio.sleep(1)
                cookies = await context.cookies()
                cookie_names = {c["name"] for c in cookies}
                # sid_tt chỉ xuất hiện khi đã đăng nhập thành công
                if "sid_tt" in cookie_names:
                    logged_in = True
                    print("[TikTok Sync] Login successful!")
                    break

            if not logged_in:
                await browser.close()
                return {"status": "error", "detail": "Hết thời gian chờ (3 phút). Vui lòng thử lại."}

            # Chờ thêm 2 giây để TikTok ghi đầy đủ cookies
            await asyncio.sleep(2)

            # Lấy msToken
            cookies = await context.cookies()
            for c in cookies:
                if c["name"] == "msToken":
                    result["ms_token"] = c["value"]
                if c["name"] == "tt_chain_token":
                    result["tt_chain_token"] = c["value"]

            # Điều hướng đến /me để TikTok redirect về trang cá nhân
            # URL sẽ đổi thành /@username
            await page.goto("https://www.tiktok.com/me", wait_until="domcontentloaded")
            await asyncio.sleep(3)

            final_url = page.url
            print(f"[TikTok Sync] Redirect URL: {final_url}")

            # Trích xuất username từ URL (dạng /@username)
            username_match = re.search(r'tiktok\.com/@([^/?]+)', final_url)
            if username_match:
                result["tiktok_username"] = username_match.group(1)

            # Nếu không lấy được từ URL, thử đọc từ DOM
            if "tiktok_username" not in result:
                try:
                    handle_el = await page.query_selector('[data-e2e="user-page-header-nickname"]')
                    if not handle_el:
                        handle_el = await page.query_selector('[data-e2e="user-subtitle"]')
                    if handle_el:
                        text = await handle_el.inner_text()
                        result["tiktok_username"] = text.replace("@", "").strip()
                except Exception:
                    pass

            await browser.close()

            # Nếu có username, fetch thêm thông tin profile
            if "tiktok_username" in result and "ms_token" in result:
                try:
                    async with TikTokApi() as api:
                        await api.create_sessions(
                            ms_tokens=[result["ms_token"]],
                            num_sessions=1,
                            sleep_after=3
                        )
                        user_data = await api.user(result["tiktok_username"]).info()
                        result["user_info"] = user_data
                except Exception as e:
                    print(f"[TikTok Sync] Failed to fetch profile: {e}")

            # Lưu vào session toàn cục
            global _synced_session
            _synced_session = result

            return {"status": "success", **result}

    except Exception as e:
        return {"status": "error", "detail": str(e)}

class ManualSyncRequest(BaseModel):
    ms_token: str
    username: Optional[str] = None

@app.post("/api/sync_manual")
async def sync_manual(req: ManualSyncRequest):
    """Lưu ms_token thủ công (từ Bookmarklet) và fetch profile."""
    result = {
        "ms_token": req.ms_token,
        "tiktok_username": req.username,
        "is_manual": True
    }
    
    # Nếu có username, lấy thông tin profile để chứng minh token hoạt động
    if req.username:
        try:
            async with TikTokApi() as api:
                await api.create_sessions(ms_tokens=[req.ms_token], num_sessions=1, sleep_after=1)
                user_data = await api.user(req.username).info()
                result["user_info"] = user_data
        except Exception as e:
            print(f"[Manual Sync] Failed to fetch profile: {e}")

    global _synced_session
    _synced_session = result
    return {"status": "success", **result}

@app.get("/api/synced_session")
async def get_synced_session():
    """Trả về session TikTok đã được sync trước đó (không cần gọi lại)"""
    if _synced_session and "ms_token" in _synced_session:
        return {"status": "success", **_synced_session}
    return {"status": "empty", "detail": "Chưa có session. Hãy bấm Đồng bộ TikTok."}


@app.delete("/api/synced_session")
async def clear_synced_session():
    """Xóa session TikTok đã lưu (đăng xuất)"""
    global _synced_session
    _synced_session = {}
    return {"status": "success", "detail": "Đã xóa session."}

# ─────────────────────────────────────
# Trending
# ─────────────────────────────────────
@app.get("/api/trending")
async def get_trending(ms_token: str = None, count: int = 10):
    try:
        videos = []
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            async for video in api.trending.videos(count=count):
                videos.append(video.as_dict)
        return {"status": "success", "data": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────
# User profile, videos, liked, playlists
# ─────────────────────────────────────
@app.get("/api/user/{username}")
async def get_user(username: str, ms_token: str = None):
    try:
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            user = api.user(username)
            data = await user.info()
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{username}/videos")
async def get_user_videos(username: str, count: int = 10, ms_token: str = None):
    try:
        videos = []
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            async for video in api.user(username).videos(count=count):
                videos.append(video.as_dict)
        return {"status": "success", "data": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{username}/liked")
async def get_user_liked(username: str, count: int = 10, ms_token: str = None):
    try:
        videos = []
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            async for video in api.user(username).liked(count=count):
                videos.append(video.as_dict)
        return {"status": "success", "data": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{username}/playlists")
async def get_user_playlists(username: str, ms_token: str = None):
    try:
        playlists = []
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            async for pl in api.user(username).playlists():
                playlists.append(pl.as_dict)
        return {"status": "success", "data": playlists}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────
# Hashtag
# ─────────────────────────────────────
@app.get("/api/hashtag/{tag}")
async def get_hashtag(tag: str, ms_token: str = None):
    try:
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            ht = api.hashtag(name=tag)
            data = await ht.info()
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/hashtag/{tag}/videos")
async def get_hashtag_videos(tag: str, count: int = 10, ms_token: str = None):
    try:
        videos = []
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            ht = api.hashtag(name=tag)
            async for video in ht.videos(count=count):
                videos.append(video.as_dict)
        return {"status": "success", "data": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────
# Sound
# ─────────────────────────────────────
@app.get("/api/sound/{sound_id}")
async def get_sound(sound_id: str, ms_token: str = None):
    try:
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            sound = api.sound(id=sound_id)
            data = await sound.info()
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sound/{sound_id}/videos")
async def get_sound_videos(sound_id: str, count: int = 10, ms_token: str = None):
    try:
        videos = []
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            sound = api.sound(id=sound_id)
            async for video in sound.videos(count=count):
                videos.append(video.as_dict)
        return {"status": "success", "data": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────
# Video by URL (extract video_id from URL)
# ─────────────────────────────────────
def extract_video_id(url: str) -> str | None:
    m = re.search(r'/video/(\d+)', url)
    return m.group(1) if m else None

async def fetch_video_data_via_browser(url: str, ms_token: str = None) -> dict:
    """Sử dụng Playwright duyệt web thực để lấy cục dữ liệu Video hoàn hảo từ thẻ <script>"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        if ms_token:
            await context.add_cookies([{"name": "msToken", "value": ms_token, "domain": ".tiktok.com", "path": "/"}])
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            element = await page.query_selector('script#__UNIVERSAL_DATA_FOR_REHYDRATION__')
            if element:
                content = await element.inner_text()
                data = json.loads(content)
                default_scope = data.get('__DEFAULT_SCOPE__', {})
                video_detail = default_scope.get('webapp.video-detail', {})
                return video_detail.get('itemInfo', {}).get('itemStruct', {})
        except Exception as e:
            print(f"[Video Fetch] Lỗi Playwright: {e}")
        finally:
            await browser.close()
    return None

@app.get("/api/video/by_url")
async def get_video_by_url(url: str, ms_token: str = None):
    try:
        video_id = extract_video_id(url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Không thể trích xuất Video ID từ URL. Định dạng đúng: https://www.tiktok.com/@user/video/123456")
        
        # 1. Dùng Playwright bốc thẳng Data không lo lỗi API
        item_info = await fetch_video_data_via_browser(url, ms_token)
        
        # 2. Lấy link MP4 không bị chặn (bypass 403) từ TikWM
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                tikwm_resp = await client.get(f"https://www.tikwm.com/api/?url={url}", timeout=10)
                tikwm_data = tikwm_resp.json()
                clean_play_url = tikwm_data.get("data", {}).get("play")
                if clean_play_url and item_info and "video" in item_info:
                    item_info["video"]["playAddr"] = clean_play_url
                    item_info["video"]["downloadAddr"] = clean_play_url
        except Exception as e:
            print(f"[TikWM Fetch Error]: {e}")

        if item_info and "id" in item_info:
            return {"status": "success", "data": item_info}
            
        # Fallback về TikTokApi nếu Playwright lỗi (mặc dù ít khi xảy ra)
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            video = api.video(id=video_id)
            data = await video.info()
        return {"status": "success", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/video/by_url/comments")
async def get_video_comments(url: str, count: int = 20, ms_token: str = None):
    try:
        video_id = extract_video_id(url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Không thể trích xuất Video ID từ URL.")
        comments = []
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            video = api.video(id=video_id)
            async for comment in video.comments(count=count):
                comments.append(comment.as_dict)
        return {"status": "success", "data": comments}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────
# Search users
# ─────────────────────────────────────
@app.get("/api/search/users")
async def search_users(q: str, count: int = 10, ms_token: str = None):
    try:
        users = []
        async with TikTokApi() as api:
            await make_session(api, ms_token)
            async for user in api.search.users(q, count=count):
                users.append({
                    "username": getattr(user, "username", ""),
                    "user_id": getattr(user, "user_id", ""),
                    "sec_uid": getattr(user, "sec_uid", ""),
                })
        return {"status": "success", "data": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
