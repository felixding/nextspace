/* Project GNUstep editing selectors onto toolkit editor operations.
 * GNUstep owns key matching and command sequences. GPL-2.0-or-later. */
#ifndef NEXTSPACE_TOOLKIT_EDIT_COMMANDS_H
#define NEXTSPACE_TOOLKIT_EDIT_COMMANDS_H

#include "../NativeUI/NativeUI.h"
#include <string.h>

typedef enum {
  EditNone, EditSelectAll, EditCopy, EditCut, EditPaste, EditUndo, EditRedo,
  EditMove, EditScroll, EditDelete, EditKillLine, EditNewline, EditCenter,
  EditTranspose, EditYank
} EditCommand;

typedef enum {
  EditCharacter, EditVisualCharacter, EditWord, EditLine, EditLineEnd,
  EditParagraphEnd, EditDocumentEnd, EditPage
} EditUnit;

typedef struct {
  EditCommand command;
  EditUnit unit;
  int direction;
  int extend;
} EditOperation;

static inline EditOperation nextspace_edit_operation(const char *selector)
{
  static const struct {
    const char *selector;
    EditCommand action;
  } commands[] = {
    {"selectAll:", EditSelectAll}, {"copy:", EditCopy}, {"cut:", EditCut},
    {"paste:", EditPaste}, {"undo:", EditUndo}, {"redo:", EditRedo},
    {"deleteToEndOfLine:", EditKillLine},
    {"insertNewlineIgnoringFieldEditor:", EditNewline},
    {"centerSelectionInVisibleArea:", EditCenter},
    {"transpose:", EditTranspose}, {"yank:", EditYank}
  };
  static const struct {
    const char *selector;
    EditCommand action;
    EditUnit unit;
    int direction;
  } motions[] = {
    {"moveBackward", EditMove, EditCharacter, -1},
    {"moveForward", EditMove, EditCharacter, 1},
    {"moveLeft", EditMove, EditVisualCharacter, -1},
    {"moveRight", EditMove, EditVisualCharacter, 1},
    {"moveWordBackward", EditMove, EditWord, -1},
    {"moveWordForward", EditMove, EditWord, 1},
    {"moveUp", EditMove, EditLine, -1},
    {"moveDown", EditMove, EditLine, 1},
    {"moveToBeginningOfLine", EditMove, EditLineEnd, -1},
    {"moveToEndOfLine", EditMove, EditLineEnd, 1},
    {"moveToBeginningOfParagraph", EditMove, EditParagraphEnd, -1},
    {"moveToEndOfParagraph", EditMove, EditParagraphEnd, 1},
    {"moveToBeginningOfDocument", EditMove, EditDocumentEnd, -1},
    {"moveToEndOfDocument", EditMove, EditDocumentEnd, 1},
    {"pageUp", EditMove, EditPage, -1},
    {"pageDown", EditMove, EditPage, 1},
    {"scrollPageUp", EditScroll, EditPage, -1},
    {"scrollPageDown", EditScroll, EditPage, 1},
    {"scrollLineUp", EditScroll, EditLine, -1},
    {"scrollLineDown", EditScroll, EditLine, 1},
    {"scrollToBeginningOfDocument", EditScroll, EditDocumentEnd, -1},
    {"scrollToEndOfDocument", EditScroll, EditDocumentEnd, 1},
    {"deleteBackward", EditDelete, EditCharacter, -1},
    {"deleteForward", EditDelete, EditCharacter, 1},
    {"deleteWordBackward", EditDelete, EditWord, -1},
    {"deleteWordForward", EditDelete, EditWord, 1}
  };
  for (unsigned i = 0; i < sizeof(commands) / sizeof(*commands); i++)
    if (!strcmp(selector, commands[i].selector))
      return (EditOperation){commands[i].action, EditCharacter, 0, 0};

  for (unsigned i = 0; i < sizeof(motions) / sizeof(*motions); i++) {
    size_t length = strlen(motions[i].selector);
    if (strncmp(selector, motions[i].selector, length))
      continue;
    const char *suffix = selector + length;
    int extend = motions[i].action == EditMove && !strcmp(suffix, "AndModifySelection:");
    if (extend || !strcmp(suffix, ":"))
      return (EditOperation){motions[i].action, motions[i].unit, motions[i].direction, extend};
  }
  return (EditOperation){EditNone, EditCharacter, 0, 0};
}

typedef struct {
  EditOperation actions[8];
  unsigned count;
  int unsupported;
} EditCommands;

static inline void nextspace_collect_edit_command(void *context, const char *selector)
{
  EditCommands *commands = (EditCommands *)context;
  EditOperation operation = nextspace_edit_operation(selector);
  if (operation.command == EditNone || commands->count == sizeof(commands->actions) / sizeof(*commands->actions))
    commands->unsupported = 1;
  else
    commands->actions[commands->count++] = operation;
}

static inline int nextspace_edit_key(unsigned key, unsigned modifiers)
{
  if (key == NXS_KEY_TEXT)
    return (modifiers & (NXS_ALT | NXS_CONTROL | NXS_SUPER)) != 0;

  /* NSInputManager has no Command modifier in its key tables. An application's
     Command function keys must not match a plain movement by dropping Command. */
  unsigned command = nxs_physical_modifier(NXS_MENU_COMMAND);
  unsigned control = nxs_physical_modifier(NXS_MENU_CONTROL);
  unsigned alternate = nxs_physical_modifier(NXS_MENU_ALTERNATE);
  if (modifiers & command & ~control)
    return 0;
  return (key >= NXS_KEY_LEFT && key <= NXS_KEY_PAGE_DOWN) ||
         (modifiers & (control | alternate)) != 0;
}

#endif
