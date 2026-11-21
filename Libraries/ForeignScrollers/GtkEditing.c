/* Resolve native bindings against the focused GTK editor. GPL-2.0-or-later. */
#include "EditCommands.h"
#include <gtk/gtk.h>

static NXSEditBindings *bindings;
static GtkWidget *last_focus;
static char *killed_text;

#if GTK_MAJOR_VERSION == 3
#define GDK_ALT_MASK GDK_MOD1_MASK
int nextspace_gtk3_context_key(const NXSKeyEvent *);
#endif

static unsigned event_modifiers(guint state)
{
  return (state & GDK_SHIFT_MASK ? NXS_SHIFT : 0) |
      (state & GDK_ALT_MASK ? NXS_ALT : 0) |
      (state & GDK_CONTROL_MASK ? NXS_CONTROL : 0) |
      (state & GDK_SUPER_MASK ? NXS_SUPER : 0);
}

static unsigned logical_key(guint key)
{
  switch (key) {
    case GDK_KEY_Escape: return NXS_KEY_ESCAPE;
    case GDK_KEY_Return:
    case GDK_KEY_KP_Enter: return NXS_KEY_ENTER;
    case GDK_KEY_KP_Left:
    case GDK_KEY_Left: return NXS_KEY_LEFT;
    case GDK_KEY_KP_Right:
    case GDK_KEY_Right: return NXS_KEY_RIGHT;
    case GDK_KEY_KP_Up:
    case GDK_KEY_Up: return NXS_KEY_UP_ARROW;
    case GDK_KEY_KP_Down:
    case GDK_KEY_Down: return NXS_KEY_DOWN_ARROW;
    case GDK_KEY_KP_Home:
    case GDK_KEY_Home: return NXS_KEY_HOME;
    case GDK_KEY_KP_End:
    case GDK_KEY_End: return NXS_KEY_END;
    case GDK_KEY_Tab:
    case GDK_KEY_ISO_Left_Tab: return NXS_KEY_TAB;
    case GDK_KEY_BackSpace: return NXS_KEY_BACKSPACE;
    case GDK_KEY_KP_Delete:
    case GDK_KEY_Delete: return NXS_KEY_DELETE;
    case GDK_KEY_KP_Page_Up:
    case GDK_KEY_Page_Up: return NXS_KEY_PAGE_UP;
    case GDK_KEY_KP_Page_Down:
    case GDK_KEY_Page_Down: return NXS_KEY_PAGE_DOWN;
    case GDK_KEY_Insert:
    case GDK_KEY_KP_Insert: return NXS_KEY_INSERT;
    default: return key >= GDK_KEY_F1 && key <= GDK_KEY_F24 ? NXS_KEY_F1 + key - GDK_KEY_F1 : NXS_KEY_TEXT;
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

static gboolean visible_entry(GtkEditable *editor)
{
#if GTK_MAJOR_VERSION == 3
  return gtk_entry_get_visibility(GTK_ENTRY(editor));
#else
  return gtk_text_get_visibility(GTK_TEXT(editor));
#endif
}

static const char *entry_text(GtkEditable *editor)
{
#if GTK_MAJOR_VERSION == 3
  return gtk_entry_get_text(GTK_ENTRY(editor));
#else
  return gtk_editable_get_text(editor);
#endif
}

static void replace_entry_range(GtkEditable *editor, EditCommand action)
{
  if (!gtk_editable_get_editable(editor))
    return;
  int start, end;
  gboolean selected = gtk_editable_get_selection_bounds(editor, &start, &end);
  if (!selected)
    start = end = gtk_editable_get_position(editor);
  const char *text = entry_text(editor);
  int length = g_utf8_strlen(text, -1);
  if (action == EditKillLine) {
    if (!selected)
      end = length;
    char *removed = visible_entry(editor) ? gtk_editable_get_chars(editor, start, end) : NULL;
    gtk_editable_delete_text(editor, start, end);
    if (removed && g_utf8_strlen(entry_text(editor), -1) == length - (end - start) && start != end) {
      g_free(killed_text);
      killed_text = removed;
    } else
      g_free(removed);
    return;
  }
  if (action == EditYank) {
    if (killed_text)
      g_signal_emit_by_name(editor, "insert-at-cursor", killed_text);
    return;
  }
  if (selected || start == 0 || length < 2)
    return;
  start -= start == length ? 2 : 1;
  const char *first = g_utf8_offset_to_pointer(text, start);
  const char *second = g_utf8_next_char(first);
  char swapped[13] = {0};
  int bytes = g_unichar_to_utf8(g_utf8_get_char(second), swapped);
  g_unichar_to_utf8(g_utf8_get_char(first), swapped + bytes);
  gtk_editable_delete_text(editor, start, start + 2);
  gtk_editable_insert_text(editor, swapped, -1, &start);
  gtk_editable_set_position(editor, start);
}

static void replace_view_range(GtkTextView *view, EditCommand action)
{
  GtkTextBuffer *buffer = gtk_text_view_get_buffer(view);
  gboolean editable = gtk_text_view_get_editable(view);
  GtkTextIter start, end;
  gboolean selected = gtk_text_buffer_get_selection_bounds(buffer, &start, &end);
  if (action == EditKillLine) {
    if (!selected) {
      if (gtk_text_iter_ends_line(&end))
        gtk_text_iter_forward_char(&end);
      else
        gtk_text_iter_forward_to_line_end(&end);
    }
    if (gtk_text_iter_equal(&start, &end))
      return;
    char *text = gtk_text_buffer_get_text(buffer, &start, &end, FALSE);
    if (gtk_text_buffer_delete_interactive(buffer, &start, &end, editable)) {
      g_free(killed_text);
      killed_text = text;
    } else
      g_free(text);
    return;
  }
  if (action == EditYank) {
    if (killed_text)
      g_signal_emit_by_name(view, "insert-at-cursor", killed_text);
    return;
  }
  if (selected || gtk_text_iter_starts_line(&end) || !gtk_text_iter_backward_cursor_position(&start))
    return;
  if (gtk_text_iter_ends_line(&end) &&
      (gtk_text_iter_starts_line(&start) || !gtk_text_iter_backward_cursor_position(&start)))
    return;
  GtkTextIter middle = start;
  gtk_text_iter_forward_cursor_position(&middle);
  end = middle;
  gtk_text_iter_forward_cursor_position(&end);
  if (!gtk_text_iter_editable(&start, editable) || !gtk_text_iter_editable(&middle, editable))
    return;
  char *left = gtk_text_buffer_get_text(buffer, &start, &middle, TRUE);
  char *right = gtk_text_buffer_get_text(buffer, &middle, &end, TRUE);
  char *swapped = g_strconcat(right, left, NULL);
  gtk_text_buffer_begin_user_action(buffer);
  gtk_text_buffer_delete(buffer, &start, &end);
  gtk_text_buffer_insert(buffer, &start, swapped, -1);
  gtk_text_buffer_place_cursor(buffer, &start);
  gtk_text_buffer_end_user_action(buffer);
  g_free(swapped);
  g_free(right);
  g_free(left);
}

static gboolean is_entry(GtkWidget *editor)
{
#if GTK_MAJOR_VERSION == 3
  return GTK_IS_ENTRY(editor);
#else
  return GTK_IS_TEXT(editor);
#endif
}

static void apply_edit(GtkWidget *editor, EditOperation operation)
{
  const char *signal = edit_signal(operation.command);
  if (signal) {
    g_signal_emit_by_name(editor, signal);
    return;
  }
  switch (operation.command) {
    case EditMove: {
      static const GtkMovementStep steps[] = {
        [EditCharacter] = GTK_MOVEMENT_LOGICAL_POSITIONS,
        [EditVisualCharacter] = GTK_MOVEMENT_VISUAL_POSITIONS,
        [EditWord] = GTK_MOVEMENT_WORDS,
        [EditLine] = GTK_MOVEMENT_DISPLAY_LINES,
        [EditLineEnd] = GTK_MOVEMENT_DISPLAY_LINE_ENDS,
        [EditParagraphEnd] = GTK_MOVEMENT_PARAGRAPH_ENDS,
        [EditDocumentEnd] = GTK_MOVEMENT_BUFFER_ENDS,
        [EditPage] = GTK_MOVEMENT_PAGES
      };
      g_signal_emit_by_name(editor, "move-cursor", steps[operation.unit],
                            operation.direction, operation.extend);
      return;
    }
    case EditScroll:
      if (GTK_IS_TEXT_VIEW(editor)) {
        GtkScrollStep step = operation.unit == EditPage ? GTK_SCROLL_PAGES :
                            operation.unit == EditLine ? GTK_SCROLL_STEPS : GTK_SCROLL_ENDS;
        g_signal_emit_by_name(editor, "move-viewport", step, operation.direction);
      }
      return;
    case EditSelectAll:
      if (is_entry(editor))
        gtk_editable_select_region(GTK_EDITABLE(editor), 0, -1);
      else
        g_signal_emit_by_name(editor, "select-all", TRUE);
      return;
    case EditDelete:
      if (operation.unit == EditCharacter && operation.direction < 0)
        g_signal_emit_by_name(editor, "backspace");
      else
        g_signal_emit_by_name(editor, "delete-from-cursor",
                              operation.unit == EditWord ? GTK_DELETE_WORD_ENDS : GTK_DELETE_CHARS,
                              operation.direction);
      return;
    case EditKillLine:
    case EditTranspose:
    case EditYank:
      if (is_entry(editor))
        replace_entry_range(GTK_EDITABLE(editor), operation.command);
      else
        replace_view_range(GTK_TEXT_VIEW(editor), operation.command);
      return;
    case EditNewline:
      if (GTK_IS_TEXT_VIEW(editor))
        g_signal_emit_by_name(editor, "insert-at-cursor", "\n");
      return;
    case EditCenter:
      if (GTK_IS_TEXT_VIEW(editor)) {
        GtkTextView *view = GTK_TEXT_VIEW(editor);
        gtk_text_view_scroll_to_mark(view, gtk_text_buffer_get_insert(gtk_text_view_get_buffer(view)),
                                    0, TRUE, 0, .5);
      }
      return;
    default: return;
  }
}

static void reset_focus(GtkWidget *editor)
{
  if (last_focus)
    g_object_remove_weak_pointer(G_OBJECT(last_focus), (gpointer *)&last_focus);
  last_focus = editor;
  if (last_focus)
    g_object_add_weak_pointer(G_OBJECT(last_focus), (gpointer *)&last_focus);
  nxs_edit_bindings_reset(bindings);
}

static GtkWidget *focused_editor(GtkWindow *window)
{
  GtkWidget *editor = gtk_window_get_focus(window);
  if (!editor || g_object_get_data(G_OBJECT(editor), "nextspace-original-editing"))
    return NULL;
#if GTK_MAJOR_VERSION == 4
  /* GtkEntry and editable composites delegate actions to GtkText. */
  if (!GTK_IS_TEXT(editor) && GTK_IS_EDITABLE(editor)) {
    GtkEditable *delegate = gtk_editable_get_delegate(GTK_EDITABLE(editor));
    if (GTK_IS_TEXT(delegate))
      editor = GTK_WIDGET(delegate);
  }
#endif
  if (gtk_widget_get_direction(editor) == GTK_TEXT_DIR_RTL ||
      (!is_entry(editor) && !GTK_IS_TEXT_VIEW(editor)))
    return NULL;
#if GTK_MAJOR_VERSION == 4
  GtkWidget *parent = gtk_widget_get_parent(editor);
  if (parent && g_object_get_data(G_OBJECT(parent), "nextspace-original-editing"))
    return NULL;
#endif
  return editor;
}

static gboolean resolve_key(GtkWindow *window, NXSKeyEvent *key)
{
  const char *shortcuts = g_getenv("NEXTSPACE_SHORTCUTS");
  if (g_strcmp0(g_getenv("NEXTSPACE_NATIVE_EDITING"), "off") == 0 ||
      (shortcuts && !g_str_equal(shortcuts, "native")))
    return FALSE;

  GtkWidget *editor = focused_editor(window);
  if (editor != last_focus)
    reset_focus(editor);
  if (!editor || !nextspace_edit_key(key->key, key->modifiers))
    return FALSE;
  if (!bindings)
    bindings = nxs_edit_bindings_create();
  EditCommands commands = {0};
  int result = nxs_edit_bindings_resolve(bindings, key, nextspace_collect_edit_command, &commands);
  if (result == NXS_EDIT_SEQUENCE)
    return TRUE;
  if (result != NXS_EDIT_COMMANDS || commands.unsupported)
    return FALSE;
  for (unsigned index = 0; index < commands.count; index++) {
    const char *signal = edit_signal(commands.actions[index].command);
    if (signal) {
      GSignalQuery query = {0};
      g_signal_query(g_signal_lookup(signal, G_OBJECT_TYPE(editor)), &query);
      if (!query.signal_id || query.n_params || query.return_type != G_TYPE_NONE)
        return FALSE;
    }
  }
  g_object_ref(editor);
  for (unsigned index = 0; index < commands.count && focused_editor(window) == editor; index++)
    apply_edit(editor, commands.actions[index]);
  g_object_unref(editor);
  return TRUE;
}

#if GTK_MAJOR_VERSION == 3
static void focus_changed(GtkWindow *window, GtkWidget *focus, gpointer unused)
{
  reset_focus(NULL);
}

static gboolean key_press(GtkWidget *widget, GdkEventKey *event, gpointer unused)
{
  if (event->is_modifier)
    return FALSE;
  char text[7] = {0}, unmodified[7] = {0};
  g_unichar_to_utf8(gdk_keyval_to_unicode(event->keyval), text);
  NXSKeyEvent key = {sizeof(key), NXS_KEY_DOWN, event_modifiers(event->state),
                     logical_key(event->keyval), 0, text, text};
  if (nextspace_gtk3_context_key(&key))
    return TRUE;
  if (event->state & GDK_MOD5_MASK)
    return FALSE;
  if (key.key == NXS_KEY_TEXT) {
    if (!key.modifiers)
      return FALSE;
    guint symbol;
    GdkKeymap *map = gdk_keymap_get_for_display(gtk_widget_get_display(widget));
    if (!gdk_keymap_translate_keyboard_state(map, event->hardware_keycode,
          event->state & (GDK_SHIFT_MASK | GDK_LOCK_MASK), event->group, &symbol, NULL, NULL, NULL))
      return FALSE;
    gunichar plain = gdk_keyval_to_unicode(symbol);
    if (plain < 32)
      return FALSE;
    g_unichar_to_utf8(plain, unmodified);
    key.unmodified_text = unmodified;
  }
  return resolve_key(GTK_WINDOW(widget), &key);
}

static gboolean activate_application_shortcut(GtkWindow *window, GdkEventKey *event, gpointer unused)
{
  const char *policy = g_getenv("NEXTSPACE_SHORTCUTS");
  if (event->is_modifier || (event->state & GDK_MOD5_MASK) ||
      (policy && !g_str_equal(policy, "native")))
    return FALSE;
  unsigned command = nxs_physical_modifier(NXS_MENU_COMMAND);
  unsigned modifiers = event_modifiers(event->state) & ~NXS_SHIFT;
  if (!command || command == NXS_CONTROL || modifiers != command)
    return FALSE;

  // GTK checks Alt mnemonics before accelerators. Dispatch the application's
  // registered primary shortcut through GTK's normal accelerator lookup.
  GdkEventKey primary = *event;
  primary.state &= ~(GDK_MOD1_MASK | GDK_MOD4_MASK | GDK_SUPER_MASK | GDK_META_MASK);
  primary.state |= GDK_CONTROL_MASK;
  return gtk_window_activate_key(window, &primary);
}

void nextspace_gtk_attach_editing(GtkWidget *widget)
{
  if (!GTK_IS_WINDOW(widget) || g_object_get_data(G_OBJECT(widget), "nextspace-editing-attached"))
    return;
  g_object_set_data(G_OBJECT(widget), "nextspace-editing-attached", GINT_TO_POINTER(1));
  g_signal_connect(widget, "key-press-event", G_CALLBACK(key_press), NULL);
  g_signal_connect(widget, "key-press-event", G_CALLBACK(activate_application_shortcut), NULL);
  g_signal_connect(widget, "set-focus", G_CALLBACK(focus_changed), NULL);
}
#else
static void focus_changed(GtkWindow *window, GParamSpec *param, gpointer unused)
{
  reset_focus(NULL);
}

static gboolean key_press(GtkEventControllerKey *controller, guint symbol, guint keycode,
                          GdkModifierType state, gpointer unused)
{
  GtkWidget *window = gtk_event_controller_get_widget(GTK_EVENT_CONTROLLER(controller));
  GdkEvent *event = gtk_event_controller_get_current_event(GTK_EVENT_CONTROLLER(controller));
  if (!event || gdk_key_event_is_modifier(event))
    return FALSE;
  char text[7] = {0}, unmodified[7] = {0};
  g_unichar_to_utf8(gdk_keyval_to_unicode(symbol), text);
  NXSKeyEvent key = {sizeof(key), NXS_KEY_DOWN, event_modifiers(state),
                     logical_key(symbol), 0, text, text};
  if (key.key == NXS_KEY_TEXT) {
    if (!key.modifiers || (gdk_key_event_get_consumed_modifiers(event) &
                           state & ~(GDK_SHIFT_MASK | GDK_LOCK_MASK)))
      return FALSE;
    guint plain_symbol;
    if (!gdk_display_translate_key(gtk_widget_get_display(window), keycode,
          state & (GDK_SHIFT_MASK | GDK_LOCK_MASK), gdk_key_event_get_layout(event),
          &plain_symbol, NULL, NULL, NULL))
      return FALSE;
    gunichar plain = gdk_keyval_to_unicode(plain_symbol);
    if (plain < 32)
      return FALSE;
    g_unichar_to_utf8(plain, unmodified);
    key.unmodified_text = unmodified;
  }
  return resolve_key(GTK_WINDOW(window), &key);
}

void nextspace_gtk_attach_editing(GtkWidget *widget)
{
  if (!GTK_IS_WINDOW(widget) || g_object_get_data(G_OBJECT(widget), "nextspace-editing-attached"))
    return;
  g_object_set_data(G_OBJECT(widget), "nextspace-editing-attached", GINT_TO_POINTER(1));
  GtkEventController *controller = gtk_event_controller_key_new();
  gtk_event_controller_set_propagation_phase(controller, GTK_PHASE_CAPTURE);
  g_signal_connect(controller, "key-pressed", G_CALLBACK(key_press), NULL);
  gtk_widget_add_controller(widget, controller);
  g_signal_connect(widget, "notify::focus-widget", G_CALLBACK(focus_changed), NULL);
}
#endif
