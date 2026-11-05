/* Views application-model bindings. All text controls remain in NativeUI. */
#include "pinned-views.h"
struct ViewsRange {uint32_t start,end;};
struct ViewsString {const uint16_t *data;size_t length;};
struct ViewsField {
  struct ViewsField *next;
  struct NativeForm transport; /* Reuse the shared control wire helpers only. */
  int owned;
};
struct ViewsTransaction {
  void *view;
  uint64_t control;
  const void *event,*string;
  const char *input;
  struct BlinkTextModel before;
  int behavior,attempted,proposed;
};
static struct ViewsField *views_fields;
static __thread void *views_paint_root,*views_caret_owner;
static __thread struct ViewsTransaction *views_transaction;
static void (*original_views_omnibox_paint)(void *,void *);
static void (*original_views_text_paint)(void *,void *);
static void (*original_views_border)(void *,void *);
static void (*original_views_cursor)(void *);
static int (*original_views_has_focus)(void *);
static void (*original_views_focus)(void *),(*original_views_blur)(void *),(*original_views_destroy)(void *);
static int (*original_views_controller_key)(void *,void *,const void *);
static int (*original_views_accelerator_key)(void *,const void *);
static void (*original_views_insert_char)(void *,const void *);
static void (*original_views_insert_text)(void *,const void *,int);
static struct ViewsField *find_views_field(const void *view) {
  for(struct ViewsField *f=views_fields;f;f=f->next)if(f->transport.node==view)return f;
  return NULL;
}
static int views_watch_needed(void) {
  if(views_enabled)for(struct ViewsField *f=views_fields;f;f=f->next)if(f->owned)return 1;
  return 0;
}
static void views_schedule(void *view)
{((void (*)(void *))(base+NXS_CHROMIUM_VIEWS_SCHEDULE_OFFSET))(view);}
static void views_native_work(int failed) {
  if(!views_enabled)return;
  for(struct ViewsField *f=views_fields;f;f=f->next)if(f->owned) {
    if(failed)f->owned=0;
    views_schedule(f->transport.node);
  }
}
static int views_model(void *view,struct BlinkTextModel *model) {
  struct ViewsString value=((struct ViewsString (*)(const void *))(base+NXS_CHROMIUM_VIEWS_VALUE_OFFSET))(view);
  if(value.length>65536||(!value.data&&value.length))return 0;
  model->value=encode_text(value.data,value.length,0);if(!model->value)return 0;
  /* These are the actual model/render-text range accesses in the guarded
   * GetEditableSelectionRange, also valid for display-only field snapshots. */
  void *render=*(void **)((char *)*(void **)((char *)view+872)+16);
  struct ViewsRange range=*(struct ViewsRange *)((char *)render+80);
  model->start=range.start<range.end?range.start:range.end;
  model->end=range.start>range.end?range.start:range.end;
  model->editable=!(*(const unsigned char *)((char *)view+892)&1);
  if(model->end>value.length){free(model->value);model->value=NULL;return 0;}
  return 1;
}
static void views_trace(struct ViewsField *f,const struct BlinkTextModel *model) {
  if(!views_trace_enabled||log_fd<0)return;
  size_t size=strlen(model->value);char *hex=malloc(size*2+1);if(!hex)return;
  const char digits[]="0123456789abcdef";
  for(size_t i=0;i<size;i++){unsigned char c=model->value[i];hex[i*2]=digits[c>>4];hex[i*2+1]=digits[c&15];}hex[size*2]=0;
  struct Rect bounds=((struct Rect (*)(const void *))(base+NXS_CHROMIUM_VIEWS_BOUNDS_OFFSET))(f->transport.node);
  dprintf(log_fd,"views-state id=%llu value_hex=%s start=%u end=%u focused=%d x=%d y=%d width=%d height=%d owned=%d\n",
    (unsigned long long)f->transport.control,hex,model->start,model->end,original_views_has_focus(f->transport.node),
    bounds.x,bounds.y,bounds.width,bounds.height,f->owned);free(hex);
}
static struct NXSResponse *views_sync(struct ViewsField *f) {
  void *view=f->transport.node;struct BlinkTextModel model={0};
  if(!views_model(view,&model))return NULL;
  f->transport.rect=*(struct Rect *)((char *)view+440);
  f->transport.enabled=*(const unsigned char *)((char *)view+458)==1;
  struct NXSResponse *response=form_request(&f->transport,1,0,0,0);
  if(response&&!!response->parts[3].y!=original_views_has_focus(view))
    response=form_input_request(&f->transport,7,original_views_has_focus(view),0,0,NULL,NULL,0,0);
  if(response)response=send_text_model(&f->transport,model.value,model.start,model.end-model.start,model.editable);
  views_trace(f,&model);free(model.value);return response;
}
static int views_has_focus(void *view) {
  /* Only the engine's own caret visibility update sees this temporary
   * predicate. Application focus, selection and accessibility keep theirs. */
  return view==views_caret_owner?0:original_views_has_focus(view);
}
static void views_cursor(void *view) {
  struct ViewsField *f=find_views_field(view);void *previous=views_caret_owner;
  if(f&&f->owned)views_caret_owner=view;
  original_views_cursor(view);views_caret_owner=previous;
}
static void views_omnibox_paint(void *self,void *canvas) {
  void *previous=views_paint_root;
  /* The compiled Omnibox painter calls Textfield at its actual +16 base. */
  views_paint_root=(char *)self+16;original_views_omnibox_paint(self,canvas);views_paint_root=previous;
}
static void views_text_paint(void *view,void *canvas) {
  if(!views_enabled||view!=views_paint_root){original_views_text_paint(view,canvas);return;}
  struct ViewsField *f=find_views_field(view);
  if(!f) {
    f=calloc(1,sizeof(*f));if(!f){original_views_text_paint(view,canvas);return;}
    f->transport.node=view;f->transport.control=++next_form_control;
    f->transport.kind=NXS_TEXTFIELD;f->transport.title=strdup("");
    f->next=views_fields;views_fields=f;
  }
  f->owned=0;
  struct NXSResponse *response=views_sync(f);
  if(response&&response->width>0&&response->height>0&&response->width==f->transport.rect.width&&
     response->height==f->transport.rect.height&&response->stride==response->width*4&&
     response->size==sizeof(*response)+(size_t)response->stride*response->height) {
    struct NXSResponse header=*response;
    uint32_t *pixels=malloc((size_t)header.stride*header.height);
    if(pixels) {
      memcpy(pixels,response+1,(size_t)header.stride*header.height);
      /* Actual gfx::Canvas::sk_canvas(), verified by the compiled painter. */
      void *paint=*(void **)((char *)canvas+192);
      if(paint) {
        f->owned=1;
        if(refresh_form_watch()) {
          draw_native_bitmap(paint,pixels,header.width,0,0,0,0,header.width,header.height);
          free(pixels);views_cursor(view);return;
        }
      }
      free(pixels);
    }
  }
  f->owned=0;original_views_cursor(view);original_views_text_paint(view,canvas);
}
static void views_border(void *view,void *canvas) {
  struct ViewsField *f=find_views_field(view);
  if(!(view==views_paint_root&&f&&f->owned))original_views_border(view,canvas);
}
static void views_focus(void *view) {
  original_views_focus(view);struct ViewsField *f=find_views_field(view);
  if(f&&f->owned){views_sync(f);views_cursor(view);}
}
static void views_blur(void *view) {
  original_views_blur(view);struct ViewsField *f=find_views_field(view);
  if(f&&f->owned)form_input_request(&f->transport,7,0,0,0,NULL,NULL,0,0);
}
static void views_destroy(void *view) {
  struct ViewsField **cursor=&views_fields;
  while(*cursor&&(*cursor)->transport.node!=view)cursor=&(*cursor)->next;
  struct ViewsField *f=*cursor;
  if(f){*cursor=f->next;form_request(&f->transport,6,0,0,0);free(f->transport.title);free(f);refresh_form_watch();}
  original_views_destroy(view);
}
static void views_clipboard_command(void *view,int command) {
  /* This field is the guarded Omnibox's Textfield base. Its real virtual
   * command handler preserves clipboard policy, URL adjustment, asynchronous
   * paste, application callbacks and history. NativeUI chooses the command. */
  ((void (*)(void *,int))(base+NXS_CHROMIUM_VIEWS_OMNIBOX_EXECUTE_OFFSET))((char *)view-16,command);
}
static int views_native_proposal(const struct NXSNativeTextEdit *edit,const char *replacement,const char *command) {
  struct ViewsTransaction *t=views_transaction;
  if(!t||edit->process!=identity()||edit->control!=t->control)return 0;
  t->proposed=1;struct ViewsField *f=find_views_field(t->view);struct BlinkTextModel model={0};
  if(!f||f->transport.control!=t->control||!f->owned||!views_model(t->view,&model))return 0;
  int same=model.editable&&!strcmp(model.value,t->before.value)&&model.start==t->before.start&&model.end==t->before.end;
  free(model.value);if(!same)return 0;
  if(command&&(!strcmp(command,"cut:")||!strcmp(command,"paste:"))) {
    t->attempted=1;views_clipboard_command(t->view,!strcmp(command,"cut:")?NXS_VIEWS_CUT:NXS_VIEWS_PASTE);
  } else if(!*replacement&&edit->range_length&&edit->range_start<=UINT32_MAX&&edit->range_length<=UINT32_MAX-edit->range_start) {
    struct ViewsRange range={edit->range_start,edit->range_start+edit->range_length};t->attempted=1;
    ((int (*)(void *,const void *))(base+NXS_CHROMIUM_VIEWS_DELETE_OFFSET))(t->view,&range);
  } else if((!command||!strcmp(command,"insertText:")||!strcmp(command,"paste:")||!strcmp(command,"yank:"))&&
     edit->range_start==model.start&&edit->range_length==model.end-model.start) {
    if(t->event&&t->input&&!strcmp(t->input,replacement)){t->attempted=1;original_views_insert_char(t->view,t->event);}
    else if(t->string&&t->input&&!strcmp(t->input,replacement)){t->attempted=1;original_views_insert_text(t->view,t->string,t->behavior);}
    else {
      /* The pinned libc++ empty u16string is 24 zero bytes. Its actual Chromium
       * UTF converter and destructor own construction/allocation/release. */
      unsigned char value[24] __attribute__((aligned(8)))={0};
      if(((int (*)(const char *,size_t,void *))(base+NXS_CHROMIUM_VIEWS_UTF16_OFFSET))(replacement,strlen(replacement),value)) {
        t->attempted=1;original_views_insert_text(t->view,value,0);
      }
      ((void (*)(void *))(base+NXS_CHROMIUM_VIEWS_STRING_DESTROY_OFFSET))(value);
    }
  }
  /* The real application model owns callbacks and undo. Veto the second
   * native mutation, then echo canonical application state after dispatch. */
  return 0;
}
static unsigned views_modifiers(const void *event) {
  unsigned flags=*(const unsigned *)((const char *)event+80);
  return ((flags&2)?NXS_SHIFT:0)|((flags&4)?NXS_CONTROL:0)|((flags&8)?NXS_ALT:0)|((flags&16)?NXS_SUPER:0);
}
static unsigned views_logical(unsigned key) {
  switch(key) {
    case 8:return NXS_KEY_BACKSPACE;case 9:return NXS_KEY_TAB;case 13:return NXS_KEY_ENTER;
    case 27:return NXS_KEY_ESCAPE;case 33:return NXS_KEY_PAGE_UP;case 34:return NXS_KEY_PAGE_DOWN;
    case 35:return NXS_KEY_END;case 36:return NXS_KEY_HOME;case 37:return NXS_KEY_LEFT;
    case 38:return NXS_KEY_UP_ARROW;case 39:return NXS_KEY_RIGHT;case 40:return NXS_KEY_DOWN_ARROW;
    case 45:return NXS_KEY_INSERT;case 46:return NXS_KEY_DELETE;default:return NXS_KEY_TEXT;
  }
}
static int views_key(struct ViewsField *f,const void *event,const void *string,int behavior,const char *text,int character) {
  void *view=f->transport.node;
  if(!f->owned||views_transaction||!original_views_has_focus(view)||
     ((int (*)(const void *))(base+NXS_CHROMIUM_VIEWS_COMPOSITION_OFFSET))(view))return 0;
  struct ViewsTransaction transaction={.view=view,.control=f->transport.control,.event=character?event:NULL,.string=string,.behavior=behavior,.input=text};
  if(!views_model(view,&transaction.before))return 0;
  unsigned key=event?views_logical(*(const uint16_t *)((const char *)event+136)):NXS_KEY_TEXT;
  unsigned modifiers=event?views_modifiers(event):0;
  if(!views_sync(f)||!native_text_filter_register(views_native_proposal)){free(transaction.before.value);return 0;}
  views_transaction=&transaction;
  struct NXSResponse *response=form_input_request(&f->transport,8,0,NXS_KEY_DOWN,key,text,text,modifiers,
    event&&(*(const unsigned *)((const char *)event+80)&(1u<<17)));
  views_transaction=NULL;free(transaction.before.value);
  int handled=response&&response->parts[3].x;
  f=find_views_field(view);
  if(f&&f->transport.control==transaction.control) {
    if(handled&&!transaction.proposed) {
      struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=21,
        .process=identity(),.kind=f->transport.kind,.control=f->transport.control};
      response=exchange_bytes(&request,sizeof(request));
      if(response&&response->parts[3].x==1) {
        size_t length=response->size-sizeof(*response);const char *command=(const char *)(response+1);
        if(length==5&&!memcmp(command,"copy:",5)) {
          views_clipboard_command(view,NXS_VIEWS_COPY);
          transaction.attempted=1;
        }
      }
    }
    f=find_views_field(view);
    if(!f||f->transport.control!=transaction.control)return transaction.proposed?transaction.attempted:handled;
    if(handled&&!transaction.proposed&&!transaction.attempted) {
      response=text_native_state(&f->transport);
      if(response) {
        struct NXSTextResponse state;memcpy(&state,response+1,sizeof(state));
        if(state.selection_start<=UINT32_MAX&&state.selection_length<=UINT32_MAX-state.selection_start) {
          struct ViewsRange range={state.selection_start,state.selection_start+state.selection_length};
          ((int (*)(void *,const void *))(base+NXS_CHROMIUM_VIEWS_SELECTION_OFFSET))(view,&range);
        }
      }
    }
    f=find_views_field(view);
    if(f&&f->transport.control==transaction.control){views_sync(f);views_schedule(view);}
  }
  return transaction.proposed?transaction.attempted:handled;
}
static int views_command_key(struct ViewsField *f,const void *event) {
  if(!f||*(const int *)((const char *)event+8)!=7)return 0;
  unsigned key=*(const uint16_t *)((const char *)event+136),logical=views_logical(key);
  if(key==16||key==17||key==18||key==91||key==92||key==9||key==13)return 0;
  if(!logical&&!(views_modifiers(event)&(NXS_CONTROL|NXS_ALT|NXS_SUPER)))return 0; /* Real character insertion follows. */
  ((uint16_t (*)(const void *))(base+NXS_CHROMIUM_VIEWS_CHARACTER_OFFSET))(event);
  unsigned dom=*(const unsigned *)((const char *)event+152),code=dom&0x1fffff;
  uint16_t units[2]={code,0};unsigned count=1;
  if(code>0xffff){code-=0x10000;units[0]=0xd800+(code>>10);units[1]=0xdc00+(code&1023);count=2;}
  char *text=(dom&0x600000)==0x400000?encode_text(units,count,0):strdup("");
  int handled=0;if(text){handled=views_key(f,event,NULL,0,text,0);free(text);}return handled;
}
static int views_accelerator_key(void *manager,const void *event) {
  /* A focused native editor gets its own modified editing commands before
   * browser accelerators. The UI library decides which commands it handles;
   * there is no duplicated browser or GNUstep shortcut table here. */
  if(views_modifiers(event)&(NXS_CONTROL|NXS_ALT|NXS_SUPER))
    for(struct ViewsField *f=views_fields;f;f=f->next)
      if(f->owned&&original_views_has_focus(f->transport.node)&&
         ((void *(*)(void *))(base+NXS_CHROMIUM_VIEWS_FOCUS_MANAGER_OFFSET))(f->transport.node)==manager&&
         views_command_key(f,event))return 0;
  return original_views_accelerator_key(manager,event);
}
static int views_controller_key(void *controller,void *view,const void *event) {
  int handled=original_views_controller_key(controller,view,event);
  return handled?handled:views_command_key(find_views_field(view),event);
}
static void views_insert_char(void *view,const void *event) {
  struct ViewsField *f=find_views_field(view);
  uint16_t unit=((uint16_t (*)(const void *))(base+NXS_CHROMIUM_VIEWS_CHARACTER_OFFSET))(event);
  char *text=encode_text(&unit,1,0);
  int handled=f&&text&&views_key(f,event,NULL,0,text,1);free(text);
  if(!handled)original_views_insert_char(view,event);
}
static void views_insert_text(void *view,const void *string,int behavior) {
  struct ViewsField *f=find_views_field(view);const unsigned char *s=string;
  size_t length=(s[0]&1)?*(const size_t *)(s+8):s[0]>>1;
  const void *data=(s[0]&1)?*(const void *const *)(s+16):s+2;
  char *text=length<=65536?encode_text(data,length,0):NULL;
  int handled=f&&text&&views_key(f,NULL,string,behavior,text,0);free(text);
  if(!handled)original_views_insert_text(view,string,behavior);
}
static struct Detour views_detours[]={
 {NXS_CHROMIUM_VIEWS_ACCELERATOR_KEY_OFFSET,chromium_views_accelerator_key_bytes,views_accelerator_key,(void **)&original_views_accelerator_key},
 {NXS_CHROMIUM_VIEWS_OMNIBOX_PAINT_OFFSET,chromium_views_omnibox_paint_bytes,views_omnibox_paint,(void **)&original_views_omnibox_paint},
 {NXS_CHROMIUM_VIEWS_TEXT_PAINT_OFFSET,chromium_views_text_paint_bytes,views_text_paint,(void **)&original_views_text_paint},
 {NXS_CHROMIUM_VIEWS_BORDER_OFFSET,chromium_views_border_bytes,views_border,(void **)&original_views_border},
 {NXS_CHROMIUM_VIEWS_HAS_FOCUS_OFFSET,chromium_views_has_focus_bytes,views_has_focus,(void **)&original_views_has_focus},
 {NXS_CHROMIUM_VIEWS_CURSOR_OFFSET,chromium_views_cursor_bytes,views_cursor,(void **)&original_views_cursor},
 {NXS_CHROMIUM_VIEWS_FOCUS_OFFSET,chromium_views_focus_bytes,views_focus,(void **)&original_views_focus},
 {NXS_CHROMIUM_VIEWS_BLUR_OFFSET,chromium_views_blur_bytes,views_blur,(void **)&original_views_blur},
 {NXS_CHROMIUM_VIEWS_DESTROY_OFFSET,chromium_views_destroy_bytes,views_destroy,(void **)&original_views_destroy},
 {NXS_CHROMIUM_VIEWS_CONTROLLER_KEY_OFFSET,chromium_views_controller_key_bytes,views_controller_key,(void **)&original_views_controller_key},
 {NXS_CHROMIUM_VIEWS_INSERT_CHAR_OFFSET,chromium_views_insert_char_bytes,views_insert_char,(void **)&original_views_insert_char},
 {NXS_CHROMIUM_VIEWS_INSERT_TEXT_OFFSET,chromium_views_insert_text_bytes,views_insert_text,(void **)&original_views_insert_text}
};
