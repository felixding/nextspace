/* Compositor-owned desktop visibility; Workspace owns names and presentation.
   SPDX-License-Identifier: MIT */
static void desktop_snapshot(struct nextspace_server *server)
{
  if (server->shell_resource && wl_resource_get_version(server->shell_resource) >= 10)
    nextspace_shell_v1_send_desktops(server->shell_resource, server->desktop, server->desktop_count);
}

static void desktop_refresh(struct nextspace_server *server)
{
  struct nextspace_toplevel *view = view_for_surface(server, server->seat->keyboard_state.focused_surface);
  if (view) view_activate(view, false);
  wlr_seat_keyboard_notify_clear_focus(server->seat);
  /* Clear focus first: visibility updates must not reorder the list being
     traversed while selecting a replacement window. */
  wl_list_for_each(view, &server->toplevels, link) {
    policy_apply_visibility(view);
    shell_window_changed(view);
  }
  wl_list_for_each(view, &server->toplevels, link) {
    if (!view->mapped || !policy_visible(view) ||
        (view->application_window && !view->application_window->accepts_focus)) continue;
    focus_toplevel(view, view_surface(view)); break;
  }
  policy_refresh_pointer(server);
}

static void desktop_switch(struct nextspace_server *server, unsigned index)
{
  if (index < server->desktop_count && index != server->desktop) {
    cancel_pointer_drag(server);
    reset_cursor_mode(server);
    server->desktop = index;
    desktop_refresh(server);
  }
  desktop_snapshot(server);
}

static void desktop_configure(struct nextspace_server *server, unsigned count)
{
  if (count >= 1 && count <= 32 && count != server->desktop_count) {
    server->desktop_count = count;
    if (server->desktop >= count) server->desktop = count - 1;
    struct nextspace_toplevel *view;
    wl_list_for_each(view, &server->toplevels, link) if (view->desktop >= count) view->desktop = count - 1;
    desktop_refresh(server);
  }
  desktop_snapshot(server);
}

static void desktop_move(struct nextspace_toplevel *view, unsigned index, bool sticky)
{
  if (index >= view->server->desktop_count || (view->desktop == index && view->sticky == sticky)) return;
  view->desktop = index; view->sticky = sticky;
  policy_apply_visibility(view);
  shell_window_changed(view);
}
