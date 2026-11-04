#!/usr/bin/env python3
"""Check late-loaded GTK through ordinary PyGObject, without adapter calls."""
import json
import time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, GLib

Gtk.init()
window=Gtk.Window(title='ForeignScrollerGI')
window.set_decorated(False)
window.set_default_size(480,360)
scroll=Gtk.ScrolledWindow()
content=Gtk.Label(label='Left to right content')
content.set_size_request(900,1200)
scroll.set_child(content)
window.set_child(scroll)
window.present()
loop=GLib.MainLoop()
result={}
deadline=time.monotonic()+10

def check():
    bar=scroll.get_vscrollbar()
    ok,bounds=bar.compute_bounds(window)
    native='libnextspace-native-scroller.so' in Path('/proc/self/maps').read_text()
    if time.monotonic()<deadline and (not native or not ok or bounds.get_width()!=18 or bounds.get_x()!=0): return True
    result.update(native=native,x=bounds.get_x(),width=bounds.get_width(),direction=int(content.get_direction()))
    print(json.dumps(result),flush=True)
    loop.quit()
    return False

GLib.timeout_add(350,check)
loop.run()
window.destroy()
assert result['native'] and result['x']==0 and result['width']==18 and result['direction']==1,result
