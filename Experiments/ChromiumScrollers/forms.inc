/* Blink element/model and event bindings only. Native controls stay in the
 * separately loaded UI provider. Exact Chromium build; GPL-2.0-or-later. */
#include "pinned-forms.h"
struct NativeForm {
  struct NativeForm *next;
  void *node;
  int kind,enabled,state,painted;
  struct Rect rect;
  char *title;
  double actions_before;
};
struct FloatRect {float x,y,width,height;};
struct SizeI {int width,height;};
struct MouseDispatchResult {void *event;int result;};
static struct NativeForm *native_forms,*active_form,*click_form;
static __thread void *native_parent;
static int form_click_allowed;
static uint64_t form_click_time;
static int forms_available;
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
static struct NativeForm *form_ancestor(void *node) {
  for(int i=0;node&&i<256;i++) {
    struct NativeForm *f=find_form(node);if(f&&f->painted)return f;
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
static char *form_title(void *node) {
  void *string=input_element(node)?((void *(*)(void *))(base+0xefa5dc0))(node):
    ((void *(*)(void *,void *))(base+0xddf7648))(node,NULL);
  if(!string)return strdup("");
  uint32_t length=*(const uint32_t *)((const char *)string+4),flags=*(const uint32_t *)((const char *)string+8);
  char *result=length<=65536?malloc((size_t)length*4+1):NULL;
  size_t used=0;
  for(uint32_t i=0;result&&i<length;i++) {
    uint32_t c;
    if(flags&1)c=((const unsigned char *)string)[12+i];
    else {
      const uint16_t *text=(const uint16_t *)((const char *)string+12);c=text[i];
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
  ((void (*)(void *))(base+0x7246038))(&string);
  return result;
}
static struct NXSResponse *form_request(struct NativeForm *form,int operation,double x,double y,unsigned modifiers) {
  size_t title_size=operation==1&&form->title?strlen(form->title):0;
  size_t size=sizeof(struct NXSControlRequest)+title_size;
  struct NXSControlRequest *req=calloc(1,size);if(!req)return NULL;
  *req=(struct NXSControlRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=form->kind,.control=(uintptr_t)form->node,.text_size=title_size,
    .width=form->rect.width,.height=form->rect.height,.minimum=0,.maximum=1,.value=form->state,
    .x=x,.y=y,.enabled=form->enabled,.state=form->state,.modifiers=modifiers};
  if(title_size)memcpy(req+1,form->title,title_size);
  struct NXSResponse *response=exchange_bytes(req,size);free(req);return response;
}
static void invalidate_form(struct NativeForm *form) {
  void *layout=decode_member((const char *)form->node+48);
  if(layout)((void (*)(void *,int))(base+0xe55f5f8))(layout,3); /* Chromium kStyle. */
}
static int paint_form(int kind,void *self,const void *element,const void *document,const void *style,const void *info,const struct Rect *rect) {
  struct NativeForm *form=find_form(element);
  if(form)form->painted=0;
  if(rect->width<1||rect->height<1)return 0;
  char *title=kind==1?form_title((void *)element):strdup("");
  if(!title)return 1;
  if(!form){form=calloc(1,sizeof(*form));if(!form){free(title);return 1;}form->node=(void *)element;form->next=native_forms;native_forms=form;}
  free(form->title);form->title=title;form->kind=kind;form->rect=*rect;
  form->enabled=form_enabled(form->node);form->state=form_state(form->node,kind);
  struct NXSResponse *response=form_request(form,1,0,0,0);
  if(!response||response->width<1||response->height<1||response->stride!=response->width*4||
     sizeof(*response)+(size_t)response->stride*response->height!=response->size){form->painted=0;return 1;}
  struct NXSResponse header=*response;
  uint32_t *pixels=malloc((size_t)header.stride*header.height);if(!pixels){form->painted=0;return 1;}
  memcpy(pixels,response+1,(size_t)header.stride*header.height);
  void *canvas=*(void **)*(void **)info;
  if(canvas)draw_native_bitmap(canvas,pixels,header.width,rect->x,rect->y,0,0,header.width,header.height);
  free(pixels);form->painted=!!canvas;
  return canvas?0:1;
}
static int paint_checkbox(void*s,const void*e,const void*d,const void*style,const void*i,const struct Rect*r)
{return paint_form(2,s,e,d,style,i,r)?original_checkbox(s,e,d,style,i,r):0;}
static int paint_radio(void*s,const void*e,const void*d,const void*style,const void*i,const struct Rect*r)
{return paint_form(3,s,e,d,style,i,r)?original_radio(s,e,d,style,i,r):0;}
static int paint_button(void*s,const void*e,const void*d,const void*style,const void*i,const struct Rect*r)
{return paint_form(1,s,e,d,style,i,r)?original_button(s,e,d,style,i,r):0;}
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
  original_box_paint(self,info);native_parent=previous;
}
static int native_button_parent(void) {struct NativeForm *f=find_form(native_parent);return f&&f->kind==1&&f->painted;}
static void inline_children(void*s,const void*i,const void*a,const void*b,void*c)
{if(!native_button_parent())original_inline_children(s,i,a,b,c);}
static void block_children(void*s,const void*i,uint64_t offset)
{if(!native_button_parent())original_block_children(s,i,offset);}
static struct FloatPoint form_point(struct NativeForm *form,const void *event) {
  void *layout=decode_member((const char *)form->node+48);
  if(!layout)return (struct FloatPoint){-1,-1};
  void *view=((void *(*)(const void *))(base+0xe11b43c))(layout);
  if(!view)return (struct FloatPoint){-1,-1};
  struct FloatPoint root=((struct FloatPoint (*)(const void *))(base+0xac35e38))(event);
  struct FloatPoint local=((struct FloatPoint (*)(const void *,const struct FloatPoint *))(base+0xdf98bbc))(view,&root);
  struct FloatRect box=((struct FloatRect (*)(const void *))(base+0xef58ad4))(form->node);
  if(box.width<=0||box.height<=0)return (struct FloatPoint){-1,-1};
  return (struct FloatPoint){(local.x-box.x)*form->rect.width/box.width,(local.y-box.y)*form->rect.height/box.height};
}
static void finish_form(double x,double y,unsigned modifiers) {
  struct NativeForm *form=active_form;if(!form)return;active_form=NULL;
  struct NXSResponse *response=form_request(form,4,x,y,modifiers);
  for(int n=0;response&&response->parts[0].y&&n<100;n++) {
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
    response=form_request(form,5,0,0,0);
  }
  click_form=form;form_click_allowed=response&&!response->parts[0].y&&response->parts[0].width>form->actions_before;
  form_click_time=0;invalidate_form(form);
}
static struct MouseDispatchResult mouse_dispatch(void *manager,void *target,const void *type,const void *event,
    const void *last,void *related,int check,const void *pointer_id,const void *pointer_type,void *down,void *up) {
  uintptr_t atom=*(const uintptr_t *)type;
  unsigned modifiers=event_modifiers(event);
  if(same_atom(atom,0x123a55f8)&&*(const int *)((const char *)event+120)==0) {
    if(active_form)finish_form(-1,-1,0);
    click_form=NULL;
    void *node=target?((void *(*)(void *))(*(uintptr_t **)target)[9])(target):NULL;
    struct NativeForm *form=form_ancestor(node);
    if(form&&form_enabled(form->node)) {
      form->enabled=1;form->state=form_state(form->node,form->kind);
      struct NXSResponse *sync=form_request(form,1,0,0,0);
      if(sync) {
        form->actions_before=sync->parts[0].width;
        struct FloatPoint point=form_point(form,event);
        struct NXSResponse *response=form_request(form,2,point.x,point.y,modifiers);
        if(response&&response->parts[0].y){active_form=form;invalidate_form(form);note("native form tracking started");}
      }
    }
  } else if(active_form&&same_atom(atom,0x123a5600)) {
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
  if((*(const unsigned short *)((const char *)event+32)&0x100)&&click_form) {
    uint64_t stamp=*(const uint64_t *)((const char *)event+88);
    if(same_atom(atom,0x123a5608))form_click_time=stamp;
    if(same_atom(atom,0x123a5590)&&stamp==form_click_time&&form_ancestor(node)==click_form) {
      int allowed=form_click_allowed;click_form=NULL;
      if(!allowed){note("native form cancelled activation");return 3;}
    }
  }
  return original_dom_dispatch(dispatcher);
}
static void element_detach(void *node,int reattach) {
  struct NativeForm **cursor=&native_forms;
  while(*cursor&&(*cursor)->node!=node)cursor=&(*cursor)->next;
  struct NativeForm *form=*cursor;
  if(form) {
    if(active_form==form)active_form=NULL;
    if(click_form==form)click_form=NULL;
    form_request(form,6,0,0,0);*cursor=form->next;free(form->title);free(form);
  }
  original_element_detach(node,reattach);
}
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
static int prepare_forms(void){return prepare_detours(form_detours,sizeof(form_detours)/sizeof(*form_detours));}
static void activate_forms(void){activate_detours(form_detours,sizeof(form_detours)/sizeof(*form_detours));}
