"""Transport for the shared native UI provider; contains no widget implementation."""
import ctypes as C
import itertools
import math
import os
import fcntl
import time
import select
import socket
import importlib.util
import struct
from pathlib import Path

MAGIC = 0x4e585549

def native_presentation_scale_supported(scale):
    return math.isfinite(scale) and .125<=scale<=8

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

def scale_rectangle(rectangle, scale):
    for field in ('x','y','width','height'):
        setattr(rectangle,field,getattr(rectangle,field)*scale)

class ControlActionsRequest(C.Structure):
    _fields_ = ControlRequest._fields_[:7]+[('after',C.c_uint64),('subscribe',C.c_uint32),
        ('padding',C.c_uint32),('unused',C.c_ubyte*56)]

class ControlInputRequest(C.Structure):
    _fields_ = ControlRequest._fields_[:7] + [
        ('type', C.c_uint32), ('modifiers', C.c_uint32), ('key', C.c_uint32),
        ('repeat', C.c_uint32), ('unmodified_size', C.c_uint32), ('focused', C.c_int32)]
class ControlStepRequest(C.Structure):
    _fields_ = ControlRequest._fields_[:7]+[('step',C.c_double)]
class ColorModel(C.Structure):
    _fields_=[('size',C.c_uint32)]+[(name,C.c_double) for name in ('red','green','blue','alpha')]
class DateModel(C.Structure):
    _fields_=[(name,C.c_uint32) for name in ('size','flags','elements','style')]+[(name,C.c_double) for name in ('value','minimum','maximum')]
class ControlColorRequest(C.Structure):
    _fields_=ControlRequest._fields_[:7]+[(name,C.c_double) for name in ('red','green','blue','alpha')]
class ControlDateRequest(C.Structure):
    _fields_=ControlRequest._fields_[:7]+[(name,C.c_uint32) for name in ('flags','elements','style','padding')]+[(name,C.c_double) for name in ('value','minimum','maximum')]
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
EditCommand=C.CFUNCTYPE(None,C.c_void_p,C.c_char_p)
EDIT_BINDINGS_OPERATION=72
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
class ListItem(C.Structure):
    _fields_=[('size',C.c_uint32),('identifier',C.c_uint64),('title',C.c_char_p),('enabled',C.c_int),('selected',C.c_int)]
class ListState(C.Structure):
    _fields_=[('size',C.c_uint32),('count',C.c_uint32),('selected_count',C.c_uint32),('flags',C.c_uint32),
        ('primary',C.c_uint64),('key_cell',C.c_uint64),('actions',C.c_uint64),('visible',ControlRect),('content',C.c_double*2)]
class ListWireState(C.Structure):
    _fields_=[('count',C.c_uint32),('selected_count',C.c_uint32),('flags',C.c_uint32),('reserved',C.c_uint32),
        ('primary',C.c_uint64),('key_cell',C.c_uint64),('actions',C.c_uint64),('visible',ControlRect),('content',C.c_double*2)]
class ListWireItem(C.Structure):
    _fields_=[('identifier',C.c_uint64),('enabled',C.c_uint32),('selected',C.c_uint32),('title_size',C.c_uint32),('reserved',C.c_uint32)]
class ControlListRequest(C.Structure):
    _fields_=ControlRequest._fields_[:7]+[('count',C.c_uint32),('flags',C.c_uint32),('key_cell',C.c_uint64),('scale',C.c_double)]
class ControlListItemRequest(C.Structure):
    _fields_=ControlRequest._fields_[:7]+[('identifier',C.c_uint64)]
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
        self.pump = pump_type(self.pump_tracking)
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
        self.list_capabilities=0
        self.scroll_capabilities=0
        self.item_hit_capabilities=0
        if hasattr(native,'nxs_control_item_hit_capabilities'):
            native.nxs_control_item_hit_capabilities.restype=C.c_uint
            self.item_hit_capabilities=native.nxs_control_item_hit_capabilities()
            if self.item_hit_capabilities&1:
                native.nxs_control_item_at_point.argtypes=[C.c_void_p,C.c_double,C.c_double,C.POINTER(C.c_uint64)]
                native.nxs_control_item_at_point.restype=C.c_int
        if hasattr(native,'nxs_control_scroll_capabilities'):
            native.nxs_control_scroll_capabilities.restype=C.c_uint
            self.scroll_capabilities=native.nxs_control_scroll_capabilities()
            if self.scroll_capabilities&1:
                native.nxs_control_scroll_geometry.argtypes=[C.c_void_p,C.POINTER(TextGeometry)]
                native.nxs_control_scroll_geometry.restype=C.c_int
        if hasattr(native,'nxs_control_list_capabilities'):
            native.nxs_control_list_capabilities.restype=C.c_uint
            self.list_capabilities=native.nxs_control_list_capabilities()
            if self.list_capabilities:
                native.nxs_control_list_items.argtypes=[C.c_void_p,C.POINTER(ListItem),C.c_uint32,C.c_uint,C.c_uint64]
                native.nxs_control_list_items.restype=C.c_int
                native.nxs_control_list_state.argtypes=[C.c_void_p];native.nxs_control_list_state.restype=ListState
                native.nxs_control_list_selection.argtypes=[C.c_void_p,C.POINTER(C.c_uint64),C.c_size_t]
                native.nxs_control_list_selection.restype=C.c_size_t
                native.nxs_control_list_item_rect.argtypes=[C.c_void_p,C.c_uint64];native.nxs_control_list_item_rect.restype=ControlRect
                native.nxs_control_list_scroll.argtypes=[C.c_void_p,C.c_double,C.c_double];native.nxs_control_list_scroll.restype=C.c_int
        self.specialized_capabilities=0
        self.color_panel_capabilities=0
        if hasattr(native,'nxs_control_color_panel_capabilities'):
            native.nxs_control_color_panel_capabilities.restype=C.c_uint
            self.color_panel_capabilities=native.nxs_control_color_panel_capabilities()
            native.nxs_control_color_open.argtypes=[C.c_void_p,C.c_int];native.nxs_control_color_open.restype=C.c_int
            if self.color_panel_capabilities&2:
                native.nxs_control_color_lifecycle.argtypes=[C.c_void_p,C.c_uint]
                native.nxs_control_color_lifecycle.restype=C.c_int
        if hasattr(native,'nxs_control_specialized_capabilities'):
            native.nxs_control_specialized_capabilities.restype=C.c_uint
            self.specialized_capabilities=native.nxs_control_specialized_capabilities()
            for name,model in [('color_sync',ColorModel),('color_get',ColorModel),('date_sync',DateModel),('date_get',DateModel)]:
                method=getattr(native,'nxs_control_'+name)
                method.argtypes=[C.c_void_p,C.POINTER(model)];method.restype=C.c_int
        self.activation_capabilities=0
        if hasattr(native,'nxs_control_activation_capabilities'):
            native.nxs_control_activation_capabilities.restype=C.c_uint
            self.activation_capabilities=native.nxs_control_activation_capabilities()
            native.nxs_control_perform_click.argtypes=[C.c_void_p,C.c_uint64]
            native.nxs_control_perform_click.restype=C.c_int
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
        self.host_epoch = 0
        self.global_generations = {}
        self.notifiers = {}
        self.edit_bindings_available = hasattr(native, 'nxs_edit_bindings_resolve')
        if self.edit_bindings_available:
            native.nxs_edit_bindings_create.argtypes = []
            native.nxs_edit_bindings_create.restype = C.c_void_p
            native.nxs_edit_bindings_destroy.argtypes = [C.c_void_p]
            native.nxs_edit_bindings_destroy.restype = None
            native.nxs_edit_bindings_reset.argtypes = [C.c_void_p]
            native.nxs_edit_bindings_reset.restype = None
            native.nxs_edit_bindings_resolve.argtypes = [C.c_void_p, C.POINTER(KeyEvent), EditCommand, C.c_void_p]
            native.nxs_edit_bindings_resolve.restype = C.c_int
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
            if self.text_capabilities&512 and hasattr(native,'nxs_control_text_placeholder'):
                native.nxs_control_text_placeholder.argtypes=[C.c_void_p,C.c_char_p]
                native.nxs_control_text_placeholder.restype=C.c_int
            else:self.text_capabilities&=~512
            if self.text_capabilities&2:
                native.nxs_control_text_filter.argtypes=[C.c_void_p,TextShouldChange,C.c_void_p]
                native.nxs_control_text_filter.restype=C.c_int
        self.text_kinds=(7,8,9) if self.text_capabilities&8 else (7,8)
        if self.text_capabilities&64:self.text_kinds+=(14,)
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
        self.callback_source_capabilities=0
        if hasattr(native,'nxs_native_ui_source_capabilities'):
            native.nxs_native_ui_source_capabilities.argtypes=[]
            native.nxs_native_ui_source_capabilities.restype=C.c_uint
            self.source_capabilities=native.nxs_native_ui_source_capabilities()
            native.nxs_native_ui_source_create.argtypes=[C.c_int]
            native.nxs_native_ui_source_create.restype=C.c_void_p
            native.nxs_native_ui_source_destroy.argtypes=[C.c_void_p]
            native.nxs_native_ui_source_destroy.restype=C.c_int
            if hasattr(native,'nxs_native_ui_callback_source_capabilities'):
                native.nxs_native_ui_callback_source_capabilities.argtypes=[]
                native.nxs_native_ui_callback_source_capabilities.restype=C.c_uint
                self.callback_source_capabilities=native.nxs_native_ui_callback_source_capabilities()
                native.nxs_native_ui_source_callback.argtypes=[C.c_int,pump_type,C.c_void_p]
                native.nxs_native_ui_source_callback.restype=C.c_void_p
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
            if hasattr(native,'nxs_control_set_screen_bounds'):
                native.nxs_control_set_screen_bounds.argtypes=[C.c_void_p,ControlRect]
                native.nxs_control_set_screen_bounds.restype=C.c_int
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
        try:from color_owners import ColorOwners
        except ModuleNotFoundError as error:
            if error.name!='color_owners':raise
            spec=importlib.util.spec_from_file_location('nextspace_color_owners',Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge/color_owners.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);ColorOwners=module.ColorOwners
        self.color_owners=ColorOwners(self)
        self.auxiliary_capabilities=0
        if hasattr(native,'nxs_control_auxiliary_capabilities'):
            native.nxs_control_auxiliary_capabilities.restype=C.c_uint
            self.auxiliary_capabilities=native.nxs_control_auxiliary_capabilities() if self.notification_capabilities else 0
            native.nxs_control_auxiliary_activate.argtypes=[C.c_void_p,C.c_char_p]
            native.nxs_control_auxiliary_activate.restype=C.c_int
            if hasattr(native,'nxs_control_auxiliary_parent'):
                native.nxs_control_auxiliary_parent.argtypes=[C.c_void_p,C.c_char_p]
                native.nxs_control_auxiliary_parent.restype=C.c_int
        try:from auxiliary_activation import AuxiliaryActivation
        except ModuleNotFoundError as error:
            if error.name!='auxiliary_activation':raise
            spec=importlib.util.spec_from_file_location('nextspace_auxiliary_activation',Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge/auxiliary_activation.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);AuxiliaryActivation=module.AuxiliaryActivation
        self.auxiliary_activation=AuxiliaryActivation(self,ColorOwners.ancestor)
        try:from outlines import NativeOutlines
        except ModuleNotFoundError as error:
            if error.name!='outlines':raise
            spec=importlib.util.spec_from_file_location('nextspace_outlines',Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge/outlines.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);NativeOutlines=module.NativeOutlines
        self.outlines=NativeOutlines(self,ControlListRequest)

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
        self.log('native-menu-owner-unavailable',stage='acknowledgment',process=process,control=state['key'][1],serial=serial,expired=time.monotonic()>=deadline)
        if self.text_filters.get(process) is entry:self.fail_text_filter(entry)
        return False

    def remove_notifier(self,process):
        self.remove_text_filter(process)
        entry=self.notifiers.pop(process,None)
        if entry:
            if entry.get('edit_bindings'):
                self.native.nxs_edit_bindings_destroy(entry['edit_bindings'])
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
        if not state['destroy'] and self.text_filters.get(process) is entry:
            self.log('native-menu-owner-unavailable' if magic==MENU_COMMAND_MAGIC else 'native-command-owner-unavailable',stage='decision',process=process,control=state['key'][1],serial=serial,expired=time.monotonic()>=deadline)
            self.fail_text_filter(entry)
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

    def generation(self,process):
        return self.generations.get(process,self.host_epoch<<32)

    def invalidate(self,process,state=None,fanout=True):
        generation=self.generation(process)+1
        self.generations[process]=generation
        if state is None:self.global_generations[process]=generation
        else:state['native_generation']=generation
        self.signal(process)
        if fanout:self.color_owners.fanout(process,state)

    def invalidation_snapshot(self,process,since):
        # Generation receipts survive another request reading a native image.
        # A missing/overflowed history requires a full application repaint.
        current=self.generation(process)
        full=(not math.isfinite(since) or since!=int(since) or since<=0 or since>current or
              self.global_generations.get(process,0)>since)
        rows=[(state['key'][1],state['key'][2]) for state in self.controls.values()
              if state['key'][0]==process and not state['destroy'] and
                 state.get('native_generation',0)>since]
        if full or len(rows)>1024:return struct.pack('II',0x4e584449,0xffffffff)
        return struct.pack('II',0x4e584449,len(rows))+b''.join(struct.pack('QII',control,kind,0) for control,kind in rows)

    def notification_message(self,client,req,descriptors,sender_pid):
        accepted=0;reason="request-or-owner"
        previous=self.notifiers.get(req.process)
        owned=not previous or (previous['client'] is client and previous['pid']==sender_pid)
        if req.kind==0 and req.control==0 and not req.text_size and owned:
            if req.operation==16 and not descriptors:
                self.remove_notifier(req.process)
                accepted=1
            elif (req.operation==15 and self.notification_capabilities and sender_pid and sender_pid>0 and len(descriptors)==1 and
                  math.isfinite(req.value) and 0<=req.value<=self.generation(req.process)):
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
                        if self.generation(req.process)>req.value:self.signal(req.process)
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
            if state['key'][2] in (6,17) and not state['destroy'] and (state['key'][2]==6 or self.specialized_capabilities&256):
                visible=bool(self.native.nxs_control_popup_state(state['native']).visible)
                if visible!=state.get('popup_visible',False):
                    state['popup_visible']=visible
                    process,control,kind=state['key']
                    self.invalidate(process,state)
                    self.log('native-popup-visibility',process=process,control=control,visible=visible,generation=self.generations[process])
            if state['key'][2]==16 and not state['destroy']:
                active=bool(self.native.nxs_control_state(state['native']).state)
                if active!=state.get('color_panel_active',False):
                    state['color_panel_active']=active
                    process,control,kind=state['key']
                    # Picker completion must wake its owner even if the inline
                    # image remains dirty or a renderer has no new bitmap.
                    self.invalidate(process,state)
                    self.log('native-color-panel-state',process=process,control=control,active=active)
            if state['destroy'] or state.get('invalidated'):
                continue
            if self.native.nxs_control_needs_display(state['native']):
                state['invalidated'] = True
                process, control, kind = state['key']
                self.invalidate(process,state)
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
        if self.list_capabilities:kinds.append(13)
        for kind,flag in [(15,1),(16,2),(17,4)]:
            if self.specialized_capabilities&flag:kinds.append(kind)
        for kind in kinds:self.preferred(kind)
        # Backend-specific support is known after the first native host draw
        # has initialized AppKit and loaded the selected display backend.
        if hasattr(self.native,'nxs_control_auxiliary_capabilities'):
            self.auxiliary_capabilities=self.native.nxs_control_auxiliary_capabilities() if self.notification_capabilities else 0
        self.log('native-auxiliary-capabilities',capabilities=self.auxiliary_capabilities)

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
        if 'action_log' in state:
            state['action_log'].append(state['actions'],event,native_state.contents.value,native_state.contents.state)
        state['edits']=state.get('edits',0)+int(event==3)
        state['activations']=state.get('activations',0)+int(event==1)
        process=state['key'][0]
        timestamp=time.monotonic_ns()
        self.invalidate(process,state)
        self.log('native-form-action', process=state['key'][0], control=state['key'][1],
                 kind=state['key'][2], action=event, count=state['actions'],
                 value=native_state.contents.value, state=native_state.contents.state,monotonic_ns=timestamp)

    def _tracking(self, state):
        return bool(state.get('starting') or self.native.nxs_control_state(state['native']).tracking)

    def owns_process(self, client, process, pid):
        entry=self.notifiers.get(process)
        return bool(entry and entry['client'] is client and entry['pid']==pid and
                    not select.select([entry['lifetime']],[],[],0)[0])

    def record_input_result(self,client,req,state,result):
        # Keep the original action baseline, even if the user edits the native
        # panel before a delayed/lost opening reply is recovered. No UI is run
        # when reading a receipt. Retention is bounded per native control.
        receipts=state.setdefault('input_receipts',[])
        current=self.native.nxs_control_state(state['native'])
        current.tracking=self._tracking(state)
        receipts.append((client,req.process,req.control,req.operation,req.reserved,
                         int(result),current,state['actions']))
        del receipts[:-8]

    def reply_input_receipt(self,client,req,state,sender_pid):
        valid=bool(state and state['client'] is client and not req.text_size and
            (not self.input_owner or self.owns_process(client,req.process,sender_pid)))
        receipt=state.get('last_key') if valid and req.x==0 else None
        snapshot=None
        if valid and req.x in (2,4,14,22,59):
            saved=next((r for r in reversed(state.get('input_receipts',[])) if
                r[:5]==(client,req.process,req.control,int(req.x),req.value)),None)
            if saved:receipt=(saved[4],saved[5]);snapshot=(saved[6],saved[7])
        accepted=bool(receipt and req.value==receipt[0])
        self.log('native-input-receipt' if req.x else 'native-key-receipt',process=req.process,
                 control=req.control,operation=req.x or 8,sequence=receipt[0] if accepted else None,accepted=accepted)
        self._respond(client,req,state,input_result=receipt[1] if accepted else 0,key_receipt=accepted,
            native_snapshot=snapshot,
            payload=self.radio_snapshot(state) if accepted and req.kind==12 else self.list_snapshot(state) if accepted and req.kind==13 else b'')

    def _respond(self, client, req, state=None, pixels=False, input_result=0, rectangle=None, payload=b'',viewport=None,image=None,key_receipt=False,native_snapshot=None):
        response = self.response_type()
        response.magic, response.reserved = MAGIC, req.reserved
        response.parts[3].x = input_result
        response.parts[3].height = int(key_receipt)
        response.parts[3].width = self.input_capabilities
        response.parts[4].x = self.generation(req.process)
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
            current = native_snapshot[0] if native_snapshot else self.native.nxs_control_state(state['native'])
            response.parts[0].x = current.value
            response.parts[0].y = current.tracking if native_snapshot else self._tracking(state)
            response.parts[0].width = native_snapshot[1] if native_snapshot else state['actions']
            response.parts[0].height = current.state
            if req.kind==16:response.parts[2].height=state.get('color_model_actions',0)
            preferred = self.native.nxs_control_size(state['native'])
            presentation=state.get('presentation',1)
            response.parts[1].width, response.parts[1].height = preferred.width*presentation, preferred.height*presentation
            response.parts[2].x = current.enabled
            if req.kind in self.text_kinds:
                response.parts[2].width=state.get('edits',0)
                response.parts[2].height=state.get('activations',0)
            if self.input_capabilities & 1:
                response.parts[3].y = self.native.nxs_control_focused(state['native'])
            if req.kind in (6,17) and self.popup_capabilities and (req.kind==6 or self.specialized_capabilities&256):
                popup=self.native.nxs_control_popup_state(state['native'])
                response.parts[5].y=popup.highlighted
                frame=rectangle if rectangle is not None else popup.frame
                for field in ('x','y','width','height'):setattr(response.parts[6],field,getattr(frame,field))
            if req.kind==10 and self.tab_capabilities:
                tabs=self.native.nxs_control_tab_state(state['native']);response.parts[5].y=tabs.count
                frame=rectangle if rectangle is not None else tabs.content
                for field in ('x','y','width','height'):setattr(response.parts[6],field,getattr(frame,field))
            if req.kind==13:
                response.parts[5].y=state.get('presentation') or (self.native.nxs_control_backing_scale(state['native']) if hasattr(self.native,'nxs_control_backing_scale') else state.get('scale',1))
            if req.kind in (12,13) and rectangle is not None:
                for field in ('x','y','width','height'):setattr(response.parts[6],field,getattr(rectangle,field))
            if pixels:
                draw_started=time.monotonic() if os.environ.get('NEXTSPACE_TRACE_NATIVE_RPC')=='1' else None
                bitmap = self.native.nxs_control_draw(state['native'], state.get('scale',1))
                if draw_started is not None and time.monotonic()-draw_started>=.02:
                    self.log('native-draw-timing',process=req.process,kind=req.kind,control=req.control,
                             seconds=time.monotonic()-draw_started,finished=time.monotonic(),
                             width=bitmap.width,height=bitmap.height)
                if bitmap.pixels:
                    response.width, response.height, response.stride = bitmap.width, bitmap.height, bitmap.stride
                    data = C.string_at(bitmap.pixels, bitmap.stride * bitmap.height)
                    state['invalidated'] = False
        if image is not None:
            response.width,response.height,response.stride,data=image
        if viewport is not None:
            for field in ('x','y','width','height'):setattr(response.parts[5],field,getattr(viewport.visible,field))
            response.parts[6].width=viewport.content.width;response.parts[6].height=viewport.content.height
        if state and state.get('presentation',1)!=1:
            scale=state['presentation']
            scale_rectangle(response.parts[6],scale)
            if viewport is not None:scale_rectangle(response.parts[5],scale)
            if req.operation in (34,52) and len(data)==C.sizeof(TextGeometry):
                geometry=TextGeometry.from_buffer_copy(data)
                scale_rectangle(geometry.clip,scale)
                for field in ('width','height'):setattr(geometry.client,field,getattr(geometry.client,field)*scale)
                for point in (geometry.minimum,geometry.maximum):point.x*=scale;point.y*=scale
                data=bytes(geometry)
        self.send(client, response, data)

    def message(self, client, data, descriptors=(),sender_pid=None,presentation=None):
        if len(data) >= 8 and int.from_bytes(data[4:8], 'little') == EDIT_BINDINGS_OPERATION:
            if not descriptors:
                self.edit_bindings_message(client, data, sender_pid)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little')==71:
            self.outlines.message(client,data);return
        if len(data)>=8 and int.from_bytes(data[4:8],'little')==65:
            size=C.sizeof(ControlRequest)
            if descriptors or len(data)<size+8:return
            req=ControlRequest.from_buffer_copy(data)
            scale=struct.unpack_from('d',data,size)[0]
            if (req.magic!=MAGIC or req.text_size!=len(data)-size-8 or
                    not native_presentation_scale_supported(scale)):
                self._respond(client,req);return
            req.operation=1
            self.message(client,bytes(req)+data[size+8:],(),sender_pid,presentation=scale)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little')==63:
            if len(data)!=C.sizeof(ControlActionsRequest):return
            req=ControlActionsRequest.from_buffer_copy(data)
            state=self.controls.get((req.process,req.control,req.kind))
            if (req.magic!=MAGIC or descriptors or req.text_size or req.padding or any(req.unused) or
                    req.subscribe not in (0,1) or not self.owns_process(client,req.process,sender_pid) or not state or
                    state['destroy'] or state['client'] is not client):
                self._respond(client,req);return
            if not req.subscribe:
                state.pop('action_log',None);self._respond(client,req,state,input_result=1);return
            if req.after>state['actions']:
                self._respond(client,req);return
            baseline='action_log' not in state
            if baseline:
                try:from action_log import ActionLog
                except ModuleNotFoundError as error:
                    if error.name!='action_log':raise
                    spec=importlib.util.spec_from_file_location('nextspace_action_log',Path(__file__).resolve().parents[2]/'Libraries/NativeUI/Bridge/action_log.py')
                    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);ActionLog=module.ActionLog
                state['action_log']=ActionLog(state['actions'])
            payload=state['action_log'].snapshot(req.after,baseline)
            self._respond(client,req,state,input_result=1,payload=payload);return
        if descriptors and (len(data)<8 or int.from_bytes(data[4:8],'little') not in (15,19,64)):return
        if len(data)>=8 and int.from_bytes(data[4:8],'little') in (55,56,57,58):
            self.specialized_message(client,data,sender_pid)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little')==47:
            if len(data)!=C.sizeof(ControlRadioItemRequest):return
            req=ControlRadioItemRequest.from_buffer_copy(data)
            state=self.controls.get((req.process,req.control,req.kind))
            if state and (state['destroy'] or state['client'] is not client):state=None
            accepted=bool(req.magic==MAGIC and not req.text_size and not req.width and not req.height and
                self.activation_capabilities and state and not state['destroy'] and
                state['client'] is client and self.idle() and not self._tracking(state) and
                self.native.nxs_control_perform_click(state['native'],req.identifier))
            self.log('native-form-perform-click',process=req.process,control=req.control,kind=req.kind,identifier=req.identifier,accepted=int(accepted))
            self._respond(client,req,state,input_result=int(accepted),payload=self.radio_snapshot(state) if accepted and req.kind==12 else b'')
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little') in (48,49,50,51):
            self.list_message(client,data)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little') in (43,45,46):
            self.radio_message(client,data)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little') in (36,38):
            self.tab_message(client,data)
            return
        if len(data)>=8 and int.from_bytes(data[4:8],'little') in (25,26,27,28,29,30,69,70):
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
            if state and not state['destroy'] and state['client'] is client and self.range_capabilities and self.native.nxs_control_set_step(state['native'],req.step):
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
        if req.operation==64:
            if descriptors:self.auxiliary_activation.register(client,req,sender_pid,descriptors)
            else:self.auxiliary_activation.publish(client,req,sender_pid,data[C.sizeof(req):])
            return
        if req.operation in (60,61,62,67):
            self.color_owners.message(client,req,sender_pid);return
        if req.operation in (0,5,59,66) and req.kind==16:
            source=self.color_owners.resolve(client,req,sender_pid)
            if source:
                if req.operation==66:
                    self.reply_input_receipt(client,req,source,sender_pid);return
                accepted=req.operation in (0,5) or req.state in (0,1) and self.color_owners.panel(client,req,sender_pid,source)
                if req.operation==59:self.record_input_result(client,req,source,accepted)
                if accepted and req.operation==59:
                    owner=self.notifiers.get(source['key'][0])
                    if req.state and owner:self.auxiliary_activation.open(source,owner['pid'])
                    else:self.auxiliary_activation.retire(source)
                self._respond(client,req,source,input_result=int(accepted),pixels=bool(accepted and req.operation!=0));return
        if req.operation in (15,16):
            self.notification_message(client,req,descriptors,sender_pid)
            return
        if req.operation in (19,20,23,24):
            self.text_filter_message(client,req,descriptors,sender_pid)
            return
        if req.operation == 9:
            self.dispatch_events()
            self._respond(client, req,payload=self.invalidation_snapshot(req.process,req.value) if self.owns_process(client,req.process,sender_pid) else struct.pack('II',0x4e584449,0xffffffff))
            return
        key = req.process, req.control, req.kind
        state = self.controls.get(key)
        if req.kind in (10,12,13,15,16,17) and state and state['client'] is not client:
            self._respond(client,req);return
        if state and state['destroy'] and req.operation != 5:
            self._respond(client, req)
            return
        if req.operation==66:
            self.reply_input_receipt(client,req,state,sender_pid)
            return
        if state and req.operation in (2,3,4,22,33,35,53):
            scale=state.get('presentation',1)
            req.x/=scale;req.y/=scale
            if req.operation==35:req.minimum/=scale;req.maximum/=scale
        if req.operation == 1:
            scale=presentation if presentation is not None else state.get('presentation',1) if state else 1
            if state and self._tracking(state) and scale!=state.get('presentation',1):
                self._respond(client,req);return
            if req.kind==13 and (not req.process or not req.control or req.text_size or req.enabled not in (0,1) or
                    any((req.minimum,req.maximum,req.value,req.x,req.y,req.state,req.indeterminate,req.modifiers))):
                self._respond(client,req);return
            if (req.kind not in (*range(1,11),12,13,14,15,16,17,18) or (15<=req.kind<=17 and not self.specialized_capabilities&(1<<(req.kind-15))) or (req.kind==18 and not self.outlines.available) or (req.kind==14 and not self.text_capabilities&64) or (req.kind==13 and not self.list_capabilities) or (req.kind==12 and not self.radio_capabilities) or (req.kind==10 and not self.tab_capabilities) or (req.kind==9 and not self.text_capabilities&8) or (req.kind==6 and not self.popup_capabilities) or
                (req.kind in self.text_kinds and not self.text_capabilities) or
                not all(math.isfinite(x) for x in (req.width, req.height, req.minimum, req.maximum, req.value))):
                self._respond(client, req)
                return
            if not 1 <= req.width <= 8192 or not 1 <= req.height <= 8192 or req.width * req.height > 8 * 1024 * 1024:
                self._respond(client, req)
                return
            if req.kind in (10,12,13):
                density=(state.get('scale',1) if state else 1) if presentation is None else 1
                if (state and self._tracking(state)) or math.floor(req.width*density+.5)*math.floor(req.height*density+.5)>8*1024*1024:
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
                if req.kind==13:
                    density=1 if presentation is not None else self.native.nxs_control_backing_scale(pointer) if hasattr(self.native,'nxs_control_backing_scale') else 1
                    if not math.isfinite(density) or not 1<=density<=8 or math.floor(req.width*density+.5)*math.floor(req.height*density+.5)>8*1024*1024:
                        self.native.nxs_control_destroy(pointer);self._respond(client,req);return
                state = dict(key=key, native=pointer, context=context, client=client, actions=0, destroy=False)
                if req.kind in (12,13) and hasattr(self.native,'nxs_control_backing_scale'):
                    state['scale']=self.native.nxs_control_backing_scale(pointer) or 1
                self.controls[key] = self.contexts[context] = state
                if req.kind in self.text_kinds and req.process in self.text_filters:self.update_text_filters(req.process)
            if presentation is not None:
                if state.get('presentation')!=presentation:
                    self.log('native-presentation',process=req.process,control=req.control,kind=req.kind,scale=presentation)
                state['presentation']=presentation
                state['scale']=presentation
            scale=state.get('presentation',1)
            req.width/=scale;req.height/=scale
            if req.kind in (12,13):
                scale=state.get('presentation') or (self.native.nxs_control_backing_scale(state['native']) if hasattr(self.native,'nxs_control_backing_scale') else 1)
                if math.floor(req.width*scale+.5)*math.floor(req.height*scale+.5)>8*1024*1024:
                    self._respond(client,req);return
            current = self.native.nxs_control_state(state['native'])
            if req.kind in (15,17) and self._tracking(state):
                # Observe the native stepper/date picker during its own
                # mouseDown/repeat loop without resetting the native gesture.
                signature=(req.width,req.height,req.minimum,req.maximum,req.enabled,title)
                if signature==state.get('tracking_configuration'):
                    self._respond(client,req,state,pixels=True)
                else:self._respond(client,req)
                return
            config = ControlConfig(C.sizeof(ControlConfig), req.width, req.height, req.minimum, req.maximum,
                                   current.value if current.tracking or req.kind==6 else req.value, req.enabled,
                                   current.state if current.tracking else req.state, req.indeterminate, title)
            if not self.native.nxs_control_sync(state['native'], C.byref(config)):
                self._respond(client, req)
                return
            dimensions=(req.width*scale,req.height*scale)
            if dimensions!=state.get('logged_dimensions'):
                state['logged_dimensions']=dimensions
                self.log('native-form-control',process=req.process,control=req.control,kind=req.kind,
                         width=dimensions[0],height=dimensions[1])
            if req.kind in (15,17):
                state['tracking_configuration']=(req.width,req.height,req.minimum,req.maximum,req.enabled,title)
            if req.kind in (10,12,13):state['dimensions']=(req.width,req.height)
            if req.kind==13:state['scale']=scale
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
            if req.operation==35 and req.kind in (9,13,18) and self.wheel_capabilities and not req.text_size:
                event=WheelEvent(C.sizeof(WheelEvent),req.modifiers,req.x,req.y,req.minimum,req.maximum)
                accepted=state['client'] is client and all(math.isfinite(v) for v in (req.minimum,req.maximum)) and self.native.nxs_control_wheel(state['native'],C.byref(event))
                viewport=self.native.nxs_control_text_viewport(state['native']) if accepted and req.kind==9 and self.text_capabilities&16 else None
                self._respond(client,req,state,input_result=int(bool(accepted)),viewport=viewport,payload=self.list_snapshot(state) if accepted and req.kind==13 else b'')
                return
            if req.operation==52 and req.kind in (9,13) and not req.text_size:
                geometry=TextGeometry(size=C.sizeof(TextGeometry))
                accepted=bool(self.scroll_capabilities&1 and state['client'] is client and
                    self.native.nxs_control_scroll_geometry(state['native'],C.byref(geometry)))
                self._respond(client,req,state,input_result=int(accepted),payload=bytes(geometry) if accepted else b'')
                return
            if req.operation==53 and not req.text_size:
                identifier=C.c_uint64()
                accepted=bool(self.item_hit_capabilities&1 and state['client'] is client and
                    self.native.nxs_control_item_at_point(state['native'],req.x,req.y,C.byref(identifier)))
                self._respond(client,req,state,input_result=int(accepted),payload=bytes(identifier) if accepted else b'')
                return
            if req.operation==59:
                accepted=bool(req.kind==16 and not req.text_size and req.state in (0,1,2) and self.color_panel_capabilities and state['client'] is client and self.color_owners.panel(client,req,sender_pid,state))
                self.record_input_result(client,req,state,accepted)
                if not accepted:
                    self.log('native-color-panel-rejected',process=req.process,control=req.control,open=req.state,tracking=bool(self._tracking(state)))
                if accepted:
                    if req.state:self.auxiliary_activation.open(state,sender_pid)
                    else:self.auxiliary_activation.retire(state)
                self._respond(client,req,state,input_result=int(accepted),pixels=accepted)
                return
            if req.operation==54:
                text=data[C.sizeof(req):]
                accepted=False
                if (self.text_capabilities&512 and req.kind in (7,8,14) and state['client'] is client and
                        req.state in (0,1) and (req.state or not req.text_size) and b'\0' not in text):
                    try:text.decode('utf-8')
                    except UnicodeDecodeError:pass
                    else:accepted=bool(self.native.nxs_control_text_placeholder(state['native'],text if req.state else None))
                self._respond(client,req,state,input_result=int(accepted),pixels=accepted)
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
                    (req.kind==13 or self.native.nxs_control_state(state['native']).enabled))
                if accepted:
                    state['starting']=True
                    state['press_sequence']=req.reserved
                    self.pending.append(lambda:self.track(state,req.x,req.y,req.modifiers,req.state))
                self.record_input_result(client,req,state,accepted)
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
            if req.operation==0 and not req.text_size:
                self._respond(client,req,state if state['client'] is client else None,input_result=int(state['client'] is client))
                return
            if req.operation==14 and req.kind in (6,17) and self.popup_open_capabilities:
                accepted=int(bool(state['client'] is client and not req.text_size and req.state in (0,1) and
                    (req.kind==6 or self.specialized_capabilities&256) and self.native.nxs_control_popup_open(state['native'],req.state)))
                self.record_input_result(client,req,state,accepted)
                if accepted:
                    # A menu stays a non-key window. The original source
                    # select retains keyboard focus and forwards native menu
                    # keys; activating its auxiliary surface would blur and
                    # dismiss the source before an item can be selected.
                    if req.state:self.auxiliary_activation.open(state,sender_pid,activate=req.kind!=6)
                    else:self.auxiliary_activation.retire(state)
                self._respond(client,req,state,input_result=accepted)
                return
            if req.operation==12 and req.kind==6 and self.popup_capabilities:
                rectangle=ControlRect()
                if req.x==int(req.x) and 0<=req.x<65536:
                    rectangle=self.native.nxs_control_popup_item_rect(state['native'],int(req.x))
                self._respond(client,req,state,rectangle=rectangle)
                return
            if req.operation==13 and self.popup_capabilities:
                if req.width or req.height:
                    bounds=ControlRect(req.x,req.y,req.width,req.height)
                    accepted=(self.native.nxs_control_set_screen_bounds(state['native'],bounds)
                              if hasattr(self.native,'nxs_control_set_screen_bounds') else 0)
                    if accepted and state.get('screen_bounds')!=(req.x,req.y,req.width,req.height):
                        state['screen_bounds']=(req.x,req.y,req.width,req.height)
                        self.log('native-control-screen-bounds',process=req.process,control=req.control,
                                 x=req.x,y=req.y,width=req.width,height=req.height)
                else:
                    accepted=self.native.nxs_control_set_screen_origin(state['native'],req.x,req.y)
                if accepted and state.get('screen_origin')!=(req.x,req.y):
                    state['screen_origin']=(req.x,req.y)
                    self.log('native-control-screen-origin',process=req.process,control=req.control,
                             x=req.x,y=req.y)
                self._respond(client,req,state,input_result=accepted)
                return
            if req.operation == 2 and self.idle():
                state['starting'] = True
                state['press_sequence']=req.reserved
                self.pending.append(lambda: self.track(state, req.x, req.y, req.modifiers))
            elif req.operation==68:
                accepted=bool(state['client'] is client and not req.text_size and
                    (not self.input_owner or self.owns_process(client,req.process,sender_pid)) and
                    req.value>0 and req.value==state.get('press_sequence'))
                if accepted:
                    if self.active is state:
                        self.native.nxs_control_send(state['native'],0,-10000,-10000,0)
                        self.native.nxs_control_send(state['native'],1,-10000,-10000,0)
                        self.finish_tracking(state)
                    elif state.get('starting'):
                        state['starting']=False;state['cancel_start']=True
                self._respond(client,req,state,input_result=int(accepted));return
            elif req.operation in (3, 4):
                if self.active is state:
                    self.native.nxs_control_send(state['native'], 0 if req.operation == 3 else 1, req.x, req.y, req.modifiers)
                    self.finish_tracking(state)
                elif state.get('starting'):
                    # Preserve real motion/release that outruns queued native
                    # mouseDown. Explicit cancellation/retirement have their
                    # own paths; an ordinary quick click is not cancellation.
                    state.setdefault('pending_pointer',[]).append(
                        (0 if req.operation==3 else 1,req.x,req.y,req.modifiers))
            elif req.operation == 6:
                self.color_owners.retire(state)
                state['destroy'] = True
                if self.active is state:
                    if req.kind!=16:self.native.nxs_control_send(state['native'], 0, -1, -1, 0)
                    self.native.nxs_control_send(state['native'], 1, -1, -1, 0)
                    self.finish_tracking(state)
        if state and req.operation in (2,4):self.record_input_result(client,req,state,0)
        self._respond(client, req, state, pixels=req.operation==5 and req.kind in (*self.text_kinds,10,12,13,15,16,17,18))

    def list_snapshot(self,state):
        value=self.native.nxs_control_list_state(state['native'])
        if value.count>4096 or value.selected_count>value.count:raise RuntimeError('Invalid native list snapshot')
        selection=(C.c_uint64*value.selected_count)()
        if self.native.nxs_control_list_selection(state['native'],selection,value.selected_count)!=value.selected_count:
            raise RuntimeError('Native list selection changed during snapshot')
        scale=state.get('presentation',1)
        scale_rectangle(value.visible,scale)
        value.content[0]*=scale;value.content[1]*=scale
        return bytes(ListWireState(value.count,value.selected_count,value.flags,0,value.primary,value.key_cell,value.actions,value.visible,value.content))+bytes(selection)

    def list_message(self,client,data):
        operation=int.from_bytes(data[4:8],'little')
        header=ControlListRequest if operation==48 else ControlListItemRequest if operation==50 else ControlRequest
        if len(data)<C.sizeof(header):return
        req=header.from_buffer_copy(data)
        if req.magic!=MAGIC or req.kind!=13 or req.text_size!=len(data)-C.sizeof(req) or req.text_size>65536:
            self._respond(client,req);return
        state=self.controls.get((req.process,req.control,req.kind))
        if not state or state['destroy'] or state['client'] is not client or not self.list_capabilities:
            self._respond(client,req);return
        if operation!=48 and (req.text_size or len(data)!=C.sizeof(header)):
            self._respond(client,req);return
        if operation==49:
            self._respond(client,req,state,input_result=1,payload=self.list_snapshot(state));return
        if operation==50:
            rect=self.native.nxs_control_list_item_rect(state['native'],req.identifier)
            accepted=rect.width>0 and rect.height>0
            self._respond(client,req,state,input_result=int(accepted),rectangle=rect,payload=self.list_snapshot(state) if accepted else b'');return
        if operation==51:
            req.x/=state.get('presentation',1);req.y/=state.get('presentation',1)
            accepted=not self._tracking(state) and math.isfinite(req.x) and math.isfinite(req.y) and self.native.nxs_control_list_scroll(state['native'],req.x,req.y)
            self._respond(client,req,state,input_result=int(bool(accepted)),payload=self.list_snapshot(state) if accepted else b'');return
        scale=state.get('presentation') or (self.native.nxs_control_backing_scale(state['native']) if hasattr(self.native,'nxs_control_backing_scale') else 1)
        dimensions=state.get('dimensions',(1,1))
        if self._tracking(state) or req.count>4096 or req.flags&~1 or not math.isfinite(req.scale) or req.scale!=scale or math.floor(dimensions[0]*scale+.5)*math.floor(dimensions[1]*scale+.5)>8*1024*1024:
            self._respond(client,req);return
        offset=C.sizeof(req);items=(ListItem*req.count)()
        for index in range(req.count):
            if offset+C.sizeof(ListWireItem)>len(data):self._respond(client,req);return
            item=ListWireItem.from_buffer_copy(data,offset);offset+=C.sizeof(ListWireItem)
            if item.enabled not in (0,1) or item.selected not in (0,1) or item.reserved or offset+item.title_size>len(data):
                self._respond(client,req);return
            title=data[offset:offset+item.title_size];offset+=item.title_size
            try:title.decode('utf-8')
            except UnicodeDecodeError:self._respond(client,req);return
            if b'\0' in title:self._respond(client,req);return
            items[index]=ListItem(C.sizeof(ListItem),item.identifier,title,item.enabled,item.selected)
        if offset!=len(data):self._respond(client,req);return
        accepted=self.native.nxs_control_list_items(state['native'],items,req.count,req.flags,req.key_cell)
        if accepted:state['scale']=scale
        self._respond(client,req,state,input_result=int(bool(accepted)),payload=self.list_snapshot(state) if accepted else b'')

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
            if req.width or req.height:
                req.width/=state.get('presentation',1);req.height/=state.get('presentation',1)
                if req.width!=rect.width or req.height!=rect.height:
                    if self._tracking(state) or not self.radio_capabilities&2 or not self.native.nxs_control_radio_cell_size(state['native'],req.width,req.height):
                        self._respond(client,req);return
                    rect=self.native.nxs_control_radio_item_rect(state['native'],req.identifier)
            scale=state.get('scale',1);bitmap=self.native.nxs_control_draw(state['native'],scale)
            x,y,width,height=[math.floor(v*scale+.5) for v in (rect.x,rect.y,rect.width,rect.height)]
            if not bitmap.pixels or min(x,y)<0 or min(width,height)<1 or x+width>bitmap.width or y+height>bitmap.height:
                self._respond(client,req);return
            pixels=b''.join(C.string_at(bitmap.pixels+(y+row)*bitmap.stride+x*4,width*4) for row in range(height))
            state['invalidated']=False
            self._respond(client,req,state,input_result=1,rectangle=rect,image=(width,height,width*4,pixels));return
        if self._tracking(state) or req.count>4096 or not req.columns or (req.count and req.columns>req.count) or not native_presentation_scale_supported(req.scale):
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
        if accepted:state['scale']=state.get('presentation',req.scale)
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
        if self._tracking(state) or count>4096 or not native_presentation_scale_supported(req.scale):
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

    def specialized_message(self,client,data,sender_pid=None):
        operation=int.from_bytes(data[4:8],'little')
        layout=ControlColorRequest if operation==55 else ControlDateRequest if operation==57 else ControlRequest
        if len(data)!=C.sizeof(layout):return
        req=layout.from_buffer_copy(data)
        if req.magic!=MAGIC:return
        state=self.controls.get((req.process,req.control,req.kind))
        if state and (state['destroy'] or state['client'] is not client):state=None
        if not state and operation==56:state=self.color_owners.resolve(client,req,sender_pid)
        color=operation in (55,56);flag=2 if color else 4;kind=16 if color else 17
        accepted=bool(state and req.kind==kind and not req.text_size and self.specialized_capabilities&flag)
        model=(ColorModel if color else DateModel)(size=C.sizeof(ColorModel if color else DateModel))
        if accepted:
            if operation==55:
                model.red,model.green,model.blue,model.alpha=req.red,req.green,req.blue,req.alpha
                snapshot=(model.red,model.green,model.blue,model.alpha)
                if self.color_owners.stale_echo(state,snapshot):accepted=True
                else:
                    accepted=bool(self.native.nxs_control_color_sync(state['native'],C.byref(model)))
                    if accepted:
                        changed=snapshot!=state.get('color_model')
                        state['color_model']=snapshot;state['color_model_actions']=state['actions']
                        if changed:
                            self.color_owners.model_applied(state)
                            self.invalidate(state['key'][0],state)
            elif operation==57:
                model.flags,model.elements,model.style=req.flags,req.elements,req.style
                model.value,model.minimum,model.maximum=req.value,req.minimum,req.maximum
                accepted=not req.padding and bool(self.native.nxs_control_date_sync(state['native'],C.byref(model)))
            else:
                accepted=bool(getattr(self.native,'nxs_control_color_get' if color else 'nxs_control_date_get')(state['native'],C.byref(model)))
                if accepted and color:self.color_owners.acknowledge(client,req,state)
        if not accepted and operation in (55,57):
            self.log('native-specialized-model-rejected',operation=operation,process=req.process,control=req.control,exists=bool(state),same_client=bool(state and state['client'] is client),tracking=bool(state and self._tracking(state)))
        self._respond(client,req,state,input_result=int(bool(accepted)),pixels=bool(accepted and operation in (55,57)),payload=bytes(model) if accepted and operation in (56,58) else b'')

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

    def edit_bindings_message(self, client, data, sender_pid):
        header_size = C.sizeof(ControlInputRequest)
        if len(data) < header_size:
            return
        req = ControlInputRequest.from_buffer_copy(data)
        if (req.magic != MAGIC or req.kind or not req.control or req.focused not in (0, 1)
                or req.text_size + req.unmodified_size != len(data) - header_size
                or len(data) - header_size > 128 or req.type or req.repeat > 1
                or req.modifiers & ~15 or not (req.key < 15 or 32 <= req.key <= 55)
                or not self.edit_bindings_available
                or not self.owns_process(client, req.process, sender_pid)):
            self._respond(client, req)
            return
        owner = self.notifiers[req.process]
        interpreter = owner.get('edit_bindings')
        if not req.focused:
            if not req.text_size and not req.unmodified_size and interpreter and owner.get('editor') == req.control:
                self.native.nxs_edit_bindings_reset(interpreter)
                owner.pop('editor', None)
            self._respond(client, req)
            return
        text = data[header_size:header_size + req.text_size]
        unmodified = data[header_size + req.text_size:]
        if b'\0' in text or b'\0' in unmodified:
            self._respond(client, req)
            return
        if not interpreter:
            interpreter = self.native.nxs_edit_bindings_create()
            if not interpreter:
                self._respond(client, req)
                return
            owner['edit_bindings'] = interpreter
        if owner.get('editor') != req.control:
            self.native.nxs_edit_bindings_reset(interpreter)
            owner['editor'] = req.control
        commands = []

        @EditCommand
        def receive(context, selector):
            commands.append(selector)

        event = KeyEvent(C.sizeof(KeyEvent), req.type, req.modifiers, req.key, req.repeat,
                         text, unmodified if req.unmodified_size else None)
        result = self.native.nxs_edit_bindings_resolve(interpreter, C.byref(event), receive, None)
        self._respond(client, req, input_result=result,
                      payload=b''.join(command + b'\0' for command in commands))

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
            state['last_key']=(req.reserved,result)
        self._respond(client, req, state, input_result=result,
            payload=self.radio_snapshot(state) if req.kind==12 and self.radio_capabilities else self.list_snapshot(state) if req.kind==13 and self.list_capabilities else b'')

    def pump_tracking(self,context):
        state=self.contexts.get(context)
        if (state is not None and state is self.active and not state['destroy'] and
                self.native.nxs_control_state(state['native']).tracking):
            for event in state.pop('pending_pointer',[]):
                self.native.nxs_control_send(state['native'],*event)
        self.dispatch(0)

    def track(self, state, x, y, modifiers,click_count=None):
        if state['destroy'] or state.pop('cancel_start',False):
            state.pop('pending_pointer',None)
            state['starting'] = False
            self.log('native-form-cancelled-before-start',process=state['key'][0],control=state['key'][1],kind=state['key'][2])
            return
        self.active, state['starting'] = state, False
        self.log('native-form-press', process=state['key'][0], control=state['key'][1], kind=state['key'][2], x=x, y=y,click_count=1 if click_count is None else click_count)
        try:
            if click_count is None:self.native.nxs_control_track(state['native'], x, y, modifiers)
            else:assert self.native.nxs_control_track_clicks(state['native'],x,y,modifiers,click_count)
        finally:
            self.finish_tracking(state)

    def finish_tracking(self,state):
        if self.active is state and not self.native.nxs_control_state(state['native']).tracking:
            self.active=None
            self.log('native-form-release',process=state['key'][0],control=state['key'][1],kind=state['key'][2],actions=state['actions'])

    def disconnect(self, client):
        self.auxiliary_activation.disconnect(client)
        self.color_owners.disconnect(client)
        self.drop_menu_replies(client=client)
        for process,entry in list(self.notifiers.items()):
            if entry['client'] is client:
                self.remove_notifier(process)
                self.log('native-notifier-disconnect',process=process,active=len(self.notifiers))
        for state in self.controls.values():
            if state['client'] is client:
                self.destroy_later(state)

    def destroy_later(self,state):
        self.auxiliary_activation.retire(state)
        self.color_owners.retire(state)
        state['destroy']=True
        if self.active is state:
            if state['key'][2]!=16:self.native.nxs_control_send(state['native'],0,-1,-1,0)
            self.native.nxs_control_send(state['native'],1,-1,-1,0)
            self.finish_tracking(state)

    def cleanup(self):
        self.auxiliary_activation.prune()
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
        self.auxiliary_activation.close()
        for process in list(self.notifiers):self.remove_notifier(process)
        self.menus.close()
        for state in self.controls.values():
            self.native.nxs_control_destroy(state['native'])
