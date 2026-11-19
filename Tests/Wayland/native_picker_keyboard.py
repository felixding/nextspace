#!/usr/bin/env python3
"""Repeated inactive-window picker activation through ordinary desktop input."""
import json,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from desktop_input import Desktop
root=Path(sys.argv[1]);desktop=Desktop(root);command=desktop.command;rows=[]
def until(read,predicate,label,end=None):
 if end is None:end=time.monotonic()+12
 while True:
  value=read()
  if predicate(value):return value
  assert time.monotonic()<end,(label,value)
  time.sleep(.05)
def panel(title):return next((w for w in command('windows') if w['visible'] and w['title']==title),None)
for app,x in [('firefox-esr',0),('chromium-browser',900)]:
 w=next(w for w in command('windows') if w['app_id']==app and w['level']==0)
 assert command('move %d %d 24'%(w['id'],x))['ok']
# Finish the initial fixture arrangement before exercising real input.
# Capturing the moved desktop neither activates a client nor changes focus.
desktop.capture('repeated-keyboard-arranged')
targets=json.loads((root/'ordinary-control-targets.json').read_text())
try:
 for app,x,y,other in [('firefox-esr',525,490,1200),('chromium-browser',1420,475,300)]:
  family='firefox' if app=='firefox-esr' else 'chromium'
  x,y=targets[family]['color']
  for title,px in [('Colors',x),('Date and Time',245 if app=='firefox-esr' else 1155)]:
   for i in range(8):
    desktop.click(other,254)
    assert command('pointer %d %d'%(px,y))['ok'];assert command('button 272 1')['ok'];time.sleep(.08)
    assert command('pointer %d %d'%(px,y+48))['ok'];assert command('button 272 0')['ok'];time.sleep(.2)
    assert not panel(title),'cancelled pointer gesture opened panel'
    main=next(w for w in command('windows') if w['app_id']==app and w['level']==0)
    assert main['focused'],'physical pointer gesture did not focus its browser'
    started=time.monotonic();desktop.key(57)
    # Fresh native parent import and focus are separate Wayland commits.
    # Both must finish inside the original single interaction deadline.
    w=until(lambda:panel(title),lambda w:w and w['focused'] and w['parent_id']==main['id'],
            app+title+' keyboard focus and parent',started+12)
    time.sleep(.4);w=panel(title);assert w and w['focused'],('panel lost focus',w)
    main=next(w for w in command('windows') if w['app_id']==app and w['level']==0)
    assert w['parent_id']==main['id'],('panel parent',w,main)
    until(lambda:[w for w in command('windows') if w['visible'] and w['level']==20],
      lambda menus:len(menus)==1 and menus[0]['title']==('firefox-esr' if app=='firefox-esr' else 'Chromium'),'owning app menu')
    rows.append(dict(app=app,title=title,iteration=i,passed=True,open_seconds=time.monotonic()-started))
    if i==7:desktop.capture(app+'-'+title.replace(' ','-')+'-repeated-keyboard')
    if title=='Colors':desktop.click(w['x']+w['width']-11,w['y']+11)
    else:desktop.key(28)
    until(lambda:panel(title),lambda p:not p,title+' closes')
    (root/'repeated-picker-keyboard.json').write_text(json.dumps(dict(complete=False,checks=rows),indent=2)+'\n')
 (root/'repeated-picker-keyboard.json').write_text(json.dumps(dict(complete=True,checks=rows),indent=2)+'\n')
 print(json.dumps(dict(complete=True,checks=len(rows))))
except BaseException as e:
 windows=command('windows')
 (root/'repeated-picker-keyboard-failure-windows.json').write_text(json.dumps(windows,indent=2)+'\n')
 desktop.capture('repeated-picker-keyboard-failure')
 (root/'repeated-picker-keyboard.json').write_text(json.dumps(dict(complete=False,checks=rows,error=repr(e)),indent=2)+'\n')
 # Diagnose the actual visible auxiliary host before the launcher tears it
 # down. Browser and panel focus are separate native clients.
 try:
  host=next(w['pid'] for w in windows if w['visible'] and w['title'] in ('Colors','Date and Time'))
  queries=['set pagination off','thread apply all bt','set $nxs_app=*(void **)&NSApp',
   'set $nxs_sel=(void *)sel_registerName("keyWindow")',
   'set $nxs_imp=(void *)objc_msg_lookup($nxs_app,$nxs_sel)',
   'set $nxs_window=((void*(*)(void*,void*))$nxs_imp)($nxs_app,$nxs_sel)',
   'p $nxs_window','set $nxs_sel=(void *)sel_registerName("firstResponder")',
   'set $nxs_imp=(void *)objc_msg_lookup($nxs_window,$nxs_sel)',
   'set $nxs_responder=((void*(*)(void*,void*))$nxs_imp)($nxs_window,$nxs_sel)',
   'p (char *)class_getName((void *)object_getClass($nxs_responder))','detach']
  trace=subprocess.run(['sudo','-n','gdb','-q','-batch','-p',str(host),
    *[arg for query in queries for arg in ('-ex',query)]],capture_output=True,text=True,timeout=10)
  (root/'repeated-picker-keyboard-failure-native-stack.txt').write_text(trace.stdout+trace.stderr)
  hook=(root/'firefox-hook.log').read_text().splitlines()
  source=next(int(line.split()[0]) for line in reversed(hook) if 'native calendar panel opened' in line)
  trace=subprocess.run(['sudo','-n','gdb','-q','-batch','-p',str(source),
    '-ex','set pagination off','-ex','thread apply all bt','-ex','detach'],
    capture_output=True,text=True,timeout=10)
  (root/'repeated-picker-keyboard-failure-source-stack.txt').write_text(trace.stdout+trace.stderr)
 except Exception as diagnostic:
  (root/'repeated-picker-keyboard-failure-diagnostic.txt').write_text(repr(diagnostic)+'\n')
 raise
