import asyncio
import httpx
import json
from bs4 import BeautifulSoup

async def get_video_info_httpx(url, ms_token):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    cookies = {
        "msToken": ms_token
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, cookies=cookies, follow_redirects=True)
        soup = BeautifulSoup(resp.text, "html.parser")
        script = soup.find("script", id="__UNIVERSAL_DATA_FOR_REHYDRATION__")
        if script:
            data = json.loads(script.string)
            default_scope = data.get('__DEFAULT_SCOPE__', {})
            video_detail = default_scope.get('webapp.video-detail', {})
            item_info = video_detail.get('itemInfo', {}).get('itemStruct', {})
            print("Video Desc:", item_info.get('desc'))
            print("Video ID:", item_info.get('id'))
        else:
            print("Not found")

if __name__ == "__main__":
    ms_token = "r2x9AF3dAqUa8qQ8zh0FPKKqk1shci567EZu_eTDErkMNwO13anUMy6iGmh1iq0w7X5HC3J2oLDtxLlIwVdQVD8Ofr5jq0JtXwGPmsngJITVBJ8d2P-0uM7Z9C-l4GmNGnpce4J1ag1-CUk="
    url = "https://www.tiktok.com/@uservollhehehe/video/7647895326988193045"
    asyncio.run(get_video_info_httpx(url, ms_token))
