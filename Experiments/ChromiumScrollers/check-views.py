#!/usr/bin/env python3
"""Check a private headless Views fixture using real compositor input and NativeUI.

The fixture owns control.sock, Chromium, GPBS and a trusted screencopy client.
NEXTSPACE_CHROMIUM_VIEWS_TRACE must be enabled only for synthetic test data.
"""
import argparse,json,os,socket,subprocess,time
from PIL import Image
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fixture',type=Path,required=True)
parser.add_argument('--references',type=Path,required=True)
parser.add_argument('--pasteboard-probe',type=Path,required=True)
parser.add_argument('--native-text-app',type=Path,required=True)
parser.add_argument('--backend',required=True)
a=parser.parse_args();root=a.fixture;results=[]
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(15);s.connect(str(root/'control.sock'));s.send(json.dumps(dict(command=text)).encode());return json.loads(s.recv(65536))
def key(code,*modifiers):
 for code2 in modifiers:assert command(f'key {code2} 1')['ok']
 for state in [1,0]:assert command(f'key {code} {state}')['ok']
 for code2 in reversed(modifiers):assert command(f'key {code2} 0')['ok']
def record():
 records=[line for line in (root/'hook.log').read_text().splitlines() if line.startswith('views-state ')]
 if not records:return None
 return dict(item.split('=',1) for item in records[-1].split()[1:])
def state():
 row=record()
 if row is None:return None
 return dict(value=bytes.fromhex(row['value_hex']).decode(),start=int(row['start']),end=int(row['end']),focused=int(row['focused']))
def wait(predicate):
 deadline=time.monotonic()+5
 while time.monotonic()<deadline:
  row=state()
  if row and predicate(row):return row
  time.sleep(.02)
 return state()
def check(case,expected):
 row=wait(lambda s:all(s[k]==v for k,v in expected.items()));passed=all(row[k]==v for k,v in expected.items())
 results.append(dict(case=case,passed=passed,state=row,expected=expected));(root/'views-results.json').write_text(json.dumps(results,indent=2)+'\n');assert passed,results[-1]
def reset():
 assert command('pointer 80 391')['ok'];assert command('button 272')['ok'];key(38,29)
 wait(lambda s:s['focused'] and s['start']==0 and s['end']>0)
 # A real pointer enter activates the browser's platform input context after
 # a native application has owned keyboard focus. Coordinates are grounded in
 # the retained screencopy of this fixed 900x700 fixture.
 assert command('pointer 220 60')['ok'];assert command('button 272')['ok']
 key(102)
 assert wait(lambda s:s['start']==s['end']==0)['end']==0
 key(107,42)
 row=wait(lambda s:s['start']==0 and s['end']==len(s['value'].encode('utf-16-le'))//2)
 assert row['start']==0 and row['end']==len(row['value'].encode('utf-16-le'))//2,row
 key(14)
 assert wait(lambda s:s['value']=='')['value']=='',state()
 prefix=''
 for c in 'Alpha beta':
  code={'a':30,'l':38,'p':25,'h':35,' ':57,'b':48,'e':18,'t':20}[c.lower()];key(code,*([42] if c.isupper() else []))
  prefix+=c
  assert wait(lambda s:s['value']==prefix and s['start']==s['end']==len(prefix))['value']==prefix,state()
 check('typed-real-address-model',dict(value='Alpha beta',start=10,end=10,focused=1))
 key(102)
 for i in range(3):key(106)
 check('native-caret-setup',dict(value='Alpha beta',start=3,end=3,focused=1))
deadline=time.monotonic()+20
owner=json.loads((root/'launch.json').read_text())['pids'][-1]
while True:
 windows=command('windows')
 window=next((w for w in windows if w['pid']==owner and w['presented'] and w['visible']),None)
 if window:break
 assert time.monotonic()<deadline,windows
 time.sleep(.02)
assert command(f"raise {window['id']}")['ok']
assert command(f"focus {window['id']}")['ok']
refs=json.loads((a.references/'results.json').read_text())
for expected in next(x for x in refs if x['id']=='normal')['keys']:
 reset();name=expected['key'];keycode={'a':30,'e':18,'b':48,'f':33,'d':32,'h':35,'k':37}.get(name.split('+')[-1],14 if name=='Backspace' else 111)
 key(keycode,*([29] if name.startswith('Control+') else []));check('native-'+name,{k:expected[k] for k in ['value','start','end']})
reset();key(102,42);check('copy-selection',dict(value='Alpha beta',start=0,end=3))
key(46,56);key(107);key(47,56);check('native-alt-copy-paste',dict(value='Alpha betaAlp',start=13,end=13))
reset();key(102,42);key(45,56);check('native-alt-cut',dict(value='ha beta',start=0,end=0))
key(47,56);check('native-alt-paste-after-cut',dict(value='Alpha beta',start=3,end=3))

# Copy from a real focused native application, publishing a Wayland selection.
# Writing unpublished GPBS storage alone does not set the system clipboard.
environment=dict(os.environ,**json.loads((root/'runtime.json').read_text()))
environment.pop('LD_PRELOAD',None)
clipboard_text='Native pasteboard: 日本語, 한글, UTF-8'
source=root/'native-clipboard.txt';source.write_text(clipboard_text)
reset();key(102);key(107,42)
with (root/'native-text-app.log').open('w') as log:
 native_app=subprocess.Popen([str(a.native_text_app),'-NSUseRunningCopy','NO','-GSBackend',a.backend,'-NSOpen',str(source)],
                             env=environment,stdout=log,stderr=log)
 try:
  deadline=time.monotonic()+15
  while True:
   assert native_app.poll() is None
   windows=command('windows')
   (root/'native-app-windows.json').write_text(json.dumps(windows,indent=2)+'\n')
   native_window=next((w for w in windows if w['pid']==native_app.pid and w['visible'] and w['presented'] and w['width']>200),None)
   if native_window:break
   assert time.monotonic()<deadline
   time.sleep(.02)
  assert command(f"raise {native_window['id']}")['ok']
  assert command(f"focus {native_window['id']}")['ok']
  key(30,56);key(46,56)
  deadline=time.monotonic()+5
  while True:
   copied=subprocess.check_output([str(a.pasteboard_probe),'--export-text'],env=environment,text=True)
   if copied==clipboard_text:break
   assert time.monotonic()<deadline,copied
   time.sleep(.02)
  assert command(f"raise {window['id']}")['ok']
  assert command(f"focus {window['id']}")['ok']
  assert command('pointer 220 60')['ok'];assert command('button 272')['ok']
  key(102);key(107,42)
  row=wait(lambda s:s['start']==0 and s['end']==len(s['value'].encode('utf-16-le'))//2)
  assert row['start']==0 and row['end']==len(row['value'].encode('utf-16-le'))//2,row
  key(47,56)
  length=len(clipboard_text.encode('utf-16-le'))//2
  check('native-application-to-browser-paste',dict(value=clipboard_text,start=length,end=length))
 finally:
  native_app.terminate()
  try:native_app.wait(timeout=5)
  except subprocess.TimeoutExpired:native_app.kill();native_app.wait()
  (root/'native-app-cleanup.json').write_text(json.dumps(dict(pid=native_app.pid,exit=native_app.returncode))+'\n')

# Stable selection avoids comparing two unrelated caret blink phases.
reset();key(102,42);check('native-image-selection',dict(value='Alpha beta',start=0,end=3))
def native_pixels(label):
 assert command('pointer 1200 500')['ok'] # Screencopy includes the real cursor.
 row=record()
 width,height=int(row['width']),int(row['height'])
 item=dict(id=label,kind=7,width=width,height=height,enabled=1,state=0,title='',text='Alpha beta',selection_start=0,selection_length=3)
 reference=Path(command('reference '+json.dumps(dict(controls=[item],name='references-'+label,focus=True)))['path'])/(label+'.png')
 expected=Image.open(reference).convert('RGBA');bg=Image.new('RGBA',expected.size,'white');bg.alpha_composite(expected);expected=bg.convert('RGB')
 deadline=time.monotonic()+5;match=None
 while time.monotonic()<deadline:
  frame=command('capture HEADLESS-1');event=frame['event']
  actual=Image.frombytes('RGB',(event['width'],event['height']),Path(frame['path']).read_bytes(),'raw','BGRX',event['stride'])
  if event['flags']&1:actual=actual.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
  # Source GetBoundsInScreen uses a fake Wayland global origin. Locate the
  # complete independent native image in the captured output instead.
  needle=expected.crop((0,0,width,1)).tobytes()
  for y in range(min(160,actual.height-height)):
   scan=actual.crop((0,y,actual.width,y+1)).tobytes();offset=scan.find(needle)
   while offset>=0:
    x=offset//3
    if offset%3==0 and actual.crop((x,y,x+width,y+height)).tobytes()==expected.tobytes():match=[x,y,width,height];break
    offset=scan.find(needle,offset+1)
   if match:break
  if match:break
  time.sleep(.02)
 actual.save(root/(label+'-desktop.png'))
 passed=match is not None
 results.append(dict(case='native-complete-pixels-'+label,passed=passed,match=match,native_size=[width,height]))
 (root/'views-results.json').write_text(json.dumps(results,indent=2)+'\n');assert passed,results[-1]
 actual.crop((match[0],match[1],match[0]+width,match[1]+height)).save(root/(label+'-actual.png'))
native_pixels('address-selected')
before_width=int(record()['width'])
assert command(f"resize {window['id']} {window['width']+132} 700")['ok']
try:
 deadline=time.monotonic()+5
 while int(record()['width'])==before_width:
  assert time.monotonic()<deadline,record()
  time.sleep(.02)
 native_pixels('address-resized')
finally:
 assert command(f"resize {window['id']} {window['width']} {window['height']}")['ok']
print(json.dumps(dict(passed=len(results))))
