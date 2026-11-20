/* Apply GNUstep editing commands to the toolkit's focused editor.
 * GPL-2.0-or-later. */
#include "EditCommands.h"
#include <QKeyEvent>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPointer>
#include <QTextEdit>

class NativeEditing {
  NXSEditBindings *bindings = nullptr;
  QPointer<QWidget> focus;
  EditCommands pending{};
  int pendingKey = 0;
  Qt::KeyboardModifiers pendingModifiers{};

  static const char *method(EditCommand command)
  {
    switch (command) {
      case EditSelectAll: return "selectAll";
      case EditCopy: return "copy";
      case EditCut: return "cut";
      case EditPaste: return "paste";
      case EditUndo: return "undo";
      case EditRedo: return "redo";
      default: return nullptr;
    }
  }

  template<typename Editor>
  static void apply(Editor *editor, EditCommand command)
  {
    bool backward = command == EditBackward || command == EditBackwardSelecting;
    bool extend = command == EditBackwardSelecting || command == EditForwardSelecting;
    editor->moveCursor(backward ? QTextCursor::PreviousCharacter : QTextCursor::NextCharacter,
                       extend ? QTextCursor::KeepAnchor : QTextCursor::MoveAnchor);
  }

  static void execute(QWidget *editor, EditCommand command)
  {
    if (const char *slot = method(command))
      QMetaObject::invokeMethod(editor, slot, Qt::DirectConnection);
    else if (auto *entry = qobject_cast<QLineEdit *>(editor)) {
      if (command == EditBackward || command == EditBackwardSelecting)
        entry->cursorBackward(command == EditBackwardSelecting);
      else
        entry->cursorForward(command == EditForwardSelecting);
    } else if (auto *text = qobject_cast<QTextEdit *>(editor))
      apply(text, command);
    else if (auto *text = qobject_cast<QPlainTextEdit *>(editor))
      apply(text, command);
  }

  void resolve(QKeyEvent *key)
  {
    pending = {};
    pendingKey = 0;
    const auto modifiers = key->modifiers();
    if (!modifiers.testAnyFlags(Qt::AltModifier | Qt::ControlModifier | Qt::MetaModifier) ||
        modifiers.testFlag(Qt::GroupSwitchModifier) || key->key() < Qt::Key_Space ||
        key->key() > Qt::Key_ydiaeresis)
      return;
    QByteArray text = key->text().toUtf8();
    QByteArray plain = QString(QChar(key->key()).toLower()).toUtf8();
    NXSKeyEvent event{sizeof(event), NXS_KEY_DOWN, 0, NXS_KEY_TEXT, unsigned(key->isAutoRepeat()),
                      text.constData(), plain.constData()};
    if (modifiers.testFlag(Qt::AltModifier)) event.modifiers |= NXS_ALT;
    if (modifiers.testFlag(Qt::ControlModifier)) event.modifiers |= NXS_CONTROL;
    if (modifiers.testFlag(Qt::ShiftModifier)) event.modifiers |= NXS_SHIFT;
    if (modifiers.testFlag(Qt::MetaModifier)) event.modifiers |= NXS_SUPER;
    if (!bindings) bindings = nxs_edit_bindings_create();
    int result = nxs_edit_bindings_resolve(bindings, &event, nextspace_collect_edit_command, &pending);
    if (result == NXS_EDIT_SEQUENCE || (result == NXS_EDIT_COMMANDS && !pending.unsupported && pending.count)) {
      pendingKey = key->key();
      pendingModifiers = modifiers;
    }
  }

public:
  ~NativeEditing() { nxs_edit_bindings_destroy(bindings); }

  void focusChanged(QWidget *current)
  {
    focus = current;
    pendingKey = 0;
    nxs_edit_bindings_reset(bindings);
  }

  bool filter(QWidget *widget, QEvent *event)
  {
    if (event->type() != QEvent::ShortcutOverride && event->type() != QEvent::KeyPress)
      return false;
    if (widget != focus || widget->layoutDirection() == Qt::RightToLeft ||
        widget->property("nextspaceOriginalEditing").toBool() ||
        (!qobject_cast<QLineEdit *>(widget) && !qobject_cast<QPlainTextEdit *>(widget) &&
         !qobject_cast<QTextEdit *>(widget)))
      return false;
    auto *key = static_cast<QKeyEvent *>(event);
    if (event->type() == QEvent::ShortcutOverride) {
      resolve(key);
      if (pendingKey)
        key->accept();
      return pendingKey != 0;
    }
    if (pendingKey != key->key() || pendingModifiers != key->modifiers())
      return false;
    pendingKey = 0;
    const auto commands = pending;
    QPointer<QWidget> target(widget);
    for (unsigned index = 0; index < commands.count && target; ++index)
      execute(target, commands.actions[index]);
    return true;
  }
};
