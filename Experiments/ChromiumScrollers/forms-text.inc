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
static int (*original_text_paint)(void *,const void *,const void *,const void *,const struct Rect *);
static void (*original_text_carets)(void *,const void *,const void *,const void *);
static void (*original_text_delete_backward)(void *,unsigned char,int);
static void (*original_text_delete_forward)(void *,void *,unsigned char,int);
static void (*original_text_view_value)(void *,const void *);
static int (*original_text_selection)(void *,unsigned,unsigned,int);
static int text_kind(int kind){return kind==NXS_TEXTFIELD||kind==NXS_PASSWORD;}
static void *text_frame(void *node) {
  void *document=node_document(node),*window=document?decode_member((char *)document+264):NULL;
  return window?decode_member((char *)window+32):NULL;
}
static int text_model(void *node,struct BlinkTextModel *model) {
  void *value=((void *(*)(const void *))(base+NXS_CHROMIUM_TEXT_VALUE_OFFSET))(node);
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
static struct NXSResponse *sync_text_form(struct NativeForm *form,struct NXSResponse *response) {
  if(!response)return NULL;
  struct BlinkTextModel model={0};if(!text_model(form->node,&model))return NULL;
  size_t length=strlen(model.value),size=sizeof(struct NXSControlTextRequest)+length;
  struct NXSControlTextRequest *request=calloc(1,size);
  if(!request){free(model.value);return NULL;}
  *request=(struct NXSControlTextRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=17,.process=identity(),
    .kind=form->kind,.control=form->control,.text_size=length,.selection_start=model.start,
    .selection_length=model.end-model.start,.editable=model.editable};
  memcpy(request+1,model.value,length);response=exchange_bytes(request,size);
  free(request);free(model.value);
  return response&&response->parts[3].x==1?response:NULL;
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
    static const struct {const char *native,*engine;} commands[]={
      {"deleteBackward:","DeleteBackward"},{"deleteForward:","DeleteForward"},
      {"deleteWordBackward:","DeleteWordBackward"},{"deleteWordForward:","DeleteWordForward"},
      {"deleteToBeginningOfLine:","DeleteToBeginningOfLine"},{"deleteToEndOfLine:","DeleteToEndOfLine"},
      {"delete:","Delete"}};
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
  if(!form||!form->painted||!form_focused(node)||text_transaction||!(*flags&0x100)||(*flags&0x60))return 0;
  uintptr_t atom=*(const uintptr_t *)((char *)event+24);
  int down=same_atom(atom,0x123a55d8),press=same_atom(atom,0x123a55e0);
  if((!down&&!press)||*(const unsigned char *)((char *)event+140))return 0;
  char *key=string_text(*(void **)((char *)event+128));if(!key)return 0;
  void *web=*(void **)((char *)event+112);if(!web){free(key);return 0;}
  unsigned modifiers=event_modifiers(web),logical=logical_key(key);
  if(!strcmp(key,"Control")||!strcmp(key,"Alt")||!strcmp(key,"Shift")||!strcmp(key,"Meta")){free(key);return 0;}
  if(down&&(logical==NXS_KEY_ENTER||(!logical&&!(modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))))){free(key);return 0;}
  if(press&&(modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))){free(key);return 0;}
  char *text=(modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))&&!logical?strdup(key):keyboard_text(web,102,"");
  char *unmodified=keyboard_text(web,110,"");free(key);
  struct BlinkTextModel before={0};
  if(!text||!unmodified||!text_model(node,&before)){free(text);free(unmodified);return 0;}
  uint64_t control=form->control;
  struct NXSResponse *response=sync_text_form(form,sync_form_focus(form,form_request(form,1,0,0,0)));
  struct BlinkTextTransaction transaction={.node=node,.frame=text_frame(node),.event=event,.control=control,.before=before.value};
  if(response&&transaction.frame&&native_text_filter_register(native_text_proposal)) {
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
    sync_text_form(form,form_request(form,1,0,0,0));invalidate_form(form);
  }
  if(handled==NXS_INPUT_NEXT||handled==NXS_INPUT_PREVIOUS)advance_form_focus(node,event,handled);
  if(handled&&logical!=NXS_KEY_ENTER){*flags|=0x40;return 1;}
  return 0;
}
static int paint_text_field(void *self,const void *element,const void *style,const void *info,const struct Rect *rect) {
  int kind=forms_text_enabled?input_form_kind((void *)element):0;
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
  {NXS_CHROMIUM_TEXT_SELECTION_OFFSET,chromium_text_selection_bytes,text_selection_changed,(void **)&original_text_selection},
  {NXS_CHROMIUM_TEXT_VIEW_VALUE_OFFSET,chromium_text_view_value_bytes,text_view_value,(void **)&original_text_view_value},
  {NXS_CHROMIUM_TEXT_PAINT_OFFSET,chromium_text_paint_bytes,paint_text_field,(void **)&original_text_paint},
  {NXS_CHROMIUM_TEXT_CARETS_OFFSET,chromium_text_carets_bytes,text_carets,(void **)&original_text_carets},
  {NXS_CHROMIUM_TEXT_DELETE_BACKWARD_OFFSET,chromium_text_delete_backward_bytes,text_delete_backward,(void **)&original_text_delete_backward},
  {NXS_CHROMIUM_TEXT_DELETE_FORWARD_OFFSET,chromium_text_delete_forward_bytes,text_delete_forward,(void **)&original_text_delete_forward}
};
