/* Complete output transactions on the authorized shell connection. MIT license. */
struct output_head_state {
  uint32_t id, scale, transform;
  bool enabled, primary;
  int width, height, refresh, x, y;
};

struct output_configuration {
  struct nextspace_server *server;
  struct wl_resource *resource;
  uint32_t revision;
  struct output_head_state heads[64], previous[64];
  size_t count, previous_count;
  bool invalid, sealed, finished;
};

static struct nextspace_output *output_by_id(struct nextspace_server *server, uint32_t id)
{
  struct nextspace_output *output;
  wl_list_for_each(output, &server->outputs, link) if (output->id == id) return output;
  return NULL;
}

static size_t output_gamma_size(struct nextspace_output *output)
{
  if (!output->wlr_output->enabled) return 0;
  size_t size = wlr_output_get_gamma_size(output->wlr_output);
  return size >= 2 && size <= 65536 ? size : 0;
}

static bool output_apply_gamma(struct nextspace_output *output, struct output_gamma gamma)
{
  struct wlr_output_state state;
  wlr_output_state_init(&state);
  bool ok = output_gamma_state(&state, output_gamma_size(output), gamma) &&
    wlr_output_test_state(output->wlr_output, &state) &&
    wlr_output_commit_state(output->wlr_output, &state);
  wlr_output_state_finish(&state);
  if (ok) { output->gamma = gamma; output->gamma_set = true; }
  return ok;
}

static void output_work_area(struct nextspace_output *output, struct wlr_box *bounds)
{
  wlr_output_layout_get_box(output->server->output_layout, output->wlr_output, bounds);
  if (!output->wlr_output->enabled) { *bounds = (struct wlr_box){0}; return; }
  int *insets = output->insets;
  if (insets[0] + insets[2] <= bounds->width / 2) {
    bounds->x += insets[0]; bounds->width -= insets[0] + insets[2];
  }
  if (insets[1] + insets[3] <= bounds->height / 2) {
    bounds->y += insets[1]; bounds->height -= insets[1] + insets[3];
  }
}

static struct output_head_state output_current(struct nextspace_output *output)
{
  struct wlr_output *o = output->wlr_output;
  struct wlr_output_layout_output *layout = wlr_output_layout_get(output->server->output_layout, o);
  if (layout) { output->x = layout->x; output->y = layout->y; }
  return (struct output_head_state){.id = output->id, .enabled = o->enabled,
    .primary = output->id == output->server->primary_output_id,
    .width = o->width, .height = o->height, .refresh = o->refresh,
    .scale = (uint32_t)roundf(o->scale * 120), .transform = o->transform,
    .x = output->x, .y = output->y};
}

static void output_snapshot(struct nextspace_server *server)
{
  struct wl_resource *resource = server->shell_resource;
  if (!resource || wl_resource_get_version(resource) < 7) return;
  nextspace_shell_v1_send_outputs_reset(resource, server->output_revision);
  struct nextspace_output *output;
  wl_list_for_each(output, &server->outputs, link) {
    struct wlr_output *o = output->wlr_output;
    struct output_head_state h = output_current(output);
    struct wlr_box box;
    wlr_output_layout_get_box(server->output_layout, o, &box);
    nextspace_shell_v1_send_output(resource, h.id, o->name, h.enabled, h.primary,
      h.width, h.height, h.refresh, h.scale, h.transform, h.x, h.y, box.width, box.height);
    nextspace_shell_v1_send_output_identity(resource, h.id, o->make ?: "", o->model ?: "",
      o->serial ?: "", o->phys_width, o->phys_height);
    struct wlr_output_mode *mode;
    wl_list_for_each(mode, &o->modes, link)
      nextspace_shell_v1_send_output_mode(resource, h.id, mode->width, mode->height,
        mode->refresh, mode->preferred);
    if (wl_list_empty(&o->modes))
      nextspace_shell_v1_send_output_mode(resource, h.id, h.width, h.height, h.refresh, 1);
    if (wl_resource_get_version(resource) >= 13) {
      output_work_area(output, &box);
      nextspace_shell_v1_send_output_work_area(resource, h.id, box.x, box.y, box.width, box.height);
    }
    if (wl_resource_get_version(resource) >= 18)
      nextspace_shell_v1_send_output_gamma(resource, h.id, output_gamma_size(output),
        wl_fixed_from_double(output->gamma.red), wl_fixed_from_double(output->gamma.green),
        wl_fixed_from_double(output->gamma.blue), wl_fixed_from_double(output->gamma.brightness));
  }
  nextspace_shell_v1_send_outputs_done(resource);
}

static void output_publish_idle(void *data)
{
  struct nextspace_server *server = data;
  server->output_idle = NULL;
  output_snapshot(server);
}

static void outputs_changed(struct nextspace_server *server)
{
  if (server->output_applying || !server->output_timer) return;
  struct nextspace_output *primary = output_by_id(server, server->primary_output_id);
  if (!primary || !primary->wlr_output->enabled) {
    server->primary_output_id = 0;
    struct nextspace_output *output;
    wl_list_for_each(output, &server->outputs, link) if (output->wlr_output->enabled) {
      server->primary_output_id = output->id; break;
    }
  }
  if (++server->output_revision == 0) ++server->output_revision;
  application_work_areas(server);
  session_lock_layout_changed(server);
  if (!server->output_idle)
    server->output_idle = wl_event_loop_add_idle(wl_display_get_event_loop(server->wl_display),
      output_publish_idle, server);
}

static void output_committed(struct wl_listener *listener, void *data)
{
  struct nextspace_output *output = wl_container_of(listener, output, commit);
  struct wlr_output_event_commit *event = data;
  if (output->server->control_fd >= 0 && (event->state->committed & WLR_OUTPUT_STATE_BUFFER)) {
    output->samples_valid = read_buffer_pixels(event->state->buffer, output->samples,
      output->server->lock_pixel_check ? output->pixel_counts : NULL, NULL);
    output->pixels_valid = output->samples_valid && output->server->lock_pixel_check;
    if (output->pixels_valid) {
      output->pixel_width = event->state->buffer->width; output->pixel_height = event->state->buffer->height;
      output->pixel_epoch = output->server->lock_epoch;
    }
  }
  if (event->state->committed & (WLR_OUTPUT_STATE_MODE | WLR_OUTPUT_STATE_ENABLED |
      WLR_OUTPUT_STATE_SCALE | WLR_OUTPUT_STATE_TRANSFORM)) outputs_changed(output->server);
}

static void output_result(struct output_configuration *config, uint32_t status, const char *reason)
{
  if (config->resource)
    nextspace_output_configuration_v1_send_result(config->resource, status, reason);
}

/* Build the same backend-wide state for test, apply and rollback. On physical
 * outputs accept only advertised modes; a nested backend may test custom modes. */
static bool output_backend_state(struct nextspace_server *server, struct output_head_state *heads,
    size_t count, bool commit)
{
  struct wlr_backend_output_state states[64];
  size_t used = 0;
  bool valid = true;
  for (size_t i = 0; i < count; i++) {
    struct output_head_state *h = &heads[i];
    struct nextspace_output *output = output_by_id(server, h->id);
    if (!output) continue; /* A disconnected head cannot be restored. */
    struct wlr_output *o = output->wlr_output;
    struct wlr_backend_output_state *s = &states[used++];
    s->output = o;
    wlr_output_state_init(&s->base);
    wlr_output_state_set_enabled(&s->base, h->enabled);
    wlr_output_state_set_scale(&s->base, h->scale / 120.0f);
    wlr_output_state_set_transform(&s->base, h->transform);
    if (!h->enabled) continue;
    if (output->gamma_set && output_gamma_size(output))
      valid &= output_gamma_state(&s->base, output_gamma_size(output), output->gamma);
    struct wlr_output_mode *mode, *found = NULL;
    wl_list_for_each(mode, &o->modes, link)
      if (mode->width == h->width && mode->height == h->height && mode->refresh == h->refresh) {
        found = mode; break;
      }
    if (found) wlr_output_state_set_mode(&s->base, found);
    else if (wl_list_empty(&o->modes))
      wlr_output_state_set_custom_mode(&s->base, h->width, h->height, h->refresh);
    else valid = false;
  }
  /* Backend-wide DRM commits do not synthesize a modeset buffer like the
   * single-output helper does. Test with matching swapchains, then render the
   * scene into those same swapchains before committing the whole layout. */
  struct wlr_output_swapchain_manager manager;
  wlr_output_swapchain_manager_init(&manager, server->backend);
  bool ok = valid && used && wlr_output_swapchain_manager_prepare(&manager, states, used);
  if (ok && commit) {
    for (size_t i = 0; i < used && ok; i++) {
      if (!states[i].base.enabled) continue;
      struct wlr_scene_output *scene = wlr_scene_get_scene_output(server->scene, states[i].output);
      struct wlr_scene_output_state_options options = {
        .swapchain = wlr_output_swapchain_manager_get_swapchain(&manager, states[i].output),
      };
      ok = scene && wlr_scene_output_build_state(scene, &states[i].base, &options);
    }
  }
  if (ok && commit) {
    if (server->output_fail_after) {
      unsigned partial = server->output_fail_after;
      server->output_fail_after = 0;
      for (size_t i = 0; i < used && i < partial; i++)
        wlr_output_commit_state(states[i].output, &states[i].base);
      ok = false;
    } else ok = wlr_backend_commit(server->backend, states, used);
    if (ok) wlr_output_swapchain_manager_apply(&manager);
    /* Enabling a DRM head can allocate its CRTC for the first time. Its ramp
       size is then available only after the mode commit. */
    for (size_t i = 0; i < used && ok; i++) {
      struct nextspace_output *output;
      wl_list_for_each(output, &server->outputs, link)
        if (output->wlr_output == states[i].output && output->wlr_output->enabled &&
            output->gamma_set && !(states[i].base.committed & WLR_OUTPUT_STATE_GAMMA_LUT))
          ok = output_apply_gamma(output, output->gamma);
    }
  }
  for (size_t i = 0; i < used; i++) wlr_output_state_finish(&states[i].base);
  wlr_output_swapchain_manager_finish(&manager);
  return ok;
}

static void output_place(struct nextspace_server *server, struct output_head_state *heads, size_t count)
{
  server->primary_output_id = 0;
  for (size_t i = 0; i < count; i++) {
    struct output_head_state *h = &heads[i];
    struct nextspace_output *output = output_by_id(server, h->id);
    if (!output) continue;
    output->x = h->x; output->y = h->y;
    if (output->wlr_output->enabled) {
      struct wlr_output_layout_output *layout =
        wlr_output_layout_add(server->output_layout, output->wlr_output, h->x, h->y);
      struct wlr_scene_output *scene = wlr_scene_get_scene_output(server->scene, output->wlr_output);
      if (layout && scene) wlr_scene_output_layout_add_output(server->scene_layout, layout, scene);
      if (h->primary) server->primary_output_id = h->id;
    } else wlr_output_layout_remove(server->output_layout, output->wlr_output);
  }
}

static void output_finish_layout(struct nextspace_server *server)
{
  server->output_applying = false;
  /* Recover windows only after every output has its final bounds. */
  application_layout_changed(&server->layout_change, NULL);
  policy_refresh_pointer(server);
}

static void output_revert_as(struct nextspace_server *server, const char *reason, uint32_t status)
{
  struct output_configuration *config = server->output_pending;
  if (!config) return;
  server->output_pending = NULL;
  wl_event_source_timer_update(server->output_timer, 0);
  server->output_applying = true;
  /* If the only previously enabled monitor disappeared, keep a surviving head
   * usable instead of restoring an entirely dark layout. */
  bool enabled = false;
  struct output_head_state *fallback = NULL;
  for (size_t i = 0; i < config->previous_count; i++) {
    struct output_head_state *h = &config->previous[i];
    if (!output_by_id(server, h->id)) continue;
    if (!fallback) fallback = h;
    enabled |= h->enabled;
  }
  if (!enabled && fallback) { fallback->enabled = true; fallback->primary = true; }
  bool restored = output_backend_state(server, config->previous, config->previous_count, true);
  output_place(server, config->previous, config->previous_count);
  output_finish_layout(server);
  config->finished = true;
  output_result(config, restored ? status : NEXTSPACE_OUTPUT_CONFIGURATION_V1_STATUS_FAILED, restored ? reason : "rollback commit failed");
  if (!restored) wlr_log(WLR_ERROR, "Output rollback failed: %s", reason);
}

static void output_revert(struct nextspace_server *server, const char *reason)
{ output_revert_as(server, reason, NEXTSPACE_OUTPUT_CONFIGURATION_V1_STATUS_REVERTED); }

static int output_timeout(void *data)
{ output_revert(data, "confirmation timed out"); return 0; }

static void output_config_destroy(struct wl_resource *resource)
{
  struct output_configuration *config = wl_resource_get_user_data(resource);
  config->resource = NULL;
  if (config->server->output_pending == config) output_revert(config->server, "settings disconnected");
  free(config);
}

static void output_config_head(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, uint32_t enabled, uint32_t primary, int32_t width, int32_t height,
    int32_t refresh, uint32_t scale, uint32_t transform, int32_t x, int32_t y)
{
  struct output_configuration *config = wl_resource_get_user_data(resource);
  if (config->sealed || config->finished) { config->invalid = true; return; }
  if (config->count == 64 || !output_by_id(config->server, id) || enabled > 1 || primary > 1 ||
      width < 16 || height < 16 || width > 16384 || height > 16384 || refresh < 0 || refresh > 1000000 ||
      scale < 60 || scale > 960 || transform > WL_OUTPUT_TRANSFORM_FLIPPED_270 ||
      x < -65536 || x > 65536 || y < -65536 || y > 65536) {
    config->invalid = true; return;
  }
  for (size_t i = 0; i < config->count; i++) if (config->heads[i].id == id) {
    config->invalid = true; return;
  }
  config->heads[config->count++] = (struct output_head_state){.id = id, .enabled = enabled,
    .primary = primary, .width = width, .height = height, .refresh = refresh,
    .scale = scale, .transform = transform, .x = x, .y = y};
}

static bool output_config_validate(struct output_configuration *config)
{
  struct nextspace_server *server = config->server;
  unsigned enabled = 0, primary = 0;
  if (config->finished || config->invalid || config->revision != server->output_revision ||
      config->count != (size_t)wl_list_length(&server->outputs) ||
      server->output_pending || server->pending_output) return false;
  for (size_t i = 0; i < config->count; i++) {
    struct output_head_state *h = &config->heads[i];
    if (!output_by_id(server, h->id) || (h->primary && !h->enabled)) return false;
    enabled += h->enabled; primary += h->primary;
  }
  return enabled && primary == 1;
}

static void output_config_test(struct wl_client *client, struct wl_resource *resource)
{
  struct output_configuration *config = wl_resource_get_user_data(resource);
  bool ok = !config->sealed && output_config_validate(config) &&
    output_backend_state(config->server, config->heads, config->count, false);
  config->sealed = true;
  if (!ok) config->finished = true;
  output_result(config, ok ? NEXTSPACE_OUTPUT_CONFIGURATION_V1_STATUS_TESTED :
    NEXTSPACE_OUTPUT_CONFIGURATION_V1_STATUS_FAILED, ok ? "" : "invalid, stale or unsupported layout");
}

static void output_config_apply(struct wl_client *client, struct wl_resource *resource, uint32_t timeout)
{
  struct output_configuration *config = wl_resource_get_user_data(resource);
  struct nextspace_server *server = config->server;
  config->sealed = true;
  if (timeout < 1000 || timeout > 30000 || !output_config_validate(config) ||
      !output_backend_state(server, config->heads, config->count, false)) {
    config->finished = true;
    output_result(config, NEXTSPACE_OUTPUT_CONFIGURATION_V1_STATUS_FAILED, "invalid, stale or unsupported layout");
    return;
  }
  struct nextspace_output *output;
  wl_list_for_each(output, &server->outputs, link)
    config->previous[config->previous_count++] = output_current(output);
  server->output_applying = true;
  server->output_pending = config;
  if (!output_backend_state(server, config->heads, config->count, true)) {
    output_revert_as(server, "commit failed", NEXTSPACE_OUTPUT_CONFIGURATION_V1_STATUS_FAILED); return;
  }
  output_place(server, config->heads, config->count);
  output_finish_layout(server);
  wl_event_source_timer_update(server->output_timer, timeout);
  output_result(config, NEXTSPACE_OUTPUT_CONFIGURATION_V1_STATUS_APPLIED, "");
}

static void output_config_confirm(struct wl_client *client, struct wl_resource *resource)
{
  struct output_configuration *config = wl_resource_get_user_data(resource);
  if (config->server->output_pending != config) return;
  config->server->output_pending = NULL;
  wl_event_source_timer_update(config->server->output_timer, 0);
  config->finished = true;
  output_result(config, NEXTSPACE_OUTPUT_CONFIGURATION_V1_STATUS_CONFIRMED, "");
}

static void output_config_cancel(struct wl_client *client, struct wl_resource *resource)
{
  struct output_configuration *config = wl_resource_get_user_data(resource);
  if (config->server->output_pending == config) output_revert(config->server, "cancelled");
  else if (!config->finished) {
    config->finished = true;
    output_result(config, NEXTSPACE_OUTPUT_CONFIGURATION_V1_STATUS_REVERTED, "cancelled before apply");
  }
}

static const struct nextspace_output_configuration_v1_interface output_config_impl = {
  .destroy = destroy_application_object, .set_head = output_config_head, .test = output_config_test,
  .apply = output_config_apply, .confirm = output_config_confirm, .cancel = output_config_cancel
};

static void shell_configure_outputs(struct wl_client *client, struct wl_resource *resource,
    uint32_t id, uint32_t revision)
{
  struct nextspace_server *server = wl_resource_get_user_data(resource);
  struct output_configuration *config = calloc(1, sizeof(*config));
  if (!config) { wl_client_post_no_memory(client); return; }
  config->server = server; config->revision = revision;
  config->resource = wl_resource_create(client, &nextspace_output_configuration_v1_interface, 1, id);
  if (!config->resource) { free(config); wl_client_post_no_memory(client); return; }
  wl_resource_set_implementation(config->resource, &output_config_impl, config, output_config_destroy);
}

static void shell_output_snapshot(struct wl_client *client, struct wl_resource *resource)
{ output_snapshot(wl_resource_get_user_data(resource)); }
