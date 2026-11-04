/* Explicit, gesture-authorized screen-color selection. MIT license. */
#include "color-cursor.h"

static uint64_t color_pick_time(void)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  return (uint64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

static void color_pick_event(struct nextspace_application_window *window,
    uint32_t id, uint32_t phase, uint32_t argb)
{
  nextspace_window_v1_send_color_pick(window->resource, id, phase,
    (argb >> 16) & 255, (argb >> 8) & 255, argb & 255);
}

static void color_pick_finish(struct nextspace_server *server, uint32_t phase, uint32_t argb)
{
  struct nextspace_application_window *window = server->color_pick_window;
  if (!window) return;
  uint32_t id = server->color_pick_id;
  server->color_pick_window = NULL;
  server->color_pick_dirty = server->color_pick_selecting = false;
  server->color_pick_density = 0;
  /* Keep swallowed presses until their releases, including after cancellation. */
  if (server->client_cursor)
    wlr_cursor_set_surface(server->cursor, server->client_cursor,
      server->cursor_hotspot_x, server->cursor_hotspot_y);
  else wlr_cursor_set_xcursor(server->cursor, server->cursor_mgr, "default");
  if (server->color_pick_cursor_buffer) wlr_buffer_drop(server->color_pick_cursor_buffer);
  server->color_pick_cursor_buffer = NULL;
  process_cursor_motion(server, 0);
  color_pick_event(window, id, phase, argb);
}

static bool color_pick_cursor(struct nextspace_server *server, struct wlr_output *output)
{
  size_t index = 0, count = sizeof(color_cursors) / sizeof(color_cursors[0]);
  while (index + 1 < count && color_cursors[index].density < output->scale * 120) ++index;
  if (server->color_pick_density == color_cursors[index].density) return true;
  struct decoration_buffer *buffer = calloc(1, sizeof(*buffer));
  if (!buffer) return false;
  int size = color_cursors[index].size;
  buffer->image = cairo_image_surface_create_for_data((unsigned char *)color_cursors[index].pixels,
    CAIRO_FORMAT_ARGB32, size, size, size * 4);
  if (cairo_surface_status(buffer->image) != CAIRO_STATUS_SUCCESS) {
    cairo_surface_destroy(buffer->image); free(buffer); return false;
  }
  wlr_buffer_init(&buffer->base, &decoration_buffer_impl, size, size);
  wlr_cursor_set_buffer(server->cursor, &buffer->base, 12, 13, color_cursors[index].density / 120.f);
  if (server->color_pick_cursor_buffer) wlr_buffer_drop(server->color_pick_cursor_buffer);
  server->color_pick_cursor_buffer = &buffer->base;
  server->color_pick_density = color_cursors[index].density;
  return true;
}

static void color_pick_schedule(struct nextspace_server *server)
{
  struct wlr_output *output = wlr_output_layout_output_at(server->output_layout,
    server->color_pick_x, server->color_pick_y);
  if (!output || !output->enabled || !color_pick_cursor(server, output)) {
    color_pick_finish(server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_UNAVAILABLE, 0);
    return;
  }
  server->color_pick_dirty = true;
  wlr_output_schedule_frame(output);
}

static void color_pick_motion(struct nextspace_server *server)
{
  if (server->color_pick_selecting) return;
  server->color_pick_x = server->cursor->x;
  server->color_pick_y = server->cursor->y;
  color_pick_schedule(server);
}

static void color_pick_select(struct nextspace_server *server)
{
  if (!server->color_pick_window || server->color_pick_selecting) return;
  server->color_pick_selecting = true;
  color_pick_schedule(server);
}

static void color_pick_frame(struct nextspace_output *output)
{
  struct nextspace_server *server = output->server;
  if (!server->color_pick_window || !server->color_pick_dirty ||
      wlr_output_layout_output_at(server->output_layout,
        server->color_pick_x, server->color_pick_y) != output->wlr_output) return;
  server->color_pick_dirty = false;
  uint32_t argb;
  if (!scene_sample_color(server, server->color_pick_x, server->color_pick_y, &argb)) {
    color_pick_finish(server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_UNAVAILABLE, 0);
  } else if (server->color_pick_selecting) {
    color_pick_finish(server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_SELECTED, argb);
  } else color_pick_event(server->color_pick_window, server->color_pick_id,
    NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_PREVIEW, argb);
}

static bool color_pick_button(struct nextspace_server *server, struct wlr_pointer_button_event *event)
{
  uint32_t bit = event->button >= 0x110 && event->button < 0x130 ? 1u << (event->button - 0x110) : 0;
  bool held = (server->color_pick_buttons & bit) != 0;
  if (!server->color_pick_window && !held) return false;
  if (event->state == WL_POINTER_BUTTON_STATE_PRESSED) server->color_pick_buttons |= bit;
  else server->color_pick_buttons &= ~bit;
  if (!server->color_pick_window) return true;
  if (event->button == 0x111 && event->state == WL_POINTER_BUTTON_STATE_PRESSED)
    color_pick_finish(server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
  else if (event->button == 0x110 && held && event->state == WL_POINTER_BUTTON_STATE_RELEASED)
    color_pick_select(server);
  return true;
}

static void color_pick_begin(struct wl_client *client, struct wl_resource *resource,
    uint32_t request_id, uint32_t serial)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  struct nextspace_toplevel *view = window->view;
  struct nextspace_server *server = view ? view->server : NULL;
  struct wlr_seat_client *seat_client = !server ? NULL : server->color_pick_gesture.keyboard ?
    server->seat->keyboard_state.focused_client : server->seat->pointer_state.focused_client;
  if (!server || server->locked || server->color_pick_window || !view->mapped ||
      !policy_visible(view) || server->seat->drag || server->seat->pointer_state.button_count ||
      wlr_seat_pointer_has_grab(server->seat) ||
      server->color_pick_buttons || server->cursor_mode != NEXTSPACE_CURSOR_PASSTHROUGH ||
      !seat_client || seat_client->client != client || !serial ||
      serial != server->color_pick_gesture.serial || view->id != server->color_pick_gesture.view ||
      color_pick_time() - server->color_pick_gesture.time > 2000 ||
      !wlr_seat_client_validate_event_serial(seat_client, serial)) {
    color_pick_event(window, request_id, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_UNAVAILABLE, 0);
    return;
  }
  server->color_pick_gesture.serial = 0;
  server->color_pick_window = window;
  server->color_pick_id = request_id;
  color_pick_motion(server);
}

static void color_pick_cancel(struct wl_client *client, struct wl_resource *resource, uint32_t request_id)
{
  struct nextspace_application_window *window = wl_resource_get_user_data(resource);
  struct nextspace_server *server = window->view ? window->view->server : NULL;
  if (server && server->color_pick_window == window && server->color_pick_id == request_id)
    color_pick_finish(server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
}
