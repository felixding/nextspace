/* Button model and display-list ownership. All title drawing and input
 * remain in the shared NSButton provider. No HTML label renderer is copied. */
struct GeckoString {const uint16_t *data;uint32_t length;uint16_t flags,class_flags;};
_Static_assert(sizeof(struct GeckoString)==16,"Pinned Gecko substring layout");
static __thread void *label_owner;
static void (*original_block_display)(void *,void *,const void *);
static void (*original_text_display)(void *,void *,const void *);
#include "pinned-button-size.h"
struct LogicalSizeI {int inline_size,block_size;};
struct IntrinsicOffsetsI {int padding,border,margin;};
static int popup_preferred(void *,struct LogicalSizeI *);
_Static_assert(sizeof(struct LogicalSizeI)==8,"Pinned Gecko logical size ABI");
_Static_assert(sizeof(struct IntrinsicOffsetsI)==12,"Pinned Gecko intrinsic offsets ABI");
static struct LogicalSizeI (*original_button_auto_size)(void *,const void *,unsigned,
  const void *,int,const void *,const struct LogicalSizeI *,const void *,unsigned);
static int (*original_button_intrinsic)(void *,const void *,unsigned);
static int (*original_button_flex_intrinsic)(void *,const void *,unsigned);
static int (*original_button_grid_intrinsic)(void *,const void *,unsigned);
static int native_button_frame(const void *frame) {
  if(!buttons_enabled||!frame||frame_kind(frame)!=NXS_BUTTON)return 0;
  void *node=*(void **)((const char *)frame+24);
  if(html_button_node(node)) {
    if(*(void **)((char *)node+96)!=frame)return 0;
  } else if(*(const uintptr_t *)frame!=base+0xa10bd38+16)return 0;
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
  if(html_button_node(w->node)) {
    /* Reuse Gecko's rendered-text accessor: whitespace, hidden descendants,
     * Unicode and line boundaries stay with the engine. Never flush layout
     * recursively from a native measurement or display-list transaction. */
    struct GeckoError error={0};
    ((void (*)(void *,void *,void *))(base+NXS_GECKO_HTML_BUTTON_INNER_TEXT_OFFSET))(&label,&error,w->node);
    int failed=!!(error.result&0x80000000u);clear_text_error(&error);
    if(failed){((void (*)(void *))(base+0x3826f2c))(&label);return NULL;}
  } else ((void (*)(void *,void *))(base+0x6eedb5c))(w->frame,&label);
  char *result=utf8_text(label.data,label.length);
  ((void (*)(void *))(base+0x3826f2c))(&label);
  return result;
}
static int button_preferred(void *frame,struct LogicalSizeI *size) {
  float scale=frame_scale(frame);
  if(!native_button_frame(frame)||!isfinite(scale)||fabsf(scale-1)>0.000001f||
     (*((const unsigned char *)frame+108)&1))return 0;
  if(html_button_node(*(void **)((char *)frame+24))) {
    /* Before the first layout, rendered text is not a complete label yet.
     * Use the native metrics supplied by the last complete display model. */
    struct Widget *w=widget_for_frame(frame);
    if(!w||w->button_preferred_width<1||w->button_preferred_height<1)return 0;
    *size=(struct LogicalSizeI){ceil(w->button_preferred_width)*60,ceil(w->button_preferred_height)*60};return 1;
  }
  struct Widget *w=bind_widget(frame);if(!w)return 0;
  struct NXSResponse *response=widget_sync(w);if(!response)return 0;
  double width=response->parts[1].width,height=response->parts[1].height;
  if(!isfinite(width)||!isfinite(height)||width<1||height<1||width>8192||height>8192)return 0;
  *size=(struct LogicalSizeI){ceil(width)*60,ceil(height)*60};
  return 1;
}
/* Gecko owns shrink-to-fit, explicit sizes, min/max, flex/grid and box sizing.
 * Supply native cell metrics at its existing intrinsic/auto-size boundaries;
 * ask its own offset accessor for the content-to-border-box conversion. */
static int button_intrinsic_size(void *frame,int *size) {
  struct LogicalSizeI preferred;
  if(!button_preferred(frame,&preferred))return 0;
  struct IntrinsicOffsetsI offsets=((struct IntrinsicOffsetsI (*)(void *,int))(base+0x6e83058))(frame,0x3fffffff);
  int content=preferred.inline_size-offsets.border-offsets.padding;
  *size=content>0?content:0;return 1;
}
static int button_intrinsic(void *frame,const void *input,unsigned type) {
  int size;return button_intrinsic_size(frame,&size)?size:original_button_intrinsic(frame,input,type);
}
static int button_flex_intrinsic(void *frame,const void *input,unsigned type) {
  int size;return button_intrinsic_size(frame,&size)?size:original_button_flex_intrinsic(frame,input,type);
}
static int button_grid_intrinsic(void *frame,const void *input,unsigned type) {
  int size;return button_intrinsic_size(frame,&size)?size:original_button_grid_intrinsic(frame,input,type);
}
static struct LogicalSizeI button_auto_size(void *frame,const void *input,unsigned mode,
    const void *cb,int available,const void *margin,const struct LogicalSizeI *border_padding,
    const void *overrides,unsigned flags) {
  struct LogicalSizeI result=original_button_auto_size(frame,input,mode,cb,available,margin,border_padding,overrides,flags),preferred;
  if(!(mode&1)&&(button_preferred(frame,&preferred)||popup_preferred(frame,&preferred))) {
    int content=preferred.block_size-border_padding->block_size;
    result.block_size=content>0?content:0;
  }
  return result;
}
static int button_cache_update(struct Widget *w,const struct NXSResponse *response) {
  if(!response||response->width<1||response->height<1||response->width>8192||response->height>8192||
     response->stride!=response->width*4||sizeof(*response)+(size_t)response->stride*response->height!=response->size)return 0;
  uint32_t *pixels=malloc((size_t)response->stride*response->height);if(!pixels)return 0;
  memcpy(pixels,response+1,(size_t)response->stride*response->height);free(w->button_pixels);
  w->button_pixels=pixels;w->button_width=response->width;w->button_height=response->height;
  w->button_focused=!!response->parts[3].y;return 1;
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
  if(w->button_reflow_pending)return w->button_label_owned&&button_cache_available(w);
  int rectangle[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,rectangle);
  double width=rectangle[2]/60.,height=rectangle[3]/60.;
  if(width<1||height<1||width>8192||height>8192) {
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
  if(html_button_node(w->node)) {
    double width=response->parts[1].width,height=response->parts[1].height;
    if(isfinite(width)&&isfinite(height)&&width>=1&&height>=1&&width<=8192&&height<=8192&&
       (width!=w->button_preferred_width||height!=w->button_preferred_height)) {
      w->button_preferred_width=width;w->button_preferred_height=height;
      w->button_reflow_pending=1;
      /* Ask Gecko to invalidate its intrinsic cache and schedule normal
       * reflow. No text measurement, CSS sizing or reflow policy is copied.
       * The guarded existing caller loads PresContext +32 and supplies these
       * same enum/dirty-bit values for a size-affecting intrinsic change. */
      void *context=*(void **)((char *)frame+40),*shell=*(void **)((char *)context+32);
      if(shell)((void (*)(void *,void *,unsigned,uint64_t,unsigned))(base+NXS_GECKO_HTML_BUTTON_REFLOW_OFFSET))(shell,frame,2,0x400,2);
    }
  }
  if(width!=floor(width)||height!=floor(height)) {
    if(!html_button_node(w->node))release_button_frame(frame);
    else {w->button_label_owned=0;w->painted=0;}
    return 0;
  }
  w->button_label_owned=1;w->painted=1;
  if(html_button_node(w->node)&&w->button_model_changed) {
    /* Native title pixels changed, not the display-item structure. Use
     * Gecko's paint-only invalidation. Rebuilding items here can discard a
     * blob image that WebRender still has queued in the same transaction. */
    w->button_model_changed=0;
    ((void (*)(void *,unsigned,int))(base+0x6e85c5c))(w->frame,0,0);
  }
  return 1;
}
static struct Widget *bind_input_widget(void *frame) {
  if(frame_kind(frame)==NXS_SLIDER)
    return prepare_range_image(frame)?widget_for_frame(frame):NULL;
  if(frame_kind(frame)==NXS_BUTTON)
    return prepare_button_image(frame)?widget_for_frame(frame):NULL;
  return bind_widget(frame);
}
static void block_display(void *frame,void *builder,const void *lists) {
  if(native_popup_display(frame,builder,lists))return;
  void *previous=label_owner;
  if(frame_kind(frame)==NXS_BUTTON)label_owner=prepare_button_image(frame)?frame:NULL;
  original_block_display(frame,builder,lists);label_owner=previous;
}
static void text_display(void *frame,void *builder,const void *lists) {
  struct Widget *owner=html_button_owner(*(void **)((char *)frame+24));
  if(owner)prepare_button_image(owner->frame);
  if(label_owner&&!html_button_node(*(void **)((char *)label_owner+24))&&
     *(void **)((char *)frame+24)==*(void **)((char *)label_owner+200))return;
  original_text_display(frame,builder,lists);
}
static struct Widget *html_button_owner(const void *node) {
  if(!node||!buttons_enabled)return NULL;
  struct Widget *owner=NULL;
  for(struct Widget *w=widgets;w;w=w->next) {
    if(w->kind!=NXS_BUTTON||!w->button_label_owned||!button_cache_available(w)||!html_button_node(w->node))continue;
    if(((int (*)(const void *,const void *))(base+NXS_GECKO_HTML_BUTTON_DESCENDANT_OFFSET))(node,w->node)&&
       (!owner||((int (*)(const void *,const void *))(base+NXS_GECKO_HTML_BUTTON_DESCENDANT_OFFSET))(w->node,owner->node)))owner=w;
  }
  return owner;
}
static void (*original_html_text_paint)(void *,void *,void *);
static int (*original_html_text_webrender)(void *,void *,void *,void *,void *,void *);
static uint32_t (*original_html_button_post)(void *,void *);
static void (*original_html_button_did_reflow)(void *,void *,const void *);
static void html_button_did_reflow(void *frame,void *context,const void *input) {
  original_html_button_did_reflow(frame,context,input);
  struct Widget *w=widget_for_frame(frame);
  if(w&&html_button_node(w->node))w->button_reflow_pending=0;
}
static int html_label_owned(void *item) {
  void *frame=((void *(*)(void *))(*(uintptr_t **)item)[20])(item);
  return frame&&html_button_owner(*(void **)((char *)frame+24));
}
static void html_text_paint(void *item,void *builder,void *context) {
  /* Retain the actual text display item and its hit testing; only native
   * NSButton owns title painting. Descendant event targets remain Gecko's. */
  if(!html_label_owned(item))original_html_text_paint(item,builder,context);
}
static int html_text_webrender(void *item,void *builder,void *resources,void *stacking,void *manager,void *display_builder) {
  return html_label_owned(item)?1:original_html_text_webrender(item,builder,resources,stacking,manager,display_builder);
}
static uint32_t html_button_post(void *node,void *visitor) {
  return widget_post(node,visitor,original_html_button_post);
}
static struct Detour button_detours[]={
  {NXS_GECKO_BLOCK_DISPLAY_OFFSET,gecko_block_display_bytes,block_display,(void **)&original_block_display},
  {NXS_GECKO_TEXT_DISPLAY_OFFSET,gecko_text_display_bytes,text_display,(void **)&original_text_display},
  {NXS_GECKO_BUTTON_AUTO_SIZE_OFFSET,gecko_button_auto_size_bytes,button_auto_size,(void **)&original_button_auto_size},
  {NXS_GECKO_BUTTON_INTRINSIC_OFFSET,gecko_button_intrinsic_bytes,button_intrinsic,(void **)&original_button_intrinsic},
  {NXS_GECKO_BUTTON_FLEX_INTRINSIC_OFFSET,gecko_button_flex_intrinsic_bytes,button_flex_intrinsic,(void **)&original_button_flex_intrinsic},
  {NXS_GECKO_BUTTON_GRID_INTRINSIC_OFFSET,gecko_button_grid_intrinsic_bytes,button_grid_intrinsic,(void **)&original_button_grid_intrinsic},
  {NXS_GECKO_HTML_BUTTON_POST_OFFSET,gecko_html_button_post_bytes,html_button_post,(void **)&original_html_button_post},
  {NXS_GECKO_HTML_BUTTON_DID_REFLOW_OFFSET,gecko_html_button_did_reflow_bytes,html_button_did_reflow,(void **)&original_html_button_did_reflow},
  {NXS_GECKO_HTML_BUTTON_TEXT_PAINT_OFFSET,gecko_html_button_text_paint_bytes,html_text_paint,(void **)&original_html_text_paint},
  {NXS_GECKO_HTML_BUTTON_TEXT_WEBRENDER_OFFSET,gecko_html_button_text_webrender_bytes,html_text_webrender,(void **)&original_html_text_webrender}
};
