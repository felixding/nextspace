#!/usr/bin/env python3
"""Exercise the geometry bridge using ordinary GTK3 windows and public APIs."""
import argparse,ctypes as C,json,os,select,sys
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--library',required=True);a=p.parse_args()
gtk=C.CDLL('libgtk-3.so.0',mode=C.RTLD_GLOBAL)
gdk=C.CDLL('libgdk-3.so.0',mode=C.RTLD_GLOBAL)
glib=C.CDLL('libglib-2.0.so.0');bridge=C.CDLL(a.library)
def signature(lib,name,args,result):
 fn=getattr(lib,name);fn.argtypes=args;fn.restype=result;return fn
init=signature(gtk,'gtk_init_check',[C.c_void_p,C.c_void_p],C.c_int)
create=signature(gtk,'gtk_window_new',[C.c_int],C.c_void_p)
transient=signature(gtk,'gtk_window_set_transient_for',[C.c_void_p,C.c_void_p],None)
size=signature(gtk,'gtk_window_set_default_size',[C.c_void_p,C.c_int,C.c_int],None)
show=signature(gtk,'gtk_widget_show_all',[C.c_void_p],None)
destroy=signature(gtk,'gtk_widget_destroy',[C.c_void_p],None)
get_window=signature(gtk,'gtk_widget_get_window',[C.c_void_p],C.c_void_p)
get_display=signature(gdk,'gdk_window_get_display',[C.c_void_p],C.c_void_p)
close_display=signature(gdk,'gdk_display_close',[C.c_void_p],None)
iterate=signature(glib,'g_main_context_iteration',[C.c_void_p,C.c_int],C.c_int)
class Geometry(C.Structure):_fields_=[('x',C.c_int32),('y',C.c_int32),('width',C.c_int32),('height',C.c_int32),('mapped',C.c_uint32)]
Callback=C.CFUNCTYPE(None,C.c_void_p)
get_geometry=signature(bridge,'nxs_gtk3_surface_geometry',[C.c_void_p,C.POINTER(Geometry),Callback],C.c_int)
count=0;generation=0

def report(event,window):
 value=Geometry();received=get_geometry(window,C.byref(value),changed)
 print(json.dumps(dict(event=event,received=received,generation=generation,callbacks=count,**{name:getattr(value,name) for name,_ in Geometry._fields_})),flush=True)
@Callback
def changed(window):
 global count
 count+=1;report('geometry',window)
def new_window():
 global generation
 generation+=1;widget=create(0);assert widget;size(widget,420,260);show(widget);window=get_window(widget);assert window
 report('ready',window);return widget,window
assert init(None,None),'GTK display unavailable'
widget,window=new_window();display_open=True
pending=b'';stopping=False
try:
 while not stopping:
  while iterate(None,0):pass
  ready,_,_=select.select([sys.stdin],[],[],.01)
  if not ready:continue
  data=os.read(sys.stdin.fileno(),4096)
  if not data:break
  pending+=data
  while b'\n' in pending:
   line,pending=pending.split(b'\n',1);command=line.decode().strip()
   if command in ('','quit'):stopping=True;break
   if command=='status':report('status',window)
   elif command=='popup':
    popup=create(1);transient(popup,widget);size(popup,100,80);show(popup);report('popup',get_window(popup));destroy(popup)
   elif command=='replace':destroy(widget);widget,window=new_window()
   elif command=='close-display':
    close_display(get_display(window));display_open=False;print(json.dumps(dict(event='display-closed',callbacks=count)),flush=True)
finally:
 if display_open:destroy(widget)
 for _ in range(20):
  if not iterate(None,0):break
