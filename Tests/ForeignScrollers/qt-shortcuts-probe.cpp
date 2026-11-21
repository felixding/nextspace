#include "QtShortcuts.h"

#include <QApplication>
#include <cassert>
#include <cstdio>

extern "C" unsigned nxs_physical_modifier(unsigned native)
{
  return native == NXS_MENU_COMMAND ? NXS_SUPER : 0;
}

int main(int argc, char **argv)
{
  QApplication app(argc, argv);
  NativeShortcuts bridge;
  QWidget window;
  QWidget editor(&window);
  editor.setFocusPolicy(Qt::StrongFocus);

  auto add = [&](QAction &action, QKeyCombination original, QKeyCombination alias) {
    action.setShortcut(QKeySequence(original));
    window.addAction(&action);
    QActionEvent event(QEvent::ActionAdded, &action);
    bridge.filter(&window, &event);
    app.processEvents();
    assert(action.shortcut() == QKeySequence(alias));
    assert(action.shortcuts().contains(QKeySequence(original)));
  };
  QAction print(&window), preferences(&window), shifted(&window);
  add(print, Qt::ControlModifier | Qt::Key_P, Qt::MetaModifier | Qt::Key_P);
  add(preferences, Qt::ControlModifier | Qt::Key_Comma, Qt::MetaModifier | Qt::Key_Comma);
  add(shifted, (Qt::ControlModifier | Qt::ShiftModifier) | Qt::Key_F8,
      (Qt::MetaModifier | Qt::ShiftModifier) | Qt::Key_F8);

  window.show();
  editor.setFocus();
  app.processEvents();
  assert(editor.hasFocus());
  QKeyEvent commandP(QEvent::KeyPress, Qt::Key_P, Qt::MetaModifier);
  QKeyEvent controlP(QEvent::KeyPress, Qt::Key_P, Qt::ControlModifier);
  int prints = 0;
  QObject::connect(&print, &QAction::triggered, &window, [&] { ++prints; });
  assert(bridge.filter(&editor, &commandP) && prints == 1);
  print.setEnabled(false);
  assert(bridge.filter(&editor, &commandP) && prints == 1);
  assert(!bridge.filter(&editor, &controlP));

  const QKeySequence custom(Qt::MetaModifier | Qt::Key_P);
  const QKeySequence rebound(Qt::ControlModifier | Qt::Key_R);
  const QKeySequence commandR(Qt::MetaModifier | Qt::Key_R);
  print.setShortcuts({custom, rebound});
  QActionEvent changed(QEvent::ActionChanged, &print);
  bridge.filter(&window, &changed);
  app.processEvents();
  assert(print.shortcuts() == QList<QKeySequence>({commandR, custom, rebound}));

  print.setProperty("nextspaceOriginalShortcut", true);
  bridge.filter(&window, &changed);
  app.processEvents();
  assert(print.shortcuts() == QList<QKeySequence>({custom, rebound}));
  std::puts("Qt aliases follow changed actions and preserve original shortcuts");
}
