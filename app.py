import os, json, socket, ssl, http.client, ipaddress, hmac, threading, time
from urllib.parse import urlsplit, urljoin, urlunsplit, urlencode
from html.parser import HTMLParser
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
BRANDS = {'ontops':'Ontops','ontops-dr':'Ontops DR','link4m':'Link4M','funlink':'FunLink','toplinks':'TopLinks','gtraffic':'GTraffic','gtraffic-dr':'GTraffic DR','layma':'LayMa'}
VERSION = '2.0'
SLOTS = threading.BoundedSemaphore(2)
DOMAIN_BRANDS = {'toplinks.io':'TopLinks','ontops.link':'Ontops','link4m.com':'Link4M','funlink.io':'FunLink','yeumoney.com':'YeuMoney','yeulink.com':'YeuLink','synurl.com':'SynURL','linktot.net':'LinkTot','gtraffic.io':'GTraffic','layma.net':'LayMa','linkvertise.com':'Linkvertise','lootlabs.gg':'LootLabs','loot-link.com':'LootLabs','work.ink':'Work.ink','adf.ly':'AdFly'}
def platform(url):
    _,host=parse_url(url)
    return next((name for domain,name in DOMAIN_BRANDS.items() if host==domain or host.endswith('.'+domain)),host)

PASSWORD = os.environ.get('APP_PASSWORD','')
API_URL = os.environ.get('BYPASS_BASE_URL','')
API_KEY = os.environ.get('BYPASS_API_KEY','')

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

def resolve_auto(url,share=False):
    result=resolve_redirect(url)
    result['platform']=platform(url)
    if result['status']=='resolved': return result
    if share:
        try:
            candidate=crowd_lookup(url)
            if candidate:
                candidate['platform']=result['platform']
                return candidate
        except (OSError,ValueError,LinkError,http.client.HTTPException):
            pass
        result['message']+=' Không tìm được kết quả từ cơ sở dữ liệu cộng đồng.'
    return result

def sdk_request(url,mode,brand):
    if not (API_URL and API_KEY and PASSWORD): raise LinkError('Chưa cấu hình API nhà cung cấp và mật khẩu ứng dụng.')
    u,host=parse_url(url); public_ip(host,443 if u.scheme=='https' else 80)
    from bypass_vuotlink_sdk import BypassVuotLink
    with BypassVuotLink(base_url=API_URL,api_key=API_KEY,timeout=55.0) as client:
        if mode=='code':
            if brand not in BRANDS: raise LinkError('Chọn đúng nền tảng lấy mã.')
            result=client.fetch_code(url,brand,source='live')
            code=getattr(result,'code',None)
            if not code: return {'status':'manual','message':'API không trả về mã.'}
            return {'status':'resolved','code':str(code),'message':'API đã trả mã; chưa xác minh việc sử dụng mã.'}
        result=client.resolve(url,max_hops=5,is_free=True,auto_solve_captcha=False)
        final=getattr(result,'final_url',None)
        if final: parse_url(final)
        partial=getattr(result,'hops_exceeded',False) or getattr(result,'free_interrupted',False) or not final or final==url
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
        if route=='/api/config': return self.send(200,{'api':bool(API_URL and API_KEY and PASSWORD),'brands':BRANDS,'locked':bool(PASSWORD),'version':VERSION,'crowd':True})
        files={'/':('index.html','text/html; charset=utf-8'),'/index.html':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8')}
        if route in files:
            path,ctype=files[route]; return self.send(200,(ROOT/'static'/path).read_bytes(),ctype)
        self.send(404,{'message':'Không tìm thấy.'})
    def do_POST(self):
        if urlsplit(self.path).path!='/api/resolve': return self.send(404,{'message':'Không tìm thấy.'})
        if PASSWORD and not hmac.compare_digest(self.headers.get('X-App-Password','').encode(),PASSWORD.encode()): return self.send(401,{'message':'Mật khẩu ứng dụng không đúng.'})
        if not SLOTS.acquire(blocking=False): return self.send(429,{'message':'Đang bận, thử lại sau.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=8192: return self.send(400,{'message':'Dữ liệu không hợp lệ.'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': return self.send(415,{'message':'Yêu cầu JSON.'})
            data=json.loads(self.rfile.read(size)); url=data.get('url','').strip(); mode=data.get('mode','auto')
            parse_url(url)
            if mode not in ('auto','redirect','sdk','code'): raise LinkError('Chế độ không hợp lệ.')
            result=resolve_auto(url,data.get('share') is True) if mode=='auto' else resolve_redirect(url) if mode=='redirect' else sdk_request(url,mode,data.get('brand'))
            self.send(200,result)
        except LinkError as e: self.send(400,{'status':'error','message':str(e)})
        except (ValueError,AttributeError,TypeError): self.send(400,{'status':'error','message':'Dữ liệu không hợp lệ.'})
        except (OSError,http.client.HTTPException): self.send(502,{'status':'error','message':'Không thể kết nối hoặc đọc phản hồi từ máy chủ.'})
        except Exception: self.send(502,{'status':'error','message':'API không xử lý được link. Kiểm tra cấu hình, hạn mức hoặc xác minh thủ công.'})
        finally: SLOTS.release()

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler).serve_forever()
