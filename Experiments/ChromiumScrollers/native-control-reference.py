#!/usr/bin/env python3
"""Render references directly through NativeUI's public ABI, without Chromium."""
import argparse
import ctypes as C
import json
import math
from pathlib import Path
from PIL import Image
from helper import Bitmap, Pump, Response
from native_controls import NativeControlServer, ControlConfig, ControlChanged, KeyEvent, PopupItem,TextModel,TextState

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--library', type=Path, required=True)
parser.add_argument('--controls', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--focus', action='store_true', help='Use the real first-responder state for enabled controls')
parser.add_argument('--keys', action='store_true', help='Record actual native slider key results')
parser.add_argument('--pointers', action='store_true', help='Record native text hit testing and selection tracking')
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
        Image.frombytes('RGBA', (image.width, image.height), pixels, 'raw', 'BGRA').save(args.output / (item['id'] + suffix + '.png'))
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
            elif not pointer_case['drag'] or selected!=pointer_case['initial']:
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
        if item.get('preferred_size'):
            preferred = native.nxs_control_size(pointer)
            config.width, config.height = math.ceil(preferred.width), math.ceil(preferred.height)
            assert native.nxs_control_sync(pointer, C.byref(config))
        if item['kind']==6:
            model=item['items'];titles=[entry['title'].encode('utf-8') for entry in model]
            entries=(PopupItem*len(model))(*[PopupItem(C.sizeof(PopupItem),title,
                entry.get('enabled',1),entry.get('separator',0)) for entry,title in zip(model,titles)])
            assert native.nxs_control_popup_items(pointer,entries,len(model),item['selected'])
        if 'step' in item:
            assert api.range_capabilities and native.nxs_control_set_step(pointer,item['step'])
        if args.focus and item['enabled'] and item['kind'] != 5:
            assert api.input_capabilities & 1
            assert native.nxs_control_focus(pointer, 1)
        if item['kind'] in (7,8):
            model=TextModel(C.sizeof(TextModel),item['text'].encode(),
                1 if args.focus and item['enabled'] else item.get('selection_start',0),
                2 if args.focus and item['enabled'] else item.get('selection_length',0),item.get('editable',1))
            assert native.nxs_control_text_sync(pointer,C.byref(model))
        image = save_image()
        preferred = native.nxs_control_size(pointer)
        results.append(dict(id=item['id'], size=[image.width, image.height],
                            preferred=[preferred.width, preferred.height]))
        if item['kind']==6 and item['enabled'] and item['items']:
            assert native.nxs_control_set_screen_origin(pointer,240,160)
            assert native.nxs_control_popup_open(pointer,1)
            native.nxs_native_ui_dispatch_events(0)
            rectangles=[]
            for index in range(len(item['items'])):
                rect=native.nxs_control_popup_item_rect(pointer,index)
                rectangles.append({key:getattr(rect,key) for key in ('x','y','width','height')})
            results[-1]['native_item_rects']=rectangles
            assert native.nxs_control_popup_open(pointer,0)
        if item['enabled'] and item['kind'] not in (5,6,7,8):
            native.nxs_control_track(pointer, config.width / 2, config.height / 2, 0)
        if args.keys and item['enabled'] and item['kind']==4:
            assert native.nxs_control_sync(pointer,C.byref(config))
            assert native.nxs_control_focus(pointer,1)
            values=[]
            for name,key in [('ArrowRight',7),('Home',10),('End',11),('PageDown',13)]:
                event=KeyEvent(C.sizeof(KeyEvent),0,0,key,0,b'',b'')
                native.nxs_control_key(pointer,C.byref(event))
                values.append(dict(key=name,value=native.nxs_control_state(pointer).value))
            results[-1]['keys']=values
        if args.keys and item['enabled'] and item['kind'] in (7,8) and item.get('editable',1):
            assert native.nxs_control_focus(pointer,1)
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
            for name,start,end,modifiers in [('left',3,3,0),('near',10,10,0),('middle',25,25,0),
                ('right',175,175,0),('forward',3,25,0),('reverse',30,3,0),
                ('outside-right',3,210,0),('outside-left',30,-20,0),('shift-left',3,3,1),('shift-right',30,30,1)]:
                model=TextModel(C.sizeof(TextModel),item['text'].encode(),1 if modifiers else 0,2 if modifiers else 0,item.get('editable',1))
                assert native.nxs_control_text_sync(pointer,C.byref(model))
                pointer_case=dict(pumped=False,drag=start!=end,end=end,modifiers=modifiers)
                native.nxs_control_track(pointer,start,12,modifiers)
                state=TextState(size=C.sizeof(TextState));buffer=C.create_string_buffer(256)
                assert native.nxs_control_text_get(pointer,buffer,len(buffer),C.byref(state))
                assert pointer_case['pumped'] and not native.nxs_control_state(pointer).tracking
                if state.selection_length:save_image('-pointer-'+name)
                values.append(dict(name=name,x=start,end_x=end,modifiers=modifiers,value=buffer.value.decode(),
                    start=state.selection_start,end=state.selection_start+state.selection_length))
            pointer_case=None;results[-1]['pointers']=values
    finally:
        assert native.nxs_control_destroy(pointer)
(args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
