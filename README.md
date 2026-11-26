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

## V2
- Auto mode identifies known platforms, follows HTTP redirects and published HTML meta refresh instructions with the existing public-IP checks.
- Optional read-only FastForward Crowd query (https://fastforwardteam.github.io/serverdocs/). Off by default; sends only domain and path for links without query/fragment. Community results are unverified candidates, not successful code extraction. Does not contribute or retry verification-required responses.
- SDK is still optional and requires authorized API credentials. No external API charges were enabled. The automatic mode does not call paid SDK operations.
- Browser userscripts and unrestricted curl-based third-party scripts are not installed on the server. For 403 or unresolved task links, use the original website or a configured provider.
- Health endpoint includes version 2.0. Deployment build runs regression tests.

## V3
- Automatic resolver reports each engine result and elapsed time; optional free-mode SDK fallback requires explicit opt-in and a configured provider.
- Code extraction is separately gated by ALLOW_CODE_API=1 and explicit per-request consent because costs may apply. Leave it disabled unless authorized.
- Android browser-assisted completion opens the original URL and allows the user to copy the code they receive. No automatic form completion or CAPTCHA solving.
- Optional Playwright adapter: install requirements-browser.txt, set BROWSER_WS_ENDPOINT to a trusted wss Playwright endpoint and BROWSER_EGRESS_ISOLATED=1 only after the operator has configured a separately isolated browser worker with an outbound firewall denying private, loopback, link-local and metadata destinations including after DNS resolution. Use a matching Playwright version. This is disabled by default; the free public Render service does not install or launch Chromium. Navigation only, no automated verification. Route guards are defense in depth, not a substitute for network isolation.
- Session history in memory in the browser only. Clear history or reload to remove. No API key or app password recorded in history.
- Ontops and TopLinks may still return HTTP 403; no claim of working free code extraction without a compatible provider. No paid service is provisioned by this update.

## V4: code-first
The default mode is now Lấy mã xác nhận. It uses the documented fetch_code API with brand detection and optional task destination URL, explicit consent and ALLOW_CODE_API=1. Set BYPASS_BASE_URL, BYPASS_API_KEY and ALLOW_CODE_API in Render only after obtaining authorized provider credentials and accepting any charges. The provider may require the actual task destination rather than the shortened link. No automatic code submission, retries, or fabricated codes. Redirect mode remains separate; a URL never counts as a confirmation code. Without credentials the app reports the missing provider and offers manual completion. Tests mock the provider; live code retrieval remains unverified.
