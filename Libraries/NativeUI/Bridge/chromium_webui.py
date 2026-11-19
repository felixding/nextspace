"""Bind shared Chromium WebUI components to the existing native HTML adapter.

The original executable and resources are untouched. One owned launch directory
hard-links the unchanged executable and links its assets, with a private data
pack containing the shared component adapter. No page resource is selected by
URL, name or page-specific selector.
"""
import gzip
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import struct
import uuid
from private_webui import private_application

EXECUTABLE_SHA256 = '7bcc9f719bc77d34358194026b4f148a468e97e4ddc45366e6ce02c119fb9bd1'
PACK_SHA256 = '443e6f201153bbce1b273d741be342b011d6104587ebbf4f3676d4abb35b329e'
SHARED_BASES = {
    49840: ('728557ab6a3bce694766c4285a97e57403bf5897874a6035027eb729d9f9d7d6',
            'connectedCallback(){super.connectedCallback();this.ensureInitialRender()}'),
    40079: ('7bb7146e5a725fb1a74296e7f44c841ac24a76932e6e29c6f146e24867691d24',
            'connectedCallback(){super.connectedCallback();this.ensureInitialRender();}'),
}
DEVTOOLS_LEGACY = 51795
DEVTOOLS_SHA256 = '413b9912ab4bd88983203520f1ffba7dff05f3f3fec17335d6d872f93aa8c08e'


def unpack_resource(raw):
    if raw.startswith(b'\x1f\x8b'):
        return gzip.decompress(raw)
    if raw.startswith(b'\x1e\x9b'):
        # Chromium GRIT's Brotli header carries a six-byte decoded length.
        size = C.c_size_t(int.from_bytes(raw[2:8], 'little'))
        if size.value > 16*1024*1024:
            raise ValueError('Unexpected shared WebUI resource size')
        decoder = C.CDLL('libbrotlidec.so.1')
        decoder.BrotliDecoderDecompress.argtypes = [C.c_size_t, C.c_void_p, C.POINTER(C.c_size_t), C.c_void_p]
        output = C.create_string_buffer(size.value)
        if decoder.BrotliDecoderDecompress(len(raw)-8, raw[8:], C.byref(size), output) != 1:
            raise ValueError('Invalid shared WebUI compressed resource')
        return output.raw[:size.value]
    return raw


def patch_pack(data, adapter):
    if hashlib.sha256(data).hexdigest() != PACK_SHA256:
        raise ValueError('Unsupported Chromium WebUI resource pack')
    version, encoding, count, aliases = struct.unpack_from('<IBxxxHH', data)
    if version != 5:
        raise ValueError('Unsupported Chromium resource pack version')
    rows = [struct.unpack_from('<HI', data, 12 + i * 6) for i in range(count + 1)]
    alias_data = data[12 + (count + 1) * 6:rows[0][1]]
    assert len(alias_data) == aliases * 4
    resources = []; changed = []
    for i, (identifier, start) in enumerate(rows[:-1]):
        raw = data[start:rows[i + 1][1]]
        if identifier == DEVTOOLS_LEGACY:
            source = unpack_resource(raw)
            if hashlib.sha256(source).hexdigest() != DEVTOOLS_SHA256:
                raise ValueError('Shared DevTools framework differs from audited source')
            text = source.decode()
            # The original ContextMenu already has a native-host path, complete
            # with source command handlers, closing callbacks and logging.
            anchor = 'i=this.useSoftMenu||o.useSoftMenu||te.InspectorFrontendHost.InspectorFrontendHostInstance.isHostedMode();if(!this.useSoftMenu&&o.useSoftMenu&&this.event.altKey&&(i=!1),i)'
            assert text.count(anchor) == 1
            text = text.replace(anchor, 'i=te.InspectorFrontendHost.InspectorFrontendHostInstance.isHostedMode();if(i)', 1)
            anchor = 'appendCustomItem(e,t){let i=new je(this.contextMenu,"item",void 0,void 0,void 0,void 0,void 0,void 0,t);return i.customElement=e,this.items.push(i),i}'
            assert text.count(anchor) == 1
            text = text.replace(anchor, 'appendCustomItem(e,t){return nxsNativeCustomMenu(this,e,t)}', 1)
            anchor = 'this.prompt.initialize(r||(()=>Promise.resolve([]))," ",a),'
            assert text.count(anchor) == 1
            text = text.replace(anchor, anchor + '!r&&nxsNativeTextPrompt(this.prompt,this.element),', 1)
            raw = gzip.compress((adapter + '\n' + text).encode(), mtime=0)
            changed.append(identifier)
        elif identifier in SHARED_BASES:
            compressed = raw.startswith(b'\x1f\x8b')
            source = gzip.decompress(raw) if compressed else raw
            digest, anchor = SHARED_BASES[identifier]
            if hashlib.sha256(source).hexdigest() != digest:
                raise ValueError('Shared WebUI base differs from audited source')
            text = source.decode()
            assert text.count('class CrLitElement extends i$1') == 1
            assert text.count(anchor) == 1
            text = text.replace('class CrLitElement extends i$1',
                                adapter + '\nclass CrLitElement extends i$1', 1)
            text = text.replace(anchor, anchor[:-1] + ';nxsNativeWebUI(this)}', 1)
            raw = text.encode()
            if compressed:
                raw = gzip.compress(raw, mtime=0)
            changed.append(identifier)
        resources.append((identifier, raw))
    assert set(changed) == set(SHARED_BASES) | {DEVTOOLS_LEGACY}
    offset = rows[0][1]; table = bytearray(); body = bytearray()
    for identifier, resource in resources:
        table += struct.pack('<HI', identifier, offset)
        body += resource; offset += len(resource)
    table += struct.pack('<HI', 0, offset)
    return data[:12] + table + alias_data + body, changed


def prepare_native_webui(executable, profile, lifetime, environment):
    executable = Path(executable).resolve()
    with executable.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != EXECUTABLE_SHA256:
            raise ValueError('Unsupported Chromium executable for native WebUI')
    profile = Path(profile)
    prefix = 'nxs-webui-' + uuid.uuid4().hex + '-'
    adapter = (Path(__file__).with_name('NativeWebControls.js').read_text() + '\n' +
               Path(__file__).with_name('ChromiumWebUI.js').read_text()).replace('__NXS_RADIO_PREFIX__', prefix)
    pack, changed = patch_pack((executable.parent / 'resources.pak').read_bytes(), adapter)
    environment['NEXTSPACE_CHROMIUM_WEBUI_RADIO_PREFIX'] = prefix
    root = private_application(executable, {'resources.pak': pack}, lifetime)
    receipt = json.dumps({
        'root': str(root), 'owner_pid': os.getpid(),
        'executable_sha256': EXECUTABLE_SHA256, 'original_pack_sha256': PACK_SHA256,
        'private_pack_sha256': hashlib.sha256(pack).hexdigest(),
        'shared_base_resources': changed,
        'adapter_sha256': hashlib.sha256(adapter.encode()).hexdigest(),
        'adapter_prefix': prefix,
    }, indent=2) + '\n'
    (root / 'native-webui.json').write_text(receipt)
    profile.mkdir(parents=True, exist_ok=True)
    (profile / 'native-webui.json').write_text(receipt)
    return root / executable.name
