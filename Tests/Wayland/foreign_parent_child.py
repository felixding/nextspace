"""Export an original GTK3 parent through the public Wayland API."""
import ctypes as C
import json
import os
import select
import sys

gtk=C.CDLL('libgtk-3.so.0',mode=C.RTLD_GLOBAL)
gdk=C.CDLL('libgdk-3.so.0',mode=C.RTLD_GLOBAL)
glib=C.CDLL('libglib-2.0.so.0')
def signature(library,name,args,result):
    fn=getattr(library,name);fn.argtypes=args;fn.restype=result;return fn
init=signature(gtk,'gtk_init_check',[C.c_void_p,C.c_void_p],C.c_int)
create=signature(gtk,'gtk_window_new',[C.c_int],C.c_void_p)
title=signature(gtk,'gtk_window_set_title',[C.c_void_p,C.c_char_p],None)
size=signature(gtk,'gtk_window_set_default_size',[C.c_void_p,C.c_int,C.c_int],None)
show=signature(gtk,'gtk_widget_show_all',[C.c_void_p],None)
destroy=signature(gtk,'gtk_widget_destroy',[C.c_void_p],None)
window=signature(gtk,'gtk_widget_get_window',[C.c_void_p],C.c_void_p)
iterate=signature(glib,'g_main_context_iteration',[C.c_void_p,C.c_int],C.c_int)
Export=C.CFUNCTYPE(None,C.c_void_p,C.c_char_p,C.c_void_p)
export=signature(gdk,'gdk_wayland_window_export_handle',[C.c_void_p,Export,C.c_void_p,C.c_void_p],C.c_int)
@Export
def exported(unused,handle,context):
    print(json.dumps(dict(event='exported',handle='wayland:'+handle.decode())),flush=True)
def make(name):
    widget=create(0);title(widget,name.encode());size(widget,300,180);show(widget);return widget
assert init(None,None)
parent=make('Foreign parent source');other=None
assert export(window(parent),exported,None,None)
try:
    while True:
        while iterate(None,0):pass
        if not select.select([sys.stdin],[],[],.01)[0]:continue
        command=sys.stdin.readline().strip()
        if command=='other':
            other=make('Other focused window');print(json.dumps(dict(event='other')),flush=True)
        elif command=='destroy-parent':
            destroy(parent);parent=None;print(json.dumps(dict(event='parent-destroyed')),flush=True)
        elif not command or command=='quit':break
finally:
    if parent:destroy(parent)
    if other:destroy(other)
