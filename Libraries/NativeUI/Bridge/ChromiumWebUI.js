/* WebUI component/model adapters. HTML controls enter the existing Blink ->
 * NativeUI -> GNUstep path. No widget drawing, key map or browser actions live
 * here. Inserted beside Chromium's shared CrLitElement, never into a page. */
function nxsNativeWebUI(host, bindingKind) {
  if (!['chrome:', 'chrome-untrusted:', 'devtools:'].includes(location.protocol)) return;
  const state = nxsNativeControlsState();
  state.bindHost = nxsNativeWebUI;
  state.bindRoot = root => {
    for (const select of root.querySelectorAll('select:not([data-nextspace-native-control])')) {
      if (select.multiple || select.size > 1 || select.dataset.nextspaceNativeInput === 'menu') continue;
      if (select.firstElementChild?.dataset.nextspaceNativeModel === 'popup') continue;
      // An empty hidden group identifies the shared native model without
      // changing the application's option collection, values or indices.
      const marker = document.createElement('optgroup');
      marker.label = '__NXS_RADIO_PREFIX__popup'; marker.hidden = true;
      marker.style.display = 'none'; marker.dataset.nextspaceNativeModel = 'popup';
      select.prepend(marker);
    }
  };
  // Inspector trees render editable code and syntax annotations. Their rich
  // content retains its original renderer; ordinary hierarchy widgets use the
  // shared native outline model.
  state.bindTree = location.protocol === 'devtools:' ? null : nxsNativeOutline;
  state.root(document);
  state.root(host.shadowRoot);
  if (state.controls.has(host)) {
    state.controls.get(host).hostUpdated();
    return;
  }
  const kind = bindingKind || new Map([
    ['cr-button', 'button'], ['cr-toggle', 'checkbox'],
    ['cr-checkbox', 'checkbox'], ['cr-slider', 'range'], ['cr-icon-button', 'icon'],
    ['cr-progress', 'progress'],
  ]).get(host.localName);
  const search = host.localName === 'cr-toolbar-search-field';
  const field = ['cr-input', 'cr-textarea'].includes(host.localName);
  const group = typeof host.select_ === 'function' && 'selectableElements' in host;
  const menu = host.localName === 'cr-action-menu';
  const navigation = host.localName === 'cr-menu-selector';
  const tabs = host.localName === 'cr-tabs';
  if (!kind && !search && !field && !group && !menu && !navigation && !tabs) return;
  const root = host.shadowRoot;
  if (!root) return;
  const controller = {scheduled: false};
  const style = new CSSStyleSheet();
  if (navigation || tabs) {
    const select = document.createElement('select');
    const originals = Array.from(root.children).map(e => e.id ? '#' + CSS.escape(e.id) : e.localName)
      .filter(s => s !== 'style').join(',');
    select.dataset.nextspaceNativeControl = navigation ? 'navigation' : 'tabs';
    select.setAttribute('aria-label', host.getAttribute('aria-label') || (tabs ? 'Tabs' : 'Navigation'));
    if (tabs) {
      const marker = document.createElement('option');
      marker.hidden = true; marker.disabled = true;
      marker.style.display = 'none';
      marker.setAttribute('role', 'presentation');
      marker.textContent = '__NXS_RADIO_PREFIX__tabs';
      select.append(marker);
      select.setAttribute('role', 'tablist');
    }
    root.append(select);
    style.replaceSync(`${originals} { display: none !important; }
      [data-nextspace-native-control] { display: block !important; width: 100% !important;
        box-sizing: border-box !important; ${tabs ? 'height: 100% !important;' : ''} }`);
    controller.sync = () => {
      const items = tabs ? host.tabNames || [] : Array.from(host.querySelectorAll(host.selectable || '[role=menuitem]'));
      controller.items = items;
      const offset = tabs ? 1 : 0;
      while (select.options.length > items.length + offset) select.options.remove(select.options.length - 1);
      while (select.options.length < items.length + offset) select.append(document.createElement('option'));
      items.forEach((item, index) => {
        const option = select.options[index + offset];
        const label = tabs ? String(item) : item.textContent.trim();
        if (option.textContent !== label) option.textContent = label;
        option.value = index;
        if (tabs) {
          option.setAttribute('role', 'tab');
          option.setAttribute('aria-selected', index === host.selected ? 'true' : 'false');
        }
        option.disabled = tabs ? false : !!(item.disabled || item.getAttribute('aria-disabled') === 'true');
        option.hidden = tabs ? false : item.hidden || getComputedStyle(item).display === 'none';
      });
      if (navigation) select.size = Math.max(2, items.length);
      select.selectedIndex = tabs ? host.selected + offset : items.indexOf(host.selectedItem);
    };
    select.addEventListener('change', () => {
      const index = Number(select.value);
      if (tabs) host.selected = index;
      else controller.items[index]?.click();
    });
    select.addEventListener('pointerdown', event => {
      select.focus({preventScroll: true});
      event.stopPropagation();
    });
    host.focus = options => select.focus(options);
    host.dataset.nextspaceNative = tabs ? 'tabs' : 'navigation';
  } else if (menu) {
    const close = host.close.bind(host);
    controller.sync = () => {};
    host.close = (...args) => {
      const select = controller.select;
      if (!select) return close(...args);
      controller.select = null;
      nxsNativeMenuOwners().delete(host);
      select.remove();
      close(...args);
      // Retain the component's original close notification/controller path.
      host.onNativeDialogClose_({target: host.getDialog()});
    };
    const open = (rect, anchor) => {
      host.close();
      host.anchorElement_ = anchor || null;
      const select = document.createElement('select');
      const marker = document.createElement('option');
      marker.textContent = '__NXS_RADIO_PREFIX__menu';
      marker.hidden = marker.disabled = true;
      marker.style.display = 'none'; marker.setAttribute('role', 'presentation');
      select.append(marker); select.setAttribute('role', 'menu');
      const items = [];
      for (const item of host.querySelectorAll('.dropdown-item, [role=menuitem], [role=menuitemcheckbox], [role=menuitemradio], hr')) {
        let visible = true;
        for (let p = item; p && p !== host; p = p.parentElement) {
          if (p.hidden || getComputedStyle(p).display === 'none') { visible = false; break; }
        }
        if (!visible) continue;
        if (item.localName === 'hr') { select.append(document.createElement('hr')); continue; }
        const option = document.createElement('option');
        const label = item.getAttribute('aria-label') || item.textContent.trim();
        option.disabled = item.disabled || item.getAttribute('aria-disabled') === 'true';
        const mixed = item.indeterminate || item.getAttribute('aria-checked') === 'mixed';
        const checked = item.checked || item.getAttribute('aria-checked') === 'true';
        option.textContent = ((option.disabled ? 2 : 0) | (mixed ? 8 : checked ? 4 : 0)) + '|' + label;
        option.setAttribute('aria-label', label);
        option.setAttribute('role', item.getAttribute('role') || 'menuitem');
        if (item.hasAttribute('aria-checked')) option.setAttribute('aria-checked', item.getAttribute('aria-checked'));
        option.value = items.length;
        items.push(item); select.append(option);
      }
      if (!items.length) return;
      select.selectedIndex = -1;
      select.style.cssText = `position:fixed;left:${rect.left}px;top:${rect.top}px;
        width:${Math.max(1, rect.width || 1)}px;height:${Math.max(1, rect.height || 1)}px;
        opacity:0;pointer-events:none;appearance:auto;`;
      select.setAttribute('aria-label', host.accessibilityLabel || 'Menu');
      document.body.append(select);
      controller.select = select;
      nxsNativeMenuOwners().set(host, () => host.close());
      host.open = true;
      select.addEventListener('change', () => {
        const item = items[Number(select.value)];
        host.close();
        if (item?.isConnected && host.contains(item) && !item.disabled &&
            item.getAttribute('aria-disabled') !== 'true' && !item.hidden) item.click();
      });
      select.addEventListener('cancel', () => host.close());
      // Routing ownership must not apply the visible-widget reset to this
      // transparent screen-space menu anchor.
      select.dataset.nextspaceNativeInput = 'menu';
      // The original popup key path follows the focused owning select.
      // The shared native NSMenu owns tracking, Escape and menu navigation.
      select.focus({preventScroll: true});
      try { select.showPicker(); }
      catch (error) { host.close(); throw error; }
      const observe = () => {
        if (controller.select !== select) return;
        if (!select.matches(':open')) { host.close(); return; }
        requestAnimationFrame(observe);
      };
      requestAnimationFrame(observe);
    };
    host.showAt = anchor => {
      anchor.scrollIntoViewIfNeeded();
      const rect = anchor.getBoundingClientRect();
      open({left: rect.left, top: rect.bottom}, anchor);
    };
    host.showAtPosition = config => open(config);
    host.setUnbounded = async () => false; // NSMenu owns the external native surface.
  } else if (group) {
    const identifier = state.nextGroup++;
    controller.sync = () => {
      (host.buttons_ || []).forEach((radio, index) => {
        nxsNativeWebUI(radio, 'radio');
        const input = state.controls.get(radio)?.input;
        if (input) input.name = '__NXS_RADIO_PREFIX__' + identifier + ':' + index;
      });
    };
  } else if (kind) {
    if (kind === 'icon') {
      style.replaceSync(`:host { position: relative !important; background: none !important; border: 0 !important;
        border-radius: 0 !important; outline: none !important; box-shadow: none !important; }
        :host::before, :host::after { display: none !important; }
        #icon { pointer-events: none !important; position: relative; z-index: 1; }
        [data-nextspace-native-control] { position: absolute !important; inset: 0 !important;
          display: block !important; width: 100% !important; height: 100% !important; margin: 0 !important; }`);
    } else if (kind === 'checkbox' && host.localName === 'cr-checkbox') {
      style.replaceSync(`#checkbox > :not([data-nextspace-native-control]) { display: none !important; }
        #checkbox { border: 0 !important; background: none !important; box-shadow: none !important;
          border-radius: 0 !important; width: auto !important; height: auto !important; }
        [data-nextspace-native-control] { display: inline-block !important; margin: 0 !important; }`);
    } else if (kind === 'radio') {
      style.replaceSync(`.disc-wrapper > :not([data-nextspace-native-control]),
        #checkMark { display: none !important; }
        .disc-wrapper { border-radius: 0 !important; }
        [data-nextspace-native-control] { display: inline-block !important; margin: 0 !important; }`);
    } else {
    style.replaceSync(`
      :host { background: none !important; border: 0 !important;
        outline: none !important;
        box-shadow: none !important; border-radius: 0 !important;
        padding: 0 !important; min-width: 0 !important;
        ${kind === 'range' ? '' : 'width: auto !important; height: auto !important;'} }
      ${Array.from(root.children).map(e => e.id ? '#' + CSS.escape(e.id) : e.localName)
          .filter(s => s !== 'style').join(',')} { display: none !important; }
      [data-nextspace-native-control] { display: inline-block !important;
        ${kind === 'range' ? 'width: 100% !important;' : ''} }
    `);
    }
    const input = document.createElement(kind === 'icon' ? 'button' : kind === 'progress' ? 'progress' : 'input');
    if (kind !== 'progress') input.type = kind === 'icon' ? 'button' : kind;
    input.dataset.nextspaceNativeControl = host.localName;
    for (const type of kind === 'progress' ? [] : ['pointerdown', 'pointermove', 'pointerup']) {
      input.addEventListener(type, event => {
        if (type === 'pointerdown' && event.button === 0 && !input.disabled) {
          input.focus({preventScroll: true});
        }
        event.stopPropagation();
      });
    }
    // A custom component can cancel its child's default click while changing
    // its own model. Read the settled original model after Blink completes
    // the cancelled input transaction, rather than its pre-rollback state.
    input.addEventListener('click', () => setTimeout(() => controller.sync(), 0));
    if (kind === 'range') {
      input.addEventListener('input', event => {
        event.stopPropagation();
        if (host.updateValue_(input.valueAsNumber)) host.fire('cr-slider-value-changed');
      });
      input.addEventListener('change', event => event.stopPropagation());
    }
    const originalRadio = kind === 'radio' ? root.querySelector('#button') :
      host.localName === 'cr-checkbox' ? root.querySelector('#checkbox') : null;
    const container = kind === 'radio' ? root.querySelector('.disc-wrapper') || originalRadio || root :
      originalRadio || root;
    container.append(input);
    controller.input = input;
    controller.focus = host.focus;
    host.focus = options => input.focus(options);
    controller.sync = () => {
      input.disabled = !!(host.disabled || host.disabled_);
      input.checked = !!host.checked;
      input.indeterminate = !!host.indeterminate;
      const labelled = (host.getAttribute('aria-labelledby') || '').split(/\s+/)
        .map(id => host.getRootNode().getElementById?.(id)?.textContent || '').join(' ').trim();
      const relatedLabel = Array.from(host.ariaLabelledByElements || [])
        .map(element => element.textContent).join(' ').trim();
      input.setAttribute('aria-label', host.getAttribute('aria-label') ||
        host.ariaLabelOverride || relatedLabel || labelled || host.label || host.title || host.textContent.trim());
      for (const name of ['aria-description', 'aria-valuetext', 'aria-valuenow', 'aria-valuemin', 'aria-valuemax']) {
        const value = host.getAttribute(name);
        if (value !== null) input.setAttribute(name, value);
      }
      if (kind === 'button') input.value = host.textContent.trim();
      if (kind === 'range') {
        input.min = host.min; input.max = host.max;
        input.step = host.snaps ? '1' : 'any';
        input.value = host.value;
      }
      if (kind === 'progress') {
        input.max = host.max - host.min;
        if (host.indeterminate) input.removeAttribute('value');
        else input.value = host.value - host.min;
      }
      if (kind === 'radio') input.tabIndex = host.focusable && !input.disabled ? 0 : -1;
      if (originalRadio) {
          originalRadio.tabIndex = -1;
          originalRadio.removeAttribute('role');
          originalRadio.removeAttribute('aria-checked');
      }
      // Preserve the original component's accessible role on the actual
      // native input and expose just one sequential focus stop.
      const role = host.getAttribute('role');
      if (role) { input.setAttribute('role', role); host.removeAttribute('role'); }
      if (host.hasAttribute('tabindex')) {
        controller.tabIndex = host.tabIndex;
        host.removeAttribute('tabindex');
      }
      if (!['radio', 'progress'].includes(kind)) input.tabIndex = controller.tabIndex ?? 0;
    };
    host.dataset.nextspaceNative = kind;
  } else if (field) {
    style.replaceSync(`#input-container, #inner-input-container, #inner-input-content {
      background: none !important; border: 0 !important; border-radius: 0 !important;
      box-shadow: none !important; padding: 0 !important; min-height: 0 !important; height: auto !important;
    } #hover-layer, #underline-base, #underline { display: none !important; }
    input { width: 100% !important; height: auto !important; min-height: 0 !important;
      box-sizing: border-box !important; }
    :host([type=search]) slot[name=inline-prefix], :host([type=search]) slot[name=suffix] {
      display: none !important;
    }`);
    controller.sync = () => {
      const input = root.querySelector('input, textarea');
      if (input) input.dataset.nextspaceNativeInput = 'field';
    };
  } else {
    style.replaceSync(`:host { outline: none !important; border: 0 !important;
      box-shadow: none !important; border-radius: 0 !important; background: none !important; }
    #background, #stateBackground, #icon, #prompt, #clearSearch {
      display: none !important;
    } #content { background: none !important; }
    #searchInput { width: 100% !important; height: auto !important; }`);
    controller.sync = () => {
      const input = root.querySelector('input');
      if (input) { input.placeholder = host.label || ''; input.dataset.nextspaceNativeInput = 'search'; }
    };
  }
  root.adoptedStyleSheets = [...root.adoptedStyleSheets, style];
  controller.hostUpdated = () => {
    if (controller.scheduled) return;
    controller.scheduled = true;
    queueMicrotask(() => {
      controller.scheduled = false;
      controller.sync();
    });
  };
  state.controls.set(host, controller);
  host.addController?.(controller);
  new MutationObserver(() => controller.hostUpdated()).observe(host, {attributes: true});
  controller.hostUpdated();
}

/* One semantic hierarchy adapter for shared and page-owned tree components.
 * Native NSOutlineView chooses selection, disclosure, focus, and key actions.
 * Existing tree items retain their original click/double-click model actions.
 * No page URL, element name, drawing, row metrics or keyboard map is used. */
function nxsNativeOutline(tree, state) {
  if (state.outlines.has(tree) || tree.dataset.nextspaceNativeControl === 'outline') return;
  const select = document.createElement('select');
  const marker = document.createElement('option');
  marker.textContent = '__NXS_RADIO_PREFIX__tree';
  marker.setAttribute('role', 'presentation');
  marker.hidden = marker.disabled = true;
  marker.style.display = 'none';
  select.append(marker);
  select.dataset.nextspaceNativeControl = 'outline';
  select.setAttribute('role', 'tree');
  select.setAttribute('aria-label', tree.getAttribute('aria-label') || 'Tree');
  select.setAttribute('aria-hidden', 'true');
  select.style.cssText = 'position:absolute!important;inset:0!important;width:100%!important;height:100%!important;box-sizing:border-box!important;margin:0!important;display:block!important;';
  if (getComputedStyle(tree).position === 'static') tree.style.position = 'relative';
  const controller = {scheduled: false, items: [], options: new WeakMap()};
  state.outlines.set(tree, controller);
  tree.append(select);
  const rows = () => {
    const result = [];
    const walk = (root, level) => {
      for (const element of root.children) {
        if (element === select) continue;
        let next = level;
        if (element.getAttribute('role') === 'treeitem' && !element.hidden) {
          next = Number(element.getAttribute('aria-level')) || level + 1;
          result.push({element, level: next});
        }
        walk(element, next);
        if (element.shadowRoot) walk(element.shadowRoot, next);
      }
    };
    walk(tree, 0);
    return result;
  };
  controller.sync = () => {
    select.disabled = tree.disabled === true || tree.getAttribute('aria-disabled') === 'true';
    const items = rows(), ancestors = [];
    controller.items = items;
    const expected = [marker];
    for (let index = 0; index < items.length; index++) {
      const {element, level} = items[index];
      while (ancestors.length && ancestors.at(-1).level >= level) ancestors.pop();
      const parent = ancestors.at(-1)?.index + 1 || 0;
      ancestors.push({level, index});
      let options = controller.options.get(element);
      if (!options) {
        options = Array.from({length: 4}, () => {
          const option = document.createElement('option');
          option.setAttribute('role', 'presentation');
          return option;
        });
        controller.options.set(element, options);
      }
      const flags = (element.getAttribute('aria-disabled') !== 'true' ? 1 : 0) |
        (element.getAttribute('aria-selected') === 'true' ? 2 : 0) |
        (element.hasAttribute('aria-expanded') ? 4 : 0) |
        (element.getAttribute('aria-expanded') === 'true' ? 8 : 0);
      const label = element.getAttribute('aria-label') || element.textContent.trim();
      const metadata = `${parent}|${flags}|${label}`;
      if (options[0].textContent !== metadata) options[0].textContent = metadata;
      options.forEach((option, action) => {
        option.value = index + ':' + (action - 1);
        expected.push(option);
      });
      element.tabIndex = -1;
      element.focus = options => select.focus(options);
    }
    if (Array.from(select.children).some((item, i) => item !== expected[i]) || select.children.length !== expected.length) {
      select.replaceChildren(...expected);
    }
    select.selectedIndex = -1;
    for (const child of tree.children) if (child !== select) child.style.opacity = '0';
  };
  controller.schedule = () => {
    if (controller.scheduled) return;
    controller.scheduled = true;
    queueMicrotask(() => { controller.scheduled = false; controller.sync(); });
  };
  select.addEventListener('change', () => {
    const [index, action] = select.value.split(':').map(Number);
    const element = controller.items[index]?.element;
    if (!element?.isConnected || element.getAttribute('aria-disabled') === 'true') return;
    if (action === 2) controller.contextElement = element;
    else if (action === 0) element.click();
    else if (element.hasAttribute('aria-expanded') &&
             (element.getAttribute('aria-expanded') === 'true') !== (action === 1)) {
      element.dispatchEvent(new MouseEvent('dblclick', {bubbles: true, composed: true}));
    }
    controller.schedule();
  });
  select.addEventListener('pointerdown', event => {
    select.focus({preventScroll: true});
    event.stopPropagation();
  });
  select.addEventListener('pointerdown', event => {
    if (event.button === 2) { controller.contextPointer = true; controller.contextElement = null; }
  });
  select.addEventListener('contextmenu', event => {
    const element = controller.contextElement || (!controller.contextPointer &&
      controller.items.find(item => item.element.getAttribute('aria-selected') === 'true')?.element);
    controller.contextPointer = false; controller.contextElement = null;
    if (!element?.isConnected) return;
    event.preventDefault(); event.stopPropagation();
    element.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, composed: true,
      button: event.button, buttons: event.buttons, clientX: event.clientX, clientY: event.clientY,
      screenX: event.screenX, screenY: event.screenY, shiftKey: event.shiftKey,
      ctrlKey: event.ctrlKey, altKey: event.altKey, metaKey: event.metaKey}));
  });
  tree.focus = options => select.focus(options);
  controller.schedule();
}

// Install before component constructors register their original key handlers.
nxsNativeWebUI(document);

/* A custom menu row can contain several original application buttons. Publish
 * those actions as native menu items, retaining their labels and callbacks.
 * The shared menu API, rather than a page adapter, owns this conversion. */
function nxsNativeCustomMenu(section, element, context) {
  const buttons = [];
  function collect(root) {
    for (const child of root.children) {
      if (child.matches('button, devtools-button, [role="button"], [role^="menuitem"]')) buttons.push(child);
      else { collect(child); if (child.shadowRoot) collect(child.shadowRoot); }
    }
  }
  collect(element);
  const caption = element.cloneNode(true);
  for (const button of caption.querySelectorAll('button, devtools-button, [role="button"], [role^="menuitem"]')) button.remove();
  const title = caption.textContent.trim() || element.getAttribute('aria-label') || element.title;
  if (!buttons.length) return section.appendItem(title, () => element.click(), {jslogContext: context});
  const menu = section.appendSubMenuItem(title, false, context);
  for (const button of buttons) {
    const label = button.getAttribute('aria-label') || button.title || button.textContent.trim();
    const options = {disabled: button.disabled || button.getAttribute('aria-disabled') === 'true'};
    const pressed = button.getAttribute('aria-pressed');
    if (pressed !== null) {
      options.checked = pressed === 'true';
      menu.defaultSection().appendCheckboxItem(label, () => button.click(), options);
    } else menu.defaultSection().appendItem(label, () => button.click(), options);
  }
  return menu;
}

/* DevTools' ordinary toolbar fields use TextPrompt even without completion or
 * rich editing. Bind that shared model to an actual input. NativeUI owns its
 * editor; the original prompt still publishes application text-change events.
 * Code editors and prompts with application completion retain their renderer. */
function nxsNativeTextPrompt(prompt, wrapper) {
  const original = prompt.element();
  const input = document.createElement('input');
  input.type = 'text'; input.value = prompt.text();
  for (const name of ['aria-label', 'aria-labelledby', 'aria-description', 'title']) {
    if (original.hasAttribute(name)) input.setAttribute(name, original.getAttribute(name));
  }
  input.dataset.nextspaceNativeInput = 'field';
  input.style.cssText = 'width:100%;min-width:0;box-sizing:border-box;font:inherit';
  original.removeAttribute('contenteditable'); original.removeAttribute('role');
  original.removeEventListener('keydown', prompt.boundOnKeyDown);
  original.tabIndex = -1;
  original.append(input);
  for (const element of [original, wrapper]) {
    for (const [name, value] of Object.entries({background: 'none', border: '0',
      'border-radius': '0', 'box-shadow': 'none', padding: '0'})) element.style.setProperty(name, value, 'important');
  }
  for (const type of ['focus', 'blur']) input.addEventListener(type, () => original.dispatchEvent(new FocusEvent(type)));
  prompt.element = () => input;
  prompt.text = () => input.value;
  prompt.setText = value => { prompt.clearAutocomplete(); input.value = value; prompt.previousText = value; };
  prompt.setEnabled = enabled => { input.disabled = !enabled; };
  prompt.setPlaceholder = (value, label) => {
    input.placeholder = value || '';
    if (label || value) input.setAttribute('aria-label', label || value);
  };
  prompt.setSelectedRange = prompt.setDOMSelection = (start, end) => input.setSelectionRange(start, end);
  prompt.moveCaretToEndOfPrompt = () => input.setSelectionRange(input.value.length, input.value.length);
  prompt.getCaretPosition = () => input.matches(':focus') && input.selectionStart === input.selectionEnd ? input.selectionStart : -1;
  prompt.isCaretAtEndOfPrompt = () => prompt.getCaretPosition() === input.value.length;
}
