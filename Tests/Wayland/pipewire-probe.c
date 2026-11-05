/* Receive an actual portal-authorized PipeWire video frame. MIT license. */
#define _GNU_SOURCE
#include <sys/types.h>
#include <pipewire/pipewire.h>
#include <spa/param/video/format-utils.h>
#include <spa/param/buffers.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>

struct probe {
  struct pw_main_loop *loop;
  struct pw_stream *stream;
  struct spa_video_info_raw video;
  const char *path;
  bool captured, continuous;
  unsigned sequence;
};
static void state_changed(void *data, enum pw_stream_state old, enum pw_stream_state state, const char *error)
{
  struct probe *probe = data;
  if (state == PW_STREAM_STATE_ERROR) {
    fprintf(stderr, "PipeWire stream: %s\n", error); pw_main_loop_quit(probe->loop);
  }
}
static void param_changed(void *data, uint32_t id, const struct spa_pod *param)
{
  struct probe *probe = data;
  if (!param || id != SPA_PARAM_Format) return;
  if (spa_format_video_raw_parse(param, &probe->video) < 0) {
    pw_main_loop_quit(probe->loop); return;
  }
  uint8_t storage[512];struct spa_pod_builder builder=SPA_POD_BUILDER_INIT(storage,sizeof(storage));
  const struct spa_pod *params[]={spa_pod_builder_add_object(&builder,
    SPA_TYPE_OBJECT_ParamMeta,SPA_PARAM_Meta,
    SPA_PARAM_META_type,SPA_POD_Id(SPA_META_VideoTransform),
    SPA_PARAM_META_size,SPA_POD_Int(sizeof(struct spa_meta_videotransform))),
    spa_pod_builder_add_object(&builder,SPA_TYPE_OBJECT_ParamMeta,SPA_PARAM_Meta,
      SPA_PARAM_META_type,SPA_POD_Id(SPA_META_VideoDamage),
      SPA_PARAM_META_size,SPA_POD_Int(4*sizeof(struct spa_region)))};
  pw_stream_update_params(probe->stream,params,2);
}
static void process(void *data)
{
  struct probe *probe = data;
  struct pw_buffer *buffer = pw_stream_dequeue_buffer(probe->stream);
  if (!buffer) return;
  struct spa_buffer *spa = buffer->buffer;
  if ((!probe->captured || probe->continuous) && spa->n_datas && spa->datas[0].data && spa->datas[0].chunk) {
    struct spa_data *pixels = &spa->datas[0]; struct spa_chunk *chunk = pixels->chunk;
    size_t size = (size_t)chunk->stride * probe->video.size.height;
    if (probe->video.size.width && chunk->stride >= (int32_t)probe->video.size.width * 4 &&
        size && size <= chunk->size && chunk->offset <= pixels->maxsize && size <= pixels->maxsize-chunk->offset) {
      char path[4096]; unsigned sequence = ++probe->sequence;
      if (snprintf(path,sizeof(path),probe->continuous ? "%s.%u.raw" : "%s",probe->path,sequence) >= sizeof(path)) exit(1);
      FILE *file = fopen(path, "wb");
      bool written = file && fwrite((char *)pixels->data+chunk->offset,1,size,file)==size;
      if (file && fclose(file)) written = false;
      if (written) {
        probe->captured = true;
        struct spa_meta_videotransform *transform=spa_buffer_find_meta_data(spa,SPA_META_VideoTransform,sizeof(*transform));
        struct spa_region *damage=spa_buffer_find_meta_data(spa,SPA_META_VideoDamage,sizeof(*damage));
        printf("{\"width\":%u,\"height\":%u,\"stride\":%d,\"format\":%u,\"bytes\":%zu,\"sequence\":%u,\"transform\":%d,\"damage\":[%d,%d,%u,%u]}\n",
          probe->video.size.width,probe->video.size.height,chunk->stride,probe->video.format,size,sequence,
          transform ? (int)transform->transform : -1,damage ? damage->position.x : -1,
          damage ? damage->position.y : -1,damage ? damage->size.width : 0,damage ? damage->size.height : 0); fflush(stdout);
        if (!probe->continuous) pw_main_loop_quit(probe->loop);
      }
    }
  }
  pw_stream_queue_buffer(probe->stream,buffer);
}
static const struct pw_stream_events stream_events = {
  PW_VERSION_STREAM_EVENTS, .state_changed = state_changed, .param_changed = param_changed, .process = process
};
static void core_error(void *data, uint32_t id, int seq, int result, const char *message)
{
  struct probe *probe = data;
  fprintf(stderr,"PipeWire core: %s\n",message); pw_main_loop_quit(probe->loop);
}
static const struct pw_core_events core_events = {PW_VERSION_CORE_EVENTS, .error = core_error};
static void stop_signal(void *data, int signal)
{ pw_main_loop_quit(((struct probe *)data)->loop); }

int main(int argc, char **argv)
{
  if (argc!=4 && (argc!=5 || strcmp(argv[4],"--continuous"))) return 1;
  pw_init(&argc,&argv);
  struct probe probe = {.path=argv[3],.continuous=argc==5};
  probe.loop = pw_main_loop_new(NULL);
  pw_loop_add_signal(pw_main_loop_get_loop(probe.loop),SIGTERM,stop_signal,&probe);
  struct pw_context *context = pw_context_new(pw_main_loop_get_loop(probe.loop),NULL,0);
  struct pw_core *core = pw_context_connect_fd(context,atoi(argv[1]),NULL,0);
  if (!core) return 1;
  struct spa_hook core_listener;
  pw_core_add_listener(core,&core_listener,&core_events,&probe);
  probe.stream = pw_stream_new(core,"NextSpace portal frame probe",
    pw_properties_new(PW_KEY_MEDIA_TYPE,"Video",PW_KEY_MEDIA_CATEGORY,"Capture",PW_KEY_MEDIA_ROLE,"Screen",NULL));
  struct spa_hook stream_listener;
  pw_stream_add_listener(probe.stream,&stream_listener,&stream_events,&probe);
  uint8_t storage[1024]; struct spa_pod_builder builder = SPA_POD_BUILDER_INIT(storage,sizeof(storage));
  struct spa_rectangle def = SPA_RECTANGLE(801,601), min = SPA_RECTANGLE(1,1), max = SPA_RECTANGLE(16384,16384);
  const struct spa_pod *params[] = {spa_pod_builder_add_object(&builder,
    SPA_TYPE_OBJECT_Format,SPA_PARAM_EnumFormat,
    SPA_FORMAT_mediaType,SPA_POD_Id(SPA_MEDIA_TYPE_video),
    SPA_FORMAT_mediaSubtype,SPA_POD_Id(SPA_MEDIA_SUBTYPE_raw),
    SPA_FORMAT_VIDEO_format,SPA_POD_CHOICE_ENUM_Id(5,SPA_VIDEO_FORMAT_BGRx,SPA_VIDEO_FORMAT_BGRx,SPA_VIDEO_FORMAT_BGRA,
      SPA_VIDEO_FORMAT_RGBx,SPA_VIDEO_FORMAT_RGBA),
    SPA_FORMAT_VIDEO_size,SPA_POD_CHOICE_RANGE_Rectangle(&def,&min,&max))};
  int result = pw_stream_connect(probe.stream,PW_DIRECTION_INPUT,strtoul(argv[2],NULL,10),
    PW_STREAM_FLAG_AUTOCONNECT|PW_STREAM_FLAG_MAP_BUFFERS,params,1);
  if (result>=0) pw_main_loop_run(probe.loop);
  pw_stream_destroy(probe.stream);pw_core_disconnect(core);pw_context_destroy(context);pw_main_loop_destroy(probe.loop);
  pw_deinit();return probe.captured ? 0 : 1;
}
