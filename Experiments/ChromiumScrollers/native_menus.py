"""Menu-model transport only. The independent UI provider owns native menus."""
import ctypes as C
import select
from native_controls import MAGIC,ControlRequest,ControlInputRequest,KeyEvent,ControlRect
MENU_COMMAND_MAGIC=0x4e584d43
class MenuModelRequest(C.Structure):
    _fields_=ControlRequest._fields_[:7]+[('count',C.c_uint32),('title_size',C.c_uint32)]
class MenuWireItem(C.Structure):
    _fields_=[('parent',C.c_int32),('flags',C.c_uint32),('command',C.c_uint64),
        ('modifiers',C.c_uint32),('title_size',C.c_uint32),('key_size',C.c_uint32),('reserved',C.c_uint32)]
class MenuItem(C.Structure):
    _fields_=[('size',C.c_uint32),('parent',C.c_int32),('command',C.c_uint64),
        ('title',C.c_char_p),('key',C.c_char_p),('modifiers',C.c_uint32),('flags',C.c_uint32)]
class MenuState(C.Structure):
    _fields_=[('size',C.c_uint32),('visible',C.c_int),('tracking',C.c_int),
        ('highlighted',C.c_int),('enabled',C.c_int),('frame',ControlRect),('item_frame',ControlRect)]
class NativeMenuCommand(C.Structure):
    _fields_=[('magic',C.c_uint32),('size',C.c_uint32),('process',C.c_uint32),
        ('phase',C.c_uint32),('control',C.c_uint64),('serial',C.c_uint64),('command',C.c_uint64)]
MenuCommand=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_uint64,C.c_uint)
class NativeMenuServer:
    def __init__(self,server,pump_type):
        self.server,self.native=server,server.native;self.states={};self.capabilities=0;self.application_key=None
        self.command=MenuCommand(self._command)
        if server.notification_capabilities and hasattr(self.native,'nxs_native_ui_menu_capabilities') and self.native.nxs_native_ui_menu_capabilities()&3==3:
            self.capabilities=1
            self.native.nxs_menu_create.argtypes=[C.c_char_p,MenuCommand,pump_type,C.c_void_p];self.native.nxs_menu_create.restype=C.c_void_p
            for name in ['destroy','cancel']:
                fn=getattr(self.native,'nxs_menu_'+name);fn.argtypes=[C.c_void_p];fn.restype=C.c_int
            self.native.nxs_menu_items.argtypes=[C.c_void_p,C.POINTER(MenuItem),C.c_uint32];self.native.nxs_menu_items.restype=C.c_int
            self.native.nxs_menu_show.argtypes=[C.c_void_p,C.c_int];self.native.nxs_menu_show.restype=C.c_int
            self.native.nxs_menu_key.argtypes=[C.c_void_p,C.POINTER(KeyEvent)];self.native.nxs_menu_key.restype=C.c_int
            self.native.nxs_menu_state.argtypes=[C.c_void_p,C.c_int];self.native.nxs_menu_state.restype=MenuState
    def owner(self,client,req,pid):
        owner=self.server.notifiers.get(req.process);entry=self.server.text_filters.get(req.process)
        return bool(self.capabilities and owner and owner['client'] is client and owner['pid']==pid and
            entry and entry.get('menus') and entry.get('socket') and not req.kind and req.control)
    def respond(self,client,req,state=None,accepted=0,index=-1):
        result=self.server.response_type();result.magic=MAGIC;result.reserved=req.reserved;result.parts[3].x=accepted
        if state:
            native=self.native.nxs_menu_state(state['native'],index)
            result.parts[0].x=state['actions'];result.parts[0].y=native.tracking
            for index,rect in [(1,native.frame),(2,native.item_frame)]:
                result.parts[index].x=rect.x;result.parts[index].y=rect.y
                result.parts[index].width=rect.width;result.parts[index].height=rect.height
            result.parts[3].y=native.visible;result.parts[3].width=native.enabled;result.parts[3].height=native.highlighted
        self.server.send(client,result)
    def model(self,client,data,pid):
        if len(data)<C.sizeof(MenuModelRequest):return
        req=MenuModelRequest.from_buffer_copy(data);state=self.states.get((req.process,req.control))
        if req.magic!=MAGIC or not self.owner(client,req,pid) or self.server.text_filters[req.process].get('waiting'):
            self.respond(client,req);return
        if req.text_size!=len(data)-C.sizeof(req) or req.text_size>65536 or req.title_size>req.text_size or req.count>4096:
            self.respond(client,req);return
        position=C.sizeof(req);title=data[position:position+req.title_size];position+=req.title_size
        items=(MenuItem*req.count)();strings=[]
        try:
            if b'\0' in title:raise ValueError()
            title.decode('utf8')
            for index in range(req.count):
                if position+C.sizeof(MenuWireItem)>len(data):raise ValueError()
                wire=MenuWireItem.from_buffer_copy(data,position);position+=C.sizeof(wire)
                if wire.reserved or position+wire.title_size+wire.key_size>len(data):raise ValueError()
                label=data[position:position+wire.title_size];position+=wire.title_size
                key=data[position:position+wire.key_size];position+=wire.key_size
                if b'\0' in label+key:raise ValueError()
                label.decode('utf8');key.decode('utf8');strings.extend([label,key])
                items[index]=MenuItem(C.sizeof(MenuItem),wire.parent,wire.command,label,key,wire.modifiers,wire.flags)
            if position!=len(data) or (state and (state['destroy'] or state['title']!=title)):raise ValueError()
        except (ValueError,UnicodeDecodeError):self.respond(client,req);return
        created=state is None
        if created:
            context=next(self.server.identities)
            pointer=self.native.nxs_menu_create(title,self.command,self.server.pump,context)
            if not pointer:self.respond(client,req);return
            state=dict(key=(req.process,req.control,0),native=pointer,context=context,client=client,
                destroy=False,title=title,actions=0)
            self.server.contexts[context]=state;self.states[(req.process,req.control)]=state
        accepted=self.native.nxs_menu_items(state['native'],items,req.count)
        if not accepted and created:
            assert self.native.nxs_menu_destroy(state['native']);del self.states[(req.process,req.control)];del self.server.contexts[state['context']];state=None
        if accepted:self.server.log('native-menu-model',process=req.process,control=req.control,count=req.count)
        self.respond(client,req,state,accepted)
    def message(self,client,data,pid):
        operation=int.from_bytes(data[4:8],'little')
        if operation==25:self.model(client,data,pid);return
        cls=ControlInputRequest if operation==27 else ControlRequest
        if len(data)<C.sizeof(cls):return
        req=cls.from_buffer_copy(data)
        if operation==27 and not req.kind and not req.control and self.application_key:
            owner=self.server.notifiers.get(req.process)
            authorized=(req.magic==MAGIC and req.focused in (0,1) and owner and owner['client'] is client
                and owner['pid']==pid and not select.select([owner['lifetime']],[],[],0)[0]
                and self.server.input_owner and self.server.input_owner(pid))
            event=self.key_event(req,data) if authorized else None
            accepted=self.application_key(event,bool(req.focused)) if event else 0
            self.respond(client,req,accepted=accepted);return
        if req.magic!=MAGIC or not self.owner(client,req,pid):self.respond(client,req);return
        if operation not in (28,29,30) and self.server.text_filters[req.process].get('waiting'):
            self.respond(client,req);return
        state=self.states.get((req.process,req.control));accepted=0;index=-1
        if not state or state['client'] is not client or state['destroy']:self.respond(client,req);return
        if operation==27:
            event=self.key_event(req,data)
            if event is None:self.respond(client,req);return
            accepted=self.native.nxs_menu_key(state['native'],C.byref(event))
        elif req.text_size or len(data)!=C.sizeof(req):self.respond(client,req);return
        elif operation==26 and req.state in (0,1):accepted=self.native.nxs_menu_show(state['native'],req.state)
        elif operation==28:accepted=1;index=req.state
        elif operation in (29,30):
            accepted=self.native.nxs_menu_cancel(state['native'])
            if operation==29:state['destroy']=True
        self.respond(client,req,state,accepted,index)
    def key_event(self,req,data):
        if req.text_size+req.unmodified_size!=len(data)-C.sizeof(req) or req.text_size+req.unmodified_size>65536:return None
        text=data[C.sizeof(req):C.sizeof(req)+req.text_size];unmodified=data[C.sizeof(req)+req.text_size:]
        try:
            if b'\0' in text+unmodified:raise ValueError()
            text.decode('utf8');unmodified.decode('utf8')
        except (ValueError,UnicodeDecodeError):return None
        return KeyEvent(C.sizeof(KeyEvent),req.type,req.modifiers,req.key,req.repeat,text,unmodified)
    def _command(self,context,command,phase):
        entry=None
        try:
            state=self.server.contexts[context];process,control,_=state['key'];entry=self.server.text_filters.get(process)
            if state['destroy'] or not entry or not entry.get('menus') or not entry.get('socket'):return 0
            serial=next(self.server.edit_serial);entry.update(serial=serial,waiting=True)
            request=NativeMenuCommand(MENU_COMMAND_MAGIC,C.sizeof(NativeMenuCommand),process,phase,control,serial,command)
            # The application may be idle. Its existing invalidation subscription
            # wakes its owner loop; callbacks still execute only on that UI thread.
            result=self.server._owner_decision(state,entry,bytes(request),serial,MENU_COMMAND_MAGIC)
            if phase==1 and result==1:state['actions']+=1
            self.server.log('native-menu-command',process=process,control=control,command=command,phase=phase,result=result)
            return int(result==1)
        except Exception as error:
            self.server.log('native-menu-command-failed',exception=type(error).__name__)
            if entry and entry.get('socket'):self.server.fail_text_filter(entry)
            return 0
        finally:
            if entry:entry['waiting']=False
    def owner_removed(self,process):
        for state in self.states.values():
            if state['key'][0]==process and not state['destroy']:
                state['destroy']=True;self.native.nxs_menu_cancel(state['native'])
    def cleanup(self):
        for key,state in list(self.states.items()):
            if state['destroy'] and self.native.nxs_menu_destroy(state['native']):
                del self.states[key];del self.server.contexts[state['context']]
                self.server.log('native-menu-destroy',process=key[0],control=key[1])
    def close(self):
        for state in self.states.values():self.native.nxs_menu_cancel(state['native'])
        for state in self.states.values():self.native.nxs_menu_destroy(state['native'])
