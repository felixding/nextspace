"""Actual-seat Firefox tabs; complete references use the shared NativeUI API."""
import json,re,subprocess,sys,time,urllib.parse
from PIL import Image,ImageChops

class Tabs:
 def __init__(self,command,wait,check,desktop,js,root,window,args,env,repo):
  self.command,self.wait,self.check,self.desktop,self.js=command,wait,check,desktop,js
  self.root,self.window,self.args,self.env,self.repo=root,window,args,env,repo
 def model(self):
  return self.js("return {rect:gBrowser.tabContainer.getBoundingClientRect().toJSON(),tabs:Array.from(gBrowser.tabs).map(t=>({title:t.label,selected:t.selected}))}")
 def snapshot(self):
  groups=[]
  for line in (self.root/'firefox-hook.log').read_text().splitlines():
   if line.startswith('tabs-state '):
    row={k:int(v) for k,v in re.findall(r'(\w+)=([^ ]+)',line)};row['items']=[];groups.append(row)
   elif line.startswith('tabs-item ') and groups:
    groups[-1]['items'].append({k:float(v) if k in ['x','y','width','height'] else int(v) for k,v in re.findall(r'(\w+)=([^ ]+)',line)})
  return next((x for x in reversed(groups) if len(x['items'])==x['count']),None)
 def native(self,count=None,selected=None):
  return self.wait(self.snapshot,lambda s:s and (count is None or s['count']==count) and (selected is None or s['selected']==selected))
 def pixels(self,name):
  def attempt():
   data=self.model();s=self.snapshot()
   if not s or s['count']!=len(data['tabs']):return False
   payload=dict(width=s['width'],height=s['height'],items=[dict(id=str(i['native_id']),title=t['title']) for i,t in zip(s['items'],data['tabs'])],selected=str(s['items'][s['selected']]['native_id']))
   p=self.root/(name+'-tab-model.json');p.write_text(json.dumps(payload,ensure_ascii=False)+'\n');out=self.root/(name+'-tab-reference.argb')
   r=subprocess.run([sys.executable,str(self.repo/'Tests/NativeUI/render-tab-reference.py'),'--library',str(self.args.library),'--model',str(p),'--output',str(out),'-GSBackend','wayland','-GSTheme','NextSpace'],env=self.env,capture_output=True,text=True,timeout=15)
   (self.root/(name+'-tab-reference.stdout')).write_text(r.stdout);(self.root/(name+'-tab-reference.stderr')).write_text(r.stderr);assert r.returncode==0,r.stderr
   info=json.loads(r.stdout);expected=Image.frombytes('RGBA',(info['width'],info['height']),out.read_bytes(),'raw','BGRA',info['stride']).convert('RGB');expected.save(out.with_suffix('.png'))
   w=next(x for x in self.command('windows') if x['id']==self.window['id']);rect=data['rect'];x=round(w['x']+w['frame_left']+rect['x']);y=round(w['y']+w['frame_top']+rect['y'])
   assert self.command('pointer 1400 900')['ok']
   actual=self.desktop(name+'-tabs').crop((x,y,x+s['width'],y+s['height']));actual.save(self.root/(name+'-tab-actual.png'))
   return ImageChops.difference(actual,expected).getbbox() is None
  self.check(name+'-whole-native-tabs-pixels',self.wait(attempt,lambda x:x))
 def point(self,index):
  data=self.model();s=self.native();w=next(x for x in self.command('windows') if x['id']==self.window['id']);item=s['items'][index]
  x=round(w['x']+w['frame_left']+data['rect']['x']+item['x']+item['width']/2);y=round(w['y']+w['frame_top']+data['rect']['y']+item['y']+item['height']/2)
  assert self.command(f'pointer {x} {y}')['ok']
 def click(self,index):
  self.point(index);assert self.command('button 272')['ok'];return self.native(selected=index)
 def keys(self,events):
  for event in events:assert self.command(event)['ok']
 def recovered(self):
  self.native(count=1);self.pixels('tabs-host-replaced')
  self.js("gBrowser.selectedTab=gBrowser.addTrustedTab('about:blank',{triggeringPrincipal:Services.scriptSecurityManager.getSystemPrincipal()});return true")
  self.native(count=2,selected=1);self.click(0)
  self.check('host-replaced-native-firefox-tab-pointer-selects-browser',self.model()['tabs'][0]['selected'])
  self.pixels('tabs-host-replaced-selected')
  self.js("gBrowser.removeTab(gBrowser.tabs[1],{animate:false});return true");self.native(count=1)
 def loading_title(self):
  import http.server,threading
  released=threading.Event()
  class Page(http.server.BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):
    if self.path!='/title-stage':self.send_error(404);return
    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
    self.wfile.write(b'<!doctype html><meta charset=utf-8><title>Initial tab title</title><p>Native title fixture</p>');self.wfile.flush()
    if released.wait(60):self.wfile.write('<script>document.title="Loaded日本語"</script>'.encode())
  with http.server.ThreadingHTTPServer(('127.0.0.1',0),Page) as server:
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    url='http://127.0.0.1:'+str(server.server_port)+'/title-stage'
    self.js('gBrowser.selectedTab=gBrowser.addTrustedTab('+json.dumps(url)+',{triggeringPrincipal:Services.scriptSecurityManager.getSystemPrincipal()});return true')
    self.wait(self.model,lambda m:len(m['tabs'])==4 and m['tabs'][3]['title']=='Initial tab title');s=self.native(count=4,selected=3);identifier=s['items'][3]['native_id']
    self.pixels('tabs-loading-title');released.set()
    self.wait(self.model,lambda m:m['tabs'][3]['title']=='Loaded日本語');self.pixels('tabs-loaded-title')
    self.check('firefox-loaded-title-keeps-native-identity',self.native()['items'][3]['native_id']==identifier)
   finally:released.set();server.shutdown();thread.join(timeout=5)
 def run(self):
  self.check('native-firefox-tab-binding-enabled','experimental native Gecko tab container installed' in (self.root/'firefox-hook.log').read_text())
  self.js("window.__nxsTabFixture={base:gBrowser.selectedTab,events:[]};gBrowser.tabContainer.addEventListener('TabSelect',e=>window.__nxsTabFixture.events.push({title:e.target.label,trusted:e.isTrusted}));return true")
  self.native(count=1);self.pixels('tabs-initial')
  for title in ['Native tab two','日本語']:
   url='data:text/html;charset=utf-8,'+urllib.parse.quote('<meta charset=utf-8><title>'+title+'</title><p>'+title+'</p>')
   self.js('gBrowser.selectedTab=gBrowser.addTrustedTab('+json.dumps(url)+',{triggeringPrincipal:Services.scriptSecurityManager.getSystemPrincipal()});return true')
   self.wait(self.model,lambda d:any(t['title']==title for t in d['tabs']))
  s=self.native(count=3,selected=2);ids=[x['native_id'] for x in s['items']]
  self.check('firefox-tab-identities-are-distinct-opaque-values',len(set(ids))==3 and all(0<i<10000 for i in ids));self.pixels('tabs-three')
  before=self.js('return window.__nxsTabFixture.events.length');self.click(0)
  self.wait(self.model,lambda d:d['tabs'][0]['selected'])
  events=self.js('return window.__nxsTabFixture.events.slice('+str(before)+')')
  self.check('native-firefox-pointer-selects-once-through-trusted-browser-event',len(events)==1 and events[0]['trusted'],events=events);self.pixels('tabs-selected')
  self.point(0);self.command('button 272');self.command('button 272');time.sleep(.4)
  w=next(w for w in self.command('windows') if w['id']==self.window['id'])
  self.check('native-firefox-tab-double-click-stays-client-area',not w['maximized'] and not w['shaded'])
  self.check('selected-firefox-native-tab-emits-no-second-selection',self.js('return window.__nxsTabFixture.events.length')==before+1)
  self.js("gBrowser.tabContainer.addEventListener('mousedown',e=>e.preventDefault(),{capture:true,once:true});return true")
  self.point(2);assert self.command('button 272')['ok'];time.sleep(.25)
  self.check('firefox-cancelled-native-tab-pointer-keeps-selection',self.model()['tabs'][0]['selected'] and self.js('return window.__nxsTabFixture.events.length')==before+1)
  self.pixels('tabs-cancelled')
  self.keys(['key 29 1','key 109 1','key 109 0','key 29 0']);self.native(selected=1)
  self.check('firefox-next-tab-command-updates-native-model',self.model()['tabs'][1]['selected']);self.pixels('tabs-next')
  self.keys(['key 29 1','key 17 1','key 17 0','key 29 0']);s=self.native(count=2)
  self.check('firefox-close-preserves-remaining-native-identities',[x['native_id'] for x in s['items']]==[ids[0],ids[2]]);self.pixels('tabs-closed')
  title='Replacement tab';url='data:text/html;charset=utf-8,'+urllib.parse.quote('<meta charset=utf-8><title>'+title+'</title>')
  self.js('gBrowser.selectedTab=gBrowser.addTrustedTab('+json.dumps(url)+',{triggeringPrincipal:Services.scriptSecurityManager.getSystemPrincipal()});return true')
  self.wait(self.model,lambda d:len(d['tabs'])==3 and d['tabs'][2]['title']==title);s=self.native(count=3,selected=2);replacement=s['items'][2]['native_id']
  self.check('firefox-replacement-gets-new-opaque-identity',replacement not in ids);self.pixels('tabs-replaced')
  self.keys(['key 29 1','key 42 1','key 104 1','key 104 0','key 42 0','key 29 0']);s=self.native(count=3,selected=1)
  self.check('firefox-reorder-preserves-native-identities',[x['native_id'] for x in s['items']]==[ids[0],replacement,ids[2]]);self.pixels('tabs-reordered')
  # Update the browser's actual title model through its existing API; the
  # separate streamed-title fixture will qualify loading-document updates.
  self.js("gBrowser._setTabLabel(gBrowser.selectedTab,'Updated日本語');return true")
  self.wait(self.model,lambda d:d['tabs'][1]['title']=='Updated日本語');self.pixels('tabs-title-updated')
  self.check('firefox-title-update-keeps-identity',self.native()['items'][1]['native_id']==replacement)
  self.loading_title()
  self.js("for(let t of Array.from(gBrowser.tabs))if(t!==window.__nxsTabFixture.base)gBrowser.removeTab(t,{animate:false});gBrowser.selectedTab=window.__nxsTabFixture.base;return true")
  s=self.native(count=1,selected=0);self.check('firefox-return-to-original-tab-keeps-identity',s['items'][0]['native_id']==ids[0]);self.pixels('tabs-original')
  def idle():
   n=(self.root/'firefox-hook.log').read_text().count('tabs-state ');time.sleep(.25);return (self.root/'firefox-hook.log').read_text().count('tabs-state ')-n
  self.wait(idle,lambda n:n==0);self.check('firefox-native-tabs-idle-without-repaint-loop',True)
  return self
