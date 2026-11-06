#!/usr/bin/env python3
"""Run the shared D-Bus menu binding as a standalone native host."""
import argparse,ctypes as C,signal,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ChromiumScrollers'))
from binding import MenuBinding
p=argparse.ArgumentParser(description=__doc__)
for name in ['library','service','path','title']:p.add_argument('--'+name,required=True)
p.add_argument('--owner',type=int,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--lifecycle',action='store_true')
a,native_args=p.parse_known_args()
binding=MenuBinding(lambda:C.CDLL(a.library),service=a.service,path=a.path,owner=a.owner,
    title=a.title,output=a.output,lifecycle=a.lifecycle)
for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,binding.stop)
signal.signal(signal.SIGUSR1,binding.dump_states)
try:
    while binding.is_alive():
        binding.tick()
        binding.native.nxs_native_ui_dispatch_events(.005)
        time.sleep(.001)
finally:assert binding.close()
