/* Blink element/model and event bindings only. Native controls stay in the
 * separately loaded UI provider. Exact Chromium build; GPL-2.0-or-later. */
#include "pinned-forms.h"
#include "pinned-coordinates.h"
#include "pinned-multiline.h"
#include "pinned-multiline-scroll.h"
#include "../../Libraries/NativeUI/NativeUI.h"
#include "../../Libraries/NativeUI/Bridge/ControlActions.inc"
struct NativeForm {
  struct NativeForm *next;
  struct NXSListBinding list;
  void *node;
  uint64_t control;
  uint32_t radio_owner,radio_member;
  unsigned radio_clicks;
  struct NXSControlAction checkbox_action;
  struct NXSRectD radio_rect;
  int kind,enabled,state,painted,input_owned,indeterminate;
  struct Rect rect;
  char *title;
  double actions_before,actions_seen,value,generation,minimum,maximum,step;
  char *popup_model,*popup_title;
  size_t popup_size;
  int *popup_indices;
  void **popup_nodes;
  unsigned popup_count;
  int popup_selected,popup_selected_list,popup_open;
  void *popup_selected_node;
  void *popup_engine;
  uint32_t popup_epoch;
  int text_tracking,text_width,text_height;
  uint32_t text_start,text_end;
  double text_x,text_y;
  void *text_area;
  uint32_t text_epoch;
  void *wheel_registry;
  NXSTextViewport text_viewport;
  NXSTextGeometry text_geometry;
  int text_geometry_ready;
  double preferred_width,preferred_height;
  void *button_style;
  int layout_pending,list_layout_retry;
};
struct FloatRect {float x,y,width,height;};
struct SizeI {int width,height;};
struct MouseDispatchResult {void *event;int result;};
static struct NativeForm *native_forms,*active_form,*click_form;
struct RadioPointerGate {uint32_t origin;uint64_t control;int armed;};
static struct RadioPointerGate radio_pointer_gate;
static __thread void *native_parent;
static __thread void *native_dispatch_event;
static __thread void *form_key_node,*form_key_event;
static uint64_t next_form_control;
static __thread uint64_t form_key_control;
static int form_click_allowed;
static uint64_t form_click_time;
static int forms_available;
static int forms_input_enabled;
static int forms_radio_groups_enabled,forms_labels_enabled;
static int forms_progress_enabled;
static int forms_animation_enabled;
static int forms_sliders_enabled;
static int forms_popups_enabled,forms_lists_enabled;
static int forms_text_enabled;
static int forms_color_enabled;
static int forms_placeholder_enabled;
static int forms_search_enabled;
static int forms_search_actions_enabled,forms_search_clear_enabled;
static __thread struct NXSControlActivation native_search_activation;
static __thread uint64_t native_search_click_time;
static int forms_multiline_enabled;
static int forms_multiline_viewport_enabled;
static int forms_wheel_enabled;
static int forms_notifications_enabled;
static __thread const void *popup_mouse_event;
static __thread int popup_measuring;
static unsigned forms_input_capabilities;
static struct SizeI form_sizes[4];
static int (*original_checkbox)(void*,const void*,const void*,const void*,const void*,const struct Rect*);
static int (*original_radio)(void*,const void*,const void*,const void*,const void*,const struct Rect*);
static int (*original_button)(void*,const void*,const void*,const void*,const void*,const struct Rect*);
static struct SizeI (*original_form_size)(void*,int);
static struct SizeI (*original_theme_size)(void*,int,int,const void*);
static void (*original_box_paint)(void*,const void*);
static void (*original_inline_children)(void*,const void*,const void*,const void*,void*);
static void (*original_block_children)(void*,const void*,uint64_t);
static int (*original_dom_dispatch)(void*);
static void (*original_element_detach)(void*,int);
static struct MouseDispatchResult (*original_mouse_dispatch)(void*,void*,const void*,const void*,const void*,void*,int,const void*,const void*,void*,void*);

static void *decode_member(const void *address) {
  int32_t compressed=*(const int32_t *)address;
  return compressed?(void *)(*(uintptr_t *)(base+0x12562900)&((uint64_t)(int64_t)compressed<<3)):NULL;
}
static struct NativeForm *find_form(const void *node) {
  for(struct NativeForm *f=native_forms;f;f=f->next)if(f->node==node)return f;
  return NULL;
}
static struct NativeForm *bind_input_form(void *node);
static int refresh_form_watch(void);
static int color_watch_needed(void);
static void color_native_work(int);
static void color_forget(void *);
static struct NXSResponse *sync_color_image(struct NativeForm *,struct NXSResponse *);
static int sync_slider_model(struct NativeForm *);
static void apply_slider_value(struct NativeForm *,struct NXSResponse *,int);
static int slider_mouse_default(void *,void *);
static int popup_element(void *);
static int list_element(void *);
static int list_owned(const struct NativeForm *);
static int list_style(void *);
static int native_layout_appearance(const void *,const void *,unsigned);
static void list_forget(struct NativeForm *);
static void list_model_changed(void *,uint64_t);
static struct NXSResponse *list_form_request(struct NativeForm *,unsigned,double,double,unsigned);
static int list_sync(struct NativeForm *);
static void list_after_input(uint32_t,uint64_t,uint64_t);
static int list_key_input(struct NativeForm *,void *,int,unsigned,const char *,const char *,unsigned,int);
static int list_default_event(void *,void *);
static int list_mouse_dispatch(void *,void *,const void *,const void *,const void *,void *,int,const void *,const void *,void *,void *,struct MouseDispatchResult *);
static struct NXSResponse *sync_popup_model(struct NativeForm *,struct NXSResponse *);
static void popup_after_input(struct NativeForm *,struct NXSResponse *);
static void popup_free_model(struct NativeForm *);
static void popup_sync_origin(struct NativeForm *);
static void native_button_size_changed(struct NativeForm *,const struct NXSResponse *);
static int native_button_owned(const struct NativeForm *);
static int text_kind(int);
static void search_activate(void *,void *,uint64_t);
static void search_clear(void *,uint64_t);
static int guard_radio_calls(void);
static struct NXSResponse *radio_form_request(struct NativeForm *,int,double,double,unsigned);
static struct NXSResponse *radio_form_focus(struct NativeForm *);
static uint32_t radio_node_id(void *);
static void *radio_node_for_id(uint64_t);
static void *radio_pointer_target(struct NativeForm *);
static int input_form_kind(void *);
static void radio_pointer_complete(uint32_t,uint64_t);
static int radio_key_input(struct NativeForm *,void *,int,unsigned,const char *,const char *,unsigned,int);
static struct NXSResponse *sync_text_form(struct NativeForm *,struct NXSResponse *);
static int default_text_key(void *,void *);
static struct NXSResponse *sync_text_image(struct NativeForm *);
static void end_text_pointer(struct NativeForm *,int);
static void echo_text_selection(struct NativeForm *);
static void echo_text_viewport(struct NativeForm *);
static int read_text_viewport(struct NativeForm *);
static int restore_text_viewport(struct NativeForm *);
static void native_wheel_binding(struct NativeForm *,int);
static int native_wheel_default(void *,void *);
static int native_wheel_dispatch(void *);
static struct NativeForm *bound_form_ancestor(void *node,int kind) {
  for(unsigned depth=0;node&&depth<4096;depth++) {
    struct NativeForm *form=find_form(node);if(form&&form->kind==kind)return form;
    node=((void *(*)(void *))(base+0xdd0e0ac))(node);
  }
  return NULL;
}
static struct NativeForm *form_ancestor(void *node) {
  for(int i=0;node&&i<256;i++) {
    struct NativeForm *f=find_form(node);
    if(!f&&forms_input_enabled)f=bind_input_form(node);
    if(f&&f->kind!=NXS_PROGRESS&&(f->painted||f->input_owned))return f;
    node=((void *(*)(void *))(base+0xdd0e0ac))(node);
  }
  return NULL;
}
static int same_atom(uintptr_t value,uintptr_t offset) {
  uintptr_t reference=*(uintptr_t *)(base+offset);
  return reference&&(value==reference||value==*(uintptr_t *)reference);
}
static int input_element(const void *node) {return *((const unsigned char *)*(uintptr_t *)node-17)==0x22;}
static int form_enabled(void *node) {return !((int (*)(const void *))(*(uintptr_t **)node)[154])(node);}
static int form_state(void *node,int kind) {
  if((kind!=2&&kind!=3)||!input_element(node))return 0;
  if(kind==2&&((int (*)(const void *))(base+0xefaa8f4))(node))return -1;
  return !!((int (*)(const void *))(base+0xefaa720))(node);
}
/* String data conversion is application-model transport, not UI rendering.
 * This build's String return is one pointer; StringImpl stores characters
 * inline after its three 32-bit fields. Release through Chromium's destructor. */
static char *encode_text(const void *data,uint32_t length,int latin1) {
  char *result=length<=65536?malloc((size_t)length*4+1):NULL;
  size_t used=0;
  for(uint32_t i=0;result&&i<length;i++) {
    uint32_t c;
    if(latin1)c=((const unsigned char *)data)[i];
    else {
      const uint16_t *text=data;c=text[i];
      if(c>=0xd800&&c<=0xdbff&&i+1<length&&text[i+1]>=0xdc00&&text[i+1]<=0xdfff) {
        c=0x10000+((c-0xd800)<<10)+(text[++i]-0xdc00);
      } else if(c>=0xd800&&c<=0xdfff)c=0xfffd;
    }
    if(!c){free(result);result=NULL;break;} /* Explicit-length titles remain an API extension. */
    if(c<0x80)result[used++]=c;
    else if(c<0x800){result[used++]=0xc0|(c>>6);result[used++]=0x80|(c&63);}
    else if(c<0x10000){result[used++]=0xe0|(c>>12);result[used++]=0x80|((c>>6)&63);result[used++]=0x80|(c&63);}
    else {result[used++]=0xf0|(c>>18);result[used++]=0x80|((c>>12)&63);result[used++]=0x80|((c>>6)&63);result[used++]=0x80|(c&63);}
    if(used>65536){free(result);result=NULL;break;}
  }
  if(result)result[used]=0;
  return result;
}
static char *string_text(const void *string) {
  if(!string)return strdup("");
  return encode_text((const char *)string+12,*(const uint32_t *)((const char *)string+4),
    *(const uint32_t *)((const char *)string+8)&1);
}
static char *form_title(void *node) {
  void *string=input_element(node)?((void *(*)(void *))(base+0xefa5dc0))(node):
    ((void *(*)(void *,void *))(base+0xddf7648))(node,NULL);
  char *result=string_text(string);
  ((void (*)(void *))(base+0x7246038))(&string);
  return result;
}
static struct NXSResponse *form_request(struct NativeForm *form,int operation,double x,double y,unsigned modifiers) {
  if(form->kind==NXS_LISTBOX)return list_form_request(form,operation,x,y,modifiers);
  if(form->kind==NXS_RADIO&&forms_radio_groups_enabled)return radio_form_request(form,operation,x,y,modifiers);
  if(operation==1&&form->kind==NXS_POPUP&&!popup_measuring)popup_sync_origin(form);
  size_t title_size=operation==1&&form->title?strlen(form->title):0;
  size_t size=sizeof(struct NXSControlRequest)+title_size;
  struct NXSControlRequest *req=calloc(1,size);if(!req)return NULL;
  *req=(struct NXSControlRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=form->kind,.control=form->control,.text_size=title_size,
    .width=form->rect.width,.height=form->rect.height,
    .minimum=form->kind==NXS_SLIDER?form->minimum:0,.maximum=form->kind==NXS_SLIDER?form->maximum:1,
    .value=(form->kind==NXS_PROGRESS||form->kind==NXS_SLIDER)?form->value:form->state,
    .x=x,.y=y,.enabled=form->enabled,.state=form->state,.indeterminate=form->indeterminate,.modifiers=modifiers};
  if(title_size)memcpy(req+1,form->title,title_size);
  struct NXSResponse *response=exchange_bytes(req,size);free(req);
  if(operation==1&&form->kind==NXS_SLIDER&&response&&response->parts[5].x!=form->step){
    struct NXSControlStepRequest step={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=10,
      .process=identity(),.kind=NXS_SLIDER,.control=form->control,.step=form->step};
    response=exchange_bytes(&step,sizeof(step));
  }
  if(operation==1&&form->kind==NXS_POPUP&&response)response=sync_popup_model(form,response);
  return response;
}
static void invalidate_form(struct NativeForm *form) {
  void *layout=decode_member((const char *)form->node+48);
  if(layout)((void (*)(void *,int))(base+0xe55f5f8))(layout,3); /* Chromium kStyle. */
}
static struct NXSResponse *sync_form_focus(struct NativeForm *,struct NXSResponse *);
static int paint_form(int kind,void *self,const void *element,const void *document,const void *style,const void *info,const struct Rect *rect) {
  struct NativeForm *form=find_form(element);
  if(form){if(form->kind==NXS_LISTBOX&&kind!=NXS_LISTBOX)list_forget(form);form->painted=0;}
  if(rect->width<1||rect->height<1)return 0;
  char *title=kind==1?form_title((void *)element):strdup("");
  if(!title)return 1;
  if(!form){form=calloc(1,sizeof(*form));if(!form){free(title);return 1;}form->node=(void *)element;form->control=++next_form_control;form->next=native_forms;native_forms=form;}
  free(form->title);form->title=title;form->kind=kind;form->rect=*rect;
  form->enabled=kind==NXS_PROGRESS?1:form_enabled(form->node);form->state=form_state(form->node,kind);
  if(kind==NXS_SLIDER&&!sync_slider_model(form))return 1;
  if(kind==NXS_PROGRESS){
    double position=((double (*)(const void *))(base+0xe7bb2e8))(element);
    form->indeterminate=position==-1;form->value=form->indeterminate?0:position;
  }
  struct NXSResponse *response;
  if(text_kind(kind))response=sync_text_image(form);
  else {
    response=form_request(form,1,0,0,0);
    if(kind!=NXS_PROGRESS)response=sync_form_focus(form,response);
    if(kind==NXS_COLORWELL)response=sync_color_image(form,response);
  }
  if(!response||response->width<1||response->height<1||response->stride!=response->width*4||
     sizeof(*response)+(size_t)response->stride*response->height!=response->size){
    if(log_fd>=0)dprintf(log_fd,"%d native bitmap unavailable kind=%d id=%llu response=%p errno=%d\n",
      getpid(),kind,(unsigned long long)form->control,(void *)response,response?0:errno);
    form->painted=0;return 1;
  }
  struct NXSResponse header=*response;
  form->generation=header.parts[4].x;
  uint32_t *pixels=malloc((size_t)header.stride*header.height);if(!pixels){form->painted=0;return 1;}
  memcpy(pixels,response+1,(size_t)header.stride*header.height);
  if(kind==NXS_TEXTAREA&&forms_multiline_viewport_enabled)read_text_viewport(form);
  void *canvas=*(void **)*(void **)info;
  /* The desktop host validates every input against a registered renderer
   * lifetime, including documents containing only buttons or other controls.
   * Establish ownership before committing any native pixels. */
  form->painted=!!canvas;
  if(canvas&&forms_input_enabled&&!refresh_form_watch()){form->painted=0;free(pixels);return 1;}
  static __thread unsigned progress_paints;
  if(kind==NXS_PROGRESS&&progress_paints++<32&&log_fd>=0)dprintf(log_fd,"%d progress paint id=%llu value=%.8g rect=%d,%d,%d,%d canvas=%p\n",
    getpid(),(unsigned long long)form->control,form->value,rect->x,rect->y,rect->width,rect->height,canvas);
  if(canvas)draw_native_bitmap(canvas,pixels,header.width,rect->x,rect->y,0,0,header.width,header.height);
  free(pixels);form->painted=!!canvas;
  if(kind==NXS_LISTBOX&&canvas&&log_fd>=0)dprintf(log_fd,"%d native-list id=%llu count=%u selected=%u rect=%d,%d %dx%d\n",getpid(),(unsigned long long)form->control,form->list.state.count,form->list.state.selected_count,rect->x,rect->y,rect->width,rect->height);
  if(kind==NXS_BUTTON&&canvas)native_button_size_changed(form,&header);
  return canvas?0:1;
}
static int paint_checkbox(void*s,const void*e,const void*d,const void*style,const void*i,const struct Rect*r)
{return paint_form(2,s,e,d,style,i,r)?original_checkbox(s,e,d,style,i,r):0;}
static int paint_radio(void*s,const void*e,const void*d,const void*style,const void*i,const struct Rect*r)
{return paint_form(3,s,e,d,style,i,r)?original_radio(s,e,d,style,i,r):0;}
static int paint_button(void*s,const void*e,const void*d,const void*style,const void*i,const struct Rect*r)
{int kind=forms_color_enabled&&input_form_kind((void *)e)==NXS_COLORWELL?NXS_COLORWELL:NXS_BUTTON;
 return paint_form(kind,s,e,d,style,i,r)?original_button(s,e,d,style,i,r):0;}
static struct SizeI native_form_size(void *self,int part) {
  if(part==9&&form_sizes[2].width>0)return form_sizes[2];
  if(part==10&&form_sizes[3].width>0)return form_sizes[3];
  return original_form_size(self,part);
}
static struct SizeI native_theme_size(void *self,int part,int state,const void *extra) {
  void *web=((void *(*)(void))(base+0xc5771c4))();
  if(self==web&&part==0&&form_sizes[2].width>0)return form_sizes[2];
  if(self==web&&part==9&&form_sizes[3].width>0)return form_sizes[3];
  return original_theme_size(self,part,state,extra);
}
static void box_paint(void *self,const void *info) {
  void *fragment=*(void **)((char *)self+32),*layout=fragment?decode_member(fragment):NULL;
  void *node=layout?((void *(*)(const void *))(base+0xe565500))(layout):NULL;
  void *previous=native_parent;native_parent=node;
  original_box_paint(self,info);
  struct NativeForm *form=node?find_form(node):NULL;if(form&&form->kind==NXS_LISTBOX&&!list_style(form->node))list_forget(form);
  native_parent=previous;
}
static int native_button_parent(void) {struct NativeForm *f=form_ancestor(native_parent);return f&&(f->kind==NXS_BUTTON?native_button_owned(f):(f->kind==NXS_POPUP||f->kind==NXS_COLORWELL||text_kind(f->kind)||list_owned(f))&&f->painted);}
static void inline_children(void*s,const void*i,const void*a,const void*b,void*c)
{if(!native_button_parent())original_inline_children(s,i,a,b,c);}
static void block_children(void*s,const void*i,uint64_t offset)
{if(!native_button_parent())original_block_children(s,i,offset);}
static struct FloatPoint form_point(struct NativeForm *form,const void *event) {
  void *layout=decode_member((const char *)form->node+48);
  if(!layout)return (struct FloatPoint){-1,-1};
  void *view=((void *(*)(const void *))(base+NXS_COORDINATE_FRAME_VIEW_OFFSET))(layout);
  if(!view)return (struct FloatPoint){-1,-1};
  struct FloatPoint root=((struct FloatPoint (*)(const void *))(base+NXS_COORDINATE_EVENT_ROOT_OFFSET))(event);
  /* Client quads are frame coordinates. RootFrameToDocument would add the
   * page scroll again; reuse the engine's frame-to-frame conversion instead. */
  struct FloatPoint local=((struct FloatPoint (*)(const void *,const struct FloatPoint *))(base+NXS_COORDINATE_FRAME_POINT_OFFSET))(view,&root);
  struct FloatRect box=((struct FloatRect (*)(const void *))(base+NXS_COORDINATE_CLIENT_BOX_OFFSET))(form->node);
  if(box.width<=0||box.height<=0)return (struct FloatPoint){-1,-1};
  return (struct FloatPoint){(local.x-box.x)*form->rect.width/box.width,(local.y-box.y)*form->rect.height/box.height};
}
static void finish_form(double x,double y,unsigned modifiers) {
  struct NativeForm *form=active_form;if(!form)return;
  if(form->kind==NXS_LISTBOX){uint32_t node=radio_node_id(form->node);uint64_t control=form->control,before=form->list.state.actions;active_form=NULL;struct NXSResponse *r=list_form_request(form,4,x,y,modifiers);for(unsigned i=0;r&&r->parts[0].y&&i<100;i++){struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);r=native_list_request(control,5,0,0,1);}list_after_input(node,control,before);return;}
  if(text_kind(form->kind)) {
    void *node=form->node;uint64_t control=form->control;
    form->text_x=x;form->text_y=y;end_text_pointer(form,1);form=find_form(node);
    if(form&&form->control==control)invalidate_form(form);return;
  }
  active_form=NULL;
  struct NXSResponse *response=form_request(form,4,x,y,modifiers);
  for(int n=0;response&&response->parts[0].y&&n<100;n++) {
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
    response=form_request(form,5,0,0,0);
  }
  native_control_action_snapshot(response,form->actions_before,&form->checkbox_action);
  click_form=form;form_click_allowed=response&&!response->parts[0].y&&response->parts[0].width>form->actions_before;
  if(form->kind==NXS_POPUP){click_form=NULL;popup_after_input(form,response);refresh_form_watch();return;}
  if(form->kind==NXS_SLIDER){
    void *node=form->node;uint64_t control=form->control;click_form=NULL;
    apply_slider_value(form,response,2);
    form=find_form(node);if(form&&form->control==control)invalidate_form(form);
    refresh_form_watch();return;
  }
  form_click_time=0;invalidate_form(form);
}
static struct MouseDispatchResult mouse_dispatch(void *manager,void *target,const void *type,const void *event,
    const void *last,void *related,int check,const void *pointer_id,const void *pointer_type,void *down,void *up) {
  struct MouseDispatchResult list_result;
  if(forms_lists_enabled&&list_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up,&list_result))return list_result;
  uintptr_t atom=*(const uintptr_t *)type;
  unsigned modifiers=event_modifiers(event);
  if(same_atom(atom,0x123a55f8)&&*(const int *)((const char *)event+120)==0)radio_pointer_gate.armed=0;
  if(forms_radio_groups_enabled&&radio_pointer_gate.armed&&
     same_atom(atom,0x123a5590)&&*(const int *)((const char *)event+120)==0) {
    uint32_t origin=radio_pointer_gate.origin;uint64_t control=radio_pointer_gate.control;radio_pointer_gate.armed=0;
    click_form=NULL;
    void *node=radio_node_for_id(origin);struct NativeForm *form=node?find_form(node):NULL;
    if(!form||form->control!=control||form->kind!=NXS_RADIO)return (struct MouseDispatchResult){0};
    void *chosen=radio_pointer_target(form);
    if(!chosen){radio_pointer_complete(origin,control);return (struct MouseDispatchResult){0};}
    /* Keep Blink's actual PointerEvent construction, source metadata and
     * preactivation/cancellation. Only the native action target changes. */
    struct MouseDispatchResult result=original_mouse_dispatch(manager,chosen,type,event,last,related,check,pointer_id,pointer_type,down,up);
    radio_pointer_complete(origin,control);return result;
  }
  if(forms_popups_enabled){
    int down_popup=same_atom(atom,0x123a55f8)&&*(const int *)((const char *)event+120)==0;
    void *node=down_popup&&target?((void *(*)(void *))(*(uintptr_t **)target)[9])(target):NULL;
    struct NativeForm *popup=down_popup?form_ancestor(node):active_form;
    if(popup&&popup->kind==NXS_POPUP){
      if(down_popup){
        if(active_form)finish_form(-10000,-10000,0);
        const void *previous=popup_mouse_event;popup_mouse_event=event;
        struct MouseDispatchResult result=original_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up);
        popup_mouse_event=previous;return result;
      }
      if(active_form==popup&&same_atom(atom,0x123a5600)){
        struct FloatPoint point=form_point(popup,event);form_request(popup,3,point.x,point.y,modifiers);
      } else if(active_form==popup&&same_atom(atom,0x123a5608)&&*(const int *)((const char *)event+120)==0){
        struct FloatPoint point=form_point(popup,event);finish_form(point.x,point.y,modifiers);
      }
      return original_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up);
    }
  }
  int slider_up=active_form&&active_form->kind==NXS_SLIDER&&same_atom(atom,0x123a5608)&&*(const int *)((const char *)event+120)==0;
  void *slider_node=slider_up?active_form->node:NULL;
  uint64_t slider_control=slider_up?active_form->control:0;
  struct NativeForm *slider=NULL;
  if(forms_sliders_enabled&&same_atom(atom,0x123a55f8)&&*(const int *)((const char *)event+120)==0){
    void *node=target?((void *(*)(void *))(*(uintptr_t **)target)[9])(target):NULL;
    slider=form_ancestor(node);
    if(slider&&slider->kind!=NXS_SLIDER)slider=NULL;
  }
  int slider_move=active_form&&active_form->kind==NXS_SLIDER&&same_atom(atom,0x123a5600);
  if(slider||slider_move||slider_up){
    if(!slider)slider=active_form;
    void *node=slider->node;uint64_t control=slider->control;
    struct FloatPoint point=form_point(slider,event);
    if(slider_up)finish_form(point.x,point.y,modifiers);
    struct MouseDispatchResult result=original_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up);
    slider=find_form(node);
    if(!slider||slider->control!=control)return result;
    unsigned flags=result.event?*(const unsigned short *)((char *)result.event+32):0;
    if(slider_up){
      if(slider->node==slider_node&&slider->control==slider_control)
        ((void (*)(void *))(base+0xefb27ac))(slider->node);
    } else if((flags&0x100)&&!(flags&0x20)&&form_enabled(slider->node)){
      if(slider_move){
        struct NXSResponse *r=form_request(slider,3,point.x,point.y,modifiers);
        apply_slider_value(slider,r,2);
      } else if(sync_slider_model(slider)){
        if(active_form)finish_form(-1,-1,0);
        /* Finishing the prior control can synchronously run application input
         * handlers. Revalidate this binding before touching it again. */
        slider=find_form(node);
        if(!slider||slider->control!=control||!sync_slider_model(slider))return result;
        click_form=NULL;slider->enabled=1;
        struct NXSResponse *r=sync_form_focus(slider,form_request(slider,1,0,0,0));
        if(r){
          slider->actions_before=slider->actions_seen=r->parts[0].width;
          r=form_request(slider,2,point.x,point.y,modifiers);
          if(r&&r->parts[0].y){active_form=slider;refresh_form_watch();invalidate_form(slider);}
        }
      }
    }
    return result;
  }
  if(forms_radio_groups_enabled&&same_atom(atom,0x123a55f8)&&*(const int *)((const char *)event+120)==0) {
    void *node=target?((void *(*)(void *))(*(uintptr_t **)target)[9])(target):NULL;
    struct NativeForm *form=form_ancestor(node);
    if(form&&form->kind==NXS_RADIO&&form->painted) {
      uint32_t origin=radio_node_id(form->node);uint64_t control=form->control;
      if(active_form)finish_form(-10000,-10000,0);
      click_form=NULL;radio_pointer_gate=(struct RadioPointerGate){origin,control,1};
      struct MouseDispatchResult result=original_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up);
      node=radio_node_for_id(origin);form=node?find_form(node):NULL;
      unsigned flags=result.event?*(const unsigned short *)((char *)result.event+32):0;
      if(form&&form->control==control&&form->kind==NXS_RADIO&&input_form_kind(node)==NXS_RADIO&&
         (flags&0x100)&&!(flags&0x20)) {
        struct NXSResponse *sync=form_request(form,1,0,0,0);
        if(sync) {
          form->actions_before=sync->parts[0].width;form->radio_clicks=*(const unsigned *)((const char *)event+160);
          struct FloatPoint point=form_point(form,event);
          struct NXSResponse *response=form_request(form,2,point.x,point.y,modifiers);
          if(response&&response->parts[0].y){active_form=form;invalidate_form(form);}
        }
      }
      return result;
    }
  }
  if(same_atom(atom,0x123a55f8)&&*(const int *)((const char *)event+120)==0) {
    if(active_form)finish_form(-1,-1,0);
    click_form=NULL;
    void *node=target?((void *(*)(void *))(*(uintptr_t **)target)[9])(target):NULL;
    struct NativeForm *form=form_ancestor(node);
    if(form&&form->kind!=NXS_COLORWELL&&!text_kind(form->kind)&&(form_enabled(form->node)||(forms_radio_groups_enabled&&form->kind==NXS_RADIO))) {
      form->enabled=1;form->state=form_state(form->node,form->kind);
      struct NXSResponse *sync=form_request(form,1,0,0,0);
      if(sync) {
        form->actions_before=sync->parts[0].width;
        form->radio_clicks=*(const unsigned *)((const char *)event+160);
        struct FloatPoint point=form_point(form,event);
        struct NXSResponse *response=form_request(form,2,point.x,point.y,modifiers);
        if(response&&response->parts[0].y){
          active_form=form;
          if(form->kind==NXS_RADIO&&forms_radio_groups_enabled)
            radio_pointer_gate=(struct RadioPointerGate){radio_node_id(form->node),form->control,1};
          invalidate_form(form);note("native form tracking started");
        }
      }
    }
  } else if(active_form&&!text_kind(active_form->kind)&&same_atom(atom,0x123a5600)) {
    struct FloatPoint point=form_point(active_form,event);
    form_request(active_form,3,point.x,point.y,modifiers);invalidate_form(active_form);
  } else if(active_form&&same_atom(atom,0x123a5608)&&*(const int *)((const char *)event+120)==0) {
    struct FloatPoint point=form_point(active_form,event);finish_form(point.x,point.y,modifiers);
  }
  return original_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up);
}
static int dom_dispatch(void *dispatcher) {
  void *node=*(void **)dispatcher,*event=*((void **)dispatcher+1);
  uintptr_t atom=*(const uintptr_t *)((const char *)event+24);
  int trusted=!!(*(const unsigned short *)((const char *)event+32)&0x100);
  struct NXSControlActivation search_action={0};
  if(forms_search_actions_enabled&&trusted) {
    if(same_atom(atom,0x123a55f8)||same_atom(atom,0x123a55d8))native_activation_clear(&native_search_activation);
    struct NativeForm *owner=native_search_activation.serial?form_ancestor(node):NULL;
    if(owner&&(uintptr_t)owner->node==native_search_activation.target&&owner->control==native_search_activation.control) {
      uint64_t stamp=*(const uint64_t *)((const char *)event+88);
      if(same_atom(atom,0x123a5608))native_search_click_time=stamp;
      if(same_atom(atom,0x123a5590)&&native_search_click_time==stamp) {
        search_action=native_search_activation;native_activation_clear(&native_search_activation);
      }
    }
  }
  if(forms_search_enabled&&(*(const unsigned short *)((const char *)event+32)&0x100)&&same_atom(atom,0x123a5590)) {
    struct NativeForm *form=form_ancestor(node);
    /* The original shadow cancel button is hidden by the complete native
     * field. Page listeners still run; its second widget default must not. */
    if(form&&form->kind==NXS_SEARCHFIELD&&form->painted)*(unsigned short *)((char *)event+32)|=0x40;
  }
  struct NXSCheckboxActivation previous_checkbox=native_checkbox_activation;int checkbox_scope=0;
  if((*(const unsigned short *)((const char *)event+32)&0x100)&&click_form) {
    uint64_t stamp=*(const uint64_t *)((const char *)event+88);
    if(same_atom(atom,0x123a5608))form_click_time=stamp;
    if(same_atom(atom,0x123a5590)&&stamp==form_click_time&&form_ancestor(node)==click_form) {
      struct NativeForm *source=click_form;int allowed=form_click_allowed;click_form=NULL;
      if(allowed&&source->kind==NXS_CHECKBOX) {
        previous_checkbox=native_checkbox_enter(radio_node_id(source->node),source->control,source->checkbox_action);checkbox_scope=1;
      }
      if(!allowed){note("native form cancelled activation");return 3;}
    }
  }
  void *previous_node=form_key_node,*previous_event=form_key_event,*previous_dispatch=native_dispatch_event;
  native_dispatch_event=event;
  uint64_t previous_control=form_key_control;
  struct NativeForm *keyboard_form=NULL;
  if(forms_input_enabled&&(*(const unsigned short *)((const char *)event+32)&0x100)&&
     (same_atom(atom,0x123a55d8)||same_atom(atom,0x123a55e0)||same_atom(atom,0x123a55e8)))
    keyboard_form=form_ancestor(node);
  form_key_node=keyboard_form?keyboard_form->node:NULL;
  form_key_event=keyboard_form?event:NULL;
  form_key_control=keyboard_form?keyboard_form->control:0;
  int result=native_wheel_dispatch(dispatcher);
  if(search_action.serial&&!(*(const unsigned short *)((char *)event+32)&0x20)) {
    void *owner=(void *)(uintptr_t)search_action.target;uint64_t control=search_action.control,item=search_action.item;
    if(native_activation_take(&search_action,(uintptr_t)owner,control)) {
      if(item==NXS_SEARCH_CANCEL)search_clear(owner,control);else search_activate(owner,event,control);
    }
  }
  if(checkbox_scope)native_checkbox_activation=previous_checkbox;
  form_key_node=previous_node;form_key_event=previous_event;
  form_key_control=previous_control;native_dispatch_event=previous_dispatch;
  return result;
}
static void element_detach(void *node,int reattach) {
  color_forget(node);
  struct NativeForm **cursor=&native_forms;
  while(*cursor&&(*cursor)->node!=node)cursor=&(*cursor)->next;
  struct NativeForm *form=*cursor;
  if(form) {
    if(native_search_activation.control==form->control)native_activation_clear(&native_search_activation);
    native_wheel_binding(form,0);
    if(active_form==form)active_form=NULL;
    if(click_form==form)click_form=NULL;
    form_request(form,6,0,0,0);*cursor=form->next;popup_free_model(form);free(form->title);free(form);
    refresh_form_watch();
  }
  original_element_detach(node,reattach);
}
#include "checkbox-activation.inc"
#include "forms-input.inc"
#include "forms-radios.inc"
#include "form-labels.inc"
#include "forms-sliders.inc"
#include "forms-layout.inc"
#include "forms-buttons.inc"
#include "forms-popups.inc"
#include "forms-progress.inc"
#include "forms-text.inc"
#include "forms-color.inc"
#include "forms-lists.inc"
#include "forms-text-scroll.inc"
#include "forms-wheel.inc"
static struct Detour form_detours[]={
 {NXS_CHECKBOX_OFFSET,nxs_checkbox_bytes,paint_checkbox,(void **)&original_checkbox},
 {NXS_RADIO_OFFSET,nxs_radio_bytes,paint_radio,(void **)&original_radio},
 {NXS_BUTTON_OFFSET,nxs_button_bytes,paint_button,(void **)&original_button},
 {NXS_FORM_SIZE_OFFSET,nxs_form_size_bytes,native_form_size,(void **)&original_form_size},
 {NXS_THEME_SIZE_OFFSET,nxs_theme_size_bytes,native_theme_size,(void **)&original_theme_size},
 {NXS_BOX_PAINT_OFFSET,nxs_box_paint_bytes,box_paint,(void **)&original_box_paint},
 {NXS_INLINE_CHILDREN_OFFSET,nxs_inline_children_bytes,inline_children,(void **)&original_inline_children},
 {NXS_BLOCK_CHILDREN_OFFSET,nxs_block_children_bytes,block_children,(void **)&original_block_children},
 {NXS_DOM_DISPATCH_OFFSET,nxs_dom_dispatch_bytes,dom_dispatch,(void **)&original_dom_dispatch},
 {NXS_ELEMENT_DETACH_OFFSET,nxs_element_detach_bytes,element_detach,(void **)&original_element_detach},
 {NXS_MOUSE_DISPATCH_OFFSET,nxs_mouse_dispatch_bytes,mouse_dispatch,(void **)&original_mouse_dispatch}
};
static int prepare_forms(void){return (!forms_radio_groups_enabled||guard_radio_calls())&&(!forms_labels_enabled||prepare_detours(form_label_detours,sizeof(form_label_detours)/sizeof(*form_label_detours)))&&guard_form_coordinates()&&guard_form_layout()&&prepare_detours(form_layout_detours,sizeof(form_layout_detours)/sizeof(*form_layout_detours))&&prepare_detours(button_model_detours,sizeof(button_model_detours)/sizeof(*button_model_detours))&&prepare_detours(form_detours,sizeof(form_detours)/sizeof(*form_detours))&&
  (!forms_input_enabled||(prepare_form_input()&&guard_checkbox_calls()&&prepare_detours(checkbox_activation_detours,sizeof(checkbox_activation_detours)/sizeof(*checkbox_activation_detours))))&&
  (!forms_progress_enabled||prepare_detours(&progress_detour,1))&&
  (!forms_color_enabled||(guard_color_calls()&&prepare_detours(color_detours,sizeof(color_detours)/sizeof(*color_detours))))&&
  (!forms_sliders_enabled||prepare_detours(slider_detours,sizeof(slider_detours)/sizeof(*slider_detours)))&&
  (!forms_popups_enabled||(guard_popup_model_calls()&&prepare_detours(popup_detours,sizeof(popup_detours)/sizeof(*popup_detours))))&&
  (!forms_lists_enabled||(guard_list_calls()&&guard_list_hit_calls()&&prepare_detours(list_detours,sizeof(list_detours)/sizeof(*list_detours))))&&
  (!forms_text_enabled||(guard_text_calls()&&prepare_detours(text_detours,sizeof(text_detours)/sizeof(*text_detours))))&&
  (!(forms_multiline_viewport_enabled||forms_lists_enabled)||(guard_multiline_scroll_calls()&&prepare_detours(multiline_scroll_detours,sizeof(multiline_scroll_detours)/sizeof(*multiline_scroll_detours))))&&
  (!forms_wheel_enabled||(guard_wheel_calls()&&prepare_detours(wheel_detours,sizeof(wheel_detours)/sizeof(*wheel_detours))));}
static void activate_forms(void){if(forms_labels_enabled)activate_detours(form_label_detours,sizeof(form_label_detours)/sizeof(*form_label_detours));activate_detours(form_layout_detours,sizeof(form_layout_detours)/sizeof(*form_layout_detours));activate_detours(button_model_detours,sizeof(button_model_detours)/sizeof(*button_model_detours));activate_detours(form_detours,sizeof(form_detours)/sizeof(*form_detours));
  if(forms_input_enabled){activate_form_input();activate_detours(checkbox_activation_detours,sizeof(checkbox_activation_detours)/sizeof(*checkbox_activation_detours));}
  if(forms_progress_enabled)activate_detours(&progress_detour,1);
  if(forms_color_enabled)activate_detours(color_detours,sizeof(color_detours)/sizeof(*color_detours));
  if(forms_sliders_enabled)activate_detours(slider_detours,sizeof(slider_detours)/sizeof(*slider_detours));
  if(forms_popups_enabled)activate_detours(popup_detours,sizeof(popup_detours)/sizeof(*popup_detours));
  if(forms_lists_enabled)activate_detours(list_detours,sizeof(list_detours)/sizeof(*list_detours));
  if(forms_text_enabled)activate_detours(text_detours,sizeof(text_detours)/sizeof(*text_detours));
  if(forms_multiline_viewport_enabled||forms_lists_enabled)activate_detours(multiline_scroll_detours,sizeof(multiline_scroll_detours)/sizeof(*multiline_scroll_detours));
  if(forms_wheel_enabled)activate_detours(wheel_detours,sizeof(wheel_detours)/sizeof(*wheel_detours));}
