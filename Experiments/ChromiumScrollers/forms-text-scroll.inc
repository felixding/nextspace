/* Native document metrics at Blink's scroll-area boundary. No layout,
 * scroller drawing, clamping or tracking implementation lives here. */
struct FixedRect {int32_t x,y,width,height;};
static struct SizeI (*original_multiline_contents)(const void *);
static struct Point (*original_multiline_minimum)(const void *);
static struct Point (*original_multiline_maximum)(const void *);
static struct FixedRect (*original_multiline_content_rect)(const void *,int);
static struct FixedRect (*original_multiline_contracted_box)(int,const void *,const void *,const void *);
static void (*original_multiline_bars)(const void *,uint8_t *,uint8_t *,int);
static int32_t (*original_multiline_box_width)(const void *);
static int32_t (*original_multiline_box_height)(const void *);
static int (*original_multiline_can_resize)(const void *);
static void (*original_multiline_update_offset)(void *,const struct FloatPoint *,int,int);
static __thread int multiline_syncing;
static const NXSScrollGeometry *scroll_geometry_for_form(const struct NativeForm *form) {
  if(!form)return NULL;
  if(form->kind==NXS_LISTBOX)return form->list.geometry_ready?&form->list.geometry:NULL;
  return form->text_geometry_ready?&form->text_geometry:NULL;
}
static NXSTextViewport scroll_viewport_for_form(const struct NativeForm *form) {
  if(form->kind!=NXS_LISTBOX)return form->text_viewport;
  return (NXSTextViewport){.size=sizeof(NXSTextViewport),
    .visible={form->list.state.visible.x,form->list.state.visible.y,form->list.state.visible.width,form->list.state.visible.height},
    .content={form->list.state.content_width,form->list.state.content_height}};
}

static struct NativeForm *multiline_layout(const void *layout) {
  if(!(forms_multiline_viewport_enabled||forms_lists_enabled)||!layout)return NULL;
  void *node=((void *(*)(const void *))(base+NXS_MULTILINE_NODE_OFFSET))(layout);
  if(!node||decode_member((char *)node+48)!=layout)return NULL;
  int kind=input_form_kind(node);
  if(kind!=NXS_TEXTAREA&&kind!=NXS_LISTBOX)return NULL;
  if(kind==NXS_TEXTAREA&&!forms_multiline_viewport_enabled)return NULL;
  if(kind==NXS_LISTBOX&&!list_style(node))return NULL;
  return find_form(node);
}
static struct NativeForm *multiline_area(const void *area,int bind) {
  if(!(forms_multiline_viewport_enabled||forms_lists_enabled)||!area)return NULL;
  void *layout=((void *(*)(const void *))(base+NXS_MULTILINE_GET_BOX_OFFSET))(area);
  if(!layout)return NULL;
  void *node=((void *(*)(const void *))(base+NXS_MULTILINE_NODE_OFFSET))(layout);
  if(!node||decode_member((char *)node+48)!=layout)return NULL;
  int kind=input_form_kind(node);
  if(kind!=NXS_TEXTAREA&&kind!=NXS_LISTBOX)return NULL;
  if(kind==NXS_TEXTAREA&&!forms_multiline_viewport_enabled)return NULL;
  if(kind==NXS_LISTBOX&&!list_style(node))return NULL;
  struct NativeForm *form=find_form(node);
  if(!form&&bind&&kind==NXS_TEXTAREA){
    form=calloc(1,sizeof(*form));if(!form)return NULL;
    form->node=node;form->control=++next_form_control;form->kind=NXS_TEXTAREA;
    form->next=native_forms;native_forms=form;
  }
  if(form)form->text_area=(void *)area;
  return form;
}
static int read_text_viewport(struct NativeForm *form) {
  struct NXSResponse *response=form_request(form,34,0,0,0);
  if(form->text_epoch!=atomic_load(&native_host_epoch))return 0;
  if(!response||response->parts[3].x!=1||response->size!=sizeof(*response)+sizeof(NXSTextGeometry))return 0;
  NXSTextGeometry geometry;memcpy(&geometry,response+1,sizeof(geometry));
  response=form_request(form,32,0,0,0);
  if(!response||response->parts[3].x!=1||geometry.size!=sizeof(geometry))return 0;
  form->text_geometry=geometry;
  form->text_viewport=(NXSTextViewport){.size=sizeof(NXSTextViewport),
    .visible={response->parts[5].x,response->parts[5].y,response->parts[5].width,response->parts[5].height},
    .content={response->parts[6].width,response->parts[6].height}};
  form->text_geometry_ready=1;
  static __thread unsigned logged;
  if(logged++<32&&log_fd>=0)dprintf(log_fd,"%d native-text-viewport id=%llu area=%p painted=%d clip=%.2f,%.2f,%.2f,%.2f content=%.2f,%.2f limits=%.2f,%.2f offset=%.2f,%.2f\n",getpid(),(unsigned long long)form->control,form->text_area,form->painted,geometry.clip.x,geometry.clip.y,geometry.clip.width,geometry.clip.height,form->text_viewport.content.width,form->text_viewport.content.height,geometry.maximum.x,geometry.maximum.y,form->text_viewport.visible.x,form->text_viewport.visible.y);
  return 1;
}
static int restore_text_viewport(struct NativeForm *form) {
  if(!form->text_area)return 0;
  /* Recreated UI objects start at zero. Replay the retained engine model only
   * on a host generation change; native input otherwise owns the viewport. */
  struct FloatPoint offset=((struct FloatPoint (*)(const void *))(base+NXS_MULTILINE_GET_OFFSET_OFFSET))(form->text_area);
  struct NXSResponse *response=form_request(form,33,offset.x,offset.y,0);
  if(!response||response->parts[3].x!=1)return 0;
  form->text_epoch=atomic_load(&native_host_epoch);return 1;
}
static int sync_multiline_layout(struct NativeForm *form,const void *area) {
  if(multiline_syncing||form->text_tracking||
     (text_transaction&&text_transaction->node==form->node))return form->text_geometry_ready;
  multiline_syncing=1;
  struct SizeI size=((struct SizeI (*)(const void *))(base+NXS_MULTILINE_AREA_SIZE_OFFSET))(area);
  form->rect.width=lround(size.width/64.0);form->rect.height=lround(size.height/64.0);
  form->enabled=form_enabled(form->node);
  int ok=form->rect.width>0&&form->rect.height>0&&
    sync_text_form(form,form_request(form,1,0,0,0))&&read_text_viewport(form);
  multiline_syncing=0;if(!ok)form->text_geometry_ready=0;
  if(ok)native_wheel_binding(form,1);
  return ok;
}
static void echo_text_viewport(struct NativeForm *form) {
  if(!form->text_area||!scroll_geometry_for_form(form)||multiline_syncing)return;
  struct FloatPoint actual=((struct FloatPoint (*)(const void *))(base+NXS_MULTILINE_GET_OFFSET_OFFSET))(form->text_area);
  NXSTextViewport viewport=scroll_viewport_for_form(form);
  struct FloatPoint offset={viewport.visible.x,viewport.visible.y};
  if(fabsf(actual.x-offset.x)<.001f&&fabsf(actual.y-offset.y)<.001f)return;
  multiline_syncing=1;
  /* Existing Blink setter retains its animation bookkeeping, invalidation,
   * trusted scroll events and scrollend lifecycle. */
  ((int (*)(void *,const struct FloatPoint *,int,int,int,int))(base+NXS_MULTILINE_SET_OFFSET_OFFSET))
    (form->text_area,&offset,0,1,1,0);
  multiline_syncing=0;
}
static struct SizeI multiline_contents(const void *area) {
  struct NativeForm *form=multiline_area(area,0);
  if(scroll_geometry_for_form(form)){NXSTextViewport viewport=scroll_viewport_for_form(form);return (struct SizeI){lround(viewport.content.width),lround(viewport.content.height)};}
  return original_multiline_contents(area);
}
static struct Point multiline_minimum(const void *area) {
  struct NativeForm *form=multiline_area(area,0);
  const NXSScrollGeometry *geometry=scroll_geometry_for_form(form);
  if(geometry)return (struct Point){lround(geometry->minimum.x),lround(geometry->minimum.y)};
  return original_multiline_minimum(area);
}
static struct Point multiline_maximum(const void *area) {
  struct NativeForm *form=multiline_area(area,0);
  const NXSScrollGeometry *geometry=scroll_geometry_for_form(form);
  if(geometry)return (struct Point){lround(geometry->maximum.x),lround(geometry->maximum.y)};
  return original_multiline_maximum(area);
}
static struct FixedRect multiline_content_rect(const void *area,int inclusion) {
  struct FixedRect rect=original_multiline_content_rect(area,inclusion);
  struct NativeForm *form=multiline_area(area,0);
  const NXSScrollGeometry *geometry=scroll_geometry_for_form(form);
  if(geometry){
    NXSSize size=inclusion?geometry->client:(NXSSize){geometry->clip.width,geometry->clip.height};
    rect.width=lround(size.width*64);rect.height=lround(size.height*64);
  }
  return rect;
}
static struct FixedRect multiline_contracted_box(int edge,const void *style,const void *fragments,const void *size) {
  if(edge==0&&(forms_multiline_viewport_enabled||forms_lists_enabled)&&fragments){
    const void *results=*(const void *const *)fragments;
    for(struct NativeForm *form=native_forms;form;form=form->next){
      const NXSScrollGeometry *geometry=scroll_geometry_for_form(form);if(!geometry||(form->kind==NXS_LISTBOX&&!list_style(form->node)))continue;
      void *layout=decode_member((char *)form->node+48);
      if(layout&&(const char *)layout+NXS_MULTILINE_LAYOUT_RESULTS_BYTE==results){
        NXSRect clip=geometry->clip;
        /* The engine still applies its own CSS zoom and DOM rounding. */
        return (struct FixedRect){lround(clip.x*64),lround(clip.y*64),lround(clip.width*64),lround(clip.height*64)};
      }
    }
  }
  return original_multiline_contracted_box(edge,style,fragments,size);
}
static void multiline_bars(const void *area,uint8_t *horizontal,uint8_t *vertical,int option) {
  if(forms_lists_enabled&&list_scrollbar_owner(area)){*horizontal=0;*vertical=0;return;}
  struct NativeForm *form=multiline_area(area,1);
  if(form&&sync_multiline_layout(form,area)){
    /* Both scrollers belong to the real native NSScrollView. */
    *horizontal=0;*vertical=0;return;
  }
  original_multiline_bars(area,horizontal,vertical,option);
}
static int32_t multiline_box_width(const void *layout) {
  struct NativeForm *form=multiline_layout(layout);
  if(scroll_geometry_for_form(form))return lround(scroll_viewport_for_form(form).content.width*64);
  return original_multiline_box_width(layout);
}
static int32_t multiline_box_height(const void *layout) {
  struct NativeForm *form=multiline_layout(layout);
  if(scroll_geometry_for_form(form))return lround(scroll_viewport_for_form(form).content.height*64);
  return original_multiline_box_height(layout);
}
static int multiline_can_resize(const void *layout) {
  struct NativeForm *form=multiline_layout(layout);
  /* The browser's corner grip overlaps the native scroller. NSScrollView owns
   * the complete control; CSS/script can still resize its enclosing box. */
  return scroll_geometry_for_form(form)?0:original_multiline_can_resize(layout);
}
static void multiline_update_offset(void *area,const struct FloatPoint *offset,int type,int source) {
  struct NativeForm *form=multiline_area(area,0);
  if(form&&form->kind==NXS_LISTBOX&&form->list.geometry_ready&&!multiline_syncing) {
    if(native_list_binding_scroll(&form->list,offset->x,offset->y)) {
      struct FloatPoint actual={form->list.state.visible.x,form->list.state.visible.y};
      original_multiline_update_offset(area,&actual,type,source);invalidate_form(form);return;
    }
  }
  if(form&&form->kind==NXS_TEXTAREA&&form->text_geometry_ready&&!multiline_syncing){
    struct NXSResponse *response=form_request(form,33,offset->x,offset->y,0);
    if(response&&response->parts[3].x==1){
      struct FloatPoint actual={response->parts[5].x,response->parts[5].y};
      form->text_viewport.visible.x=actual.x;form->text_viewport.visible.y=actual.y;
      original_multiline_update_offset(area,&actual,type,source);
      /* A complete native viewport is in the border-box display item. Engine
       * scrolling alone only translates its hidden document paint layer. */
      invalidate_form(form);return;
    }
  }
  original_multiline_update_offset(area,offset,type,source);
}
static struct Point (*original_multiline_scroll_origin)(const void *);
static struct Point multiline_scroll_origin(const void *area) {
  struct NativeForm *form=multiline_area(area,0);
  const NXSScrollGeometry *geometry=scroll_geometry_for_form(form);
  if(geometry) {
    struct FloatPoint offset=((struct FloatPoint (*)(const void *))(base+NXS_MULTILINE_GET_OFFSET_OFFSET))(area);
    /* Encode the engine's physical coordinate units using the real native
     * clip origin. Selection/default scrolling remain original engine calls. */
    return (struct Point){floorf(offset.x*64)-lround(geometry->clip.x*64),floorf(offset.y*64)-lround(geometry->clip.y*64)};
  }
  return original_multiline_scroll_origin(area);
}
static struct Detour multiline_scroll_detours[]={
  {NXS_MULTILINE_SCROLL_ORIGIN_OFFSET,nxs_multiline_scroll_origin_bytes,multiline_scroll_origin,(void **)&original_multiline_scroll_origin},
  {NXS_MULTILINE_CAN_RESIZE_OFFSET,nxs_multiline_can_resize_bytes,multiline_can_resize,(void **)&original_multiline_can_resize},
  {NXS_MULTILINE_CONTRACTED_BOX_OFFSET,nxs_multiline_contracted_box_bytes,multiline_contracted_box,(void **)&original_multiline_contracted_box},
  {NXS_MULTILINE_CONTENTS_OFFSET,nxs_multiline_contents_bytes,multiline_contents,(void **)&original_multiline_contents},
  {NXS_MULTILINE_MINIMUM_OFFSET,nxs_multiline_minimum_bytes,multiline_minimum,(void **)&original_multiline_minimum},
  {NXS_MULTILINE_MAXIMUM_OFFSET,nxs_multiline_maximum_bytes,multiline_maximum,(void **)&original_multiline_maximum},
  {NXS_MULTILINE_CONTENT_RECT_OFFSET,nxs_multiline_content_rect_bytes,multiline_content_rect,(void **)&original_multiline_content_rect},
  {NXS_MULTILINE_BARS_OFFSET,nxs_multiline_bars_bytes,multiline_bars,(void **)&original_multiline_bars},
  {NXS_MULTILINE_BOX_WIDTH_OFFSET,nxs_multiline_box_width_bytes,multiline_box_width,(void **)&original_multiline_box_width},
  {NXS_MULTILINE_BOX_HEIGHT_OFFSET,nxs_multiline_box_height_bytes,multiline_box_height,(void **)&original_multiline_box_height},
  {NXS_MULTILINE_UPDATE_OFFSET_OFFSET,nxs_multiline_update_offset_bytes,multiline_update_offset,(void **)&original_multiline_update_offset}
};
