from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from TikTokApi import TikTokApi
from playwright.async_api import async_playwright
import re, os, asyncio

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
async def fetch_ms_token():
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
        return {"status": "error", "detail": "Không tìm thấy msToken. TikTok có thể đang chặn request."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/api/video/by_url")
async def get_video_by_url(url: str, ms_token: str = None):
    try:
        video_id = extract_video_id(url)
        if not video_id:
            raise HTTPException(status_code=400, detail="Không thể trích xuất Video ID từ URL. Định dạng đúng: https://www.tiktok.com/@user/video/123456")
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
