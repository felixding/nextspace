/* Logical window levels; focus changes order only within a level. MIT license. */
struct nextspace_layer {
  struct wl_list link;
  struct wlr_scene_tree *tree;
  int level;
};

static struct wlr_scene_tree *policy_layer(struct nextspace_server *server, int level)
{
  struct nextspace_layer *layer, *higher = NULL;
  wl_list_for_each(layer, &server->layers, link) {
    if (layer->level == level) return layer->tree;
    if (layer->level > level) { higher = layer; break; }
  }
  layer = calloc(1, sizeof(*layer));
  if (!layer) return NULL;
  layer->tree = wlr_scene_tree_create(server->desktop_tree);
  if (!layer->tree) { free(layer); return NULL; }
  layer->level = level;
  wl_list_insert(higher ? higher->link.prev : server->layers.prev, &layer->link);
  if (higher) wlr_scene_node_place_below(&layer->tree->node, &higher->tree->node);
  return layer->tree;
}

static struct nextspace_toplevel *policy_parent(struct nextspace_toplevel *view)
{
  struct wlr_xdg_toplevel *parent = view->xdg_toplevel->parent;
  struct wlr_scene_tree *tree = parent ? parent->base->data : NULL;
  return tree ? tree->node.data : NULL;
}

static bool policy_descendant(struct nextspace_toplevel *view, struct nextspace_toplevel *ancestor)
{
  for (unsigned depth = 0; view && depth < 64; depth++, view = policy_parent(view))
    if (view == ancestor) return true;
  return false;
}

static int policy_effective_level(struct nextspace_toplevel *view, struct nextspace_toplevel *focused)
{
  struct nextspace_toplevel *ancestor = view;
  for (unsigned depth = 0; ancestor && depth < 64; depth++, ancestor = policy_parent(ancestor))
    if (ancestor->fullscreen && policy_descendant(focused, ancestor))
      return view->level < 100 ? 100 : view->level;
  return view->level;
}

static void policy_focus_layers(struct nextspace_server *server, struct nextspace_toplevel *focused)
{
  /* An inactive fullscreen window retains its geometry without covering the
     newly focused app. Its transient dialogs remain above it while active. */
  struct nextspace_toplevel *view;
  wl_list_for_each_reverse(view, &server->toplevels, link) {
    struct wlr_scene_tree *layer = policy_layer(server, policy_effective_level(view, focused));
    if (layer) wlr_scene_node_reparent(&view->scene_tree->node, layer);
  }
}

static struct nextspace_toplevel *popup_owner(struct nextspace_popup *popup)
{
  struct wlr_xdg_surface *root = wlr_xdg_surface_try_from_wlr_surface(popup->xdg_popup->parent);
  while (root && root->role == WLR_XDG_SURFACE_ROLE_POPUP)
    root = wlr_xdg_surface_try_from_wlr_surface(root->popup->parent);
  if (!root || !root->data) return NULL;
  struct wlr_scene_tree *tree = root->data;
  return tree->node.data;
}

static void policy_update_popups(struct nextspace_server *server)
{
  input_popup_update_all(server);
  /* Creation order keeps nested popup parents ahead of their children. */
  struct nextspace_popup *popup;
  wl_list_for_each(popup, &server->popups, link) {
    if (!popup->holder) continue;
    struct wlr_xdg_surface *parent = wlr_xdg_surface_try_from_wlr_surface(popup->xdg_popup->parent);
    struct nextspace_toplevel *owner = popup_owner(popup);
    if (!parent || !parent->data || !owner) continue;
    struct wlr_scene_tree *layer = policy_layer(server, owner->level > 101 ? owner->level : 101);
    if (!layer) continue;
    wlr_scene_node_reparent(&popup->holder->node, layer);
    struct wlr_scene_tree *parent_tree = parent->data;
    int x, y;
    bool visible = wlr_scene_node_coords(&parent_tree->node, &x, &y);
    wlr_scene_node_set_position(&popup->holder->node, x, y);
    wlr_scene_node_set_enabled(&popup->holder->node, visible && !owner->shaded);
    popup->holder->node.data = owner;
  }
}

static void policy_set_level(struct nextspace_toplevel *view, int level)
{
  /* This is stacking metadata, never a session-lock or shell capability. */
  if (level < -1000) level = -1000;
  if (level > 1000) level = 1000;
  if (level == view->level) return;
  view->level = level;
  struct nextspace_toplevel *focused = view_for_surface(view->server, view->server->seat->keyboard_state.focused_surface);
  struct wlr_scene_tree *layer = policy_layer(view->server, policy_effective_level(view, focused));
  if (layer) wlr_scene_node_reparent(&view->scene_tree->node, layer);
  policy_update_popups(view->server);
  shell_window_changed(view);
}

static void policy_order(struct nextspace_toplevel *view, bool above, struct nextspace_toplevel *relative)
{
  if (relative && relative != view && relative->scene_tree &&
      relative->scene_tree->node.parent == view->scene_tree->node.parent) {
    if (above) wlr_scene_node_place_above(&view->scene_tree->node, &relative->scene_tree->node);
    else wlr_scene_node_place_below(&view->scene_tree->node, &relative->scene_tree->node);
  } else if (!relative) {
    if (above) wlr_scene_node_raise_to_top(&view->scene_tree->node);
    else wlr_scene_node_lower_to_bottom(&view->scene_tree->node);
  }
}

static void policy_refresh_pointer(struct nextspace_server *server)
{
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  process_cursor_motion(server, now.tv_sec * 1000 + now.tv_nsec / 1000000);
}

static void policy_dismiss_popups(struct nextspace_toplevel *view)
{
  for (;;) {
    struct nextspace_popup *popup, *last = NULL;
    wl_list_for_each_reverse(popup, &view->server->popups, link)
      if (popup_owner(popup) == view) { last = popup; break; }
    if (!last) return;
    wlr_xdg_popup_destroy(last->xdg_popup);
  }
}

static void policy_update_clip(struct nextspace_toplevel *view)
{
  if (view->server_decorated) {
    wlr_scene_node_set_enabled(&view->content_tree->node, !view->shaded);
    decoration_update(view);
    return;
  }
  struct wlr_box clip;
  view_geometry(view, &clip);
  if (clip.height > (int)view->title_height) clip.height = view->title_height;
  wlr_scene_subsurface_tree_set_clip(view->content_tree ? &view->content_tree->node :
    &view->scene_tree->node, view->shaded ? &clip : NULL);
}

static void policy_set_shaded(struct nextspace_toplevel *view, bool shaded)
{
  if (shaded && view->fullscreen) return;
  if (view->shaded == shaded || (shaded && !view->title_height)) return;
  view->shaded = shaded;
  if (shaded) {
    drag_cancel_origin(view);
    policy_dismiss_popups(view);
    if (view->server->grabbed_toplevel == view) reset_cursor_mode(view->server);
  }
  policy_update_clip(view);
  policy_update_popups(view->server);
  policy_refresh_pointer(view->server);
  decoration_update(view);
  shell_window_changed(view);
}

static bool policy_visible(struct nextspace_toplevel *view)
{
  return !view->minimized && !view->shell_hidden && !view->client_hidden &&
    (view->sticky || view->desktop == view->server->desktop);
}

static void policy_apply_visibility(struct nextspace_toplevel *view)
{
  bool visible = policy_visible(view);
  if (!visible && view->server->color_pick_window == view->application_window && view->application_window)
    color_pick_finish(view->server, NEXTSPACE_WINDOW_V1_COLOR_PICK_PHASE_CANCELLED, 0);
  if (!visible) { policy_dismiss_popups(view); drag_cancel_origin(view); }
  wlr_scene_node_set_enabled(&view->scene_tree->node, visible);
  policy_update_popups(view->server);
  if (!visible && view->server->grabbed_toplevel == view) reset_cursor_mode(view->server);
  policy_refresh_pointer(view->server);
  if (!visible && view->server->seat->keyboard_state.focused_surface == view_surface(view)) {
    view_activate(view, false);
    wlr_seat_keyboard_notify_clear_focus(view->server->seat);
    struct nextspace_toplevel *candidate;
    wl_list_for_each(candidate, &view->server->toplevels, link) {
      if (candidate == view || !candidate->mapped || !policy_visible(candidate) ||
          (candidate->application_window && !candidate->application_window->accepts_focus)) continue;
      focus_toplevel(candidate, view_surface(candidate)); break;
    }
    decoration_update_all(view->server);
  }
  decoration_update(view);
}

static void policy_set_presented(struct nextspace_toplevel *view, bool presented)
{
  if (view->shell_hidden == !presented) return;
  view->shell_hidden = !presented;
  policy_apply_visibility(view);
  shell_window_changed(view);
}

static void policy_set_client_presented(struct nextspace_toplevel *view, bool presented)
{
  if (view->client_hidden == !presented) return;
  view->client_hidden = !presented;
  policy_apply_visibility(view);
  shell_window_changed(view);
}

static void policy_set_minimized(struct nextspace_toplevel *view, bool minimized)
{
  if (view->minimized == minimized) return;
  view->minimized = minimized;
  policy_apply_visibility(view);
  if (view->application_window && wl_resource_get_version(view->application_window->resource) >= 3)
    nextspace_window_v1_send_minimized(view->application_window->resource, minimized);
  shell_window_changed(view);
}

static void policy_request_minimize(struct wl_listener *listener, void *data)
{
  struct nextspace_toplevel *view = wl_container_of(listener, view, request_minimize);
  policy_set_minimized(view, true);
}

/* Maximize and fullscreen share logical output geometry and one normal frame.
 * Fullscreen temporarily supersedes maximization, including its chosen output. */
static struct nextspace_output *policy_size_output(struct nextspace_toplevel *view,
    uint32_t id, struct wlr_output *requested)
{
  struct wlr_box frame;
  view_geometry(view, &frame);
  frame.x = view->scene_tree->node.x; frame.y = view->scene_tree->node.y;
  struct nextspace_output *output, *best = NULL;
  int64_t area = -1;
  wl_list_for_each(output, &view->server->outputs, link) {
    if (!output->wlr_output->enabled) continue;
    if ((requested && output->wlr_output == requested) || (!requested && output->id == id)) return output;
    struct wlr_box bounds, overlap;
    wlr_output_layout_get_box(view->server->output_layout, output->wlr_output, &bounds);
    int64_t visible = wlr_box_intersection(&overlap, &frame, &bounds) ? (int64_t)overlap.width * overlap.height : 0;
    if (visible > area || (visible == area && output->id == view->server->primary_output_id)) {
      best = output; area = visible;
    }
  }
  return best;
}

static bool policy_size_geometry(struct nextspace_toplevel *view)
{
  if ((!view->maximized && !view->fullscreen) || !view->scene_tree) return false;
  uint32_t *id = view->fullscreen ? &view->fullscreen_output : &view->maximized_output;
  struct nextspace_output *output = policy_size_output(view, *id, NULL);
  if (!output) return false;
  *id = output->id;
  struct wlr_box bounds;
  wlr_output_layout_get_box(view->server->output_layout, output->wlr_output, &bounds);
  if (!view->fullscreen) output_work_area(output, &bounds);
  int x = bounds.x, y = bounds.y;
  int width = bounds.width, height = bounds.height;
  if (!view->fullscreen) {
    x = view->maximized & MAXIMIZE_HORIZONTAL ? x + view->maximized_dx : view->normal_geometry.x;
    y = view->maximized & MAXIMIZE_VERTICAL ? y + view->maximized_dy : view->normal_geometry.y;
    if (!(view->maximized & MAXIMIZE_HORIZONTAL)) width = view->normal_geometry.width;
    if (!(view->maximized & MAXIMIZE_VERTICAL)) height = view->normal_geometry.height;
    constrain_position(view, &x, &y);
    if (view->maximized & MAXIMIZE_HORIZONTAL) view->maximized_dx = x - bounds.x;
    else view->normal_geometry.x = x;
    if (view->maximized & MAXIMIZE_VERTICAL) view->maximized_dy = y - bounds.y;
    else view->normal_geometry.y = y;
  }
  view_move(view, x, y);
  view_resize(view, width, height);
  if (view->fullscreen_background) wlr_scene_rect_set_size(view->fullscreen_background, bounds.width, bounds.height);
  return true;
}

static void policy_center_fullscreen(struct nextspace_toplevel *view)
{
  if (!view->fullscreen || !view->mapped || !view->xdg_toplevel->current.fullscreen) return;
  struct nextspace_output *output = policy_size_output(view, view->fullscreen_output, NULL);
  if (!output) return;
  struct wlr_box bounds, geometry;
  wlr_output_layout_get_box(view->server->output_layout, output->wlr_output, &bounds);
  view_geometry(view, &geometry);
  int dx = geometry.width < bounds.width ? (bounds.width - geometry.width) / 2 : 0;
  int dy = geometry.height < bounds.height ? (bounds.height - geometry.height) / 2 : 0;
  view_move(view, bounds.x + dx, bounds.y + dy);
  if (view->fullscreen_background) {
    wlr_scene_node_set_position(&view->fullscreen_background->node, -dx, -dy);
    wlr_scene_rect_set_size(view->fullscreen_background, bounds.width, bounds.height);
  }
}

static void policy_cancel_interactive(struct nextspace_toplevel *view)
{
  if (view->server->grabbed_toplevel == view) reset_cursor_mode(view->server);
}

static void policy_apply_size_state(struct nextspace_toplevel *view, unsigned maximized,
    bool fullscreen, struct wlr_output *requested, bool during_move)
{
  if (!view->scene_tree) return;
  if (!during_move) policy_cancel_interactive(view);
  if (!view->maximized && !view->fullscreen && (maximized || fullscreen) &&
      (!view->xdg_toplevel->current.maximized && !view->xdg_toplevel->current.fullscreen)) {
    view_geometry(view, &view->normal_geometry);
    view->normal_geometry.x = view->scene_tree->node.x;
    view->normal_geometry.y = view->scene_tree->node.y;
  }
  if (maximized != view->maximized) {
    view->maximized_dx = view->maximized_dy = 0;
    struct nextspace_output *output = policy_size_output(view, 0, NULL);
    view->maximized_output = output ? output->id : 0;
  }
  if (fullscreen && (!view->fullscreen || requested)) {
    struct nextspace_output *output = policy_size_output(view, 0, requested);
    view->fullscreen_output = output ? output->id : 0;
  }
  bool restore = (view->maximized || view->fullscreen) && !maximized && !fullscreen;
  wlr_log(WLR_DEBUG, "Window %u state max=%u full=%d normal=%dx%d at %d,%d", view->id,
    maximized, fullscreen, view->normal_geometry.width, view->normal_geometry.height,
    view->normal_geometry.x, view->normal_geometry.y);
  view->maximized = maximized; view->fullscreen = fullscreen;
  if (maximized || fullscreen) policy_set_shaded(view, false);
  wlr_xdg_toplevel_set_maximized(view->xdg_toplevel, maximized != 0);
  wlr_xdg_toplevel_set_fullscreen(view->xdg_toplevel, fullscreen);

  policy_focus_layers(view->server, view_for_surface(view->server, view->server->seat->keyboard_state.focused_surface));
  if (fullscreen && !view->fullscreen_background) {
    const float black[] = {0, 0, 0, 1};
    view->fullscreen_background = wlr_scene_rect_create(view->scene_tree, 0, 0, black);
    if (view->fullscreen_background) wlr_scene_node_lower_to_bottom(&view->fullscreen_background->node);
  } else if (!fullscreen && view->fullscreen_background) {
    wlr_scene_node_destroy(&view->fullscreen_background->node);
    view->fullscreen_background = NULL;
  }
  if (!policy_size_geometry(view) && restore) {
    int x = view->normal_geometry.x, y = view->normal_geometry.y;
    constrain_position(view, &x, &y);
    view_move(view, x, y);
    view_resize(view, view->normal_geometry.width, view->normal_geometry.height);
  }
  policy_update_popups(view->server);
  if (!during_move) policy_refresh_pointer(view->server);
  shell_window_changed(view);
}

static void policy_set_size_state(struct nextspace_toplevel *view, unsigned maximized,
    bool fullscreen, struct wlr_output *requested)
{ policy_apply_size_state(view, maximized, fullscreen, requested, false); }

static void policy_set_fullscreen(struct nextspace_toplevel *view, bool fullscreen, struct wlr_output *requested)
{
  /* Read the preserved axis state after rolling back any superseded move. */
  policy_cancel_interactive(view);
  policy_set_size_state(view, view->maximized, fullscreen, requested);
}

static void policy_finish(struct nextspace_server *server)
{
  struct nextspace_layer *layer, *temporary;
  wl_list_for_each_safe(layer, temporary, &server->layers, link) {
    wl_list_remove(&layer->link);
    free(layer);
  }
}
