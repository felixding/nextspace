/* Shared DevTools menu model adapter. Firefox's existing Menu API owns native
 * popup creation; GNUstep owns presentation, tracking and key interpretation. */
"use strict";
const Menu = require("resource://devtools/client/framework/menu.js");
const MenuItem = require("resource://devtools/client/framework/menu-item.js");
const DevToolsUtils = require("resource://devtools/shared/DevToolsUtils.js");

function hide(tooltip) {
  const active = tooltip._nextspaceNativeMenu;
  if (!active) return;
  tooltip._nextspaceNativeMenu = null;
  active.cancelled = true;
  active.document?.getElementById(active.id)?.hidePopup();
  active.anchor.classList.remove("tooltip-anchor");
  tooltip.emit("hidden");
}

async function show(tooltip, anchor) {
  if (tooltip._nextspaceNativeMenu) return;
  const active = {anchor, id: "nextspace-devtools-menu-" + Services.uuid.generateUUID().toString()};
  tooltip._nextspaceNativeMenu = active;
  // MenuButton mounts its React portal when expanded. Read the settled original
  // semantic model, including Fluent labels, rather than a second item model.
  await new Promise(resolve => anchor.ownerDocument.defaultView.requestAnimationFrame(resolve));
  if (active.cancelled || !anchor.isConnected) { hide(tooltip); return; }
  const menu = new Menu({id: active.id});
  for (const item of tooltip.panel.querySelectorAll('[role=menuitem], [role=menuitemcheckbox], [role=menuitemradio], [role=separator]')) {
    if (item.hidden || item.closest('[hidden]')) continue;
    const role = item.getAttribute('role');
    menu.append(new MenuItem({
      type: role === 'separator' ? 'separator' : role === 'menuitemcheckbox' ? 'checkbox' : role === 'menuitemradio' ? 'radio' : 'normal',
      label: item.getAttribute('aria-label') || item.querySelector('.label')?.textContent || item.textContent.trim(),
      accelerator: item.querySelector('.accelerator')?.textContent || null,
      accesskey: item.getAttribute('accesskey'),
      disabled: item.disabled || item.getAttribute('aria-disabled') === 'true',
      checked: item.getAttribute('aria-checked') === 'true',
      click: () => {
        if (item.isConnected && !item.disabled && item.getAttribute('aria-disabled') !== 'true') item.click();
        hide(tooltip);
      },
    }));
  }
  tooltip.container.style.setProperty('display', 'none', 'important');
  anchor.classList.add('tooltip-anchor');
  active.document = DevToolsUtils.getTopWindow(anchor.ownerDocument.defaultView).document;
  menu.on('open', () => { if (!active.cancelled) tooltip.emit('shown'); });
  menu.on('close', () => { if (tooltip._nextspaceNativeMenu === active) hide(tooltip); });
  // Gecko supplies the complete nested-document/zoom projection in top chrome
  // CSS coordinates. Passing that document avoids a second zoom conversion.
  const bounds = anchor.ownerDocument.defaultView.windowUtils.getElementBoundingScreenRect(anchor);
  menu.popup(bounds.x + bounds.width / 2, bounds.bottom, active.document);
}

module.exports = {show, hide};
