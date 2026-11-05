/* Select application data/lifecycle bindings. NSPopUpButton/NSMenu stay native. */
#include "pinned-popups.h"
struct PopupSnapshot {
  struct NXSControlPopupRequest *request;
  int *indices;
  void **nodes;
};
static int (*original_popup_paint)(void *,const void *,const void *,const void *,const void *,const struct Rect *);
static void (*original_select_default)(void *,void *);
static void (*original_internal_popup_show)(void *,int);
static void (*original_internal_popup_hide)(void *);
static void popup_sync_origin(struct NativeForm *form)
{
  void *document=node_document(form->node);
  void *window=document?decode_member((char *)document+264):NULL;
  void *frame=window?decode_member((char *)window+32):NULL;
  void *page=frame?decode_member((char *)frame+32):NULL;
  void *chrome=page?decode_member((char *)page+76):NULL;
  void *view=document?((void *(*)(const void *))(base+0xeec73e8))(document):NULL;
  if(!chrome||!view)return;
  /* Use the engine's clipped local-root bounds and its actual viewport/window
   * conversion. NativeUI supplies menu placement relative to that anchor. */
  struct Rect local=((struct Rect (*)(const void *))(base+0xef57da8))(form->node);
  struct Rect screen=((struct Rect (*)(void *,const struct Rect *,const void *))
    (*(uintptr_t **)chrome)[15])(chrome,&local,view);
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=13,
    .process=identity(),.kind=NXS_POPUP,.control=form->control,.x=screen.x,.y=screen.y};
  exchange_bytes(&request,sizeof(request));
}
static void popup_engine_closed(void *engine)
{
  /* The stock PagePopup calls DidClosePopup after its window closes. NativeUI
   * owns that window now, so forward the same lifecycle notification directly.
   * Hide alone only cancels selection when there is no stock PagePopup. */
  if(engine)((void (*)(void *))(base+0xe753cd4))(engine);
}
static struct NXSResponse *popup_visibility_request(struct NativeForm *form,int open)
{
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=14,
    .process=identity(),.kind=NXS_POPUP,.control=form->control,.state=open};
  return exchange_bytes(&request,sizeof(request));
}
static int popup_element(void *node)
{
  return *(uintptr_t *)node==base+0x11ced808+16&&
    *((unsigned char *)node+608)&&!*((unsigned char *)node+609);
}
static void popup_free_model(struct NativeForm *form)
{
  free(form->popup_model);free(form->popup_indices);free(form->popup_nodes);
  form->popup_model=NULL;form->popup_indices=NULL;form->popup_nodes=NULL;
  form->popup_size=0;form->popup_count=0;
}
static void popup_snapshot_free(struct PopupSnapshot *snapshot)
{free(snapshot->request);free(snapshot->indices);free(snapshot->nodes);memset(snapshot,0,sizeof(*snapshot));}
static int popup_snapshot(void *node,struct PopupSnapshot *snapshot)
{
  memset(snapshot,0,sizeof(*snapshot));
  /* The real SelectedListIndex calls GetListItems and recalculates it when
   * dirty. Only its pinned vector representation is decoded below. */
  int selected=((int (*)(const void *))(base+0xe0ff7b8))(node);
  unsigned count=*(unsigned *)((char *)node+588);
  void *items=*(void **)((char *)node+576);
  if(count>65536||(!items&&count))return 0;
  snapshot->request=calloc(1,sizeof(*snapshot->request)+65536);
  snapshot->indices=calloc(count?count:1,sizeof(int));snapshot->nodes=calloc(count?count:1,sizeof(void *));
  if(!snapshot->request||!snapshot->indices||!snapshot->nodes){popup_snapshot_free(snapshot);return 0;}
  struct NXSControlPopupRequest *request=snapshot->request;
  *request=(struct NXSControlPopupRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=11,.kind=NXS_POPUP,.selected=-1};
  unsigned char *data=(unsigned char *)(request+1);
  for(unsigned i=0;i<count;i++) {
    void *item=decode_member((char *)items+i*4);if(!item)continue;
    unsigned kind=*((unsigned char *)*(uintptr_t *)item-17);
    if(kind==0x38&&((int (*)(void *,int))(base+0xe0f7434))(item,1))continue;
    void *label=((void *(*)(const void *,const void *))(base+0xe102cd0))(node,item);
    char *title=string_text(label);((void (*)(void *))(base+0x7246038))(&label);
    if(!title){popup_snapshot_free(snapshot);return 0;}
    size_t length=strlen(title);
    if(request->text_size+8+length>65536){free(title);popup_snapshot_free(snapshot);return 0;}
    uint32_t flags=kind==0x38?(form_enabled(item)?1:0):kind==0x37?0:2;
    uint32_t size=length;memcpy(data+request->text_size,&flags,4);memcpy(data+request->text_size+4,&size,4);
    memcpy(data+request->text_size+8,title,length);free(title);request->text_size+=8+length;
    snapshot->indices[request->count]=i;snapshot->nodes[request->count]=item;
    if((int)i==selected)request->selected=request->count;
    request->count++;
  }
  return 1;
}
static int popup_same_model(struct NativeForm *form,struct PopupSnapshot *snapshot)
{
  struct NXSControlPopupRequest *request=snapshot->request;
  return form->popup_model&&form->popup_size==request->text_size&&form->popup_count==request->count&&
    form->popup_selected==request->selected&&!memcmp(form->popup_model,request+1,request->text_size)&&
    !memcmp(form->popup_nodes,snapshot->nodes,request->count*sizeof(void *));
}
static struct NXSResponse *sync_popup_model(struct NativeForm *form,struct NXSResponse *response)
{
  struct PopupSnapshot snapshot;if(!popup_snapshot(form->node,&snapshot))return NULL;
  struct NXSControlPopupRequest *request=snapshot.request;
  if(popup_same_model(form,&snapshot)||response->parts[6].width>0){popup_snapshot_free(&snapshot);return response;}
  request->process=identity();request->control=form->control;
  response=exchange_bytes(request,sizeof(*request)+request->text_size);
  if(response&&response->parts[3].x==1) {
    popup_free_model(form);
    form->popup_model=malloc(request->text_size?request->text_size:1);
    if(!form->popup_model){popup_snapshot_free(&snapshot);return NULL;}
    memcpy(form->popup_model,request+1,request->text_size);form->popup_size=request->text_size;
    form->popup_count=request->count;form->popup_selected=request->selected;
    form->popup_indices=snapshot.indices;form->popup_nodes=snapshot.nodes;
    snapshot.indices=NULL;snapshot.nodes=NULL;
  } else response=NULL;
  popup_snapshot_free(&snapshot);return response;
}
static void popup_after_input(struct NativeForm *form,struct NXSResponse *response)
{
  if(!response)return;
  void *node=form->node;uint64_t control=form->control;
  int visible=response->parts[6].width>0;
  int action=response->parts[0].width>form->actions_seen;
  int selection=(int)response->parts[0].x;
  double action_count=response->parts[0].width;
  form->actions_seen=response->parts[0].width;
  if(visible&&!form->popup_open) {
    /* Run the real menu-list lifecycle (:open, observers, accessibility
     * notification). Its InternalPopupMenu::Show is bound below. */
    void *type=decode_member((char *)node+168);
    if(type)((void (*)(void *,int))(base+0xe116c40))(type,1); /* PopupMenu::kOther */
    form=find_form(node);if(!form||form->control!=control)return;
  }
  if(!visible&&form->popup_open) {
    form->popup_open=0;
    popup_engine_closed(form->popup_engine);
    form=find_form(node);if(!form||form->control!=control)return;
  }
  if(action&&selection>=0&&(unsigned)selection<form->popup_count) {
    struct PopupSnapshot snapshot;
    if(popup_snapshot(node,&snapshot)) {
      int valid=popup_same_model(form,&snapshot),index=valid?form->popup_indices[selection]:-1;
      popup_snapshot_free(&snapshot);
      /* Selection validation, trusted input/change events and the application
       * model update are Chromium's real implementation. Stale models cannot
       * select a replacement DOM option. */
      if(valid){
        ((void (*)(void *,int))(base+0xe1030e4))(node,index);
        if(log_fd>=0){struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);
          dprintf(log_fd,"%d native popup action applied process=%u control=%llu actions=%.0f time_ns=%llu\n",
            getpid(),identity(),(unsigned long long)control,action_count,
            (unsigned long long)now.tv_sec*1000000000ull+now.tv_nsec);}
      }
      else note("native popup stale model action discarded");
    }
  }
  form=find_form(node);if(form&&form->control==control)invalidate_form(form);
  refresh_form_watch();
}
static int paint_popup(void *self,const void *element,const void *document,const void *style,const void *info,const struct Rect *rect)
{
  if(popup_element((void *)element)&&!paint_form(NXS_POPUP,self,element,document,style,info,rect))return 0;
  return original_popup_paint(self,element,document,style,info,rect);
}
static void select_default(void *node,void *event)
{if(!default_form_key(node,event))original_select_default(node,event);}
static void internal_popup_show(void *self,int type)
{
  void *node=decode_member((char *)self+20);
  struct NativeForm *form=find_form(node);
  if(!form||form->kind!=NXS_POPUP||!form->painted){original_internal_popup_show(self,type);return;}
  form->popup_engine=self;form->popup_open=1;
  struct NXSResponse *response=sync_form_focus(form,form_request(form,1,0,0,0));
  if(response&&response->parts[6].width<=0) {
    if(popup_mouse_event) {
      form->actions_seen=response->parts[0].width;
      struct FloatPoint point=form_point(form,popup_mouse_event);
      response=form_request(form,2,point.x,point.y,event_modifiers(popup_mouse_event));
      if(response&&response->parts[0].y){active_form=form;form->actions_before=form->actions_seen;}
    } else response=popup_visibility_request(form,1);
  }
  if(!response){form->popup_open=0;original_internal_popup_hide(self);popup_engine_closed(self);}
  refresh_form_watch();
}
static void internal_popup_hide(void *self)
{
  void *node=decode_member((char *)self+20);
  struct NativeForm *form=find_form(node);
  int owned=form&&form->kind==NXS_POPUP&&form->popup_engine==self;
  if(owned){
    form->popup_open=0;
    if(active_form==form)finish_form(-10000,-10000,0);
    else popup_visibility_request(form,0);
  }
  original_internal_popup_hide(self);
  if(owned)popup_engine_closed(self);
  refresh_form_watch();
}
static struct Detour popup_detours[]={
 {NXS_POPUP_PAINT_OFFSET,nxs_popup_paint_bytes,paint_popup,(void **)&original_popup_paint},
 {NXS_SELECT_DEFAULT_OFFSET,nxs_select_default_bytes,select_default,(void **)&original_select_default},
 {NXS_INTERNAL_POPUP_SHOW_OFFSET,nxs_internal_popup_show_bytes,internal_popup_show,(void **)&original_internal_popup_show},
 {NXS_INTERNAL_POPUP_HIDE_OFFSET,nxs_internal_popup_hide_bytes,internal_popup_hide,(void **)&original_internal_popup_hide}
};
