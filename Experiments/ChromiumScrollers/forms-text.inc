/* Blink model/transaction bindings. The shared native editor owns the UI. */
#include "pinned-text.h"
struct BlinkTextModel {char *value;uint32_t start,end;int editable;};
struct BlinkEditorCommand {void *command;int source,padding;void *frame;};
_Static_assert(sizeof(struct BlinkEditorCommand)==24,"Pinned menu/key command ABI");
struct BlinkTextTransaction {
  void *node,*frame,*event;
  uint64_t control;
  const char *before;
  const struct NXSNativeTextEdit *edit;
  int attempted;
};
static __thread struct BlinkTextTransaction *text_transaction;
static int native_text_proposal(const struct NXSNativeTextEdit *,const char *,const char *);
static void *text_frame(void *);
static int blink_application_command(const struct NXSNativeCommand *request,const char *selector) {
  static const struct {const char *selector,*name;uintptr_t enabled;} commands[]={
    {"copy:","Copy",NXS_CHROMIUM_TEXT_COPY_ENABLED_OFFSET},
    {"cut:","Cut",NXS_CHROMIUM_TEXT_CUT_ENABLED_OFFSET},
    {"paste:","Paste",NXS_CHROMIUM_TEXT_PASTE_ENABLED_OFFSET}};
  struct BlinkTextTransaction *t=text_transaction;
  if(!t||request->process!=identity()||request->control!=t->control)return 0;
  struct NativeForm *form=find_form(t->node);
  if(!form||form->kind!=(int)request->kind||form->control!=t->control||text_frame(t->node)!=t->frame)return 0;
  for(unsigned n=0;n<sizeof(commands)/sizeof(*commands);n++)if(!strcmp(selector,commands[n].selector)) {
    int enabled=((uint8_t (*)(void *,void *,int))(base+commands[n].enabled))(t->frame,t->event,0);
    if(request->phase==NXS_COMMAND_VALIDATE)return !!enabled;
    t->attempted=1;
    form=find_form(t->node);
    if(!enabled||!form||form->control!=t->control||text_frame(t->node)!=t->frame)return 0;
    void *name=((void *(*)(const char *,size_t))(base+NXS_CHROMIUM_TEXT_FROM_UTF8_OFFSET))(commands[n].name,strlen(commands[n].name));
    struct BlinkEditorCommand action={.command=((void *(*)(const void *))(base+NXS_CHROMIUM_TEXT_COMMAND_OFFSET))(&name),.source=0,.frame=t->frame};
    if(!action.command)action.frame=NULL;
    void *empty=NULL;
    int handled=((int (*)(const void *,const void *,void *))(base+NXS_CHROMIUM_TEXT_EXECUTE_OFFSET))(&action,&empty,t->event);
    ((void (*)(void *))(base+0x7246038))(&name);
    if(log_fd>=0)dprintf(log_fd,"%d native-blink-command control=%llu command=%s result=%d\n",getpid(),(unsigned long long)t->control,commands[n].name,!!handled);
    return !!handled;
  }
  return -1;
}
static int (*original_text_paint)(void *,const void *,const void *,const void *,const struct Rect *);
static void (*original_text_carets)(void *,const void *,const void *,const void *);
static void (*original_text_delete_backward)(void *,unsigned char,int);
static void (*original_text_delete_forward)(void *,void *,unsigned char,int);
static void (*original_text_view_value)(void *,const void *);
static int (*original_text_selection)(void *,unsigned,unsigned,int);
static int (*original_text_mouse_press)(void *,const void *);
static int (*original_text_mouse_release)(void *,const void *,const void *);
static int (*original_text_mouse_drag)(void *,const void *);
static int (*original_text_pointer_up)(void *,const void *);
static void *text_pointer_controller,*text_pointer_frame,*text_pointer_handler;
static int text_kind(int kind){return kind==NXS_TEXTFIELD||kind==NXS_PASSWORD||kind==NXS_TEXTAREA||kind==NXS_SEARCHFIELD;}
static int native_text_input_owned(const struct NativeForm *form) {
  return form&&text_kind(form->kind)&&(form->painted||
    (form->input_owned&&form->kind!=NXS_TEXTAREA&&
     native_layout_appearance(form->node,decode_member((const char *)form->node+48),form->kind==NXS_SEARCHFIELD?11:12)));
}
static void (*original_textarea_default)(void *,void *);
static void textarea_default(void *node,void *event)
{if(!native_wheel_default(node,event)&&(!forms_multiline_enabled||!default_text_key(node,event)))original_textarea_default(node,event);}
static void *text_frame(void *node) {
  void *document=node_document(node),*window=document?decode_member((char *)document+264):NULL;
  return window?decode_member((char *)window+32):NULL;
}
static int text_model(void *node,struct BlinkTextModel *model) {
  int kind=node?input_form_kind(node):0;if(!text_kind(kind))return 0;
  uintptr_t getter=kind==NXS_TEXTAREA?NXS_TEXTAREA_VALUE_OFFSET:NXS_CHROMIUM_TEXT_VALUE_OFFSET;
  void *value=((void *(*)(const void *))(base+getter))(node);
  model->value=string_text(value);
  ((void (*)(void *))(base+0x7246038))(&value);
  if(!model->value)return 0;
  model->start=((unsigned (*)(const void *))(base+NXS_CHROMIUM_TEXT_START_OFFSET))(node);
  model->end=((unsigned (*)(const void *))(base+NXS_CHROMIUM_TEXT_END_OFFSET))(node);
  model->editable=!((int (*)(const void *))(base+NXS_CHROMIUM_TEXT_READONLY_OFFSET))(node);
  if(model->start>model->end){free(model->value);model->value=NULL;return 0;}
  return 1;
}
static void text_selection(void *node,uint64_t start,uint64_t length) {
  if(start>UINT32_MAX||length>UINT32_MAX-start)return;
  ((int (*)(void *,unsigned,unsigned,int))(base+NXS_CHROMIUM_TEXT_SELECTION_OFFSET))(node,start,start+length,0);
}
static struct NXSResponse *send_text_model(struct NativeForm *form,const char *value,uint32_t start,uint32_t length,int editable) {
  size_t bytes=strlen(value),size=sizeof(struct NXSControlTextRequest)+bytes;
  struct NXSControlTextRequest *request=calloc(1,size);
  if(!request)return NULL;
  *request=(struct NXSControlTextRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=17,.process=identity(),
    .kind=form->kind,.control=form->control,.text_size=bytes,.selection_start=start,
    .selection_length=length,.editable=editable};
  memcpy(request+1,value,bytes);struct NXSResponse *response=exchange_bytes(request,size);free(request);
  return response&&response->parts[3].x==1?response:NULL;
}
static struct NXSResponse *sync_text_form(struct NativeForm *form,struct NXSResponse *response) {
  if(!response||!text_kind(form->kind))return NULL;
  struct BlinkTextModel model={0};if(!text_model(form->node,&model))return NULL;
  response=send_text_model(form,model.value,model.start,model.end-model.start,model.editable);
  free(model.value);
  if(response&&forms_multiline_viewport_enabled&&form->kind==NXS_TEXTAREA&&
     form->text_epoch!=atomic_load(&native_host_epoch)) {
    if(!restore_text_viewport(form))return NULL;
    response=form_request(form,5,0,0,0);
  }
  return response;
}
static struct NXSResponse *text_native_state(struct NativeForm *form) {
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=18,
    .process=identity(),.kind=form->kind,.control=form->control};
  struct NXSResponse *response=exchange_bytes(&request,sizeof(request));
  return response&&response->parts[3].x==1&&response->size>=sizeof(*response)+sizeof(struct NXSTextResponse)?response:NULL;
}
static int text_pointer_matches(struct NativeForm *form,struct NXSResponse *response,struct BlinkTextModel *model) {
  if(!response)return 0;
  struct NXSTextResponse state;memcpy(&state,response+1,sizeof(state));
  size_t length=strlen(model->value);
  int same=state.text_size==length&&response->size==sizeof(*response)+sizeof(state)+length&&
    !memcmp((char *)(response+1)+sizeof(state),model->value,length)&&
    !!(state.flags&2)==!!model->editable&&response->parts[2].x&&response->parts[3].y&&
    form_focused(form->node)&&form_enabled(form->node)&&
    form->text_width==form->rect.width&&form->text_height==form->rect.height&&
    model->start==form->text_start&&model->end==form->text_end;
  return same;
}
static void echo_text_selection(struct NativeForm *form) {
  struct BlinkTextModel model={0};if(!form->text_tracking||!text_model(form->node,&model))return;
  struct NXSResponse *response=text_native_state(form);
  if(text_pointer_matches(form,response,&model)) {
    struct NXSTextResponse state;memcpy(&state,response+1,sizeof(state));
    if(state.selection_start<=UINT32_MAX&&state.selection_length<=UINT32_MAX-state.selection_start) {
      form->text_start=state.selection_start;form->text_end=state.selection_start+state.selection_length;
      if(model.start!=form->text_start||model.end!=form->text_end)
        text_selection(form->node,state.selection_start,state.selection_length);
    }
  } else if(active_form==form)end_text_pointer(form,0);
  free(model.value);
  if(forms_multiline_viewport_enabled&&form->kind==NXS_TEXTAREA&&read_text_viewport(form))echo_text_viewport(form);
}
static void end_text_pointer(struct NativeForm *form,int echo) {
  if(!form->text_tracking)return;
  void *node=form->node;uint64_t control=form->control;
  struct BlinkTextModel before={0};
  struct BlinkTextTransaction transaction={.node=node,.frame=text_frame(node),.control=control};
  int scope=echo&&form->kind==NXS_SEARCHFIELD&&!text_transaction&&form_focused(node)&&
    text_model(node,&before);
  if(scope){transaction.before=before.value;text_transaction=&transaction;}
  if(active_form==form)active_form=NULL;
  struct NXSResponse *response=form_request(form,4,form->text_x,form->text_y,0);
  form=find_form(node);
  for(int n=0;response&&response->parts[0].y&&n<100;n++) {
    if(!form||form->control!=control)break;
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
    response=form_request(form,5,0,0,0);
    form=find_form(node);
  }
  if(scope){text_transaction=NULL;free(before.value);}
  if(!form||form->control!=control)return;
  if(transaction.attempted)sync_text_form(form,sync_form_focus(form,form_request(form,1,0,0,0)));
  if(echo)echo_text_selection(form);
  form->text_tracking=0;
  refresh_form_watch();
}
static struct NXSResponse *sync_text_image(struct NativeForm *form) {
  if(text_transaction&&text_transaction->node==form->node)
    return form_request(form,5,0,0,0);
  if(form->text_tracking) {
    struct BlinkTextModel model={0};if(!text_model(form->node,&model))return NULL;
    int same=text_pointer_matches(form,text_native_state(form),&model);free(model.value);
    /* Querying draws the actual busy editor without rebinding its model or
     * disturbing AppKit's mouseDown stack. Script/focus/size changes end it. */
    if(same)return form_request(form,5,0,0,0);
    end_text_pointer(form,0);
  }
  return sync_text_form(form,sync_form_focus(form,form_request(form,1,0,0,0)));
}
static int text_mouse_press(void *self,const void *event) {
  /* Pinned EventWithHitTestResults embeds WebMouseEvent first. Its hit result
   * holds a compressed InnerNode at 204 and scrollbar at 236 (audited code). */
  void *node=decode_member((const char *)event+204);
  struct NativeForm *form=form_ancestor(node);
  unsigned clicks=*(const unsigned *)((const char *)event+160);
  if(native_text_input_owned(form)&&form_focused(form->node)&&form_enabled(form->node)&&
     *(const int *)((const char *)event+120)==0&&clicks>0&&
     (clicks==1||(forms_pointer_capabilities&NXS_POINTER_CLICK_COUNT))&&
     !decode_member((const char *)event+236)) {
    struct BlinkTextModel model={0};
    if(text_model(form->node,&model)) {
      struct NXSResponse *response=sync_text_image(form);
      if(response&&(form->kind!=NXS_SEARCHFIELD||native_text_filter_register(native_text_proposal))) {
        struct FloatPoint point=form_point(form,event);
        response=clicks==1?form_request(form,2,point.x,point.y,event_modifiers(event)):
          native_pointer_press(form->kind,form->control,point.x,point.y,event_modifiers(event),clicks);
        if(response&&response->parts[0].y) {
          form->text_tracking=1;form->text_width=form->rect.width;form->text_height=form->rect.height;
          form->text_start=model.start;form->text_end=model.end;form->text_x=point.x;form->text_y=point.y;
          active_form=form;text_pointer_controller=self;text_pointer_frame=text_frame(form->node);
          text_pointer_handler=text_pointer_frame?decode_member((char *)text_pointer_frame+592):NULL;
          echo_text_selection(form);invalidate_form(form);free(model.value);return 1;
        }
      }
      free(model.value);
    }
  }
  return original_text_mouse_press(self,event);
}
static int text_mouse_drag(void *self,const void *event) {
  /* DOM/capture dispatch already ran. Avoid competing Blink text-data dragging
   * and selection autoscroll while the real native editor owns this gesture. */
  if(text_pointer_controller&&decode_member(self)==text_pointer_frame) {
    struct NativeForm *form=active_form;
    if(form&&text_kind(form->kind)) {
      struct FloatPoint point=form_point(form,event);form->text_x=point.x;form->text_y=point.y;
      form_request(form,3,point.x,point.y,event_modifiers(event));echo_text_selection(form);invalidate_form(form);
    }
    return 3;
  }
  return original_text_mouse_drag(self,event);
}
static int text_mouse_release(void *self,const void *event,const void *origin) {
  if(self==text_pointer_controller)return 1;
  return original_text_mouse_release(self,event,origin);
}
static int text_pointer_up(void *self,const void *event) {
  void *controller=self==text_pointer_handler?text_pointer_controller:NULL;
  int result=original_text_pointer_up(self,event);
  if(controller&&controller==text_pointer_controller) {
    /* This outer path also runs when a page cancels mouseup or discards its
     * target, so native tracking cannot remain stranded after release. */
    if(active_form&&text_kind(active_form->kind))end_text_pointer(active_form,1);
    text_pointer_controller=text_pointer_frame=text_pointer_handler=NULL;
  }
  return result;
}
static int native_text_proposal(const struct NXSNativeTextEdit *edit,const char *replacement,const char *command) {
  struct BlinkTextTransaction *transaction=text_transaction;
  if(!transaction||edit->process!=identity()||edit->control!=transaction->control)return 0;
  struct NativeForm *form=find_form(transaction->node);
  if(!form||form->control!=transaction->control||form->kind!=(int)edit->kind)return 0;
  transaction->edit=edit;transaction->attempted=1;
  if(!command||!strcmp(command,"insertText:")||!strcmp(command,"yank:")) {
    void *value=((void *(*)(const char *,size_t))(base+NXS_CHROMIUM_TEXT_FROM_UTF8_OFFSET))(replacement,strlen(replacement));
    int cancelled=((int (*)(void *,const void *,int,void *))(base+NXS_CHROMIUM_TEXT_BEFORE_INSERT_OFFSET))
      (transaction->node,&value,1,NULL);
    form=find_form(transaction->node);
    if(!cancelled&&form&&form->control==transaction->control&&text_frame(transaction->node)==transaction->frame) {
      void *handler=decode_member((char *)transaction->frame+592);
      if(handler)((int (*)(void *,const void *,void *,int))(base+NXS_CHROMIUM_TEXT_INSERT_EVENT_OFFSET))
        (handler,&value,transaction->event,0);
    }
    ((void (*)(void *))(base+0x7246038))(&value);
  } else {
    /* Delete requires a pre-existing DOM range; DeleteBackward reaches the
     * guarded hook that installs the native proposal after beforeinput. */
    static const struct {const char *native,*engine;} commands[]={
      {"deleteBackward:","DeleteBackward"},{"deleteForward:","DeleteForward"},
      {"deleteWordBackward:","DeleteWordBackward"},{"deleteWordForward:","DeleteWordForward"},
      {"deleteToBeginningOfLine:","DeleteToBeginningOfLine"},{"deleteToEndOfLine:","DeleteToEndOfLine"},
      {"delete:","DeleteBackward"},{"insertNewline:","InsertNewline"},{"insertTab:","InsertTab"}};
    int found=0;
    for(size_t i=0;i<sizeof(commands)/sizeof(*commands);i++)if(!strcmp(command,commands[i].native)) {
      void *name=((void *(*)(const char *,size_t))(base+NXS_CHROMIUM_TEXT_FROM_UTF8_OFFSET))
        (commands[i].engine,strlen(commands[i].engine));
      struct BlinkEditorCommand action={
        .command=((void *(*)(const void *))(base+NXS_CHROMIUM_TEXT_COMMAND_OFFSET))(&name),
        .source=0,.frame=transaction->frame};
      if(!action.command)action.frame=NULL;
      void *empty=NULL;
      ((int (*)(const void *,const void *,void *))(base+NXS_CHROMIUM_TEXT_EXECUTE_OFFSET))(&action,&empty,transaction->event);
      ((void (*)(void *))(base+0x7246038))(&name);found=1;break;
    }
    if(!found)note("native text command has no Blink transaction binding yet");
  }
  /* Blink owns validation, events and undo. Echo its canonical model after
   * dispatch instead of allowing a second local native text mutation. */
  return 0;
}
static void native_delete_selection(void) {
  struct BlinkTextTransaction *transaction=text_transaction;
  if(!transaction||!transaction->edit)return;
  struct NativeForm *form=find_form(transaction->node);
  if(!form||form->control!=transaction->control)return;
  struct BlinkTextModel current={0};
  if(text_model(transaction->node,&current)) {
    const struct NXSNativeTextEdit *edit=transaction->edit;
    /* The real beforeinput dispatch already ran; preserve script changes. */
    if(!strcmp(current.value,transaction->before)&&current.start==edit->selection_start&&
       current.end-current.start==edit->selection_length)
      text_selection(transaction->node,edit->range_start,edit->range_length);
    free(current.value);
  }
}
static void text_delete_backward(void *document,unsigned char options,int granularity) {
  native_delete_selection();original_text_delete_backward(document,options,granularity);
}
static void text_delete_forward(void *document,void *state,unsigned char options,int granularity) {
  native_delete_selection();original_text_delete_forward(document,state,options,granularity);
}
static int default_text_key(void *node,void *event) {
  struct NativeForm *form=find_form(node);
  unsigned short *flags=(unsigned short *)((char *)event+32);
  if(!native_text_input_owned(form)||!form_focused(node)||text_transaction||!(*flags&0x100)||(*flags&0x60))return 0;
  uintptr_t atom=*(const uintptr_t *)((char *)event+24);
  int down=same_atom(atom,0x123a55d8),press=same_atom(atom,0x123a55e0);
  if((!down&&!press)||*(const unsigned char *)((char *)event+140))return 0;
  char *key=string_text(*(void **)((char *)event+128));if(!key)return 0;
  void *web=*(void **)((char *)event+112);if(!web){free(key);return 0;}
  unsigned modifiers=event_modifiers(web),logical=logical_key(key);
  if(!strcmp(key,"Control")||!strcmp(key,"Alt")||!strcmp(key,"Shift")||!strcmp(key,"Meta")){free(key);return 0;}
  if(down&&(logical==NXS_KEY_ENTER||(!logical&&!(modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))))){free(key);return 0;}
  if(press&&(modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))){free(key);return 0;}
  if(form->text_tracking) {
    uint64_t control=form->control;end_text_pointer(form,1);form=find_form(node);
    if(!form||form->control!=control){free(key);*flags|=0x40;return 1;}
  }
  char *text=(modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))&&!logical?strdup(key):keyboard_text(web,102,"");
  /* Linux supplies a derived control character in unmodifiedText for real
   * Control-letter events. GNUstep expects the key's character here; Blink's
   * DOM key already supplies it. Keep Alt/AltGr and logical-key data intact. */
  char *unmodified=text&&!logical&&(modifiers&NXS_CONTROL)&&!(modifiers&(NXS_ALT|NXS_SUPER))?
    strdup(text):keyboard_text(web,110,"");free(key);
  struct BlinkTextModel before={0};
  if(!text||!unmodified||!text_model(node,&before)){free(text);free(unmodified);return 0;}
  uint64_t control=form->control;
  struct NXSResponse *response=sync_text_form(form,sync_form_focus(form,form_request(form,1,0,0,0)));
  struct BlinkTextTransaction transaction={.node=node,.frame=text_frame(node),.event=event,.control=control,.before=before.value};
  if(response&&transaction.frame&&native_text_filter_register(native_text_proposal)&&
     (!forms_commands_enabled||native_command_filter_register(chromium_application_command))) {
    text_transaction=&transaction;
    response=form_input_request(form,8,0,NXS_KEY_DOWN,logical,text,unmodified,modifiers,!!(*(const unsigned *)((char *)event+108)&(1u<<5)));
    text_transaction=NULL;
  } else response=NULL;
  free(text);free(unmodified);free(before.value);
  int handled=response?response->parts[3].x:transaction.attempted?NXS_INPUT_HANDLED:0;
  form=find_form(node);
  if(form&&form->control==control) {
    if(response&&!transaction.attempted) {
      struct NXSControlRequest get={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=18,.process=identity(),.kind=form->kind,.control=control};
      response=exchange_bytes(&get,sizeof(get));
      if(response&&response->parts[3].x==1&&response->size>=sizeof(*response)+sizeof(struct NXSTextResponse)) {
        struct NXSTextResponse state;memcpy(&state,response+1,sizeof(state));text_selection(node,state.selection_start,state.selection_length);
      }
    }
    if(sync_text_form(form,form_request(form,1,0,0,0))&&handled&&
       forms_multiline_viewport_enabled&&form->kind==NXS_TEXTAREA&&read_text_viewport(form))echo_text_viewport(form);
    invalidate_form(form);
  }
  if(handled==NXS_INPUT_NEXT||handled==NXS_INPUT_PREVIOUS)advance_form_focus(node,event,handled);
  if(handled&&(logical!=NXS_KEY_ENTER||input_form_kind(node)==NXS_TEXTAREA)){*flags|=0x40;return 1;}
  return 0;
}
static int paint_text_field(void *self,const void *element,const void *style,const void *info,const struct Rect *rect) {
  int kind=forms_text_enabled?input_form_kind((void *)element):0;
  /* A complete native widget is painted in border-box space. Blink's second
   * theme call paints the scrolling document background, not another widget. */
  if(kind==NXS_TEXTAREA&&forms_multiline_viewport_enabled&&
     *((const unsigned char *)info+NXS_MULTILINE_CONTENTS_PAINT_BYTE))return 0;
  if(text_kind(kind)&&rect->width>=1&&rect->height>=1) {
    if(!paint_form(kind,self,element,NULL,style,info,rect)&&refresh_form_watch())return 0;
    struct NativeForm *form=find_form(element);if(form)form->painted=0;
  }
  return original_text_paint(self,element,style,info,rect);
}
static void text_carets(void *self,const void *state,const void *info,const void *offset) {
  struct NativeForm *form=form_ancestor(native_parent);
  if(form&&text_kind(form->kind)&&form->painted)return;
  original_text_carets(self,state,info,offset);
}
static void text_view_value(void *node,const void *value) {
  original_text_view_value(node,value);
  struct NativeForm *form=find_form(node);
  /* Blink normally invalidates anonymous editor content for a script value
   * update. This field's complete native snapshot belongs to its background. */
  if(form&&text_kind(form->kind))invalidate_form(form);
}
static int text_selection_changed(void *node,unsigned start,unsigned end,int direction) {
  int changed=original_text_selection(node,start,end,direction);
  struct NativeForm *form=find_form(node);
  if(changed&&form&&text_kind(form->kind))invalidate_form(form);
  return changed;
}
static struct Detour text_detours[]={
  {NXS_TEXTAREA_DEFAULT_OFFSET,nxs_textarea_default_bytes,textarea_default,(void **)&original_textarea_default},
  {NXS_CHROMIUM_TEXT_MOUSE_PRESS_OFFSET,chromium_text_mouse_press_bytes,text_mouse_press,(void **)&original_text_mouse_press},
  {NXS_CHROMIUM_TEXT_MOUSE_DRAG_OFFSET,chromium_text_mouse_drag_bytes,text_mouse_drag,(void **)&original_text_mouse_drag},
  {NXS_CHROMIUM_TEXT_MOUSE_RELEASE_OFFSET,chromium_text_mouse_release_bytes,text_mouse_release,(void **)&original_text_mouse_release},
  {NXS_CHROMIUM_TEXT_POINTER_UP_OFFSET,chromium_text_pointer_up_bytes,text_pointer_up,(void **)&original_text_pointer_up},
  {NXS_CHROMIUM_TEXT_SELECTION_OFFSET,chromium_text_selection_bytes,text_selection_changed,(void **)&original_text_selection},
  {NXS_CHROMIUM_TEXT_VIEW_VALUE_OFFSET,chromium_text_view_value_bytes,text_view_value,(void **)&original_text_view_value},
  {NXS_CHROMIUM_TEXT_PAINT_OFFSET,chromium_text_paint_bytes,paint_text_field,(void **)&original_text_paint},
  {NXS_CHROMIUM_TEXT_CARETS_OFFSET,chromium_text_carets_bytes,text_carets,(void **)&original_text_carets},
  {NXS_CHROMIUM_TEXT_DELETE_BACKWARD_OFFSET,chromium_text_delete_backward_bytes,text_delete_backward,(void **)&original_text_delete_backward},
  {NXS_CHROMIUM_TEXT_DELETE_FORWARD_OFFSET,chromium_text_delete_forward_bytes,text_delete_forward,(void **)&original_text_delete_forward}
};
