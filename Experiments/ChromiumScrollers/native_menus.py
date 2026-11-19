"""Menu-model transport only. The independent UI provider owns native menus."""
import ctypes as C
import select
import math
import sys
import os
from native_controls import MAGIC,ControlRequest,ControlInputRequest,KeyEvent,ControlRect
MENU_COMMAND_MAGIC=0x4e584d43
MENU_ENABLED_SNAPSHOT=64
MENU_STATE_SNAPSHOTS=16
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
def replaced_branch(items,branch,replacement):
    def tree(projection):
        roots=[];nodes=[]
        for item in projection:
            node=dict(item,children=[]);nodes.append(node)
            (roots if item['parent']<0 else nodes[item['parent']]['children']).append(node)
        return roots,nodes
    roots,nodes=tree(items);children,_=tree(replacement)
    target=next(node for node in nodes if node['command']==branch);target['children']=children
    result=[]
    def flatten(nodes,parent):
        for node in nodes:
            index=len(result);result.append({k:v for k,v in dict(node,parent=parent).items() if k!='children'})
            flatten(node['children'],index)
    flatten(roots,-1);return result
class NativeMenuServer:
    def __init__(self,server,pump_type):
        self.server,self.native=server,server.native;self.states={};self.capabilities=0;self.application_key=None
        self.presentation=None;self.selected=None
        self.command=MenuCommand(self._command)
        self.lifecycle=MenuCommand(self._lifecycle)
        self.context_queue=[];self.context_closed=[];self.context_active=None;self.context_failure=None
        self.context_pump=pump_type(self._context_pump)
        if server.notification_capabilities and hasattr(self.native,'nxs_native_ui_menu_capabilities') and self.native.nxs_native_ui_menu_capabilities()&3==3:
            self.capabilities=1
            self.native.nxs_menu_create.argtypes=[C.c_char_p,MenuCommand,pump_type,C.c_void_p];self.native.nxs_menu_create.restype=C.c_void_p
            for name in ['destroy','cancel']:
                fn=getattr(self.native,'nxs_menu_'+name);fn.argtypes=[C.c_void_p];fn.restype=C.c_int
            self.native.nxs_menu_items.argtypes=[C.c_void_p,C.POINTER(MenuItem),C.c_uint32];self.native.nxs_menu_items.restype=C.c_int
            self.native.nxs_menu_show.argtypes=[C.c_void_p,C.c_int];self.native.nxs_menu_show.restype=C.c_int
            self.native.nxs_menu_key.argtypes=[C.c_void_p,C.POINTER(KeyEvent)];self.native.nxs_menu_key.restype=C.c_int
            if self.native.nxs_native_ui_menu_capabilities()&8:
                self.native.nxs_menu_key_query.argtypes=[C.c_void_p,C.POINTER(KeyEvent)];self.native.nxs_menu_key_query.restype=C.c_int
                self.capabilities|=4
            self.native.nxs_menu_state.argtypes=[C.c_void_p,C.c_int];self.native.nxs_menu_state.restype=MenuState
            if self.native.nxs_native_ui_menu_capabilities()&32:
                self.capabilities|=8
                self.native.nxs_menu_popup.argtypes=[C.c_void_p,C.c_double,C.c_double];self.native.nxs_menu_popup.restype=C.c_int
                for name in ('parent','activate'):
                    call=getattr(self.native,'nxs_menu_auxiliary_'+name);call.argtypes=[C.c_void_p,C.c_char_p];call.restype=C.c_int
                if self.native.nxs_native_ui_menu_capabilities()&4:
                    self.capabilities|=16
                    self.native.nxs_menu_lifecycle.argtypes=[C.c_void_p,MenuCommand,C.c_void_p];self.native.nxs_menu_lifecycle.restype=C.c_int
                    self.native.nxs_menu_branch_items.argtypes=[C.c_void_p,C.c_uint64,C.POINTER(MenuItem),C.c_uint32];self.native.nxs_menu_branch_items.restype=C.c_int
    def owner(self,client,req,pid):
        owner=self.server.notifiers.get(req.process);entry=self.server.text_filters.get(req.process)
        return bool(self.capabilities and owner and owner['client'] is client and owner['pid']==pid and
            entry and entry.get('menus') and entry.get('socket') and
            (req.kind in (0,1,2,3) if req.operation in (25,70) else not req.kind) and req.control)
    def owned_models(self,pid):
        for state in list(self.states.values()):
            owner=self.server.notifiers.get(state['key'][0])
            if not state['destroy'] and not state.get('context_popup') and owner and owner['client'] is state['client'] and owner['pid']==pid and not select.select([owner['lifetime']],[],[],0)[0]:
                yield state
    def has_owner(self,pid):return bool(pid and next(self.owned_models(pid),None))
    def busy(self):
        return any(self.native.nxs_menu_state(state['native'],-1).tracking for state in list(self.states.values()) if not state['destroy'])
    def cancel_foreign_contexts(self,pid):
        for state in list(self.states.values()):
            if not state['destroy'] and state.get('context_popup') and (not pid or not (self.server.auxiliary_activation.ancestor(state.get('context_pid',0),pid) or self.server.auxiliary_activation.ancestor(pid,state.get('context_pid',0)))):
                if os.environ.get('NEXTSPACE_TRACE_NATIVE_CONTEXT_MENUS')=='1':self.server.log('native-context-menu-owner-dismiss',control=state['key'][1],source=state['context_pid'],selected=pid)
                self.native.nxs_menu_cancel(state['native'])
                if state in self.context_queue:
                    self.context_queue.remove(state);self.context_closed.append(state)
    def select_owner(self,pid):
        self.cancel_foreign_contexts(pid)
        chosen=next((state for state in self.owned_models(pid) if state.get('requested_visible')),None) if pid else None
        if chosen is self.selected:return
        for state in list(self.states.values()):
            if state is not chosen and not state.get('context_popup'):self.native.nxs_menu_cancel(state['native'])
        self.selected=chosen if not chosen or self.native.nxs_menu_show(chosen['native'],1) else None
    def selected_key(self,pid,event,execute):
        state=self.selected
        if not state or not any(candidate is state for candidate in self.owned_models(pid)):return 0
        call=self.native.nxs_menu_key if execute else self.native.nxs_menu_key_query
        return call(state['native'],C.byref(event))
    def respond(self,client,req,state=None,accepted=0,index=-1):
        result=self.server.response_type();result.magic=MAGIC;result.reserved=req.reserved;result.parts[3].x=accepted
        result.parts[4].x=self.server.generation(req.process)
        if state:
            native=self.native.nxs_menu_state(state['native'],index)
            result.parts[0].x=state['actions'];result.parts[0].y=bool(native.tracking or state.get('context_pending'))
            for index,rect in [(1,native.frame),(2,native.item_frame)]:
                result.parts[index].x=rect.x;result.parts[index].y=rect.y
                result.parts[index].width=rect.width;result.parts[index].height=rect.height
            result.parts[3].y=native.visible;result.parts[3].width=native.enabled;result.parts[3].height=native.highlighted
        self.server.send(client,result)
    def model(self,client,data,pid):
        if len(data)<C.sizeof(MenuModelRequest):return
        req=MenuModelRequest.from_buffer_copy(data);state=self.states.get((req.process,req.control))
        branch=0;position=C.sizeof(req)
        if req.operation==70:
            if len(data)<position+8:self.respond(client,req);return
            branch=int.from_bytes(data[position:position+8],'little');position+=8
            if not branch or not state or not state.get('context_lifecycle') or state.get('preparing')!=branch or req.title_size:self.respond(client,req);return
        if req.magic!=MAGIC or not self.owner(client,req,pid) or (req.kind and not self.capabilities&8) or (req.kind==2 and not self.capabilities&16) or (self.server.text_filters[req.process].get('waiting') and not branch):
            self.respond(client,req);return
        if req.text_size!=len(data)-C.sizeof(req) or req.text_size>65536 or req.title_size>req.text_size or req.count>4096:
            self.respond(client,req);return
        title=data[position:position+req.title_size];position+=req.title_size
        items=(MenuItem*req.count)();strings=[]
        try:
            if b'\0' in title:raise ValueError()
            title.decode('utf8')
            for index in range(req.count):
                if position+C.sizeof(MenuWireItem)>len(data):raise ValueError()
                wire=MenuWireItem.from_buffer_copy(data,position);position+=C.sizeof(wire)
                if wire.reserved or wire.flags&~63 or position+wire.title_size+wire.key_size>len(data):raise ValueError()
                label=data[position:position+wire.title_size];position+=wire.title_size
                key=data[position:position+wire.key_size];position+=wire.key_size
                if b'\0' in label+key:raise ValueError()
                label.decode('utf8');key.decode('utf8');strings.extend([label,key])
                flags=wire.flags
                if not flags&1 and self.native.nxs_native_ui_menu_capabilities()&MENU_STATE_SNAPSHOTS:
                    flags|=MENU_ENABLED_SNAPSHOT
                items[index]=MenuItem(C.sizeof(MenuItem),wire.parent,wire.command,label,key,wire.modifiers,flags)
            if position!=len(data) or (state and (state['destroy'] or (not branch and state['title']!=title) or state.get('context_popup',False)!=bool(req.kind))):raise ValueError()
        except (ValueError,UnicodeDecodeError):self.respond(client,req);return
        display_title=title
        if req.kind and not display_title:
            source=next(self.owned_models(pid),None)
            if source:display_title=source['title']
        created=state is None
        if created:
            context=next(self.server.identities)
            pointer=self.native.nxs_menu_create(display_title,self.command,self.context_pump,context)
            if not pointer:self.respond(client,req);return
            state=dict(key=(req.process,req.control,0),native=pointer,context=context,client=client,
                destroy=False,title=title,actions=0,context_popup=bool(req.kind),context_lifecycle=req.kind==2,context_activate=req.kind!=3,context_pid=pid)
            self.server.contexts[context]=state;self.states[(req.process,req.control)]=state
        accepted=self.native.nxs_menu_branch_items(state['native'],branch,items,req.count) if branch else self.native.nxs_menu_items(state['native'],items,req.count)
        if accepted and not branch and state.get('context_lifecycle'):accepted=self.native.nxs_menu_lifecycle(state['native'],self.lifecycle,state['context'])
        if accepted and state.get('context_popup'):
            projection=[dict(title=(item.title or b'').decode('utf8'),parent=item.parent,flags=item.flags,command=item.command) for item in items]
            state['context_items']=replaced_branch(state['context_items'],branch,projection) if branch else projection
            state['context_trace_branch']=branch;state['context_trace_dirty']=True
            if os.environ.get('NEXTSPACE_TRACE_NATIVE_CONTEXT_MENUS')=='1':self.server.log('native-context-menu-branch' if branch else 'native-context-menu-projection',control=req.control,branch=branch,items=projection)
        if not accepted and created:
            assert self.native.nxs_menu_destroy(state['native']);del self.states[(req.process,req.control)];del self.server.contexts[state['context']];state=None
        if accepted:self.server.log('native-menu-model',process=req.process,control=req.control,count=req.count)
        self.respond(client,req,state,accepted)
    def message(self,client,data,pid):
        operation=int.from_bytes(data[4:8],'little')
        if operation in (25,70):self.model(client,data,pid);return
        cls=ControlInputRequest if operation==27 else ControlRequest
        if len(data)<C.sizeof(cls):return
        req=cls.from_buffer_copy(data)
        if operation==27 and self.context_active:
            state=self.context_active;owner=self.server.notifiers.get(req.process)
            authorized=(req.magic==MAGIC and req.focused in (-1,0,1) and not req.kind and owner and owner['client'] is client
                and owner['pid']==pid and self.server.auxiliary_activation.ancestor(state['context_pid'],pid) and not select.select([owner['lifetime']],[],[],0)[0]
                and not self.server.text_filters.get(req.process,{}).get('waiting')
                and (not self.server.input_owner or self.server.input_owner(pid)))
            event=self.key_event(req,data) if authorized else None
            call=self.native.nxs_menu_key_query if req.focused in (-1,0) else self.native.nxs_menu_key
            accepted=call(state['native'],C.byref(event)) if event else 0
            if event and not accepted and not req.control and req.focused>=0 and self.application_key:
                # Some toolkit context models omit accelerators. Reuse the
                # current application's native menu registry, including its
                # original validation, rather than adding shortcut bindings.
                accepted=self.application_key(event,False)
                if accepted and req.focused==1:
                    state['context_application_key']=event
                    self.native.nxs_menu_cancel(state['native'])
            if os.environ.get('NEXTSPACE_TRACE_NATIVE_CONTEXT_MENUS')=='1':self.server.log('native-context-menu-key',control=state['key'][1],key=req.key,type=req.type,mode=req.focused,modifiers=req.modifiers,text=event.text.decode('utf8') if event and event.text else '',authorized=bool(authorized),accepted=accepted)
            self.respond(client,req,accepted=accepted);return
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
            # Legacy model clients use focused=0 for execution. New clients
            # explicitly query (-1) or execute (1), with the same input-owner
            # restriction as native fields when a shell broker is present.
            # Queries never invoke an application action.
            if req.focused not in (-1,0,1) or (req.focused==-1 and not self.capabilities&4):
                self.respond(client,req);return
            if req.focused and (select.select([self.server.notifiers[req.process]['lifetime']],[],[],0)[0]
                    or self.server.input_owner and not self.server.input_owner(pid)):
                self.respond(client,req);return
            event=self.key_event(req,data)
            if event is None:self.respond(client,req);return
            key=self.native.nxs_menu_key_query if req.focused==-1 else self.native.nxs_menu_key
            accepted=key(state['native'],C.byref(event))
        elif req.text_size or len(data)!=C.sizeof(req):self.respond(client,req);return
        elif operation==69:
            accepted=bool(self.capabilities&8 and state.get('context_popup') and not self.context_active and not self.context_queue
                and not any((req.state,req.width,req.height,req.minimum,req.maximum,req.value,req.enabled,req.indeterminate,req.modifiers))
                and math.isfinite(req.x) and math.isfinite(req.y)
                and (not self.server.input_owner or self.server.input_owner(pid)))
            if accepted:
                state.update(context_popup=True,requested_visible=False,context_pid=pid,context_point=(req.x,req.y),context_pending=True)
                self.context_queue.append(state)
        elif operation==26 and req.state in (0,1):
            state['requested_visible']=bool(req.state)
            if self.presentation:accepted=self.presentation(state,pid,req.state)
            else:accepted=self.native.nxs_menu_show(state['native'],req.state)
        elif operation==28:accepted=1;index=req.state
        elif operation in (29,30):
            if state.get('context_popup') and os.environ.get('NEXTSPACE_TRACE_NATIVE_CONTEXT_MENUS')=='1':self.server.log('native-context-menu-source-close',control=state['key'][1],operation=operation)
            state['requested_visible']=False
            was_queued=state in self.context_queue
            self.context_queue=[s for s in self.context_queue if s is not state]
            if operation==30 and was_queued:self.context_closed.append(state)
            accepted=self.native.nxs_menu_cancel(state['native'])
            if operation==29:state['destroy']=True
        self.respond(client,req,state,accepted,index)
    def _context_pump(self,context):
        state=self.context_active
        try:
            if state and not state.get('context_activated') and self.native.nxs_menu_state(state['native'],-1).visible:
                state['context_activated']=True
                self.server.auxiliary_activation.open(state,state['context_pid'],activate=state.get('context_activate',True))
            if state and state.get('context_trace_dirty') and os.environ.get('NEXTSPACE_TRACE_NATIVE_CONTEXT_MENUS')=='1':
                items=state.get('context_items',[]);branch=state.get('context_trace_branch',0)
                parent=next((i for i,item in enumerate(items) if item['command']==branch),-1) if branch else -1
                first=next((i for i,item in enumerate(items) if item['parent']==parent),None)
                if first is not None and self.native.nxs_menu_state(state['native'],first).visible:
                    state['context_trace_dirty']=False
                    for index,item in enumerate(items):
                        rect=self.native.nxs_menu_state(state['native'],index).item_frame
                        self.server.log('native-context-menu-item',control=state['key'][1],index=index,
                            rect=[rect.x,rect.y,rect.width,rect.height],**item)
        except BaseException:
            self.context_failure=sys.exc_info()
            if state:self.native.nxs_menu_cancel(state['native'])
        self.server.pump(context)
    def dispatch_context(self):
        if not self.context_active and self.context_closed:
            state=self.context_closed.pop(0)
            if not state['destroy']:self._command(state['context'],0,1)
            state['context_pending']=False;self.server.invalidate(state['key'][0])
        if self.context_active or not self.context_queue or not self.server.idle():return
        state=self.context_queue.pop(0)
        if state['destroy']:return
        if self.server.input_owner and not self.server.input_owner(state['context_pid']):
            self._command(state['context'],0,1);return
        self.context_active=state;state['context_activated']=False
        try:
            self.server.log('native-context-menu-open',process=state['key'][0],control=state['key'][1],point=state['context_point'])
            self.native.nxs_menu_popup(state['native'],*state['context_point'])
            if self.context_failure:
                _,error,trace=self.context_failure;self.context_failure=None;raise error.with_traceback(trace)
        finally:
            self.context_active=None
            self.server.auxiliary_activation.retire(state)
        # The original application closes its model after native tracking has
        # ended. Command0 is this lifecycle receipt, never a menu item.
        closed=self._command(state['context'],0,1) if not state['destroy'] else 0
        state['context_pending']=False;self.server.invalidate(state['key'][0])
        event=state.pop('context_application_key',None)
        if closed==1 and event and self.application_key and self.server.input_owner and self.server.input_owner(state['context_pid']):
            self.application_key(event,True)
        self.server.log('native-context-menu-closed',process=state['key'][0],control=state['key'][1])
    def key_event(self,req,data):
        if req.text_size+req.unmodified_size!=len(data)-C.sizeof(req) or req.text_size+req.unmodified_size>65536:return None
        text=data[C.sizeof(req):C.sizeof(req)+req.text_size];unmodified=data[C.sizeof(req)+req.text_size:]
        try:
            if b'\0' in text+unmodified:raise ValueError()
            text.decode('utf8');unmodified.decode('utf8')
        except (ValueError,UnicodeDecodeError):return None
        return KeyEvent(C.sizeof(KeyEvent),req.type,req.modifiers,req.key,req.repeat,text,unmodified)
    def _lifecycle(self,context,branch,phase):
        state=self.server.contexts.get(context)
        if not state or state['destroy']:return 0
        previous=state.get('preparing');state['preparing']=branch if phase==0 else None
        try:return self._command(context,branch,phase+2)
        finally:state['preparing']=previous
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
