"""A real native layout rejection must not route a list through a text getter."""
import json,time

def run(f):
 f.reset();f.focus('list');f.key_cell=0
 initial=f.pixels('list',True,label='failure-before');f.key_cell=initial['list_state']['key_cell']
 for label,width,multiple in [('single',181,False),('multiple',183,True),('single-again',185,False)]:
  arm=f.root/'reject-native-list-state.json';receipt=arm.with_suffix('.receipt.json');receipt.unlink(missing_ok=True)
  arm.write_text(json.dumps(dict(kind=13,operation=49)))
  actual=f.js('list.multiple='+json.dumps(multiple)+';list.style.width='+json.dumps(str(width)+'px')+';return list.offsetWidth')
  f.check(label+'-renderer-survives-native-layout-rejection',actual==width,actual=actual)
  f.check(label+'-real-native-state-request-was-rejected',f.wait(receipt.exists),receipt=json.loads(receipt.read_text()))
  reference=f.pixels('list',True,label='failure-recovered-'+label)
  clip=reference['scroll_geometry']['clip'];native=reference['list_state']
  actual=f.js('return {client:[list.clientLeft,list.clientTop,list.clientWidth,list.clientHeight],width:list.scrollWidth,height:list.scrollHeight}')
  f.check(label+'-recovered-DOM-viewport-matches-native',actual['client']==[clip[k] for k in ['x','y','width','height']] and actual['width']==native['content']['width'] and actual['height']==native['content']['height'],actual=actual,native=reference)
 f.js('list.selectedIndex=0;return true');time.sleep(.1);f.clear();f.key(108)
 f.check('recovered-list-keeps-native-navigation-and-original-trusted-events',f.selected()==[3] and [e['type'] for e in f.changes()]==['input','change'] and all(e['trusted'] for e in f.changes()),selected=f.selected(),events=f.changes())
