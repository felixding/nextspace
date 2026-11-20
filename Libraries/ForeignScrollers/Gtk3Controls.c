/* Host ordinary GTK buttons using GNUstep drawing.
 * GTK keeps its event, action and accessibility objects. GPL-2.0-or-later. */
#include "../NativeUI/NativeUI.h"
#include <gtk/gtk.h>

static void dispose_button(gpointer data)
{
  nxs_control_destroy(data);
}

static int button_kind(GtkWidget *widget)
{
  if (!GTK_IS_BUTTON(widget))
    return 0;
  int requested = GPOINTER_TO_INT(g_object_get_data(G_OBJECT(widget), "nextspace-control-kind"));
  if (requested == NXS_BUTTON)
    return requested;
  if (GTK_IS_TOGGLE_BUTTON(widget) && (requested == NXS_CHECKBOX || requested == NXS_RADIO))
    return requested;
  GType type = G_OBJECT_TYPE(widget);
  if (type == GTK_TYPE_BUTTON) return NXS_BUTTON;
  if (type == GTK_TYPE_CHECK_BUTTON) return NXS_CHECKBOX;
  if (type == GTK_TYPE_RADIO_BUTTON) return NXS_RADIO;
  return 0;
}

static NXSControl *sync_button(GtkWidget *widget, double width, double height)
{
  if (g_object_get_data(G_OBJECT(widget), "nextspace-original-control") ||
      gtk_widget_get_direction(widget) == GTK_TEXT_DIR_RTL ||
      gtk_button_get_image(GTK_BUTTON(widget)) ||
      gtk_button_get_relief(GTK_BUTTON(widget)) == GTK_RELIEF_NONE ||
      gtk_style_context_has_class(gtk_widget_get_style_context(widget), GTK_STYLE_CLASS_SUGGESTED_ACTION) ||
      gtk_style_context_has_class(gtk_widget_get_style_context(widget), GTK_STYLE_CLASS_DESTRUCTIVE_ACTION))
    return NULL;

  int kind = button_kind(widget);
  if (!kind)
    return NULL;
  GtkWidget *child = gtk_bin_get_child(GTK_BIN(widget));
  if (!GTK_IS_LABEL(child) || gtk_label_get_use_markup(GTK_LABEL(child)))
    return NULL;

  NXSControl *control = g_object_get_data(G_OBJECT(widget), "nextspace-native-button");
  if (!control) {
    control = nxs_control_create(kind, NULL, NULL, NULL);
    if (!control)
      return NULL;
    g_object_set_data_full(G_OBJECT(widget), "nextspace-native-button", control, dispose_button);
  }
  int state = 0;
  if (kind != NXS_BUTTON)
    state = gtk_toggle_button_get_inconsistent(GTK_TOGGLE_BUTTON(widget)) ? -1 :
        gtk_toggle_button_get_active(GTK_TOGGLE_BUTTON(widget));
  NXSControlConfig config = {
    .size = sizeof(config), .width = width, .height = height,
    .enabled = gtk_widget_is_sensitive(widget), .state = state,
    .title = gtk_label_get_text(GTK_LABEL(child))
  };
  return nxs_control_sync(control, &config) ? control : NULL;
}

static gboolean draw(GtkWidget *widget, cairo_t *cr, gpointer unused)
{
  if (gtk_widget_get_state_flags(widget) & GTK_STATE_FLAG_ACTIVE)
    return FALSE;
  NXSControl *control = sync_button(widget, gtk_widget_get_allocated_width(widget),
                                   gtk_widget_get_allocated_height(widget));
  if (!control)
    return FALSE;
  nxs_control_focus(control, gtk_widget_has_visible_focus(widget));
  double scale = gtk_widget_get_scale_factor(widget);
  NXSBitmap bitmap = nxs_control_draw(control, scale);
  if (!bitmap.pixels)
    return FALSE;
  cairo_surface_t *surface = cairo_image_surface_create_for_data((unsigned char *)bitmap.pixels,
      CAIRO_FORMAT_ARGB32, bitmap.width, bitmap.height, bitmap.stride);
  cairo_surface_set_device_scale(surface, scale, scale);
  cairo_save(cr);
  cairo_set_source_surface(cr, surface, 0, 0);
  cairo_paint(cr);
  cairo_restore(cr);
  cairo_surface_destroy(surface);
  return TRUE;
}

void nextspace_gtk3_attach_control(GtkWidget *widget)
{
  if (g_strcmp0(g_getenv("NEXTSPACE_NATIVE_CONTROLS"), "off") == 0 ||
      g_object_get_data(G_OBJECT(widget), "nextspace-control-attached"))
    return;
  if (!button_kind(widget))
    return;
  g_object_set_data(G_OBJECT(widget), "nextspace-control-attached", GINT_TO_POINTER(1));
  g_signal_connect(widget, "draw", G_CALLBACK(draw), NULL);
}
