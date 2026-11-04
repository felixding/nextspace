/* Negotiated NeXT-style server frames in logical coordinates. MIT license. */
#include <cairo.h>
#include <pango/pangocairo.h>
#include "title-text.h"
#include "title-font.h"
#include <wlr/interfaces/wlr_buffer.h>
#include "xdg-decoration-unstable-v1-server-protocol.h"
#include "title-controls.h"

enum decoration_part { DECORATION_NONE, DECORATION_TITLE, DECORATION_MINIMIZE,
  DECORATION_CLOSE, DECORATION_LEFT, DECORATION_RIGHT, DECORATION_BOTTOM,
  DECORATION_BOTTOM_LEFT, DECORATION_BOTTOM_RIGHT, DECORATION_TOP };

struct decoration_buffer {
  struct wlr_buffer base;
  cairo_surface_t *image;
};

struct nextspace_decoration {
  struct nextspace_toplevel *view;
  struct wlr_xdg_toplevel_decoration_v1 *protocol;
  struct wl_listener request, destroy, outputs_update, buffer_destroy;
  struct wlr_scene_buffer *content, *title;
  struct wlr_scene_tree *tree;
  struct wlr_scene_rect *left, *right, *bottom, *grooves[2], *selection[3];
  struct wl_event_source *idle;
  char *text;
  int width, height, scale;
  bool edited, selected;
  unsigned pressed, style, title_state;
  uint32_t title_revision;
};

static void decoration_buffer_destroy(struct wlr_buffer *buffer)
{
  struct decoration_buffer *frame = wl_container_of(buffer, frame, base);
  cairo_surface_destroy(frame->image);
  free(frame);
}

static bool decoration_buffer_access(struct wlr_buffer *buffer, uint32_t flags,
    void **data, uint32_t *format, size_t *stride)
{
  if (flags & WLR_BUFFER_DATA_PTR_ACCESS_WRITE) return false;
  struct decoration_buffer *frame = wl_container_of(buffer, frame, base);
  *data = cairo_image_surface_get_data(frame->image);
  *format = DRM_FORMAT_ARGB8888;
  *stride = cairo_image_surface_get_stride(frame->image);
  return true;
}

static void decoration_buffer_end(struct wlr_buffer *buffer) {}
static const struct wlr_buffer_impl decoration_buffer_impl = {
  .destroy = decoration_buffer_destroy,
  .begin_data_ptr_access = decoration_buffer_access,
  .end_data_ptr_access = decoration_buffer_end,
};

static void decoration_fill(cairo_t *cr, double gray, int x, int y, int width, int height)
{
  cairo_set_source_rgb(cr, gray, gray, gray);
  cairo_rectangle(cr, x, y, width, height);
  cairo_fill(cr);
}

static void decoration_fill_scaled(cairo_t *cr, double gray, int x, int y, int width, int height, int scale)
{
  int left = ns_scale_edge(x, scale), top = ns_scale_edge(y, scale);
  decoration_fill(cr, gray, left, top, ns_scale_edge(x + width, scale) - left,
    ns_scale_edge(y + height, scale) - top);
}

static void decoration_draw_button(cairo_t *cr, int x, int y, bool close, bool pressed,
    bool edited, int scale)
{
  cairo_save(cr);
  cairo_identity_matrix(cr);
  /* Match the AppKit 15-unit control, including its 14-unit visible bezel. */
  decoration_fill_scaled(cr, 2. / 3, x, y, 14, 14, scale);
  decoration_fill_scaled(cr, 1, x, y, 14, 1, scale);
  decoration_fill_scaled(cr, 1, x, y, 1, 14, scale);
  decoration_fill_scaled(cr, 1. / 3, x + 1, y + 13, 13, 1, scale);
  decoration_fill_scaled(cr, 1. / 3, x + 13, y + 1, 1, 12, scale);
  const struct decoration_glyph *glyph = close ?
    (edited ? (pressed ? &common_closebrokenh : &common_closebroken) :
      (pressed ? &common_closeh : &common_close)) :
    (pressed ? &common_miniaturizeh : &common_miniaturize);
  decoration_draw_glyph(cr, glyph, x + 1, y + 1, scale);
  cairo_restore(cr);
}

static unsigned decoration_style(struct nextspace_toplevel *view)
{ return view->has_metadata ? view->style : 15; }

static uint32_t decoration_title_state(struct nextspace_toplevel *view)
{
  struct nextspace_toplevel *focused = view_for_surface(view->server,
    view->server->seat->keyboard_state.focused_surface);
  if (focused == view) return NEXTSPACE_WINDOW_V1_TITLE_STATE_KEY;
  if (focused && view->application_window &&
      view->application_window->title_state == NEXTSPACE_WINDOW_V1_TITLE_STATE_MAIN &&
      wl_resource_get_client(view_surface(focused)->resource) == wl_resource_get_client(view_surface(view)->resource))
    return NEXTSPACE_WINDOW_V1_TITLE_STATE_MAIN;
  return NEXTSPACE_WINDOW_V1_TITLE_STATE_NORMAL;
}

static struct decoration_buffer *decoration_render(struct nextspace_decoration *frame,
    int width, int logical_height, int scale, const char *text, uint32_t state, unsigned pressed,
    unsigned style, bool edited, bool selected)
{
  struct decoration_buffer *buffer = calloc(1, sizeof(*buffer));
  if (!buffer) return NULL;
  int pixels = (width * scale + 60) / 120;
  int height = ns_buffer_extent(logical_height, scale);
  buffer->image = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, pixels, height);
  if (cairo_surface_status(buffer->image) != CAIRO_STATUS_SUCCESS) {
    cairo_surface_destroy(buffer->image); free(buffer); return NULL;
  }
  cairo_t *cr = cairo_create(buffer->image);
  decoration_fill_scaled(cr, 0, 0, 0, width, logical_height, scale);
  if (selected) decoration_fill_scaled(cr, 1, 0, 0, width, 1, scale);
  if (logical_height > 2) {
    double gray = state == NEXTSPACE_WINDOW_V1_TITLE_STATE_KEY ? 0 :
      state == NEXTSPACE_WINDOW_V1_TITLE_STATE_MAIN ? 1. / 3 : 2. / 3;
    double light = state == NEXTSPACE_WINDOW_V1_TITLE_STATE_NORMAL ? 1 : 2. / 3;
    double dark = state == NEXTSPACE_WINDOW_V1_TITLE_STATE_MAIN ? 0 : 1. / 3;
    decoration_fill_scaled(cr, light, 1, 1, 1, logical_height - 2, scale);
    decoration_fill_scaled(cr, light, 2, 1, width - 3, 1, scale);
    decoration_fill_scaled(cr, dark, width - 2, 2, 1, logical_height - 3, scale);
    decoration_fill_scaled(cr, dark, 2, logical_height - 2, width - 4, 1, scale);
    decoration_fill_scaled(cr, gray, 2, 2, width - 4, logical_height - 4, scale);
  }
  cairo_scale(cr, scale / 120.0, scale / 120.0);
  bool buttons = logical_height >= 20;
  if (buttons && (style & 4)) decoration_draw_button(cr, 4, 4, false,
    pressed == DECORATION_MINIMIZE, false, scale);
  if (buttons && (style & 2)) decoration_draw_button(cr, width - 19, 4, true,
    pressed == DECORATION_CLOSE, edited, scale);
  int text_left = buttons && (style & 4) ? 23 : 3;
  int text_right = buttons && (style & 2) ? 23 : 3;
  if ((style & 1) && width > text_left + text_right && logical_height > 2) {
    cairo_rectangle(cr, text_left, 2, width - text_left - text_right, logical_height - 4);
    cairo_clip(cr);
    double text_gray = state == NEXTSPACE_WINDOW_V1_TITLE_STATE_NORMAL ? 0 : 1;
    cairo_set_source_rgb(cr, text_gray, text_gray, text_gray);
    int available = width - text_left - text_right;
    struct nextspace_server *server = frame->view->server;
    PangoLayout *layout = title_text_layout(cr, text, available,
      server->title_font->description, server->title_font->antialiased, server->title_font->map, server->title_font->options);
    int text_width, text_height;
    title_text_size(layout, &text_width, &text_height);
    int x = server->title_justification == NEXTSPACE_SHELL_V1_TITLE_JUSTIFICATION_LEFT ? text_left :
      server->title_justification == NEXTSPACE_SHELL_V1_TITLE_JUSTIFICATION_RIGHT ? width - text_right - text_width :
      text_left + (available - text_width) / 2;
    /* Match the legacy titlebar's integer baseline inside its one-unit border. */
    cairo_move_to(cr, x, 1 + (logical_height - 1 - text_height) / 2);
    title_text_draw(cr, layout);
    g_object_unref(layout);
  }
  cairo_destroy(cr);
  cairo_surface_flush(buffer->image);
  wlr_buffer_init(&buffer->base, &decoration_buffer_impl, pixels, height);
  const char *directory = getenv("NEXTSPACE_COMPOSITOR_CAPTURE_DIR");
  if (directory) {
    char *path = NULL;
    if (asprintf(&path, "%s/frame-%u-%d.png", directory, frame->view->id, scale) >= 0) {
      cairo_surface_write_to_png(buffer->image, path);
      free(path);
    }
  }
  return buffer;
}

static void decoration_unwatch(struct nextspace_decoration *frame)
{
  if (!frame->content) return;
  wl_list_remove(&frame->outputs_update.link);
  wl_list_remove(&frame->buffer_destroy.link);
  frame->content = NULL;
}

static void decoration_content_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_decoration *frame = wl_container_of(listener, frame, buffer_destroy);
  decoration_unwatch(frame);
}

static void decoration_idle(void *data)
{
  struct nextspace_decoration *frame = data;
  frame->idle = NULL;
  decoration_update(frame->view);
}

static void decoration_outputs_update(struct wl_listener *listener, void *data)
{
  struct nextspace_decoration *frame = wl_container_of(listener, frame, outputs_update);
  if (!frame->idle) frame->idle = wl_event_loop_add_idle(
    wl_display_get_event_loop(frame->view->server->wl_display), decoration_idle, frame);
}

static void decoration_update(struct nextspace_toplevel *view)
{
  struct nextspace_decoration *frame = view->decoration;
  if (!frame) return;
  bool visible = decoration_visible(view);
  wlr_scene_node_set_enabled(&frame->tree->node, visible);
  wlr_scene_node_set_position(&view->content_tree->node,
    visible ? view->frame.left : 0, visible ? view->frame.top : 0);
  if (!visible) return;
  if (!frame->content && view->mapped && (frame->content = view_buffer(view))) {
    frame->outputs_update.notify = decoration_outputs_update;
    wl_signal_add(&frame->content->events.outputs_update, &frame->outputs_update);
    frame->buffer_destroy.notify = decoration_content_destroy;
    wl_signal_add(&frame->content->node.events.destroy, &frame->buffer_destroy);
  }
  struct wlr_box geometry;
  view_geometry(view, &geometry);
  int width = geometry.width, height = geometry.height;
  struct ns_frame_extents insets = view->frame;
  int scale = frame->content && frame->content->primary_output ?
    lroundf(frame->content->primary_output->output->scale * 120) : 120;
  uint32_t state = decoration_title_state(view);
  unsigned pressed = view->server->decoration_pressed == view ? view->server->decoration_button : 0;
  unsigned style = decoration_style(view);
  const char *text = view_title(view);
  if (!text) text = "";
  wlr_scene_node_set_enabled(&frame->title->node, insets.top > 0);
  if (insets.top > 0 && (width != frame->width || insets.top != frame->height ||
      style != frame->style || scale != frame->scale || state != frame->title_state ||
      view->server->title_revision != frame->title_revision ||
      view->document_edited != frame->edited ||
      view->selected != frame->selected ||
      pressed != frame->pressed || !frame->text || strcmp(text, frame->text))) {
    struct decoration_buffer *buffer = decoration_render(frame, width, insets.top, scale, text,
      state, pressed, style, view->document_edited, view->selected);
    if (buffer) {
      wlr_scene_buffer_set_buffer(frame->title, &buffer->base);
      wlr_scene_buffer_set_dest_size(frame->title, width, insets.top);
      wlr_buffer_drop(&buffer->base);
      frame->width = width; frame->scale = scale; frame->title_state = state; frame->pressed = pressed;
      frame->height = insets.top; frame->style = style;
      frame->title_revision = view->server->title_revision;
      frame->edited = view->document_edited;
      frame->selected = view->selected;
      free(frame->text); frame->text = strdup(text);
    }
  }
  wlr_scene_rect_set_size(frame->left, insets.left, height - insets.top);
  wlr_scene_node_set_position(&frame->left->node, 0, insets.top);
  wlr_scene_rect_set_size(frame->right, insets.right, height - insets.top);
  wlr_scene_node_set_position(&frame->right->node, width - insets.right, insets.top);
  wlr_scene_rect_set_size(frame->bottom, width - insets.left - insets.right, insets.bottom);
  wlr_scene_node_set_position(&frame->bottom->node, insets.left, height - insets.bottom);
  int visible_height = view->shaded ? insets.top : height;
  for (int n = 0; n < 3; n++) {
    wlr_scene_node_set_enabled(&frame->selection[n]->node, view->selected);
    wlr_scene_rect_set_size(frame->selection[n], n == 2 ? width : 1, n == 2 ? 1 : visible_height);
    wlr_scene_node_set_position(&frame->selection[n]->node, n == 1 ? width - 1 : 0,
      n == 2 ? visible_height - 1 : 0);
  }
  for (int n = 0; n < 2; n++) {
    wlr_scene_rect_set_size(frame->grooves[n], 1, insets.bottom);
    wlr_scene_node_set_position(&frame->grooves[n]->node, n ? width - 29 : 28, height - insets.bottom);
    wlr_scene_node_set_enabled(&frame->grooves[n]->node, width >= 58 && insets.bottom > 1 &&
      (style & 8) && !view->shaded);
  }
  wlr_scene_node_set_enabled(&frame->left->node, insets.left > 0 && !view->shaded);
  wlr_scene_node_set_enabled(&frame->right->node, insets.right > 0 && !view->shaded);
  wlr_scene_node_set_enabled(&frame->bottom->node, insets.bottom > 0 && !view->shaded);
}

static void decoration_update_all(struct nextspace_server *server)
{
  /* A main title depends on a sibling's focus, even if its client is stopped. */
  struct nextspace_toplevel *view;
  wl_list_for_each(view, &server->toplevels, link) decoration_update(view);
}

static void decoration_set_title_appearance(struct nextspace_server *server,
    const char *font, uint32_t antialiased, uint32_t justification)
{
  if (antialiased > 1 || justification > NEXTSPACE_SHELL_V1_TITLE_JUSTIFICATION_RIGHT) return;
  struct title_font *selected = title_font_create(font, antialiased);
  if (!selected) return;
  if (FcPatternEqual(selected->pattern, server->title_font->pattern) && justification == server->title_justification) {
    title_font_destroy(selected); return;
  }
  title_font_destroy(server->title_font);
  server->title_font = selected;
  server->title_justification = justification;
  server->title_revision++;
  decoration_update_all(server);
}

static void decoration_commit(struct nextspace_toplevel *view)
{
  struct nextspace_decoration *frame = view->decoration;
  if (!frame) return;
  bool enabled = frame->protocol && frame->protocol->current.mode == WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE;
  if (enabled != view->server_decorated || view->frame_pending) {
    struct ns_frame_extents old = view->server_decorated ? view->frame : (struct ns_frame_extents){0};
    if (view->server->decoration_pressed == view) reset_cursor_mode(view->server);
    if (view->frame_pending) { view->frame = view->pending_frame; view->frame_pending = false; }
    struct ns_frame_extents next = enabled ? view->frame : (struct ns_frame_extents){0};
    if (view->normal_geometry.width > 0 && (view->maximized || view->fullscreen)) {
      view->normal_geometry.width += ns_frame_horizontal(next) - ns_frame_horizontal(old);
      view->normal_geometry.height += ns_frame_vertical(next) - ns_frame_vertical(old);
    }
    view->server_decorated = enabled;
    view->title_height = enabled ? view->frame.top : view->client_title_height;
    if (!enabled || !view->frame.top) view->shaded = false;
    wlr_scene_subsurface_tree_set_clip(&view->content_tree->node, NULL);
    wlr_scene_node_set_enabled(&view->content_tree->node, !view->shaded);
    policy_update_clip(view);
    policy_size_geometry(view);
  }
  decoration_update(view);
}

static void decoration_request(struct wl_listener *listener, void *data)
{
  struct nextspace_decoration *frame = wl_container_of(listener, frame, request);
  enum wlr_xdg_toplevel_decoration_v1_mode mode = frame->protocol->requested_mode;
  if (mode != WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_NONE &&
      mode != WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_CLIENT_SIDE &&
      mode != WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE) {
    wl_resource_post_error(frame->protocol->resource, ZXDG_TOPLEVEL_DECORATION_V1_ERROR_INVALID_MODE,
      "Invalid decoration mode"); return;
  }
  if (!frame->protocol->toplevel->base->initialized) return;
  wlr_xdg_toplevel_decoration_v1_set_mode(frame->protocol,
    mode == WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_CLIENT_SIDE ? mode : WLR_XDG_TOPLEVEL_DECORATION_V1_MODE_SERVER_SIDE);
}

static void decoration_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_decoration *frame = wl_container_of(listener, frame, destroy);
  wl_list_remove(&frame->request.link);
  wl_list_remove(&frame->destroy.link);
  frame->protocol = NULL;
  /* The protocol removes the frame at the client's next surface commit. */
}

static void decoration_finish(struct nextspace_toplevel *view)
{
  struct nextspace_decoration *frame = view->decoration;
  if (!frame) return;
  if (view->server->decoration_pressed == view) {
    view->server->decoration_pressed = NULL;
    view->server->decoration_button = 0;
  }
  if (frame->idle) wl_event_source_remove(frame->idle);
  decoration_unwatch(frame);
  if (frame->protocol) decoration_destroy(&frame->destroy, NULL);
  free(frame->text);
  free(frame);
  view->decoration = NULL;
}

static void decoration_new(struct wl_listener *listener, void *data)
{
  struct wlr_xdg_toplevel_decoration_v1 *protocol = data;
  struct nextspace_server *server = wl_container_of(listener, server, new_decoration);
  struct nextspace_toplevel *view = view_for_surface(server, protocol->toplevel->base->surface);
  /* Unmapped toplevels have not joined the managed list yet. */
  if (!view && protocol->toplevel->base->data) {
    struct wlr_scene_tree *tree = protocol->toplevel->base->data;
    view = tree->node.data;
  }
  if (!view) return;
  struct nextspace_decoration *frame = view->decoration;
  if (!frame) {
    frame = calloc(1, sizeof(*frame));
    if (!frame) { wl_client_post_no_memory(wl_resource_get_client(protocol->resource)); return; }
    view->decoration = frame;
    frame->view = view;
    frame->tree = wlr_scene_tree_create(view->scene_tree);
    frame->title = wlr_scene_buffer_create(frame->tree, NULL);
    const float black[] = {0, 0, 0, 1}, gray[] = {.67, .67, .67, 1};
    frame->left = wlr_scene_rect_create(frame->tree, 1, 1, black);
    frame->right = wlr_scene_rect_create(frame->tree, 1, 1, black);
    frame->bottom = wlr_scene_rect_create(frame->tree, 1, 9, gray);
    for (int n = 0; n < 2; n++) frame->grooves[n] = wlr_scene_rect_create(frame->tree, 1, 9, black);
    const float white[] = {1, 1, 1, 1};
    for (int n = 0; n < 3; n++) frame->selection[n] = wlr_scene_rect_create(frame->tree, 1, 1, white);
    wlr_scene_node_set_enabled(&frame->tree->node, false);
  }
  frame->protocol = protocol;
  frame->request.notify = decoration_request;
  frame->destroy.notify = decoration_destroy;
  wl_signal_add(&protocol->events.request_mode, &frame->request);
  wl_signal_add(&protocol->events.destroy, &frame->destroy);
  decoration_request(&frame->request, NULL);
}

static unsigned decoration_part_at(struct nextspace_toplevel *view)
{
  if (!view || !decoration_visible(view)) return DECORATION_NONE;
  int x = view->server->cursor->x - view->scene_tree->node.x;
  int y = view->server->cursor->y - view->scene_tree->node.y;
  struct wlr_box box;
  view_geometry(view, &box);
  struct ns_frame_extents insets = view->frame;
  unsigned style = decoration_style(view);
  if (x < 0 || x >= box.width || y < 0 || y >= (view->shaded ? insets.top : box.height)) return DECORATION_NONE;
  if (y < insets.top) {
    if (insets.top >= 20 && y >= 4 && y < 19) {
      if ((style & 4) && x >= 4 && x < 19) return DECORATION_MINIMIZE;
      if ((style & 2) && x >= box.width - 19 && x < box.width - 4) return DECORATION_CLOSE;
    }
    return y < 2 && !view->shaded && (style & 8) ? DECORATION_TOP : DECORATION_TITLE;
  }
  if (!(style & 8)) return DECORATION_NONE;
  if (y >= box.height - insets.bottom)
    return x < 29 ? DECORATION_BOTTOM_LEFT : x >= box.width - 29 ? DECORATION_BOTTOM_RIGHT : DECORATION_BOTTOM;
  return x < insets.left ? DECORATION_LEFT : x >= box.width - insets.right ? DECORATION_RIGHT : DECORATION_NONE;
}

static const char *decoration_cursor_name(struct nextspace_toplevel *view)
{
  switch (decoration_part_at(view)) {
  case DECORATION_TOP: return "n-resize";
  case DECORATION_LEFT: return "w-resize";
  case DECORATION_RIGHT: return "e-resize";
  case DECORATION_BOTTOM: return "s-resize";
  case DECORATION_BOTTOM_LEFT: return "sw-resize";
  case DECORATION_BOTTOM_RIGHT: return "se-resize";
  default: return "default";
  }
}

static bool decoration_double_click(struct nextspace_toplevel *view, uint32_t button, uint32_t time)
{
  struct nextspace_server *server = view->server;
  bool paired = server->decoration_click_view == view->id && server->decoration_click_button == button &&
    time - server->decoration_click_time <= server->double_click_time;
  server->decoration_click_view = paired ? 0 : view->id;
  server->decoration_click_button = button;
  server->decoration_click_time = time;
  return paired;
}

static bool decoration_pointer_axis(struct nextspace_server *server, struct nextspace_toplevel *view,
    struct wlr_pointer_axis_event *event)
{
  if (decoration_part_at(view) != DECORATION_TITLE) return false;
  if (event->orientation == WL_POINTER_AXIS_VERTICAL_SCROLL && event->delta_discrete) {
    uint32_t button = event->delta_discrete < 0 ? 0x10000 : 0x10001;
    if (server->decoration_scroll_view != view->id ||
        (int64_t)server->decoration_scroll_remainder * event->delta_discrete < 0)
      server->decoration_scroll_remainder = 0;
    server->decoration_scroll_view = view->id;
    int64_t discrete = (int64_t)server->decoration_scroll_remainder + event->delta_discrete;
    int ticks = llabs(discrete) / WLR_POINTER_AXIS_DISCRETE_STEP;
    server->decoration_scroll_remainder = discrete % WLR_POINTER_AXIS_DISCRETE_STEP;
    for (int n = 0; n < ticks; n++)
      if (decoration_double_click(view, button, event->time_msec))
        policy_set_shaded(view, button == 0x10000);
  }
  return true;
}

static bool decoration_pointer_button(struct nextspace_server *server,
    struct nextspace_toplevel *view, uint32_t button, uint32_t state, uint32_t time)
{
  unsigned part = decoration_part_at(view);
  if (state == WL_POINTER_BUTTON_STATE_RELEASED && server->decoration_pressed &&
      server->decoration_press_button == button) {
    struct nextspace_toplevel *pressed = server->decoration_pressed;
    unsigned action = server->decoration_button;
    server->decoration_pressed = NULL; server->decoration_button = 0;
    finish_cursor_mode(server, false);
    if (view == pressed && action == part && button == 0x110) {
      if (action == DECORATION_CLOSE) wlr_xdg_toplevel_send_close(view->xdg_toplevel);
      if (action == DECORATION_MINIMIZE) policy_set_minimized(view, true);
    }
    decoration_update(pressed);
    policy_refresh_pointer(server);
    return true;
  }
  if (state != WL_POINTER_BUTTON_STATE_PRESSED) return false;
  server->decoration_scroll_remainder = 0;
  if (!part || (part != DECORATION_TITLE && button != 0x110)) {
    server->decoration_click_view = 0;
    return false;
  }
  struct wlr_keyboard *keyboard = wlr_seat_get_keyboard(server->seat);
  uint32_t mods = keyboard ? wlr_keyboard_get_modifiers(keyboard) &
    (WLR_MODIFIER_CTRL | WLR_MODIFIER_SHIFT | WLR_MODIFIER_ALT | WLR_MODIFIER_LOGO) : 0;
  if (button == 0x110 && !(mods & (WLR_MODIFIER_ALT | WLR_MODIFIER_LOGO)))
    focus_toplevel(view, view_surface(view));
  server->decoration_pressed = view; server->decoration_button = part;
  server->decoration_press_button = button;
  bool paired = part == DECORATION_TITLE && decoration_double_click(view, button, time);
  if (part != DECORATION_TITLE) server->decoration_click_view = 0;
  if (part == DECORATION_TITLE) {
    if (button == 0x110 && (mods & WLR_MODIFIER_SHIFT) && !(mods & WLR_MODIFIER_CTRL))
      view->selected = !view->selected;
    if (button == 0x112 && paired) view->selected = !view->selected; /* BTN_MIDDLE */
    if (paired && button == 0x110) {
      unsigned axes = (mods & WLR_MODIFIER_CTRL ? MAXIMIZE_VERTICAL : 0) |
        (mods & WLR_MODIFIER_SHIFT ? MAXIMIZE_HORIZONTAL : 0);
      if (!mods) policy_set_shaded(view, !view->shaded);
      else if (axes && (decoration_style(view) & 8))
        policy_set_size_state(view, view->maximized ^ axes, false, NULL);
    }
  }
  decoration_update(view);
  if (part == DECORATION_TITLE && button == 0x110 && !paired &&
      !((mods & WLR_MODIFIER_SHIFT) && !(mods & WLR_MODIFIER_CTRL)))
    begin_interactive(view, NEXTSPACE_CURSOR_MOVE, 0, true);
  uint32_t edges = part == DECORATION_TOP ? WLR_EDGE_TOP :
    part == DECORATION_LEFT ? WLR_EDGE_LEFT : part == DECORATION_RIGHT ? WLR_EDGE_RIGHT :
    part == DECORATION_BOTTOM ? WLR_EDGE_BOTTOM :
    part == DECORATION_BOTTOM_LEFT ? WLR_EDGE_BOTTOM | WLR_EDGE_LEFT :
    part == DECORATION_BOTTOM_RIGHT ? WLR_EDGE_BOTTOM | WLR_EDGE_RIGHT : 0;
  if (edges && button == 0x110) begin_interactive(view, NEXTSPACE_CURSOR_RESIZE, edges, true);
  return true;
}
