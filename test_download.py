import asyncio
import httpx

async def test_download(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.tiktok.com/"
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        print("Status:", resp.status_code)
        print("Length:", len(resp.content))

if __name__ == "__main__":
    play_url = "https://v16-webapp-prime.tiktok.com/video/tos/alisg/tos-alisg-pve-0037c001/oAkefddiAIpQA6FfiFxdYEHANXtjRxgeMgUKLf/?a=1988&bti=ODszNWYuMDE6&&bt=749&ft=4fUEKM3a8Zmo0vYG_a4jVlNb-pWrKsd.&mime_type=video_mp4&rc=OTVmOjY2ZjM3ZDk5ZTtoNEBpM3l5d3U5cnRmOzMzODczNEBgMV8yYC4zNTQxMWFeYjVjYSNqY2pwMmQ0NmVhLS1kMWBzcw%3D%3D&expire=1781914684&l=202606180817416B7E57DEB92FAEA863DB&ply_type=2&policy=2&signature=19df558cba9495d79f9d8bbc15549da1&tk=tt_chain_token&btag=e000b8000"
    asyncio.run(test_download(play_url))
