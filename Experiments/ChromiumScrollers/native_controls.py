"""Transport for the shared native UI provider; contains no widget implementation."""
import ctypes as C
import itertools
import math
import os
import fcntl
import time
import select
import socket
from pathlib import Path

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
class ControlTextRequest(C.Structure):
    _fields_ = ControlRequest._fields_[:7]+[('selection_start',C.c_uint64),
        ('selection_length',C.c_uint64),('editable',C.c_int32),('padding',C.c_uint32)]
class TextModel(C.Structure):
    _fields_ = [('size',C.c_uint32),('text',C.c_char_p),('selection_start',C.c_uint64),
        ('selection_length',C.c_uint64),('editable',C.c_int)]
class TextState(C.Structure):
    _fields_ = [('size',C.c_uint32),('selection_start',C.c_uint64),('selection_length',C.c_uint64),
        ('marked_start',C.c_uint64),('marked_length',C.c_uint64),('editing',C.c_int),
        ('editable',C.c_int),('secure',C.c_int)]
class TextResponse(C.Structure):
    _fields_ = [('text_size',C.c_uint32),('flags',C.c_uint32),('selection_start',C.c_uint64),
        ('selection_length',C.c_uint64),('marked_start',C.c_uint64),('marked_length',C.c_uint64)]
class TextEdit(C.Structure):
    _fields_=[('size',C.c_uint32),('range_start',C.c_uint64),('range_length',C.c_uint64),
        ('selection_start',C.c_uint64),('selection_length',C.c_uint64),('replacement',C.c_char_p),('command',C.c_char_p)]
class NativeTextEdit(C.Structure):
    _fields_=[('magic',C.c_uint32),('size',C.c_uint32),('process',C.c_uint32),('kind',C.c_uint32),
        ('control',C.c_uint64),('serial',C.c_uint64),('range_start',C.c_uint64),('range_length',C.c_uint64),
        ('selection_start',C.c_uint64),('selection_length',C.c_uint64),('text_size',C.c_uint32),('command_size',C.c_uint32)]
class NativeTextDecision(C.Structure):
    _fields_=[('magic',C.c_uint32),('accepted',C.c_uint32),('serial',C.c_uint64)]
TextShouldChange=C.CFUNCTYPE(C.c_int,C.c_void_p,C.POINTER(TextEdit))
TEXT_EDIT_MAGIC=0x4e585445
COMMAND_MAGIC=0x4e58434d
MENU_COMMAND_MAGIC=0x4e584d43
MENU_ACK_MAGIC=0x4e584d41
class NativeMenuAck(C.Structure):
    _fields_=[('magic',C.c_uint32),('request_sequence',C.c_uint32),('serial',C.c_uint64)]
class NativeCommand(C.Structure):
    _fields_=[('magic',C.c_uint32),('size',C.c_uint32),('process',C.c_uint32),('kind',C.c_uint32),
        ('control',C.c_uint64),('serial',C.c_uint64),('phase',C.c_uint32),('command_size',C.c_uint32)]
class NativeCommandDecision(C.Structure):
    _fields_=[('magic',C.c_uint32),('result',C.c_int32),('serial',C.c_uint64)]
CommandFilter=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_char_p,C.c_uint)
class PopupItem(C.Structure):
    _fields_ = [('size',C.c_uint32),('title',C.c_char_p),('enabled',C.c_int),('separator',C.c_int)]
class ControlRect(C.Structure):
    _fields_ = [('x',C.c_double),('y',C.c_double),('width',C.c_double),('height',C.c_double)]
class TabItem(C.Structure):
    _fields_=[('size',C.c_uint32),('identifier',C.c_uint64),('title',C.c_char_p),('tooltip',C.c_char_p)]
class TabState(C.Structure):
    _fields_=[('size',C.c_uint32),('count',C.c_uint32),('selected_index',C.c_int32),('reserved',C.c_uint32),('selected',C.c_uint64),('content',ControlRect)]
class ControlTabsRequest(C.Structure):
    _fields_=ControlRequest._fields_[:7]+[('count',C.c_uint32),('padding',C.c_uint32),('selected',C.c_uint64),('scale',C.c_double)]
class ControlTabItemRequest(C.Structure):
    _fields_=ControlRequest._fields_[:7]+[('identifier',C.c_uint64)]
class TabWireState(C.Structure):
    _fields_=[('count',C.c_uint32),('selected_index',C.c_int32),('selected',C.c_uint64),('content',ControlRect)]
class RadioItem(C.Structure):
    _fields_=[('size',C.c_uint32),('identifier',C.c_uint64),('title',C.c_char_p),('enabled',C.c_int)]
class RadioState(C.Structure):
    _fields_=[('size',C.c_uint32),('count',C.c_uint32),('rows',C.c_uint32),('columns',C.c_uint32),
        ('selected',C.c_uint64),('key_cell',C.c_uint64),('actions',C.c_uint64)]
class RadioWireState(C.Structure):
    _fields_=[('count',C.c_uint32),('rows',C.c_uint32),('columns',C.c_uint32),('reserved',C.c_uint32),
        ('selected',C.c_uint64),('key_cell',C.c_uint64),('actions',C.c_uint64)]
class ControlRadioRequest(C.Structure):
    _fields_=ControlRequest._fields_[:7]+[('count',C.c_uint32),('columns',C.c_uint32),
        ('selected',C.c_uint64),('key_cell',C.c_uint64),('scale',C.c_double)]
class ControlRadioItemRequest(C.Structure):
    _fields_=ControlRequest._fields_[:7]+[('identifier',C.c_uint64),('width',C.c_double),('height',C.c_double)]
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

class TextViewport(C.Structure):
    _fields_ = [('size',C.c_uint32),('visible',ControlRect),('content',Size)]
class Point(C.Structure):
    _fields_ = [('x',C.c_double),('y',C.c_double)]
class TextGeometry(C.Structure):
    _fields_ = [('size',C.c_uint32),('clip',ControlRect),('client',Size),('minimum',Point),('maximum',Point)]
class WheelEvent(C.Structure):
    _fields_=[('size',C.c_uint32),('modifiers',C.c_uint32),('x',C.c_double),('y',C.c_double),('delta_x',C.c_double),('delta_y',C.c_double)]

ControlChanged = C.CFUNCTYPE(None, C.c_void_p, C.c_int, C.POINTER(ControlState))

class NativeControlServer:
    def __init__(self, native, bitmap_type, response_type, pump_type, dispatch, pending, send, idle, log):
        self.native, self.response_type = native, response_type
        self.pending, self._send, self.idle, self.log = pending, send, idle, log
        self.reply_barriers={};self.menu_reply_barriers={}
        self.dispatch=dispatch
        self.input_owner=None
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
        if hasattr(native,'nxs_control_backing_scale'):
            native.nxs_control_backing_scale.argtypes=[C.c_void_p]
            native.nxs_control_backing_scale.restype=C.c_double
        native.nxs_control_track.argtypes = [C.c_void_p, C.c_double, C.c_double, C.c_uint]
        native.nxs_control_send.argtypes = [C.c_void_p, C.c_int, C.c_double, C.c_double, C.c_uint]
        self.input_capabilities = 0
        self.pointer_capabilities=0
        self.wheel_capabilities=0
        self.tab_capabilities=0
        self.radio_capabilities=0
        if hasattr(native,'nxs_control_radio_capabilities'):
            native.nxs_control_radio_capabilities.restype=C.c_uint
            self.radio_capabilities=native.nxs_control_radio_capabilities()
            # The wire needs native cell sizing and bounded model replacement.
            # Earlier C-only group providers remain usable by their old clients.
            if self.radio_capabilities&3!=3:self.radio_capabilities=0
            if self.radio_capabilities:
                native.nxs_control_radio_items.argtypes=[C.c_void_p,C.POINTER(RadioItem),C.c_uint32,C.c_uint32,C.c_uint64,C.c_uint64]
                native.nxs_control_radio_items.restype=C.c_int
                native.nxs_control_radio_state.argtypes=[C.c_void_p];native.nxs_control_radio_state.restype=RadioState
                native.nxs_control_radio_item_rect.argtypes=[C.c_void_p,C.c_uint64];native.nxs_control_radio_item_rect.restype=ControlRect
                if self.radio_capabilities&2:
                    native.nxs_control_radio_cell_size.argtypes=[C.c_void_p,C.c_double,C.c_double]
                    native.nxs_control_radio_cell_size.restype=C.c_int
        if hasattr(native,'nxs_control_tab_capabilities'):
            native.nxs_control_tab_capabilities.restype=C.c_uint
            self.tab_capabilities=native.nxs_control_tab_capabilities()
            if self.tab_capabilities:
                native.nxs_control_tab_items.argtypes=[C.c_void_p,C.POINTER(TabItem),C.c_uint32,C.c_uint64]
                native.nxs_control_tab_items.restype=C.c_int
                native.nxs_control_tab_state.argtypes=[C.c_void_p];native.nxs_control_tab_state.restype=TabState
                native.nxs_control_tab_item_rect.argtypes=[C.c_void_p,C.c_uint64];native.nxs_control_tab_item_rect.restype=ControlRect
        if hasattr(native,'nxs_control_wheel_capabilities'):
            native.nxs_control_wheel_capabilities.restype=C.c_uint
            self.wheel_capabilities=native.nxs_control_wheel_capabilities()
            if self.wheel_capabilities:
                native.nxs_control_wheel.argtypes=[C.c_void_p,C.POINTER(WheelEvent)]
                native.nxs_control_wheel.restype=C.c_int
        if hasattr(native,'nxs_control_pointer_capabilities'):
            native.nxs_control_pointer_capabilities.restype=C.c_uint
            self.pointer_capabilities=native.nxs_control_pointer_capabilities()
            native.nxs_control_track_clicks.argtypes=[C.c_void_p,C.c_double,C.c_double,C.c_uint,C.c_uint]
            native.nxs_control_track_clicks.restype=C.c_int
        self.event_capabilities, self.event_deadline = 0, -1
        self.generations = {}
        self.notifiers = {}
        self.range_capabilities=0
        self.popup_capabilities=0
        self.popup_title_capabilities=0
        self.popup_open_capabilities=0
        self.text_capabilities=0
        if hasattr(native,'nxs_control_text_command'):
            native.nxs_control_text_command.argtypes=[C.c_void_p]
            native.nxs_control_text_command.restype=C.c_char_p
        self.text_filters={}
        self.edit_serial=itertools.count(1)
        self.text_filter=TextShouldChange(self._before_text_edit)
        self.command_capabilities=0
        self.command_filter=CommandFilter(self._command)
        if hasattr(native,'nxs_control_command_capabilities'):
            native.nxs_control_command_capabilities.restype=C.c_uint
            self.command_capabilities=native.nxs_control_command_capabilities()
            native.nxs_control_command_filter.argtypes=[C.c_void_p,CommandFilter,C.c_void_p]
            native.nxs_control_command_filter.restype=C.c_int
        if hasattr(native,'nxs_control_text_capabilities'):
            native.nxs_control_text_capabilities.argtypes=[]
            native.nxs_control_text_capabilities.restype=C.c_uint
            self.text_capabilities=native.nxs_control_text_capabilities()
            native.nxs_control_text_sync.argtypes=[C.c_void_p,C.POINTER(TextModel)]
            native.nxs_control_text_sync.restype=C.c_int
            native.nxs_control_text_get.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(TextState)]
            native.nxs_control_text_get.restype=C.c_size_t
            if self.text_capabilities&2:
                native.nxs_control_text_filter.argtypes=[C.c_void_p,TextShouldChange,C.c_void_p]
                native.nxs_control_text_filter.restype=C.c_int
        self.text_kinds=(7,8,9) if self.text_capabilities&8 else (7,8)
        if self.text_capabilities&16:
            native.nxs_control_text_viewport.argtypes=[C.c_void_p]
            native.nxs_control_text_viewport.restype=TextViewport
            native.nxs_control_text_scroll.argtypes=[C.c_void_p,C.c_double,C.c_double]
            native.nxs_control_text_scroll.restype=C.c_int
        if self.text_capabilities&32:
            native.nxs_control_text_geometry.argtypes=[C.c_void_p,C.POINTER(TextGeometry)]
            native.nxs_control_text_geometry.restype=C.c_int
        if hasattr(native,'nxs_control_popup_open_capabilities'):
            native.nxs_control_popup_open_capabilities.argtypes=[]
            native.nxs_control_popup_open_capabilities.restype=C.c_uint
            self.popup_open_capabilities=native.nxs_control_popup_open_capabilities()
            native.nxs_control_popup_open.argtypes=[C.c_void_p,C.c_int]
            native.nxs_control_popup_open.restype=C.c_int
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
        if hasattr(native,'nxs_control_popup_title_capabilities'):
            native.nxs_control_popup_title_capabilities.restype=C.c_uint
            self.popup_title_capabilities=native.nxs_control_popup_title_capabilities()
            native.nxs_control_popup_title.argtypes=[C.c_void_p,C.c_char_p]
            native.nxs_control_popup_title.restype=C.c_int
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
        self.notification_capabilities=int(bool(self.event_capabilities and self.source_capabilities and hasattr(os,'pidfd_open')))
        from native_menus import NativeMenuServer
        self.menus=NativeMenuServer(self,pump_type)

    def send(self,client,response,data=b''):
        barrier=self.reply_barriers.get((client,int(response.reserved)&0xffffffff))
        if barrier is not None:
            barrier['replies'].append((self.response_type.from_buffer_copy(bytes(response)),bytes(data)))
            self.log('native-menu-reply-deferred',process=barrier['process'],serial=barrier['serial'],sequence=barrier['sequence'])
        else:self._send(client,response,data)

    def complete_menu_reply(self,process,serial):
        barrier=self.menu_reply_barriers.pop((process,serial),None)
        if barrier:
            self.reply_barriers.pop((barrier['client'],barrier['sequence']),None)
            for response,data in barrier['replies']:self._send(barrier['client'],response,data)
            self.log('native-menu-reply-resumed',process=process,serial=serial,replies=len(barrier['replies']))

    def drop_menu_replies(self,process=None,client=None):
        for key,barrier in list(self.menu_reply_barriers.items()):
            if key[0]==process or barrier['client'] is client:
                del self.menu_reply_barriers[key];self.reply_barriers.pop((barrier['client'],barrier['sequence']),None)

    def menu_acknowledge(self,state,entry,serial,deadline):
        process=state['key'][0];owner=self.notifiers.get(process)
        if not owner:return False
        connection=entry['socket']
        while not state['destroy'] and self.text_filters.get(process) is entry and time.monotonic()<deadline:
            ready,_,_=select.select([connection,owner['lifetime']],[],[],max(0,deadline-time.monotonic()))
            if owner['lifetime'] in ready:self.owner_exited(owner['lifetime']);return False
            if connection not in ready:break
            data=connection.recv(C.sizeof(NativeMenuAck)+1,socket.MSG_DONTWAIT)
            if len(data)!=C.sizeof(NativeMenuAck):break
            ack=NativeMenuAck.from_buffer_copy(data)
            if ack.magic==MENU_ACK_MAGIC and ack.serial==serial:
                if ack.request_sequence:
                    barrier=dict(client=state['client'],pid=owner['pid'],process=process,serial=serial,sequence=ack.request_sequence,replies=[])
                    key=(state['client'],ack.request_sequence)
                    if key in self.reply_barriers:break
                    self.reply_barriers[key]=barrier;self.menu_reply_barriers[(process,serial)]=barrier
                return True
            decision=NativeCommandDecision.from_buffer_copy(data)
            if decision.magic not in (TEXT_EDIT_MAGIC,COMMAND_MAGIC,MENU_COMMAND_MAGIC) or decision.serial>=serial or decision.result not in ((-1,0,1) if decision.magic==COMMAND_MAGIC else (0,1)):break
            if decision.magic==MENU_COMMAND_MAGIC:self.complete_menu_reply(process,decision.serial)
        if self.text_filters.get(process) is entry:self.fail_text_filter(entry)
        return False

    def remove_notifier(self,process):
        self.remove_text_filter(process)
        entry=self.notifiers.pop(process,None)
        if entry:
            assert self.native.nxs_native_ui_source_destroy(entry['source'])
            os.close(entry['lifetime']);os.close(entry['descriptor'])

    def remove_text_filter(self,process):
        self.menus.owner_removed(process)
        entry=self.text_filters.pop(process,None)
        if entry:
            if entry.get('source'):assert self.native.nxs_native_ui_source_destroy(entry['source'])
            if entry.get('socket'):entry['socket'].close()
        self.update_text_filters(process)

    def fail_text_filter(self,entry):
        # EOF must stop waking the native loop. Retain a failed gate until
        # explicit removal so losing validation never silently permits edits.
        if entry.get('source'):assert self.native.nxs_native_ui_source_destroy(entry['source'])
        if entry.get('socket'):entry['socket'].close()
        entry.update(source=None,socket=None)
        for process,registered in self.text_filters.items():
            if registered is entry:self.menus.owner_removed(process)

    def update_text_filters(self,process):
        for state in self.controls.values():
            if state['key'][0]!=process or state['key'][2] not in self.text_kinds:continue
            enabled=process in self.text_filters
            if state.get('text_filter',False)!=enabled and self.native.nxs_control_text_filter(state['native'],self.text_filter if enabled else TextShouldChange(),state['context']):
                state['text_filter']=enabled
            commands=bool(self.text_filters.get(process,{}).get('commands'))
            if self.command_capabilities and state.get('command_filter',False)!=commands:
                if self.native.nxs_control_command_filter(state['native'],self.command_filter if commands else CommandFilter(),state['context']):
                    state['command_filter']=commands

    def text_filter_message(self,client,req,descriptors,sender_pid):
        accepted=0;owner=self.notifiers.get(req.process)
        if (self.text_capabilities&2 and owner and owner['client'] is client and owner['pid']==sender_pid and
            not req.kind and not req.control and not req.text_size):
            if req.operation==20 and not descriptors:
                self.remove_text_filter(req.process);accepted=1
            elif req.operation in (23,24) and not descriptors and req.state in (0,1) and (
                    self.command_capabilities if req.operation==23 else self.menus.capabilities):
                entry=self.text_filters.get(req.process)
                if entry:
                    entry['commands' if req.operation==23 else 'menus']=bool(req.state)
                    if req.operation==24 and not req.state:self.menus.owner_removed(req.process)
                    self.update_text_filters(req.process);accepted=1
            elif req.operation==19 and len(descriptors)==1:
                connection=None;source=None
                try:
                    connection=socket.socket(fileno=os.dup(descriptors[0]))
                    if connection.family!=socket.AF_UNIX or connection.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_SEQPACKET:
                        raise ValueError('Unsupported callback endpoint')
                    connection.getpeername() # A connected endpoint, not a listener.
                    source=self.native.nxs_native_ui_source_create(connection.fileno())
                    if not source:raise ValueError('Cannot watch callback endpoint')
                    self.remove_text_filter(req.process)
                    self.text_filters[req.process]=dict(socket=connection,source=source)
                    connection=None;source=None
                    self.update_text_filters(req.process);accepted=1
                except (OSError,ValueError):pass
                finally:
                    if source:self.native.nxs_native_ui_source_destroy(source)
                    if connection:connection.close()
        self.log('native-text-filter',process=req.process,operation=req.operation,accepted=accepted)
        self._respond(client,req,input_result=accepted)

    def _before_text_edit(self,context,pointer):
        # This callback runs on the actual native editor's stack. Keep AppKit
        # and other embedding requests responsive while its owner validates.
        entry=None
        try:
            state=self.contexts[context];process,control,kind=state['key']
            entry=self.text_filters.get(process)
            if not entry or not entry.get('socket') or state['destroy']:return 0
            edit=pointer.contents;text=edit.replacement or b'';command=edit.command or b''
            if len(text)>65536 or len(command)>256:return 0
            serial=next(self.edit_serial)
            entry.update(serial=serial,waiting=True)
            proposal=NativeTextEdit(TEXT_EDIT_MAGIC,C.sizeof(NativeTextEdit)+len(text)+len(command),
                process,kind,control,serial,edit.range_start,edit.range_length,
                edit.selection_start,edit.selection_length,len(text),len(command))
            return self._owner_decision(state,entry,bytes(proposal)+text+command,serial,TEXT_EDIT_MAGIC)
        except Exception as error:
            self.log('native-text-filter-failed',exception=type(error).__name__)
            if 'entry' in locals() and entry and entry.get('socket'):self.fail_text_filter(entry)
            return 0
        finally:
            if entry:entry['waiting']=False

    def _owner_decision(self,state,entry,payload,serial,magic):
        connection=entry['socket'];process=state['key'][0]
        if connection.send(payload,socket.MSG_DONTWAIT|socket.MSG_NOSIGNAL)!=len(payload):return 0
        if magic==MENU_COMMAND_MAGIC:
            self.log('native-menu-awaiting-owner',process=process,serial=serial)
            self.invalidate(process)
        deadline=time.monotonic()+2
        if magic==MENU_COMMAND_MAGIC and not self.menu_acknowledge(state,entry,serial,deadline):return 0
        while not state['destroy'] and self.text_filters.get(process) is entry and time.monotonic()<deadline:
            if select.select([connection],[],[],0)[0]:
                data=connection.recv(C.sizeof(NativeCommandDecision)+1,socket.MSG_DONTWAIT)
                if len(data)!=C.sizeof(NativeCommandDecision):self.fail_text_filter(entry);return 0
                decision=NativeCommandDecision.from_buffer_copy(data)
                if (decision.magic not in (TEXT_EDIT_MAGIC,COMMAND_MAGIC,MENU_COMMAND_MAGIC) or decision.serial>serial or
                    decision.result not in ((-1,0,1) if decision.magic==COMMAND_MAGIC else (0,1))):
                    self.fail_text_filter(entry);return 0
                if decision.serial==serial:
                    if decision.magic!=magic:self.fail_text_filter(entry);return 0
                    if decision.magic==MENU_COMMAND_MAGIC:self.complete_menu_reply(process,serial)
                    return decision.result
                if decision.magic==MENU_COMMAND_MAGIC:self.complete_menu_reply(process,decision.serial)
            self.native.nxs_native_ui_dispatch_events(min(.1,max(0,deadline-time.monotonic())))
            self.dispatch(0)
        if not state['destroy'] and self.text_filters.get(process) is entry:self.fail_text_filter(entry)
        return 0

    def _command(self,context,selector,phase):
        entry=None
        try:
            state=self.contexts[context];process,control,kind=state['key'];entry=self.text_filters.get(process)
            if not entry or not entry.get('commands'):return -1
            if not entry.get('socket') or state['destroy'] or not selector or len(selector)>256 or phase>1:return 0
            serial=next(self.edit_serial);entry.update(serial=serial,waiting=True)
            proposal=NativeCommand(COMMAND_MAGIC,C.sizeof(NativeCommand)+len(selector),process,kind,control,serial,phase,len(selector))
            result=self._owner_decision(state,entry,bytes(proposal)+selector,serial,COMMAND_MAGIC)
            self.log('native-command',process=process,control=control,kind=kind,phase=phase,result=result)
            return result
        except Exception as error:
            self.log('native-command-failed',exception=type(error).__name__)
            if entry and entry.get('socket'):self.fail_text_filter(entry)
            return 0
        finally:
            if entry:entry['waiting']=False

    def notification_fds(self):return [entry['lifetime'] for entry in self.notifiers.values()]

    def text_filter_fds(self):
        return [entry['socket'].fileno() for entry in self.text_filters.values()
                if entry.get('socket') and not entry.get('waiting')]

    def text_filter_ready(self,descriptor):
        for entry in self.text_filters.values():
            if not entry.get('socket') or entry['socket'].fileno()!=descriptor:continue
            try:
                data=entry['socket'].recv(C.sizeof(NativeTextDecision)+1,socket.MSG_DONTWAIT)
                if len(data)!=C.sizeof(NativeTextDecision):self.fail_text_filter(entry);return
                decision=NativeCommandDecision.from_buffer_copy(data)
                # Validation can finish after its frame was removed. Drain the
                # late decision so it cannot continuously wake NSRunLoop.
                if decision.magic not in (TEXT_EDIT_MAGIC,COMMAND_MAGIC,MENU_COMMAND_MAGIC) or decision.serial>entry.get('serial',0) or decision.result not in ((-1,0,1) if decision.magic==COMMAND_MAGIC else (0,1)):
                    self.fail_text_filter(entry)
                elif decision.magic==MENU_COMMAND_MAGIC:
                    process=next(p for p,e in self.text_filters.items() if e is entry)
                    self.complete_menu_reply(process,decision.serial)
            except BlockingIOError:pass
            except OSError:self.fail_text_filter(entry)
            return

    def owner_exited(self,descriptor):
        for process,entry in list(self.notifiers.items()):
            if entry['lifetime']==descriptor:
                self.remove_notifier(process)
                self.drop_menu_replies(process=process)
                for state in self.controls.values():
                    if state['key'][0]==process:self.destroy_later(state)
                self.log('native-notifier-owner-exit',process=process,active=len(self.notifiers))
                break

    def signal(self,process):
        notifier=self.notifiers.get(process)
        if notifier:
            try:os.eventfd_write(notifier['descriptor'],1)
            except BlockingIOError:pass # Already readable: invalidations coalesce.

    def invalidate(self,process):
        self.generations[process]=self.generations.get(process,0)+1
        self.signal(process)

    def notification_message(self,client,req,descriptors,sender_pid):
        accepted=0;reason="request-or-owner"
        previous=self.notifiers.get(req.process)
        owned=not previous or (previous['client'] is client and previous['pid']==sender_pid)
        if req.kind==0 and req.control==0 and not req.text_size and owned:
            if req.operation==16 and not descriptors:
                self.remove_notifier(req.process)
                accepted=1
            elif (req.operation==15 and self.notification_capabilities and sender_pid and sender_pid>0 and len(descriptors)==1 and
                  math.isfinite(req.value) and 0<=req.value<=self.generations.get(req.process,0)):
                reason="eventfd-validation"
                descriptor=descriptors[0]
                try:
                    # Only write to a caller-owned, nonblocking eventfd. Never
                    # accept a file/socket or change its shared descriptor flags.
                    info=dict(line.split(':',1) for line in Path('/proc/self/fdinfo/'+str(descriptor)).read_text().splitlines() if ':' in line)
                    identity=int(info['eventfd-id'])
                    valid=(os.readlink('/proc/self/fd/'+str(descriptor))=='anon_inode:[eventfd]' and
                        fcntl.fcntl(descriptor,fcntl.F_GETFL)&os.O_NONBLOCK and int(info['eventfd-semaphore'])==0 and
                        all(process==req.process or entry['identity']!=identity for process,entry in self.notifiers.items()))
                    if valid:
                        # Kernel credentials identify the real sender even when
                        # sandboxed renderers all see namespace-local PID 1.
                        # pidfd readiness also covers crashes while the shared
                        # browser connection remains open in other processes.
                        reason="notification-source"
                        lifetime=os.pidfd_open(sender_pid,0)
                        source=self.native.nxs_native_ui_source_create(lifetime)
                        if not source:os.close(lifetime);raise OSError('Cannot watch notification owner')
                        try:duplicate=os.dup(descriptor)
                        except OSError:
                            self.native.nxs_native_ui_source_destroy(source);os.close(lifetime);raise
                        self.remove_notifier(req.process)
                        self.notifiers[req.process]=dict(descriptor=duplicate,identity=identity,client=client,
                            pid=sender_pid,lifetime=lifetime,source=source)
                        accepted=1
                        # Cover the race between the renderer's generation
                        # snapshot and registration without polling or timers.
                        if self.generations.get(req.process,0)>req.value:self.signal(req.process)
                except (OSError,KeyError,ValueError) as error:reason=type(error).__name__+":"+str(error)
        if not accepted:self.log('native-notifier-rejected',reason=reason,sender_pid=sender_pid,descriptors=len(descriptors))
        self.log('native-notifier',process=req.process,operation=req.operation,accepted=accepted,
                 active=len(self.notifiers))
        self._respond(client,req,input_result=accepted)

    def dispatch_events(self,maximum_wait=0):
        if not self.event_capabilities:
            return -1
        self.event_deadline = self.native.nxs_native_ui_dispatch_events(maximum_wait)
        for state in self.controls.values():
            if state['key'][2]==6 and not state['destroy']:
                visible=bool(self.native.nxs_control_popup_state(state['native']).visible)
                if visible!=state.get('popup_visible',False):
                    state['popup_visible']=visible
                    process,control,kind=state['key']
                    self.invalidate(process)
                    self.log('native-popup-visibility',process=process,control=control,visible=visible,generation=self.generations[process])
            if state['destroy'] or state.get('invalidated'):
                continue
            if self.native.nxs_control_needs_display(state['native']):
                state['invalidated'] = True
                process, control, kind = state['key']
                self.invalidate(process)
                self.log('native-form-invalidation', process=process, control=control, kind=kind,
                         generation=self.generations[process])
        return self.event_deadline

    def prepare(self):
        # AppKit loads shared fonts/images lazily on its first draw. Finish
        # those native draws before publishing the service, rather than make
        # an application's first paint wait inside a bounded RPC.
        kinds=list(range(1,7 if self.popup_capabilities else 6))
        if self.text_capabilities:kinds.extend(self.text_kinds)
        if self.tab_capabilities:kinds.append(10)
        for kind in kinds:self.preferred(kind)

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
                scale=self.native.nxs_control_backing_scale(pointer) if hasattr(self.native,'nxs_control_backing_scale') else 0
                if not self.native.nxs_control_draw(pointer,scale or 1).pixels:
                    raise RuntimeError('Native control preparation failed')
            finally:
                self.native.nxs_control_destroy(pointer)
        return self.metric_cache[kind]

    def _changed(self, context, event, native_state):
        state = self.contexts[context]
        if state['destroy']:
            return
        state['actions'] += 1
        state['edits']=state.get('edits',0)+int(event==3)
        state['activations']=state.get('activations',0)+int(event==1)
        process=state['key'][0]
        timestamp=time.monotonic_ns()
        self.invalidate(process)
        self.log('native-form-action', process=state['key'][0], control=state['key'][1],
                 kind=state['key'][2], action=event, count=state['actions'],
                 value=native_state.contents.value, state=native_state.contents.state,monotonic_ns=timestamp)

    def _tracking(self, state):
        return bool(state.get('starting') or self.native.nxs_control_state(state['native']).tracking)

    def _respond(self, client, req, state=None, pixels=False, input_result=0, rectangle=None, payload=b'',viewport=None,image=None):
        response = self.response_type()
        response.magic, response.reserved = MAGIC, req.reserved
        response.parts[3].x = input_result
        response.parts[3].width = self.input_capabilities
        response.parts[4].x = self.generations.get(req.process, 0)
        response.parts[4].y = self.event_deadline
        response.parts[4].width = self.event_capabilities
        response.parts[5].width = self.range_capabilities
        response.parts[5].height = self.popup_capabilities
        response.parts[2].y = self.tab_capabilities
        response.parts[1].x = self.popup_title_capabilities
        response.parts[1].y = self.radio_capabilities
        data = payload
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
            if req.kind in self.text_kinds:
                response.parts[2].width=state.get('edits',0)
                response.parts[2].height=state.get('activations',0)
            if self.input_capabilities & 1:
                response.parts[3].y = self.native.nxs_control_focused(state['native'])
            if req.kind==6 and self.popup_capabilities:
                popup=self.native.nxs_control_popup_state(state['native'])
                response.parts[5].y=popup.highlighted
                frame=rectangle if rectangle is not None else popup.frame
                for field in ('x','y','width','height'):setattr(response.parts[6],field,getattr(frame,field))
            if req.kind==10 and self.tab_capabilities:
                tabs=self.native.nxs_control_tab_state(state['native']);response.parts[5].y=tabs.count
                frame=rectangle if rectangle is not None else tabs.content
                for field in ('x','y','width','height'):setattr(response.parts[6],field,getattr(frame,field))
            if req.kind==12 and rectangle is not None:
                for field in ('x','y','width','height'):setattr(response.parts[6],field,getattr(rectangle,field))
            if pixels:
                bitmap = self.native.nxs_control_draw(state['native'], state.get('scale',1))
                if bitmap.pixels:
                    response.width, response.height, response.stride = bitmap.width, bitmap.height, bitmap.stride
                    data = C.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
                    state['invalidated'] = False
        if image is not None:
            response.width,response.height,response.stride,data=image
        if viewport is not None:
            for field in ('x','y','width','height'):setattr(response.parts[5],field,getattr(viewport.visible,field))
            response.parts[6].width=viewport.content.width;response.parts[6].height=viewport.content.height
        self.send(client, response, data)

    def message(self, client, data, descriptors=(),sender_pid=None):
        if descriptors and (len(data)<8 or int.from_bytes(data[4:8],'little') not in (15,19)):return
        if len(data)>=8 and int.from_bytes(data[4:8],'little') in (43,45,46):
            self.radio_message(client,data)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little') in (36,38):
            self.tab_message(client,data)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little') in (25,26,27,28,29,30):
            self.menus.message(client,data,sender_pid)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little')==31:
            if len(data)!=C.sizeof(ControlRequest):return
            req=ControlRequest.from_buffer_copy(data);barrier=self.menu_reply_barriers.get((req.process,req.control))
            if req.magic==MAGIC and not descriptors and not req.kind and not req.text_size and barrier and barrier['client'] is client and barrier['pid']==sender_pid:
                self.complete_menu_reply(req.process,req.control)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little')==17:
            self.text_message(client,data)
            return
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
            self.input_message(client, data,sender_pid)
            return
        if len(data) < C.sizeof(ControlRequest):
            return
        req = ControlRequest.from_buffer_copy(data)
        if req.magic != MAGIC or req.text_size != len(data) - C.sizeof(req) or req.text_size > 65536:
            return
        if not all(math.isfinite(x) for x in (req.x, req.y)):
            self._respond(client, req)
            return
        if req.operation in (15,16):
            self.notification_message(client,req,descriptors,sender_pid)
            return
        if req.operation in (19,20,23,24):
            self.text_filter_message(client,req,descriptors,sender_pid)
            return
        if req.operation == 9:
            self.dispatch_events()
            self._respond(client, req)
            return
        key = req.process, req.control, req.kind
        state = self.controls.get(key)
        if req.kind in (10,12) and state and state['client'] is not client:
            self._respond(client,req);return
        if state and state['destroy'] and req.operation != 5:
            self._respond(client, req)
            return
        if req.operation == 1:
            if (req.kind not in (*range(1,11),12) or (req.kind==12 and not self.radio_capabilities) or (req.kind==10 and not self.tab_capabilities) or (req.kind==9 and not self.text_capabilities&8) or (req.kind==6 and not self.popup_capabilities) or
                (req.kind in self.text_kinds and not self.text_capabilities) or
                not all(math.isfinite(x) for x in (req.width, req.height, req.minimum, req.maximum, req.value))):
                self._respond(client, req)
                return
            if not 1 <= req.width <= 8192 or not 1 <= req.height <= 8192 or req.width * req.height > 8 * 1024 * 1024:
                self._respond(client, req)
                return
            if req.kind in (10,12):
                scale=state.get('scale',1) if state else 1
                if (state and self._tracking(state)) or math.floor(req.width*scale+.5)*math.floor(req.height*scale+.5)>8*1024*1024:
                    self._respond(client,req);return
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
                if req.kind==12 and hasattr(self.native,'nxs_control_backing_scale'):
                    state['scale']=self.native.nxs_control_backing_scale(pointer) or 1
                self.controls[key] = self.contexts[context] = state
                if req.kind in self.text_kinds and req.process in self.text_filters:self.update_text_filters(req.process)
                self.log('native-form-control', process=req.process, control=req.control, kind=req.kind,
                         width=req.width, height=req.height)
            if req.kind==12:
                scale=self.native.nxs_control_backing_scale(state['native']) if hasattr(self.native,'nxs_control_backing_scale') else 1
                if req.width*scale*req.height*scale>8*1024*1024:
                    self._respond(client,req);return
            current = self.native.nxs_control_state(state['native'])
            config = ControlConfig(C.sizeof(ControlConfig), req.width, req.height, req.minimum, req.maximum,
                                   current.value if current.tracking or req.kind==6 else req.value, req.enabled,
                                   current.state if current.tracking else req.state, req.indeterminate, title)
            if not self.native.nxs_control_sync(state['native'], C.byref(config)):
                self._respond(client, req)
                return
            if req.kind in (10,12):state['dimensions']=(req.width,req.height)
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
            if req.operation==44 and req.kind==12 and self.radio_capabilities and not req.text_size:
                self._respond(client,req,state,input_result=1,payload=self.radio_snapshot(state));return
            if req.operation==42 and req.kind==6:
                title=data[C.sizeof(req):]
                accepted=bool(self.popup_title_capabilities and state['client'] is client and not self._tracking(state) and
                    req.state in (0,1) and (req.state or not title) and b'\0' not in title)
                if accepted:
                    try:title.decode('utf-8')
                    except UnicodeDecodeError:accepted=False
                if accepted:
                    accepted=bool(self.native.nxs_control_popup_title(state['native'],title if req.state else None))
                self._respond(client,req,state,input_result=int(accepted),pixels=accepted)
                return
            if req.operation==37 and req.kind==10 and self.tab_capabilities and not req.text_size:
                tabs=self.native.nxs_control_tab_state(state['native'])
                wire=TabWireState(tabs.count,tabs.selected_index,tabs.selected,tabs.content)
                self._respond(client,req,state,input_result=1,payload=bytes(wire));return
            if req.operation==35 and req.kind==9 and self.wheel_capabilities and not req.text_size:
                event=WheelEvent(C.sizeof(WheelEvent),req.modifiers,req.x,req.y,req.minimum,req.maximum)
                accepted=state['client'] is client and all(math.isfinite(v) for v in (req.minimum,req.maximum)) and self.native.nxs_control_wheel(state['native'],C.byref(event))
                viewport=self.native.nxs_control_text_viewport(state['native']) if accepted and self.text_capabilities&16 else None
                self._respond(client,req,state,input_result=int(bool(accepted)),viewport=viewport)
                return
            if req.operation==34 and req.kind==9 and self.text_capabilities&32 and not req.text_size:
                geometry=TextGeometry(size=C.sizeof(TextGeometry))
                accepted=state['client'] is client and self.native.nxs_control_text_geometry(state['native'],C.byref(geometry))
                self._respond(client,req,state,input_result=int(bool(accepted)),payload=bytes(geometry) if accepted else b'')
                return
            if req.operation in (32,33) and req.kind==9 and self.text_capabilities&16 and not req.text_size:
                accepted=state['client'] is client and (req.operation==32 or self.native.nxs_control_text_scroll(state['native'],req.x,req.y))
                viewport=self.native.nxs_control_text_viewport(state['native']) if accepted else None
                self._respond(client,req,state,input_result=int(accepted),viewport=viewport)
                return
            if req.operation==22:
                accepted=bool(self.pointer_capabilities&1 and not req.text_size and req.kind!=5 and
                    req.state>0 and self.idle() and not self._tracking(state) and
                    self.native.nxs_control_state(state['native']).enabled)
                if accepted:
                    state['starting']=True
                    self.pending.append(lambda:self.track(state,req.x,req.y,req.modifiers,req.state))
                self._respond(client,req,state,input_result=int(accepted))
                return
            if req.operation==21 and req.kind in self.text_kinds and self.text_capabilities&4 and not req.text_size:
                command=self.native.nxs_control_text_command(state['native']) or b''
                self._respond(client,req,state,input_result=1,payload=command)
                return
            if req.operation==18 and req.kind in self.text_kinds and self.text_capabilities and not req.text_size:
                current=TextState(size=C.sizeof(TextState))
                required=self.native.nxs_control_text_get(state['native'],None,0,C.byref(current))
                if not 0<required<=32*1024*1024-C.sizeof(TextResponse):
                    self._respond(client,req);return
                buffer=C.create_string_buffer(required)
                actual=self.native.nxs_control_text_get(state['native'],buffer,required,C.byref(current))
                if actual!=required:self._respond(client,req);return
                info=TextResponse(required-1,bool(current.editing)|bool(current.editable)<<1|bool(current.secure)<<2,
                    current.selection_start,current.selection_length,current.marked_start,current.marked_length)
                self._respond(client,req,state,input_result=1,payload=bytes(info)+buffer.raw[:-1])
                return
            if req.operation==14 and req.kind==6 and self.popup_open_capabilities:
                accepted=self.native.nxs_control_popup_open(state['native'],req.state)
                self._respond(client,req,state,input_result=accepted)
                return
            if req.operation==12 and req.kind==6 and self.popup_capabilities:
                rectangle=ControlRect()
                if req.x==int(req.x) and 0<=req.x<65536:
                    rectangle=self.native.nxs_control_popup_item_rect(state['native'],int(req.x))
                self._respond(client,req,state,rectangle=rectangle)
                return
            if req.operation==13 and self.popup_capabilities:
                accepted=self.native.nxs_control_set_screen_origin(state['native'],req.x,req.y)
                if accepted and state.get('screen_origin')!=(req.x,req.y):
                    state['screen_origin']=(req.x,req.y)
                    self.log('native-control-screen-origin',process=req.process,control=req.control,
                             x=req.x,y=req.y)
                self._respond(client,req,state,input_result=accepted)
                return
            if req.operation == 2 and self.idle():
                state['starting'] = True
                self.pending.append(lambda: self.track(state, req.x, req.y, req.modifiers))
            elif req.operation in (3, 4) and self.active is state:
                self.native.nxs_control_send(state['native'], 0 if req.operation == 3 else 1, req.x, req.y, req.modifiers)
            elif req.operation == 6:
                state['destroy'] = True
                if self.active is state:
                    self.native.nxs_control_send(state['native'], 0, -1, -1, 0)
                    self.native.nxs_control_send(state['native'], 1, -1, -1, 0)
        self._respond(client, req, state, pixels=req.operation==5 and req.kind in (*self.text_kinds,10,12))

    def radio_snapshot(self,state):
        value=self.native.nxs_control_radio_state(state['native'])
        return bytes(RadioWireState(value.count,value.rows,value.columns,0,value.selected,value.key_cell,value.actions))

    def radio_message(self,client,data):
        operation=int.from_bytes(data[4:8],'little')
        header=ControlRadioRequest if operation==43 else ControlRadioItemRequest
        if len(data)<C.sizeof(header):return
        req=header.from_buffer_copy(data)
        if req.magic!=MAGIC or req.kind!=12 or req.text_size!=len(data)-C.sizeof(req) or req.text_size>65536:
            self._respond(client,req);return
        state=self.controls.get((req.process,req.control,req.kind))
        if not state or state['destroy'] or state['client'] is not client or not self.radio_capabilities:
            self._respond(client,req);return
        if operation in (45,46):
            if req.text_size:self._respond(client,req);return
            rect=self.native.nxs_control_radio_item_rect(state['native'],req.identifier)
            if not rect.width>0 or not rect.height>0:self._respond(client,req);return
            if operation==45:
                self._respond(client,req,state,input_result=1,rectangle=rect);return
            if self._tracking(state):self._respond(client,req);return
            if req.width or req.height:
                if not self.radio_capabilities&2 or not self.native.nxs_control_radio_cell_size(state['native'],req.width,req.height):
                    self._respond(client,req);return
                rect=self.native.nxs_control_radio_item_rect(state['native'],req.identifier)
            scale=state.get('scale',1);bitmap=self.native.nxs_control_draw(state['native'],scale)
            x,y,width,height=[math.floor(v*scale+.5) for v in (rect.x,rect.y,rect.width,rect.height)]
            if not bitmap.pixels or min(x,y)<0 or min(width,height)<1 or x+width>bitmap.width or y+height>bitmap.height:
                self._respond(client,req);return
            pixels=b''.join(C.string_at(bitmap.pixels+(y+row)*bitmap.stride+x*4,width*4) for row in range(height))
            state['invalidated']=False
            self._respond(client,req,state,input_result=1,rectangle=rect,image=(width,height,width*4,pixels));return
        if self._tracking(state) or req.count>4096 or not req.columns or req.count%req.columns or not math.isfinite(req.scale) or not 1<=req.scale<=8:
            self._respond(client,req);return
        offset=C.sizeof(req);items=(RadioItem*req.count)()
        for index in range(req.count):
            if offset+16>len(data):self._respond(client,req);return
            identifier=int.from_bytes(data[offset:offset+8],'little');enabled=int.from_bytes(data[offset+8:offset+12],'little');length=int.from_bytes(data[offset+12:offset+16],'little');offset+=16
            if enabled not in (0,1) or offset+length>len(data):self._respond(client,req);return
            title=data[offset:offset+length];offset+=length
            try:title.decode('utf-8')
            except UnicodeDecodeError:self._respond(client,req);return
            if b'\0' in title:self._respond(client,req);return
            items[index]=RadioItem(C.sizeof(RadioItem),identifier,title,enabled)
        if offset!=len(data):self._respond(client,req);return
        accepted=self.native.nxs_control_radio_items(state['native'],items,req.count,req.columns,req.selected,req.key_cell)
        if accepted:state['scale']=req.scale
        self._respond(client,req,state,input_result=int(bool(accepted)),payload=self.radio_snapshot(state))

    def tab_message(self,client,data):
        operation=int.from_bytes(data[4:8],'little');kind=ControlTabsRequest if operation==36 else ControlTabItemRequest
        if len(data)<C.sizeof(kind):return
        req=kind.from_buffer_copy(data)
        if req.magic!=MAGIC or req.kind!=10 or req.text_size!=len(data)-C.sizeof(req) or req.text_size>65536:
            self._respond(client,req);return
        state=self.controls.get((req.process,req.control,req.kind))
        if not state or state['destroy'] or state['client'] is not client or not self.tab_capabilities:
            self._respond(client,req);return
        if operation==38:
            if req.text_size:self._respond(client,req);return
            rect=self.native.nxs_control_tab_item_rect(state['native'],req.identifier)
            self._respond(client,req,state,input_result=1,rectangle=rect);return
        count=req.count
        if self._tracking(state) or count>4096 or not math.isfinite(req.scale) or not 1<=req.scale<=8:
            self._respond(client,req);return
        width,height=state['dimensions']
        if math.floor(width*req.scale+.5)*math.floor(height*req.scale+.5)>8*1024*1024:
            self._respond(client,req);return
        offset=C.sizeof(req);items=(TabItem*count)()
        for index in range(count):
            if offset+16>len(data):self._respond(client,req);return
            identifier=int.from_bytes(data[offset:offset+8],'little');title_size=int.from_bytes(data[offset+8:offset+12],'little');tip_size=int.from_bytes(data[offset+12:offset+16],'little');offset+=16
            if offset+title_size+tip_size>len(data):self._respond(client,req);return
            title=data[offset:offset+title_size];offset+=title_size;tip=data[offset:offset+tip_size];offset+=tip_size
            try:title.decode('utf-8');tip.decode('utf-8')
            except UnicodeDecodeError:self._respond(client,req);return
            if b'\0' in title or b'\0' in tip:self._respond(client,req);return
            items[index]=TabItem(C.sizeof(TabItem),identifier,title,tip or None)
        if offset!=len(data):self._respond(client,req);return
        accepted=self.native.nxs_control_tab_items(state['native'],items,count,req.selected)
        if accepted:state['scale']=req.scale
        self._respond(client,req,state,input_result=accepted,pixels=bool(accepted))

    def text_message(self,client,data):
        if len(data)<C.sizeof(ControlTextRequest):return
        req=ControlTextRequest.from_buffer_copy(data)
        if req.magic!=MAGIC or req.kind not in self.text_kinds or req.text_size!=len(data)-C.sizeof(req) or req.text_size>65536:
            self._respond(client,req);return
        state=self.controls.get((req.process,req.control,req.kind))
        if not state or state['destroy'] or not self.text_capabilities:
            self._respond(client,req);return
        text=data[C.sizeof(req):]
        try:text.decode('utf-8')
        except UnicodeDecodeError:self._respond(client,req);return
        if b'\0' in text:self._respond(client,req);return
        model=TextModel(C.sizeof(TextModel),text,req.selection_start,req.selection_length,req.editable)
        accepted=self.native.nxs_control_text_sync(state['native'],C.byref(model))
        self._respond(client,req,state,input_result=accepted,pixels=bool(accepted))

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

    def input_message(self, client, data,sender_pid=None):
        if len(data) < C.sizeof(ControlInputRequest):
            return
        req = ControlInputRequest.from_buffer_copy(data)
        if req.magic != MAGIC or req.text_size + req.unmodified_size != len(data) - C.sizeof(req):
            return
        state = self.controls.get((req.process, req.control, req.kind))
        owner=self.notifiers.get(req.process) if self.input_owner else None
        authorized=(not self.input_owner or owner and owner['client'] is client and owner['pid']==sender_pid
                    and not select.select([owner['lifetime']],[],[],0)[0] and self.input_owner(sender_pid))
        if (not state or state['destroy'] or state['client'] is not client
                or req.text_size + req.unmodified_size > 65536
                or not authorized):
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
        self._respond(client, req, state, input_result=result,
            payload=self.radio_snapshot(state) if req.kind==12 and self.radio_capabilities else b'')

    def track(self, state, x, y, modifiers,click_count=None):
        if state['destroy']:
            state['starting'] = False
            return
        self.active, state['starting'] = state, False
        self.log('native-form-press', process=state['key'][0], control=state['key'][1], kind=state['key'][2], x=x, y=y,click_count=1 if click_count is None else click_count)
        try:
            if click_count is None:self.native.nxs_control_track(state['native'], x, y, modifiers)
            else:assert self.native.nxs_control_track_clicks(state['native'],x,y,modifiers,click_count)
        finally:
            self.active = None
        self.log('native-form-release', process=state['key'][0], control=state['key'][1], kind=state['key'][2], actions=state['actions'])

    def disconnect(self, client):
        self.drop_menu_replies(client=client)
        for process,entry in list(self.notifiers.items()):
            if entry['client'] is client:
                self.remove_notifier(process)
                self.log('native-notifier-disconnect',process=process,active=len(self.notifiers))
        for state in self.controls.values():
            if state['client'] is client:
                self.destroy_later(state)

    def destroy_later(self,state):
        state['destroy']=True
        if self.active is state:
            self.native.nxs_control_send(state['native'],0,-1,-1,0)
            self.native.nxs_control_send(state['native'],1,-1,-1,0)

    def cleanup(self):
        self.menus.cleanup()
        for process in {state['key'][0] for state in self.controls.values() if state.get('text_filter')}:
            self.update_text_filters(process)
        for key, state in list(self.controls.items()):
            if state['destroy'] and self.native.nxs_control_destroy(state['native']):
                if key[2] == 5:
                    self.log('native-progress-destroy', process=key[0], control=key[1])
                elif key[2]==6:
                    self.log('native-popup-destroy',process=key[0],control=key[1])
                else:
                    self.log('native-form-destroy',process=key[0],control=key[1],kind=key[2])
                del self.controls[key]
                del self.contexts[state['context']]

    def close(self):
        for process in list(self.notifiers):self.remove_notifier(process)
        self.menus.close()
        for state in self.controls.values():
            self.native.nxs_control_destroy(state['native'])
