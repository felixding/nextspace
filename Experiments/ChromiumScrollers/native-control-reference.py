#!/usr/bin/env python3
"""Render references directly through NativeUI's public ABI, without Chromium."""
import argparse
import ctypes as C
import json
import math
from pathlib import Path
from PIL import Image
from helper import Bitmap, Pump, Response
from native_controls import NativeControlServer, ControlConfig, ControlChanged, KeyEvent, PopupItem,TextModel,TextState,TextGeometry,WheelEvent,TextShouldChange,RadioItem,ListItem

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--library', type=Path, required=True)
parser.add_argument('--controls', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--focus', action='store_true', help='Use the real first-responder state for enabled controls')
parser.add_argument('--keys', action='store_true', help='Record actual native slider key results')
parser.add_argument('--pointers', action='store_true', help='Record native text hit testing and selection tracking')
parser.add_argument('--click-counts',action='store_true',help='Include native word/line click and drag references')
args, _ = parser.parse_known_args()
args.output.mkdir(parents=True, exist_ok=True)
native = C.CDLL(str(args.library))
# Reuse only the C ABI declarations; no helper transport or browser participates.
api = NativeControlServer(native, Bitmap, Response, Pump, lambda _: None, [],
                          lambda *_: None, lambda: True, lambda *_, **__: None)
results = []
for item in json.loads(args.controls.read_text()):
    def save_image(suffix=''):
        image = native.nxs_control_draw(pointer, 1)
        assert image.pixels and image.stride == image.width * 4
        pixels = C.string_at(image.pixels, image.stride * image.height)
        rendered=Image.frombytes('RGBA', (image.width, image.height), pixels, 'raw', 'BGRA')
        if item['kind']==12:
            rect=native.nxs_control_radio_item_rect(pointer,item['member'])
            rendered=rendered.crop((round(rect.x),round(rect.y),round(rect.x+rect.width),round(rect.y+rect.height)))
        rendered.save(args.output / (item['id'] + suffix + '.png'))
        return image
    def release(_):
        if pointer_case is not None:
            current=TextState(size=C.sizeof(TextState))
            assert native.nxs_control_text_get(pointer,None,0,C.byref(current))
            selected=(current.selection_start,current.selection_length)
            if not pointer_case['pumped']:
                pointer_case['pumped']=True;pointer_case['initial']=selected
                native.nxs_control_send(pointer,0 if pointer_case['drag'] else 1,
                    pointer_case['end'],12,pointer_case['modifiers'])
            # Word/line dragging may keep the initial range. Release on the
            # next native event-pump pass even when that range did not change.
            elif not pointer_case['drag'] or selected!=pointer_case['initial'] or pointer_case['clicks']>1:
                native.nxs_control_send(pointer,1,pointer_case['end'],12,pointer_case['modifiers'])
            return
        save_image('-pressed')
        native.nxs_control_send(pointer, 1, config.width / 2, config.height / 2, 0)
    pointer_case=None
    pump = Pump(release)
    pointer = native.nxs_control_create(item['kind'], ControlChanged(), pump, None)
    assert pointer
    try:
        title = item['title'].encode('utf-8')
        config = ControlConfig(C.sizeof(ControlConfig), item['width'], item['height'],
                               item.get('minimum',0), item.get('maximum',1), item.get('value',item['state']),
                               item['enabled'], item['state'], item.get('indeterminate',0), title)
        assert native.nxs_control_sync(pointer, C.byref(config))
        if item['kind']==12:
            entries=(RadioItem*len(item['items']))(*[RadioItem(C.sizeof(RadioItem),entry['id'],b'',entry['enabled']) for entry in item['items']])
            assert native.nxs_control_radio_items(pointer,entries,len(entries),1,item['selected'],item['key_cell'])
            assert native.nxs_control_radio_cell_size(pointer,item['width'],item['height'])
        if item['kind']==13:
            model=item['items'];titles=[entry['title'].encode('utf-8') for entry in model]
            entries=(ListItem*len(model))(*[ListItem(C.sizeof(ListItem),entry['id'],title,
                entry.get('enabled',1),entry.get('selected',0)) for entry,title in zip(model,titles)])
            assert native.nxs_control_list_items(pointer,entries,len(model),item.get('flags',0),item.get('key_cell',0))
        if item.get('preferred_size') and item['kind']!=6:
            preferred = native.nxs_control_size(pointer)
            config.width, config.height = math.ceil(preferred.width), math.ceil(preferred.height)
            assert native.nxs_control_sync(pointer, C.byref(config))
        if item['kind']==6:
            model=item['items'];titles=[entry['title'].encode('utf-8') for entry in model]
            entries=(PopupItem*len(model))(*[PopupItem(C.sizeof(PopupItem),title,
                entry.get('enabled',1),entry.get('separator',0)) for entry,title in zip(model,titles)])
            assert native.nxs_control_popup_items(pointer,entries,len(model),item['selected'])
            if 'popup_title' in item:
                assert api.popup_title_capabilities
                value=item['popup_title']
                assert native.nxs_control_popup_title(pointer,None if value is None else value.encode('utf-8'))
            if item.get('preferred_size'):
                preferred=native.nxs_control_size(pointer)
                config.width,config.height=math.ceil(preferred.width),math.ceil(preferred.height)
                config.value=native.nxs_control_state(pointer).value
                assert native.nxs_control_sync(pointer,C.byref(config))
        if 'step' in item:
            assert api.range_capabilities and native.nxs_control_set_step(pointer,item['step'])
        if args.focus and item['enabled'] and item['kind'] != 5:
            assert api.input_capabilities & 1
            assert native.nxs_control_focus(pointer, 1)
        if item['kind'] in (7,8,9):
            model=TextModel(C.sizeof(TextModel),item['text'].encode(),
                item.get('selection_start',1) if args.focus and item['enabled'] else item.get('selection_start',0),
                item.get('selection_length',2) if args.focus and item['enabled'] else item.get('selection_length',0),item.get('editable',1))
            assert native.nxs_control_text_sync(pointer,C.byref(model))
        if item['kind']==9 and 'scroll' in item:
            assert native.nxs_control_text_scroll(pointer,*item['scroll'])
        if item['kind']==13 and 'scroll' in item:
            assert native.nxs_control_list_scroll(pointer,*item['scroll'])
        list_keys=[]
        for entry in item.get('list_keys',[]):
            assert item['kind']==13
            event=KeyEvent(C.sizeof(KeyEvent),entry.get('type',0),entry.get('modifiers',0),entry.get('key',0),
                entry.get('repeat',0),entry.get('text','').encode(),entry.get('unmodified',entry.get('text','')).encode())
            handled=native.nxs_control_key(pointer,C.byref(event));state=native.nxs_control_list_state(pointer)
            selection=(C.c_uint64*state.selected_count)()
            assert native.nxs_control_list_selection(pointer,selection,len(selection))==len(selection)
            list_keys.append(dict(handled=handled,selected=list(selection),primary=state.primary,key_cell=state.key_cell,actions=state.actions))
        if item.get('click'):
            native.nxs_control_track(pointer,*item['click'],0)
        if item.get('wheel'):
            for entry in item['wheel']:
                event=WheelEvent(C.sizeof(WheelEvent),entry.get('modifiers',0),entry.get('x',40),entry.get('y',12),entry.get('dx',0),entry.get('dy',0))
                assert native.nxs_control_wheel(pointer,C.byref(event))
        text_keys=[]
        veto=TextShouldChange(lambda *_:0) if item.get('text_veto') else None
        if veto:assert native.nxs_control_text_filter(pointer,veto,None)
        for entry in item.get('text_keys',[]):
            event=KeyEvent(C.sizeof(KeyEvent),0,entry.get('modifiers',0),entry.get('key',0),
                entry.get('repeat',0),entry.get('text','').encode(),entry.get('unmodified',entry.get('text','')).encode())
            handled=native.nxs_control_key(pointer,C.byref(event))
            state=TextState(size=C.sizeof(TextState))
            required=native.nxs_control_text_get(pointer,None,0,C.byref(state));assert required
            buffer=C.create_string_buffer(required)
            assert native.nxs_control_text_get(pointer,buffer,required,C.byref(state))==required
            viewport=native.nxs_control_text_viewport(pointer)
            observed=buffer.value.decode()
            record=dict(handled=handled,start=state.selection_start,
                end=state.selection_start+state.selection_length,top=viewport.visible.y,left=viewport.visible.x)
            # Do not repeat a long unchanged document for every arrow key in
            # the fixture's bounded control-socket reply.
            if not text_keys or observed!=previous_text:record['value']=observed
            text_keys.append(record);previous_text=observed
        if item.get('blur_after_keys'):assert native.nxs_control_focus(pointer,0)
        image = save_image()
        preferred = native.nxs_control_size(pointer)
        results.append(dict(id=item['id'], size=[image.width, image.height],
                            preferred=[preferred.width, preferred.height]))
        if text_keys:results[-1]['text_keys']=text_keys
        if item['kind']==13:
            state=native.nxs_control_list_state(pointer);selection=(C.c_uint64*state.selected_count)()
            assert native.nxs_control_list_selection(pointer,selection,len(selection))==len(selection)
            results[-1]['list_state']=dict(selected=list(selection),primary=state.primary,key_cell=state.key_cell,actions=state.actions,
                visible={key:getattr(state.visible,key) for key in ('x','y','width','height')},
                content=dict(width=state.content[0],height=state.content[1]))
            if api.scroll_capabilities&1:
                geometry=TextGeometry(size=C.sizeof(TextGeometry))
                assert native.nxs_control_scroll_geometry(pointer,C.byref(geometry))
                results[-1]['scroll_geometry']={key:{axis:getattr(getattr(geometry,key),axis) for axis in axes}
                    for key,axes in [('clip',('x','y','width','height')),('client',('width','height')),('minimum',('x','y')),('maximum',('x','y'))]}
            rectangles=[]
            for entry in item['items']:
                rect=native.nxs_control_list_item_rect(pointer,entry['id'])
                rectangles.append({key:getattr(rect,key) for key in ('x','y','width','height')})
            results[-1]['native_item_rects']=rectangles
            if list_keys:results[-1]['list_keys']=list_keys
        if item['kind']==9:
            viewport=native.nxs_control_text_viewport(pointer)
            geometry=TextGeometry(size=C.sizeof(TextGeometry))
            assert native.nxs_control_text_geometry(pointer,C.byref(geometry))
            results[-1]['viewport']={key:getattr(viewport.visible,key) for key in ('x','y','width','height')}
            results[-1]['content']={key:getattr(viewport.content,key) for key in ('width','height')}
            results[-1]['clip']={key:getattr(geometry.clip,key) for key in ('x','y','width','height')}
            results[-1]['maximum']={key:getattr(geometry.maximum,key) for key in ('x','y')}
        if item['kind']==6 and item['enabled'] and item['items']:
            assert native.nxs_control_set_screen_origin(pointer,240,160)
            assert native.nxs_control_popup_open(pointer,1)
            native.nxs_native_ui_dispatch_events(0)
            rectangles=[]
            for index in range(len(item['items'])):
                rect=native.nxs_control_popup_item_rect(pointer,index)
                rectangles.append({key:getattr(rect,key) for key in ('x','y','width','height')})
            results[-1]['native_item_rects']=rectangles
            frame=native.nxs_control_popup_state(pointer).frame
            results[-1]['native_menu_frame']={key:getattr(frame,key) for key in ('x','y','width','height')}
            assert native.nxs_control_popup_open(pointer,0)
        if item['enabled'] and item['kind'] not in (5,6,7,8,9,12,13):
            native.nxs_control_track(pointer, config.width / 2, config.height / 2, 0)
        if args.keys and item['enabled'] and item['kind']==4:
            assert native.nxs_control_sync(pointer,C.byref(config))
            assert native.nxs_control_focused(pointer) or native.nxs_control_focus(pointer,1)
            values=[]
            for name,key in [('ArrowRight',7),('Home',10),('End',11),('PageDown',13)]:
                event=KeyEvent(C.sizeof(KeyEvent),0,0,key,0,b'',b'')
                native.nxs_control_key(pointer,C.byref(event))
                values.append(dict(key=name,value=native.nxs_control_state(pointer).value))
            results[-1]['keys']=values
        if args.keys and item['enabled'] and item['kind'] in (7,8) and item.get('editable',1):
            assert native.nxs_control_focused(pointer) or native.nxs_control_focus(pointer,1)
            values=[]
            for name,key,text,modifiers in [('Control+a',0,b'a',4),('Control+e',0,b'e',4),
                ('Control+b',0,b'b',4),('Control+f',0,b'f',4),('Backspace',3,b'',0),
                ('Delete',4,b'',0),('Control+d',0,b'd',4),('Control+h',0,b'h',4),('Control+k',0,b'k',4)]:
                model=TextModel(C.sizeof(TextModel),b'Alpha beta',3,0,1)
                assert native.nxs_control_text_sync(pointer,C.byref(model))
                event=KeyEvent(C.sizeof(KeyEvent),0,modifiers,key,0,text,text)
                native.nxs_control_key(pointer,C.byref(event))
                state=TextState(size=C.sizeof(TextState));buffer=C.create_string_buffer(256)
                assert native.nxs_control_text_get(pointer,buffer,len(buffer),C.byref(state))
                values.append(dict(key=name,value=buffer.value.decode(),start=state.selection_start,
                    end=state.selection_start+state.selection_length))
            results[-1]['keys']=values
            model=TextModel(C.sizeof(TextModel),b'Hello',1,2,1)
            assert native.nxs_control_text_sync(pointer,C.byref(model))
            for key,text in [(1,b''),(0,b'X')]:
                event=KeyEvent(C.sizeof(KeyEvent),0,0,key,0,text,text)
                native.nxs_control_key(pointer,C.byref(event))
            state=TextState(size=C.sizeof(TextState));buffer=C.create_string_buffer(256)
            assert native.nxs_control_text_get(pointer,buffer,len(buffer),C.byref(state))
            results[-1]['return_sequence']=dict(value=buffer.value.decode(),start=state.selection_start,
                end=state.selection_start+state.selection_length)
        if args.pointers and item['enabled'] and item['kind'] in (7,8):
            assert native.nxs_control_focused(pointer) or native.nxs_control_focus(pointer,1),item['id']
            values=[]
            cases=[('left',3,3,0),('near',10,10,0),('middle',25,25,0),
                ('right',175,175,0),('forward',3,25,0),('reverse',30,3,0),
                ('outside-right',3,config.width+30,0),('outside-left',30,-20,0),('shift-left',3,3,1),('shift-right',30,30,1)]
            cases=[(*entry,1) for entry in cases]
            if 'pointer_cases' in item:
                cases=[(entry['name'],entry['x'],entry['end_x'],entry.get('modifiers',0),entry.get('click_count',1)) for entry in item['pointer_cases']]
            if args.click_counts:
                assert api.pointer_capabilities&1
                cases += [('word',25,25,0,2),('line',25,25,0,3),('word-forward',10,100,0,2),
                    ('word-reverse',100,10,0,2),('line-forward',10,100,0,3),('line-reverse',100,10,0,3)]
            for name,start,end,modifiers,clicks in cases:
                model=TextModel(C.sizeof(TextModel),item['text'].encode(),1 if modifiers else 0,2 if modifiers else 0,item.get('editable',1))
                assert native.nxs_control_text_sync(pointer,C.byref(model))
                pointer_case=dict(pumped=False,drag=start!=end,end=end,modifiers=modifiers,clicks=clicks)
                if clicks==1:native.nxs_control_track(pointer,start,12,modifiers)
                else:
                    assert api.pointer_capabilities&1
                    assert native.nxs_control_track_clicks(pointer,start,12,modifiers,clicks)
                state=TextState(size=C.sizeof(TextState));buffer=C.create_string_buffer(256)
                assert native.nxs_control_text_get(pointer,buffer,len(buffer),C.byref(state))
                assert pointer_case['pumped'] and not native.nxs_control_state(pointer).tracking
                if state.selection_length:save_image('-pointer-'+name)
                values.append(dict(name=name,x=start,end_x=end,modifiers=modifiers,click_count=clicks,value=buffer.value.decode(),
                    start=state.selection_start,end=state.selection_start+state.selection_length))
            pointer_case=None;results[-1]['pointers']=values
    finally:
        assert native.nxs_control_destroy(pointer)
(args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
