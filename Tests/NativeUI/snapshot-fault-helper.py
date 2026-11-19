#!/usr/bin/env python3
"""Owned test host: withhold bitmap payloads while preserving native edits."""
import os
from pathlib import Path
import runpy
import sys
import hashlib
import json

source=Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'
sys.path.insert(0,str(source))
from native_controls import NativeControlServer

marker=Path(os.environ['NEXTSPACE_NATIVE_UI_TEST_FAULT'])
original=NativeControlServer._respond
image_evidence=os.environ.get('NEXTSPACE_NATIVE_UI_IMAGE_EVIDENCE')
image_records={}


def respond(self,client,request,state=None,pixels=False,*args,**kwargs):
    popup_drop=marker.parent/'withhold-calendar-configuration-replies'
    if request.operation==1 and request.kind==17 and state and popup_drop.exists() and self.native.nxs_control_popup_state(state['native']).visible:
        self.log('test-native-calendar-configuration-reply-withheld',control=request.control,sequence=request.reserved)
        return
    dropped=marker.parent/('drop-next-native-reply-'+str(request.operation))
    if request.operation in (2,14,59,66) and dropped.exists():
        dropped.unlink()
        self.log('test-native-input-reply-withheld',operation=request.operation,
                 kind=request.kind,control=request.control,sequence=request.reserved)
        return
    if pixels and state and request.kind in (7,9,17):
        self.log('test-native-density',kind=request.kind,control=request.control,
            presentation=state.get('presentation',1),
            backing=self.native.nxs_control_backing_scale(state['native']))
        if request.kind==9:
            viewport=self.native.nxs_control_text_viewport(state['native'])
            self.log('test-native-textarea-viewport',process=request.process,control=request.control,
                visible={k:getattr(viewport.visible,k) for k in ('x','y','width','height')},
                content={k:getattr(viewport.content,k) for k in ('width','height')})
    if request.operation==8 and request.type==0 and (marker.parent/'drop-one-native-key-reply').exists():
        (marker.parent/'drop-one-native-key-reply').unlink()
        self.log('test-native-key-reply-withheld',kind=request.kind,sequence=request.reserved,type=request.type)
        return
    if request.kind in self.text_kinds and marker.exists() and pixels:
        pixels=False
        self.log('test-native-bitmap-withheld',kind=request.kind,control=request.control)
    if request.kind==16 and (marker.parent/'withhold-color-bitmaps').exists() and pixels:
        pixels=False
        self.log('test-native-color-bitmap-withheld',control=request.control)
    if request.kind==1 and (marker.parent/'withhold-button-bitmaps').exists() and pixels:
        pixels=False
        self.log('test-native-button-bitmap-withheld',control=request.control)
    if not image_evidence or request.kind!=7 or not pixels or not state:
        return original(self,client,request,state,pixels,*args,**kwargs)
    # Observe the bytes already sent by the original host. Never issue an
    # extra draw, change focus or force a repaint to produce test evidence.
    send=self.send
    def observe(peer,reply,data=b''):
        if reply.width>0 and reply.height>0 and len(data)==reply.stride*reply.height:
            from PIL import Image
            root=Path(image_evidence);root.mkdir(exist_ok=True)
            digest=hashlib.sha256(data).hexdigest();path=root/(digest+'.png')
            if not path.exists():Image.frombytes('RGBA',(reply.width,reply.height),data,'raw','BGRA',reply.stride).save(path)
            record=dict(process=request.process,control=request.control,kind=request.kind,
                width=state['logged_dimensions'][0]/state.get('presentation',1),
                height=state['logged_dimensions'][1]/state.get('presentation',1),scale=state.get('presentation',1),
                bitmap_width=reply.width,bitmap_height=reply.height,sha256=digest,path=str(path))
            key=(request.process,request.control)
            if image_records.get(key)!=record:
                with (root/'images.jsonl').open('a') as output:output.write(json.dumps(record)+'\n')
                image_records[key]=record
        return send(peer,reply,data)
    self.send=observe
    try:return original(self,client,request,state,pixels,*args,**kwargs)
    finally:self.send=send


NativeControlServer._respond=respond
runpy.run_path(str(source/'helper.py'),run_name='__main__')
