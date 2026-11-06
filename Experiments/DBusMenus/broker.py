"""Trusted inherited menu-address channel for a shared native control host."""
import json
import os
from pathlib import Path
import select
import socket
from binding import MenuBinding
from glib_loop import GLibLoop


_UNCHANGED=object()


class MenuBroker:
    def __init__(self,native,descriptor,output,dispatch,log,models=None):
        self.native,self.output,self.dispatch,self.log=native,Path(output),dispatch,log
        self.control=socket.socket(fileno=descriptor)
        if self.control.family!=socket.AF_UNIX or self.control.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_SEQPACKET:
            raise ValueError('Menu broker requires an inherited Unix SEQPACKET endpoint')
        self.control.setblocking(False)
        self.loop=GLibLoop();self.current=None;self.pending=_UNCHANGED;self.connected=True
        self.models=models;self.selected_pid=0
        if models:models.presentation=self.model_visibility
        self.key_capabilities=bool(native.nxs_native_ui_menu_capabilities()&8)
        if self.key_capabilities:
            import ctypes as C
            from native_controls import KeyEvent
            native.nxs_menu_key_query.argtypes=[C.c_void_p,C.POINTER(KeyEvent)];native.nxs_menu_key_query.restype=C.c_int

    def key(self,event,execute):
        if self.models and self.models.has_owner(self.selected_pid):
            return self.models.selected_key(self.selected_pid,event,execute)
        if not self.current or not self.current['binding'].is_alive():return 0
        import ctypes as C
        call=self.native.nxs_menu_key if execute else self.native.nxs_menu_key_query
        return call(self.current['binding'].menu,C.byref(event))

    def model_visibility(self,state,pid,visible):
        # The shell owns selection. Keep a valid model available while its
        # browser becomes active, without displaying a second main menu.
        if not visible:return self.native.nxs_menu_cancel(state['native'])
        return int(self.connected)

    def busy(self):
        items=[self.current,self.pending if self.pending is not _UNCHANGED else None]
        return any(self.native.nxs_menu_state(item['binding'].menu,-1).tracking for item in items if item and item['binding'].menu)

    def stop(self):
        self.selected_pid=0
        if self.models:self.models.select_owner(0)
        if self.current:self.current['binding'].stop()
        if self.pending is not _UNCHANGED and self.pending:self.pending['binding'].stop()

    def receive(self):
        try:data,ancillary,flags,_=self.control.recvmsg(8192,0,socket.MSG_DONTWAIT)
        except BlockingIOError:return
        except ConnectionResetError:data=b'';ancillary=[];flags=0
        if not data:
            self.connected=False;self.stop();self.discard_pending();return
        candidate=None
        try:
            if ancillary or flags&(socket.MSG_TRUNC|socket.MSG_CTRUNC):raise ValueError('Invalid menu broker packet')
            request=json.loads(data)
            if not isinstance(request,dict):raise ValueError('Invalid menu broker request')
            operation=request.get('operation')
            if operation=='snapshot':
                if self.current:self.current['binding'].dump_states()
                reply=dict(accepted=True)
            elif operation in ('bind','clear'):
                selected_pid=0
                if operation=='bind':
                    window,pid=request.get('window'),request.get('pid')
                    title=request.get('title')
                    if (type(window) is not int or not 0<window<2**32 or type(pid) is not int or pid<=0
                            or not isinstance(title,str) or '\0' in title or len(title)>256):
                        raise ValueError('Invalid menu window identity')
                    selected_pid=pid
                    if not self.models or not self.models.has_owner(pid):
                        binding=MenuBinding(lambda:self.native,service=request['service'],path=request['path'],
                            owner=pid,title=title,output=self.output/str(window),lifecycle=True,
                            embedding_pump=lambda:self.dispatch(0,False),deferred=True,logger=self.log)
                        try:lifetime=os.pidfd_open(pid,0)
                        except OSError:
                            assert binding.close();raise
                        candidate=dict(window=window,pid=pid,lifetime=lifetime,binding=binding)
                if self.pending is not _UNCHANGED and self.pending:
                    if not self.dispose(self.pending):raise RuntimeError('Previous menu replacement is busy')
                self.pending=candidate
                self.selected_pid=selected_pid
                if self.current:self.current['binding'].stop()
                reply=dict(accepted=True,pending=True)
            else:raise ValueError('Unknown menu broker operation')
        except Exception as error:
            if candidate and candidate is not self.pending:assert self.dispose(candidate)
            self.log('dbus-menu-rejected',message=str(error));reply=dict(accepted=False)
        try:self.control.send(json.dumps(reply).encode())
        except (BrokenPipeError,ConnectionResetError):self.connected=False;self.stop();self.discard_pending()

    def discard_pending(self):
        if self.pending is not _UNCHANGED and self.pending:assert self.dispose(self.pending)
        self.pending=None

    def pump(self):self.loop.pump()

    def poll(self):
        readers,writers,delay=self.loop.poll()
        if self.connected:readers.add(self.control.fileno())
        if self.current:readers.add(self.current['lifetime'])
        if (self.pending is not _UNCHANGED or self.current and
                (not self.current['binding'].is_alive() or self.current['binding'].needs_tick())):delay=0
        return readers,writers,delay

    def ready(self,descriptor):
        if self.connected and descriptor==self.control.fileno():self.receive()
        elif self.current and descriptor==self.current['lifetime']:self.current['binding'].stop()
        else:self.pump()

    def dispose(self,item):
        if not item['binding'].close():return False
        os.close(item['lifetime']);return True

    def tick(self):
        self.pump()
        if self.models:
            if self.models.has_owner(self.selected_pid):
                if self.current:
                    self.current['binding'].stop()
                    if not self.dispose(self.current):return
                    self.current=None
                if self.pending is not _UNCHANGED and self.pending:
                    self.pending['binding'].stop()
                    if not self.dispose(self.pending):return
                self.pending=_UNCHANGED
                self.models.select_owner(self.selected_pid)
                return
            self.models.select_owner(0)
        if self.current and (self.pending is not _UNCHANGED or not self.current['binding'].is_alive()):
            if not self.dispose(self.current):return
            self.current=None
        if self.pending is not _UNCHANGED:
            self.current,self.pending=self.pending,_UNCHANGED
            if self.current:
                self.log('dbus-menu-bound',window=self.current['window'],pid=self.current['pid'],
                    output=str(self.output/str(self.current['window'])))
        if self.current:self.current['binding'].tick()

    def allows_input(self,pid):
        if not self.selected_pid:return True
        owner=self.selected_pid
        if pid is None:return False
        # Kernel credentials supply the guest PID. Browser renderer processes
        # can be descendants; opaque transport IDs and namespace getpid logs
        # cannot establish this relation.
        seen=set()
        while pid>1 and pid not in seen:
            if pid==owner:
                if self.models and self.models.has_owner(owner):return True
                return bool(self.current and self.current['pid']==owner and self.current['binding'].is_alive()
                    and not select.select([self.current['lifetime']],[],[],0)[0])
            seen.add(pid)
            try:pid=int((Path('/proc')/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()[1])
            except (OSError,ValueError,IndexError):return False
        return False

    def close(self):
        self.stop()
        for item in [self.current,self.pending if self.pending is not _UNCHANGED else None]:
            if item:assert self.dispose(item)
        self.current=None;self.pending=_UNCHANGED;self.control.close()
        if self.models:self.models.presentation=None
