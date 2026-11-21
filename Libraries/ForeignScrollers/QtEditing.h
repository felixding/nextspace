/* Apply GNUstep editing commands to the toolkit's focused editor.
 * GPL-2.0-or-later. */
#include "EditCommands.h"
#include <QAccessible>
#include <QAction>
#include <QComboBox>
#include <QCoreApplication>
#include <QKeyEvent>
#include <QKeySequence>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QPointer>
#include <QScopedValueRollback>
#include <QScrollBar>
#include <QTextBoundaryFinder>
#include <QTextEdit>

class NativeEditing {
  NXSEditBindings *bindings = nullptr;
  QPointer<QWidget> focus;
  EditCommands pending{};
  int pendingKey = 0;
  Qt::KeyboardModifiers pendingModifiers{};
  bool applying = false;
  QString killedText;

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

  struct Motion {
    QTextCursor::MoveOperation cursor;
    QKeySequence::StandardKey move, extend;
  };

  static Motion motion(EditOperation operation)
  {
    using Cursor = QTextCursor;
    using Key = QKeySequence;
    const bool backward = operation.direction < 0;
    switch (operation.unit) {
      case EditCharacter:
        return backward ? Motion{Cursor::PreviousCharacter, Key::MoveToPreviousChar, Key::SelectPreviousChar}
                        : Motion{Cursor::NextCharacter, Key::MoveToNextChar, Key::SelectNextChar};
      case EditVisualCharacter:
        return backward ? Motion{Cursor::Left, Key::MoveToPreviousChar, Key::SelectPreviousChar}
                        : Motion{Cursor::Right, Key::MoveToNextChar, Key::SelectNextChar};
      case EditWord:
        return backward ? Motion{Cursor::PreviousWord, Key::MoveToPreviousWord, Key::SelectPreviousWord}
                        : Motion{Cursor::NextWord, Key::MoveToNextWord, Key::SelectNextWord};
      case EditLine:
        return backward ? Motion{Cursor::Up, Key::MoveToPreviousLine, Key::SelectPreviousLine}
                        : Motion{Cursor::Down, Key::MoveToNextLine, Key::SelectNextLine};
      case EditLineEnd:
        return backward ? Motion{Cursor::StartOfLine, Key::MoveToStartOfLine, Key::SelectStartOfLine}
                        : Motion{Cursor::EndOfLine, Key::MoveToEndOfLine, Key::SelectEndOfLine};
      case EditParagraphEnd:
        return backward ? Motion{Cursor::StartOfBlock, Key::MoveToStartOfBlock, Key::SelectStartOfBlock}
                        : Motion{Cursor::EndOfBlock, Key::MoveToEndOfBlock, Key::SelectEndOfBlock};
      case EditDocumentEnd:
        return backward ? Motion{Cursor::Start, Key::MoveToStartOfDocument, Key::SelectStartOfDocument}
                        : Motion{Cursor::End, Key::MoveToEndOfDocument, Key::SelectEndOfDocument};
      case EditPage:
        return backward ? Motion{Cursor::NoMove, Key::MoveToPreviousPage, Key::SelectPreviousPage}
                        : Motion{Cursor::NoMove, Key::MoveToNextPage, Key::SelectNextPage};
    }
    return {Cursor::NoMove, Key::UnknownKey, Key::UnknownKey};
  }

  static void moveEntry(QLineEdit *entry, EditOperation operation)
  {
    const bool backward = operation.direction < 0;
    switch (operation.unit) {
      case EditCharacter:
        if (backward) entry->cursorBackward(operation.extend);
        else entry->cursorForward(operation.extend);
        return;
      case EditVisualCharacter: {
        const auto movement = motion(operation);
        applyStandard(entry, operation.extend ? movement.extend : movement.move);
        return;
      }
      case EditWord:
        if (backward) entry->cursorWordBackward(operation.extend);
        else entry->cursorWordForward(operation.extend);
        return;
      case EditLineEnd: case EditParagraphEnd: case EditDocumentEnd:
        if (backward) entry->home(operation.extend);
        else entry->end(operation.extend);
        return;
      default: return;
    }
  }

  static int wordBoundary(QAccessibleTextInterface *text, int origin, int length, bool backward)
  {
    // Use word starts when moving backward and word ends when moving forward.
    const int lower = qMax(0, origin - 4096), upper = origin + qMin(4096, length - origin);
    const QString around = text->text(lower, upper);
    QTextBoundaryFinder finder(QTextBoundaryFinder::Word, around);
    if (!finder.isValid() || origin - lower > around.size())
      return -1;
    finder.setPosition(origin - lower);
    auto boundary = backward ? QTextBoundaryFinder::StartOfItem : QTextBoundaryFinder::EndOfItem;
    qsizetype offset;
    do {
      offset = backward ? finder.toPreviousBoundary() : finder.toNextBoundary();
    } while (offset >= 0 && !(finder.boundaryReasons() & boundary));
    if ((backward && lower > 0 && offset <= 0) ||
        (!backward && upper < length && (offset < 0 || offset == around.size())))
      return -1;
    return offset < 0 ? (backward ? 0 : length) : lower + offset;
  }

  static int paragraphBoundary(QAccessibleTextInterface *text, int origin, bool backward)
  {
    int start = -1, end = -1;
    auto paragraph = text->textAtOffset(origin, QAccessible::ParagraphBoundary, &start, &end);
    if (start < 0 || end < start)
      return -1;
    if (backward)
      return start;
    while (paragraph.endsWith(u'\n') || paragraph.endsWith(u'\r')) {
      --end;
      paragraph.chop(1);
    }
    return qMax(start, end);
  }

  static bool moveBoundary(QWidget *editor, EditOperation operation)
  {
    auto *accessible = QAccessible::queryAccessibleInterface(editor);
    auto *text = accessible ? accessible->textInterface() : nullptr;
    if (!text || accessible->state().passwordEdit)
      return false;

    const int caret = text->cursorPosition();
    const int length = text->characterCount();
    if (caret < 0 || caret > length)
      return false;
    int start = caret, end = caret;
    if (text->selectionCount())
      text->selection(0, &start, &end);
    const bool backward = operation.direction < 0;
    int origin = operation.extend ? caret : (backward ? start : end);
    if (origin < 0 || origin > length)
      return false;
    const int anchor = caret == start ? end : start;

    const int target = operation.unit == EditWord ? wordBoundary(text, origin, length, backward)
                                                  : paragraphBoundary(text, origin, backward);
    if (target < 0 || target > length)
      return false;

    if (auto *entry = qobject_cast<QLineEdit *>(editor)) {
      if (operation.extend)
        entry->setSelection(anchor, target - anchor);
      else {
        entry->deselect();
        entry->setCursorPosition(target);
      }
    } else if (auto *rich = qobject_cast<QTextEdit *>(editor)) {
      auto cursor = rich->textCursor();
      cursor.setPosition(target, operation.extend ? QTextCursor::KeepAnchor : QTextCursor::MoveAnchor);
      rich->setTextCursor(cursor);
    } else if (auto *plain = qobject_cast<QPlainTextEdit *>(editor)) {
      auto cursor = plain->textCursor();
      cursor.setPosition(target, operation.extend ? QTextCursor::KeepAnchor : QTextCursor::MoveAnchor);
      plain->setTextCursor(cursor);
    } else {
      if (!operation.extend && text->selectionCount())
        text->removeSelection(0);
      text->setCursorPosition(target);
      if (operation.extend) {
        if (anchor != target)
          text->setSelection(0, qMin(anchor, target), qMax(anchor, target));
        else if (text->selectionCount())
          text->removeSelection(0);
      }
    }
    return true;
  }

  static QKeySequence::StandardKey standard(EditCommand command)
  {
    using Key = QKeySequence;
    switch (command) {
      case EditSelectAll: return Key::SelectAll;
      case EditCopy: return Key::Copy;
      case EditCut: return Key::Cut;
      case EditPaste: return Key::Paste;
      case EditUndo: return Key::Undo;
      case EditRedo: return Key::Redo;
      case EditNewline: return Key::InsertLineSeparator;
      default: return Key::UnknownKey;
    }
  }

  static void applyKey(QWidget *editor, const QKeySequence &sequence)
  {
    if (sequence.count() != 1)
      return;
    for (auto *widget = editor; widget; widget = widget->parentWidget()) {
      for (auto *action : widget->actions()) {
        if (action->isEnabled() && action->isVisible() &&
            (widget == editor || action->shortcutContext() != Qt::WidgetShortcut) &&
            action->shortcuts().contains(sequence)) {
          action->trigger();
          return;
        }
      }
      if (widget->isWindow()) break;
    }
    auto key = sequence[0];
    QKeyEvent native(QEvent::KeyPress, key.key(), key.keyboardModifiers());
    QCoreApplication::sendEvent(editor, &native);
  }

  static void applyStandard(QWidget *editor, QKeySequence::StandardKey operation)
  {
    const auto sequences = QKeySequence::keyBindings(operation);
    if (!sequences.isEmpty())
      applyKey(editor, sequences.first());
  }

  static QScrollBar *verticalScrollBar(QWidget *editor)
  {
    if (auto *area = qobject_cast<QAbstractScrollArea *>(editor))
      return area->verticalScrollBar();
    // A custom editor may expose a separate view and scrollbar.
    if (auto *parent = editor->parentWidget())
      for (auto *bar : parent->findChildren<QScrollBar *>(Qt::FindDirectChildrenOnly))
        if (bar->orientation() == Qt::Vertical && bar->isVisible())
          return bar;
    return nullptr;
  }

  static void center(QWidget *editor)
  {
    if (auto *plain = qobject_cast<QPlainTextEdit *>(editor)) {
      plain->centerCursor();
      return;
    }
    if (auto *rich = qobject_cast<QTextEdit *>(editor)) {
      auto *bar = rich->verticalScrollBar();
      bar->setValue(bar->value() + rich->cursorRect().center().y() - rich->viewport()->height() / 2);
      return;
    }
    const QRect caret = editor->inputMethodQuery(Qt::ImCursorRectangle).toRect();
    auto *bar = verticalScrollBar(editor);
    if (caret.height() > 0 && bar && editor->height() > 0) {
      int offset = caret.center().y() - editor->height() / 2;
      bar->setValue(bar->value() + qRound(double(offset) * bar->pageStep() / editor->height()));
    }
  }

  static void scroll(QWidget *editor, EditOperation operation)
  {
    auto *bar = verticalScrollBar(editor);
    if (!bar)
      return;
    using Slider = QAbstractSlider;
    const bool backward = operation.direction < 0;
    switch (operation.unit) {
      case EditPage: bar->triggerAction(backward ? Slider::SliderPageStepSub : Slider::SliderPageStepAdd); break;
      case EditLine: bar->triggerAction(backward ? Slider::SliderSingleStepSub : Slider::SliderSingleStepAdd); break;
      case EditDocumentEnd: bar->triggerAction(backward ? Slider::SliderToMinimum : Slider::SliderToMaximum); break;
      default: break;
    }
  }

  static bool replace(QWidget *editor, const QString &text, int offset = 0, int length = 0)
  {
    if (auto *entry = qobject_cast<QLineEdit *>(editor)) {
      if (entry->isReadOnly())
        return false;
      QPointer<QLineEdit> target(entry);
      const auto before = entry->text();
      if (length)
        entry->setSelection(entry->cursorPosition() + offset, length);
      if (target) {
        if (text.isEmpty())
          target->del();
        else
          target->insert(text);
      }
      return target && target->text() != before;
    }
    QInputMethodEvent event;
    event.setCommitString(text, offset, length);
    event.setAccepted(false);
    QCoreApplication::sendEvent(editor, &event);
    return event.isAccepted();
  }

  void editText(QWidget *editor, EditCommand command)
  {
    if (command == EditCenter) {
      center(editor);
      return;
    }
    const auto enabled = editor->inputMethodQuery(Qt::ImEnabled);
    if (enabled.isValid() && !enabled.toBool())
      return;
    if (command == EditYank) {
      if (!killedText.isEmpty())
        replace(editor, killedText);
      return;
    }
    auto selection = editor->inputMethodQuery(Qt::ImCurrentSelection).toString();
    const auto text = editor->inputMethodQuery(Qt::ImSurroundingText).toString();
    const int caret = editor->inputMethodQuery(Qt::ImCursorPosition).toInt();
    if (caret < 0 || caret > text.size())
      return;
    const qsizetype newline = text.indexOf(u'\n', caret);
    const qsizetype end = newline < 0 ? text.size() : newline;
    if (command == EditKillLine) {
      const auto hints = Qt::InputMethodHints(editor->inputMethodQuery(Qt::ImHints).toInt());
      auto *entry = qobject_cast<QLineEdit *>(editor);
      const bool sensitive = hints.testAnyFlags(Qt::ImhHiddenText | Qt::ImhSensitiveData) ||
                             (entry && entry->echoMode() != QLineEdit::Normal);
      if (selection.isEmpty()) {
        selection = text.mid(caret, end - caret);
        if (selection.isEmpty() && !entry) {
          applyStandard(editor, QKeySequence::SelectNextChar);
          selection = editor->inputMethodQuery(Qt::ImCurrentSelection).toString();
          if (selection.isEmpty())
            return;
          applyKey(editor, QKeySequence(Qt::Key_Delete));
          if (editor->inputMethodQuery(Qt::ImCurrentSelection).toString().isEmpty() &&
              !sensitive)
            killedText = selection;
          return;
        }
        if (!selection.isEmpty() && replace(editor, QString(), 0, selection.size()) &&
            !sensitive)
          killedText = selection;
      } else {
        applyKey(editor, QKeySequence(Qt::Key_Delete));
        if (editor->inputMethodQuery(Qt::ImCurrentSelection).toString().isEmpty() &&
            !sensitive)
          killedText = selection;
      }
      return;
    }
    if (!selection.isEmpty() || !caret)
      return;
    QTextBoundaryFinder boundary(QTextBoundaryFinder::Grapheme, text);
    if (caret == end)
      boundary.setPosition(caret);
    else {
      boundary.setPosition(caret);
      boundary.toNextBoundary();
    }
    const auto right = boundary.position();
    const auto middle = boundary.toPreviousBoundary();
    const auto left = boundary.toPreviousBoundary();
    if (left >= 0 && middle > left && right > middle && !text.mid(left, right - left).contains(u'\n'))
      replace(editor, text.mid(middle, right - middle) + text.mid(left, middle - left),
              left - caret, right - left);
  }

  void execute(QWidget *editor, EditOperation operation)
  {
    const auto command = operation.command;
    if (command == EditCenter || command == EditKillLine || command == EditTranspose || command == EditYank) {
      editText(editor, command);
      return;
    }
    if (command == EditScroll) {
      scroll(editor, operation);
      return;
    }

    auto *entry = qobject_cast<QLineEdit *>(editor);
    auto *rich = qobject_cast<QTextEdit *>(editor);
    auto *plain = qobject_cast<QPlainTextEdit *>(editor);
    if (command == EditMove) {
      if ((operation.unit == EditWord || (operation.unit == EditParagraphEnd && !entry && !rich && !plain)) &&
          moveBoundary(editor, operation))
        return;
      if (entry) {
        moveEntry(entry, operation);
        return;
      }
      const auto movement = motion(operation);
      const auto selection = operation.extend ? QTextCursor::KeepAnchor : QTextCursor::MoveAnchor;
      if (movement.cursor != QTextCursor::NoMove && rich)
        rich->moveCursor(movement.cursor, selection);
      else if (movement.cursor != QTextCursor::NoMove && plain)
        plain->moveCursor(movement.cursor, selection);
      else
        applyStandard(editor, operation.extend ? movement.extend : movement.move);
      return;
    }

    if (command == EditDelete) {
      if (operation.unit == EditWord)
        applyStandard(editor, operation.direction < 0 ? QKeySequence::DeleteStartOfWord : QKeySequence::DeleteEndOfWord);
      else
        applyKey(editor, QKeySequence(operation.direction < 0 ? Qt::Key_Backspace : Qt::Key_Delete));
      return;
    }
    if (entry || rich || plain) {
      if (const char *slot = method(command)) {
        QMetaObject::invokeMethod(editor, slot, Qt::DirectConnection);
        return;
      }
      if (command == EditNewline) {
        if (entry || (rich ? rich->isReadOnly() : plain->isReadOnly()))
          return;
        auto cursor = rich ? rich->textCursor() : plain->textCursor();
        cursor.insertBlock();
        if (rich) rich->setTextCursor(cursor);
        else plain->setTextCursor(cursor);
        return;
      }
    }
    applyStandard(editor, standard(command));
  }

  static unsigned logicalKey(int key)
  {
    switch (key) {
      case Qt::Key_Left: return NXS_KEY_LEFT;
      case Qt::Key_Right: return NXS_KEY_RIGHT;
      case Qt::Key_Up: return NXS_KEY_UP_ARROW;
      case Qt::Key_Down: return NXS_KEY_DOWN_ARROW;
      case Qt::Key_Home: return NXS_KEY_HOME;
      case Qt::Key_End: return NXS_KEY_END;
      case Qt::Key_PageUp: return NXS_KEY_PAGE_UP;
      case Qt::Key_PageDown: return NXS_KEY_PAGE_DOWN;
      case Qt::Key_Insert: return NXS_KEY_INSERT;
      case Qt::Key_Backspace: return NXS_KEY_BACKSPACE;
      case Qt::Key_Delete: return NXS_KEY_DELETE;
      case Qt::Key_Escape: return NXS_KEY_ESCAPE;
      case Qt::Key_Return: case Qt::Key_Enter: return NXS_KEY_ENTER;
      case Qt::Key_Tab: case Qt::Key_Backtab: return NXS_KEY_TAB;
      default: return key >= Qt::Key_F1 && key <= Qt::Key_F24 ? NXS_KEY_F1 + key - Qt::Key_F1 : NXS_KEY_TEXT;
    }
  }

  void resolve(QKeyEvent *key)
  {
    pending = {};
    pendingKey = 0;
    const auto modifiers = key->modifiers();
    const auto logical = logicalKey(key->key());
    if (modifiers.testFlag(Qt::GroupSwitchModifier) ||
        (logical == NXS_KEY_TEXT && (key->key() < Qt::Key_Space || key->key() > 0x10ffff)))
      return;

    QByteArray text = key->text().toUtf8();
    QByteArray plain;
    NXSKeyEvent event{sizeof(event), NXS_KEY_DOWN, 0, logical, unsigned(key->isAutoRepeat()),
                      text.constData(), nullptr};
    if (modifiers.testFlag(Qt::AltModifier)) event.modifiers |= NXS_ALT;
    if (modifiers.testFlag(Qt::ControlModifier)) event.modifiers |= NXS_CONTROL;
    if (modifiers.testFlag(Qt::ShiftModifier)) event.modifiers |= NXS_SHIFT;
    if (modifiers.testFlag(Qt::MetaModifier)) event.modifiers |= NXS_SUPER;
    if (!nextspace_edit_key(logical, event.modifiers))
      return;
    if (logical == NXS_KEY_TEXT) {
      const char32_t character = key->key();
      plain = QString::fromUcs4(&character, 1).toLower().toUtf8();
      event.unmodified_text = plain.constData();
    }
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
    if (applying || (event->type() != QEvent::ShortcutOverride && event->type() != QEvent::KeyPress))
      return false;
    const QByteArray shortcuts = qgetenv("NEXTSPACE_SHORTCUTS");
    if (!shortcuts.isEmpty() && shortcuts != "native")
      return false;
    if (widget != focus || widget->property("nextspaceOriginalEditing").toBool())
      return false;
    // Qt gives an editable combo box keyboard focus on behalf of its line edit.
    QWidget *editor = widget;
    if (auto *combo = qobject_cast<QComboBox *>(widget))
      editor = combo->lineEdit();
    if (!editor || editor->layoutDirection() == Qt::RightToLeft ||
        editor->property("nextspaceOriginalEditing").toBool() ||
        (!qobject_cast<QLineEdit *>(editor) && !qobject_cast<QPlainTextEdit *>(editor) &&
         !qobject_cast<QTextEdit *>(editor) &&
         (!editor->inputMethodQuery(Qt::ImCursorPosition).isValid() ||
          !editor->inputMethodQuery(Qt::ImSurroundingText).isValid())))
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
    QScopedValueRollback<bool> guard(applying, true);
    QPointer<QWidget> target(editor);
    for (unsigned index = 0; index < commands.count && target; ++index)
      execute(target, commands.actions[index]);
    return true;
  }
};
