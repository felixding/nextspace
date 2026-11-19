import argparse
from pathlib import Path
import json,sys,time
sys.path.insert(0,'/workspace/Tests/Wayland')
from native_density_controls import DensityFixture
parser=argparse.ArgumentParser(description='Original file-button pixels survive zoom and native chooser cancellation.')
parser.add_argument('root');parser.add_argument('--port',type=int,default=9293);parser.add_argument('--scale',type=float,default=2)
args=parser.parse_args();f=DensityFixture(args.root,'chromium',args.port,args.scale,report='file-button-checks.json')
f.js('file.multiple=true');f.cdp('Browser.setWindowBounds',dict(windowId=f.browser_window_id,bounds=dict(width=500,height=500)))
root=f.cdp('DOM.getDocument',dict(depth=-1,pierce=True))['root']
def walk(n):
 yield n
 for k in ('children','shadowRoots'):
  for c in n.get(k,[]):yield from walk(c)
file=next(n for n in walk(root) if dict(zip(n.get('attributes',[])[::2],n.get('attributes',[])[1::2])).get('id')=='file')
b=next(n for n in walk(file) if dict(zip(n.get('attributes',[])[::2],n.get('attributes',[])[1::2])).get('type')=='button')
o=f.cdp('DOM.resolveNode',dict(backendNodeId=b['backendNodeId']))['object']['objectId']
def state():
 return f.cdp('Runtime.callFunctionOn',dict(objectId=o,functionDeclaration='function(){return {rect:this.getBoundingClientRect().toJSON(),value:this.value,appearance:getComputedStyle(this).appearance}}',returnByValue=True))['result']['value']
def pixels(label):
 def part():
  q=state()['rect'];a=f.js('file.getBoundingClientRect().toJSON()')
  return dict(x=q['x']-a['x'],y=q['y']-a['y'],width=q['width'],height=q['height'])
 f.js('file.scrollIntoView({block:"center"})');v=state()
 f.pixels('file',dict(kind=1,title=v['value']),part=part,label=label,keep_cursor=True,preserve_focus=True,reference_focus=f.js('document.activeElement===file'))
pixels('file-before-focus')
before=f.js('devicePixelRatio')
for code,key_state in [(56,1),(42,1),(13,1),(13,0),(42,0),(56,0)]:assert f.command(f'key {code} {key_state}')['ok']
f.until(lambda:f.js('devicePixelRatio')>before,'original browser zoom increases')
f.chord(12,56);f.until(lambda:f.js('devicePixelRatio')==before,'original browser zoom restored')
f.js('file.scrollIntoView({block:"center"})');a=f.js('file.getBoundingClientRect().toJSON()');f.point(a,20,a['height']/2);f.button(1);f.button(0)
p=f.until(lambda:next((w for w in f.command('windows') if w['visible'] and w['title'].startswith('Open')),None),'native file panel opens')
from PIL import Image
shot=f.command('capture '+f.command('outputs')[0]['name']);e=shot['event']
Image.frombytes('RGB',(e['width'],e['height']),Path(shot['path']).read_bytes(),'raw','BGRX',e['stride']).save(f.root/'file-panel-before-cancel.png')
assert f.command('pointer %d %d'%(p['x']+p['width']-125,p['y']+p['height']-30))['ok'];f.button(1);f.button(0)
f.until(lambda:not any(w['visible'] and w['title'].startswith('Open') for w in f.command('windows')),'native file cancellation')
pixels('file-after-cancel-and-zoom')
f.check('native-chooser-cancel-preserves-original-file-input',f.js('file.type==="file"&&file.files.length===0'))
f.js('document.head.insertAdjacentHTML("beforeend",\'<style id="file-author-style">#file::file-selector-button{appearance:none;background:rgb(255,255,0);color:rgb(0,0,255);border:2px solid rgb(0,0,255);font:16px serif}</style>\')')
f.check('author-appearance-none-remains-owned-by-original-engine',state()['appearance']=='none')
deadline=time.monotonic()+10
while True:
 f.update_origin();q=state()['rect'];shot=f.command('capture '+f.command('outputs')[0]['name']);e=shot['event']
 im=Image.frombytes('RGB',(e['width'],e['height']),Path(shot['path']).read_bytes(),'raw','BGRX',e['stride'])
 x,y=round(f.origin_pixels[0]+q['x']*f.scale),round(f.origin_pixels[1]+q['y']*f.scale)
 im=im.crop((x,y,x+round(q['width']*f.scale),y+round(q['height']*f.scale)))
 colors=list(im.getdata());visible=sum(r>220 and g>220 and b<40 for r,g,b in colors)>10 and sum(b>180 and r<60 and g<60 for r,g,b in colors)>10
 if visible or time.monotonic()>deadline:break
 time.sleep(.05)
im.save(f.root/'file-author-style.png');f.check('original-author-button-pixels-are-visible',visible)
f.js('document.getElementById("file-author-style").remove()');pixels('file-native-appearance-restored')
print('File button retains original native pixels and author CSS fallback',flush=True)
