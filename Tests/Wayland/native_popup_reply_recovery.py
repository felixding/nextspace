"""A missing configuration reply must not retire a live original picker."""
import argparse,json,time
from pathlib import Path
from PIL import Image
from native_density_controls import DensityFixture

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('root',type=Path)
p.add_argument('--family',choices=('chromium','firefox'),required=True)
p.add_argument('--port',type=int,required=True)
a=p.parse_args()
fixture=DensityFixture(a.root,a.family,a.port,2,report='popup-reply-recovery.json')

def panel():
    return next((w for w in fixture.command('windows') if w['visible'] and w['title']=='Date and Time'),None)

def capture(name):
    shot=fixture.command('capture '+fixture.command('outputs')[0]['name']);e=shot['event']
    Image.frombytes('RGB',(e['width'],e['height']),Path(shot['path']).read_bytes(),'raw','BGRX',e['stride']).save(a.root/(name+'.png'))

def open_panel():
    box=fixture.js('nxsPickerOpen.getBoundingClientRect().toJSON()')
    fixture.point(box,box['width']/2,box['height']/2)
    fixture.button(1);fixture.button(0)
    fixture.until(lambda:panel() and panel()['focused'],'native calendar focus')

try:
    fixture.pixels('date',dict(kind=17,date_flags=20,date_elements=2,date_style=0,date_value=1794268800))
    fixture.js('(()=>{const b=document.createElement("button");b.id="nxsPickerOpen";b.textContent="Calendar";b.style="position:fixed;right:8px;top:8px";b.onclick=()=>date.showPicker();document.body.append(b)})()')
    open_panel();capture('popup-before-lost-configuration')
    fixture.check('native-calendar-starts-open',bool(panel()))
    marker=a.root/'withhold-calendar-configuration-replies';marker.touch()
    fixture.until(lambda:'test-native-calendar-configuration-reply-withheld' in (a.root/'helper.jsonl').read_text(),'configuration reply deliberately withheld')
    time.sleep(6)
    marker.unlink()
    capture('popup-after-lost-configuration')
    fixture.check('lost-configuration-keeps-original-panel-open',bool(panel()))
    fixture.key(28)
    fixture.check('Return-closes-after-lost-configuration',fixture.until(lambda:not panel(),'native Return closes recovered calendar'))
    open_panel()
    fixture.check('same-source-reopens-original-calendar',bool(panel()))
    fixture.key(1)
    fixture.check('Escape-closes-reopened-calendar',fixture.until(lambda:not panel(),'native Escape closes recovered calendar'))
    rows=[json.loads(l) for l in (a.root/'helper.jsonl').read_text().splitlines()]
    fixture.check('fault-used-real-native-configuration-reply',any(r.get('event')=='test-native-calendar-configuration-reply-withheld' for r in rows))
finally:
    if fixture.family=='firefox':fixture.driver.close()
