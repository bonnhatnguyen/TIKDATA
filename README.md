# TikTok API Tester Web App

Ứng dụng web để test toàn bộ chức năng của thư viện [davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api).

## Tính năng
- 🔄 Tự động lấy `ms_token` thông qua Playwright
- 📈 Lấy danh sách video Trending
- 👤 Xem Profile người dùng (ảnh, bio, follower, stats)
- 🎬 Xem video của người dùng
- ❤️ Xem video đã thích của người dùng
- 📋 Xem Playlist của người dùng
- 🏷️ Thông tin Hashtag + Video của Hashtag
- 🎵 Thông tin Sound + Video dùng Sound
- 🎬 Thông tin Video theo URL + Bình luận
- 🔍 Tìm kiếm User

## Cài đặt & Chạy

```bash
pip install fastapi uvicorn TikTokApi playwright
python -m playwright install chromium
uvicorn main:create_app_from_env --factory --host 127.0.0.1 --port 8000
```

Mở trình duyệt tại: http://127.0.0.1:8000
