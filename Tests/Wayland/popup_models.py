"""Common actual-seat option-model checks for the native browser bridges."""
import time

def run(fixture,indent='',collapse_hr=True):
 js,check,reset,command,pixels=fixture.js,fixture.check,fixture.reset,fixture.command,fixture.pixels
 focus,key,state,wait=fixture.focus,fixture.key,fixture.state,fixture.wait
 native_menu,model_geometry,image,highlight=fixture.native_menu,fixture.model_geometry,fixture.image,fixture.highlight
 reset();command('pointer 1500 1100')
 grouped=dict(selected=1,items=[dict(title='Group',enabled=0),dict(title=indent+'Repeated'),dict(title=indent+'Disabled option',enabled=0),dict(title=indent+'Repeated'),dict(title='',enabled=0,separator=1),dict(title='Last')])
 reference=pixels('grouped',True,grouped)
 focus('grouped');key(57);wait(lambda:state('grouped'),lambda x:x['open']);menu=wait(native_menu)
 frame=reference['native_menu_frame'];check('grouped-native-menu-geometry',model_geometry(reference),menu=menu,reference=frame);image('grouped-native-menu')
 key(108);key(28);s=state('grouped');check('disabled-option-keeps-native-menu-open',s['open'] and s['index']==0 and not s['changes'],actual=s)
 key(108);key(28);s=wait(lambda:state('grouped'),lambda x:not x['open']);check('grouped-row-maps-original-option-index',s['index']==2 and [x['type'] for x in s['changes']]==['input','change'] and all(x['trusted'] for x in s['changes']),actual=s)
 grouped['selected']=3;pixels('grouped',True,grouped,'grouped-selected')
 reset();js("document.getElementById('select').innerHTML='<option hidden selected value=hidden>Hidden chosen</option><optgroup label=Group disabled><option value=blocked>Blocked</option></optgroup><option value=visible>Visible</option>';window.events=[];return true")
 hidden=dict(selected=-1,popup_title='Hidden chosen',items=[dict(title='Group',enabled=0),dict(title=indent+'Blocked',enabled=0),dict(title='Visible')])
 reference=pixels('select',True,hidden,'hidden-selected');focus();key(57);wait(state,lambda x:x['open']);menu=wait(native_menu);frame=reference['native_menu_frame']
 check('hidden-choice-omitted-native-menu-geometry',model_geometry(reference),menu=menu,reference=frame);image('hidden-selected-native-menu')
 highlight(3,2);key(28);s=wait(state,lambda x:not x['open']);check('hidden-selection-commits-visible-original-option',s['value']=='visible' and s['index']==2 and [x['type'] for x in s['changes']]==['input','change'] and all(x['trusted'] for x in s['changes']),actual=s)
 hidden.update(selected=2,popup_title=None);pixels('select',True,hidden,'hidden-selection-replaced')
 js("const e=document.getElementById('select');e.selectedIndex=0;e.options[0].hidden=false;window.events=[];return true")
 shown=dict(selected=0,items=[dict(title='Hidden chosen'),*hidden['items']]);pixels('select',False,shown,'hidden-choice-shown')
 reset();js("document.getElementById('select').innerHTML='<option selected style=display:none>CSS hidden</option><optgroup label=Omitted style=display:none><option>Omitted child</option></optgroup><optgroup label=Hidden hidden><option>Hidden child</option></optgroup><hr><hr><option>Visible</option>';window.events=[];return true")
 css=dict(selected=-1,popup_title='CSS hidden',items=[dict(title='',separator=1,enabled=0)]*(1 if collapse_hr else 2)+[dict(title='Visible')]);reference=pixels('select',True,css,'css-hidden-groups');focus();key(57);wait(state,lambda x:x['open']);menu=wait(native_menu);frame=reference['native_menu_frame']
 check('hidden-groups-and-repeated-hr-native-menu-geometry',model_geometry(reference),menu=menu,reference=frame);image('css-hidden-groups-native-menu');key(1)
 reset();js("document.getElementById('select').innerHTML='<option hidden selected>Only hidden</option><optgroup label=Hidden hidden><option>Other hidden</option></optgroup>';window.events=[];return true")
 pixels('select',True,dict(selected=-1,popup_title='Only hidden',items=[]),'all-hidden');focus();key(57);time.sleep(.15)
 check('all-hidden-model-keeps-native-menu-closed',not state()['open'] and not native_menu() and not state()['changes'],actual=state())
 reset();focus('grouped');key(57);wait(lambda:state('grouped'),lambda x:x['open']);js("document.getElementById('grouped').firstElementChild.disabled=true;return true");highlight(6,3);key(28);s=wait(lambda:state('grouped'),lambda x:not x['open']);check('stale-disabled-model-cannot-commit',s['index']==0 and not s['changes'],actual=s)
 reset();focus('grouped');key(57);wait(lambda:state('grouped'),lambda x:x['open']);js("const e=document.getElementById('grouped'),o=new Option('Inserted hidden','hidden');o.hidden=true;e.prepend(o);return true");highlight(6,3);key(28);s=wait(lambda:state('grouped'),lambda x:not x['open']);check('hidden-insertion-invalidates-original-index-map',s['index']==1 and not s['changes'],actual=s)
 key(57);wait(lambda:state('grouped'),lambda x:x['open']);highlight(6,3);key(28);s=wait(lambda:state('grouped'),lambda x:not x['open']);check('updated-hidden-index-map-commits-on-next-menu',s['index']==3 and [x['type'] for x in s['changes']]==['input','change'] and all(x['trusted'] for x in s['changes']),actual=s)
