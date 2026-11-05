/* Input-button model and display-list ownership. All title drawing and input
 * remain in the shared NSButton provider. No HTML label renderer is copied. */
struct GeckoString {const uint16_t *data;uint32_t length;uint16_t flags,class_flags;};
_Static_assert(sizeof(struct GeckoString)==16,"Pinned Gecko substring layout");
static __thread void *label_owner;
static void (*original_block_display)(void *,void *,const void *);
static void (*original_text_display)(void *,void *,const void *);
static int native_button_frame(const void *frame) {
  if(!buttons_enabled||!frame||*(const uintptr_t *)frame!=base+0xa10bd38+16||frame_kind(frame)!=NXS_BUTTON)return 0;
  const void *style=*(void *const *)((const char *)frame+32);
  const void *display=*(void *const *)((const char *)style+80);
  if(!*((const unsigned char *)display+6))return 0;
  void *context=*(void *const *)((const char *)frame+40);
  void *theme=((void *(*)(const void *))(base+0x370c190))(context);
  return theme&&((int (*)(void *,void *,const void *,unsigned))(base+0x6a60e78))(theme,context,frame,10);
}
static char *button_title(const struct Widget *w) {
  if(!native_button_frame(w->frame))return NULL;
  static const uint16_t empty;
  struct GeckoString label={.data=&empty,.flags=1};
  ((void (*)(void *,void *))(base+0x6eedb5c))(w->frame,&label);
  char *result=utf8_text(label.data,label.length);
  ((void (*)(void *))(base+0x3826f2c))(&label);
  return result;
}
static int button_cache_update(struct Widget *w,const struct NXSResponse *response) {
  if(!response||response->width<1||response->height<1||response->width>8192||response->height>8192||
     response->stride!=response->width*4||sizeof(*response)+(size_t)response->stride*response->height!=response->size)return 0;
  uint32_t *pixels=malloc((size_t)response->stride*response->height);if(!pixels)return 0;
  memcpy(pixels,response+1,(size_t)response->stride*response->height);free(w->button_pixels);
  w->button_pixels=pixels;w->button_width=response->width;w->button_height=response->height;return 1;
}
static int button_cache_available(const struct Widget *w) {return w&&w->button_pixels;}
static void release_button_frame(void *frame) {
  reset_widget_process();
  struct Widget **cursor=&widgets;while(*cursor&&(*cursor)->frame!=frame)cursor=&(*cursor)->next;
  if(*cursor&&(*cursor)->kind==NXS_BUTTON)forget_widget(cursor);
}
static int prepare_button_image(void *frame) {
  float scale=frame_scale(frame);
  if(!native_button_frame(frame)||!isfinite(scale)||fabsf(scale-1)>0.000001f) {
    release_button_frame(frame);return 0;
  }
  struct Widget *w=bind_widget(frame);if(!w)return 0;
  int rectangle[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,rectangle);
  double width=rectangle[2]/60.,height=rectangle[3]/60.;
  if(width<1||height<1||width>8192||height>8192||width!=floor(width)||height!=floor(height)) {
    release_button_frame(frame);return 0;
  }
  w->width=width;w->height=height;
  /* Refresh for this display-list transaction. Keep a complete native title
   * and bezel snapshot if the service disappears before the item is painted.
   * A later failed preparation restores Gecko's whole background and label. */
  struct NXSResponse *response=widget_sync(w);
  if(!response||!button_cache_available(w)) {
    release_button_frame(frame);return 0;
  }
  w->button_label_owned=1;return 1;
}
static void block_display(void *frame,void *builder,const void *lists) {
  void *previous=label_owner;
  if(frame_kind(frame)==NXS_BUTTON)label_owner=prepare_button_image(frame)?frame:NULL;
  original_block_display(frame,builder,lists);label_owner=previous;
}
static void text_display(void *frame,void *builder,const void *lists) {
  if(label_owner&&*(void **)((char *)frame+24)==*(void **)((char *)label_owner+200))return;
  original_text_display(frame,builder,lists);
}
static struct Detour button_detours[]={
  {NXS_GECKO_BLOCK_DISPLAY_OFFSET,gecko_block_display_bytes,block_display,(void **)&original_block_display},
  {NXS_GECKO_TEXT_DISPLAY_OFFSET,gecko_text_display_bytes,text_display,(void **)&original_text_display}
};
