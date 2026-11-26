import os, json, socket, ssl, http.client, ipaddress, hmac, threading, time
from urllib.parse import urlsplit, urljoin, urlunsplit, urlencode
from html.parser import HTMLParser
import re
from collections import deque
import browser_probe
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
BRANDS = {'ontops':'Ontops','ontops-dr':'Ontops DR','link4m':'Link4M','funlink':'FunLink','toplinks':'TopLinks','gtraffic':'GTraffic','gtraffic-dr':'GTraffic DR','layma':'LayMa'}
VERSION = '5.0'
SLOTS = threading.BoundedSemaphore(2)
PUBLIC_CALLS=deque()
PUBLIC_LOCK=threading.Lock()
def public_allowed():
    now=time.monotonic()
    with PUBLIC_LOCK:
        while PUBLIC_CALLS and now-PUBLIC_CALLS[0]>=60: PUBLIC_CALLS.popleft()
        if len(PUBLIC_CALLS)>=20: return False
        PUBLIC_CALLS.append(now)
        return True
DOMAIN_BRANDS = {'toplinks.io':'TopLinks','ontops.link':'Ontops','link4m.com':'Link4M','funlink.io':'FunLink','yeumoney.com':'YeuMoney','yeulink.com':'YeuLink','synurl.com':'SynURL','linktot.net':'LinkTot','gtraffic.io':'GTraffic','layma.net':'LayMa','linkvertise.com':'Linkvertise','lootlabs.gg':'LootLabs','loot-link.com':'LootLabs','work.ink':'Work.ink','adf.ly':'AdFly'}
def platform(url):
    _,host=parse_url(url)
    return next((name for domain,name in DOMAIN_BRANDS.items() if host==domain or host.endswith('.'+domain)),host)

PASSWORD = os.environ.get('PROVIDER_PASSWORD','')
API_URL = os.environ.get('BYPASS_BASE_URL','')
API_KEY = os.environ.get('BYPASS_API_KEY','')
ALLOW_CODE = os.environ.get('ALLOW_CODE_API','0')=='1'
def detect_code_brand(url):
    name=platform(url).lower()
    return next((key for key,label in BRANDS.items() if label.lower()==name),None)

def api_ready():
    # Public mode never spends the owner's provider balance without a separate gate.
    return bool(API_URL and API_KEY and PASSWORD)
def capability():
    return {'version':VERSION,'api':api_ready(),'code':api_ready() and ALLOW_CODE,
            'brands':BRANDS,'locked':False,'provider_locked':bool(PASSWORD),'crowd':True,'manual_browser':True,'code_brands':{domain:detect_code_brand('https://'+domain) for domain in DOMAIN_BRANDS},'browser':browser_probe.configured()}


class LinkError(Exception): pass

def parse_url(url):
    if not isinstance(url,str) or len(url)>4096 or any(ord(c)<33 or ord(c)==127 for c in url):
        raise LinkError('Link không hợp lệ.')
    try:
        u=urlsplit(url)
        if u.scheme not in ('http','https') or not u.hostname or u.username is not None or u.password is not None or '\\' in url:
            raise ValueError()
        if u.port not in (None, 443 if u.scheme=='https' else 80): raise ValueError()
        host=u.hostname.rstrip('.').encode('idna').decode('ascii')
        if not host or '.' not in host or ':' in host: raise ValueError()
        return u,host
    except (ValueError,UnicodeError): raise LinkError('Chỉ chấp nhận URL HTTP/HTTPS công khai, cổng mặc định.')

def public_ip(host,port):
    records=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    addresses=list(dict.fromkeys(r[4][0] for r in records))
    if not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast for a in addresses):
        raise LinkError('Địa chỉ nội bộ hoặc không công khai bị chặn.')
    return addresses[0]

class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self,host,ip,port,timeout):
        super().__init__(host,port,timeout=timeout); self.ip=ip
    def connect(self): self.sock=socket.create_connection((self.ip,self.port),self.timeout)

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip,port,timeout):
        super().__init__(host,port,timeout=timeout,context=ssl.create_default_context()); self.ip=ip
    def connect(self):
        raw=socket.create_connection((self.ip,self.port),self.timeout)
        try: self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
        except Exception: raw.close(); raise

class RefreshParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.destination=None
    def handle_starttag(self,tag,attrs):
        if tag!='meta' or self.destination: return
        attrs=dict(attrs)
        if (attrs.get('http-equiv') or '').strip().lower()!='refresh': return
        self.destination=refresh_target(attrs.get('content') or '')
def refresh_target(value):
    if not value: return None
    match=re.match(r"""^\s*\d+(?:\.\d+)?\s*;\s*url\s*=\s*(.+?)\s*$""",value,re.I)
    return match.group(1).strip().strip('"\'') if match else None

def response_headers(url,timeout):
    u,host=parse_url(url); port=443 if u.scheme=='https' else 80
    ip=public_ip(host,port)
    cls=PinnedHTTPS if u.scheme=='https' else PinnedHTTP
    conn=cls(host,ip,port,timeout)
    target=urlunsplit(('','',u.path or '/',u.query,''))
    try:
        conn.request('GET',target,headers={'User-Agent':'LinkInspector/1.0','Accept':'text/html,*/*;q=0.1','Connection':'close'})
        res=conn.getresponse()
        location=res.getheader('Location')
        if 200<=res.status<300:
            # Only follow explicitly published refresh instructions, never arbitrary script.
            location=refresh_target(res.getheader('Refresh'))
            if not location and 'text/html' in (res.getheader('Content-Type') or '').lower():
                parser=RefreshParser()
                parser.feed(res.read(65536).decode('utf-8',errors='replace'))
                location=parser.destination
            if location: return 302,location
        return res.status,location
    finally: conn.close()

def resolve_redirect(url):
    chain=[]; seen=set(); deadline=time.monotonic()+20
    for _ in range(8):
        parse_url(url)
        if url in seen: raise LinkError('Phát hiện vòng lặp chuyển hướng.')
        if time.monotonic()>=deadline: raise LinkError('Hết thời gian xử lý.')
        seen.add(url); chain.append(url)
        status,location=response_headers(url,min(5,max(1,deadline-time.monotonic())))
        if status in (301,302,303,307,308) and location:
            url=urljoin(url,location); continue
        if len(chain)>1 and 200<=status<300:
            return {'status':'resolved','url':url,'chain':chain,'message':'Đã tìm được đích chuyển hướng HTTP. Chưa xác minh nội dung trang đích.'}
        return {'status':'manual','url':url,'chain':chain,'http_status':status,'message':('Máy chủ đích từ chối truy cập (HTTP '+str(status)+'). Cần mở link gốc trên trình duyệt hoặc API được cấu hình.' if status in (401,403,429) else f'HTTP {status}: chưa xác nhận được đích cuối. Có thể cần thao tác trên trang hoặc API riêng.')}
    return {'status':'manual','url':url,'chain':chain,'message':'Đã đạt giới hạn chuyển hướng; chưa xác nhận đích cuối.'}

def crowd_lookup(url):
    u,host=parse_url(url)
    # Do not send private query parameters, credentials or fragments to a shared service.
    if u.query or u.fragment or not u.path.strip('/'): return None
    public_ip(host,443 if u.scheme=='https' else 80)
    server='crowd.fastforward.team'
    conn=PinnedHTTPS(server,public_ip(server,443),443,7)
    try:
        body=urlencode({'domain':host,'path':u.path.lstrip('/')})
        conn.request('POST','/crowd/query_v1',body=body,headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'text/plain','Connection':'close','User-Agent':'LinkInspector/2.0'})
        res=conn.getresponse()
        # 201 requires user verification; respect that instead of retrying.
        if res.status!=200: return None
        target=res.read(4097).decode('utf-8').strip()
        if not target or len(target)>4096: return None
        if '://' not in target: target='https://'+target
        t,h=parse_url(target)
        public_ip(h,443 if t.scheme=='https' else 80)
        if target==url: return None
        return {'status':'candidate','url':target,'provider':'FastForward Crowd','message':'Đích do cộng đồng cung cấp, chưa xác minh. Kiểm tra trước khi mở.'}
    finally: conn.close()

def resolve_auto(url,share=False,provider=False):
    started=time.monotonic()
    trace=[]
    result=resolve_redirect(url)
    result['platform']=platform(url)
    trace.append({'engine':'HTTP / HTML','status':result['status'],'http_status':result.get('http_status')})
    if result['status']!='resolved' and share:
        try:
            candidate=crowd_lookup(url)
            trace.append({'engine':'FastForward','status':'candidate' if candidate else 'not_found'})
            if candidate:
                candidate['platform']=result['platform']
                result=candidate
            else:
                result['message']+=' Không có đích tham khảo từ cộng đồng.'
        except (OSError,ValueError,LinkError,http.client.HTTPException):
            trace.append({'engine':'FastForward','status':'unavailable'})
            result['message']+=' Dịch vụ cộng đồng không phản hồi.'
    if result['status']=='manual' and provider:
        if not api_ready():
            trace.append({'engine':'API miễn phí','status':'not_configured'})
        else:
            try:
                other=sdk_request(url,'sdk',None)
                trace.append({'engine':'API miễn phí','status':other['status']})
                if other['status']=='resolved':
                    result=other
                else:
                    result['message']+=' API: '+other.get('message','Chưa hoàn tất.')
            except Exception:
                trace.append({'engine':'API miễn phí','status':'unavailable'})
                result['message']+=' API không khả dụng hoặc cần xác minh.'
    result['platform']=platform(url)
    result['trace']=trace
    result['elapsed_ms']=round((time.monotonic()-started)*1000)
    result['original_url']=url
    return result

def validate_public_url(url):
    u,host=parse_url(url)
    public_ip(host,443 if u.scheme=='https' else 80)

def provider_error(exc):
    name=type(exc).__name__
    messages={'WorkflowMaintenanceError':'Nền tảng đang bảo trì.',
              'UnsupportedUrlError':'API chưa hỗ trợ URL này.',
              'UnsafeUrlError':'API từ chối URL không an toàn.',
              'CodeExhaustedError':'Nhà cung cấp hiện hết mã.',
              'DailyViewLimitError':'Đã hết hạn mức trong ngày.',
              'InvalidLinkError':'Link không hợp lệ hoặc đã bị xóa.',
              'KeywordExhaustedError':'Nhà cung cấp đã hết lượt xử lý từ khóa.'}
    status=getattr(exc,'status_code',None)
    if status in (401,402,403,429):
        return {401:'API key không hợp lệ hoặc đã thu hồi.',402:'Số dư API không đủ.',403:'API từ chối quyền truy cập.',429:'API giới hạn lượt gọi.'}[status]
    return messages.get(name,'API không trả kết quả. Kiểm tra kết nối hoặc hạn mức; không tự thử lại.')

def workflow_metadata(url):
    validate_public_url(url)
    from bypass_vuotlink_sdk import BypassVuotLink
    with BypassVuotLink(base_url=API_URL,api_key=API_KEY,timeout=12.0) as client:
        w=client.check_workflow(url)
        return {'name':str(getattr(w,'name','') or '').lower(),
                'maintenance':bool(getattr(w,'maintenance',False)),
                'price':getattr(w,'price',None),
                'code_ttl_seconds':getattr(w,'code_ttl_seconds',None),
                'has_captcha':bool(getattr(w,'has_captcha',False)),
                'is_support_free':getattr(w,'is_support_free',None)}

def preflight_code(url,brand=None):
    selected=detect_code_brand(url) if brand in (None,'','auto') else brand
    result={'kind':'code_preflight','brand':selected,'platform':BRANDS.get(selected,platform(url)),
            'status':'manual','message':'Chưa cấu hình API nhận mã. Không phát sinh phí.'}
    if not api_ready() or not ALLOW_CODE:
        return result
    try:
        meta=workflow_metadata(url)
    except Exception as exc:
        return dict(result,message=provider_error(exc))
    actual=meta['name']
    if actual in BRANDS:
        if brand not in (None,'','auto') and selected and selected!=actual:
            return dict(result,message='Nền tảng đã chọn không khớp dữ liệu nhà cung cấp.',workflow=meta)
        selected=actual
    if selected not in BRANDS:
        return dict(result,message='Không nhận diện được nền tảng nhận mã.',workflow=meta)
    if meta['maintenance']:
        return dict(result,brand=selected,platform=BRANDS[selected],message='Nền tảng đang bảo trì.',workflow=meta)
    return dict(result,status='ready',brand=selected,platform=BRANDS[selected],workflow=meta,
                message='Đã đọc metadata workflow; giá workflow không phải báo giá chắc chắn của Fetch Code.')

def request_code(url,brand=None,destination=None,consent=False):
    started=time.monotonic()
    requested=brand
    selected=detect_code_brand(url) if brand in (None,'','auto') else brand
    result={'status':'manual','kind':'code','platform':BRANDS.get(selected,platform(url)),'original_url':url}
    if not api_ready() or not ALLOW_CODE:
        return dict(result,message='Chưa bật API lấy mã trên hosting. Không có mã xác nhận; hãy hoàn thành trên trang gốc.',trace=[{'engine':'Fetch Code','status':'not_configured'}])
    if not consent:
        raise LinkError('Cần xác nhận hạn mức trước khi lấy mã.')
    target=destination or url
    validate_public_url(target)
    pre=preflight_code(url,requested)
    if pre.get('status')!='ready':
        return dict(result,message=pre['message'],trace=[{'engine':'Workflow','status':'manual'}])
    brand=pre['brand']
    result['platform']=BRANDS[brand]
    try:
        received=sdk_request(target,'code',brand)
    except Exception as exc:
        return dict(result,message=provider_error(exc),trace=[{'engine':'Fetch Code','status':'unavailable'}])
    code=received.get('code')
    if received.get('status')=='resolved' and isinstance(code,str) and code.strip() and len(code)<=200 and not any(ord(ch)<32 for ch in code):
        return dict(result,status='resolved',code=code,provider='VuotLink API',workflow=pre.get('workflow'),message='Đã nhận mã từ API; thời hạn workflow chỉ là tham khảo, chưa xác minh mã được trang nhiệm vụ chấp nhận.',elapsed_ms=round((time.monotonic()-started)*1000),trace=[{'engine':'Fetch Code','status':'code_received'}])
    return dict(result,message='API không trả mã. Nếu đang dùng link rút gọn, hãy cung cấp URL trang đích của nhiệm vụ.',trace=[{'engine':'Fetch Code','status':'not_found'}])

def sdk_request(url,mode,brand):
    if not api_ready(): raise LinkError('Chưa cấu hình API nhà cung cấp và mật khẩu ứng dụng.')
    if mode=='code' and not ALLOW_CODE: raise LinkError('API lấy mã chưa được chủ hosting cho phép sử dụng; có thể phát sinh phí.')
    u,host=parse_url(url); public_ip(host,443 if u.scheme=='https' else 80)
    from bypass_vuotlink_sdk import BypassVuotLink
    with BypassVuotLink(base_url=API_URL,api_key=API_KEY,timeout=55.0) as client:
        if mode=='code':
            if brand not in BRANDS: raise LinkError('Chọn đúng nền tảng lấy mã.')
            result=client.fetch_code(url,brand,source='live')
            code=getattr(result,'code',None)
            if not isinstance(code,(str,int)) or isinstance(code,bool) or not str(code).strip(): return {'status':'manual','message':'API không trả về mã.'}
            return {'status':'resolved','code':str(code),'message':'API đã trả mã; chưa xác minh việc sử dụng mã.'}
        result=client.resolve(url,max_hops=5,is_free=True,auto_solve_captcha=False)
        final=getattr(result,'final_url',None)
        if final:
            dest,host=parse_url(final)
            public_ip(host,443 if dest.scheme=='https' else 80)
        partial=getattr(result,'hops_exceeded',False) or getattr(result,'free_interrupted',False) or not final or final==url or getattr(result,'status_code',200) in (401,403,429)
        return {'status':'manual' if partial else 'resolved','url':final,'message':'Chưa hoàn tất; cần thao tác hoặc nền tảng không hỗ trợ miễn phí.' if partial else 'API trả về link đích.','provider':str(getattr(result,'workflow','') or '')}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,status,data,ctype='application/json; charset=utf-8'):
        raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer'); self.send_header('X-Frame-Options','DENY'); self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"); self.end_headers();
        if self.command != 'HEAD': self.wfile.write(raw)
    def do_HEAD(self):
        self.do_GET()
    def do_GET(self):
        route=urlsplit(self.path).path or '/'
        if route=='/health': return self.send(200,{'ok':True,'version':VERSION})
        if route=='/api/config': return self.send(200,capability())
        files={'/':('index.html','text/html; charset=utf-8'),'/index.html':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8')}
        if route in files:
            path,ctype=files[route]; return self.send(200,(ROOT/'static'/path).read_bytes(),ctype)
        self.send(404,{'message':'Không tìm thấy.'})
    def do_POST(self):
        route=urlsplit(self.path).path
        if route not in ('/api/resolve','/api/code/preflight'): return self.send(404,{'message':'Không tìm thấy.'})
        if not SLOTS.acquire(blocking=False): return self.send(429,{'message':'Đang bận, thử lại sau.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=8192: return self.send(400,{'message':'Dữ liệu không hợp lệ.'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.send(415,{'message':'Yêu cầu JSON.'})
            data=json.loads(self.rfile.read(size)); url=data.get('url','').strip(); mode=data.get('mode','auto')
            parse_url(url)
            uses_provider=(route=='/api/code/preflight' or mode in ('sdk','code','browser') or (mode=='auto' and data.get('provider') is True))
            if uses_provider and PASSWORD and not hmac.compare_digest(self.headers.get('X-Provider-Password','').encode(),PASSWORD.encode()):
                return self.send(401,{'status':'error','message':'API riêng yêu cầu xác thực; chế độ miễn phí không cần mật khẩu.'})
            if not (uses_provider and PASSWORD) and not public_allowed():
                return self.send(429,{'status':'error','message':'Đã đạt giới hạn 20 yêu cầu/phút cho web công khai.'})
            if route=='/api/code/preflight':
                return self.send(200,preflight_code(url,data.get('brand')))
            if mode not in ('auto','redirect','sdk','code','browser'): raise LinkError('Chế độ không hợp lệ.')
            if mode=='code':
                destination=data.get('destination') or None
                if destination: parse_url(destination)
                return self.send(200,request_code(url,data.get('brand'),destination,data.get('accept_cost') is True))
            result=resolve_auto(url,data.get('share') is True,data.get('provider') is True) if mode=='auto' else resolve_redirect(url) if mode=='redirect' else browser_probe.probe(url,validate_public_url) if mode=='browser' else sdk_request(url,mode,data.get('brand'))
            self.send(200,result)
        except LinkError as e: self.send(400,{'status':'error','message':str(e)})
        except (ValueError,AttributeError,TypeError): self.send(400,{'status':'error','message':'Dữ liệu không hợp lệ.'})
        except (OSError,http.client.HTTPException): self.send(502,{'status':'error','message':'Không thể kết nối hoặc đọc phản hồi từ máy chủ.'})
        except Exception: self.send(502,{'status':'error','message':'API không xử lý được link. Kiểm tra cấu hình, hạn mức hoặc xác minh thủ công.'})
        finally: SLOTS.release()

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler).serve_forever()
