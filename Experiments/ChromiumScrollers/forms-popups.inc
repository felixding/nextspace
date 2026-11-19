/* Select application data/lifecycle bindings. NSPopUpButton/NSMenu stay native. */
#include "pinned-popups.h"
static int guard_popup_model_calls(void) {
  return !memcmp((void *)(base+NXS_POPUP_DISPLAY_NONE_OFFSET),nxs_popup_display_none_bytes,20)&&
    !memcmp((void *)(base+NXS_POPUP_PARENT_OFFSET),nxs_popup_parent_bytes,20)&&
    !memcmp((void *)(base+NXS_POPUP_LATIN1_OFFSET),nxs_popup_latin1_bytes,20)&&
    !memcmp((void *)(base+NXS_POPUP_INVALIDATE_SIZE_OFFSET),nxs_popup_invalidate_size_bytes,20);
}
struct PopupSnapshot {
  struct NXSControlPopupRequest *request;
  int *indices;
  void **nodes,*selected_node;
  int selected_list;
  char *title;
};
static int (*original_popup_paint)(void *,const void *,const void *,const void *,const void *,const struct Rect *);
static int (*original_popup_decoration)(void *,const void *,const void *,const void *,const void *,const struct Rect *);
static void (*original_select_default)(void *,void *);
static void (*original_internal_popup_show)(void *,int);
static void (*original_internal_popup_hide)(void *);
static int (*original_popup_inline_size)(const void *,const void *);
static void *(*original_popup_ua_sheet)(const void *);
static void (*original_popup_option_changed)(void *,const void *);
static void (*original_popup_option_attribute)(void *,const void *);
static void (*original_popup_group_attribute)(void *,const void *);
static void *popup_ua_sheet(const void *sheet) {
  const void *string=*(void *const *)sheet;
  unsigned length=string?*(const unsigned *)((const char *)string+4):0;
  if(!string||!(*(const unsigned *)((const char *)string+8)&1)||length>2097152)return original_popup_ua_sheet(sheet);
  char *text=malloc((size_t)length+1);if(!text)return original_popup_ua_sheet(sheet);
  memcpy(text,(const char *)string+12,length);text[length]=0;
  const char *correction=forms_lists_enabled?"\nselect:not(:-internal-list-box):not([multiple]):disabled{opacity:1}select:disabled{opacity:1}select:-internal-list-box{border-radius:0}":"\nselect:not(:-internal-list-box):not([multiple]):disabled{opacity:1}";
  if(!strstr(text,"select:disabled")||!strstr(text,"-internal-auto-base(")||strstr(text,correction)){free(text);return original_popup_ua_sheet(sheet);}
  /* Native NSCell already owns the disabled appearance. Override the original
   * UA fades, including their feature-dependent rules, at the same UA origin.
   * An enabled list binding extends this to listboxes. Author/user opacity
   * stays at its original higher cascade origin. */
  size_t extra=strlen(correction);
  char *changed=malloc((size_t)length+extra);if(!changed){free(text);return original_popup_ua_sheet(sheet);}
  memcpy(changed,text,length);memcpy(changed+length,correction,extra);
  void *value=((void *(*)(const void *,size_t))(base+NXS_POPUP_LATIN1_OFFSET))(changed,length+extra);
  void *result=original_popup_ua_sheet(&value);((void (*)(void *))(base+0x7246038))(&value);
  free(changed);free(text);note("native popup disabled appearance delegated to native cell");return result;
}
static int form_screen_rectangle(struct NativeForm *form,struct Rect *rectangle)
{
  void *document=node_document(form->node);
  void *window=document?decode_member((char *)document+264):NULL;
  void *frame=window?decode_member((char *)window+32):NULL;
  void *page=frame?decode_member((char *)frame+32):NULL;
  void *chrome=page?decode_member((char *)page+76):NULL;
  void *view=document?((void *(*)(const void *))(base+NXS_DATE_PANEL_DOCUMENT_VIEW))(document):NULL;
  if(!chrome||!view)return 0;
  /* Use the engine's clipped local-root bounds and its actual viewport/window
   * conversion. NativeUI supplies menu placement relative to that anchor. */
  struct Rect local=((struct Rect (*)(const void *))(base+NXS_DATE_PANEL_LOCAL_BOUNDS))(form->node);
  struct Rect screen=((struct Rect (*)(void *,const struct Rect *,const void *))
    (*(uintptr_t **)chrome)[15])(chrome,&local,view);
  *rectangle=screen;return 1;
}
static int form_sync_screen_origin(struct NativeForm *form)
{
  struct Rect screen;if(!form_screen_rectangle(form,&screen))return 0;
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(form->screen_anchor_valid&&form->screen_anchor_epoch==epoch&&
     !memcmp(&form->screen_anchor,&screen,sizeof(screen)))return 1;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=13,
    .process=identity(),.kind=form->kind,.control=form->control,.x=screen.x,.y=screen.y};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  if(!response||response->parts[3].x!=1)return 0;
  form->screen_anchor=screen;form->screen_anchor_epoch=epoch;form->screen_anchor_valid=1;return 1;
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
  return native_popup_visibility(NXS_POPUP,form->control,open);
}
static int popup_element(void *node)
{
  return *(uintptr_t *)node==base+0x11ced808+16&&
    *((unsigned char *)node+608)&&!*((unsigned char *)node+609);
}
static void popup_free_model(struct NativeForm *form)
{
  free(form->popup_model);free(form->popup_indices);free(form->popup_nodes);free(form->popup_title);
  form->popup_model=NULL;form->popup_indices=NULL;form->popup_nodes=NULL;form->popup_title=NULL;form->popup_selected_node=NULL;
  form->popup_size=0;form->popup_count=0;
}
static void popup_snapshot_free(struct PopupSnapshot *snapshot)
{free(snapshot->request);free(snapshot->indices);free(snapshot->nodes);free(snapshot->title);memset(snapshot,0,sizeof(*snapshot));}
static int popup_item_visible(void *item,void *select) {
  /* This guarded display accessor uses only Element's common style storage
   * and original EnsureComputedStyle. It has no HTMLOptionElement fields.
   * Reuse it for the engine's list elements and their original DOM ancestry. */
  for(unsigned depth=0;item&&item!=select&&depth<4096;depth++) {
    if(((int (*)(void *,int))(base+NXS_POPUP_DISPLAY_NONE_OFFSET))(item,1))return 0;
    item=((void *(*)(void *))(base+NXS_POPUP_PARENT_OFFSET))(item);
  }
  return item==select;
}
static char *popup_item_label(void *select,void *item) {
  void *label=((void *(*)(const void *,const void *))(base+0xe102cd0))(select,item);
  char *title=string_text(label);((void (*)(void *))(base+0x7246038))(&label);return title;
}
static int popup_snapshot(void *node,struct PopupSnapshot *snapshot)
{
  memset(snapshot,0,sizeof(*snapshot));
  /* The real SelectedListIndex calls GetListItems and recalculates it when
   * dirty. Only its pinned vector representation is decoded below. */
  int selected=((int (*)(const void *))(base+0xe0ff7b8))(node);
  snapshot->selected_list=selected;
  unsigned count=*(unsigned *)((char *)node+588);
  void *items=*(void **)((char *)node+576);
  if(count>65536||(!items&&count))return 0;
  snapshot->request=native_popup_model_new(-1);
  snapshot->indices=calloc(count?count:1,sizeof(int));snapshot->nodes=calloc(count?count:1,sizeof(void *));
  if(!snapshot->request||!snapshot->indices||!snapshot->nodes){popup_snapshot_free(snapshot);return 0;}
  struct NXSControlPopupRequest *request=snapshot->request;
  for(unsigned i=0;i<count;i++) {
    void *item=decode_member((char *)items+i*4);if(!item)continue;
    unsigned kind=*((unsigned char *)*(uintptr_t *)item-17);
    if((int)i==selected)snapshot->selected_node=item;
    if(!popup_item_visible(item,node))continue;
    char *title=popup_item_label(node,item);
    if(!title){popup_snapshot_free(snapshot);return 0;}
    unsigned row=request->count;
    if(!native_popup_model_append(request,title,kind==0x38&&form_enabled(item),kind!=0x38&&kind!=0x37)){
      free(title);popup_snapshot_free(snapshot);return 0;
    }
    free(title);snapshot->indices[row]=i;snapshot->nodes[row]=item;
    if((int)i==selected)request->selected=row;
  }
  if(request->selected<0&&snapshot->selected_node) {
    snapshot->title=popup_item_label(node,snapshot->selected_node);
    if(!snapshot->title){popup_snapshot_free(snapshot);return 0;}
  }
  return 1;
}
static int popup_same_model(struct NativeForm *form,struct PopupSnapshot *snapshot)
{
  struct NXSControlPopupRequest *request=snapshot->request;
  return form->popup_model&&form->popup_size==request->text_size&&form->popup_count==request->count&&
    form->popup_selected==request->selected&&form->popup_selected_list==snapshot->selected_list&&form->popup_selected_node==snapshot->selected_node&&
    (form->popup_title&&snapshot->title?!strcmp(form->popup_title,snapshot->title):form->popup_title==snapshot->title)&&
    !memcmp(form->popup_indices,snapshot->indices,request->count*sizeof(int))&&!memcmp(form->popup_model,request+1,request->text_size)&&
    !memcmp(form->popup_nodes,snapshot->nodes,request->count*sizeof(void *));
}
static struct NXSResponse *sync_popup_model(struct NativeForm *form,struct NXSResponse *response)
{
  uint32_t epoch=atomic_load(&native_host_epoch);
  if(form->popup_epoch!=epoch)form->actions_seen=response->parts[0].width;
  struct PopupSnapshot snapshot;if(!popup_snapshot(form->node,&snapshot))return NULL;
  struct NXSControlPopupRequest *request=snapshot.request;
  if(snapshot.title&&response->parts[1].x!=1){popup_snapshot_free(&snapshot);return NULL;}
  if((form->popup_epoch==epoch&&popup_same_model(form,&snapshot))||response->parts[6].width>0){popup_snapshot_free(&snapshot);return response;}
  request->process=identity();request->control=form->control;
  response=exchange_bytes(request,sizeof(*request)+request->text_size);
  if(response&&response->parts[3].x==1&&response->parts[1].x==1)response=native_popup_title(form->control,snapshot.title);
  if(response&&response->parts[3].x==1) {
    popup_free_model(form);
    form->popup_model=malloc(request->text_size?request->text_size:1);
    if(!form->popup_model){popup_snapshot_free(&snapshot);return NULL;}
    memcpy(form->popup_model,request+1,request->text_size);form->popup_size=request->text_size;
    form->popup_count=request->count;form->popup_selected=request->selected;form->popup_selected_list=snapshot.selected_list;
    form->popup_selected_node=snapshot.selected_node;form->popup_title=snapshot.title;snapshot.title=NULL;
    form->popup_indices=snapshot.indices;form->popup_nodes=snapshot.nodes;
    form->popup_epoch=epoch;
    snapshot.indices=NULL;snapshot.nodes=NULL;
  } else response=NULL;
  popup_snapshot_free(&snapshot);return response;
}
static int popup_preferred(void *node,const void *layout,struct SizeI *size) {
  if(!popup_element(node)||!native_layout_supported_scale(node,layout))return 0;
  /* Hierarchy carriers fill an existing application viewport. Their model
   * metadata is not an intrinsic text width, and an unlaid-out 1px rectangle
   * must not resize the native scroll view during measurement. */
  if(component_native_kind(node)==NXS_OUTLINE||component_native_kind(node)==NXS_WEBUI_MENU)return 0;
  int kind=component_native_kind(node)?component_native_kind(node):NXS_POPUP;
  struct NativeForm *form=find_form(node);
  if(!form) {
    form=calloc(1,sizeof(*form));if(!form)return 0;
    form->node=node;form->kind=kind;form->control=++next_form_control;
    form->title=strdup("");form->rect=(struct Rect){0,0,1,1};
    form->next=native_forms;native_forms=form;
  }
  form->enabled=form_enabled(node);form->state=form_state(node,kind);
  /* Before first layout, host only the application model. Native NSCell size
   * owns all title/arrow/border metrics; no geometry query may flush layout. */
  popup_measuring++;struct NXSResponse *response=form_request(form,1,0,0,0);popup_measuring--;
  if(!response)return 0;
  double width=response->parts[1].width,height=response->parts[1].height;
  if(!isfinite(width)||!isfinite(height)||width<1||height<1||width>8192||height>8192)return 0;
  *size=(struct SizeI){ceil(width),ceil(height)};return 1;
}
static int popup_inline_size(const void *node,const void *layout) {
  if(original_form_block_size(layout,0)<0)return original_popup_inline_size(node,layout);
  struct SizeI preferred;
  return popup_preferred((void *)node,layout,&preferred)?native_content_size(layout,preferred.width,0):original_popup_inline_size(node,layout);
}
static struct NativeForm *popup_owner(void *node) {return bound_form_ancestor(node,NXS_POPUP);}
static void popup_invalidate_size(void *node,uint64_t control) {
  struct NativeForm *form=find_form(node);
  if(!form||form->control!=control||form->kind!=NXS_POPUP||!popup_element(node))return;
  void *type=decode_member((char *)node+168);
  /* Existing option notifications own selection/content changes. Ask Blink's
   * original menu-list method to dirty its intrinsic layout after those
   * notifications, including unselected labels and group/visibility data. */
  if(type)((void (*)(const void *))(base+NXS_POPUP_INVALIDATE_SIZE_OFFSET))(type);
}
static void popup_option_changed(void *node,const void *option) {
  struct NativeForm *form=find_form(node);uint64_t control=form?form->control:0;
  original_popup_option_changed(node,option);
  if(control){popup_invalidate_size(node,control);list_model_changed(node,control);}
}
static void popup_option_attribute(void *option,const void *params) {
  struct NativeForm *form=popup_owner(option);if(!form)form=bound_form_ancestor(option,NXS_LISTBOX);
  void *node=form?form->node:NULL;uint64_t control=form?form->control:0;
  original_popup_option_attribute(option,params);
  if(control){popup_invalidate_size(node,control);list_model_changed(node,control);}
}
static void popup_group_attribute(void *group,const void *params) {
  struct NativeForm *form=popup_owner(group);if(!form)form=bound_form_ancestor(group,NXS_LISTBOX);
  void *node=form?form->node:NULL;uint64_t control=form?form->control:0;
  original_popup_group_attribute(group,params);
  if(control){popup_invalidate_size(node,control);list_model_changed(node,control);}
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
  if(component_native_kind((void *)element)==NXS_WEBUI_MENU)return 0;
  if(popup_element((void *)element)&&!paint_form(component_native_kind((void *)element)?component_native_kind((void *)element):NXS_POPUP,self,element,document,style,info,rect))return 0;
  return original_popup_paint(self,element,document,style,info,rect);
}
static void select_default(void *node,void *event)
{
  int component=component_native_kind(node);
  if(component&&component!=NXS_POPUP) {
    /* Suppress the select's popup default, without marking pointerdown as
     * handled: Blink must still construct its compatibility mouse events. */
    if(!native_wheel_default(node,event))default_form_key(node,event);
    return;
  }
  if(!list_default_event(node,event)&&!default_form_key(node,event))original_select_default(node,event);
}
static int paint_popup_decoration(void *self,const void *element,const void *document,const void *style,const void *info,const struct Rect *rect)
{
  /* Blink sends selects with authored backgrounds through decorations instead
   * of PaintMenuList. Explicit shared-component ownership enters the same
   * native popup renderer; ordinary authored website controls keep Blink's path. */
  if(component_native_kind((void *)element)==NXS_POPUP&&
     !paint_form(NXS_POPUP,self,element,document,style,info,rect))return 0;
  return original_popup_decoration(self,element,document,style,info,rect);
}
static void internal_popup_show(void *self,int type)
{
  void *node=decode_member((char *)self+20);
  /* showPicker can precede paint (including a transparent WebUI menu anchor).
   * Bind its existing layout/model at the event boundary, just as keyboard
   * focus already binds ordinary controls before their first paint. */
  struct NativeForm *form=node?find_form(node):NULL;if(node&&!form)form=bind_input_form(node);
  if(form&&form->kind==NXS_WEBUI_MENU) {
    if(!component_menu_open(form,self)){form->popup_open=0;popup_engine_closed(self);}
    return;
  }
  if(!form||form->kind!=NXS_POPUP){original_internal_popup_show(self,type);return;}
  form->popup_engine=self;form->popup_open=1;
  if(!forms_available&&!native_form_events_ready()) {
    form->popup_open=0;form->popup_engine=NULL;refresh_form_watch();
    original_internal_popup_show(self,type);return;
  }
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
  int owned=form&&(form->kind==NXS_POPUP||form->kind==NXS_WEBUI_MENU)&&form->popup_engine==self;
  if(owned&&form->kind==NXS_WEBUI_MENU) {
    form->popup_open=0;component_menu_request(form,6);original_internal_popup_hide(self);popup_engine_closed(self);refresh_form_watch();return;
  }
  if(owned){
    form->popup_open=0;
    if(active_form==form)finish_form(-10000,-10000,0);
    else popup_visibility_request(form,0);
  }
  original_internal_popup_hide(self);
  if(owned)popup_engine_closed(self);
  refresh_form_watch();
}
static void dismiss_popup_before_scroll(void)
{
  if(!forms_popups_enabled||forms_available)return;
  for(struct NativeForm *form=native_forms;form;form=form->next)
    if(form->kind==NXS_POPUP&&form->popup_open&&form->popup_engine) {
      /* The native scrollbar consumes this press before it reaches Blink's
       * popup dismissal path. Close through the existing menu lifecycle. */
      internal_popup_hide(form->popup_engine);
      return;
    }
}
static struct Detour popup_detours[]={
 {NXS_POPUP_UA_SHEET_OFFSET,nxs_popup_ua_sheet_bytes,popup_ua_sheet,(void **)&original_popup_ua_sheet},
 {NXS_POPUP_OPTION_CHANGED_OFFSET,nxs_popup_option_changed_bytes,popup_option_changed,(void **)&original_popup_option_changed},
 {NXS_POPUP_OPTION_ATTRIBUTE_OFFSET,nxs_popup_option_attribute_bytes,popup_option_attribute,(void **)&original_popup_option_attribute},
 {NXS_POPUP_GROUP_ATTRIBUTE_OFFSET,nxs_popup_group_attribute_bytes,popup_group_attribute,(void **)&original_popup_group_attribute},
 {NXS_POPUP_INLINE_SIZE_OFFSET,nxs_popup_inline_size_bytes,popup_inline_size,(void **)&original_popup_inline_size},
 {NXS_POPUP_PAINT_OFFSET,nxs_popup_paint_bytes,paint_popup,(void **)&original_popup_paint},
 {NXS_POPUP_DECORATION_OFFSET,nxs_popup_decoration_bytes,paint_popup_decoration,(void **)&original_popup_decoration}
};
static struct Detour popup_lifecycle_detours[]={
 {NXS_INTERNAL_POPUP_SHOW_OFFSET,nxs_internal_popup_show_bytes,internal_popup_show,(void **)&original_internal_popup_show},
 {NXS_INTERNAL_POPUP_HIDE_OFFSET,nxs_internal_popup_hide_bytes,internal_popup_hide,(void **)&original_internal_popup_hide},
 {NXS_SELECT_DEFAULT_OFFSET,nxs_select_default_bytes,select_default,(void **)&original_select_default}
};
