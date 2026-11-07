/* Blink list data and DOM transactions. Shared ListBinding/NativeUI own the
 * actual NSBrowser, cells, matrix, focus, selection, scrolling and tracking. */
#include "pinned-lists.h"
#include "pinned-list-hits.h"
struct ListSnapshot {NXSListItem *items;unsigned count,flags;};
static int list_element(void *node)
{return forms_lists_enabled&&node&&*(uintptr_t *)node==base+0x11ced808+16&&!*((unsigned char *)node+608);}
static int list_style(void *node)
{
  void *layout=node?decode_member((char *)node+48):NULL;
  if(!native_layout_unit_scale(node,layout))return 0;
  const void *style=decode_member((char *)layout+32),*data=style?decode_member((char *)style+4):NULL;
  /* EffectiveAppearance is the same guarded application style field read by
   * the original shared text-field painter. kListbox is 5 in this build. */
  return data&&((*(const uint64_t *)((char *)data+56)>>15)&31)==5;
}
static int list_owned(const struct NativeForm *form)
{return form&&form->kind==NXS_LISTBOX&&form->painted&&list_element(form->node)&&list_style(form->node);}
static void list_snapshot_free(struct ListSnapshot *snapshot)
{native_list_binding_free_items(snapshot->items,snapshot->count);memset(snapshot,0,sizeof(*snapshot));}
static int list_snapshot(void *node,struct ListSnapshot *snapshot)
{
  memset(snapshot,0,sizeof(*snapshot));if(!list_element(node))return 0;
  /* The original accessor recalculates GetListItems when dirty. Keep Blink's
   * vector/DOM ordering, labels, visibility and stable engine identities. */
  ((int (*)(const void *))(base+0xe0ff7b8))(node);
  unsigned count=*(unsigned *)((char *)node+588);void *items=*(void **)((char *)node+576);
  if(count>4096||(!items&&count))return 0;
  snapshot->items=calloc(count?count:1,sizeof(*snapshot->items));if(!snapshot->items)return 0;
  snapshot->flags=*((unsigned char *)node+609)?NXS_LIST_MULTIPLE:0;
  for(unsigned i=0;i<count;i++) {
    void *item=decode_member((char *)items+i*4);if(!item||!popup_item_visible(item,node))continue;
    unsigned kind=*((unsigned char *)*(uintptr_t *)item-17);
    char *title=popup_item_label(node,item);uint32_t identifier=radio_node_id(item);
    if(!title||!identifier){free(title);list_snapshot_free(snapshot);return 0;}
    snapshot->items[snapshot->count++]=(NXSListItem){.size=sizeof(NXSListItem),.identifier=identifier,.title=title,
      .enabled=kind==0x38&&form_enabled(item),.selected=kind==0x38&&*((unsigned char *)item+112)};
  }
  return 1;
}
static void list_forget(struct NativeForm *form)
{native_list_binding_destroy(&form->list);form->painted=0;form->list_layout_retry=0;}
static void list_model_changed(void *node,uint64_t control)
{struct NativeForm *form=find_form(node);if(form&&form->control==control&&form->kind==NXS_LISTBOX)invalidate_form(form);}
static void (*original_list_selected_state)(void *,int,int);
static void list_selected_state(void *option,int selected,int skip_popup_update)
{
  struct NativeForm *form=bound_form_ancestor(option,NXS_LISTBOX);
  uint32_t origin=form?radio_node_id(form->node):0;
  uint64_t control=form?form->control:0;
  int changed=form&&*((unsigned char *)option+112)!=(selected&1);
  original_list_selected_state(option,selected,skip_popup_update);
  /* Script setters and reset invalidate original option items. Their pixels
   * belong to the complete native owner now, so invalidate that owner too. */
  if(changed){void *node=radio_node_for_id(origin);if(node)list_model_changed(node,control);}
}
static int list_sync(struct NativeForm *form)
{
  if(!list_element(form->node)||!list_style(form->node)){list_forget(form);return 0;}
  struct ListSnapshot snapshot;if(!list_snapshot(form->node,&snapshot))return 0;
  int existing=form->list.created&&form->list.epoch==atomic_load(&native_host_epoch);
  form->list.control=form->control;
  int okay=native_list_binding_sync(&form->list,snapshot.items,snapshot.count,snapshot.flags,
    form->rect.width,form->rect.height,form_enabled(form->node),form_focused(form->node));
  list_snapshot_free(&snapshot);
  if(okay&&!existing&&form->text_area) {
    /* New native objects replay the retained application scroll model once.
     * Native input owns subsequent movement and the provider clamps it. */
    struct FloatPoint position=((struct FloatPoint (*)(const void *))(base+NXS_MULTILINE_GET_OFFSET_OFFSET))(form->text_area);
    okay=native_list_binding_scroll(&form->list,position.x,position.y);
  }
  okay=okay&&form->list.pixel_width==form->rect.width&&form->list.pixel_height==form->rect.height;
  if(okay&&form->list_layout_retry) {
    /* A temporary engine fallback may have installed its own scrollbars.
     * Reuse the deferred original layout invalidation when native data returns. */
    form->list_layout_retry=0;native_layout_changed(form);
  }
  return okay;
}
static int list_scrollbar_owner(const void *area)
{
  void *layout=area?((void *(*)(const void *))(base+NXS_MULTILINE_GET_BOX_OFFSET))(area):NULL;
  void *node=layout?((void *(*)(const void *))(base+NXS_MULTILINE_NODE_OFFSET))(layout):NULL;
  if(!list_element(node)||!list_style(node))return 0;
  struct NativeForm *form=find_form(node);
  if(!form){form=calloc(1,sizeof(*form));if(!form)return 0;form->node=node;form->kind=NXS_LISTBOX;form->control=++next_form_control;form->next=native_forms;native_forms=form;}
  struct SizeI size=((struct SizeI (*)(const void *))(base+NXS_MULTILINE_AREA_SIZE_OFFSET))(area);
  form->text_area=(void *)area;
  form->rect.width=lround(size.width/64.);form->rect.height=lround(size.height/64.);
  int okay=form->rect.width>0&&form->rect.height>0&&list_sync(form);
  if(!okay)form->list_layout_retry=1;
  if(okay)native_wheel_binding(form,1);return okay;
}
static struct NXSResponse *list_form_request(struct NativeForm *form,unsigned operation,double x,double y,unsigned modifiers)
{
  if(operation==6){list_forget(form);return NULL;}
  if(operation==1) {
    if(!list_sync(form))return NULL;
    return native_list_request(form->control,5,0,0,1);
  }
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=NXS_LISTBOX,.control=form->control,.x=x,.y=y,.modifiers=modifiers};
  return operation==2&&form->radio_clicks>1?native_pointer_press(NXS_LISTBOX,form->control,x,y,modifiers,form->radio_clicks):exchange_bytes(&request,sizeof(request));
}
static void list_after_input(uint32_t origin,uint64_t control,uint64_t actions)
{
  void *node=radio_node_for_id(origin);struct NativeForm *form=node?find_form(node):NULL;
  if(!form||form->control!=control||form->kind!=NXS_LISTBOX||!native_list_binding_refresh(&form->list))return;
  if(form->list.state.actions!=actions) {
    struct ListSnapshot snapshot;
    if(list_snapshot(node,&snapshot)) {
      int valid=native_list_binding_same(&form->list,snapshot.items,snapshot.count,snapshot.flags)&&form_enabled(node);
      void *type=valid?decode_member((char *)node+168):NULL;int changed=0;
      if(type)((void (*)(void *))(base+NXS_CHROMIUM_LIST_SAVE))(type);
      for(unsigned i=0;type&&i<snapshot.count;i++) {
        void *option=radio_node_for_id(snapshot.items[i].identifier);
        if(!option||*((unsigned char *)*(uintptr_t *)option-17)!=0x38)continue;
        int selected=0;for(unsigned j=0;j<form->list.state.selected_count;j++)
          if(form->list.selection[j]==snapshot.items[i].identifier)selected=1;
        if(selected==snapshot.items[i].selected)continue;
        /* The original binding setter owns dirty state, selectedcontent,
         * validity, accessibility and canonical single-selection behavior. */
        ((void (*)(void *,int))(base+NXS_CHROMIUM_LIST_SET_SELECTED))(option,selected);changed=1;
        node=radio_node_for_id(origin);form=node?find_form(node):NULL;
        if(!form||form->control!=control||!list_element(node)){type=NULL;break;}
        form->list.items[i].selected=selected;
      }
      list_snapshot_free(&snapshot);
      if(type&&changed)((void (*)(void *))(base+NXS_CHROMIUM_LIST_CHANGE))(type);
      else if(!valid)note("native Blink list stale model action discarded");
    }
  }
  node=radio_node_for_id(origin);form=node?find_form(node):NULL;
  if(form&&form->control==control){list_sync(form);echo_text_viewport(form);invalidate_form(form);}
}
static int list_key_input(struct NativeForm *form,void *event,int type,unsigned key,const char *text,const char *unmodified,unsigned modifiers,int repeat)
{
  unsigned short *flags=(unsigned short *)((char *)event+32);
  if(!list_sync(form)){*flags|=0x40;return 1;}
  uint32_t origin=radio_node_id(form->node);uint64_t control=form->control,actions=form->list.state.actions;
  NXSKeyEvent input={.size=sizeof(input),.type=type,.key=key,.text=text,.unmodified_text=unmodified,.modifiers=modifiers,.repeat=repeat};
  struct NXSResponse *response=native_list_input(control,0,&input);
  if(!response){*flags|=0x40;return 1;}int result=response->parts[3].x;
  if(result==NXS_INPUT_NEXT||result==NXS_INPUT_PREVIOUS)advance_form_focus(form->node,event,result);
  if(result!=NXS_INPUT_UNHANDLED||type==NXS_KEY_UP)*flags|=0x40;
  list_after_input(origin,control,actions);return 1;
}
static int list_default_event(void *node,void *event)
{
  if(native_wheel_default(node,event))return 1;
  struct NativeForm *form=find_form(node);if(!list_owned(form))return 0;
  unsigned short *flags=(unsigned short *)((char *)event+32);
  if(!(*flags&0x100)||(*flags&0x60))return 0;
  uintptr_t atom=*(uintptr_t *)((char *)event+24);
  int down=same_atom(atom,0x123a55f8),move=same_atom(atom,0x123a5600),up=same_atom(atom,0x123a5608);
  if(!down&&!move&&!up)return 0;
  if(down&&form_enabled(node))((void (*)(void *))(base+NXS_CHROMIUM_LIST_FOCUS))(node);
  *flags|=0x40;return 1;
}
static int list_mouse_dispatch(void *manager,void *target,const void *type,const void *event,const void *last,void *related,int check,
    const void *pointer_id,const void *pointer_type,void *down,void *up,struct MouseDispatchResult *result)
{
  uintptr_t atom=*(uintptr_t *)type;int press=same_atom(atom,0x123a55f8)&&*(const int *)((char *)event+120)==0;
  struct NativeForm *form=active_form&&active_form->kind==NXS_LISTBOX?active_form:NULL;
  if(press){void *node=target?((void *(*)(void *))(*(uintptr_t **)target)[9])(target):NULL;form=bound_form_ancestor(node,NXS_LISTBOX);}
  int move=same_atom(atom,0x123a5600),release=same_atom(atom,0x123a5608)&&*(const int *)((char *)event+120)==0;
  if(!form||(!press&&!move&&!release))return 0;
  uint32_t origin=radio_node_id(form->node);uint64_t control=form->control,actions=form->list.state.actions;
  struct FloatPoint point=form_point(form,event);unsigned modifiers=event_modifiers(event);
  if(release)finish_form(point.x,point.y,modifiers);
  *result=original_mouse_dispatch(manager,target,type,event,last,related,check,pointer_id,pointer_type,down,up);
  void *node=radio_node_for_id(origin);form=node?find_form(node):NULL;
  if(!form||form->control!=control||!list_owned(form))return 1;
  unsigned flags=result->event?*(unsigned short *)((char *)result->event+32):0;
  if(press&&(flags&0x100)&&!(flags&0x20)&&list_sync(form)) {
    if(active_form)finish_form(-10000,-10000,0);
    node=radio_node_for_id(origin);form=node?find_form(node):NULL;if(!form||form->control!=control)return 1;
    form->radio_clicks=*(unsigned *)((char *)event+160);
    struct NXSResponse *response=list_form_request(form,2,point.x,point.y,modifiers);
    if(response&&response->parts[0].y){active_form=form;form->list.tracking=1;refresh_form_watch();}
    list_after_input(origin,control,actions);
  } else if(move&&active_form==form) {
    list_form_request(form,3,point.x,point.y,modifiers);list_after_input(origin,control,actions);
  }
  return 1;
}

/* Geometry data from the actual native row. Both the original selection
 * reveal task and public client-rectangle queries use that same measurement. */
static int list_option_geometry(void *node,struct NXSRectD *rect,struct NativeForm **owner)
{
  *owner=NULL;if(!node||*((unsigned char *)*(uintptr_t *)node-17)!=0x38)return 0;
  struct NativeForm *form=bound_form_ancestor(node,NXS_LISTBOX);if(!list_owned(form))return 0;
  uint32_t option=radio_node_id(node),origin=radio_node_id(form->node);uint64_t control=form->control;
  if(!native_list_item_rect(control,option,rect))return -1;
  /* Metadata RPC can service an application callback. Reacquire both semantic
   * identities before reading their layout, as the input transaction does. */
  void *root=radio_node_for_id(origin),*current=radio_node_for_id(option);form=root?find_form(root):NULL;
  if(current!=node||!form||form->control!=control||!list_owned(form)||bound_form_ancestor(current,NXS_LISTBOX)!=form)return -1;
  *owner=form;return 1;
}
static struct Rect (*original_list_option_bounds)(const void *);
static struct FloatRect (*original_list_client_bounds)(const void *);
static struct Rect list_option_bounds(const void *layout)
{
  void *node=((void *(*)(const void *))(base+NXS_MULTILINE_NODE_OFFSET))(layout);
  struct NXSRectD row;struct NativeForm *form;int owned=list_option_geometry(node,&row,&form);
  if(owned<0||(owned&&decode_member((char *)node+48)!=layout))return (struct Rect){0};
  void *root=form?decode_member((char *)form->node+48):NULL;
  if(root) {
    struct Rect bounds=original_list_option_bounds(root);
    return (struct Rect){bounds.x+lround(row.x*64),bounds.y+lround(row.y*64),lround(row.width*64),lround(row.height*64)};
  }
  return original_list_option_bounds(layout);
}
static struct FloatRect list_client_bounds(const void *node)
{
  struct NXSRectD row;struct NativeForm *form;int owned=list_option_geometry((void *)node,&row,&form);
  if(owned<0)return (struct FloatRect){0};
  if(form) {
    struct FloatRect root=original_list_client_bounds(form->node);
    return (struct FloatRect){root.x+row.x,root.y+row.y,row.width,row.height};
  }
  return original_list_client_bounds(node);
}

/* Keep the engine's original hit traversal, cache and trusted dispatch. Only
 * the owned control's semantic item and local coordinate come from NativeUI. */
static int (*original_list_hit_test)(const void *,const void *,void *);
static __thread int list_hit_query;
static int list_hit_test(const void *view,const void *location,void *hit)
{
  int found=original_list_hit_test(view,location,hit);
  /* List/rectangle queries have a separate multi-node result contract. */
  if(!found||list_hit_query||(*(const unsigned *)hit&(1u<<11))||*((const unsigned char *)location+68))return found;
  void *initial=decode_member((char *)hit+36);
  struct NativeForm *form=bound_form_ancestor(initial,NXS_LISTBOX);if(!list_owned(form))return found;
  uint32_t origin=radio_node_id(form->node);uint64_t control=form->control;
  struct Point point=*(const struct Point *)((char *)hit+48);
  list_hit_query=1;
  int okay=list_sync(form);void *root=radio_node_for_id(origin);form=root?find_form(root):NULL;
  if(!root||!form||form->control!=control||!list_owned(form))goto retired;
  if(okay) {
    struct FloatRect box=original_list_client_bounds(root);
    double x=point.x/64.-box.x,y=point.y/64.-box.y;uint64_t identifier=0;
    okay=native_control_item_at_point(NXS_LISTBOX,control,x,y,&identifier);
    root=radio_node_for_id(origin);form=root?find_form(root):NULL;
    if(!root||!form||form->control!=control||!list_owned(form))goto retired;
    void *node=identifier?radio_node_for_id(identifier):root;
    if(okay&&(!node||bound_form_ancestor(node,NXS_LISTBOX)!=form))goto retired;
    if(okay&&node&&bound_form_ancestor(node,NXS_LISTBOX)==form) {
      struct NXSRectD row={0};
      okay=!identifier||native_list_item_rect(control,identifier,&row);
      root=radio_node_for_id(origin);form=root?find_form(root):NULL;node=identifier?radio_node_for_id(identifier):root;
      if(!root||!form||form->control!=control||!list_owned(form))goto retired;
      if(okay&&(!node||bound_form_ancestor(node,NXS_LISTBOX)!=form))goto retired;
      if(okay&&node&&bound_form_ancestor(node,NXS_LISTBOX)==form) {
        struct Point local={lround((x-row.x)*64),lround((y-row.y)*64)};
        /* The original setter owns compressed references, write barriers and
         * element/pseudo normalization. A null fragment uses this local point. */
        ((void (*)(void *,void *,const void *,const struct Point *))(base+NXS_CHROMIUM_LIST_HIT_SET_POSITION))(hit,node,NULL,&local);
      }
    }
  }
  list_hit_query=0;return found;
retired:
  ((void (*)(void *,void *,const void *,const struct Point *))(base+NXS_CHROMIUM_LIST_HIT_SET_POSITION))(hit,NULL,NULL,&(struct Point){0});
  list_hit_query=0;return 0;
}

/* Blink intentionally sends listboxes to CSS at its common theme boundary,
 * before the text-field painter. Keep every other appearance in that original
 * dispatch, including the existing native text adapter's virtual calls. */
static int (*original_list_theme_paint)(void *,const void *,const void *,const struct Rect *);
static int (*original_list_theme_border)(void *,const void *,const void *,const void *,const struct Rect *);
static int list_theme_paint(void *self,const void *layout,const void *info,const struct Rect *rect)
{
  void *node=((void *(*)(const void *))(base+NXS_LAYOUT_NODE_OFFSET))(layout);
  if(list_element(node)&&list_style(node)) {
    if(*((const unsigned char *)info+NXS_MULTILINE_CONTENTS_PAINT_BYTE))return 0;
    void *style=decode_member((char *)layout+32);
    if(!paint_form(NXS_LISTBOX,self,node,NULL,style,info,rect))return 0;
  }
  return original_list_theme_paint(self,layout,info,rect);
}
static int list_theme_border(void *self,const void *node,const void *style,const void *info,const struct Rect *rect)
{
  if(list_owned(find_form(node)))return 0;
  return original_list_theme_border(self,node,style,info,rect);
}
static struct Detour list_detours[]={
  {NXS_CHROMIUM_LIST_HIT_HIT_TEST,chromium_list_hit_hit_test_bytes,list_hit_test,(void **)&original_list_hit_test},
  {NXS_CHROMIUM_LIST_PAINT,chromium_list_paint_bytes,list_theme_paint,(void **)&original_list_theme_paint},
  {NXS_CHROMIUM_LIST_BORDER,chromium_list_border_bytes,list_theme_border,(void **)&original_list_theme_border},
  {NXS_CHROMIUM_LIST_SELECTED_STATE,chromium_list_selected_state_bytes,list_selected_state,(void **)&original_list_selected_state},
  {NXS_CHROMIUM_LIST_OPTION_BOUNDS,chromium_list_option_bounds_bytes,list_option_bounds,(void **)&original_list_option_bounds},
  {NXS_CHROMIUM_LIST_CLIENT_BOUNDS,chromium_list_client_bounds_bytes,list_client_bounds,(void **)&original_list_client_bounds}
};
