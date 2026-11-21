/* GTK3 host adapter; rendering and tracking remain in NSScroller.
 * GPL-2.0-or-later. */
#include "NativeScroller.h"
#include <gtk/gtk.h>
#include <math.h>
#include <string.h>
void nextspace_gtk3_attach_control(GtkWidget *);
void nextspace_gtk3_attach_menu(GtkWidget *);
void nextspace_gtk_attach_editing(GtkWidget *);
void nextspace_gtk3_observe_context_parent(void *);
typedef struct {
  GtkWidget *widget;
  NXSScroller *native;
  GtkAdjustment *adjustment;
  gboolean detached;
  guint source;
  double down_x,down_y,last_x,last_y;
  unsigned down_modifiers,last_modifiers;
  gboolean moved,released;
} NativeBar;
static gboolean (*original_draw)(GtkWidget *,cairo_t *);
static unsigned modifiers(guint state) {
  return ((state&GDK_MOD1_MASK)?NXS_ALT:0)|((state&GDK_SHIFT_MASK)?NXS_SHIFT:0)|
    ((state&GDK_CONTROL_MASK)?NXS_CONTROL:0)|((state&GDK_SUPER_MASK)?NXS_SUPER:0);
}
static void changed(void *context,double value) {
  NativeBar *bar=context;
  if(bar->widget) {gtk_adjustment_set_value(bar->adjustment,value);gtk_widget_queue_draw(bar->widget);}
}
static void pump(void *context) {
  NativeBar *bar=context;
  if(bar->moved) {bar->moved=FALSE;nxs_scroller_send(bar->native,NXS_MOVE,bar->last_x,bar->last_y,bar->last_modifiers);}
  if(bar->released) {bar->released=FALSE;nxs_scroller_send(bar->native,NXS_RELEASE,bar->last_x,bar->last_y,bar->last_modifiers);}
  for(int i=0;i<16 && g_main_context_pending(NULL);i++) g_main_context_iteration(NULL,FALSE);
}
static void sync_bar(NativeBar *bar) {
  GtkAdjustment *a=bar->adjustment;
  gboolean horizontal=gtk_orientable_get_orientation(GTK_ORIENTABLE(bar->widget))==GTK_ORIENTATION_HORIZONTAL;
  nxs_scroller_sync(bar->native,horizontal?gtk_widget_get_allocated_width(bar->widget):gtk_widget_get_allocated_height(bar->widget),
    gtk_adjustment_get_lower(a),gtk_adjustment_get_upper(a),gtk_adjustment_get_page_size(a),
    gtk_adjustment_get_step_increment(a),gtk_adjustment_get_page_increment(a),gtk_adjustment_get_value(a),gtk_widget_is_sensitive(bar->widget));
}
static gboolean draw(GtkWidget *widget,cairo_t *cr) {
  NativeBar *bar=g_object_get_data(G_OBJECT(widget),"nextspace-native-scroller");
  if(!bar) return original_draw(widget,cr);
  sync_bar(bar);
  NXSBitmap bitmap=nxs_scroller_draw(bar->native,gtk_widget_get_scale_factor(widget));
  if(bitmap.pixels) {
    cairo_surface_t *image=cairo_image_surface_create_for_data((unsigned char *)bitmap.pixels,
      CAIRO_FORMAT_ARGB32,bitmap.width,bitmap.height,bitmap.stride);
    cairo_save(cr);double scale=gtk_widget_get_scale_factor(widget);cairo_scale(cr,1/scale,1/scale);
    cairo_set_source_surface(cr,image,0,0);cairo_paint(cr);cairo_restore(cr);cairo_surface_destroy(image);
  }
  return TRUE;
}
static void queue(GtkAdjustment *adjustment,gpointer data) {
  NativeBar *bar=data;if(bar->widget) gtk_widget_queue_draw(bar->widget);
}
static void bind_adjustment(GObject *object,GParamSpec *property,gpointer data) {
  NativeBar *bar=data;
  if(bar->adjustment) {g_signal_handlers_disconnect_by_data(bar->adjustment,bar);g_clear_object(&bar->adjustment);}
  bar->adjustment=g_object_ref(gtk_range_get_adjustment(GTK_RANGE(object)));
  g_signal_connect(bar->adjustment,"changed",G_CALLBACK(queue),bar);
  g_signal_connect(bar->adjustment,"value-changed",G_CALLBACK(queue),bar);
}
static void free_bar(gpointer data) {
  NativeBar *bar=data;bar->widget=NULL;
  if(bar->source) g_source_remove(bar->source);
  g_signal_handlers_disconnect_by_data(bar->adjustment,bar);g_clear_object(&bar->adjustment);
  if(nxs_scroller_tracking(bar->native)) {bar->detached=TRUE;nxs_scroller_send(bar->native,NXS_RELEASE,0,0,0);return;}
  nxs_scroller_destroy(bar->native);g_free(bar);
}
static gboolean begin_tracking(gpointer data) {
  NativeBar *bar=data;bar->source=0;sync_bar(bar);
  nxs_scroller_track(bar->native,bar->down_x,bar->down_y,bar->down_modifiers);
  if(bar->widget) {gtk_grab_remove(bar->widget);gtk_widget_queue_draw(bar->widget);}
  if(bar->detached) {nxs_scroller_destroy(bar->native);g_free(bar);}
  return G_SOURCE_REMOVE;
}
static void unmapped(GtkWidget *widget,gpointer data) {
  NativeBar *bar=data;
  if(bar->source) {g_source_remove(bar->source);bar->source=0;gtk_grab_remove(widget);}
  nxs_scroller_send(bar->native,NXS_RELEASE,0,0,0);
}
static gboolean input(GtkWidget *widget,GdkEvent *event,gpointer data) {
  NativeBar *bar=data;double x,y;guint state;
  if(event->type==GDK_2BUTTON_PRESS||event->type==GDK_3BUTTON_PRESS) return TRUE;
  if(!gdk_event_get_coords(event,&x,&y)) return FALSE;
  gdk_event_get_state(event,&state);
  /* GtkRange owns an input-only window; its event coordinates are widget-local. */
  if(bar->source || nxs_scroller_tracking(bar->native)) {
    if(event->type==GDK_MOTION_NOTIFY||event->type==GDK_BUTTON_RELEASE) {
      if(bar->source) {
        bar->last_x=x;bar->last_y=y;bar->last_modifiers=modifiers(state);
        if(event->type==GDK_BUTTON_RELEASE) bar->released=TRUE;else bar->moved=TRUE;
      } else nxs_scroller_send(bar->native,event->type==GDK_BUTTON_RELEASE?NXS_RELEASE:NXS_MOVE,x,y,modifiers(state));
      return TRUE;
    }
  } else if(event->type==GDK_BUTTON_PRESS&&event->button.button==GDK_BUTTON_PRIMARY) {
    gtk_grab_add(widget);bar->down_x=x;bar->down_y=y;bar->down_modifiers=modifiers(state);
    bar->moved=bar->released=FALSE;
    bar->source=g_idle_add_full(G_PRIORITY_DEFAULT_IDLE,begin_tracking,bar,NULL);
    return TRUE;
  }
  return FALSE;
}
static void placement(GtkWidget *widget) {
  GtkScrolledWindow *window=GTK_SCROLLED_WINDOW(widget);
  GtkCornerType corner=gtk_widget_get_direction(widget)==GTK_TEXT_DIR_RTL?GTK_CORNER_TOP_LEFT:GTK_CORNER_TOP_RIGHT;
  if(gtk_scrolled_window_get_placement(window)!=corner) gtk_scrolled_window_set_placement(window,corner);
  if(gtk_scrolled_window_get_overlay_scrolling(window)) gtk_scrolled_window_set_overlay_scrolling(window,FALSE);
}
static void settings_changed(GObject *object,GParamSpec *property,gpointer data) {placement(GTK_WIDGET(object));}
static void direction_changed(GtkWidget *widget,GtkTextDirection previous,gpointer data) {placement(widget);}
static gboolean observe_context(gpointer data)
{
  GtkWidget *widget=data;
  if (gtk_widget_get_mapped(widget))
    nextspace_gtk3_observe_context_parent(gtk_widget_get_window(widget));
  return G_SOURCE_REMOVE;
}
static gboolean mapped(GSignalInvocationHint *hint,guint count,const GValue *values,gpointer unused) {
  GtkWidget *widget=g_value_get_object(values);
  nextspace_gtk3_attach_control(widget);
  nextspace_gtk3_attach_menu(widget);
  nextspace_gtk_attach_editing(widget);
  if (GTK_IS_WINDOW(widget) && gtk_window_get_window_type(GTK_WINDOW(widget)) == GTK_WINDOW_TOPLEVEL)
    g_idle_add_full(G_PRIORITY_DEFAULT_IDLE, observe_context, g_object_ref(widget), g_object_unref);
  if(g_strcmp0(g_getenv("NEXTSPACE_SCROLLBARS"),"off")==0) return TRUE;
  if(g_object_get_data(G_OBJECT(widget),"nextspace-original-control")) return TRUE;
  if(GTK_IS_SCROLLED_WINDOW(widget)) {
    placement(widget);
    if(!g_object_get_data(G_OBJECT(widget),"nextspace-scroller-placement")) {
      g_object_set_data(G_OBJECT(widget),"nextspace-scroller-placement",GINT_TO_POINTER(1));
      g_signal_connect(widget,"notify::window-placement",G_CALLBACK(settings_changed),NULL);
      g_signal_connect(widget,"notify::overlay-scrolling",G_CALLBACK(settings_changed),NULL);
      g_signal_connect(widget,"direction-changed",G_CALLBACK(direction_changed),NULL);
    }
  }
  if(GTK_IS_SCROLLBAR(widget)&&!g_object_get_data(G_OBJECT(widget),"nextspace-native-scroller")) {
    NativeBar *bar=g_new0(NativeBar,1);bar->widget=widget;
    gboolean horizontal=gtk_orientable_get_orientation(GTK_ORIENTABLE(widget))==GTK_ORIENTATION_HORIZONTAL;
    bar->native=nxs_scroller_create(horizontal,changed,pump,bar);
    if(!bar->native) {g_free(bar);return TRUE;}
    g_object_set_data_full(G_OBJECT(widget),"nextspace-native-scroller",bar,free_bar);
    bind_adjustment(G_OBJECT(widget),NULL,bar);
    g_signal_connect(widget,"notify::adjustment",G_CALLBACK(bind_adjustment),bar);
    g_signal_connect(widget,"unmap",G_CALLBACK(unmapped),bar);
    int width=(int)lround(nxs_scroller_width());
    gtk_widget_set_size_request(widget,horizontal?-1:width,horizontal?width:-1);
    GtkCssProvider *css=gtk_css_provider_new();
    gtk_css_provider_load_from_data(css,"* { min-width: 0; min-height: 0; padding: 0; margin: 0; border: 0; }",-1,NULL);
    gtk_style_context_add_provider(gtk_widget_get_style_context(widget),GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_USER);
    g_object_unref(css);
    gtk_widget_add_events(widget,GDK_BUTTON_PRESS_MASK|GDK_BUTTON_RELEASE_MASK|GDK_POINTER_MOTION_MASK);
    g_signal_connect(widget,"button-press-event",G_CALLBACK(input),bar);
    g_signal_connect(widget,"button-release-event",G_CALLBACK(input),bar);
    g_signal_connect(widget,"motion-notify-event",G_CALLBACK(input),bar);
  }
  return TRUE;
}
void nextspace_gtk3_scrollbars_init(void) {
  static gboolean initialized;
  if(initialized) return;
  initialized=TRUE;GtkWidgetClass *klass=g_type_class_ref(GTK_TYPE_SCROLLBAR);
  original_draw=klass->draw;klass->draw=draw;
  g_signal_add_emission_hook(g_signal_lookup("map",GTK_TYPE_WIDGET),0,mapped,NULL,NULL);
}
/* GTK3's normal module loader also supports the adapter without LD_PRELOAD. */
void gtk_module_init(gint *argc,gchar ***argv) {nextspace_gtk3_scrollbars_init();}
