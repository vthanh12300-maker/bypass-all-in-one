# Link All-in-One

Web mobile tiếng Việt; kiểm tra redirect HTTP thật, tùy chọn SDK API lấy mã. Không phải dịch vụ bypass độc lập toàn bộ nền tảng.

## Deploy qua GitHub + Render
1. Mở https://dashboard.render.com/ và đăng nhập, kết nối GitHub.
2. New > Blueprint, chọn repo này và nhánh main. Cấu hình APP_PASSWORD riêng khi được hỏi. Không commit mật khẩu.
3. Render cấp URL onrender.com sau khi deploy thành công. GitHub Pages không chạy Python. Nếu tạo Web Service thủ công: Python, Free, build `pip install -r requirements.txt`, start `python app.py`, health check /health.

## API Việt Nam tùy chọn
Cần nhà cung cấp tương thích bypass-vuotlink-sdk, base URL thật và API key được cấp. Đặt BYPASS_BASE_URL, BYPASS_API_KEY, APP_PASSWORD trong Render Environment. Không đưa key vào frontend. Resolve đặt free mode và không tự giải CAPTCHA; chế độ lấy mã dùng fetch_code và cần đúng URL trang đích của nhiệm vụ, không nhất thiết là link rút gọn. Việc lấy mã có thể phát sinh phí/hạn mức nhà cung cấp. Hỗ trợ thực tế phụ thuộc registry API, chưa kiểm thử live. SDK: https://pypi.org/project/bypass-vuotlink-sdk/

## Chạy local
`python app.py` rồi mở http://localhost:8080. Không cần SDK nếu chỉ dùng redirect. `python -m unittest discover -v` để chạy unit tests.

## Giới hạn
Không xử lý JS/form/CAPTCHA bằng redirect thường, không khẳng định có mã nếu API chưa trả mã; không thay thế kiểm tra an toàn link. Chặn IP private, cổng tùy ý, kiểm tra từng redirect, pin IP DNS khi kết nối. API bên thứ ba cần tự bảo vệ SSRF, xác thực và hạn mức; chỉ dùng dịch vụ đáng tin. Server đơn giản cho thử nghiệm cá nhân, không phải public production; Render free có sleep/quota. Không lưu URL trên ứng dụng, host/API ngoài có thể ghi log. Không tự gửi mã hoàn thành nhiệm vụ.
