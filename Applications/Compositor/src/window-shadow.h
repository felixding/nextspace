/* One shared window-shadow renderer for server-decorated applications. MIT. */
enum { WINDOW_SHADOW_MARGIN = 16, WINDOW_SHADOW_TILE = 64 };

static bool window_shadow_accepts_input(struct wlr_scene_buffer *buffer,
    double *x, double *y)
{ (void)buffer; (void)x; (void)y; return false; }

static struct decoration_buffer *window_shadow_render(int scale)
{
  struct decoration_buffer *buffer = calloc(1, sizeof(*buffer));
  if (!buffer) return NULL;
  int pixels = ns_buffer_extent(WINDOW_SHADOW_TILE, scale);
  buffer->image = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, pixels, pixels);
  if (cairo_surface_status(buffer->image) != CAIRO_STATUS_SUCCESS) {
    cairo_surface_destroy(buffer->image); free(buffer); return NULL;
  }
  unsigned char *data = cairo_image_surface_get_data(buffer->image);
  int stride = cairo_image_surface_get_stride(buffer->image);
  /* The Gaussian integral is separable for a rectangle. Evaluate it once
   * in logical units, then stretch only its constant edges and center.
   * libc owns erf; there is no density table or per-application artwork. */
  const double sigma = 5, opacity = .35, divisor = sigma * M_SQRT2;
  for (int y = 0; y < pixels; y++) {
    double py = (y + .5) * 120. / scale;
    double ay = .5 * (erf((py - 16) / divisor) - erf((py - 48) / divisor));
    uint32_t *row = (uint32_t *)(data + y * stride);
    for (int x = 0; x < pixels; x++) {
      double px = (x + .5) * 120. / scale;
      double ax = .5 * (erf((px - 16) / divisor) - erf((px - 48) / divisor));
      row[x] = (uint32_t)lround(255 * opacity * ax * ay) << 24;
    }
  }
  cairo_surface_mark_dirty(buffer->image);
  wlr_buffer_init(&buffer->base, &decoration_buffer_impl, pixels, pixels);
  return buffer;
}

static void window_shadow_update(struct nextspace_decoration *frame,
    int width, int height, int scale)
{
  struct nextspace_toplevel *view = frame->view;
  bool visible = !view->fullscreen && !view->maximized && width > 0 && height > 0;
  for (int n = 0; n < 9; n++) wlr_scene_node_set_enabled(&frame->shadow[n]->node, visible);
  if (!visible) return;
  if (frame->shadow_scale != scale) {
    struct decoration_buffer *buffer = window_shadow_render(scale);
    if (!buffer) {
      for (int n = 0; n < 9; n++) wlr_scene_node_set_enabled(&frame->shadow[n]->node, false);
      return;
    }
    for (int n = 0; n < 9; n++) wlr_scene_buffer_set_buffer(frame->shadow[n], &buffer->base);
    wlr_buffer_drop(&buffer->base);
    frame->shadow_scale = scale;
  }
  int pixels = ns_buffer_extent(WINDOW_SHADOW_TILE, scale), middle = pixels / 2;
  double source[3] = {0, middle, middle + 1};
  double extent[3] = {middle, 1, pixels - middle - 1};
  int corner_x = width < 32 ? (width + 32) / 2 : 32;
  int corner_y = height < 32 ? (height + 32) / 2 : 32;
  int sizes_x[3] = {corner_x, width + 32 - 2 * corner_x, corner_x};
  int sizes_y[3] = {corner_y, height + 32 - 2 * corner_y, corner_y};
  int top = 3 - WINDOW_SHADOW_MARGIN;
  for (int row = 0; row < 3; row++) {
    int left = 3 - WINDOW_SHADOW_MARGIN;
    for (int col = 0; col < 3; col++) {
      struct wlr_scene_buffer *part = frame->shadow[row * 3 + col];
      struct wlr_fbox crop = {source[col], source[row], extent[col], extent[row]};
      wlr_scene_node_set_enabled(&part->node, sizes_x[col] > 0 && sizes_y[row] > 0);
      wlr_scene_buffer_set_source_box(part, &crop);
      wlr_scene_buffer_set_dest_size(part, sizes_x[col], sizes_y[row]);
      wlr_scene_node_set_position(&part->node, left, top);
      left += sizes_x[col];
    }
    top += sizes_y[row];
  }
}
