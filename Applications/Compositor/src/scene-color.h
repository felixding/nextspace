/* Cursor-independent scene sampling. MIT; raster-box/texture handling follows
 * the pinned wlroots 0.18.2 scene renderer (see LICENSE.wlroots). */
#include <limits.h>
#include <math.h>
#include <wlr/render/drm_format_set.h>
#include <wlr/render/pass.h>
#include <wlr/types/wlr_buffer.h>
#include <wlr/util/transform.h>

struct scene_color_render {
  struct nextspace_server *server;
  struct wlr_render_pass *pass;
  struct wl_array textures;
  int output_x, output_y, pixel_x, pixel_y;
  float scale;
};

static bool scene_color_box(struct scene_color_render *render, int x, int y,
    int width, int height, struct wlr_box *box)
{
  double left = round((x - (double)render->output_x) * render->scale);
  double top = round((y - (double)render->output_y) * render->scale);
  double right = round((x - (double)render->output_x + width) * render->scale);
  double bottom = round((y - (double)render->output_y + height) * render->scale);
  left -= render->pixel_x; right -= render->pixel_x;
  top -= render->pixel_y; bottom -= render->pixel_y;
  if (left < INT_MIN || top < INT_MIN || right > INT_MAX || bottom > INT_MAX ||
      right - left > INT_MAX || bottom - top > INT_MAX) return false;
  *box = (struct wlr_box){left, top, right-left, bottom-top};
  return true;
}

static struct wlr_texture *scene_color_texture(struct scene_color_render *render,
    struct wlr_scene_buffer *buffer)
{
  /* wlroots keeps imported textures after releasing a scene buffer's source.
   * Read its pinned cache, without changing ownership or scene state. */
  if (buffer->texture) return buffer->texture;
  if (!buffer->buffer) return NULL;
  struct wlr_client_buffer *client = wlr_client_buffer_get(buffer->buffer);
  if (client) return client->texture;
  struct wlr_texture *texture = wlr_texture_from_buffer(render->server->renderer, buffer->buffer);
  if (!texture) return NULL;
  struct wlr_texture **owned = wl_array_add(&render->textures, sizeof(*owned));
  if (!owned) { wlr_texture_destroy(texture); return NULL; }
  *owned = texture;
  return texture;
}

static bool scene_color_node(struct scene_color_render *render,
    struct wlr_scene_node *node, int parent_x, int parent_y)
{
  if (!node->enabled) return true;
  int x = parent_x + node->x, y = parent_y + node->y;
  if (node->type == WLR_SCENE_NODE_TREE) {
    struct wlr_scene_node *child;
    wl_list_for_each(child, &wlr_scene_tree_from_node(node)->children, link)
      if (!scene_color_node(render, child, x, y)) return false;
    return true;
  }
  struct wlr_scene_rect *rect = NULL;
  struct wlr_scene_buffer *buffer = NULL;
  int width, height;
  if (node->type == WLR_SCENE_NODE_RECT) {
    rect = wlr_scene_rect_from_node(node);
    width = rect->width; height = rect->height;
  } else {
    buffer = wlr_scene_buffer_from_node(node);
    if (!buffer->opacity) return true;
    width = buffer->dst_width; height = buffer->dst_height;
    if (!width || !height) {
      width = buffer->buffer_width; height = buffer->buffer_height;
      if (buffer->transform & 1) { int swap = width; width = height; height = swap; }
    }
  }
  struct wlr_box box;
  if (!scene_color_box(render, x, y, width, height, &box)) return false;
  if (box.x > 0 || box.y > 0 || (int64_t)box.x + box.width <= 0 ||
      (int64_t)box.y + box.height <= 0) return true;
  if (rect) {
    wlr_render_pass_add_rect(render->pass, &(struct wlr_render_rect_options){
      .box = box, .color = {rect->color[0], rect->color[1], rect->color[2], rect->color[3]},
    });
  } else {
    struct wlr_texture *texture = scene_color_texture(render, buffer);
    if (!texture) return false;
    wlr_render_pass_add_texture(render->pass, &(struct wlr_render_texture_options){
      .texture = texture, .src_box = buffer->src_box, .dst_box = box,
      .transform = wlr_output_transform_invert(buffer->transform),
      .alpha = &buffer->opacity, .filter_mode = buffer->filter_mode,
    });
  }
  return true;
}

static bool scene_sample_color(struct nextspace_server *server,
    double x, double y, uint32_t *argb)
{
  if (server->locked || !isfinite(x) || !isfinite(y)) return false;
  struct wlr_output *output = wlr_output_layout_output_at(server->output_layout, x, y);
  if (!output || !output->enabled) return false;
  struct wlr_box bounds;
  wlr_output_layout_get_box(server->output_layout, output, &bounds);
  if (!server->color_sample_buffer) {
    uint64_t modifier = DRM_FORMAT_MOD_LINEAR;
    const struct wlr_drm_format format = {
      .format = DRM_FORMAT_ARGB8888, .len = 1, .modifiers = &modifier,
    };
    server->color_sample_buffer = wlr_allocator_create_buffer(server->allocator, 1, 1, &format);
    if (!server->color_sample_buffer) return false;
  }
  struct scene_color_render render = {
    .server = server, .scale = output->scale, .output_x = bounds.x, .output_y = bounds.y,
    .pixel_x = floor((x-bounds.x)*output->scale), .pixel_y = floor((y-bounds.y)*output->scale),
  };
  wl_array_init(&render.textures);
  render.pass = wlr_renderer_begin_buffer_pass(server->renderer, server->color_sample_buffer, NULL);
  if (!render.pass) return false;
  wlr_render_pass_add_rect(render.pass, &(struct wlr_render_rect_options){
    .box = {0,0,1,1}, .color = {0,0,0,1}, .blend_mode = WLR_RENDER_BLEND_MODE_NONE,
  });
  bool ok = scene_color_node(&render, &server->scene->tree.node, 0, 0);
  bool submitted = wlr_render_pass_submit(render.pass);
  struct wlr_texture **owned;
  wl_array_for_each(owned, &render.textures) wlr_texture_destroy(*owned);
  wl_array_release(&render.textures);
  if (!ok || !submitted) return false;
  struct wlr_texture *texture = wlr_texture_from_buffer(server->renderer, server->color_sample_buffer);
  if (!texture) return false;
  ok = wlr_texture_read_pixels(texture, &(struct wlr_texture_read_pixels_options){
    .data = argb, .format = DRM_FORMAT_ARGB8888, .stride = sizeof(*argb),
    .src_box = {0,0,1,1},
  });
  wlr_texture_destroy(texture);
  return ok;
}
