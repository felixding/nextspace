/* Private, inherited capability for the prototype controller. MIT license.
 * Deliberately not a public Wayland global or a same-user control socket. */
static struct nextspace_toplevel *find_toplevel(struct nextspace_server *server, unsigned id)
{
  struct nextspace_toplevel *t;
  wl_list_for_each(t, &server->toplevels, link) if (t->id == id) return t;
  return NULL;
}

static bool apply_scale(struct nextspace_output *output, unsigned scale)
{
  if (scale < 60 || scale > 960) return false;
  struct wlr_output_state state;
  wlr_output_state_init(&state);
  wlr_output_state_set_scale(&state, scale / 120.0f);
  bool ok = wlr_output_test_state(output->wlr_output, &state) &&
    wlr_output_commit_state(output->wlr_output, &state);
  wlr_output_state_finish(&state);
  return ok;
}

static int rollback_scale(void *data)
{
  struct nextspace_server *server = data;
  if (server->pending_output) {
    if (!apply_scale(server->pending_output, (unsigned)roundf(server->previous_scale * 120)))
      wlr_log(WLR_ERROR, "Could not restore output scale");
    server->pending_output = NULL;
  }
  return 0;
}

static void json_string(FILE *f, const char *s)
{
  fputc('"', f);
  for (const unsigned char *p = (const unsigned char *)(s ? s : ""); *p; p++) {
    if (*p == '"' || *p == '\\') fprintf(f, "\\%c", *p);
    else if (*p < 32) fprintf(f, "\\u%04x", *p);
    else fputc(*p, f);
  }
  fputc('"', f);
}

static bool read_buffer_pixels(struct wlr_buffer *buffer, uint32_t samples[5], uint64_t counts[3], uint64_t *hash)
{
  struct wlr_client_buffer *client = buffer ? wlr_client_buffer_get(buffer) : NULL;
  if (client) buffer = client->source;
  void *pixels; uint32_t format; size_t stride;
  bool valid = false;
  if (buffer && wlr_buffer_begin_data_ptr_access(buffer, WLR_BUFFER_DATA_PTR_ACCESS_READ, &pixels, &format, &stride)) {
    if (format == DRM_FORMAT_ARGB8888 || format == DRM_FORMAT_XRGB8888) {
      for (int y = 0; y < 2; y++) for (int x = 0; x < 2; x++) {
        memcpy(&samples[y*2+x], (char *)pixels + stride * ((2*y+1) * buffer->height / 4) +
          sizeof(uint32_t) * ((2*x+1) * buffer->width / 4), sizeof(uint32_t));
      }
      memcpy(&samples[4], (char *)pixels + stride * (buffer->height / 2) +
        sizeof(uint32_t) * (buffer->width / 2), sizeof(uint32_t));
      if (format == DRM_FORMAT_XRGB8888) for (int i = 0; i < 5; i++) samples[i] |= 0xff000000;
      if (counts || hash) {
        if (counts) counts[0] = counts[1] = counts[2] = 0;
        if (hash) *hash = UINT64_C(14695981039346656037);
        for (int y = 0; y < buffer->height; y++) for (int x = 0; x < buffer->width; x++) {
          uint32_t pixel;
          memcpy(&pixel, (char *)pixels + stride * y + sizeof(uint32_t) * x, sizeof(pixel));
          if (format == DRM_FORMAT_XRGB8888) pixel |= 0xff000000;
          if (counts) counts[pixel == 0xff000000 ? 0 : pixel == 0xff204080 ? 1 : 2]++;
          if (hash) {
            for (unsigned shift = 0; shift < 32; shift += 8) {
              *hash ^= (pixel >> shift) & 255;
              *hash *= UINT64_C(1099511628211);
            }
          }
        }
      }
      valid = true;
    }
    wlr_buffer_end_data_ptr_access(buffer);
  }
  return valid;
}

static bool read_buffer_samples(struct wlr_buffer *buffer, uint32_t samples[5])
{ return read_buffer_pixels(buffer, samples, NULL, NULL); }

static void json_buffer_samples(FILE *f, struct wlr_buffer *buffer)
{
  uint32_t samples[5];
  if (read_buffer_samples(buffer, samples))
    fprintf(f, ",\"samples\":[%u,%u,%u,%u]", samples[0], samples[1], samples[2], samples[3]);
}

static void control_disconnect(struct nextspace_server *server)
{
  rollback_scale(server);
  wl_event_source_remove(server->control_source);
  server->control_source = NULL;
  close(server->control_fd);
  server->control_fd = -1;
}

static void find_headless_backend(struct wlr_backend *backend, void *data)
{
  struct wlr_backend **found = data;
  if (wlr_backend_is_headless(backend)) *found = backend;
}

static int control_ready(int fd, uint32_t mask, void *data)
{
  struct nextspace_server *server = data;
  char command[256], name[128], extra;
  ssize_t n = recv(fd, command, sizeof(command) - 1, MSG_TRUNC);
  if (n < 0 && (errno == EAGAIN || errno == EINTR)) return 0;
  if (n <= 0 || n >= (ssize_t)sizeof(command)) {
    control_disconnect(server);
    return 0;
  }
  command[n] = 0;
  char *response = NULL;
  size_t size = 0;
  FILE *f = open_memstream(&response, &size);
  if (!f) { control_disconnect(server); return 0; }
  unsigned id, scale, timeout;
  int x, y;
  if (strcmp(command, "lock-state") == 0) {
    session_lock_state_json(f, server);
  } else if (strcmp(command, "lock-surfaces") == 0) {
    session_lock_surfaces_json(f, server);
  } else if (strcmp(command, "add-output") == 0) {
    struct wlr_backend *headless = NULL;
    if (wlr_backend_is_multi(server->backend))
      wlr_multi_for_each_backend(server->backend, find_headless_backend, &headless);
    else find_headless_backend(server->backend, &headless);
    bool ok = headless && wlr_headless_add_output(headless, 1600, 1200);
    fprintf(f, "{\"ok\":%s}", ok ? "true" : "false");
  } else if (sscanf(command, "resize-output %127s %d %d %c", name, &x, &y, &extra) == 3) {
    bool ok = false;
    struct nextspace_output *output;
    wl_list_for_each(output, &server->outputs, link) {
      if (strcmp(name, output->wlr_output->name) != 0 ||
          !wlr_output_is_headless(output->wlr_output) || x < 128 || x > 8192 || y < 128 || y > 8192) continue;
      struct wlr_output_state state;
      wlr_output_state_init(&state);
      wlr_output_state_set_custom_mode(&state, x, y, 0);
      ok = wlr_output_test_state(output->wlr_output, &state) && wlr_output_commit_state(output->wlr_output, &state);
      wlr_output_state_finish(&state);
      break;
    }
    fprintf(f, "{\"ok\":%s}", ok ? "true" : "false");
  } else if (sscanf(command, "output-position %127s %d %d %c", name, &x, &y, &extra) == 3) {
    bool ok = false;
    struct nextspace_output *output;
    wl_list_for_each(output, &server->outputs, link) {
      if (strcmp(name, output->wlr_output->name) == 0 &&
          wlr_output_is_headless(output->wlr_output) && x >= -65536 && x <= 65536 && y >= -65536 && y <= 65536) {
        ok = wlr_output_layout_add(server->output_layout, output->wlr_output, x, y) != NULL;
        break;
      }
    }
    fprintf(f, "{\"ok\":%s}", ok ? "true" : "false");
  } else if (sscanf(command, "remove-output %127s %c", name, &extra) == 1) {
    struct nextspace_output *output;
    unsigned enabled = 0;
    wl_list_for_each(output, &server->outputs, link) enabled += output->wlr_output->enabled;
    bool ok = false;
    wl_list_for_each(output, &server->outputs, link) {
      if (strcmp(name, output->wlr_output->name) == 0 && enabled > 1 &&
          wlr_output_is_headless(output->wlr_output)) {
        wlr_output_destroy(output->wlr_output);
        ok = true;
        break;
      }
    }
    fprintf(f, "{\"ok\":%s}", ok ? "true" : "false");
  } else if (strcmp(command, "color-pick-state") == 0) {
    struct wlr_buffer *buffer = server->color_pick_cursor_buffer;
    fprintf(f, "{\"active\":%s,\"id\":%u,\"owner\":%u,\"selecting\":%s,\"buttons\":%u,\"density\":%d,\"seat_buttons\":%zu",
      server->color_pick_window ? "true" : "false", server->color_pick_id,
      server->color_pick_window && server->color_pick_window->view ? server->color_pick_window->view->id : 0,
      server->color_pick_selecting ? "true" : "false", server->color_pick_buttons,
      server->color_pick_density, server->seat->pointer_state.button_count);
    if (buffer) {
      uint32_t samples[5]; uint64_t hash;
      fprintf(f, ",\"width\":%d,\"height\":%d,\"hotspot_x\":12,\"hotspot_y\":13", buffer->width, buffer->height);
      if (read_buffer_pixels(buffer, samples, NULL, &hash))
        fprintf(f, ",\"pixels_hash\":\"%016llx\"", (unsigned long long)hash);
    }
    fputc('}', f);
  } else if (strcmp(command, "cursor-state") == 0) {
    struct wlr_surface *s = server->client_cursor;
    fprintf(f, "{\"visible\":%s,\"x\":%.3f,\"y\":%.3f", s && s->buffer ? "true" : "false",
      server->cursor->x, server->cursor->y);
    if (s && s->buffer) {
      fprintf(f, ",\"width\":%d,\"height\":%d,\"buffer_width\":%d,\"buffer_height\":%d,\"hotspot_x\":%d,\"hotspot_y\":%d",
        s->current.width, s->current.height, s->current.buffer_width, s->current.buffer_height,
        server->cursor_hotspot_x, server->cursor_hotspot_y);
      fputs(",\"outputs\":[", f);
      struct wlr_surface_output *cursor_output;
      bool first = true;
      wl_list_for_each(cursor_output, &s->current_outputs, link) {
        if (!first) fputc(',', f);
        first = false;
        json_string(f, cursor_output->output->name);
      }
      fputc(']', f);
      json_buffer_samples(f, s->buffer->source);
      uint32_t samples[5]; uint64_t hash;
      if (read_buffer_pixels(s->buffer->source, samples, NULL, &hash))
        fprintf(f, ",\"pixels_hash\":\"%016llx\"", (unsigned long long)hash);
    }
    fputc('}', f);
  } else if (strcmp(command, "selection-state") == 0) {
    fprintf(f, "{\"owned\":%s,\"pending\":%s,\"bytes\":%zu,\"writers\":%d,\"serial\":%u}",
      server->seat->selection_source && server->seat->selection_source->impl == &clipboard_impl ? "true" : "false",
      server->clipboard_copy ? "true" : "false", server->clipboard_bytes,
      wl_list_length(&server->clipboard_writes), server->seat->selection_serial);
  } else if (strcmp(command, "primary-selection-state") == 0) {
    fprintf(f, "{\"active\":%s,\"serial\":%u}", server->seat->primary_selection_source ? "true" : "false",
      server->seat->primary_selection_serial);
  } else if (strcmp(command, "selection") == 0 || strcmp(command, "primary-selection") == 0) {
    bool primary = strcmp(command, "primary-selection") == 0;
    struct wl_array *mimes = primary ? (server->seat->primary_selection_source ?
      &server->seat->primary_selection_source->mime_types : NULL) : (server->seat->selection_source ?
      &server->seat->selection_source->mime_types : NULL);
    fputc('[', f);
    if (mimes) {
      char **mime;
      bool first = true;
      wl_array_for_each(mime, mimes) {
        if (!first) fputc(',', f);
        json_string(f, *mime); first = false;
      }
    }
    fputc(']', f);
  } else if (strcmp(command, "desktops") == 0) {
    fprintf(f, "{\"current\":%u,\"count\":%u}", server->desktop, server->desktop_count);
  } else if (strcmp(command, "background-state") == 0) {
    struct wlr_scene_rect *background = server->background;
    fprintf(f, "{\"Red\":%.8f,\"Green\":%.8f,\"Blue\":%.8f,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}",
      background->color[0], background->color[1], background->color[2], background->node.x, background->node.y,
      background->width, background->height);
  } else if (strncmp(command, "sample-color ", 13) == 0) {
    double sample_x, sample_y; uint32_t argb = 0;
    bool ok = sscanf(command, "sample-color %lf %lf %c", &sample_x, &sample_y, &extra) == 2 &&
      scene_sample_color(server, sample_x, sample_y, &argb);
    fprintf(f, "{\"ok\":%s,\"argb\":%u}", ok ? "true" : "false", argb);
  } else if (sscanf(command, "output-pixels %127s %c", name, &extra) == 1) {
    struct nextspace_output *output;
    bool found = false;
    wl_list_for_each(output, &server->outputs, link) {
      if (strcmp(name, output->wlr_output->name) || !output->pixels_valid) continue;
      int width, height;
      wlr_output_transformed_resolution(output->wlr_output, &width, &height);
      fprintf(f, "{\"width\":%d,\"height\":%d,\"output_width\":%d,\"output_height\":%d,\"epoch\":%u,\"black\":%llu,\"locker\":%llu,\"other\":%llu}",
        output->pixel_width, output->pixel_height, width, height, output->pixel_epoch,
        (unsigned long long)output->pixel_counts[0], (unsigned long long)output->pixel_counts[1],
        (unsigned long long)output->pixel_counts[2]); found = true; break;
    }
    if (!found) fputs("{}", f);
  } else if (sscanf(command, "output-samples %127s %c", name, &extra) == 1) {
    struct nextspace_output *output;
    fputc('{', f);
    wl_list_for_each(output, &server->outputs, link) {
      if (strcmp(name, output->wlr_output->name) || !output->samples_valid) continue;
      uint32_t *samples = output->samples;
      fprintf(f, "\"samples\":[%u,%u,%u,%u],\"center\":%u",
        samples[0], samples[1], samples[2], samples[3], samples[4]);
      break;
    }
    fputc('}', f);
  } else if (strcmp(command, "outputs") == 0) {
    fputc('[', f);
    struct nextspace_output *output;
    bool first = true;
    wl_list_for_each(output, &server->outputs, link) {
      struct wlr_output *o = output->wlr_output;
      struct wlr_box box;
      wlr_output_layout_get_box(server->output_layout, o, &box);
      fprintf(f, "%s{\"name\":", first ? "" : ","); first = false;
      json_string(f, o->name);
      fprintf(f, ",\"scale\":%u,\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d",
        (unsigned)roundf(o->scale * 120), box.x, box.y, box.width, box.height);
      output_work_area(output, &box);
      fprintf(f, ",\"work_x\":%d,\"work_y\":%d,\"work_width\":%d,\"work_height\":%d}",
        box.x, box.y, box.width, box.height);
    }
    fputc(']', f);
  } else if (strcmp(command, "input-popups") == 0) {
    struct nextspace_input_popup *popup;
    bool first = true;
    fputc('[', f);
    wl_list_for_each(popup, &server->input_popups, link) {
      int px, py;
      if (!wlr_scene_node_coords(&popup->tree->node, &px, &py)) continue;
      struct wlr_surface_state *s = &popup->popup->surface->current;
      fprintf(f, "%s{\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d}",
        first ? "" : ",", px, py, s->width, s->height);
      first = false;
    }
    fputc(']', f);
  } else if (strcmp(command, "popups") == 0) {
    struct nextspace_popup *popup;
    bool first = true;
    fputc('[', f);
    wl_list_for_each_reverse(popup, &server->popups, link) {
      struct wlr_xdg_surface *xdg = popup->xdg_popup->base;
      if (!xdg->surface->mapped) continue;
      struct wlr_scene_tree *tree = xdg->data;
      int px, py;
      wlr_scene_node_coords(&tree->node, &px, &py);
      struct wlr_surface_state *s = &xdg->surface->current;
      fprintf(f, "%s{\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d,\"buffer_width\":%d,\"buffer_height\":%d}",
        first ? "" : ",", px, py, s->width, s->height, s->buffer_width, s->buffer_height);
      first = false;
    }
    fputc(']', f);
  } else if (strcmp(command, "windows") == 0) {
    fputc('[', f);
    struct nextspace_toplevel *t;
    bool first = true;
    wl_list_for_each(t, &server->toplevels, link) {
      struct wlr_surface_state *s = &view_surface(t)->current;
      struct wlr_scene_buffer *buffer = view_buffer(t);
      unsigned preferred = buffer && buffer->primary_output ?
        (unsigned)roundf(buffer->primary_output->output->scale * 120) : 0;
      fprintf(f, "%s{\"id\":%u,\"title\":", first ? "" : ",", t->id); first = false;
      json_string(f, view_title(t));
      fputs(",\"app_id\":", f); json_string(f, view_app_id(t));
      fprintf(f, ",\"pid\":%d", view_pid(t));
      fprintf(f, ",\"legacy\":false,\"level\":%d", t->level);
      fprintf(f, ",\"minimized\":%s", t->minimized ? "true" : "false");
      fprintf(f, ",\"maximized\":%s,\"fullscreen\":%s", t->maximized ? "true" : "false",
        t->fullscreen ? "true" : "false");
      fprintf(f, ",\"maximized_axes\":%u", t->maximized);
      fprintf(f, ",\"selected\":%s", t->selected ? "true" : "false");
      fprintf(f, ",\"presented\":%s", t->shell_hidden ? "false" : "true");
      fprintf(f, ",\"desktop\":%u,\"sticky\":%s,\"visible\":%s", t->desktop,
        t->sticky ? "true" : "false", policy_visible(t) ? "true" : "false");
      fprintf(f, ",\"shaded\":%s,\"client_id\":%u,\"style\":%u,\"title_height\":%u",
        t->shaded ? "true" : "false", t->client_id, t->style, t->title_height);
      fprintf(f, ",\"document_edited\":%s", t->document_edited ? "true" : "false");
      fprintf(f, ",\"title_state\":%u,\"client_title_state\":%u", decoration_title_state(t),
        t->application_window ? t->application_window->title_state : NEXTSPACE_WINDOW_V1_TITLE_STATE_NORMAL);
      fprintf(f, ",\"accepts_focus\":%s,\"focused\":%s",
        !t->application_window || t->application_window->accepts_focus ? "true" : "false",
        server->seat->keyboard_state.focused_surface == view_surface(t) ? "true" : "false");
      struct wlr_box geometry;
      view_geometry(t, &geometry);
      fprintf(f, ",\"frame_width\":%d,\"frame_height\":%d,\"server_decorated\":%s",
        geometry.width, geometry.height, decoration_visible(t) ? "true" : "false");
      fprintf(f, ",\"frame_left\":%d,\"frame_top\":%d,\"frame_right\":%d,\"frame_bottom\":%d",
        t->frame.left, t->frame.top, t->frame.right, t->frame.bottom);
      fprintf(f, ",\"surface_width\":%d,\"surface_height\":%d", s->width, s->height);
      if (s->viewport.has_src) fprintf(f, ",\"viewport_source\":[%.3f,%.3f,%.3f,%.3f]",
        s->viewport.src.x, s->viewport.src.y, s->viewport.src.width, s->viewport.src.height);
      if (t->decoration && t->decoration->title->buffer) {
        struct wlr_buffer *title = t->decoration->title->buffer;
        fprintf(f, ",\"decoration_scale\":%d,\"decoration_buffer_width\":%d,\"decoration_buffer_height\":%d",
          t->decoration->scale, title->width, title->height);
      }
      fprintf(f, ",\"x\":%d,\"y\":%d,\"width\":%d,\"height\":%d,\"buffer_width\":%d,\"buffer_height\":%d,\"preferred_scale\":%u}",
        t->scene_tree->node.x, t->scene_tree->node.y, geometry.width, geometry.height,
        s->buffer_width, s->buffer_height, preferred);
    }
    fputc(']', f);
  } else if (strcmp(command, "move-state") == 0) {
    fprintf(f, "{\"id\":%u,\"mode\":%u}", server->grabbed_toplevel ? server->grabbed_toplevel->id : 0,
      server->cursor_mode);
  } else if (strcmp(command, "drag-state") == 0) {
    struct wlr_drag *drag = server->seat->drag;
    bool icon = server->drag_icon != NULL;
    struct nextspace_toplevel *target = drag ? view_for_surface(server, drag->focus) : NULL;
    fprintf(f, "{\"active\":%s,\"icon\":%s,\"target\":%u,\"action\":%u",
      drag ? "true" : "false", icon ? "true" : "false", target ? target->id : 0,
      drag && drag->source ? drag->source->current_dnd_action : 0);
    if (drag && drag->icon) {
      struct wlr_surface *s = drag->icon->surface;
      fprintf(f, ",\"width\":%d,\"height\":%d,\"buffer_width\":%d,\"buffer_height\":%d",
        s->current.width, s->current.height, s->current.buffer_width, s->current.buffer_height);
      if (s->buffer) json_buffer_samples(f, s->buffer->source);
    }
    fputc('}', f);
  } else if (strcmp(command, "decoration-settings") == 0) {
    fprintf(f, "{\"double_click_time\":%u,\"title_appearance\":{\"font\":", server->double_click_time);
    json_string(f, server->title_font->description);
    fprintf(f, ",\"antialiased\":%s,\"justification\":%u,\"revision\":%u}}",
      server->title_font->antialiased ? "true" : "false", server->title_justification, server->title_revision);
  } else if (strcmp(command, "pointer-focus") == 0) {
    struct nextspace_toplevel *view = view_for_surface(server, server->seat->pointer_state.focused_surface);
    fprintf(f, "{\"id\":%u}", view ? view->id : 0);
  } else if (sscanf(command, "hit %d %d %c", &x, &y, &extra) == 2) {
    double sx, sy; struct wlr_surface *surface = NULL;
    struct nextspace_toplevel *view = desktop_toplevel_at(server, x, y, &surface, &sx, &sy);
    fprintf(f, "{\"id\":%u,\"popup\":%s}", view ? view->id : 0,
      surface && wlr_xdg_surface_try_from_wlr_surface(surface) &&
      wlr_xdg_surface_try_from_wlr_surface(surface)->role == WLR_XDG_SURFACE_ROLE_POPUP ? "true" : "false");
  } else if (sscanf(command, "pointer %d %d %c", &x, &y, &extra) == 2) {
    wlr_cursor_warp_closest(server->cursor, NULL, x, y);
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    process_cursor_motion(server, now.tv_sec * 1000 + now.tv_nsec / 1000000);
    wlr_seat_pointer_notify_frame(server->seat);
    fputs("{\"ok\":true}", f);
  } else if (strncmp(command, "button ", 7) == 0) {
    unsigned state;
    bool click = sscanf(command, "button %u %c", &id, &extra) == 1;
    bool ok = (click || (sscanf(command, "button %u %u %c", &id, &state, &extra) == 2 && state <= 1)) && id <= 767;
    if (ok) {
      struct timespec now;
      clock_gettime(CLOCK_MONOTONIC, &now);
      for (unsigned i = 0; i < (click ? 2u : 1u); i++) {
        struct wlr_pointer_button_event event = {
          .button = id, .state = click ? (i ? WL_POINTER_BUTTON_STATE_RELEASED : WL_POINTER_BUTTON_STATE_PRESSED) : state,
          .time_msec = now.tv_sec * 1000 + now.tv_nsec / 1000000 + i};
        server_cursor_button(&server->cursor_button, &event);
      }
      wlr_seat_pointer_notify_frame(server->seat);
    }
    fprintf(f, "{\"ok\":%s}", ok ? "true" : "false");
  } else if (sscanf(command, "scroll %d %c", &y, &extra) == 1 ||
      sscanf(command, "scroll-v120 %d %c", &y, &extra) == 1) {
    bool high_resolution = strncmp(command, "scroll-v120 ", 12) == 0;
    bool ok = y >= -10000 && y <= 10000;
    if (ok) {
      struct timespec now;
      clock_gettime(CLOCK_MONOTONIC, &now);
      struct wlr_pointer_axis_event event = {.time_msec = now.tv_sec * 1000 + now.tv_nsec / 1000000,
        .orientation = WL_POINTER_AXIS_VERTICAL_SCROLL, .delta = high_resolution ? y / 120.0 : y,
        .delta_discrete = high_resolution ? y : y * WLR_POINTER_AXIS_DISCRETE_STEP, .source = WL_POINTER_AXIS_SOURCE_WHEEL,
        .relative_direction = WL_POINTER_AXIS_RELATIVE_DIRECTION_IDENTICAL};
      server_cursor_axis(&server->cursor_axis, &event);
      wlr_seat_pointer_notify_frame(server->seat);
    }
    fprintf(f, "{\"ok\":%s}", ok ? "true" : "false");
  } else if (sscanf(command, "key %u %u %c", &id, &scale, &extra) == 2) {
    bool ok = id <= 767 && scale <= 1;
    if (ok) {
      struct timespec now;
      clock_gettime(CLOCK_MONOTONIC, &now);
      struct wlr_keyboard_key_event event = {.keycode = id, .state = scale,
        .update_state = true, .time_msec = now.tv_sec * 1000 + now.tv_nsec / 1000000};
      wlr_keyboard_notify_key(&server->control_keyboard, &event);
    }
    fprintf(f, "{\"ok\":%s}", ok ? "true" : "false");
  } else if (sscanf(command, "move %u %d %d %c", &id, &x, &y, &extra) == 3) {
    struct nextspace_toplevel *t = find_toplevel(server, id);
    bool found = t && x > -100000 && x < 100000 && y > -100000 && y < 100000;
    if (found) view_move(t, x, y);
    fprintf(f, "{\"ok\":%s}", found ? "true" : "false");
  } else if (sscanf(command, "resize %u %d %d %c", &id, &x, &y, &extra) == 3) {
    struct nextspace_toplevel *t = find_toplevel(server, id);
    bool ok = t && x > 0 && x <= 32768 && y > 0 && y <= 32768;
    if (ok) view_resize(t, x, y);
    fprintf(f, "{\"ok\":%s}", ok ? "true" : "false");
  } else if (sscanf(command, "present %u %u %c", &id, &scale, &extra) == 2) {
    struct nextspace_toplevel *t = shell_view(server, id);
    if (t) policy_set_presented(t, scale != 0);
    fprintf(f, "{\"ok\":%s}", t ? "true" : "false");
  } else if (sscanf(command, "shade %u %u %c", &id, &scale, &extra) == 2) {
    struct nextspace_toplevel *t = find_toplevel(server, id);
    if (t) policy_set_shaded(t, scale != 0);
    fprintf(f, "{\"ok\":%s}", t ? "true" : "false");
  } else if (sscanf(command, "minimize %u %u %c", &id, &scale, &extra) == 2) {
    struct nextspace_toplevel *t = find_toplevel(server, id);
    if (t) policy_set_minimized(t, scale != 0);
    fprintf(f, "{\"ok\":%s}", t ? "true" : "false");
  } else if (sscanf(command, "raise %u %c", &id, &extra) == 1) {
    struct nextspace_toplevel *t = shell_view(server, id);
    if (t) { policy_order(t, true, NULL); policy_refresh_pointer(server); }
    fprintf(f, "{\"ok\":%s}\n", t ? "true" : "false");
  } else if (sscanf(command, "focus %u %c", &id, &extra) == 1) {
    struct nextspace_toplevel *t = find_toplevel(server, id);
    if (t) focus_toplevel(t, view_surface(t));
    fprintf(f, "{\"ok\":%s}", t ? "true" : "false");
  } else if (sscanf(command, "close %u %c", &id, &extra) == 1) {
    struct nextspace_toplevel *t = find_toplevel(server, id);
    if (t) wlr_xdg_toplevel_send_close(t->xdg_toplevel);
    fprintf(f, "{\"ok\":%s}", t ? "true" : "false");
  } else if (sscanf(command, "test-scale %127s %u %u %c", name, &scale, &timeout, &extra) == 3) {
    struct nextspace_output *output;
    bool ok = false;
    if (!server->pending_output && !server->output_pending && timeout >= 100 && timeout <= 30000) {
      wl_list_for_each(output, &server->outputs, link) {
        if (strcmp(name, output->wlr_output->name) == 0) {
          float old = output->wlr_output->scale;
          if (apply_scale(output, scale)) {
            server->previous_scale = old;
            server->pending_output = output;
            wl_event_source_timer_update(server->rollback_timer, timeout);
            ok = true;
          }
          break;
        }
      }
    }
    fprintf(f, "{\"ok\":%s}", ok ? "true" : "false");
  } else if (strcmp(command, "confirm") == 0 && server->pending_output) {
    server->pending_output = NULL;
    wl_event_source_timer_update(server->rollback_timer, 0);
    fputs("{\"ok\":true}", f);
  } else if (sscanf(command, "fail-output-commit %u %c", &id, &extra) == 1 && id > 0 && id <= 64) {
    server->output_fail_after = id;
    fputs("{\"ok\":true}", f);
  } else if (strcmp(command, "quit") == 0) {
    fputs("{\"ok\":true}", f);
    wl_display_terminate(server->wl_display);
  } else fputs("{\"ok\":false}", f);
  fclose(f);
  if (send(fd, response, size, MSG_NOSIGNAL) != (ssize_t)size)
    control_disconnect(server);
  free(response);
  return 0;
}
