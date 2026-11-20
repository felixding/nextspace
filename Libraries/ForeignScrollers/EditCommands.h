/* Project AppKit selectors onto the original toolkit editor actions.
 * GNUstep decides which keys produce these selectors. GPL-2.0-or-later. */
#ifndef NEXTSPACE_TOOLKIT_EDIT_COMMANDS_H
#define NEXTSPACE_TOOLKIT_EDIT_COMMANDS_H

#include "../NativeUI/NativeUI.h"
#include <string.h>

typedef enum {
  EditNone, EditSelectAll, EditCopy, EditCut, EditPaste, EditUndo, EditRedo,
  EditBackward, EditForward, EditBackwardSelecting, EditForwardSelecting
} EditCommand;

static inline EditCommand nextspace_edit_command(const char *selector)
{
  static const struct {
    const char *selector;
    EditCommand action;
  } commands[] = {
    {"selectAll:", EditSelectAll}, {"copy:", EditCopy}, {"cut:", EditCut},
    {"paste:", EditPaste}, {"undo:", EditUndo}, {"redo:", EditRedo},
    {"moveBackward:", EditBackward}, {"moveForward:", EditForward},
    {"moveLeft:", EditBackward}, {"moveRight:", EditForward},
    {"moveBackwardAndModifySelection:", EditBackwardSelecting},
    {"moveForwardAndModifySelection:", EditForwardSelecting},
    {"moveLeftAndModifySelection:", EditBackwardSelecting},
    {"moveRightAndModifySelection:", EditForwardSelecting}
  };
  for (unsigned index = 0; index < sizeof(commands) / sizeof(*commands); index++)
    if (!strcmp(selector, commands[index].selector))
      return commands[index].action;
  return EditNone;
}

typedef struct {
  EditCommand actions[8];
  unsigned count;
  int unsupported;
} EditCommands;

static inline void nextspace_collect_edit_command(void *context, const char *selector)
{
  EditCommands *commands = (EditCommands *)context;
  EditCommand action = nextspace_edit_command(selector);
  if (action == EditNone || commands->count == sizeof(commands->actions) / sizeof(*commands->actions))
    commands->unsupported = 1;
  else
    commands->actions[commands->count++] = action;
}

#endif
