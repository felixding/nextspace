"""Bind Firefox's shared MozLitElement to the common native control bridge.

One private shared module, no page patches, browser rebuild or installed-file
mutation. The ordinary launch lifetime owns the private resource archive.
"""
import hashlib
import io
import json
from pathlib import Path
import uuid
import zipfile
from private_webui import private_application

EXECUTABLE_SHA256 = '25ba4ed56923ad27ed378ea7aeab346d4c3cbb24183ffdf0183eadceae581a48'
PACK_SHA256 = '08d630209386462735294949d721a281fcaa4cd4ff59ad93e65df53f4c28c359'
BASE_PATH = 'chrome/toolkit/content/global/lit-utils.mjs'
BASE_SHA256 = '63641b89498add8324af22ab7d7357fd5ec95e8f3a8072d0ec11a0a94df269f8'
PANEL_PATH = 'chrome/toolkit/content/global/elements/panel-list.mjs'
PANEL_SHA256 = '65c5077cf499ee1ffb5b30696bac895f37243d26ba849c4236f2c181d000f100'
ADAPTER_PATH = 'chrome/toolkit/content/global/nextspace-native-controls.mjs'
CLASSIC_PATH = 'chrome/toolkit/content/global/nextspace-native-controls.js'
BROWSER_PACK_SHA256 = '00586f758b510c8105f5711804ed5fb244b4f65f8c69fc366e84d8081bd4adac'
DEVTOOLS_ROOT = 'chrome/devtools/modules/devtools/client/'
RENDERER_PATH = DEVTOOLS_ROOT + 'shared/vendor/react-dom.mjs'
RENDERER_SHA256 = 'da5bc67e755d89230f2b52d2ae40c275f30a71b875dc813056e5a2d36a62ef45'
TOOLTIP_PATH = DEVTOOLS_ROOT + 'shared/widgets/tooltip/HTMLTooltip.js'
TOOLTIP_SHA256 = '755d90092e2c4fca6000309010c056f0a468bbb6275ed91f85e6b196d6b34b29'
EDITOR_PATH = DEVTOOLS_ROOT + 'shared/sourceeditor/editor.js'
EDITOR_SHA256 = 'cdb60a1fd55f400ec65dd58a5316eeffde48de141856dedfba2f968c1061386f'
DEVTOOLS_ADAPTER_PATH = DEVTOOLS_ROOT + 'shared/nextspace-native-controls.js'


def patch_pack(data, adapter, *, replace_controls=True):
    if hashlib.sha256(data).hexdigest() != PACK_SHA256:
        raise ValueError('Unsupported Firefox shared-component archive')
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as original, zipfile.ZipFile(output, 'w') as patched:
        for item in original.infolist():
            value = original.read(item.filename)
            if replace_controls and item.filename == BASE_PATH:
                if hashlib.sha256(value).hexdigest() != BASE_SHA256:
                    raise ValueError('Shared Firefox base differs from audited source')
                text = value.decode()
                anchor = '  connectedCallback() {\n    super.connectedCallback();'
                assert text.count('export class MozLitElement extends LitElement {') == 1
                text = 'import {nxsNativeFirefox} from "chrome://global/content/nextspace-native-controls.mjs";\n' + text
                assert text.count(anchor) == 2
                text = text.replace(anchor, anchor + '\n    this.updateComplete.then(() => nxsNativeFirefox(this));', 1)
                value = text.encode()
            elif item.filename == PANEL_PATH:
                if hashlib.sha256(value).hexdigest() != PANEL_SHA256:
                    raise ValueError('Shared Firefox menu differs from audited source')
                text = value.decode()
                anchor = '    this.initializePopover();'
                assert text.count(anchor) == 1
                text = text.replace(anchor, anchor + '\n    nxsNativeFirefoxPanelList(this);', 1)
                value = ('import {nxsNativeFirefoxPanelList} from "chrome://global/content/nextspace-native-controls.mjs";\n' + text).encode()
            patched.writestr(item, value)
        patched.writestr(ADAPTER_PATH, adapter + '\nexport {nxsNativeFirefox,nxsNativeFirefoxPanelList};\n')
        if replace_controls:
            patched.writestr(CLASSIC_PATH, adapter)
        patched.comment = original.comment
    return output.getvalue()


def patch_browser_pack(data, adapter, *, replace_controls=True):
    if hashlib.sha256(data).hexdigest() != BROWSER_PACK_SHA256:
        raise ValueError('Unsupported Firefox DevTools archive')
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as original, zipfile.ZipFile(output, 'w') as patched:
        for item in original.infolist():
            value = original.read(item.filename)
            if replace_controls and item.filename == RENDERER_PATH:
                if hashlib.sha256(value).hexdigest() != RENDERER_SHA256:
                    raise ValueError('Shared Firefox renderer differs from audited source')
                text = value.decode()
                bootstrap = '''function nxsNativeDevtoolsRoot(container) {
  const doc = container.nodeType === 9 ? container : container.ownerDocument;
  const win = doc.defaultView;
  if (!win[Symbol.for('org.nextspace.native-controls')])
    Services.scriptloader.loadSubScript('chrome://global/content/nextspace-native-controls.js', win);
}
'''
                for anchor in ['function legacyRenderSubtreeIntoContainer(parentComponent, children, container, forceHydrate, callback) {',
                               'function createPortal$$1(children, container) {',
                               'function createRoot(container, options) {']:
                    assert text.count(anchor) == 1
                    text = text.replace(anchor, anchor + '\n  nxsNativeDevtoolsRoot(container);', 1)
                value = (bootstrap + text).encode()
            elif not replace_controls and item.filename == EDITOR_PATH:
                if hashlib.sha256(value).hexdigest() != EDITOR_SHA256:
                    raise ValueError('Shared Firefox editor differs from audited source')
                text = value.decode()
                setup = '    editors.set(this, cm);\n\n    this.reloadPreferences'
                controller = '    insertCommandsController(this);'
                registry = 'const editors = new WeakMap();'
                assert text.count(setup) == text.count(controller) == text.count(registry) == 1
                # Gecko's focused textarea dispatches to its existing command controller.
                # Some original DevTools callers also install it explicitly.
                text = text.replace(setup, setup.replace('\n\n', '\n    this.insertCommandsController();\n\n'), 1)
                text = text.replace(registry, registry + '\nconst nxsCommandEditors = new WeakSet();', 1)
                text = text.replace(controller,
                    '    const editor = editors.get(this);\n'
                    '    if (nxsCommandEditors.has(editor)) {\n'
                    '      return;\n'
                    '    }\n'
                    '    insertCommandsController(this);\n'
                    '    nxsCommandEditors.add(editor);', 1)
                value = text.encode()
            elif item.filename == TOOLTIP_PATH:
                if hashlib.sha256(value).hexdigest() != TOOLTIP_SHA256:
                    raise ValueError('Shared Firefox tooltip differs from audited source')
                text = value.decode()
                changes = {
                    '  async show(anchor, options) {': 'if (this.isMenuTooltip) return nxsNativeDevtools.show(this, anchor);',
                    '  async hide({ fromMouseup = false } = {}) {': 'if (this.isMenuTooltip) return nxsNativeDevtools.hide(this);',
                    '  isVisible() {': 'if (this.isMenuTooltip) return !!this._nextspaceNativeMenu;',
                    '  focus() {': 'if (this.isMenuTooltip) return !!this._nextspaceNativeMenu;',
                    '  focusEnd() {': 'if (this.isMenuTooltip) return !!this._nextspaceNativeMenu;',
                }
                for anchor, replacement in changes.items():
                    assert text.count(anchor) == 1
                    text = text.replace(anchor, anchor + '\n    ' + replacement, 1)
                value = ('const nxsNativeDevtools = require("resource://devtools/client/shared/nextspace-native-controls.js");\n' + text).encode()
            patched.writestr(item, value)
        patched.writestr(DEVTOOLS_ADAPTER_PATH, adapter)
        patched.comment = original.comment
    return output.getvalue()


def prepare_native_webui(executable, profile, lifetime, environment, *, replace_controls=True):
    executable = Path(executable).resolve()
    with executable.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != EXECUTABLE_SHA256:
            raise ValueError('Unsupported Firefox executable for native WebUI')
    prefix = 'nxs-webui-' + uuid.uuid4().hex + '-' if replace_controls else ''
    here = Path(__file__).parent
    adapter = ((here / 'NativeWebControls.js').read_text() + '\n' +
               (here / 'FirefoxWebUI.js').read_text()).replace('__NXS_WEBUI_PREFIX__', prefix)
    if replace_controls:
        adapter += '\nnxsNativeFirefox(document);\n'
    pack = patch_pack((executable.parent / 'omni.ja').read_bytes(), adapter,
                      replace_controls=replace_controls)
    devtools_adapter = (here / 'FirefoxDevTools.js').read_text()
    browser_pack = patch_browser_pack((executable.parent / 'browser/omni.ja').read_bytes(), devtools_adapter,
                                      replace_controls=replace_controls)
    if replace_controls:
        environment['NEXTSPACE_FIREFOX_WEBUI_PREFIX'] = prefix
    else:
        environment.pop('NEXTSPACE_FIREFOX_WEBUI_PREFIX', None)
    root = private_application(executable, {'omni.ja': pack, 'browser/omni.ja': browser_pack}, lifetime)
    receipt = json.dumps(dict(root=str(root), executable_sha256=EXECUTABLE_SHA256,
        original_pack_sha256=PACK_SHA256, private_pack_sha256=hashlib.sha256(pack).hexdigest(),
        original_browser_pack_sha256=BROWSER_PACK_SHA256,
        private_browser_pack_sha256=hashlib.sha256(browser_pack).hexdigest(),
        shared_base_resources=[BASE_PATH, PANEL_PATH, RENDERER_PATH, TOOLTIP_PATH] if replace_controls
                              else [PANEL_PATH, TOOLTIP_PATH, EDITOR_PATH],
        adapter_sha256=hashlib.sha256(adapter.encode()).hexdigest(),
        adapter_prefix=prefix if replace_controls else None,
        devtools_adapter_sha256=hashlib.sha256(devtools_adapter.encode()).hexdigest()), indent=2) + '\n'
    (root / 'native-webui.json').write_text(receipt)
    profile = Path(profile); profile.mkdir(parents=True, exist_ok=True)
    (profile / 'native-webui.json').write_text(receipt)
    return root / executable.name
