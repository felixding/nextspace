/* Text-input-v3 relay for the session-authorized input method. GPL-2.0-or-later. */
struct nextspace_text_input {
  struct nextspace_server *server;
  struct wlr_text_input_v3 *input;
  struct wl_list link;
  struct wl_listener enable, commit, disable, destroy;
  char *method_text;
  uint32_t method_cursor, method_anchor, method_hint, method_purpose, method_features;
  uint32_t method_first_serial;
  struct wlr_input_method_v2_preedit_string method_preedit;
  bool method_state_sent;
};

struct nextspace_input_popup {
  struct nextspace_server *server;
  struct wlr_input_popup_surface_v2 *popup;
  struct wlr_scene_tree *tree;
  struct wl_list link;
  struct wl_listener commit, destroy;
};

struct input_surface_position {
  struct wlr_surface *surface;
  int x, y;
  bool found;
};

static void text_input_clear_preedit(struct nextspace_text_input *text)
{
  free(text->method_preedit.text);
  text->method_preedit = (struct wlr_input_method_v2_preedit_string){0};
}

static void input_surface_position(struct wlr_scene_buffer *buffer, int x, int y, void *data)
{
  struct input_surface_position *position = data;
  struct wlr_scene_surface *surface = wlr_scene_surface_try_from_buffer(buffer);
  if (surface && surface->surface == position->surface) {
    position->x = x; position->y = y; position->found = true;
  }
}

static void input_popup_update(struct nextspace_input_popup *popup)
{
  struct nextspace_server *server = popup->server;
  struct nextspace_text_input *active = server->active_text_input;
  struct wlr_surface *surface = active ? active->input->focused_surface : NULL;
  struct nextspace_toplevel *owner = surface ? view_for_surface(server, surface) : NULL;
  struct input_surface_position position = {.surface = surface};
  if (surface) wlr_scene_node_for_each_buffer(&server->scene->tree.node, input_surface_position, &position);
  bool visible = position.found && owner && !owner->shaded && popup->popup->surface->mapped;
  wlr_scene_node_set_enabled(&popup->tree->node, visible);
  if (!visible) return;
  struct wlr_box caret = active->input->current.cursor_rectangle;
  if (!(active->input->active_features & WLR_TEXT_INPUT_V3_FEATURE_CURSOR_RECTANGLE))
    caret = (struct wlr_box){.height = surface->current.height};
  /* An application can report an offscreen caret or arbitrary protocol ints.
     Constrain it before adding desktop coordinates. */
  caret.x = fmax(0, fmin(caret.x, surface->current.width));
  caret.y = fmax(0, fmin(caret.y, surface->current.height));
  caret.width = fmax(0, fmin(caret.width, surface->current.width - caret.x));
  caret.height = fmax(0, fmin(caret.height, surface->current.height - caret.y));
  int x = position.x + caret.x, y = position.y + caret.y + caret.height;
  struct wlr_output *output = wlr_output_layout_output_at(server->output_layout, x, y);
  if (!output) output = wlr_output_layout_output_at(server->output_layout, position.x, position.y);
  if (output) {
    struct wlr_box bounds;
    wlr_output_layout_get_box(server->output_layout, output, &bounds);
    int width = popup->popup->surface->current.width, height = popup->popup->surface->current.height;
    if (y + height > bounds.y + bounds.height) y = position.y + caret.y - height;
    if (x + width > bounds.x + bounds.width) x = bounds.x + bounds.width - width;
    if (x < bounds.x) x = bounds.x;
    if (y < bounds.y) y = bounds.y;
  }
  struct wlr_scene_tree *layer = policy_layer(server, owner->level > 101 ? owner->level : 101);
  if (layer) wlr_scene_node_reparent(&popup->tree->node, layer);
  popup->tree->node.data = owner;
  wlr_scene_node_set_position(&popup->tree->node, x, y);
  caret.x += position.x - x; caret.y += position.y - y;
  wlr_input_popup_surface_v2_send_text_input_rectangle(popup->popup, &caret);
}

static void input_popup_update_all(struct nextspace_server *server)
{
  if (!server->input_method_manager) return;
  struct nextspace_input_popup *popup;
  wl_list_for_each(popup, &server->input_popups, link) input_popup_update(popup);
}

static void text_input_acknowledge(struct nextspace_server *server,
    struct wlr_text_input_v3 *input, bool preserve_preedit)
{
  struct wlr_input_method_v2_preedit_string *preedit = &server->active_text_input->method_preedit;
  if (!preserve_preedit) text_input_clear_preedit(server->active_text_input);
  if (preedit->text)
    wlr_text_input_v3_send_preedit_string(input, preedit->text, preedit->cursor_begin, preedit->cursor_end);
  /* Acknowledge this client serial even if the IME has no edits to return.
     Never replay a commit or deletion while doing so. */
  wlr_text_input_v3_send_done(input);
}

static void input_method_send_state(struct nextspace_server *server)
{
  struct wlr_input_method_v2 *method = server->input_method;
  struct nextspace_text_input *active = server->active_text_input;
  if (!method || !active) return;
  struct wlr_text_input_v3 *input = active->input;
  uint32_t features = input->active_features &
    (WLR_TEXT_INPUT_V3_FEATURE_SURROUNDING_TEXT | WLR_TEXT_INPUT_V3_FEATURE_CONTENT_TYPE);
  const char *text = "";
  uint32_t cursor = 0, anchor = 0, hint = 0, purpose = 0;
  if (features & WLR_TEXT_INPUT_V3_FEATURE_SURROUNDING_TEXT) {
    text = input->current.surrounding.text ? input->current.surrounding.text : "";
    size_t length = strlen(text);
    cursor = input->current.surrounding.cursor; anchor = input->current.surrounding.anchor;
    if (length > 4000 || cursor > length || anchor > length ||
        ((unsigned char)text[cursor] & 0xc0) == 0x80 || ((unsigned char)text[anchor] & 0xc0) == 0x80) {
      text = ""; cursor = anchor = 0;
    }
  }
  if (features & WLR_TEXT_INPUT_V3_FEATURE_CONTENT_TYPE) {
    hint = input->current.content_type.hint; purpose = input->current.content_type.purpose;
  }
  /* wlroots retains the feature flags. Compare the actual context so a caret
     update cannot invalidate already queued composition or commit batches.
     Change cause describes a text change, not cursor-popup placement. */
  input_popup_update_all(server);
  if (active->method_state_sent && active->method_features == features &&
      active->method_cursor == cursor && active->method_anchor == anchor &&
      active->method_hint == hint && active->method_purpose == purpose &&
      strcmp(active->method_text, text) == 0) {
    text_input_acknowledge(server, input, true);
    return;
  }
  char *copy = strdup(text);
  if (!copy) { wl_resource_post_no_memory(input->resource); return; }
  bool new_context = !active->method_state_sent || active->method_features != features ||
    active->method_hint != hint || active->method_purpose != purpose;
  free(active->method_text); active->method_text = copy;
  active->method_cursor = cursor; active->method_anchor = anchor;
  active->method_hint = hint; active->method_purpose = purpose;
  active->method_features = features;
  active->method_state_sent = true;
  if (features & WLR_TEXT_INPUT_V3_FEATURE_SURROUNDING_TEXT)
    wlr_input_method_v2_send_surrounding_text(method, text, cursor, anchor);
  wlr_input_method_v2_send_text_change_cause(method, input->current.text_change_cause);
  if (features & WLR_TEXT_INPUT_V3_FEATURE_CONTENT_TYPE)
    wlr_input_method_v2_send_content_type(method, hint, purpose);
  wlr_input_method_v2_send_done(method);
  if (new_context) active->method_first_serial = method->current_serial;
  /* Protocol cause 0 denotes an IME edit. External edits must not restore
     preedit from the previous text context. */
  text_input_acknowledge(server, input, !new_context && input->current.text_change_cause == 0);
}

static void input_method_deactivate(struct nextspace_server *server)
{
  if (server->active_text_input) {
    server->active_text_input->method_state_sent = false;
    text_input_clear_preedit(server->active_text_input);
  }
  if (server->input_method && server->input_method->active) {
    wlr_input_method_v2_send_deactivate(server->input_method);
    wlr_input_method_v2_send_done(server->input_method);
  }
  server->active_text_input = NULL;
  input_popup_update_all(server);
}

static void text_input_update(struct nextspace_text_input *text)
{
  struct nextspace_server *server = text->server;
  if (server->locked) return;
  if (!text->input->focused_surface || !text->input->current_enabled) return;
  if (text->input->focused_surface != server->seat->keyboard_state.focused_surface) return;
  if (server->active_text_input != text) {
    input_method_deactivate(server);
    server->active_text_input = text;
    if (server->input_method) wlr_input_method_v2_send_activate(server->input_method);
  }
  input_method_send_state(server);
}

static void text_input_enable(struct wl_listener *listener, void *data)
{
  struct nextspace_text_input *text = wl_container_of(listener, text, enable);
  text_input_update(text);
}

static void text_input_commit(struct wl_listener *listener, void *data)
{
  struct nextspace_text_input *text = wl_container_of(listener, text, commit);
  text_input_update(text);
}

static void text_input_disable(struct wl_listener *listener, void *data)
{
  struct nextspace_text_input *text = wl_container_of(listener, text, disable);
  if (text->server->active_text_input == text) input_method_deactivate(text->server);
}

static void text_input_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_text_input *text = wl_container_of(listener, text, destroy);
  if (text->server->active_text_input == text) input_method_deactivate(text->server);
  wl_list_remove(&text->enable.link); wl_list_remove(&text->commit.link);
  wl_list_remove(&text->disable.link); wl_list_remove(&text->destroy.link);
  wl_list_remove(&text->link); free(text->method_text); text_input_clear_preedit(text); free(text);
}

static void text_input_enter(struct nextspace_text_input *text, struct wlr_surface *surface)
{
  if (surface && wl_resource_get_client(text->input->resource) == wl_resource_get_client(surface->resource))
    wlr_text_input_v3_send_enter(text->input, surface);
}

static void text_input_focus(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, text_focus);
  struct wlr_seat_keyboard_focus_change_event *event = data;
  input_method_deactivate(server);
  struct nextspace_text_input *text;
  wl_list_for_each(text, &server->text_inputs, link) {
    if (text->input->focused_surface) wlr_text_input_v3_send_leave(text->input);
    text_input_enter(text, event->new_surface);
  }
}

static void text_input_new(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, new_text_input);
  struct wlr_text_input_v3 *input = data;
  if (input->seat != server->seat) return;
  struct nextspace_text_input *text = calloc(1, sizeof(*text));
  if (!text) { wl_resource_post_no_memory(input->resource); return; }
  text->server = server; text->input = input;
  text->enable.notify = text_input_enable; wl_signal_add(&input->events.enable, &text->enable);
  text->commit.notify = text_input_commit; wl_signal_add(&input->events.commit, &text->commit);
  text->disable.notify = text_input_disable; wl_signal_add(&input->events.disable, &text->disable);
  text->destroy.notify = text_input_destroy; wl_signal_add(&input->events.destroy, &text->destroy);
  wl_list_insert(&server->text_inputs, &text->link);
  text_input_enter(text, server->seat->keyboard_state.focused_surface);
}

static void input_method_commit(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, input_method_commit);
  const struct wlr_input_method_v2_commit_event *event = data;
  struct nextspace_text_input *active = server->active_text_input;
  if (server->locked || !active || !active->method_state_sent || event->input_method != server->input_method ||
      !server->input_method->active ||
      active->input->focused_surface != server->seat->keyboard_state.focused_surface) return;
  /* Context feedback can overtake edits already sent by the method. Apply
     those edits in wire order, as input-method-v2 requires, but never accept
     a serial from before this activation or from the future (also at wrap). */
  uint32_t current = server->input_method->current_serial;
  if (current - event->serial > current - active->method_first_serial) return;
  const struct wlr_input_method_v2_state *state = event->state;
  char *preedit = state->preedit.text ? strdup(state->preedit.text) : NULL;
  if (state->preedit.text && !preedit) { wl_resource_post_no_memory(active->input->resource); return; }
  free(active->method_preedit.text);
  active->method_preedit = state->preedit;
  active->method_preedit.text = preedit;
  if (state->delete.before_length || state->delete.after_length)
    wlr_text_input_v3_send_delete_surrounding_text(active->input,
      state->delete.before_length, state->delete.after_length);
  if (state->commit_text) wlr_text_input_v3_send_commit_string(active->input, state->commit_text);
  wlr_text_input_v3_send_preedit_string(active->input, state->preedit.text,
    state->preedit.cursor_begin, state->preedit.cursor_end);
  wlr_text_input_v3_send_done(active->input);
}

static void input_method_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, input_method_destroy);
  if (server->active_text_input && server->active_text_input->input->focused_surface) {
    text_input_clear_preedit(server->active_text_input);
    wlr_text_input_v3_send_preedit_string(server->active_text_input->input, "", 0, 0);
    wlr_text_input_v3_send_done(server->active_text_input->input);
  }
  wl_list_remove(&server->input_method_commit.link); wl_list_remove(&server->input_method_destroy.link);
  wl_list_remove(&server->input_method_popup.link); wl_list_remove(&server->input_method_grab.link);
  server->input_method = NULL;
}

static void input_popup_commit(struct wl_listener *listener, void *data)
{
  struct nextspace_input_popup *popup = wl_container_of(listener, popup, commit);
  input_popup_update(popup);
}

static void input_popup_destroy(struct wl_listener *listener, void *data)
{
  struct nextspace_input_popup *popup = wl_container_of(listener, popup, destroy);
  wl_list_remove(&popup->commit.link); wl_list_remove(&popup->destroy.link); wl_list_remove(&popup->link);
  wlr_scene_node_destroy(&popup->tree->node); free(popup);
}

static void input_method_popup(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, input_method_popup);
  struct wlr_input_popup_surface_v2 *surface = data;
  struct nextspace_input_popup *popup = calloc(1, sizeof(*popup));
  if (!popup) { wl_resource_post_no_memory(surface->resource); return; }
  popup->server = server; popup->popup = surface;
  popup->tree = wlr_scene_tree_create(server->desktop_tree);
  if (!popup->tree || !wlr_scene_subsurface_tree_create(popup->tree, surface->surface)) {
    if (popup->tree) wlr_scene_node_destroy(&popup->tree->node);
    free(popup); wl_resource_post_no_memory(surface->resource); return;
  }
  popup->commit.notify = input_popup_commit; wl_signal_add(&surface->surface->events.commit, &popup->commit);
  popup->destroy.notify = input_popup_destroy; wl_signal_add(&surface->events.destroy, &popup->destroy);
  wl_list_insert(&server->input_popups, &popup->link);
  input_popup_update(popup);
}

static struct wlr_input_method_keyboard_grab_v2 *input_method_keyboard_grab(struct nextspace_keyboard *keyboard)
{
  struct nextspace_server *server = keyboard->server;
  if (server->locked || !server->active_text_input || !server->input_method || !server->input_method->active ||
      wlr_input_device_get_virtual_keyboard(&keyboard->wlr_keyboard->base)) return NULL;
  struct wlr_input_method_keyboard_grab_v2 *grab = server->input_method->keyboard_grab;
  if (grab) wlr_input_method_keyboard_grab_v2_set_keyboard(grab, keyboard->wlr_keyboard);
  return grab;
}

static void input_method_grab(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, input_method_grab);
  struct nextspace_keyboard *keyboard;
  wl_list_for_each(keyboard, &server->keyboards, link) {
    if (wlr_input_device_get_virtual_keyboard(&keyboard->wlr_keyboard->base)) continue;
    wlr_input_method_keyboard_grab_v2_set_keyboard(data, keyboard->wlr_keyboard);
    break;
  }
}

static void input_method_new(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, new_input_method);
  struct wlr_input_method_v2 *method = data;
  if (server->input_method || method->seat != server->seat ||
      wl_resource_get_client(method->resource) != server->input_method_client) {
    wlr_input_method_v2_send_unavailable(method); return;
  }
  server->input_method = method;
  server->input_method_commit.notify = input_method_commit;
  wl_signal_add(&method->events.commit_pending, &server->input_method_commit);
  server->input_method_destroy.notify = input_method_destroy;
  wl_signal_add(&method->events.destroy, &server->input_method_destroy);
  server->input_method_popup.notify = input_method_popup;
  wl_signal_add(&method->events.new_popup_surface, &server->input_method_popup);
  server->input_method_grab.notify = input_method_grab;
  wl_signal_add(&method->events.grab_keyboard, &server->input_method_grab);
  if (server->active_text_input) {
    server->active_text_input->method_state_sent = false;
    wlr_input_method_v2_send_activate(method);
    input_method_send_state(server);
  }
}

static void input_method_virtual_keyboard(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, new_virtual_keyboard);
  struct wlr_virtual_keyboard_v1 *keyboard = data;
  if (keyboard->seat == server->seat && wl_resource_get_client(keyboard->resource) == server->input_method_client)
    server_new_keyboard(server, &keyboard->keyboard.base);
}

static bool text_input_init(struct nextspace_server *server)
{
  wl_list_init(&server->text_inputs); wl_list_init(&server->input_popups);
  server->text_input_manager = wlr_text_input_manager_v3_create(server->wl_display);
  server->input_method_manager = wlr_input_method_manager_v2_create(server->wl_display);
  server->virtual_keyboard_manager = wlr_virtual_keyboard_manager_v1_create(server->wl_display);
  if (!server->text_input_manager || !server->input_method_manager || !server->virtual_keyboard_manager) return false;
  server->new_text_input.notify = text_input_new;
  wl_signal_add(&server->text_input_manager->events.text_input, &server->new_text_input);
  server->new_input_method.notify = input_method_new;
  wl_signal_add(&server->input_method_manager->events.input_method, &server->new_input_method);
  server->new_virtual_keyboard.notify = input_method_virtual_keyboard;
  wl_signal_add(&server->virtual_keyboard_manager->events.new_virtual_keyboard, &server->new_virtual_keyboard);
  server->text_focus.notify = text_input_focus;
  wl_signal_add(&server->seat->keyboard_state.events.focus_change, &server->text_focus);
  return true;
}
