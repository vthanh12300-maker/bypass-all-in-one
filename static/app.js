'use strict';
const $=id=>document.getElementById(id);
let copied='',config=null,history=[];
function safeURL(s){try{const u=new URL(s);return ['https:','http:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
function link(id,url,label){const el=$(id),safe=safeURL(url);el.hidden=!safe;if(safe){el.href=safe;el.textContent=label;}else el.removeAttribute('href');}
function modeChange(){const m=$('mode').value;$('run').textContent=m==='code'?'Lấy mã xác nhận':'Xử lý link';$('cost').disabled=!config?.code;$('codeapi').textContent=config?.code?'API lấy mã đã được bật, chưa xác minh kết nối live.':'API lấy mã chưa được bật. Chỉ có thể nhận mã từ trang gốc.';$('brands').hidden=m!=='code';$('advanced').hidden=m!=='auto';$('lock').hidden=!(config?.provider_locked&&(['code','sdk','browser'].includes(m)||(m==='auto'&&$('provider').checked)));}
fetch('/api/config').then(r=>{if(!r.ok)throw Error();return r.json();}).then(c=>{
 config=c;$('apistatus').textContent='V'+c.version+' · '+(c.api?'API đã cấu hình, chưa xác nhận kết nối live.':'Chưa cấu hình API Việt Nam. Chế độ kiểm tra miễn phí và mở trình duyệt vẫn khả dụng.');
 $('providerbox').hidden=!c.api;
 for(const [id,name] of Object.entries(c.brands||{})){const o=document.createElement('option');o.value=id;o.textContent=name;$('brand').append(o);const s=document.createElement('span');s.className='chip';s.textContent=name;$('chips').append(s);}
 for(const o of $('mode').options){if(o.value==='browser'){o.disabled=!c.browser;if(c.browser)o.textContent='Playwright · kiểm tra bằng trình duyệt';}if(o.value==='sdk'){o.disabled=!c.api;if(c.api)o.textContent='API miễn phí';}}
 modeChange();
}).catch(()=>{$('apistatus').textContent='Không tải được cấu hình máy chủ. Có thể dùng mở trình duyệt.';});
$('mode').addEventListener('change',modeChange);
$('paste').onclick=async()=>{try{$('url').value=(await navigator.clipboard.readText()).trim();$('hint').textContent='';}catch{$('url').focus();$('hint').textContent='Nhấn giữ ô link rồi chọn Dán.';}};
$('clear').onclick=()=>{$('url').value='';$('result').hidden=true;$('hint').textContent='';$('url').focus();};
function record(url,status){history=[{url,status},...history.filter(x=>x.url!==url)].slice(0,15);renderHistory();}
function renderHistory(){$('history').replaceChildren();for(const h of history){const b=document.createElement('button');b.type='button';b.className='secondary';b.textContent=h.status+' · '+h.url;b.onclick=()=>{$('url').value=h.url;window.scrollTo({top:0,behavior:'smooth'});};$('history').append(b);}}
$('clearhistory').onclick=()=>{history=[];renderHistory();};
function manual(url){$('manual').hidden=false;link('original',url,'Mở trang gốc trên trình duyệt');}
function render(d,url){$('state').textContent=d.status==='resolved'?(d.code?'Đã nhận mã xác nhận':'Có link đích'):d.status==='candidate'?'Đích tham khảo — chưa xác minh':d.status==='manual'?'Cần hoàn thành trên trang gốc':'Không xử lý được';
 $('codepanel').hidden=!(d.kind==='code'&&d.status==='resolved'&&d.code);$('codevalue').textContent=$('codepanel').hidden?'':d.code;$('codettl').textContent=d.workflow?.code_ttl_seconds!=null?'Thời hạn tham khảo theo nền tảng: '+d.workflow.code_ttl_seconds+' giây (không phải thời gian còn lại).':'';
 $('output').textContent=[d.platform?'Nền tảng: '+d.platform:'',d.message,d.code&&$('codepanel').hidden?'Mã: '+d.code:'',d.url?'URL: '+d.url:''].filter(Boolean).join('\n');
 $('steps').replaceChildren();$('trace').hidden=!d.trace?.length;
 const labels={resolved:'Có đích',manual:'Chưa hoàn tất',candidate:'Có đích tham khảo',not_found:'Không tìm thấy',code_received:'Đã nhận mã',not_configured:'Chưa cấu hình',unavailable:'Không khả dụng'};
 for(const t of d.trace||[]){const row=document.createElement('div');row.className='trace';row.textContent=t.engine+' — '+(labels[t.status]||t.status)+(t.http_status?' (HTTP '+t.http_status+')':'');$('steps').append(row);}
 if(d.elapsed_ms!=null){const row=document.createElement('div');row.className='trace muted';row.textContent='Thời gian: '+(d.elapsed_ms/1000).toFixed(2)+' giây';$('steps').append(row);}
 if(['resolved','candidate'].includes(d.status)){copied=d.code||d.url||'';$('copy').hidden=!copied;$('copy').textContent=d.code?'Sao chép mã':'Sao chép kết quả';}
 if(d.url&&d.status!=='manual')link('open',d.url,d.status==='candidate'?'Mở đích tham khảo':'Mở link đích');
 if(d.status!=='resolved')manual(url);record(url,$('state').textContent);
}
$('form').addEventListener('submit',async e=>{e.preventDefault();const url=safeURL($('url').value.trim()),mode=$('mode').value;if(!url){$('hint').textContent='Nhập URL HTTP/HTTPS hợp lệ.';return;}if(mode==='code'&&config?.code&&!$('cost').checked){$('hint').textContent='Xác nhận hạn mức API trước khi lấy mã.';return;}
 $('hint').textContent='';$('run').disabled=true;$('result').hidden=false;$('state').textContent='Đang xử lý…';$('output').textContent='';$('copy').hidden=true;$('copy').textContent='Sao chép kết quả';$('open').hidden=true;$('trace').hidden=true;$('codepanel').hidden=true;$('codevalue').textContent='';$('manual').hidden=true;$('manualcode').value='';$('codestate').textContent='';copied='';
 try{if(mode==='manual'){render({status:'manual',message:'Sử dụng phiên Chrome/Firefox của bạn để hoàn thành nhiệm vụ.'},url);return;}
 const r=await fetch('/api/resolve',{method:'POST',headers:{'Content-Type':'application/json','X-Provider-Password':$('password').value},body:JSON.stringify({url,mode,brand:$('brand').value,share:$('share').checked,provider:$('provider').checked,destination:$('destination').value.trim(),accept_cost:$('cost').checked})});const d=await r.json();render(d,url);
 }catch(err){render({status:'error',message:'Không kết nối được backend. Có thể mở trang gốc.'},url);}finally{$('run').disabled=false;}
});
async function copy(value,status){if(!value){status.textContent='Chưa có dữ liệu để sao chép.';return;}try{await navigator.clipboard.writeText(value);status.textContent='Đã sao chép';}catch{status.textContent='Nhấn giữ dữ liệu để sao chép.';}}
$('copy').onclick=()=>copy(copied,$('copy'));
$('copycode').onclick=()=>copy($('manualcode').value.trim(),$('codestate'));

modeChange();

$('provider').addEventListener('change',modeChange);
$('preflight').onclick=async()=>{const url=safeURL($('url').value.trim());if(!url){$('preflightresult').textContent='Nhập link hợp lệ trước.';return;}const b=$('preflight');b.disabled=true;$('preflightresult').textContent='Đang kiểm tra…';try{const r=await fetch('/api/code/preflight',{method:'POST',headers:{'Content-Type':'application/json','X-Provider-Password':$('password').value},body:JSON.stringify({url,brand:$('brand').value})});const d=await r.json();const w=d.workflow;$('preflightresult').textContent=[d.platform,d.message,w?.price!=null?'Giá workflow tham khảo: '+w.price:null,w?.code_ttl_seconds!=null?'TTL tham khảo: '+w.code_ttl_seconds+' giây':null,w?.has_captcha?'Có bước CAPTCHA':null].filter(Boolean).join(' · ');if(d.status==='ready'&&d.brand&&[...$('brand').options].some(o=>o.value===d.brand))$('brand').value=d.brand;}catch{$('preflightresult').textContent='Không kết nối được backend.';}finally{b.disabled=false;}};
