/* Independent native toolkit comparison. SPDX-License-Identifier: MIT */
#include <gtk/gtk.h>
#include <gdk/x11/gdkx.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>

static bool drag_source_mode, drag_target_mode;
static bool drag_move, drag_reject;
static const char *drag_file;
static const char *drag_uri;
static const char *drag_text = "NextSpace日本語";
static unsigned drag_repeat = 1;
static bool initial_maximized, initial_fullscreen;
static bool window_drag;
static const char *window_title;
static bool capture_pattern;
static void install_window_keys(GtkWidget *window);

static gboolean window_key(GtkEventControllerKey *controller, guint keyval,
    guint keycode, GdkModifierType state, gpointer data)
{
  GtkWindow *window = data;
  switch (keyval) {
  case GDK_KEY_m: gtk_window_maximize(window); break;
  case GDK_KEY_u: gtk_window_unmaximize(window); break;
  case GDK_KEY_f: gtk_window_fullscreen(window); break;
  case GDK_KEY_r: gtk_window_unfullscreen(window); break;
  case GDK_KEY_d: {
    GtkWidget *dialog = gtk_window_new();
    gtk_window_set_title(GTK_WINDOW(dialog), "GtkStateDialog");
    gtk_window_set_default_size(GTK_WINDOW(dialog), 321, 201);
    gtk_window_set_decorated(GTK_WINDOW(dialog), FALSE);
    gtk_window_set_transient_for(GTK_WINDOW(dialog), window);
    gtk_window_set_modal(GTK_WINDOW(dialog), TRUE);
    install_window_keys(dialog);
    gtk_window_present(GTK_WINDOW(dialog));
    break;
  }
  case GDK_KEY_Escape:
    if (!gtk_window_get_transient_for(window)) return FALSE;
    gtk_window_destroy(window);
    break;
  case GDK_KEY_1: case GDK_KEY_2: {
    GListModel *monitors = gdk_display_get_monitors(gtk_widget_get_display(GTK_WIDGET(window)));
    GdkMonitor *monitor = g_list_model_get_item(monitors, keyval - GDK_KEY_1);
    if (monitor) {
      printf("{\"event\":\"fullscreen-output\",\"name\":\"%s\"}\n", gdk_monitor_get_connector(monitor));
      fflush(stdout);
      gtk_window_fullscreen_on_monitor(window, monitor); g_object_unref(monitor);
    }
    break;
  }
  default: return FALSE;
  }
  return TRUE;
}

static void install_window_keys(GtkWidget *window)
{
  GtkEventController *keys = gtk_event_controller_key_new();
  g_signal_connect(keys, "key-pressed", G_CALLBACK(window_key), window);
  gtk_widget_add_controller(window, keys);
}

static void window_state(GObject *object, GParamSpec *property, gpointer data)
{
  printf("{\"event\":\"window-state\",\"maximized\":%s,\"fullscreen\":%s}\n",
    gtk_window_is_maximized(GTK_WINDOW(object)) ? "true" : "false",
    gtk_window_is_fullscreen(GTK_WINDOW(object)) ? "true" : "false");
  fflush(stdout);
}

static gboolean x11_event(GdkDisplay *display, XEvent *event, void *data)
{
  if (window_drag && event->type == ConfigureNotify) {
    printf("{\"event\":\"x11-configure\",\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}\n",
      event->xconfigure.x, event->xconfigure.y, event->xconfigure.width, event->xconfigure.height);
    fflush(stdout);
  }
  if (event->type == ClientMessage && event->xclient.message_type ==
      gdk_x11_get_xatom_by_name_for_display(display, "XdndFinished")) {
    printf("{\"event\":\"xdnd-finished\",\"success\":%s}\n",
      event->xclient.data.l[1] & 1 ? "true" : "false"); fflush(stdout);
  }
  return FALSE;
}

static void draw(GtkDrawingArea *area, cairo_t *cr, int width, int height, void *data)
{
  cairo_set_source_rgb(cr, 0.75, 0.75, 0.75); cairo_paint(cr);
  if (capture_pattern) {
    cairo_set_source_rgb(cr, 0.25, 0.25, 0.25);
    cairo_rectangle(cr, width / 2, 0, width - width / 2, height); cairo_fill(cr);
  }
  cairo_set_source_rgb(cr, 0, 0, 0); cairo_set_font_size(cr, 18);
  cairo_move_to(cr, 20, 40); cairo_show_text(cr, "GTK native Wayland: text and thin lines");
  cairo_rectangle(cr, 20, 60, 761, 1); cairo_fill(cr);
}
static void pressed(GtkGestureClick *gesture, int count, double x, double y, void *data)
{
  printf("{\"event\":\"click\",\"x\":%.0f,\"y\":%.0f}\n", x, y); fflush(stdout);
  if (window_drag) {
    GtkEventController *controller = GTK_EVENT_CONTROLLER(gesture);
    GdkEvent *event = gtk_event_controller_get_current_event(controller);
    GdkSurface *surface = gtk_native_get_surface(GTK_NATIVE(data));
    gdk_toplevel_begin_move(GDK_TOPLEVEL(surface), gdk_event_get_device(event),
      gtk_gesture_single_get_current_button(GTK_GESTURE_SINGLE(gesture)), x, y,
      gdk_event_get_time(event));
    gdk_display_sync(gdk_surface_get_display(surface));
    puts("{\"event\":\"window-move-requested\"}"); fflush(stdout);
  }
}
static gboolean move_input(GtkEventControllerLegacy *controller, GdkEvent *event, void *data)
{
  double x = 0, y = 0;
  gdk_event_get_position(event, &x, &y);
  GdkEventType type = gdk_event_get_event_type(event);
  if (type == GDK_BUTTON_PRESS || type == GDK_BUTTON_RELEASE || type == GDK_MOTION_NOTIFY ||
      type == GDK_ENTER_NOTIFY || type == GDK_LEAVE_NOTIFY) {
    printf("{\"event\":\"move-input\",\"type\":%u,\"x\":%.0f,\"y\":%.0f,\"time\":%u}\n",
      type, x, y, gdk_event_get_time(event)); fflush(stdout);
  }
  return FALSE;
}
static GdkContentProvider *drag_prepare(GtkDragSource *source, double x, double y, void *data)
{
  puts("{\"event\":\"drag-prepare\"}"); fflush(stdout);
  if (drag_uri) {
    GBytes *bytes = g_bytes_new(drag_uri, strlen(drag_uri));
    GdkContentProvider *provider = gdk_content_provider_new_for_bytes("text/uri-list", bytes);
    g_bytes_unref(bytes); return provider;
  }
  if (drag_file) {
    GFile *file = g_file_new_for_path(drag_file);
    GdkFileList *files = gdk_file_list_new_from_array(&file, 1);
    GdkContentProvider *provider = gdk_content_provider_new_typed(GDK_TYPE_FILE_LIST, files);
    g_boxed_free(GDK_TYPE_FILE_LIST, files); g_object_unref(file);
    return provider;
  }
  GString *text = g_string_new(NULL);
  for (unsigned i = 0; i < drag_repeat; i++) g_string_append(text, drag_text);
  GdkContentProvider *provider = gdk_content_provider_new_typed(G_TYPE_STRING, text->str);
  g_string_free(text, TRUE);
  return provider;
}
static gboolean drag_cancel(GtkDragSource *source, GdkDrag *drag, GdkDragCancelReason reason, void *data)
{
  printf("{\"event\":\"drag-cancel\",\"reason\":%u}\n", reason); fflush(stdout);
  return FALSE;
}
static void drag_end(GtkDragSource *source, GdkDrag *drag, gboolean delete_data, void *data)
{
  printf("{\"event\":\"drag-end\",\"action\":%u,\"delete\":%s}\n",
    gdk_drag_get_selected_action(drag), delete_data ? "true" : "false"); fflush(stdout);
}
static void drag_action(GdkDrag *drag, GParamSpec *property, void *data)
{
  printf("{\"event\":\"drag-action\",\"action\":%u}\n", gdk_drag_get_selected_action(drag));
  fflush(stdout);
}
static void drag_begin(GtkDragSource *source, GdkDrag *drag, void *data)
{
  g_signal_connect(drag, "notify::selected-action", G_CALLBACK(drag_action), NULL);
  drag_action(drag, NULL, NULL);
}
static gboolean drag_drop(GtkDropTarget *target, const GValue *value, double x, double y, void *data)
{
  if (drag_reject) return FALSE;
  if (G_VALUE_HOLDS(value, GDK_TYPE_FILE_LIST)) {
    GSList *files = gdk_file_list_get_files(g_value_get_boxed(value));
    if (!files) return FALSE;
    printf("{\"event\":\"drop\",\"x\":%.0f,\"y\":%.0f,\"file_base64\":[", x, y);
    for (GSList *item = files; item; item = item->next) {
      char *path = g_file_get_path(item->data);
      char *encoded = path ? g_base64_encode((const guchar *)path, strlen(path)) : NULL;
      printf("%s\"%s\"", item == files ? "" : ",", encoded ? encoded : "");
      g_free(path); g_free(encoded);
    }
    puts("]}"); fflush(stdout);
    return TRUE;
  }
  const char *text = g_value_get_string(value);
  if (!text) return FALSE;
  char *encoded = g_base64_encode((const guchar *)text, strlen(text));
  printf("{\"event\":\"drop\",\"base64\":\"%s\",\"x\":%.0f,\"y\":%.0f}\n", encoded, x, y);
  fflush(stdout); g_free(encoded);
  return TRUE;
}
static void install_drag_source(GtkWidget *area, GtkGesture *click)
{
  GtkDragSource *source = gtk_drag_source_new();
  gtk_drag_source_set_actions(source, drag_move ? GDK_ACTION_MOVE : GDK_ACTION_COPY);
  g_signal_connect(source, "prepare", G_CALLBACK(drag_prepare), NULL);
  g_signal_connect(source, "drag-begin", G_CALLBACK(drag_begin), NULL);
  g_signal_connect(source, "drag-end", G_CALLBACK(drag_end), NULL);
  g_signal_connect(source, "drag-cancel", G_CALLBACK(drag_cancel), NULL);
  guchar *pixels = g_malloc(32 * 32 * 4);
  for (int index = 0; index < 32 * 32; index++) {
    pixels[index * 4] = 255; pixels[index * 4 + 1] = 0;
    pixels[index * 4 + 2] = 0; pixels[index * 4 + 3] = 255;
  }
  GBytes *bytes = g_bytes_new_take(pixels, 32 * 32 * 4);
  GdkTexture *texture = gdk_memory_texture_new(32, 32, GDK_MEMORY_R8G8B8A8_PREMULTIPLIED, bytes, 128);
  gtk_drag_source_set_icon(source, GDK_PAINTABLE(texture), 8, 8);
  g_object_unref(texture); g_bytes_unref(bytes);
  gtk_widget_add_controller(area, GTK_EVENT_CONTROLLER(source));
  gtk_gesture_group(click, GTK_GESTURE(source));
}
static void activate(GtkApplication *app, void *data)
{
  GdkDisplay *display = gdk_display_get_default();
  if ((drag_source_mode || window_drag) && GDK_IS_X11_DISPLAY(display))
    g_signal_connect(display, "xevent", G_CALLBACK(x11_event), NULL);
  GtkWidget *window = gtk_application_window_new(app);
  gtk_window_set_title(GTK_WINDOW(window), window_title ? window_title :
    drag_source_mode ? "GtkDragSource" : drag_target_mode ? "GtkDragTarget" : "GtkProbe");
  gtk_window_set_decorated(GTK_WINDOW(window), FALSE);
  gtk_window_set_default_size(GTK_WINDOW(window), 801, 601);
  install_window_keys(window);
  g_signal_connect(window, "notify::maximized", G_CALLBACK(window_state), NULL);
  g_signal_connect(window, "notify::fullscreened", G_CALLBACK(window_state), NULL);
  GtkWidget *area = gtk_drawing_area_new();
  gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(area), draw, NULL, NULL);
  GtkGesture *click = gtk_gesture_click_new();
  g_signal_connect(click, "pressed", G_CALLBACK(pressed), window);
  gtk_widget_add_controller(area, GTK_EVENT_CONTROLLER(click));
  if (window_drag) {
    GtkEventController *input = gtk_event_controller_legacy_new();
    gtk_event_controller_set_propagation_phase(input, GTK_PHASE_CAPTURE);
    g_signal_connect(input, "event", G_CALLBACK(move_input), NULL);
    gtk_widget_add_controller(window, input);
  }
  if (drag_source_mode) install_drag_source(area, click);
  if (drag_target_mode) {
    GtkDropTarget *target = gtk_drop_target_new(G_TYPE_STRING, drag_move ? GDK_ACTION_MOVE : GDK_ACTION_COPY);
    GType types[] = {GDK_TYPE_FILE_LIST, G_TYPE_STRING};
    gtk_drop_target_set_gtypes(target, types, G_N_ELEMENTS(types));
    g_signal_connect(target, "drop", G_CALLBACK(drag_drop), NULL);
    gtk_widget_add_controller(area, GTK_EVENT_CONTROLLER(target));
  }
  gtk_window_set_child(GTK_WINDOW(window), area);
  if (initial_maximized) gtk_window_maximize(GTK_WINDOW(window));
  if (initial_fullscreen) gtk_window_fullscreen(GTK_WINDOW(window));
  gtk_window_present(GTK_WINDOW(window));
}
int main(int argc, char **argv)
{
  int arguments = 1;
  for (int index = 1; index < argc; index++) {
    if (strcmp(argv[index], "--maximize") == 0) initial_maximized = true;
    else if (strcmp(argv[index], "--fullscreen") == 0) initial_fullscreen = true;
    else if (strcmp(argv[index], "--window-drag") == 0) window_drag = true;
    else if (strcmp(argv[index], "--capture-pattern") == 0) capture_pattern = true;
    else if (strcmp(argv[index], "--title") == 0 && index + 1 < argc) window_title = argv[++index];
    else if (strcmp(argv[index], "--drag-source") == 0) drag_source_mode = true;
    else if (strcmp(argv[index], "--drag-target") == 0) drag_target_mode = true;
    else if (strcmp(argv[index], "--drag-move") == 0) drag_move = true;
    else if (strcmp(argv[index], "--reject-drop") == 0) drag_reject = true;
    else if (strcmp(argv[index], "--drag-file") == 0 && index + 1 < argc) drag_file = argv[++index];
    else if (strcmp(argv[index], "--drag-uri") == 0 && index + 1 < argc) drag_uri = argv[++index];
    else if (strcmp(argv[index], "--drag-repeat") == 0 && index + 1 < argc) {
      char *end;
      guint64 value = g_ascii_strtoull(argv[++index], &end, 10);
      if (*end || value < 1 || value > 1048576) return 2;
      drag_repeat = value;
    }
    else argv[arguments++] = argv[index];
  }
  argv[arguments] = NULL;
  GtkApplication *app = gtk_application_new("org.nextspace.GtkProbe", G_APPLICATION_NON_UNIQUE);
  g_signal_connect(app, "activate", G_CALLBACK(activate), NULL);
  int result = g_application_run(G_APPLICATION(app), arguments, argv);
  g_object_unref(app);
  return result;
}
