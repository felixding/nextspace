"""FileChooser data adapter; every visible component belongs to NativeUI.

No file browsing, editing, selection, modal or overwrite UI lives here.
GPL-2.0-or-later.
"""
import ctypes as C
import fnmatch
import os
from gi.repository import Gio, GLib

PUMP = C.CFUNCTYPE(None, C.c_void_p)
ALLOWS = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_char_p, C.c_uint32)
STRINGS = C.POINTER(C.c_char_p)


class Choice(C.Structure):
    _fields_ = [('size', C.c_uint32), ('count', C.c_uint32),
                ('selected', C.c_uint32), ('reserved', C.c_uint32),
                ('label', C.c_char_p), ('options', STRINGS)]


class Config(C.Structure):
    _fields_ = [(name, C.c_uint32) for name in
                ('size', 'flags', 'filter_count', 'selected_filter', 'choice_count', 'batch_count')]
    _fields_ += [(name, C.c_char_p) for name in ('title', 'directory', 'name', 'accept_label')]
    _fields_ += [('filter_titles', STRINGS), ('choices', C.POINTER(Choice)), ('batch_names', STRINGS),
                ('parent_window', C.c_char_p)]


class State(C.Structure):
    _fields_ = [('size', C.c_uint32), ('result', C.c_int32),
                ('count', C.c_uint32), ('selected_filter', C.c_uint32)]


def text(value):
    if not isinstance(value, str) or '\0' in value:
        raise ValueError('Expected text without NUL characters')
    encoded = value.encode('utf-8')
    if len(encoded) > 65536:
        raise ValueError('Text exceeds the native model limit')
    return encoded


def path_bytes(value):
    raw = bytes(value)
    if not raw or raw[-1] != 0 or b'\0' in raw[:-1]:
        raise ValueError('Expected a NUL-terminated filename')
    return text(raw[:-1].decode('utf-8'))


def mnemonic(value):
    # Portal labels use underscores for mnemonics; AppKit owns key handling.
    return value.replace('__', '\0').replace('_', '').replace('\0', '_')


class Model:
    def __init__(self, method, title, options, parent=''):
        self.config = Config(size=C.sizeof(Config), title=text(title))
        self.config.parent_window = text(parent) if parent else None
        self.mode = int(method == 'SaveFile')
        self.filters = list(options.get('filters', []))
        current = options.get('current_filter')
        if current is not None and current not in self.filters:
            self.filters.append(current)
        if len(self.filters) > 64:
            raise ValueError('Too many filters')
        for label, rules in self.filters:
            text(label)
            if len(rules) > 256:
                raise ValueError('Too many filter rules')
            for kind, pattern in rules:
                if kind not in (0, 1):
                    raise ValueError('Unknown filter type')
                text(pattern)
        self.config.filter_count = len(self.filters)
        self.config.selected_filter = self.filters.index(current) if current is not None else 0
        self.filter_titles = (C.c_char_p * len(self.filters))(*(text(f[0]) for f in self.filters))
        self.config.filter_titles = self.filter_titles
        self.choice_models = list(options.get('choices', []))
        if len(self.choice_models) > 64:
            raise ValueError('Too many choices')
        self.choices = (Choice * len(self.choice_models))()
        self.option_arrays = []
        identifiers = set()
        for index, (identifier, label, values, selected) in enumerate(self.choice_models):
            text(identifier)
            if not identifier or identifier in identifiers or len(values) > 64:
                raise ValueError('Invalid choice identity or count')
            identifiers.add(identifier)
            ids = [v[0] for v in values]
            if len(set(ids)) != len(ids) or any(not item for item in ids):
                raise ValueError('Invalid option identity')
            for item in ids:
                text(item)
            if values:
                chosen = ids.index(selected) if selected else 0
            else:
                if selected not in ('', 'true', 'false'):
                    raise ValueError('Invalid boolean choice')
                chosen = int(selected == 'true')
            array = (C.c_char_p * len(values))(*(text(v[1]) for v in values))
            self.option_arrays.append(array)
            self.choices[index] = Choice(C.sizeof(Choice), len(values), chosen, 0, text(label), array)
        self.config.choice_count = len(self.choices)
        self.config.choices = self.choices
        if options.get('current_folder'):
            self.config.directory = path_bytes(options['current_folder'])
            if not os.path.isabs(self.config.directory):
                raise ValueError('The initial folder must be absolute')
        if method == 'OpenFile':
            self.config.flags = int(options.get('multiple', False)) | (2 if options.get('directory') else 0)
        elif method == 'SaveFile':
            self.config.name = text(options.get('current_name', ''))
            if options.get('current_file'):
                filename = path_bytes(options['current_file'])
                if not os.path.isabs(filename):
                    raise ValueError('The initial file must be absolute')
                self.config.directory, self.config.name = os.path.split(filename)
        elif method == 'SaveFiles':
            files = options.get('files', [])
            if not 0 < len(files) <= 4096:
                raise ValueError('Expected one or more file names')
            names = [path_bytes(value) for value in files]
            if any(not name or name in (b'.', b'..') or b'/' in name for name in names):
                raise ValueError('Batch files must have single-component names')
            self.batch_names = (C.c_char_p * len(names))(*names)
            self.config.batch_count = len(names)
            self.config.batch_names = self.batch_names
            self.config.flags = 2
        else:
            raise ValueError('Unknown file dialog method')
        if 'accept_label' in options:
            value = options['accept_label']
            text(value)
            self.config.accept_label = text(mnemonic(value))

    def allows(self, unused, filename, index):
        try:
            if not self.filters:
                return 1
            rules = self.filters[index][1]
            basename = os.path.basename(filename.decode('utf-8'))
            content_type = None
            for kind, pattern in rules:
                if kind == 0 and fnmatch.fnmatchcase(basename, pattern):
                    return 1
                if kind == 1:
                    if content_type is None:
                        content_type = Gio.content_type_guess(filename.decode('utf-8'), None)[0]
                    if Gio.content_type_is_a(content_type, pattern):
                        return 1
            return 0
        except Exception:
            return 0

    def results(self, native, panel):
        state = native.nxs_file_panel_state(panel)
        if state.result != 0 or not state.count:
            raise RuntimeError('The native panel has no accepted selection')
        uris = []
        for index in range(state.count):
            count = native.nxs_file_panel_result(panel, index, None, 0)
            if not 1 < count <= 1048576:
                raise RuntimeError('Invalid native file URI')
            buffer = C.create_string_buffer(count)
            if native.nxs_file_panel_result(panel, index, buffer, count) != count:
                raise RuntimeError('Native file selection changed')
            uri = buffer.value.decode('utf-8')
            if not uri.startswith('file://'):
                raise RuntimeError('The native panel returned a non-file URI')
            uris.append(uri)
        result = {'uris': GLib.Variant('as', uris)}
        choices = []
        for index, (identifier, label, values, selected) in enumerate(self.choice_models):
            chosen = native.nxs_file_panel_choice(panel, index)
            if not 0 <= chosen < (len(values) or 2):
                raise RuntimeError('Invalid native choice')
            choices.append((identifier, values[chosen][0] if values else ('false', 'true')[chosen]))
        if choices:
            result['choices'] = GLib.Variant('a(ss)', choices)
        if self.filters:
            result['current_filter'] = GLib.Variant('(sa(us))', self.filters[state.selected_filter])
        return result


def load(path):
    native = C.CDLL(str(path))
    declarations = {
        'nxs_file_panel_capabilities': (C.c_uint, []),
        'nxs_native_ui_callback_source_capabilities': (C.c_uint, []),
        'nxs_native_ui_source_callback': (C.c_void_p, [C.c_int, PUMP, C.c_void_p]),
        'nxs_native_ui_source_destroy': (C.c_int, [C.c_void_p]),
        'nxs_native_ui_dispatch_events': (C.c_double, [C.c_double]),
        'nxs_file_panel_create': (C.c_void_p, [C.c_int, ALLOWS, C.c_void_p]),
        'nxs_file_panel_configure': (C.c_int, [C.c_void_p, C.POINTER(Config)]),
        'nxs_file_panel_run': (C.c_int, [C.c_void_p]),
        'nxs_file_panel_cancel': (C.c_int, [C.c_void_p]),
        'nxs_file_panel_state': (State, [C.c_void_p]),
        'nxs_file_panel_result': (C.c_size_t, [C.c_void_p, C.c_uint32, C.c_void_p, C.c_size_t]),
        'nxs_file_panel_choice': (C.c_int, [C.c_void_p, C.c_uint32]),
        'nxs_file_panel_destroy': (C.c_int, [C.c_void_p]),
    }
    for name, (result, arguments) in declarations.items():
        function = getattr(native, name)
        function.restype, function.argtypes = result, arguments
    if not native.nxs_file_panel_capabilities() or not native.nxs_native_ui_callback_source_capabilities():
        raise RuntimeError('The selected provider lacks native file panels or modal event sources')
    return native
