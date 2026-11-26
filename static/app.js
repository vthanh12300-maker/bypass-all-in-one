'use strict';
const $=id=>document.getElementById(id); let copied='';
fetch('/api/config').then(r=>r.json()).then(c=>{
 $('apistatus').textContent=c.api?'API đã được cấu hình (chưa xác minh tình trạng nhà cung cấp).':'Chưa cấu hình API; chỉ có kiểm tra redirect HTTP.';
 $('lock').hidden=!c.locked;
 for(const [id,name] of Object.entries(c.brands)){const o=document.createElement('option');o.value=id;o.textContent=name;$('brand').append(o);const s=document.createElement('span');s.className='chip';s.textContent=name;$('chips').append(s);}
 for(const o of $('mode').options){if(o.value!=='redirect'){o.disabled=!c.api;if(c.api)o.textContent=o.value==='code'?'API lấy mã':'API vượt link (miễn phí nếu hỗ trợ)';}}
}).catch(()=>{$('apistatus').textContent='Không tải được cấu hình.';});
$('mode').addEventListener('change',()=>{$('brands').hidden=$('mode').value!=='code';});
$('form').addEventListener('submit',async e=>{e.preventDefault();$('run').disabled=true;$('result').hidden=false;$('state').textContent='Đang xử lý…';$('output').textContent='';$('copy').hidden=true;$('open').hidden=true;copied='';
 try{const r=await fetch('/api/resolve',{method:'POST',headers:{'Content-Type':'application/json','X-App-Password':$('password').value},body:JSON.stringify({url:$('url').value.trim(),mode:$('mode').value,brand:$('brand').value})});const d=await r.json();$('state').textContent=d.status==='resolved'?'Có kết quả':d.status==='manual'?'Chưa hoàn tất':'Không xử lý được';$('output').textContent=[d.message,d.code?'Mã: '+d.code:'',d.url?'URL: '+d.url:''].filter(Boolean).join('\n');if(d.status==='resolved'){copied=d.code||d.url||'';$('copy').hidden=!copied;}if(d.url){const u=new URL(d.url);if(['https:','http:'].includes(u.protocol)){$('open').href=u.href;$('open').hidden=false;}}}
 catch(err){$('state').textContent='Lỗi kết nối';$('output').textContent='Không thể kết nối backend.';}finally{$('run').disabled=false;}});
$('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(copied);$('copy').textContent='Đã sao chép';}catch{$('copy').textContent='Hãy nhấn giữ kết quả để sao chép';}});
