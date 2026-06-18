import asyncio
import httpx

async def test_tikwm(url):
    api_url = f"https://www.tikwm.com/api/?url={url}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(api_url)
        print("Status:", resp.status_code)
        print("Data:", resp.json())

if __name__ == "__main__":
    url = "https://www.tiktok.com/@uservollhehehe/video/7647895326988193045"
    asyncio.run(test_tikwm(url))
