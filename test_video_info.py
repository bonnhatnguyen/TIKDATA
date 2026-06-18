import asyncio
import json
from playwright.async_api import async_playwright

async def get_video_info(url, ms_token):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies([
            {"name": "msToken", "value": ms_token, "domain": ".tiktok.com", "path": "/"}
        ])
        page = await context.new_page()
        print("Visiting:", url)
        await page.goto(url, wait_until="domcontentloaded")
        
        # Lấy script chứa data
        try:
            element = await page.query_selector('script#__UNIVERSAL_DATA_FOR_REHYDRATION__')
            if element:
                content = await element.inner_text()
                data = json.loads(content)
                print("Found data keys:", data.keys())
                # Thông tin video thường nằm trong __DEFAULT_SCOPE__ -> webapp.video-detail
                default_scope = data.get('__DEFAULT_SCOPE__', {})
                video_detail = default_scope.get('webapp.video-detail', {})
                item_info = video_detail.get('itemInfo', {}).get('itemStruct', {})
                print("Video Desc:", item_info.get('desc'))
                print("Video ID:", item_info.get('id'))
                print("Play Addr:", item_info.get('video', {}).get('playAddr'))
            else:
                print("Not found script block")
        except Exception as e:
            print("Error:", e)
        await browser.close()

if __name__ == "__main__":
    ms_token = "r2x9AF3dAqUa8qQ8zh0FPKKqk1shci567EZu_eTDErkMNwO13anUMy6iGmh1iq0w7X5HC3J2oLDtxLlIwVdQVD8Ofr5jq0JtXwGPmsngJITVBJ8d2P-0uM7Z9C-l4GmNGnpce4J1ag1-CUk="
    url = "https://www.tiktok.com/@uservollhehehe/video/7647895326988193045"
    asyncio.run(get_video_info(url, ms_token))
