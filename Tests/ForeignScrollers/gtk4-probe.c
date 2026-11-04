/* An ordinary GTK app: it neither links nor calls the adapter. GPL-2.0-or-later. */
#include <gtk/gtk.h>
#include <glib-unix.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <math.h>
static GtkWidget *window, *scroll, *content;
static GMainLoop *loop;
static GtkApplication *application_instance;
static gboolean ready;
static unsigned ticks;
static gboolean tick(GtkWidget *widget,GdkFrameClock *clock,gpointer data) {ticks++;return G_SOURCE_CONTINUE;}
static void report(void) {
  GtkAdjustment *adjustment=gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(scroll));
  GtkWidget *bar=gtk_scrolled_window_get_vscrollbar(GTK_SCROLLED_WINDOW(scroll));
  double x,y,width,height,scale;
#if GTK_MAJOR_VERSION == 4
  graphene_rect_t bounds;
  if(!gtk_widget_compute_bounds(bar,window,&bounds)) return;
  x=bounds.origin.x;y=bounds.origin.y;width=bounds.size.width;height=bounds.size.height;
  scale=gdk_surface_get_scale(gtk_native_get_surface(gtk_widget_get_native(bar)));
#else
  int bx,by;gtk_widget_translate_coordinates(bar,window,0,0,&bx,&by);
  x=bx;y=by;width=gtk_widget_get_allocated_width(bar);height=gtk_widget_get_allocated_height(bar);
  scale=gtk_widget_get_scale_factor(bar);
#endif
  printf("{\"event\":\"state\",\"ready\":%s,\"ticks\":%u,\"value\":%g,\"minimum\":%g,\"maximum\":%g,\"page\":%g,\"step\":%g,\"bar\":[%g,%g,%g,%g],\"direction\":%d,\"scale\":%g,\"native\":%s}\n",ready?"true":"false",ticks,
    gtk_adjustment_get_value(adjustment),gtk_adjustment_get_lower(adjustment),
    gtk_adjustment_get_upper(adjustment)-gtk_adjustment_get_page_size(adjustment),
    gtk_adjustment_get_page_size(adjustment),gtk_adjustment_get_step_increment(adjustment),
    x,y,width,height,
    gtk_widget_get_direction(content),scale,g_object_get_data(G_OBJECT(bar),"nextspace-native-scroller")?"true":"false");
  fflush(stdout);
}
static gboolean later(gpointer data) { report();puts("{\"event\":\"done\"}");fflush(stdout);return G_SOURCE_REMOVE; }
static void changed(GtkAdjustment *adjustment, gpointer data) { report(); }
static gboolean capture(GtkWidget *widget,const char *path) {
#if GTK_MAJOR_VERSION == 4
  GdkPaintable *paintable=gtk_widget_paintable_new(widget);
  GtkSnapshot *snapshot=gtk_snapshot_new();
  double scale=gdk_surface_get_scale(gtk_native_get_surface(gtk_widget_get_native(widget)));
  gtk_snapshot_scale(snapshot,scale,scale);
  gdk_paintable_snapshot(paintable,GDK_SNAPSHOT(snapshot),gtk_widget_get_width(widget),gtk_widget_get_height(widget));
  GskRenderNode *node=gtk_snapshot_free_to_node(snapshot);
  if(node) {
    graphene_rect_t bounds=GRAPHENE_RECT_INIT(0,0,ceil(gtk_widget_get_width(widget)*scale),ceil(gtk_widget_get_height(widget)*scale));
    GdkTexture *texture=gsk_renderer_render_texture(gtk_native_get_renderer(gtk_widget_get_native(widget)),node,&bounds);
    gdk_texture_save_to_png(texture,path); g_object_unref(texture); gsk_render_node_unref(node);
  }
  g_object_unref(paintable);
  return node!=NULL;
#else
  /* Process pending size requests before GTK3's synchronous draw API. */
  gtk_container_check_resize(GTK_CONTAINER(window));
  int scale=gtk_widget_get_scale_factor(widget);
  cairo_surface_t *surface=cairo_image_surface_create(CAIRO_FORMAT_ARGB32,gtk_widget_get_allocated_width(widget)*scale,gtk_widget_get_allocated_height(widget)*scale);
  cairo_t *cr=cairo_create(surface);cairo_scale(cr,scale,scale);gtk_widget_draw(widget,cr);cairo_surface_write_to_png(surface,path);
  cairo_destroy(cr);cairo_surface_destroy(surface);
  return TRUE;
#endif
}
static gboolean capture_ready(gpointer data) {
  char bar_path[1000];snprintf(bar_path,sizeof(bar_path),"%s.bar.png",(char *)data);
  if(!capture(window,data)||!capture(gtk_scrolled_window_get_vscrollbar(GTK_SCROLLED_WINDOW(scroll)),bar_path)) return G_SOURCE_CONTINUE;
  report();puts("{\"event\":\"done\"}");fflush(stdout);return G_SOURCE_REMOVE;
}
static gboolean input(gint fd,GIOCondition condition,gpointer data) {
  char buffer[1024],path[900]; int a,b;
  if(!fgets(buffer,sizeof(buffer),stdin)) { g_main_loop_quit(loop); return G_SOURCE_REMOVE; }
  if(!strncmp(buffer,"quit",4)) {
    gtk_widget_set_visible(window,FALSE);
    if(application_instance) g_application_quit(G_APPLICATION(application_instance));else g_main_loop_quit(loop);
  }
  else if(sscanf(buffer,"resize %d %d",&a,&b)==2) {
#if GTK_MAJOR_VERSION == 4
    gtk_window_set_default_size(GTK_WINDOW(window),a,b);
#else
    gtk_window_resize(GTK_WINDOW(window),a,b);
#endif
  }
  else if(sscanf(buffer,"value %d",&a)==1) gtk_adjustment_set_value(gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(scroll)),a);
  else if(!strncmp(buffer,"rtl",3)) gtk_widget_set_direction(scroll,GTK_TEXT_DIR_RTL);
  else if(sscanf(buffer,"capture %899s",path)==1) {
    g_timeout_add_full(G_PRIORITY_DEFAULT,10,capture_ready,g_strdup(path),g_free);
    return G_SOURCE_CONTINUE;
  }
  g_timeout_add(80,later,NULL); return G_SOURCE_CONTINUE;
}
static gboolean initial(gpointer data) {
  ready=TRUE;
  gtk_adjustment_set_value(gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(scroll)),300);
  report();return G_SOURCE_REMOVE;
}
static void activate(GtkApplication *application,gpointer data) {
#if GTK_MAJOR_VERSION == 4
  window=application?gtk_application_window_new(application):gtk_window_new();
#else
  window=application?gtk_application_window_new(application):gtk_window_new(GTK_WINDOW_TOPLEVEL);
#endif
  gtk_window_set_title(GTK_WINDOW(window),"ForeignScrollerGtk");gtk_window_set_default_size(GTK_WINDOW(window),480,360);
  gtk_window_set_decorated(GTK_WINDOW(window),FALSE);
#if GTK_MAJOR_VERSION == 4
  scroll=gtk_scrolled_window_new();
#else
  scroll=gtk_scrolled_window_new(NULL,NULL);
#endif
  content=gtk_label_new("Left to right content");
  gtk_label_set_xalign(GTK_LABEL(content),0);gtk_label_set_yalign(GTK_LABEL(content),0);
  gtk_widget_set_size_request(content,900,1200);
#if GTK_MAJOR_VERSION == 4
  gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll),content);gtk_window_set_child(GTK_WINDOW(window),scroll);
#else
  gtk_container_add(GTK_CONTAINER(scroll),content);gtk_container_add(GTK_CONTAINER(window),scroll);gtk_widget_show_all(window);
#endif
  gtk_window_present(GTK_WINDOW(window));
  gtk_widget_add_tick_callback(window,tick,NULL,NULL);
  g_signal_connect(gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(scroll)),"value-changed",G_CALLBACK(changed),NULL);
  g_timeout_add(200,initial,NULL);g_unix_fd_add(STDIN_FILENO,G_IO_IN,input,NULL);
}
int main(int argc,char **argv) {
  loop=g_main_loop_new(NULL,FALSE);
  if(g_getenv("PROBE_APPLICATION")) {
    GtkApplication *application=gtk_application_new("org.nextspace.ForeignScrollerProbe",G_APPLICATION_NON_UNIQUE);
    application_instance=application;
    g_signal_connect(application,"activate",G_CALLBACK(activate),NULL);
    /* Tests use stdin to close the window explicitly. */
    g_application_run(G_APPLICATION(application),argc,argv);g_object_unref(application);
  } else {
#if GTK_MAJOR_VERSION == 4
    gtk_init();
#else
    gtk_init(&argc,&argv);
#endif
    activate(NULL,NULL);g_main_loop_run(loop);
  }
  if(window) {
#if GTK_MAJOR_VERSION == 4
    gtk_window_destroy(GTK_WINDOW(window));
#else
    gtk_widget_destroy(window);
#endif
  }
  g_main_loop_unref(loop);return 0;
}
