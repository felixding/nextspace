/* Shared native DOM ownership and root adoption; no widget drawing or key map. */
function nxsNativeControlsState() {
  const key = Symbol.for('org.nextspace.native-controls');
  if (globalThis[key]) return globalThis[key];
    const state = {roots: new WeakSet(), controls: new WeakMap(), nextGroup: 1, outlines: new Map(), transients: new Map()};
    // Native widgets own their complete key interpretation. Suppress only
    // replaced widget handlers, preserving application/document shortcuts.
    // Retain listener identity, capture, once, abort and object-listener rules.
    const listeners = new WeakMap();
    const add = EventTarget.prototype.addEventListener;
    const remove = EventTarget.prototype.removeEventListener;
    const nativeEvent = event => event.composedPath().some(element =>
      element.dataset?.nextspaceNativeControl || element.dataset?.nextspaceNativeInput);
    const replacedWidget = target => {
      if (target?.dataset?.nextspaceNativeControl || target?.dataset?.nextspaceNativeInput) return false;
      const owns = element => state.controls.has(element) && state.controls.get(element).nativeKeyboard !== false;
      return owns(target) || state.outlines.has(target) ||
        owns(target?.host) || owns(target?.getRootNode?.().host);
    };
    const listener = (type, callback, options, create) => {
      if (!['keydown', 'keyup', 'keypress'].includes(type) || !callback ||
          !['function', 'object'].includes(typeof callback)) return callback;
      const capture = typeof options === 'boolean' ? options : !!options?.capture;
      const identity = type + ':' + capture;
      let map = listeners.get(callback);
      if (!map) { if (!create) return callback; listeners.set(callback, map = new Map()); }
      if (!map.has(identity) && create) map.set(identity, function(event) {
        if (replacedWidget(this) && nativeEvent(event)) return;
        if (typeof callback === 'function') return Reflect.apply(callback, this, [event]);
        return callback.handleEvent(event);
      });
      return map.get(identity) || callback;
    };
    EventTarget.prototype.addEventListener = function(type, callback, options) {
      return Reflect.apply(add, this, [type, listener(type, callback, options, true), options]);
    };
    EventTarget.prototype.removeEventListener = function(type, callback, options) {
      return Reflect.apply(remove, this, [type, listener(type, callback, options, false), options]);
    };
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(`
      input:not([type=hidden]), textarea, select, button, progress {
        appearance: auto !important;
        border: revert !important; border-radius: revert !important;
        background: revert !important; color: revert !important;
        box-shadow: none !important; padding: revert !important;
        outline: none !important;
        font: inherit !important; line-height: normal !important;
      }
      [data-nextspace-native-control] {
        all: revert !important; appearance: auto !important;
        font: inherit !important; vertical-align: middle !important;
      }
    `);
    state.root = root => {
      if (!root) return;
      state.bindRoot?.(root);
      if (!root.adoptedStyleSheets.includes(sheet)) {
        root.adoptedStyleSheets = [...root.adoptedStyleSheets, sheet];
      }
      for (const tree of [root, ...root.querySelectorAll('[role=tree]')]) {
        if (tree.getAttribute?.('role') === 'tree') state.bindTree?.(tree, state);
      }
      if (state.roots.has(root)) return;
      state.roots.add(root);
      new MutationObserver(records => {
        // A component's output attributes are not another model update.
        // Only structural changes may rediscover component bindings; ARIA
        // changes notify hierarchy data consumers without reentering render.
        const structure = records.some(record => record.type === 'childList');
        if (structure || records.some(record => record.attributeName === 'role')) state.root(root);
        if (structure && root.host) state.bindHost?.(root.host);
        for (const [tree, controller] of state.outlines) {
          if (tree.isConnected) controller.schedule(); else state.outlines.delete(tree);
        }
      }).observe(root, {childList: true, subtree: true, attributes: true,
        attributeFilter: ['role', 'aria-level', 'aria-expanded', 'aria-selected', 'aria-disabled', 'hidden']});
      for (const element of root.querySelectorAll('*')) {
        if (element.shadowRoot) state.root(element.shadowRoot);
      }
    };
    const attach = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function(...args) {
      const root = Reflect.apply(attach, this, args);
      state.root(root);
      return root;
    };
    // Menu lifetime also applies to retained browser chrome, which does not
    // adopt the built-in-page control styles.
    new MutationObserver(() => {
      for (const [owner, close] of state.transients) if (!owner.isConnected) close();
    }).observe(document, {childList: true, subtree: true});
  globalThis[key] = state;
  return state;
}
