"""Actual-seat browser tab checks; reference pixels come from public NativeUI."""
import json,re,subprocess,sys,time,urllib.parse,urllib.request
from PIL import Image

class Tabs:
 def __init__(self,command,wait,check,desktop,pages,root,window,args,env,repo):
  self.command,self.wait,self.check,self.desktop,self.pages=command,wait,check,desktop,pages
  self.root,self.window,self.args,self.env,self.repo=root,window,args,env,repo
  self.order=[pages()[0]['id']]
 def snapshot(self):
  lines=(self.root/'chromium-hook.log').read_text().splitlines();groups=[]
  for line in lines:
   if line.startswith('tabs-state '):
    value=dict(re.findall(r'(\w+)=([^ ]+)',line));value={k:int(v) if k!='content' else [float(n) for n in v.split(',')] for k,v in value.items()};value['items']=[];groups.append(value)
   elif line.startswith('tabs-item ') and groups:
    item=dict(re.findall(r'(\w+)=([^ ]+)',line));groups[-1]['items'].append({k:float(v) if k in ['x','y','width','height'] else int(v) for k,v in item.items()})
  return next((g for g in reversed(groups) if len(g['items'])==g['count']),None)
 def native(self,count=None,selected=None):
  return self.wait(self.snapshot,lambda s:s and (count is None or s['count']==count) and (selected is None or s['selected']==selected))
 def pixels(self,label,state=None):
  # Browser model/geometry can precede the completed original container
  # animation. Require the complete committed native image, not a timer.
  result=self.wait(lambda:self.pixel_attempt(label),lambda r:r[0])
  self.check(label+'-whole-native-tabs-pixels',result[0],box=result[1],state=result[2])
 def pixel_attempt(self,label,state=None):
  state=state or self.native();metadata={p['id']:p for p in self.pages()}
  self.order.extend(p['id'] for p in reversed(self.pages()) if p['id'] not in self.order)
  assert len(self.order)==state['count'],(self.order,state)
  items=[dict(id=str(item['native_id']),title=metadata[target]['title']) for item,target in zip(state['items'],self.order)]
  model=dict(width=state['width'],height=state['height'],items=items,selected=items[state['selected']]['id'])
  path=self.root/(label+'-tab-model.json');path.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
  pixels=self.root/(label+'-tab-reference.argb')
  result=subprocess.run([sys.executable,str(self.repo/'Tests/NativeUI/render-tab-reference.py'),'--library',str(self.args.library),'--model',str(path),'--output',str(pixels),'-GSBackend','wayland','-GSTheme','NextSpace'],env=self.env,text=True,capture_output=True,timeout=15)
  (self.root/(label+'-tab-reference.stdout')).write_text(result.stdout);(self.root/(label+'-tab-reference.stderr')).write_text(result.stderr);assert result.returncode==0,result.stderr
  info=json.loads(result.stdout);expected=Image.frombytes('RGBA',(info['width'],info['height']),pixels.read_bytes(),'raw','BGRA',info['stride']).convert('RGB');expected.save(pixels.with_suffix('.png'))
  windows=self.command('windows');window=next(w for w in windows if w['id']==self.window['id'])
  left=window['x']+window.get('frame_left',0)+state['x'];top=window['y']+window.get('frame_top',0)+state['y']
  box=(left,top,left+state['width'],top+state['height'])
  assert self.command('pointer 1400 900')['ok']
  actual=self.desktop(label+'-tabs').crop(box);actual.save(self.root/(label+'-tab-actual.png'))
  return actual.size==expected.size and actual.tobytes()==expected.tobytes(),box,state
 def click(self,index):
  state=self.native();item=state['items'][index]
  window=next(w for w in self.command('windows') if w['id']==self.window['id'])
  x=round(window['x']+window.get('frame_left',0)+state['x']+item['x']+item['width']/2)
  y=round(window['y']+window.get('frame_top',0)+state['y']+item['y']+item['height']/2)
  assert self.command('pointer '+str(x)+' '+str(y))['ok'];assert self.command('button 272')['ok']
  return self.native(selected=index)
 def recovered(self):
  state=self.native(count=len(self.pages()));self.pixels('recovered',state)
  self.click(0);self.check('recovered-native-tab-pointer-selects-browser',self.native()['selected']==0)
  self.pixels('recovered-selected')
 def title_updates(self):
  import http.server,threading
  released=threading.Event()
  class Page(http.server.BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_GET(self):
    if self.path!='/title-stage':self.send_error(404);return
    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
    self.wfile.write(b'<!doctype html><meta charset=utf-8><title>Initial tab title</title><p>Native title fixture</p>');self.wfile.flush()
    if released.wait(60):self.wfile.write('<script>document.title="Updated日本語"</script>'.encode())
  with http.server.ThreadingHTTPServer(('127.0.0.1',0),Page) as server:
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    url='http://127.0.0.1:'+str(server.server_port)+'/title-stage'
    target=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(self.args.port)+'/json/new?'+url,method='PUT'),timeout=5));self.order.append(target['id'])
    self.wait(self.pages,lambda values:any(p['id']==target['id'] and p['title']=='Initial tab title' for p in values))
    state=self.native(count=len(self.order),selected=len(self.order)-1);identifier=state['items'][-1]['native_id']
    self.pixels('loading-title',state);released.set()
    self.wait(self.pages,lambda values:any(p['id']==target['id'] and p['title']=='Updated日本語' for p in values))
    self.pixels('updated-title');self.check('late-title-update-retains-native-tab-identity',self.native()['items'][-1]['native_id']==identifier)
   finally:released.set();server.shutdown();thread.join(timeout=5)

def run(command,wait,check,desktop,pages,root,window,args,env,repo):
 tabs=Tabs(command,wait,check,desktop,pages,root,window,args,env,repo)
 check('native-tab-binding-enabled','experimental native browser tabs enabled' in (root/'chromium-hook.log').read_text())
 tabs.native(count=1)
 for title in ['Native tab two','日本語']:
  url='data:text/html;charset=utf-8,'+urllib.parse.quote('<meta charset=utf-8><title>'+title+'</title><p>'+title+'</p>')
  request=urllib.request.Request('http://127.0.0.1:'+str(args.port)+'/json/new?'+url,method='PUT')
  target=json.load(urllib.request.urlopen(request,timeout=5));tabs.order.append(target['id'])
  wait(pages,lambda values:any(p['id']==target['id'] and p['title']==title for p in values))
 state=tabs.native(count=3,selected=2);tabs.pixels('initial',state)
 first_ids=[item['native_id'] for item in state['items']]
 check('tab-wire-identities-are-opaque-sequence-values',first_ids==[1,2,3])
 before=(root/'chromium-hook.log').read_text().count('tabs-select ');tabs.click(0)
 trace=(root/'chromium-hook.log').read_text();check('native-tab-pointer-calls-browser-controller-once',trace.count('tabs-select ')==before+1)
 expected=next(p['title'] for p in pages() if p['id']==tabs.order[0])
 selected=wait(lambda:command('windows'),lambda ws:any(w['id']==window['id'] and expected in w['title'] for w in ws))
 check('native-tab-selection-reaches-browser-document',any(w['id']==window['id'] and expected in w['title'] for w in selected))
 tabs.pixels('selected')
 before_click=next(w for w in command('windows') if w['id']==window['id'])
 tabs.click(0)
 # Consecutive physical clicks must remain native client input. The old
 # engine's empty-container classification treated them as a caption pair.
 assert command('button 272')['ok']
 time.sleep(.4)
 current=next(w for w in command('windows') if w['id']==window['id'])
 check('native-tab-double-click-stays-client-area',not current['maximized'] and not current['shaded'] and tuple(current[k] for k in ['x','y','width','height'])==tuple(before_click[k] for k in ['x','y','width','height']),before=before_click,after=current)
 check('selected-native-tab-click-has-no-second-command',(root/'chromium-hook.log').read_text().count('tabs-select ')==before+1)
 for key in ['key 29 1','key 15 1','key 15 0','key 29 0']:assert command(key)['ok']
 state=tabs.native(selected=1);check('browser-next-tab-command-updates-native-selection',state['selected']==1);tabs.pixels('next-command',state)
 closing=tabs.order.pop(1)
 for key in ['key 29 1','key 17 1','key 17 0','key 29 0']:assert command(key)['ok']
 wait(pages,lambda values:all(p['id']!=closing for p in values))
 state=tabs.native(count=2,selected=1)
 check('close-tab-command-retains-remaining-native-identities',[item['native_id'] for item in state['items']]==[first_ids[0],first_ids[2]])
 tabs.pixels('closed',state)
 url='data:text/html;charset=utf-8,'+urllib.parse.quote('<meta charset=utf-8><title>Replacement tab</title>')
 target=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(args.port)+'/json/new?'+url,method='PUT'),timeout=5));tabs.order.append(target['id'])
 wait(pages,lambda values:any(p['id']==target['id'] and p['title']=='Replacement tab' for p in values))
 state=tabs.native(count=3,selected=2)
 check('replacement-tab-receives-fresh-opaque-identity',[item['native_id'] for item in state['items']]==[first_ids[0],first_ids[2],4]);tabs.pixels('replaced',state)
 for key in ['key 29 1','key 42 1','key 104 1','key 104 0','key 42 0','key 29 0']:assert command(key)['ok']
 tabs.order.insert(1,tabs.order.pop(2));state=tabs.native(count=3,selected=1)
 check('browser-reorder-command-retains-native-identities',[item['native_id'] for item in state['items']]==[first_ids[0],4,first_ids[2]]);tabs.pixels('reordered',state)
 def menu_visible(windows):
  menus=[w for w in windows if w['level']==20 and w['visible']]
  return len(menus)==1 and menus[0]['title']=='Chromium' and any(w['id']==window['id'] and w['focused'] for w in windows)
 visible=wait(lambda:command('windows'),menu_visible)
 check('detached-menu-recovers-after-tab-input-without-refocus',menu_visible(visible))
 tabs.title_updates()
 def idle():
  before=(root/'chromium-hook.log').read_text().count('tabs-state ');time.sleep(.25)
  return (root/'chromium-hook.log').read_text().count('tabs-state ')-before
 wait(idle,lambda frames:frames==0)
 check('native-tabs-do-not-repaint-continuously-while-idle',True)
 return tabs
