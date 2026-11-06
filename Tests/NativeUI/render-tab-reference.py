#!/usr/bin/env python3
"""Render fixture application data through the already qualified NativeUI API."""
import argparse,ctypes as C,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Experiments/ChromiumScrollers'))
from native_controls import ControlConfig,TabItem
from helper import Bitmap
p=argparse.ArgumentParser(description=__doc__)
for name in ['library','model','output']:p.add_argument('--'+name,type=Path,required=True)
a,_=p.parse_known_args();data=json.loads(a.model.read_text());native=C.CDLL(str(a.library),mode=C.RTLD_GLOBAL)
native.nxs_control_create.argtypes=[C.c_int,C.c_void_p,C.c_void_p,C.c_void_p];native.nxs_control_create.restype=C.c_void_p
native.nxs_control_sync.argtypes=[C.c_void_p,C.POINTER(ControlConfig)];native.nxs_control_sync.restype=C.c_int
native.nxs_control_tab_items.argtypes=[C.c_void_p,C.POINTER(TabItem),C.c_uint,C.c_uint64];native.nxs_control_tab_items.restype=C.c_int
native.nxs_control_draw.argtypes=[C.c_void_p,C.c_double];native.nxs_control_draw.restype=Bitmap
native.nxs_control_destroy.argtypes=[C.c_void_p];native.nxs_control_destroy.restype=C.c_int
control=native.nxs_control_create(10,None,None,None);assert control
try:
 config=ControlConfig(C.sizeof(ControlConfig),data['width'],data['height'],0,1,0,1,0,0,b'')
 assert native.nxs_control_sync(control,C.byref(config))
 items=(TabItem*len(data['items']))(*(TabItem(C.sizeof(TabItem),int(item['id']),item['title'].encode(),None) for item in data['items']))
 assert native.nxs_control_tab_items(control,items,len(items),int(data['selected']))
 image=native.nxs_control_draw(control,1);assert image.pixels
 a.output.write_bytes(C.string_at(image.pixels,image.stride*image.height))
 print(json.dumps(dict(width=image.width,height=image.height,stride=image.stride)))
finally:assert native.nxs_control_destroy(control)
