/* TextEditCommand ABI from Chromium a21ce95c24ce3964416f09ae1862f53f319eb4d0,
 * ui/base/ime/text_edit_commands.inc. Names are exposed as selectors. */
static const char *const chromium_edit_selectors[]={
  "deleteBackward:", "deleteForward:", "deleteToBeginningOfLine:",
  "deleteToBeginningOfParagraph:", "deleteToEndOfLine:", "deleteToEndOfParagraph:",
  "deleteWordBackward:", "deleteWordForward:", "moveBackward:",
  "moveBackwardAndModifySelection:", "moveDown:", "moveDownAndModifySelection:",
  "moveForward:", "moveForwardAndModifySelection:", "moveLeft:",
  "moveLeftAndModifySelection:", "movePageDown:", "movePageDownAndModifySelection:",
  "movePageUp:", "movePageUpAndModifySelection:", "moveRight:",
  "moveRightAndModifySelection:", "moveToBeginningOfDocument:", "moveToBeginningOfDocumentAndModifySelection:",
  "moveToBeginningOfLine:", "moveToBeginningOfLineAndModifySelection:", "moveToBeginningOfParagraph:",
  "moveToBeginningOfParagraphAndModifySelection:", "moveToEndOfDocument:", "moveToEndOfDocumentAndModifySelection:",
  "moveToEndOfLine:", "moveToEndOfLineAndModifySelection:", "moveToEndOfParagraph:",
  "moveToEndOfParagraphAndModifySelection:", "moveParagraphBackwardAndModifySelection:", "moveParagraphForwardAndModifySelection:",
  "moveUp:", "moveUpAndModifySelection:", "moveWordBackward:",
  "moveWordBackwardAndModifySelection:", "moveWordForward:", "moveWordForwardAndModifySelection:",
  "moveWordLeft:", "moveWordLeftAndModifySelection:", "moveWordRight:",
  "moveWordRightAndModifySelection:", "scrollPageDown:", "scrollPageUp:",
  "scrollToBeginningOfDocument:", "scrollToEndOfDocument:", "undo:",
  "redo:", "cut:", "copy:",
  "paste:", "selectAll:", "selectWord:",
  "transpose:", "yank:", "insertText:",
  "setMark:", "unselect:", "invalidCommand:",
};
enum { CHROMIUM_EDIT_INVALID=62 };
_Static_assert(sizeof(chromium_edit_selectors)/sizeof(*chromium_edit_selectors)==CHROMIUM_EDIT_INVALID+1,
  "Pinned Chromium edit command enum");
