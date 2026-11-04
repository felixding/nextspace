/* Rootless Xwayland lifecycle/input fixture. SPDX-License-Identifier: MIT */
#include <xcb/xcb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdbool.h>
#include <poll.h>

static xcb_atom_t atom(xcb_connection_t *connection, const char *name)
{
  xcb_intern_atom_reply_t *reply = xcb_intern_atom_reply(connection,
    xcb_intern_atom(connection, 0, strlen(name), name), NULL);
  if (!reply) exit(1);
  xcb_atom_t result = reply->atom;
  free(reply);
  return result;
}

static int clipboard(xcb_connection_t *connection, xcb_window_t window, bool write_mode, const char *path, bool primary)
{
  alarm(20);
  xcb_atom_t selection = primary ? XCB_ATOM_PRIMARY : atom(connection, "CLIPBOARD"), utf8 = atom(connection, "UTF8_STRING");
  xcb_atom_t targets = atom(connection, "TARGETS"), property = atom(connection, "NEXTSPACE_CLIPBOARD");
  xcb_atom_t incr = atom(connection, "INCR");
  FILE *file = fopen(path, write_mode ? "rb" : "wb");
  if (!file) return 1;
  char *payload = NULL;
  size_t length = 0;
  bool incremental = false, done = false;
  if (write_mode) {
    fseek(file, 0, SEEK_END); length = ftell(file); rewind(file);
    payload = malloc(length);
    if (fread(payload, 1, length, file) != length) return 1;
    fclose(file); file = NULL;
    xcb_set_selection_owner(connection, window, selection, XCB_CURRENT_TIME);
    puts("X11 clipboard source set"); fflush(stdout);
  } else xcb_convert_selection(connection, window, selection, utf8, property, XCB_CURRENT_TIME);
  xcb_flush(connection);
  xcb_generic_event_t *event;
  int result = 1;
  while (!done && (event = xcb_wait_for_event(connection))) {
    uint8_t type = event->response_type & 0x7f;
    if (type == XCB_SELECTION_REQUEST && write_mode) {
      xcb_selection_request_event_t *request = (void *)event;
      xcb_atom_t prop = request->property ? request->property : request->target;
      xcb_selection_notify_event_t reply = {.response_type = XCB_SELECTION_NOTIFY,
        .requestor = request->requestor, .selection = request->selection,
        .target = request->target, .time = request->time, .property = prop};
      if (request->target == targets) {
        xcb_atom_t supported[] = {targets, utf8};
        xcb_change_property(connection, XCB_PROP_MODE_REPLACE, request->requestor,
          prop, XCB_ATOM_ATOM, 32, 2, supported);
      } else if (request->target == utf8) {
        xcb_change_property(connection, XCB_PROP_MODE_REPLACE, request->requestor,
          prop, utf8, 8, length, payload);
      } else reply.property = XCB_ATOM_NONE;
      xcb_send_event(connection, 0, request->requestor, 0, (const char *)&reply);
      xcb_flush(connection);
    } else if (!write_mode && (type == XCB_SELECTION_NOTIFY ||
        (type == XCB_PROPERTY_NOTIFY && incremental && ((xcb_property_notify_event_t *)event)->state == XCB_PROPERTY_NEW_VALUE))) {
      if (type == XCB_SELECTION_NOTIFY && ((xcb_selection_notify_event_t *)event)->property == XCB_ATOM_NONE) {
        /* XWM ownership follows the Wayland offer asynchronously. */
        free(event);
        poll(NULL, 0, 10);
        xcb_convert_selection(connection, window, selection, utf8, property, XCB_CURRENT_TIME);
        xcb_flush(connection);
        continue;
      }
      xcb_get_property_reply_t *reply = xcb_get_property_reply(connection,
        xcb_get_property(connection, 1, window, property, XCB_GET_PROPERTY_TYPE_ANY, 0, 16 * 1024 * 1024), NULL);
      if (!reply) { free(event); break; }
      if (reply->type == incr) {
        incremental = true;
      } else {
        int count = xcb_get_property_value_length(reply);
        if (fwrite(xcb_get_property_value(reply), 1, count, file) != (size_t)count) {
          free(reply); free(event); break;
        }
        if (!incremental || count == 0) { result = 0; done = true; }
      }
      free(reply); xcb_flush(connection);
    }
    free(event);
  }
  if (file) fclose(file);
  free(payload); alarm(0);
  return result;
}

int main(int argc, char **argv)
{
  xcb_connection_t *connection = xcb_connect(NULL, NULL);
  if (xcb_connection_has_error(connection)) { xcb_disconnect(connection); return 1; }
  if (argc > 1 && strcmp(argv[1], "--check") == 0) { xcb_disconnect(connection); return 0; }
  xcb_screen_t *screen = xcb_setup_roots_iterator(xcb_get_setup(connection)).data;
  xcb_window_t window = xcb_generate_id(connection);
  uint32_t values[] = {screen->white_pixel, XCB_EVENT_MASK_BUTTON_PRESS | XCB_EVENT_MASK_FOCUS_CHANGE | XCB_EVENT_MASK_PROPERTY_CHANGE};
  xcb_create_window(connection, XCB_COPY_FROM_PARENT, window, screen->root, 0, 0,
    801, 601, 0, XCB_WINDOW_CLASS_INPUT_OUTPUT, screen->root_visual,
    XCB_CW_BACK_PIXEL | XCB_CW_EVENT_MASK, values);
  bool primary = argc == 3 && strncmp(argv[1], "--primary-", 10) == 0;
  bool clipboard_mode = primary || (argc == 3 && strncmp(argv[1], "--clipboard-", 12) == 0);
  const char *title = clipboard_mode ? "X11ClipboardProbe" : "NextSpaceX11Probe";
  xcb_change_property(connection, XCB_PROP_MODE_REPLACE, window, XCB_ATOM_WM_NAME,
    XCB_ATOM_STRING, 8, strlen(title), title);
  if (clipboard_mode) {
    const char resource[] = "X11ClipboardProbe\0X11ClipboardProbe";
    xcb_change_property(connection, XCB_PROP_MODE_REPLACE, window, XCB_ATOM_WM_CLASS,
      XCB_ATOM_STRING, 8, sizeof(resource), resource);
  }
  xcb_atom_t protocols = atom(connection, "WM_PROTOCOLS");
  xcb_atom_t close = atom(connection, "WM_DELETE_WINDOW");
  xcb_change_property(connection, XCB_PROP_MODE_REPLACE, window, protocols, XCB_ATOM_ATOM, 32, 1, &close);
  xcb_map_window(connection, window);
  xcb_flush(connection);
  if (clipboard_mode) {
    /* Publishing requires an actually focused Xwayland surface. */
    alarm(20);
    xcb_generic_event_t *focus;
    bool focused = false;
    while ((focus = xcb_wait_for_event(connection))) {
      focused = (focus->response_type & 0x7f) == XCB_FOCUS_IN;
      free(focus);
      if (focused) break;
    }
    if (!focused) { xcb_disconnect(connection); return 1; }
    int result = clipboard(connection, window, strcmp(argv[1], "--clipboard-write") == 0 ||
      strcmp(argv[1], "--primary-write") == 0, argv[2], primary);
    xcb_destroy_window(connection, window); xcb_disconnect(connection);
    return result;
  }
  xcb_generic_event_t *event;
  while ((event = xcb_wait_for_event(connection))) {
    uint8_t type = event->response_type & 0x7f;
    if (type == XCB_BUTTON_PRESS) {
      xcb_button_press_event_t *button = (void *)event;
      printf("{\"event\":\"click\",\"x\":%d,\"y\":%d}\n", button->event_x, button->event_y);
      fflush(stdout);
    } else if (type == XCB_FOCUS_IN) {
      puts("{\"event\":\"focus\"}"); fflush(stdout);
    } else if (type == XCB_CLIENT_MESSAGE && ((xcb_client_message_event_t *)event)->data.data32[0] == close) {
      free(event); break;
    }
    free(event);
  }
  xcb_destroy_window(connection, window);
  xcb_flush(connection);
  xcb_disconnect(connection);
  return 0;
}
