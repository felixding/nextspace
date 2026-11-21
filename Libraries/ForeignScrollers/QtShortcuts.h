/* Preserve the original QAction and its shortcut context. GPL-2.0-or-later. */
#include "../NativeUI/NativeUI.h"
#include <QAction>
#include <QActionEvent>
#include <QKeyEvent>
#include <QTimer>
#include <QVariant>
#include <QWidget>

class NativeShortcuts {
  static bool enabled()
  {
    const QByteArray policy = qgetenv("NEXTSPACE_SHORTCUTS");
    return policy.isEmpty() || policy == "native";
  }

  static Qt::KeyboardModifier command()
  {
    switch (nxs_physical_modifier(NXS_MENU_COMMAND)) {
      case NXS_ALT: return Qt::AltModifier;
      case NXS_CONTROL: return Qt::ControlModifier;
      case NXS_SUPER: return Qt::MetaModifier;
      default: return Qt::NoModifier;
    }
  }

  static QKeyCombination equivalent(QKeyCombination original, Qt::KeyboardModifier modifier)
  {
    const auto mods = original.keyboardModifiers();
    if (mods == Qt::ControlModifier || mods == (Qt::ControlModifier | Qt::ShiftModifier))
      return (modifier | (mods & Qt::ShiftModifier)) | original.key();
    return original;
  }

  static void bind(QAction *action)
  {
    const auto current = action->shortcuts();
    const auto previous = action->property("_nextspaceShortcutAliases").value<QList<QKeySequence>>();
    const auto installed = action->property("_nextspaceInstalledShortcuts").value<QList<QKeySequence>>();
    // Strip aliases only while the action still has the exact list we installed.
    const auto originals = current == installed ? current.mid(previous.size()) : current;
    const auto modifier = command();
    QList<QKeySequence> aliases;
    if (modifier != Qt::NoModifier && !action->property("nextspaceOriginalShortcut").toBool()) {
      for (const auto &original : originals) {
        if (original.count() != 1)
          continue;
        const QKeySequence alias(equivalent(original[0], modifier));
        if (!originals.contains(alias) && !aliases.contains(alias))
          aliases.append(alias);
      }
    }
    const auto updated = aliases + originals;
    if (updated == current && aliases == previous)
      return;
    action->setProperty("_nextspaceShortcutAliases", QVariant::fromValue(aliases));
    action->setProperty("_nextspaceInstalledShortcuts", QVariant::fromValue(updated));
    if (updated != current)
      action->setShortcuts(updated);
  }

public:
  bool filter(QWidget *widget, QEvent *event)
  {
    if (!enabled()) return false;
    if (event->type() == QEvent::ActionAdded || event->type() == QEvent::ActionChanged) {
      QAction *action = static_cast<QActionEvent *>(event)->action();
      if (!action->property("_nextspaceShortcutPending").toBool()) {
        action->setProperty("_nextspaceShortcutPending", true);
        QTimer::singleShot(0, action, [action] {
          bind(action);
          action->setProperty("_nextspaceShortcutPending", false);
        });
      }
    }
    if ((event->type() != QEvent::ShortcutOverride && event->type() != QEvent::KeyPress) ||
        !widget->hasFocus())
      return false;
    auto *key = static_cast<QKeyEvent *>(event);
    const auto modifier = command();
    const auto mods = key->modifiers() & ~Qt::ShiftModifier;
    if (modifier == Qt::NoModifier || modifier == Qt::ControlModifier || mods != modifier)
      return false;

    const QKeySequence shortcut(key->keyCombination());
    // Check the actual focused widget's action scope before Qt can interpret
    // an Alt-based Command chord as a menu mnemonic.
    for (QWidget *owner = widget; owner; owner = owner->isWindow() ? nullptr : owner->parentWidget()) {
      QAction *match = nullptr;
      for (QAction *action : owner->actions()) {
        if (!action->isVisible() || !action->shortcuts().contains(shortcut) ||
            (action->shortcutContext() == Qt::WidgetShortcut && owner != widget))
          continue;
        if (match || action->property("nextspaceOriginalShortcut").toBool() ||
            !action->property("_nextspaceShortcutAliases").value<QList<QKeySequence>>().contains(shortcut))
          return false;
        match = action;
      }
      if (!match)
        continue;
      key->accept();
      if (event->type() == QEvent::KeyPress && match->isEnabled() &&
          (!key->isAutoRepeat() || match->autoRepeat()))
        match->trigger();
      return true;
    }
    return false;
  }
};
