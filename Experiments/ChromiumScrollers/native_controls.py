"""Transport for the shared native UI provider; contains no widget implementation."""
import ctypes as C
import itertools
import math

MAGIC = 0x4e585549

class ControlRequest(C.Structure):
    _fields_ = [('magic', C.c_uint32), ('operation', C.c_uint32), ('process', C.c_uint32),
                ('kind', C.c_uint32), ('control', C.c_uint64), ('text_size', C.c_uint32),
                ('reserved', C.c_uint32), ('width', C.c_double), ('height', C.c_double),
                ('minimum', C.c_double), ('maximum', C.c_double), ('value', C.c_double),
                ('x', C.c_double), ('y', C.c_double), ('enabled', C.c_int32), ('state', C.c_int32),
                ('indeterminate', C.c_int32), ('modifiers', C.c_uint32)]

class ControlConfig(C.Structure):
    _fields_ = [('size', C.c_uint32), ('width', C.c_double), ('height', C.c_double),
                ('minimum', C.c_double), ('maximum', C.c_double), ('value', C.c_double),
                ('enabled', C.c_int), ('state', C.c_int), ('indeterminate', C.c_int), ('title', C.c_char_p)]

class ControlInputRequest(C.Structure):
    _fields_ = ControlRequest._fields_[:7] + [
        ('type', C.c_uint32), ('modifiers', C.c_uint32), ('key', C.c_uint32),
        ('repeat', C.c_uint32), ('unmodified_size', C.c_uint32), ('focused', C.c_int32)]
class ControlStepRequest(C.Structure):
    _fields_ = ControlRequest._fields_[:7]+[('step',C.c_double)]
class ControlPopupRequest(C.Structure):
    _fields_ = ControlRequest._fields_[:7]+[('count',C.c_uint32),('selected',C.c_int32)]
class PopupItem(C.Structure):
    _fields_ = [('size',C.c_uint32),('title',C.c_char_p),('enabled',C.c_int),('separator',C.c_int)]
class ControlRect(C.Structure):
    _fields_ = [('x',C.c_double),('y',C.c_double),('width',C.c_double),('height',C.c_double)]
class PopupState(C.Structure):
    _fields_ = [('size',C.c_uint32),('visible',C.c_int),('highlighted',C.c_int),('frame',ControlRect)]

class KeyEvent(C.Structure):
    _fields_ = [('size', C.c_uint32), ('type', C.c_uint32), ('modifiers', C.c_uint32),
                ('key', C.c_uint32), ('repeat', C.c_uint32),
                ('text', C.c_char_p), ('unmodified_text', C.c_char_p)]

class ControlState(C.Structure):
    _fields_ = [('size', C.c_uint32), ('value', C.c_double), ('state', C.c_int),
                ('enabled', C.c_int), ('tracking', C.c_int)]

class Size(C.Structure):
    _fields_ = [('width', C.c_double), ('height', C.c_double)]

ControlChanged = C.CFUNCTYPE(None, C.c_void_p, C.c_int, C.POINTER(ControlState))

class NativeControlServer:
    def __init__(self, native, bitmap_type, response_type, pump_type, dispatch, pending, send, idle, log):
        self.native, self.response_type = native, response_type
        self.pending, self.send, self.idle, self.log = pending, send, idle, log
        self.controls, self.contexts = {}, {}
        self.identities = itertools.count(1)
        self.active = None
        self.metric_cache = {}
        self.changed = ControlChanged(self._changed)
        self.pump = pump_type(lambda context: dispatch(0))
        native.nxs_control_create.argtypes = [C.c_int, ControlChanged, pump_type, C.c_void_p]
        native.nxs_control_create.restype = C.c_void_p
        native.nxs_control_destroy.argtypes = [C.c_void_p]
        native.nxs_control_destroy.restype = C.c_int
        native.nxs_control_sync.argtypes = [C.c_void_p, C.POINTER(ControlConfig)]
        native.nxs_control_sync.restype = C.c_int
        native.nxs_control_state.argtypes = [C.c_void_p]
        native.nxs_control_state.restype = ControlState
        native.nxs_control_size.argtypes = [C.c_void_p]
        native.nxs_control_size.restype = Size
        native.nxs_control_draw.argtypes = [C.c_void_p, C.c_double]
        native.nxs_control_draw.restype = bitmap_type
        native.nxs_control_track.argtypes = [C.c_void_p, C.c_double, C.c_double, C.c_uint]
        native.nxs_control_send.argtypes = [C.c_void_p, C.c_int, C.c_double, C.c_double, C.c_uint]
        self.input_capabilities = 0
        self.event_capabilities, self.event_deadline = 0, -1
        self.generations = {}
        self.range_capabilities=0
        self.popup_capabilities=0
        self.source_capabilities=0
        if hasattr(native,'nxs_native_ui_source_capabilities'):
            native.nxs_native_ui_source_capabilities.argtypes=[]
            native.nxs_native_ui_source_capabilities.restype=C.c_uint
            self.source_capabilities=native.nxs_native_ui_source_capabilities()
            native.nxs_native_ui_source_create.argtypes=[C.c_int]
            native.nxs_native_ui_source_create.restype=C.c_void_p
            native.nxs_native_ui_source_destroy.argtypes=[C.c_void_p]
            native.nxs_native_ui_source_destroy.restype=C.c_int
        if hasattr(native,'nxs_control_popup_capabilities'):
            native.nxs_control_popup_capabilities.argtypes=[]
            native.nxs_control_popup_capabilities.restype=C.c_uint
            self.popup_capabilities=native.nxs_control_popup_capabilities()
            native.nxs_control_popup_items.argtypes=[C.c_void_p,C.POINTER(PopupItem),C.c_uint32,C.c_int]
            native.nxs_control_popup_items.restype=C.c_int
            native.nxs_control_popup_state.argtypes=[C.c_void_p]
            native.nxs_control_popup_state.restype=PopupState
            native.nxs_control_popup_item_rect.argtypes=[C.c_void_p,C.c_int]
            native.nxs_control_popup_item_rect.restype=ControlRect
            native.nxs_control_set_screen_origin.argtypes=[C.c_void_p,C.c_double,C.c_double]
            native.nxs_control_set_screen_origin.restype=C.c_int
        if hasattr(native,'nxs_control_range_capabilities'):
            native.nxs_control_range_capabilities.argtypes=[]
            native.nxs_control_range_capabilities.restype=C.c_uint
            self.range_capabilities=native.nxs_control_range_capabilities()
            native.nxs_control_set_step.argtypes=[C.c_void_p,C.c_double]
            native.nxs_control_set_step.restype=C.c_int
        if hasattr(native, 'nxs_control_input_capabilities'):
            native.nxs_control_input_capabilities.argtypes = []
            native.nxs_control_input_capabilities.restype = C.c_uint
            self.input_capabilities = native.nxs_control_input_capabilities()
            native.nxs_control_focus.argtypes = [C.c_void_p, C.c_int]
            native.nxs_control_focus.restype = C.c_int
            native.nxs_control_focused.argtypes = [C.c_void_p]
            native.nxs_control_focused.restype = C.c_int
            native.nxs_control_key.argtypes = [C.c_void_p, C.POINTER(KeyEvent)]
            native.nxs_control_key.restype = C.c_int
        if hasattr(native, 'nxs_native_ui_event_capabilities'):
            native.nxs_native_ui_event_capabilities.argtypes = []
            native.nxs_native_ui_event_capabilities.restype = C.c_uint
            self.event_capabilities = native.nxs_native_ui_event_capabilities()
            native.nxs_native_ui_dispatch_events.argtypes = [C.c_double]
            native.nxs_native_ui_dispatch_events.restype = C.c_double
            native.nxs_control_needs_display.argtypes = [C.c_void_p]
            native.nxs_control_needs_display.restype = C.c_int

    def dispatch_events(self,maximum_wait=0):
        if not self.event_capabilities:
            return -1
        self.event_deadline = self.native.nxs_native_ui_dispatch_events(maximum_wait)
        for state in self.controls.values():
            if state['destroy'] or state.get('invalidated'):
                continue
            if self.native.nxs_control_needs_display(state['native']):
                state['invalidated'] = True
                process, control, kind = state['key']
                self.generations[process] = self.generations.get(process, 0) + 1
                self.log('native-form-invalidation', process=process, control=control, kind=kind,
                         generation=self.generations[process])
        return self.event_deadline

    def preferred(self, kind):
        if kind not in self.metric_cache:
            pointer = self.native.nxs_control_create(kind, ControlChanged(), type(self.pump)(), None)
            if not pointer:
                return 0, 0
            try:
                config = ControlConfig(C.sizeof(ControlConfig), 128, 24, 0, 100, 0, 1, 0, 0, b'')
                self.native.nxs_control_sync(pointer, C.byref(config))
                size = self.native.nxs_control_size(pointer)
                self.metric_cache[kind] = size.width, size.height
            finally:
                self.native.nxs_control_destroy(pointer)
        return self.metric_cache[kind]

    def _changed(self, context, event, native_state):
        state = self.contexts[context]
        if state['destroy']:
            return
        state['actions'] += 1
        process=state['key'][0]
        self.generations[process]=self.generations.get(process,0)+1
        self.log('native-form-action', process=state['key'][0], control=state['key'][1],
                 kind=state['key'][2], action=event, count=state['actions'],
                 value=native_state.contents.value, state=native_state.contents.state)

    def _tracking(self, state):
        return bool(state.get('starting') or self.native.nxs_control_state(state['native']).tracking)

    def _respond(self, client, req, state=None, pixels=False, input_result=0, rectangle=None):
        response = self.response_type()
        response.magic, response.reserved = MAGIC, req.reserved
        response.parts[3].x = input_result
        response.parts[3].width = self.input_capabilities
        response.parts[4].x = self.generations.get(req.process, 0)
        response.parts[4].y = self.event_deadline
        response.parts[4].width = self.event_capabilities
        response.parts[5].width = self.range_capabilities
        response.parts[5].height = self.popup_capabilities
        data = b''
        if state:
            response.parts[5].x=state.get('step',0)
            current = self.native.nxs_control_state(state['native'])
            response.parts[0].x = current.value
            response.parts[0].y = self._tracking(state)
            response.parts[0].width = state['actions']
            response.parts[0].height = current.state
            preferred = self.native.nxs_control_size(state['native'])
            response.parts[1].width, response.parts[1].height = preferred.width, preferred.height
            response.parts[2].x = current.enabled
            if self.input_capabilities & 1:
                response.parts[3].y = self.native.nxs_control_focused(state['native'])
            if req.kind==6 and self.popup_capabilities:
                popup=self.native.nxs_control_popup_state(state['native'])
                response.parts[5].y=popup.highlighted
                frame=rectangle if rectangle is not None else popup.frame
                for field in ('x','y','width','height'):setattr(response.parts[6],field,getattr(frame,field))
            if pixels:
                bitmap = self.native.nxs_control_draw(state['native'], 1)
                if bitmap.pixels:
                    response.width, response.height, response.stride = bitmap.width, bitmap.height, bitmap.stride
                    data = C.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
                    state['invalidated'] = False
        self.send(client, response, data)

    def message(self, client, data):
        if len(data)>=8 and int.from_bytes(data[4:8],'little')==11:
            self.popup_message(client,data)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little')==10:
            if len(data)!=C.sizeof(ControlStepRequest):return
            req=ControlStepRequest.from_buffer_copy(data)
            if req.magic!=MAGIC or req.text_size:return
            state=self.controls.get((req.process,req.control,req.kind))
            if state and not state['destroy'] and self.range_capabilities and self.native.nxs_control_set_step(state['native'],req.step):
                state['step']=req.step
                self.log('native-slider-step',process=req.process,control=req.control,step=req.step)
                self._respond(client,req,state,pixels=True)
            else:self._respond(client,req)
            return
        if len(data) >= 8 and int.from_bytes(data[4:8], 'little') in (7, 8):
            self.input_message(client, data)
            return
        if len(data) < C.sizeof(ControlRequest):
            return
        req = ControlRequest.from_buffer_copy(data)
        if req.magic != MAGIC or req.text_size != len(data) - C.sizeof(req) or req.text_size > 65536:
            return
        if not all(math.isfinite(x) for x in (req.x, req.y)):
            self._respond(client, req)
            return
        if req.operation == 9:
            self.dispatch_events()
            self._respond(client, req)
            return
        key = req.process, req.control, req.kind
        state = self.controls.get(key)
        if state and state['destroy'] and req.operation != 5:
            self._respond(client, req)
            return
        if req.operation == 1:
            if not 1 <= req.kind <= 6 or (req.kind==6 and not self.popup_capabilities) or not all(math.isfinite(x) for x in (req.width, req.height, req.minimum, req.maximum, req.value)):
                self._respond(client, req)
                return
            if not 1 <= req.width <= 8192 or not 1 <= req.height <= 8192 or req.width * req.height > 8 * 1024 * 1024:
                self._respond(client, req)
                return
            title = data[C.sizeof(req):]
            if b'\0' in title:
                self._respond(client, req)
                return
            try:
                title.decode('utf-8')
            except UnicodeDecodeError:
                self._respond(client, req)
                return
            if state is None:
                context = next(self.identities)
                pointer = self.native.nxs_control_create(req.kind, self.changed, self.pump, context)
                if not pointer:
                    self._respond(client, req)
                    return
                state = dict(key=key, native=pointer, context=context, client=client, actions=0, destroy=False)
                self.controls[key] = self.contexts[context] = state
                self.log('native-form-control', process=req.process, control=req.control, kind=req.kind,
                         width=req.width, height=req.height)
            current = self.native.nxs_control_state(state['native'])
            config = ControlConfig(C.sizeof(ControlConfig), req.width, req.height, req.minimum, req.maximum,
                                   current.value if current.tracking else req.value, req.enabled,
                                   current.state if current.tracking else req.state, req.indeterminate, title)
            if not self.native.nxs_control_sync(state['native'], C.byref(config)):
                self._respond(client, req)
                return
            if req.kind == 5:
                current = self.native.nxs_control_state(state['native'])
                model = req.width, req.height, current.value, bool(req.indeterminate)
                if state.get('progress_model') != model:
                    state['progress_model'] = model
                    self.log('native-progress-model', process=req.process, control=req.control,
                             width=req.width, height=req.height, value=current.value,
                             indeterminate=bool(req.indeterminate))
            self._respond(client, req, state, pixels=True)
            return
        if state:
            if req.operation==12 and req.kind==6 and self.popup_capabilities:
                rectangle=ControlRect()
                if req.x==int(req.x) and 0<=req.x<65536:
                    rectangle=self.native.nxs_control_popup_item_rect(state['native'],int(req.x))
                self._respond(client,req,state,rectangle=rectangle)
                return
            if req.operation==13 and self.popup_capabilities:
                accepted=self.native.nxs_control_set_screen_origin(state['native'],req.x,req.y)
                self._respond(client,req,state,input_result=accepted)
                return
            if req.operation == 2 and self.idle():
                state['starting'] = True
                self.pending.append(lambda: self.track(state, req.x, req.y, req.modifiers))
            elif req.operation in (3, 4) and self._tracking(state):
                self.native.nxs_control_send(state['native'], 0 if req.operation == 3 else 1, req.x, req.y, req.modifiers)
            elif req.operation == 6:
                state['destroy'] = True
                if self._tracking(state):
                    self.native.nxs_control_send(state['native'], 0, -1, -1, 0)
                    self.native.nxs_control_send(state['native'], 1, -1, -1, 0)
        self._respond(client, req, state)

    def popup_message(self,client,data):
        if len(data)<C.sizeof(ControlPopupRequest):return
        req=ControlPopupRequest.from_buffer_copy(data)
        if req.magic!=MAGIC or req.kind!=6 or req.text_size!=len(data)-C.sizeof(req) or req.text_size>65536 or req.count>65536:
            self._respond(client,req);return
        state=self.controls.get((req.process,req.control,req.kind))
        if not state or state['destroy'] or not self.popup_capabilities:
            self._respond(client,req);return
        offset=C.sizeof(req);items=(PopupItem*req.count)()
        for index in range(req.count):
            if offset+8>len(data):self._respond(client,req);return
            flags=int.from_bytes(data[offset:offset+4],'little');size=int.from_bytes(data[offset+4:offset+8],'little');offset+=8
            if flags&~3 or size>65536 or offset+size>len(data):self._respond(client,req);return
            title=data[offset:offset+size];offset+=size
            try:title.decode('utf-8')
            except UnicodeDecodeError:self._respond(client,req);return
            if b'\0' in title:self._respond(client,req);return
            items[index]=PopupItem(C.sizeof(PopupItem),title,flags&1,bool(flags&2))
        if offset!=len(data):self._respond(client,req);return
        accepted=self.native.nxs_control_popup_items(state['native'],items,req.count,req.selected)
        if accepted:self.log('native-popup-model',process=req.process,control=req.control,count=req.count,selected=req.selected)
        self._respond(client,req,state,pixels=bool(accepted),input_result=accepted)

    def input_message(self, client, data):
        if len(data) < C.sizeof(ControlInputRequest):
            return
        req = ControlInputRequest.from_buffer_copy(data)
        if req.magic != MAGIC or req.text_size + req.unmodified_size != len(data) - C.sizeof(req):
            return
        state = self.controls.get((req.process, req.control, req.kind))
        if not state or state['destroy'] or req.text_size + req.unmodified_size > 65536:
            self._respond(client, req)
            return
        result = 0
        if req.operation == 7 and self.input_capabilities & 1:
            result = self.native.nxs_control_focus(state['native'], req.focused)
            self.log('native-form-focus', process=req.process, control=req.control, kind=req.kind,
                     focused=self.native.nxs_control_focused(state['native']), accepted=result)
        elif req.operation == 8 and self.input_capabilities & 2:
            payload = data[C.sizeof(req):]
            text, unmodified = payload[:req.text_size], payload[req.text_size:]
            if b'\0' in payload:
                self._respond(client, req, state)
                return
            try:
                text.decode('utf-8'); unmodified.decode('utf-8')
            except UnicodeDecodeError:
                self._respond(client, req, state)
                return
            event = KeyEvent(C.sizeof(KeyEvent), req.type, req.modifiers, req.key, req.repeat,
                             text, unmodified if req.unmodified_size else None)
            result = self.native.nxs_control_key(state['native'], C.byref(event))
            # Text is deliberately excluded from the diagnostic log.
            self.log('native-form-key', process=req.process, control=req.control, kind=req.kind,
                     type=req.type, result=result, actions=state['actions'])
        self._respond(client, req, state, input_result=result)

    def track(self, state, x, y, modifiers):
        if state['destroy']:
            state['starting'] = False
            return
        self.active, state['starting'] = state, False
        self.log('native-form-press', process=state['key'][0], control=state['key'][1], kind=state['key'][2], x=x, y=y)
        try:
            self.native.nxs_control_track(state['native'], x, y, modifiers)
        finally:
            self.active = None
        self.log('native-form-release', process=state['key'][0], control=state['key'][1], kind=state['key'][2], actions=state['actions'])

    def disconnect(self, client):
        for state in self.controls.values():
            if state['client'] is client:
                state['destroy'] = True
                if self._tracking(state):
                    self.native.nxs_control_send(state['native'], 0, -1, -1, 0)
                    self.native.nxs_control_send(state['native'], 1, -1, -1, 0)

    def cleanup(self):
        for key, state in list(self.controls.items()):
            if state['destroy'] and self.native.nxs_control_destroy(state['native']):
                if key[2] == 5:
                    self.log('native-progress-destroy', process=key[0], control=key[1])
                elif key[2]==6:
                    self.log('native-popup-destroy',process=key[0],control=key[1])
                del self.controls[key]
                del self.contexts[state['context']]

    def close(self):
        for state in self.controls.values():
            self.native.nxs_control_destroy(state['native'])
