"""Expose GLib's own poll descriptors/deadline to the native host loop."""
import ctypes as C
from gi.repository import GLib


class PollFD(C.Structure):
    _fields_=[('fd',C.c_int),('events',C.c_ushort),('revents',C.c_ushort)]


class GLibLoop:
    def __init__(self):
        self.context=GLib.MainContext.default()
        self.glib=C.CDLL('libglib-2.0.so.0')
        signatures={
            'g_main_context_default':(C.c_void_p,[]),
            'g_main_context_acquire':(C.c_int,[C.c_void_p]),
            'g_main_context_release':(None,[C.c_void_p]),
            'g_main_context_prepare':(C.c_int,[C.c_void_p,C.POINTER(C.c_int)]),
            'g_main_context_query':(C.c_int,[C.c_void_p,C.c_int,C.POINTER(C.c_int),C.POINTER(PollFD),C.c_int])}
        for name,(result,args) in signatures.items():
            fn=getattr(self.glib,name);fn.restype=result;fn.argtypes=args
        self.pointer=self.glib.g_main_context_default()

    def pump(self):
        while self.context.pending():self.context.iteration(False)

    def poll(self):
        if not self.glib.g_main_context_acquire(self.pointer):
            raise RuntimeError('GLib context belongs to another thread')
        try:
            priority,timeout=C.c_int(),C.c_int()
            ready=self.glib.g_main_context_prepare(self.pointer,C.byref(priority))
            count=self.glib.g_main_context_query(self.pointer,priority.value,C.byref(timeout),None,0)
            while True:
                if not 0<=count<=4096:raise RuntimeError('Excessive GLib poll descriptors')
                descriptors=(PollFD*count)()
                actual=self.glib.g_main_context_query(self.pointer,priority.value,C.byref(timeout),descriptors,count)
                if actual<=count:break
                count=actual
            readers={p.fd for p in descriptors[:actual] if p.fd>=0 and p.events&1}
            writers={p.fd for p in descriptors[:actual] if p.fd>=0 and p.events&4}
            delay=0 if ready else None if timeout.value<0 else timeout.value/1000
            return readers,writers,delay
        finally:self.glib.g_main_context_release(self.pointer)
