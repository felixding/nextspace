#!/usr/bin/env python3
"""Compare address-field pointer selection with direct NativeUI results.

Run inside the owned headless Views fixture at 100 percent scale. Held images
compare pixels outside the measured cursor overlay; released images compare
the complete field after moving the pointer away. Raw captures stay unchanged.
"""
import argparse,json,os,socket,subprocess,time
from pathlib import Path
from PIL import Image,ImageChops
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--fixture',type=Path,required=True)
p.add_argument('--library',type=Path,required=True)
p.add_argument('--backend',required=True)
p.add_argument('--click-counts',action='store_true',help='Compare double/triple click selection and dragging')
a=p.parse_args();root=a.fixture;results=[]
def command(text):
 with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as s:
  s.settimeout(15);s.connect(str(root/'control.sock'));s.send(json.dumps(dict(command=text)).encode());return json.loads(s.recv(65536))
def key(code,*mods):
 for mod in mods:assert command(f'key {mod} 1')['ok']
 for value in [1,0]:assert command(f'key {code} {value}')['ok']
 for mod in reversed(mods):assert command(f'key {mod} 0')['ok']
def record():
 lines=[x for x in (root/'hook.log').read_text().splitlines() if x.startswith('views-state ')]
 return dict(x.split('=',1) for x in lines[-1].split()[1:])
def state():
 row=record();return dict(value=bytes.fromhex(row['value_hex']).decode(),start=int(row['start']),end=int(row['end']))
def wait(expected):
 deadline=time.monotonic()+5
 while time.monotonic()<deadline:
  row=state()
  if all(row[k]==v for k,v in expected.items()):return row
  time.sleep(.02)
 return state()
def check(case,expected):
 row=wait(expected);passed=all(row[k]==v for k,v in expected.items());results.append(dict(case=case,passed=passed,state=row,expected=expected));(root/'pointer-results.json').write_text(json.dumps(results,indent=2)+'\n');assert passed,results[-1]
def prepare(shift=False):
 # Keep each requested gesture a single click: this interior focus click is
 # farther than Chromium's click aggregation threshold from every case start.
 # It also activates the real platform input context after an app switch.
 assert command('pointer 220 60')['ok'];assert command('button 272')['ok']
 key(102);wait(dict(start=0,end=0));key(107,42);row=state();wait(dict(start=0,end=len(row['value'].encode('utf-16-le'))//2));key(14);assert wait(dict(value=''))['value']==''
 prefix=''
 for c in ('Hello Hello' if a.click_counts else 'Hello'):
  key({'H':35,'e':18,'l':38,'o':24,' ':57}[c],*([42] if c=='H' else []));prefix+=c;assert wait(dict(value=prefix))['value']==prefix
 key(102);wait(dict(start=0,end=0))
 if shift:
  key(106);wait(dict(start=1,end=1));key(106,42);key(106,42);check('shift-seed',dict(value=prefix,start=1,end=3))
def capture():
 frame=command('capture HEADLESS-1');e=frame['event'];im=Image.frombytes('RGB',(e['width'],e['height']),Path(frame['path']).read_bytes(),'raw','BGRX',e['stride'])
 return im.transpose(Image.Transpose.FLIP_TOP_BOTTOM) if e['flags']&1 else im
def reference(spec,directory,pointers=False):
 env=dict(os.environ,**json.loads((root/'runtime.json').read_text()));env.pop('LD_PRELOAD',None)
 path=root/(directory+'.json');path.write_text(json.dumps([spec]));out=root/directory
 subprocess.run(['python3',str(Path(__file__).with_name('native-control-reference.py')),'--library',str(a.library),'--controls',str(path),'--output',str(out),'--focus',*(['--pointers'] if pointers else []),'-GSBackend',a.backend],env=env,check=True,timeout=20,stdout=(root/'pointer-references.log').open('a'),stderr=(root/'pointer-references.stderr').open('a'))
 return out
def rgb(path):
 im=Image.open(path).convert('RGBA');bg=Image.new('RGBA',im.size,'white');bg.alpha_composite(im);return bg.convert('RGB')
deadline=time.monotonic()+20
owner=json.loads((root/'launch.json').read_text())['pids'][-1]
while True:
 window=next((w for w in command('windows') if w['pid']==owner and w['presented'] and w['visible']),None)
 if window and (root/'hook.log').exists() and 'views-state ' in (root/'hook.log').read_text():break
 assert time.monotonic()<deadline
 time.sleep(.02)
assert command(f"raise {window['id']}")['ok'];assert command(f"focus {window['id']}")['ok']
assert command('pointer 220 60')['ok'];assert command('button 272')['ok']
prepare(True);assert command('pointer 1200 500')['ok'];row=record();w,h=int(row['width']),int(row['height'])
spec=dict(id='address',kind=7,width=w,height=h,enabled=1,state=0,title='',text='Hello Hello' if a.click_counts else 'Hello',selection_start=1,selection_length=2)
location=reference(spec,'pointer-references');expected=rgb(location/'address.png');im=capture();match=None
for y in range(160):
 scan=im.crop((0,y,im.width,y+1)).tobytes();needle=expected.crop((0,0,w,1)).tobytes();offset=scan.find(needle)
 while offset>=0:
  x=offset//3
  if offset%3==0 and im.crop((x,y,x+w,y+h)).tobytes()==expected.tobytes():match=[x,y,w,h];break
  offset=scan.find(needle,offset+1)
 if match:break
im.save(root/'pointer-before.png');assert match,dict(width=w,height=h)
(root/'pointer-field.json').write_text(json.dumps(match)+'\n')
cases=[dict(name=name,x=x,end_x=end,modifiers=mods) for name,x,end,mods in [('left',3,3,0),('near',10,10,0),('middle',25,25,0),('right',175,175,0),('forward',3,25,0),('reverse',30,3,0),('outside-right',3,w+50,0),('outside-left',30,-20,0),('shift-left',3,3,1),('shift-right',30,30,1)]]
if a.click_counts:
 cases=[dict(name=name,x=x,end_x=end,click_count=clicks) for name,x,end,clicks in
  [('word',25,25,2),('line',25,25,3),('word-forward',25,70,2),('word-reverse',70,25,2),
   ('line-forward',25,100,3),('line-reverse',70,3,3)]]
spec['pointer_cases']=cases;location=reference(spec,'pointer-references',True)
refs=json.loads((location/'results.json').read_text())[0]['pointers']
def pixels(case,phase):
 expected=rgb(location/('address-pointer-'+case['name']+'.png'));deadline=time.monotonic()+5;difference=True
 cursor=command('cursor-state') if phase=='held' else None;occluded=None
 if cursor and cursor['visible']:
  x=round(cursor['x']-cursor['hotspot_x'])-match[0];y=round(cursor['y']-cursor['hotspot_y'])-match[1]
  box=[max(0,x),max(0,y),min(w,x+cursor['width']),min(h,y+cursor['height'])]
  if box[0]<box[2] and box[1]<box[3]:occluded=box
 while difference is not None and time.monotonic()<deadline:
  actual=capture();crop=actual.crop((match[0],match[1],match[0]+w,match[1]+h));delta=ImageChops.difference(crop,expected)
  unmasked_difference=delta.getbbox()
  if occluded:delta.paste((0,0,0),tuple(occluded))
  difference=delta.getbbox()
  if difference is not None:time.sleep(.02)
 results.append(dict(case=phase+'-pixels-'+case['name'],passed=difference is None,difference=difference,unmasked_difference=unmasked_difference,cursor=cursor,cursor_occlusion=occluded,complete_field_compared=occluded is None));crop.save(root/(phase+'-pointer-'+case['name']+'.png'));(root/'pointer-results.json').write_text(json.dumps(results,indent=2)+'\n');assert difference is None,results[-1]
def native_presses():
 rows=[json.loads(line) for line in (root/'helper.jsonl').read_text().splitlines()]
 owner=next(row for row in rows if row.get('event')=='native-form-control' and row.get('kind')==7 and row.get('width',0)>400)
 return [row for row in rows if row.get('event')=='native-form-press' and row.get('process')==owner['process'] and row.get('control')==owner['control']]
for case in refs:
 prepare(bool(case['modifiers']))
 if case['modifiers']:assert command('key 42 1')['ok']
 before_presses=len(native_presses())
 for prior in range(1,case.get('click_count',1)):
  assert command(f"pointer {match[0]+case['x']} {match[1]+12}")['ok'];assert command('button 272')['ok']
 assert command(f"pointer {match[0]+case['x']} {match[1]+12}")['ok'];assert command('button 272 1')['ok']
 try:
  deadline=time.monotonic()+5
  while len(native_presses())<before_presses+case.get('click_count',1):
   assert time.monotonic()<deadline,dict(case=case['name'],reason='The single-click native gesture was not entered')
   time.sleep(.02)
  press=native_presses()[-1];passed=press['x']==case['x'] and press['y']==12 and press.get('click_count',1)==case.get('click_count',1)
  results.append(dict(case='native-tracking-'+case['name'],passed=passed,press=press));assert passed,results[-1]
  if case['x']!=case['end_x']:assert command(f"pointer {match[0]+case['end_x']} {match[1]+12}")['ok']
  check('held-'+case['name'],{k:case[k] for k in ['value','start','end']})
  if case['start']!=case['end']:pixels(case,'held')
 finally:
  assert command('button 272 0')['ok']
  if case['modifiers']:assert command('key 42 0')['ok']
 check('released-'+case['name'],{k:case[k] for k in ['value','start','end']})
 if case['start']!=case['end']:
  assert command('pointer 1200 500')['ok'];pixels(case,'released')
if a.click_counts:
 print(json.dumps(dict(passed=len(results))));raise SystemExit(0)
# The native range must govern the next real application edit.
prepare();assert command(f"pointer {match[0]+3} {match[1]+12}")['ok'];assert command('button 272 1')['ok']
assert command(f"pointer {match[0]+25} {match[1]+12}")['ok']
check('held-before-typing',dict(value='Hello',start=0,end=3))
assert command('button 272 0')['ok'];key(45,42)
check('typing-replaces-native-range',dict(value='Xlo',start=1,end=1))

# Changing application geometry while AppKit owns mouseDown must end that old
# native gesture, preserve the application range and permit normal editing.
prepare();assert command(f"pointer {match[0]+30} {match[1]+12}")['ok'];assert command('button 272 1')['ok']
assert command(f"pointer {match[0]+3} {match[1]+12}")['ok']
check('held-before-resize',dict(value='Hello',start=0,end=4))
old_width=int(record()['width'])
assert command(f"resize {window['id']} {window['width']+100} {window['height']}")['ok']
try:
 deadline=time.monotonic()+5
 while int(record()['width'])==old_width:
  assert time.monotonic()<deadline,record()
  time.sleep(.02)
 check('resize-keeps-application-range',dict(value='Hello',start=0,end=4))
 assert command('button 272 0')['ok'];key(45,42)
 check('typing-after-held-resize',dict(value='Xo',start=1,end=1))
finally:
 assert command('button 272 0')['ok']
 assert command(f"resize {window['id']} {window['width']} {window['height']}")['ok']
print(json.dumps(dict(passed=len(results))))
