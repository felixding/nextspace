/* Native field model and Gecko transactions. No text editor is implemented here. */
#include "pinned-text.h"
#include "../../Libraries/NativeUI/Bridge/TextPlaceholder.inc"
static char *text_placeholder(void *);
#include "frontend.inc"
#include "commands.inc"
struct TextModel {char *value;uint32_t start,end;int editable;};
struct TextTransaction {
  void *node,*editor,*pres_context,*pointer_event;
  const struct NXSNativeTextEdit *edit;
  const char *before;
  int attempted,delete_depth;
};
static __thread struct TextTransaction *text_transaction;
static int native_text_proposal(const struct NXSNativeTextEdit *,const char *,const char *);
static void (*original_text_scroll_display)(void *,void *,const void *);
static uint32_t (*original_text_keypress)(void *,void *);
static void *original_text_delete_subaction;
static uint32_t (*original_text_delete_action)(void *,short,short,void *);
static uint32_t (*original_text_frame_event)(void *,void *,void *,int *);
static unsigned text_watch;
static int (*text_watch_remove)(unsigned);
static int text_kind(int kind){return kind==NXS_TEXTFIELD||kind==NXS_PASSWORD||kind==NXS_TEXTAREA||kind==NXS_SEARCHFIELD;}
static void *text_control_state(void *node)
{return *(void **)((char *)node+(node_kind(node)==NXS_TEXTAREA?304:352));}
static uint32_t (*original_textarea_post)(void *,void *);
static uint32_t textarea_post(void *node,void *visitor)
{if(multiline_enabled)text_post_keyboard(node,visitor);return original_textarea_post(node,visitor);}
static void clear_text_error(struct GeckoError *error)
{((void (*)(void *))(base+NXS_GECKO_TEXT_CLEAR_ERROR_OFFSET))(error);}
static int native_text_frame(const void *frame) {
  if(!texts_enabled||!frame||*(const uintptr_t *)frame!=base+0xa10b810+16||!text_kind(frame_kind(frame)))return 0;
  if(frontend_text_frame(frame))return 1;
  const void *style=*(void *const *)((const char *)frame+32),*display=*(void *const *)((const char *)style+80);
  return ((int (*)(const void *,const void *,void *))(base+NXS_GECKO_TEXT_IS_THEMED_OFFSET))(frame,display,NULL);
}
static int text_model(void *node,struct TextModel *model) {
  static const uint16_t empty;
  struct GeckoString value={.data=&empty,.flags=1};
  if(number_node(node)) {
    void *state=text_control_state(node);if(!state)return 0;
    ((void (*)(const void *,void *,int))(base+NXS_GECKO_NUMBER_VALUE))(state,&value,1);
  } else if(node_kind(node)==NXS_TEXTAREA)
    ((void (*)(void *,void *))(base+NXS_GECKO_MULTILINE_VALUE_OFFSET))(node,&value);
  else ((void (*)(void *,void *,unsigned))(base+NXS_GECKO_TEXT_VALUE_OFFSET))(node,&value,0);
  model->value=utf8_text(value.data,value.length);
  ((void (*)(void *))(base+0x3826f2c))(&value);
  if(!model->value)return 0;
  struct GeckoError error={0};
  if(node_kind(node)==NXS_TEXTAREA||number_node(node)) {
    ((void (*)(void *,uint32_t *,uint32_t *,void *))(base+NXS_GECKO_MULTILINE_SELECTION_OFFSET))
      (text_control_state(node),&model->start,&model->end,&error);
  } else {
    model->start=((uint32_t (*)(void *,void *))(base+NXS_GECKO_TEXT_SELECTION_START_OFFSET))(node,&error);
    model->end=((uint32_t (*)(void *,void *))(base+NXS_GECKO_TEXT_SELECTION_END_OFFSET))(node,&error);
  }
  int okay=!(error.result&0x80000000u)&&model->start<=model->end&&strlen(model->value)<=65536;
  clear_text_error(&error);
  model->editable=!(*(const uint64_t *)((const char *)node+112)&0x800010u);
  if(!okay){free(model->value);model->value=NULL;}return okay;
}
static int text_selection(void *node,uint64_t start,uint64_t length) {
  if(!text_kind(node_kind(node))||start>UINT32_MAX||length>UINT32_MAX-start)return 0;
  void *state=text_control_state(node);if(!state)return 0;
  struct GeckoError error={0};
  ((void (*)(void *,uint32_t,uint32_t,unsigned,void *,unsigned))(base+NXS_GECKO_TEXT_SELECTION_SET_OFFSET))
    (state,start,start+length,0,&error,1);
  int okay=!(error.result&0x80000000u);clear_text_error(&error);return okay;
}
static struct NXSResponse *native_text_state(struct Widget *w) {
  struct NXSControlRequest get={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=18,.process=identity(),.kind=w->kind,.control=w->id};
  struct NXSResponse *response=exchange_bytes(&get,sizeof(get));
  return response&&response->parts[3].x==1&&response->size>=sizeof(*response)+sizeof(struct NXSTextResponse)?response:NULL;
}
static void echo_native_selection(struct Widget *w) {
  struct NXSResponse *response=native_text_state(w);
  if(response) {
    struct NXSTextResponse selection;memcpy(&selection,response+1,sizeof(selection));
    struct TextModel model={0};
    if(text_model(w->node,&model)) {
      size_t length=strlen(model.value);
      if(selection.text_size==length&&response->size==sizeof(*response)+sizeof(selection)+length&&
         !memcmp((char *)(response+1)+sizeof(selection),model.value,length))
        text_selection(w->node,selection.selection_start,selection.selection_length);
      free(model.value);
    }
  }
  if(multiline_viewport_enabled&&w->kind==NXS_TEXTAREA)echo_text_viewport(w);
}
static struct NXSResponse *end_text_pointer(struct Widget *w,int commit,void *context,void *event) {
  void *node=w->node;uint64_t control=w->id;
  struct TextModel before={0};
  struct TextTransaction transaction={.node=node,.pres_context=context,.pointer_event=event};
  int scope=commit&&w->kind==NXS_SEARCHFIELD&&!text_transaction&&widget_focused(w)&&text_model(node,&before);
  if(scope) {
    transaction.editor=((void *(*)(void *))(base+NXS_GECKO_TEXT_EDITOR_OFFSET))(node);
    if(transaction.editor) {
      ((unsigned (*)(void *))(base+NXS_GECKO_TEXT_EDITOR_ADDREF_OFFSET))(transaction.editor);
      transaction.before=before.value;text_transaction=&transaction;
    }
  }
  if(active_widget==w)active_widget=NULL;
  struct NXSResponse *response=widget_request(w,4,w->range_x,w->range_y,0);
  w=widget_for_node(node);
  for(unsigned n=0;response&&response->parts[0].y&&n<100;n++) {
    if(!w||w->id!=control)break;
    struct timespec pause={.tv_nsec=2000000};nanosleep(&pause,NULL);
    response=widget_request(w,5,0,0,0);w=widget_for_node(node);
  }
  if(scope) {
    if(transaction.editor){text_transaction=NULL;((unsigned (*)(void *))(base+NXS_GECKO_TEXT_EDITOR_RELEASE_OFFSET))(transaction.editor);}
    free(before.value);
  }
  w=widget_for_node(node);
  if(w&&w->id==control){w->text_tracking=0;if(transaction.attempted)response=sync_text_widget(w);}
  return response;
}
static struct NXSResponse *sync_text_widget(struct Widget *w) {
  struct TextModel model={0};if(!text_model(w->node,&model))return NULL;
  if(w->text_tracking) {
    struct NXSResponse *native=native_text_state(w);struct NXSTextResponse state={0};
    if(native)memcpy(&state,native+1,sizeof(state));
    size_t length=strlen(model.value);
    int same=native&&state.text_size==length&&native->size==sizeof(*native)+sizeof(state)+length&&
      !memcmp((char *)(native+1)+sizeof(state),model.value,length)&&!!(state.flags&2)==!!model.editable&&
      widget_focused(w)&&native->parts[2].x&&w->width==w->text_width&&w->height==w->text_height;
    if(same) {
      struct NXSResponse *response=widget_request(w,5,0,0,0);
      if(!response||!button_cache_update(w,response))response=NULL;
      free(model.value);return response;
    }
    end_text_pointer(w,0,NULL,NULL);
  }
  struct NXSResponse *response=widget_request(w,1,0,0,0);
  if(!response)goto done;
  if(!!response->parts[3].y!=widget_focused(w)) {
    struct NXSControlInputRequest focus={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=7,.process=identity(),
      .kind=w->kind,.control=w->id,.focused=widget_focused(w)};
    response=exchange_bytes(&focus,sizeof(focus));if(!response)goto done;
  }
  if(placeholder_enabled&&w->kind!=NXS_TEXTAREA) {
    char *placeholder=text_placeholder(w->node);
    int accepted=placeholder&&native_text_placeholder(w->kind,w->id,placeholder);
    free(placeholder);if(!accepted){response=NULL;goto done;}
  }
  size_t length=strlen(model.value),size=sizeof(struct NXSControlTextRequest)+length;
  struct NXSControlTextRequest *request=calloc(1,size);if(!request){response=NULL;goto done;}
  *request=(struct NXSControlTextRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=17,.process=identity(),
    .kind=w->kind,.control=w->id,.text_size=length,.selection_start=model.start,
    .selection_length=model.end-model.start,.editable=model.editable};
  memcpy(request+1,model.value,length);response=exchange_bytes(request,size);free(request);
  if(!response||response->parts[3].x!=1){response=NULL;goto done;}
  if(multiline_viewport_enabled&&w->kind==NXS_TEXTAREA) {
    response=sync_viewport_widget(w)?widget_request(w,5,0,0,0):NULL;
  }
  if(!response||!button_cache_update(w,response))response=NULL;
 done:free(model.value);return response;
}
static int text_notification(int fd,unsigned condition,void *unused) {
  if(condition&~1u){text_watch=0;color_native_work(1);return 0;}
  drain_widget_notifier();
  color_native_work(0);
  number_native_work();
  tabs_native_notification();native_popup_notification();
  if(active_widget&&text_kind(active_widget->kind)) {
    void *node=active_widget->node;
    ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
    if(widget_focused(active_widget))echo_native_selection(active_widget);
    ((unsigned (*)(void *))(base+0x47ba6b8))(node);
  }
  for(struct Widget *w=widgets;w;w=w->next)if((text_kind(w->kind)&&w->text_owned)||w->kind==NXS_COLORWELL)invalidate_widget(w);
  return 1;
}
static void *text_pointer_frame(void *frame) {
  if(!frame)return NULL;
  void *root=native_text_frame(frame)?frame:
    ((void *(*)(void *,unsigned))(base+NXS_GECKO_TEXT_NEAREST_SCROLL_OFFSET))(frame,3);
  return native_text_frame(root)?root:NULL;
}
static uint32_t text_frame_event(void *frame,void *context,void *event,int *status) {
  unsigned message=*(const uint16_t *)((char *)event+18);
  if((*(const uint8_t *)((char *)event+48)&1)&&
     (message==13||((message==14||message==15)&&*(const int16_t *)((char *)event+152)==0))) {
    if(active_widget&&text_kind(active_widget->kind))return 0;
    void *root=text_pointer_frame(frame);
    if(message==15&&*status!=1&&!(*((const uint8_t *)event+49)&2)&&root&&prepare_text_image(root))return 0;
  }
  return original_text_frame_event(frame,context,event,status);
}
static uint32_t text_pointer_post(void *self,void *context,void *event,void *frame,int *status,void *override,void *root) {
  unsigned message=*(const uint16_t *)((char *)event+18);
  void *node=message==15&&root?*(void **)((char *)root+24):NULL;
  if(node)((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  if(active_widget&&text_kind(active_widget->kind)&&(message==13||message==14)) {
    struct Widget *w=active_widget;void *owner=w->node;uint64_t control=w->id;struct PointI point=widget_point(w,event);
    w->range_x=point.x/60.;w->range_y=point.y/60.;
    if(message==14&&*(const int16_t *)((char *)event+152)==0)end_text_pointer(w,1,context,event);
    else if(message==13)pointer_request(w,3,event);
    w=widget_for_node(owner);
    if(!w||w->id!=control) {
      /* Page beforeinput may destroy the frame during the native action.
       * DOM dispatch already ran; do not call the old widget's post handler. */
      *status=1;
      if(node)((unsigned (*)(void *))(base+0x47ba6b8))(node);
      return 0;
    }
    if(w&&w->id==control){if(widget_focused(w))echo_native_selection(w);invalidate_widget(w);}
  }
  uint64_t search_serial=native_search_activation.serial;
  uint32_t result=original_post_event(self,context,event,frame,status,override);
  if(search_serial&&native_search_activation.serial==search_serial)native_activation_clear(&native_search_activation);
  if(node&&*status!=1&&!(*((const uint8_t *)event+49)&2)&&*(const int16_t *)((char *)event+152)==0) {
    void *live=*(void **)((char *)node+96);
    if(prepare_text_image(live)) {
      struct Widget *w=widget_for_node(node);
      if(w&&widget_focused(w)&&!active_widget) {
        struct NXSResponse *response=widget_sync(w);
        if(response&&response->parts[2].x) {
          struct PointI point=widget_point(w,event);w->range_x=point.x/60.;w->range_y=point.y/60.;
          response=pointer_request(w,2,event);
          if(response&&response->parts[0].y) {
            w->text_tracking=1;w->text_width=w->width;w->text_height=w->height;active_widget=w;
            ((void (*)(void *,int))(base+NXS_GECKO_TEXT_STOP_DRAG_OFFSET))(self,1);
            ((void (*)(void *,unsigned,void *))(base+NXS_GECKO_TEXT_CAPTURE_OFFSET))(node,1,NULL);
            echo_native_selection(w);invalidate_widget(w);
          }
        }
      }
    } else if(live)original_text_frame_event(live,context,event,status);
  }
  if(node)((unsigned (*)(void *))(base+0x47ba6b8))(node);
  return result;
}
static int ensure_text_watch(void) {
  if(text_watch)return 1;
  unsigned (*add)(int,unsigned,int (*)(int,unsigned,void *),void *)=dlsym(RTLD_DEFAULT,"g_unix_fd_add");
  text_watch_remove=dlsym(RTLD_DEFAULT,"g_source_remove");
  if(!add||!text_watch_remove||widget_notifier<0)return 0;
  text_watch=add(widget_notifier,1,text_notification,NULL);return text_watch!=0;
}
static void remove_text_watch(void) {
  if(text_watch&&text_watch_remove)text_watch_remove(text_watch);
  text_watch=0;
}
static uint16_t *text_utf16(const char *input,uint32_t *length) {
  size_t bytes=strlen(input);uint16_t *out=malloc((bytes+1)*sizeof(*out));if(!out)return NULL;
  const unsigned char *p=(const unsigned char *)input;uint32_t used=0;
  while(*p) {
    uint32_t c=*p++;
    if(c>=0xf0){c&=7;for(int i=0;i<3;i++)c=(c<<6)|(*p++&63);}
    else if(c>=0xe0){c&=15;for(int i=0;i<2;i++)c=(c<<6)|(*p++&63);}
    else if(c>=0xc0){c=((c&31)<<6)|(*p++&63);}
    if(c>=0x10000){c-=0x10000;out[used++]=0xd800+(c>>10);out[used++]=0xdc00+(c&1023);}
    else out[used++]=c;
  }
  out[used]=0;*length=used;return out;
}
static int native_text_proposal(const struct NXSNativeTextEdit *edit,const char *replacement,const char *command) {
  struct TextTransaction *transaction=text_transaction;
  if(!transaction||edit->process!=identity())return 0;
  struct Widget *w=widget_for_node(transaction->node);
  if(!w||w->id!=edit->control||w->kind!=(int)edit->kind)return 0;
  transaction->edit=edit;transaction->attempted=1;
  uint32_t result=0;
  if(application_text_command(transaction->node,command)) {
    /* The existing controller may dispatch asynchronous paste or application
     * callbacks. Never perform a second edit in the native helper. */
  } else if(command&&!strcmp(command,"insertNewline:")&&node_kind(transaction->node)==NXS_TEXTAREA) {
    result=((uint32_t (*)(void *,void *))(base+NXS_GECKO_MULTILINE_NEWLINE_OFFSET))(transaction->editor,NULL);
  } else if(!command||!strcmp(command,"insertText:")||!strcmp(command,"yank:")||
      (node_kind(transaction->node)==NXS_TEXTAREA&&!strcmp(command,"insertTab:"))) {
    uint32_t length=0;uint16_t *data=text_utf16(replacement,&length);if(!data)return 0;
    struct GeckoString value={.data=data,.length=length,.flags=1};
    result=((uint32_t (*)(void *,const void *,void *))(base+NXS_GECKO_TEXT_INSERT_ACTION_OFFSET))(transaction->editor,&value,NULL);
    free(data);
  } else {
    static const struct {const char *name;short direction;} commands[]={
      {"deleteBackward:",2},{"deleteForward:",1},{"deleteWordBackward:",4},{"deleteWordForward:",3},
      {"deleteToBeginningOfLine:",5},{"deleteToEndOfLine:",6},{"delete:",0}};
    int found=0;
    for(size_t i=0;i<sizeof(commands)/sizeof(*commands);i++)if(!strcmp(command,commands[i].name)) {
      transaction->delete_depth=1;
      result=original_text_delete_action(transaction->editor,commands[i].direction,1,NULL);
      transaction->delete_depth=0;found=1;break;
    }
    if(!found)note("native text command has no engine transaction binding yet");
  }
  if(log_fd>=0)dprintf(log_fd,"%d native-text-transaction id=%llu result=%x\n",getpid(),(unsigned long long)edit->control,result);
  /* The engine owns validation, trusted events and undo. Echo its canonical
   * result after this native dispatch; do not perform a second local edit. */
  return 0;
}
static int native_application_command(const struct NXSNativeCommand *command,const char *selector) {
  struct TextTransaction *transaction=text_transaction;
  if(!transaction||command->process!=identity())return 0;
  struct Widget *w=widget_for_node(transaction->node);
  if(!w||w->id!=command->control||w->kind!=(int)command->kind)return 0;
  int numeric=number_application_command(transaction->node,selector,command->phase);
  if(numeric>=0){if(command->phase!=NXS_COMMAND_VALIDATE)transaction->attempted=1;return numeric;}
  if(search_actions_enabled&&w->kind==NXS_SEARCHFIELD&&(!strcmp(selector,"performClick:")||
     (search_clear_enabled&&!strcmp(selector,"clearSearch:")))) {
    if(!transaction->pres_context||!transaction->pointer_event)return !strcmp(selector,"clearSearch:")?0:-1;
    if(command->phase==NXS_COMMAND_VALIDATE)return 1;
    native_activation_arm(&native_search_activation,(uintptr_t)w->node,w->id,command->serial,!strcmp(selector,"clearSearch:")?NXS_SEARCH_CANCEL:NXS_SEARCH_BUTTON);
    native_search_context=transaction->pres_context;native_search_pointer_event=transaction->pointer_event;
    transaction->attempted=1;return 1;
  }
  int enabled=application_text_command_enabled(transaction->node,selector);
  if(enabled<0||command->phase==NXS_COMMAND_VALIDATE)return enabled;
  transaction->attempted=1;
  return enabled?application_text_command(transaction->node,selector):0;
}
static void search_clear(struct Widget *w) {
  if(text_transaction||!widget_focused(w)||!sync_text_widget(w))return;
  void *node=w->node;uint64_t control=w->id;
  struct TextModel before={0};if(!text_model(node,&before))return;
  struct TextTransaction transaction={.node=node,.before=before.value};
  transaction.editor=((void *(*)(void *))(base+NXS_GECKO_TEXT_EDITOR_OFFSET))(node);
  if(transaction.editor) {
    ((unsigned (*)(void *))(base+NXS_GECKO_TEXT_EDITOR_ADDREF_OFFSET))(transaction.editor);
    text_transaction=&transaction;
    native_control_perform_click(NXS_SEARCHFIELD,control,NXS_SEARCH_CANCEL);
    text_transaction=NULL;
    ((unsigned (*)(void *))(base+NXS_GECKO_TEXT_EDITOR_RELEASE_OFFSET))(transaction.editor);
    w=widget_for_node(node);if(w&&w->id==control)sync_text_widget(w);
  }
  free(before.value);
}
static uint32_t search_click_events(void *self,void *shell,void *event,int *status,void *target,void *override) {
  if(event!=native_search_pointer_event)return original_click_events(self,shell,event,status,target,override);
  struct NXSControlActivation action=native_search_activation;void *context=native_search_context;
  native_activation_clear(&native_search_activation);
  uint32_t result=original_click_events(self,shell,event,status,target,override);
  void *node=(void *)(uintptr_t)action.target;uint64_t control=action.control,item=action.item;
  struct Widget *w=widget_for_node(node);
  if(*status!=1&&w&&w->id==control&&w->kind==NXS_SEARCHFIELD&&!(widget_content_state(w)&16)&&
     native_activation_take(&action,(uintptr_t)node,control)) {
    if(item==NXS_SEARCH_CANCEL){search_clear(w);return result;}
    ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
    ((void (*)(void *))(base+NXS_GECKO_SEARCH_CHANGE_OFFSET))(node);
    w=widget_for_node(node);
    if(w&&w->id==control)((void (*)(void *,void *))(base+NXS_GECKO_SEARCH_SUBMIT_OFFSET))(node,context);
    ((unsigned (*)(void *))(base+0x47ba6b8))(node);
  }
  return result;
}
static void (*original_text_value_changed)(void *,unsigned,int,const void *);
static void text_value_changed(void *node,unsigned kind,int empty,const void *known) {
  original_text_value_changed(node,kind,empty,known);
  /* Value changes normally invalidate anonymous editor content. Its native
   * replacement lives in the owner's background display item instead. */
  if(texts_enabled&&text_kind(node_kind(node))) {
    struct Widget *w=widget_for_node(node);
    if(w&&w->text_owned)invalidate_widget(w);
  }
}
static int prepare_text_image(void *frame) {
  if(!native_text_frame(frame)||fabsf(frame_scale(frame)-1)>0.000001f)goto release;
  /* Engine callbacks can reflow while the native editor is waiting for its
   * pre-edit decision. Its existing object/image remain valid but busy. */
  if(text_transaction) {
    struct Widget *busy=widget_for_frame(frame);
    return busy&&busy->node==text_transaction->node&&busy->text_owned&&button_cache_available(busy);
  }
  struct Widget *w=bind_widget(frame);if(!w)goto release;
  int rect[4]={0};engine_frame_rect((void *)(base+0x6daae5c),frame,rect);
  double width=rect[2]/60.,height=rect[3]/60.;
  if(width<1||height<1||width>8192||height>8192||
     (!frontend_text_frame(frame)&&(width!=floor(width)||height!=floor(height))))goto release;
  w->width=width;w->height=height;
  if(w->number_stepper.control&&!number_node(w->node))number_forget(w);
  if(number_node(w->node)&&!number_prepare(w,width,height))goto release;
  if(frontend_text_frame(frame)&&log_fd>=0)dprintf(log_fd,"%d native-frontend-geometry id=%llu size=%.17g,%.17g\n",getpid(),(unsigned long long)w->id,width,height);
  if(!ensure_text_watch()||!native_text_filter_register(native_text_proposal)||
     (application_commands&&!native_command_filter_register(native_application_command))||!sync_text_widget(w))goto release;
  w->text_owned=1;w->painted=1;return 1;
 release: {
    struct Widget **cursor=&widgets;while(*cursor&&(*cursor)->frame!=frame)cursor=&(*cursor)->next;
    if(*cursor&&text_kind((*cursor)->kind))forget_widget(cursor);
    return 0;
  }
}
static void text_scroll_display(void *frame,void *builder,const void *lists) {
  if(lists_requested&&native_list_display(frame,builder,lists))return;
  if(prepare_text_image(frame)) {
    /* Use the existing background display item for the complete native field.
     * Its native editor now owns contents, clipping, selection and caret. */
    void *previous=frontend_background_frame;
    if(frontend_text_frame(frame))frontend_background_frame=frame;
    ((void (*)(void *,void *,const void *))(base+NXS_GECKO_TEXT_DISPLAY_BACKGROUND_OFFSET))(frame,builder,lists);
    frontend_background_frame=previous;return;
  }
  struct Widget *w=widget_for_frame(frame);if(w&&text_kind(w->kind))w->text_owned=0;
  original_text_scroll_display(frame,builder,lists);
}
static uint32_t text_delete_action(void *editor,short direction,short strip,void *principal) {
  struct TextTransaction *t=text_transaction;
  int nested=t&&t->editor==editor&&t->delete_depth;
  if(nested)t->delete_depth++;
  uint32_t result=original_text_delete_action(editor,direction,strip,principal);
  if(nested)t->delete_depth--;
  return result;
}
__attribute__((naked)) static void call_text_delete(void *function,void *editor,short direction,short strip,void *output) {
  __asm__("mov x16,x0\nmov x0,x1\nmov w1,w2\nmov w2,w3\nmov x8,x4\nbr x16");
}
__attribute__((used,noinline)) static void text_delete_impl(void *editor,short direction,short strip,void *output) {
  struct TextTransaction *transaction=text_transaction;
  if(transaction&&transaction->editor==editor&&transaction->edit&&transaction->delete_depth<=1) {
    struct TextModel current={0};
    if(text_model(transaction->node,&current)) {
      const struct NXSNativeTextEdit *edit=transaction->edit;
      /* beforeinput has already run. Preserve changes made by its listeners. */
      if(!strcmp(current.value,transaction->before)&&current.start==edit->selection_start&&
         current.end-current.start==edit->selection_length&&
         text_selection(transaction->node,edit->range_start,edit->range_length))direction=0;
      free(current.value);
    }
  }
  call_text_delete(original_text_delete_subaction,editor,direction,strip,output);
}
__attribute__((naked)) static void text_delete(void *editor,short direction,short strip) {
  __asm__("mov x3,x8\nb text_delete_impl");
}
static int dispatch_text_key(void *node,void *event,void *listener) {
  void *manager=*(void **)(base+0xa439c38);
  if(!node||!manager||node!=*(void **)((char *)manager+128)||!text_kind(node_kind(node))||
     !(*(const uint8_t *)((char *)event+48)&1)||(*((const uint8_t *)event+49)&2)||text_transaction)return 0;
  ((unsigned (*)(void *))(base+0x3b9f0e4))(node);
  void *editor=((void *(*)(void *))(base+(node_kind(node)==NXS_TEXTAREA?NXS_GECKO_MULTILINE_EDITOR_OFFSET:NXS_GECKO_TEXT_EDITOR_OFFSET)))(node);
  if(!editor||(listener&&editor!=*(void **)((char *)listener+16)))goto fallback;
  ((unsigned (*)(void *))(base+NXS_GECKO_TEXT_EDITOR_ADDREF_OFFSET))(editor);
  if(listener&&!((int (*)(void *,void *))(*(uintptr_t **)editor)[76])(editor,event))goto release_editor;
  void *document=*(void **)((char *)editor+48);
  if(document)((void (*)(void *,unsigned))(base+NXS_GECKO_TEXT_FLUSH_LAYOUT_OFFSET))(document,6);
  struct Widget *w=widget_for_node(node);
  if(w&&w->text_tracking) {
    uint64_t control=w->id;end_text_pointer(w,0,NULL,NULL);
    if(native_search_activation.control==control)native_activation_clear(&native_search_activation);
  }
  void *frame=*(void **)((char *)node+96);
  if(!prepare_text_image(frame))goto release_editor;
  w=widget_for_node(node);if(!w)goto release_editor;
  struct TextModel before={0};if(!text_model(node,&before))goto release_editor;
  int modifier=text_modifier_event(event);
  char *text=key_text(event);if(!text){free(before.value);goto release_editor;}
  size_t length=strlen(text),size=sizeof(struct NXSControlInputRequest)+2*length;
  struct NXSControlInputRequest *request=calloc(1,size);if(!request){free(text);free(before.value);goto release_editor;}
  *request=(struct NXSControlInputRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=8,.process=identity(),
    .kind=w->kind,.control=w->id,.type=modifier?NXS_KEY_MODIFIERS:NXS_KEY_DOWN,.modifiers=widget_modifiers(event),
    .key=logical_key(*(uint32_t *)((char *)event+200)),.repeat=!!*((uint8_t *)event+223),.text_size=length,.unmodified_size=length};
  memcpy(request+1,text,length);memcpy((char *)(request+1)+length,text,length);free(text);
  struct TextTransaction transaction={.node=node,.editor=editor,.before=before.value};
  text_transaction=&transaction;
  struct NXSResponse *response=exchange_bytes(request,size);
  text_transaction=NULL;free(request);free(before.value);
  int handled=response?response->parts[3].x:transaction.attempted?NXS_INPUT_HANDLED:0;
  if(response&&!modifier&&!transaction.attempted&&text_command_reporting) {
    struct NXSControlRequest get={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=21,.process=identity(),.kind=w->kind,.control=w->id};
    response=exchange_bytes(&get,sizeof(get));
    if(response&&response->parts[3].x==1&&response->size>=sizeof(*response)&&response->size<=sizeof(*response)+256) {
      size_t bytes=response->size-sizeof(*response);char selector[257];memcpy(selector,response+1,bytes);selector[bytes]=0;
      transaction.attempted=application_text_command(node,selector);
    }
  }
  if(response&&!modifier&&!transaction.attempted) {
    w=widget_for_node(node);
    if(w) {
      struct NXSControlRequest get={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=18,.process=identity(),.kind=w->kind,.control=w->id};
      response=exchange_bytes(&get,sizeof(get));
      if(response&&response->size>=sizeof(*response)+sizeof(struct NXSTextResponse)) {
        struct NXSTextResponse selection;memcpy(&selection,response+1,sizeof(selection));
        text_selection(node,selection.selection_start,selection.selection_length);
      }
    }
  }
  w=widget_for_node(node);if(w){
    if(sync_text_widget(w)&&!modifier&&handled!=NXS_INPUT_UNHANDLED&&
       multiline_viewport_enabled&&w->kind==NXS_TEXTAREA)echo_text_viewport(w);
    invalidate_widget(w);
  }
  if(handled==NXS_INPUT_NEXT||handled==NXS_INPUT_PREVIOUS)advance_focus(node,handled);
  ((unsigned (*)(void *))(base+NXS_GECKO_TEXT_EDITOR_RELEASE_OFFSET))(editor);
  ((unsigned (*)(void *))(base+0x47ba6b8))(node);
  if(modifier)return 0;
  if(handled!=NXS_INPUT_UNHANDLED&&(*(const uint32_t *)((char *)event+200)!=13||node_kind(node)==NXS_TEXTAREA)) {
    ((void (*)(void *,int,void *))(base+NXS_GECKO_TEXT_PREVENT_DEFAULT_OFFSET))(event,1,NULL);
  }
  return handled;
 release_editor:((unsigned (*)(void *))(base+NXS_GECKO_TEXT_EDITOR_RELEASE_OFFSET))(editor);
 fallback:((unsigned (*)(void *))(base+0x47ba6b8))(node);return 0;
}
static uint32_t text_keypress(void *listener,void *event) {
  void *manager=*(void **)(base+0xa439c38),*node=manager?*(void **)((char *)manager+128):NULL;
  if(dispatch_text_key(node,event,listener)||!*(void **)((char *)listener+16))return 0;
  return original_text_keypress(listener,event);
}
static struct Detour text_detours[]={
  {NXS_GECKO_TEXT_DELETE_ACTION_OFFSET,gecko_text_delete_action_bytes,text_delete_action,(void **)&original_text_delete_action},
  {NXS_GECKO_TEXT_VALUE_CHANGED_OFFSET,gecko_text_value_changed_bytes,text_value_changed,(void **)&original_text_value_changed},
  {NXS_GECKO_MULTILINE_POST_OFFSET,gecko_multiline_post_bytes,textarea_post,(void **)&original_textarea_post},
  {NXS_GECKO_TEXT_FRAME_EVENT_OFFSET,gecko_text_frame_event_bytes,text_frame_event,(void **)&original_text_frame_event},
  {NXS_GECKO_TEXT_SCROLL_DISPLAY_OFFSET,gecko_text_scroll_display_bytes,text_scroll_display,(void **)&original_text_scroll_display},
  {NXS_GECKO_TEXT_KEYPRESS_OFFSET,gecko_text_keypress_bytes,text_keypress,(void **)&original_text_keypress},
  {NXS_GECKO_TEXT_DELETE_SUBACTION_OFFSET,gecko_text_delete_subaction_bytes,text_delete,&original_text_delete_subaction}
};
