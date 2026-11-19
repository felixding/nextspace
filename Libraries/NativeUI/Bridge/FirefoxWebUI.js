/* Shared Firefox component/model adapter. Existing HTML controls use Gecko's
 * NativeUI binding. Original components retain actions and application state. */
function nxsNativeFirefoxDocument() {
  return ['about:', 'chrome:', 'resource:'].includes(location.protocol) &&
    location.href !== 'chrome://browser/content/browser.xhtml';
}
function nxsNativeFirefox(host) {
  if (!nxsNativeFirefoxDocument()) return;
  const state = nxsNativeControlsState();
  state.bindHost = nxsNativeFirefox;
  state.bindRoot = root => {
    for (const input of root.querySelectorAll('input, textarea, button, select, progress')) {
      if (input.namespaceURI !== 'http://www.w3.org/1999/xhtml') continue;
      input.setAttribute('data-nextspace-native-widget', '__NXS_WEBUI_PREFIX__');
      input.dataset.nextspaceNativeInput = 'field';
    }
  };
  state.root(document);
  state.root(host.shadowRoot);
  if (!host.shadowRoot || state.controls.has(host)) return;
  const root = host.shadowRoot;
  const controller = {scheduled: false, nativeKeyboard: !!(host.inputEl ||
    host.constructor.activatedProperty || host.localName === 'moz-button' || host.localName === 'moz-radio-group')};
  const sheet = new CSSStyleSheet();
  // Ask the engine for its native control path, including wrappers that would
  // otherwise paint a second authored button or switch over that control.
  sheet.replaceSync(`button, input, select, textarea { font: inherit !important; }
    button:has(> .button-background) { position: relative !important; }
    button:has(> .button-background:not(.labelled)) {
      min-width: var(--button-size-icon) !important; min-height: var(--button-size-icon) !important;
    }
    button:has(> .button-background[size=small]:not(.labelled)) {
      min-width: var(--button-size-icon-small) !important; min-height: var(--button-size-icon-small) !important;
    }
    .button-background { position: absolute !important; inset: 0 !important;
      width: 100% !important; height: 100% !important; min-height: 0 !important;
      background-color: transparent !important; border: 0 !important;
      border-radius: 0 !important; box-shadow: none !important; padding: 0 !important; }
    .select-chevron-icon { display: none !important; }
    .select-wrapper { background: none !important; border: 0 !important;
      border-radius: 0 !important; box-shadow: none !important; }
    input::before, input::after { display: none !important; }`);
  root.adoptedStyleSheets = [...root.adoptedStyleSheets, sheet];
  if (host.localName === 'moz-toggle') {
    const input = document.createElement('input');
    input.type = 'checkbox'; input.dataset.nextspaceNativeControl = 'toggle';
    input.setAttribute('role', 'switch');
    root.append(input);
    input.addEventListener('click', event => {
      event.stopPropagation();
      root.querySelector('button')?.click();
      setTimeout(() => controller.sync(), 0);
    });
    sheet.replaceSync(`button { display: none !important; }
      input { margin: 0 !important; }`);
    host.focus = options => input.focus(options);
    controller.sync = () => {
      input.checked = !!host.pressed;
      input.disabled = !!(host.disabled || host.parentDisabled);
      input.setAttribute('aria-label', host.ariaLabel || host.label || '');
    };
  } else if (host.constructor.childElementName && host.type === 'radio') {
    controller.nativeKeyboard = true;
    const name = '__NXS_WEBUI_PREFIX__radio-' + crypto.randomUUID();
    controller.sync = () => {
      host.childElements.forEach((item, index) => {
        const input = item.shadowRoot?.querySelector('input[type=radio]');
        if (input) input.name = name + ':' + index;
      });
    };
  } else if (host.controller?.type === 'radio' && !root.querySelector('input[type=radio]')) {
    const original = root.querySelector('[role=radio]');
    if (!original) return;
    const input = document.createElement('input');
    input.type = 'radio'; input.dataset.nextspaceNativeControl = 'radio';
    original.prepend(input);
    // The original semantic item emits its own application input/change.
    for (const type of ['input', 'change']) input.addEventListener(type, event => event.stopPropagation());
    controller.nativeKeyboard = true;
    sheet.replaceSync(`.picker-item { border: 0 !important; border-radius: 0 !important;
      background: none !important; box-shadow: none !important; outline: none !important; }
      .picker-item::before, .picker-item::after { display: none !important; }`);
    host.focus = options => input.focus(options);
    controller.sync = () => {
      input.checked = !!host.checked; input.disabled = !!host.isDisabled;
      input.setAttribute('aria-label', host.label || host.getAttribute('aria-label') || host.textContent.trim());
      input.value = host.value;
      original.removeAttribute('role'); original.tabIndex = -1;
    };
  } else {
    controller.sync = () => state.bindRoot(root);
  }
  controller.hostUpdated = () => {
    if (controller.scheduled) return;
    controller.scheduled = true;
    queueMicrotask(() => {
      controller.scheduled = false;
      controller.sync();
      if (host.localName === 'moz-radio') {
        const owner = host.controller;
        if (owner) state.controls.get(owner)?.hostUpdated();
      }
    });
  };
  state.controls.set(host, controller);
  host.addController(controller);
  controller.hostUpdated();
}

/* PanelList model -> Firefox's existing native-menu API -> shared NSMenu.
 * Original popup geometry, hierarchy, activation and native key routing remain
 * in Gecko/NativeUI. Original panel items retain their application actions. */
function nxsNativeFirefoxPanelList(host) {
  if (!['about:', 'chrome:', 'resource:'].includes(location.protocol) || !document.createXULElement || host.nextspaceNativeMenu) return;
  host.nextspaceNativeMenu = true;
  host.style.setProperty('display', 'none', 'important');
  const show = host.show, hide = host.onHide;
  let active = null;
  host.show = function(...args) {
    // The foreign parent panel is replaced by the native menu presentation.
    const parent = this.parentIsXULPanel;
    this.parentIsXULPanel = () => false;
    try { return Reflect.apply(show, this, args); }
    finally { this.parentIsXULPanel = parent; }
  };
  const visible = (item, parent) => {
    for (let element = item; element && element !== parent; element = element.parentElement) {
      if (element.hidden || getComputedStyle(element).display === 'none') return false;
    }
    return true;
  };
  const populate = (panel, popup) => {
    for (const item of panel.children) {
      if (!visible(item, panel)) continue;
      if (['hr', 'panel-separator'].includes(item.localName) || item.getAttribute('role') === 'separator') {
        popup.append(document.createXULElement('menuseparator')); continue;
      }
      if (item.localName !== 'panel-item') continue;
      const submenu = item.hasSubmenu && item.submenuPanel;
      const native = document.createXULElement(submenu ? 'menu' : 'menuitem');
      native.setAttribute('label', item.button?.getAttribute('aria-label') || item.label?.textContent || item.textContent.trim());
      native.disabled = !!item.disabled;
      if (item.type === 'checkbox') {
        native.setAttribute('type', 'checkbox'); native.setAttribute('checked', String(item.checked));
        native.setAttribute('autocheck', 'false');
      }
      const accesskey = item.accessKey || item._accessKey;
      if (accesskey) native.setAttribute('accesskey', accesskey);
      if (submenu) {
        const branch = document.createXULElement('menupopup');
        branch.addEventListener('popupshowing', event => {
          if (event.target !== branch) return;
          submenu.sendEvent('showing'); branch.replaceChildren(); populate(submenu, branch);
        });
        branch.addEventListener('popupshown', event => { if (event.target === branch) submenu.sendEvent('shown'); });
        branch.addEventListener('popuphidden', event => { if (event.target === branch) submenu.sendEvent('hidden'); });
        native.append(branch);
      } else {
        native.addEventListener('command', event => {
          event.stopPropagation();
          host.hide(undefined, {force: true});
          if (item.isConnected && panel.contains(item) && !item.disabled && !item.hidden) item.click();
        });
      }
      popup.append(native);
    }
  };
  host.onShow = function() {
    this.sendEvent('showing');
    const popup = document.createXULElement('menupopup');
    active = popup; populate(this, popup);
    nxsNativeMenuOwners().set(host, () => host.hide(undefined, {force: true}));
    document.documentElement.append(popup);
    popup.addEventListener('popupshown', event => {
      if (event.target !== popup) return;
      this.lastAnchorNode?.setAttribute('aria-expanded', 'true'); this.sendEvent('shown');
    });
    popup.addEventListener('popuphidden', event => {
      if (event.target !== popup || active !== popup) return;
      active = null;
      if (this.open) this.hide(undefined, {force: true});
      popup.remove();
    });
    const event = this.triggeringEvent;
    if (event?.type === 'contextmenu') popup.openPopupAtScreen(event.screenX, event.screenY, true, event);
    else {
      // Anchored XUL popups use Gecko's custom popup renderer. Its native-menu
      // API accepts screen coordinates; use the original complete projection.
      const bounds = window.windowUtils.getElementBoundingScreenRect(this.lastAnchorNode || this.parentElement);
      popup.openPopupAtScreen(bounds.x + bounds.width / 2, bounds.bottom, true, event);
    }
  };
  host.onHide = function() {
    const popup = active; active = null;
    nxsNativeMenuOwners().delete(host);
    if (popup) { popup.hidePopup(); popup.remove(); }
    return Reflect.apply(hide, this, []);
  };
}
