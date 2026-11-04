/* Host NSScroller in GTK's existing adjustment/accessibility boundary.
 * GPL-2.0-or-later. */
#include "NativeScroller.h"
#include <gtk/gtk.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  GtkWidget *widget;
  NXSScroller *native;
  GtkAdjustment *adjustment;
  GdkSurface *surface;
  gulong scale_handler;
  gboolean detached;
  guint source;
  double down_x,down_y,last_x,last_y;
  unsigned down_modifiers,last_modifiers;
  gboolean moved,released;
} NativeBar;
static void (*original_snapshot)(GtkWidget *, GtkSnapshot *);
static void (*original_allocate)(GtkWidget *, int, int, int);

static void allocate(GtkWidget *widget, int width, int height, int baseline)
{
  original_allocate(widget,width,height,baseline);
  if (!g_object_get_data(G_OBJECT(widget),"nextspace-scroller-placement")) return;
  GtkScrolledWindow *window=GTK_SCROLLED_WINDOW(widget);
  GtkWidget *child=gtk_scrolled_window_get_child(window);
  GtkWidget *vertical=gtk_scrolled_window_get_vscrollbar(window);
  GtkWidget *horizontal=gtk_scrolled_window_get_hscrollbar(window);
  if (!child || !gtk_widget_get_child_visible(vertical)) return;
  GtkAllocation content, bar; GtkBorder border={0};
  gtk_widget_get_allocation(child,&content);
  if (GTK_IS_SCROLLABLE(child)) gtk_scrollable_get_border(GTK_SCROLLABLE(child),&border);
  gtk_widget_get_allocation(vertical,&bar);
  /* GTK4.18's non-overlay TOP_RIGHT path drops the content's X origin when
   * allocating scrollbars. Keep its content layout and repair that offset. */
  int left=content.x+border.left-bar.width;
  if (bar.x!=left) {bar.x=left;gtk_widget_size_allocate(vertical,&bar,-1);}
  if (gtk_widget_get_child_visible(horizontal)) {
    gtk_widget_get_allocation(horizontal,&bar);
    if (bar.x!=content.x+border.left) {bar.x=content.x+border.left;gtk_widget_size_allocate(horizontal,&bar,-1);}
  }
}

static unsigned modifiers(GdkModifierType flags)
{
  return ((flags & GDK_ALT_MASK) ? NXS_ALT : 0) | ((flags & GDK_SHIFT_MASK) ? NXS_SHIFT : 0) |
    ((flags & GDK_CONTROL_MASK) ? NXS_CONTROL : 0) | ((flags & GDK_SUPER_MASK) ? NXS_SUPER : 0);
}
static void changed(void *context, double value)
{
  NativeBar *bar = context;
  if (!bar->widget) return;
  gtk_adjustment_set_value(gtk_scrollbar_get_adjustment(GTK_SCROLLBAR(bar->widget)), value);
  gtk_widget_queue_draw(bar->widget);
}
static void pump(void *context)
{
  NativeBar *bar=context;
  if(bar->moved) {bar->moved=FALSE;nxs_scroller_send(bar->native,NXS_MOVE,bar->last_x,bar->last_y,bar->last_modifiers);}
  if(bar->released) {bar->released=FALSE;nxs_scroller_send(bar->native,NXS_RELEASE,bar->last_x,bar->last_y,bar->last_modifiers);}
  /* Dispatch a bounded batch: a busy source must not starve native tracking. */
  for (int i = 0; i < 16 && g_main_context_pending(NULL); i++) g_main_context_iteration(NULL, FALSE);
}
static void sync_bar(NativeBar *bar)
{
  GtkAdjustment *adjustment = gtk_scrollbar_get_adjustment(GTK_SCROLLBAR(bar->widget));
  gboolean horizontal = gtk_orientable_get_orientation(GTK_ORIENTABLE(bar->widget)) == GTK_ORIENTATION_HORIZONTAL;
  nxs_scroller_sync(bar->native, horizontal ? gtk_widget_get_width(bar->widget) : gtk_widget_get_height(bar->widget),
    gtk_adjustment_get_lower(adjustment), gtk_adjustment_get_upper(adjustment),
    gtk_adjustment_get_page_size(adjustment), gtk_adjustment_get_step_increment(adjustment),
    gtk_adjustment_get_page_increment(adjustment), gtk_adjustment_get_value(adjustment),
    gtk_widget_is_sensitive(bar->widget));
}
static void scale_changed(GObject *surface,GParamSpec *property,gpointer data)
{
  NativeBar *bar=data;if(bar->widget) gtk_widget_queue_draw(bar->widget);
}
static void watch_surface(NativeBar *bar)
{
  GtkNative *native=gtk_widget_get_native(bar->widget);
  GdkSurface *surface=native?gtk_native_get_surface(native):NULL;
  if(bar->surface==surface) return;
  if(bar->surface) {g_signal_handler_disconnect(bar->surface,bar->scale_handler);g_clear_object(&bar->surface);}
  if(surface) {
    bar->surface=g_object_ref(surface);
    /* A fractional scale change can leave GTK's integer scale-factor intact.
     * Our native bitmap must be regenerated at the new physical density. */
    bar->scale_handler=g_signal_connect(surface,"notify::scale",G_CALLBACK(scale_changed),bar);
  }
}
static void snapshot(GtkWidget *widget, GtkSnapshot *snapshot)
{
  NativeBar *bar = g_object_get_data(G_OBJECT(widget), "nextspace-native-scroller");
  if (!bar) { original_snapshot(widget, snapshot); return; }
  sync_bar(bar);
  GtkNative *native = gtk_widget_get_native(widget);
  GdkSurface *surface = native ? gtk_native_get_surface(native) : NULL;
  double scale = surface ? gdk_surface_get_scale(surface) : gtk_widget_get_scale_factor(widget);
  NXSBitmap bitmap = nxs_scroller_draw(bar->native, scale);
  if (!bitmap.pixels) return;
  graphene_rect_t bounds = GRAPHENE_RECT_INIT(0, 0, gtk_widget_get_width(widget), gtk_widget_get_height(widget));
  cairo_t *cr = gtk_snapshot_append_cairo(snapshot, &bounds);
  cairo_surface_t *image = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, bitmap.width, bitmap.height);
  for (int y=0; y<bitmap.height; y++) memcpy(cairo_image_surface_get_data(image)+y*cairo_image_surface_get_stride(image),
    bitmap.pixels+y*bitmap.stride, bitmap.stride);
  cairo_surface_mark_dirty(image);
  cairo_scale(cr, 1/scale, 1/scale);
  cairo_set_source_surface(cr, image, 0, 0); cairo_paint(cr);
  cairo_surface_destroy(image); cairo_destroy(cr);
}
static void free_bar(gpointer data)
{
  NativeBar *bar = data; bar->widget = NULL;
  if(bar->surface) {g_signal_handler_disconnect(bar->surface,bar->scale_handler);g_clear_object(&bar->surface);}
  if(bar->source) g_source_remove(bar->source);
  if (bar->adjustment) { g_signal_handlers_disconnect_by_data(bar->adjustment,bar); g_clear_object(&bar->adjustment); }
  if (nxs_scroller_tracking(bar->native)) {
    bar->detached = TRUE; nxs_scroller_send(bar->native, NXS_RELEASE, 0, 0, 0); return;
  }
  nxs_scroller_destroy(bar->native); g_free(bar);
}
static void adjustment_changed(GtkAdjustment *adjustment, gpointer data)
{
  NativeBar *bar=data;
  if (bar->widget) gtk_widget_queue_draw(bar->widget);
}
static void bind_adjustment(GObject *object, GParamSpec *property, gpointer data)
{
  NativeBar *bar=data;
  if (bar->adjustment) { g_signal_handlers_disconnect_by_data(bar->adjustment,bar); g_clear_object(&bar->adjustment); }
  bar->adjustment=g_object_ref(gtk_scrollbar_get_adjustment(GTK_SCROLLBAR(object)));
  g_signal_connect(bar->adjustment,"changed",G_CALLBACK(adjustment_changed),bar);
  g_signal_connect(bar->adjustment,"value-changed",G_CALLBACK(adjustment_changed),bar);
  gtk_widget_queue_draw(GTK_WIDGET(object));
}
static gboolean begin_tracking(gpointer data)
{
  NativeBar *bar=data;bar->source=0;
  sync_bar(bar);
  nxs_scroller_track(bar->native,bar->down_x,bar->down_y,bar->down_modifiers);
  if(bar->widget) gtk_widget_queue_draw(bar->widget);
  if(bar->detached) {nxs_scroller_destroy(bar->native);g_free(bar);}
  return G_SOURCE_REMOVE;
}
static void unmapped(GtkWidget *widget,gpointer data)
{
  NativeBar *bar=data;
  if(bar->source) {g_source_remove(bar->source);bar->source=0;}
  nxs_scroller_send(bar->native,NXS_RELEASE,0,0,0);
}
static gboolean input(GtkEventControllerLegacy *controller, GdkEvent *event, gpointer data)
{
  NativeBar *bar = data;
  GdkEventType type = gdk_event_get_event_type(event);
  double x, y;
  if (!gdk_event_get_position(event, &x, &y)) return FALSE;
  /* GDK positions are surface coordinates; translate into the scrollbar. */
  GtkNative *native = gtk_widget_get_native(bar->widget);
  graphene_point_t source = GRAPHENE_POINT_INIT(x, y), destination;
  double tx, ty; gtk_native_get_surface_transform(native, &tx, &ty);
  source.x -= tx; source.y -= ty;
  if (!gtk_widget_compute_point(GTK_WIDGET(native), bar->widget, &source, &destination)) return FALSE;
  unsigned flags = modifiers(gdk_event_get_modifier_state(event));
  if (bar->source || nxs_scroller_tracking(bar->native)) {
    if (type == GDK_MOTION_NOTIFY || type == GDK_BUTTON_RELEASE) {
      if(bar->source) {
        bar->last_x=destination.x;bar->last_y=destination.y;bar->last_modifiers=flags;
        if(type==GDK_BUTTON_RELEASE) bar->released=TRUE;else bar->moved=TRUE;
      } else nxs_scroller_send(bar->native, type == GDK_BUTTON_RELEASE ? NXS_RELEASE : NXS_MOVE,
        destination.x, destination.y, flags);
      return TRUE;
    }
  } else if (type == GDK_BUTTON_PRESS && gdk_button_event_get_button(event) == GDK_BUTTON_PRIMARY) {
    /* Return from GDK's event dispatch before entering AppKit tracking. GDK
     * keeps its frame clock frozen until that dispatch completes. */
    bar->down_x=destination.x;bar->down_y=destination.y;bar->down_modifiers=flags;
    bar->moved=bar->released=FALSE;
    bar->source=g_idle_add_full(G_PRIORITY_DEFAULT_IDLE,begin_tracking,bar,NULL);
    return TRUE;
  }
  return FALSE;
}
static void placement(GtkScrolledWindow *window)
{
  /* Placement changes content geometry, never text or application direction. */
  GtkCornerType corner = gtk_widget_get_direction(GTK_WIDGET(window)) == GTK_TEXT_DIR_RTL ?
    GTK_CORNER_TOP_LEFT : GTK_CORNER_TOP_RIGHT;
  if (gtk_scrolled_window_get_placement(window) != corner) gtk_scrolled_window_set_placement(window, corner);
  if (gtk_scrolled_window_get_overlay_scrolling(window)) gtk_scrolled_window_set_overlay_scrolling(window, FALSE);
}
static void settings_changed(GObject *object, GParamSpec *property, gpointer data) { placement(GTK_SCROLLED_WINDOW(object)); }
static void direction_changed(GtkWidget *widget, GtkTextDirection previous, gpointer data) { placement(GTK_SCROLLED_WINDOW(widget)); }

static gboolean mapped(GSignalInvocationHint *hint, guint count, const GValue *values, gpointer unused)
{
  GtkWidget *widget = g_value_get_object(values);
  GdkDisplay *display=gtk_widget_get_display(widget);
  if(!g_object_get_data(G_OBJECT(display),"nextspace-scroller-css")) {
    GtkCssProvider *css=gtk_css_provider_new();
    gtk_css_provider_load_from_string(css,"scrollbar.nextspace-native-scroller { min-width: 0; min-height: 0; padding: 0; margin: 0; border: 0; background: none; }");
    gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_USER);
    g_object_unref(css);g_object_set_data(G_OBJECT(display),"nextspace-scroller-css",GINT_TO_POINTER(1));
  }
  if (GTK_IS_SCROLLED_WINDOW(widget)) {
    placement(GTK_SCROLLED_WINDOW(widget));
    if (!g_object_get_data(G_OBJECT(widget), "nextspace-scroller-placement")) {
      g_object_set_data(G_OBJECT(widget), "nextspace-scroller-placement", GINT_TO_POINTER(1));
      g_signal_connect(widget, "notify::window-placement", G_CALLBACK(settings_changed), NULL);
      g_signal_connect(widget, "notify::overlay-scrolling", G_CALLBACK(settings_changed), NULL);
      g_signal_connect(widget, "direction-changed", G_CALLBACK(direction_changed), NULL);
    }
  }
  if (GTK_IS_SCROLLBAR(widget) && !g_object_get_data(G_OBJECT(widget), "nextspace-native-scroller")) {
    NativeBar *bar = g_new0(NativeBar, 1); bar->widget = widget;
    gboolean horizontal = gtk_orientable_get_orientation(GTK_ORIENTABLE(widget)) == GTK_ORIENTATION_HORIZONTAL;
    bar->native = nxs_scroller_create(horizontal, changed, pump, bar);
    if (!bar->native) { g_free(bar); return TRUE; }
    g_object_set_data_full(G_OBJECT(widget), "nextspace-native-scroller", bar, free_bar);
    bind_adjustment(G_OBJECT(widget),NULL,bar);
    g_signal_connect(widget,"notify::adjustment",G_CALLBACK(bind_adjustment),bar);
    g_signal_connect(widget,"unmap",G_CALLBACK(unmapped),bar);
    /* Keep GTK's adjustment and accessible range; replace its child drawing
     * and input with the real NSScroller. No replacement scrollbar class. */
    GtkWidget *range = gtk_widget_get_first_child(widget);
    if (range) gtk_widget_set_child_visible(range, FALSE);
    gtk_widget_add_css_class(widget, "nextspace-native-scroller");
    int width = (int)lround(nxs_scroller_width());
    gtk_widget_set_size_request(widget, horizontal ? -1 : width, horizontal ? width : -1);
    GtkEventController *events = gtk_event_controller_legacy_new();
    gtk_event_controller_set_propagation_phase(events, GTK_PHASE_CAPTURE);
    g_signal_connect(events, "event", G_CALLBACK(input), bar);
    gtk_widget_add_controller(widget, events);
  }
  if(GTK_IS_SCROLLBAR(widget)) {
    NativeBar *bar=g_object_get_data(G_OBJECT(widget),"nextspace-native-scroller");
    if(bar) watch_surface(bar);
  }
  return TRUE;
}
static void visit(GtkWidget *widget)
{
  GValue value=G_VALUE_INIT;g_value_init(&value,G_TYPE_OBJECT);g_value_set_object(&value,widget);
  mapped(NULL,1,&value,NULL);g_value_unset(&value);
  for(GtkWidget *child=gtk_widget_get_first_child(widget);child;child=gtk_widget_get_next_sibling(child)) visit(child);
}

void nextspace_gtk4_scrollbars_init(void)
{
  static gboolean initialized;
  if (initialized || g_strcmp0(g_getenv("NEXTSPACE_SCROLLBARS"), "off") == 0) return;
  initialized = TRUE;
  GtkWidgetClass *klass = g_type_class_ref(GTK_TYPE_SCROLLBAR);
  original_snapshot = klass->snapshot; klass->snapshot = snapshot;
  GtkWidgetClass *scrolled=g_type_class_ref(GTK_TYPE_SCROLLED_WINDOW);
  original_allocate=scrolled->size_allocate;scrolled->size_allocate=allocate;
  g_signal_add_emission_hook(g_signal_lookup("map", GTK_TYPE_WIDGET), 0, mapped, NULL, NULL);
  /* Late-loaded language bindings may have mapped their initial widgets. */
  GListModel *windows=gtk_window_get_toplevels();
  for(guint i=0;i<g_list_model_get_n_items(windows);i++) {
    GtkWidget *window=g_list_model_get_item(windows,i);visit(window);g_object_unref(window);
  }
}
