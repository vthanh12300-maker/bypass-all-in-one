"""Optional normal browser navigation in a separately isolated Playwright worker.
Never launch a browser in the public Render service. The remote worker MUST
enforce its own outbound firewall (deny private/link-local/metadata addresses,
including after DNS resolution). Routing here is defense in depth only.
"""
import os
import time
import threading
from importlib.util import find_spec
from urllib.parse import urlsplit

SLOT = threading.BoundedSemaphore(1)

def configured():
    endpoint = os.environ.get('BROWSER_WS_ENDPOINT', '')
    try:
        return bool(os.environ.get('APP_PASSWORD') and
                    os.environ.get('BROWSER_EGRESS_ISOLATED') == '1' and
                    urlsplit(endpoint).scheme == 'wss' and
                    urlsplit(endpoint).hostname and find_spec('playwright'))
    except (ValueError, ImportError):
        return False

def probe(url, validate):
    if not configured():
        return {'status':'manual','url':url,'message':'Chưa có browser worker cách ly.'}
    if not SLOT.acquire(blocking=False):
        return {'status':'manual','url':url,'message':'Browser worker đang bận.'}
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        validate(url)
        with sync_playwright() as p:
            browser=p.chromium.connect(os.environ['BROWSER_WS_ENDPOINT'],timeout=6000)
            context=None
            try:
                context=browser.new_context(service_workers='block',accept_downloads=False)
                deadline=time.monotonic()+15
                count=0
                def route_request(route):
                    nonlocal count
                    count+=1
                    req=route.request
                    try:
                        if count>90 or time.monotonic()>deadline or req.method not in ('GET','HEAD'):
                            return route.abort()
                        validate(req.url)
                    except Exception:
                        return route.abort()
                    return route.continue_()
                context.route('**/*',route_request)
                context.route_web_socket('**/*',lambda ws: ws.close())
                page=context.new_page()
                page.set_default_timeout(3000)
                response=page.goto(url,wait_until='domcontentloaded',timeout=10000)
                if response and response.status in (401,403,429):
                    return {'status':'manual','url':url,'http_status':response.status,'message':'Trang từ chối truy cập trong trình duyệt. Không tự vượt xác minh.'}
                try:
                    page.wait_for_timeout(1200)
                except PWTimeout:
                    pass
                final=page.url
                validate(final)
                if final!=url:
                    return {'status':'candidate','url':final,'provider':'Playwright','message':'URL quan sát được trong trình duyệt, chưa xác nhận là đích cuối.'}
                return {'status':'manual','url':url,'message':'Trang cần tương tác thủ công hoặc chưa chuyển hướng.'}
            finally:
                if context:
                    context.close()
                browser.close()
    except Exception:
        return {'status':'manual','url':url,'message':'Browser worker không khả dụng hoặc không thể tải trang.'}
    finally:
        SLOT.release()
