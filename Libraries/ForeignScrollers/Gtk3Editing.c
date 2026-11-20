/* Resolve native bindings against the focused GTK editor. GPL-2.0-or-later. */
#include "EditCommands.h"
#include <gtk/gtk.h>

static NXSEditBindings *bindings;
static GtkWidget *last_focus;

int nextspace_gtk3_context_key(const NXSKeyEvent *);

static unsigned event_modifiers(guint state)
{
  return (state & GDK_SHIFT_MASK ? NXS_SHIFT : 0) |
      (state & GDK_MOD1_MASK ? NXS_ALT : 0) |
      (state & GDK_CONTROL_MASK ? NXS_CONTROL : 0) |
      (state & GDK_SUPER_MASK ? NXS_SUPER : 0);
}

static unsigned menu_key(guint key)
{
  switch (key) {
    case GDK_KEY_Escape: return NXS_KEY_ESCAPE;
    case GDK_KEY_Return:
    case GDK_KEY_KP_Enter: return NXS_KEY_ENTER;
    case GDK_KEY_Left: return NXS_KEY_LEFT;
    case GDK_KEY_Right: return NXS_KEY_RIGHT;
    case GDK_KEY_Up: return NXS_KEY_UP_ARROW;
    case GDK_KEY_Down: return NXS_KEY_DOWN_ARROW;
    case GDK_KEY_Home: return NXS_KEY_HOME;
    case GDK_KEY_End: return NXS_KEY_END;
    case GDK_KEY_Tab:
    case GDK_KEY_ISO_Left_Tab: return NXS_KEY_TAB;
    case GDK_KEY_BackSpace: return NXS_KEY_BACKSPACE;
    case GDK_KEY_Delete: return NXS_KEY_DELETE;
    case GDK_KEY_Page_Up: return NXS_KEY_PAGE_UP;
    case GDK_KEY_Page_Down: return NXS_KEY_PAGE_DOWN;
    default: return NXS_KEY_TEXT;
  }
}

static const char *edit_signal(EditCommand action)
{
  switch (action) {
    case EditCopy: return "copy-clipboard";
    case EditCut: return "cut-clipboard";
    case EditPaste: return "paste-clipboard";
    case EditUndo: return "undo";
    case EditRedo: return "redo";
    default: return NULL;
  }
}

static void focus_changed(GtkWindow *window, GtkWidget *focus, gpointer unused)
{
  if (last_focus)
    g_object_remove_weak_pointer(G_OBJECT(last_focus), (gpointer *)&last_focus);
  last_focus = focus;
  if (last_focus)
    g_object_add_weak_pointer(G_OBJECT(last_focus), (gpointer *)&last_focus);
  nxs_edit_bindings_reset(bindings);
}

static gboolean key_press(GtkWidget *widget, GdkEventKey *event, gpointer unused)
{
  char text[7] = {0}, unmodified[7] = {0};
  g_unichar_to_utf8(gdk_keyval_to_unicode(event->keyval), text);
  unsigned modifiers = event_modifiers(event->state);
  NXSKeyEvent key = {sizeof(key), NXS_KEY_DOWN, modifiers, menu_key(event->keyval), 0, text, text};
  if (!event->is_modifier && nextspace_gtk3_context_key(&key))
    return TRUE;
  if (g_strcmp0(g_getenv("NEXTSPACE_NATIVE_EDITING"), "off") == 0)
    return FALSE;

  GtkWidget *editor = gtk_window_get_focus(GTK_WINDOW(widget));
  if (editor != last_focus)
    focus_changed(GTK_WINDOW(widget), editor, NULL);
  if (!editor || (!GTK_IS_ENTRY(editor) && !GTK_IS_TEXT_VIEW(editor)) ||
      gtk_widget_get_direction(editor) == GTK_TEXT_DIR_RTL ||
      g_object_get_data(G_OBJECT(editor), "nextspace-original-editing") ||
      !(event->state & (GDK_MOD1_MASK | GDK_CONTROL_MASK | GDK_SUPER_MASK)) ||
      (event->state & GDK_MOD5_MASK) || event->is_modifier)
    return FALSE;

  guint keyval;
  GdkKeymap *keymap = gdk_keymap_get_for_display(gtk_widget_get_display(widget));
  if (!gdk_keymap_translate_keyboard_state(keymap, event->hardware_keycode, 0,
          event->group, &keyval, NULL, NULL, NULL))
    return FALSE;
  gunichar plain = gdk_keyval_to_unicode(keyval);
  if (plain < 32)
    return FALSE;
  g_unichar_to_utf8(plain, unmodified);
  key.unmodified_text = unmodified;
  if (!bindings)
    bindings = nxs_edit_bindings_create();
  EditCommands commands = {0};
  int result = nxs_edit_bindings_resolve(bindings, &key, nextspace_collect_edit_command, &commands);
  if (result == NXS_EDIT_SEQUENCE)
    return TRUE;
  if (result != NXS_EDIT_COMMANDS || commands.unsupported)
    return FALSE;
  for (unsigned index = 0; index < commands.count; index++) {
    const char *signal = edit_signal(commands.actions[index]);
    if (signal) {
      GSignalQuery query = {0};
      g_signal_query(g_signal_lookup(signal, G_OBJECT_TYPE(editor)), &query);
      if (!query.signal_id || query.n_params || query.return_type != G_TYPE_NONE)
        return FALSE;
    }
  }
  g_object_ref(editor);
  for (unsigned index = 0; index < commands.count; index++) {
    EditCommand action = commands.actions[index];
    const char *signal = edit_signal(action);
    if (signal) {
      g_signal_emit_by_name(editor, signal);
    } else if (action == EditSelectAll) {
      if (GTK_IS_ENTRY(editor))
        gtk_editable_select_region(GTK_EDITABLE(editor), 0, -1);
      else
        g_signal_emit_by_name(editor, "select-all", TRUE);
    } else {
      int direction = (action == EditBackward || action == EditBackwardSelecting) ? -1 : 1;
      gboolean extend = action == EditBackwardSelecting || action == EditForwardSelecting;
      g_signal_emit_by_name(editor, "move-cursor", GTK_MOVEMENT_LOGICAL_POSITIONS, direction, extend);
    }
  }
  g_object_unref(editor);
  return TRUE;
}

void nextspace_gtk3_attach_editing(GtkWidget *widget)
{
  if (!GTK_IS_WINDOW(widget) || g_object_get_data(G_OBJECT(widget), "nextspace-editing-attached"))
    return;
  g_object_set_data(G_OBJECT(widget), "nextspace-editing-attached", GINT_TO_POINTER(1));
  g_signal_connect(widget, "key-press-event", G_CALLBACK(key_press), NULL);
  g_signal_connect(widget, "set-focus", G_CALLBACK(focus_changed), NULL);
}
