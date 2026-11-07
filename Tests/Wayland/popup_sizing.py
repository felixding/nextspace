"""Native cell metrics feed original browser layout; references come from public NativeUI."""
import json

def run(fixture,indent=''):
 js,check,wait,command=fixture.js,fixture.check,fixture.wait,fixture.command
 check('native-sizing-document',js('return document.title')=='Native select sizing')
 command('pointer 1500 1100')
 group=dict(selected=1,items=[dict(title='A long native group heading',enabled=0),dict(title=indent+'Short')])
 def model(identifier,override=None):
  value=js("const e=document.getElementById("+json.dumps(identifier)+");return {id:e.id,kind:6,title:'',state:0,width:1,height:1,enabled:!e.disabled,selected:e.selectedIndex,items:[...e.options].map(o=>({title:o.label,enabled:!o.disabled}))}")
  if override:value.update(override)
  return value
 def measure(identifier,label,override=None):
  data=model(identifier,override);data['preferred_size']=True
  result=command('reference '+json.dumps(dict(name=label+'-size-reference',controls=[data])))
  from pathlib import Path
  reference=json.loads((Path(result['path'])/'results.json').read_text())[0]
  return reference['size']
 def rectangle(identifier):
  return js('return document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
 def compare(identifier,label,override=None,expected=None):
  preferred=measure(identifier,label,override)
  if expected is None:expected=preferred
  def same():
   rect=rectangle(identifier);return rect['width']==expected[0] and rect['height']==expected[1]
  check(label+'-native-size',wait(same),preferred=preferred,expected=expected,actual=rectangle(identifier))
  fixture.pixels(identifier,False,override,label)
  return preferred
 for identifier in ['automatic','empty','disabled','unicode','borderbox']:
  compare(identifier,identifier)
 compare('grouped','grouped',group)
 compare('fixed','fixed',expected=[180,31])
 minimum=measure('minimum','minimum-probe');compare('minimum','minimum',expected=[max(300,minimum[0]),minimum[1]])
 maximum=measure('maximum','maximum-probe');compare('maximum','maximum',expected=[min(90,maximum[0]),maximum[1]])
 old=rectangle('automatic')['width']
 js("document.getElementById('automatic').options[1].text='A much longer native label after an application mutation';return true")
 compare('automatic','automatic-grown');check('native-label-growth-reflows-original-layout',rectangle('automatic')['width']>old)
 js("document.getElementById('automatic').options[1].firstChild.data='Changed text data';return true")
 compare('automatic','character-data-changed')
 js("document.getElementById('automatic').options[1].label='Changed option label attribute';return true")
 compare('automatic','option-label-changed')
 js("document.getElementById('automatic').options[1].hidden=true;return true")
 compare('automatic','long-option-hidden',dict(items=[dict(title='First')]))
 js("document.getElementById('automatic').options[1].hidden=false;return true")
 compare('automatic','long-option-restored')
 js("document.getElementById('automatic').options[1].remove();return true")
 compare('automatic','automatic-shrunk');check('native-option-removal-reflows-original-layout',rectangle('automatic')['width']<old)
 js("document.getElementById('automatic').add(new Option('An appended option changes the native preferred size','appended'));return true")
 compare('automatic','option-appended')
 js("document.getElementById('grouped').firstElementChild.label='An even longer group heading changes native preferred width';return true")
 group['items'][0]['title']='An even longer group heading changes native preferred width'
 compare('grouped','group-heading-grown',group)
 check('native-size-updates-emit-no-application-actions',js("return !events.some(e=>e.type==='input'||e.type==='change')"))
