/* Application focus/model bindings. The separate provider interprets keys and
 * draws focus; this file implements no control or key-binding policy. */
#include "pinned-form-input.h"
_Static_assert(sizeof(struct NXSControlInputRequest)==56,"Control input wire ABI");
_Static_assert(offsetof(struct NXSControlInputRequest,reserved)==28,"Input sequence offset");
static void (*original_element_focus)(void *,int,int,int);
static void (*original_button_default)(void *,void *);
static void (*original_input_default)(void *,void *);
static int (*original_focus_ring)(void *,const void *,const void *);

static void *node_document(const void *node) {
  /* Node::GetDocument(): this build's TreeScope and Document references. */
  void *scope=*(void **)((const char *)node+24);
  return scope?*(void **)((char *)scope+8):NULL;
}
static int form_focused(const void *node) {
  if(!(*(const unsigned char *)((const char *)node+21)&1))return 0;
  void *document=node_document(node);
  /* Call Chromium's UserActionElementSet::HasFlags(kIsFocused). */
  return document&&((int (*)(const void *,const void *,unsigned))(base+0xdd7ef18))((char *)document+1496,node,8);
}
static int input_form_kind(void *node) {
  uintptr_t table=*(const uintptr_t *)node;
  if(forms_popups_enabled&&popup_element(node))return component_native_kind(node)?component_native_kind(node):NXS_POPUP;
  if(!forms_available)return 0;
  if(forms_numbers_enabled&&number_owner(node))return NXS_STEPPER;
  if(table==base+0x11cf3500+16)return NXS_BUTTON;
  if(forms_lists_enabled&&list_element(node))return NXS_LISTBOX;
  if(forms_multiline_enabled&&table==base+NXS_TEXTAREA_VTABLE_OFFSET+16)return NXS_TEXTAREA;
  if(table!=base+0x11dc01d8+16)return 0;
  const void *atom=((const void *(*)(const void *))(base+0xefa0da4))(node);
  char *type=atom?string_text(*(void *const *)atom):NULL;
  if(!type)return 0;
  int kind=!strcmp(type,"checkbox")?NXS_CHECKBOX:!strcmp(type,"radio")?NXS_RADIO:
    (forms_sliders_enabled&&!strcmp(type,"range"))?NXS_SLIDER:
    (forms_color_enabled&&!strcmp(type,"color"))?NXS_COLORWELL:
    (forms_search_enabled&&!strcmp(type,"search"))?NXS_SEARCHFIELD:
    (forms_numbers_enabled&&!strcmp(type,"number"))?NXS_TEXTFIELD:
    ((forms_dates_enabled&&!strcmp(type,"date"))||(forms_times_enabled&&(!strcmp(type,"time")||!strcmp(type,"datetime-local"))))?NXS_DATEPICKER:
    (forms_months_enabled&&!strcmp(type,"month"))?NXS_DATEPICKER:
    (forms_weeks_enabled&&!strcmp(type,"week"))?NXS_DATEPICKER:
    (forms_text_enabled&&(!strcmp(type,"text")||!strcmp(type,"url")||!strcmp(type,"tel")||!strcmp(type,"email")))?NXS_TEXTFIELD:
    (forms_text_enabled&&!strcmp(type,"password"))?NXS_PASSWORD:
    (!strcmp(type,"button")||!strcmp(type,"submit")||!strcmp(type,"reset"))?NXS_BUTTON:0;
  free(type);return kind;
}
static struct NativeForm *bind_input_form(void *node) {
  struct NativeForm *form=find_form(node);if(form)return form;
  int kind=input_form_kind(node);
  if(kind==NXS_LISTBOX||kind==NXS_TEXTAREA)return NULL; /* These controls bind through theme paint. */
  if(!kind||!decode_member((const char *)node+48))return NULL;
  if(text_kind(kind)&&!native_layout_appearance(node,decode_member((const char *)node+48),kind==NXS_SEARCHFIELD?11:12))return NULL;
  /* Keyboard focus can precede the first paint. Use the engine's layout box
   * and semantic control type to create the native object at that boundary. */
  struct FloatRect box=((struct FloatRect (*)(const void *))(base+0xef58ad4))(node);
  if(!isfinite(box.width)||!isfinite(box.height)||box.width<1||box.height<1||box.width>8192||box.height>8192)return NULL;
  char *title=kind==NXS_BUTTON?form_title(node):strdup("");if(!title)return NULL;
  form=calloc(1,sizeof(*form));if(!form){free(title);return NULL;}
  form->node=node;form->control=++next_form_control;form->kind=kind;form->title=title;form->input_owned=1;
  form->rect=(struct Rect){lroundf(box.x),lroundf(box.y),lroundf(box.width),lroundf(box.height)};
  form->enabled=form_enabled(node);form->state=form_state(node,kind);
  if(kind==NXS_SLIDER&&!sync_slider_model(form)){free(form->title);free(form);return NULL;}
  form->next=native_forms;native_forms=form;
  if(kind==NXS_WEBUI_MENU)return form;
  if(log_fd>=0)dprintf(log_fd,"%d native form bound before paint id=%llu kind=%d\n",getpid(),(unsigned long long)form->control,kind);
  struct NXSResponse *response=form_request(form,1,0,0,0);
  if(kind==NXS_POPUP)response=sync_popup_model(form,response);
  if(text_kind(kind)) {
    response=sync_text_form(form,response);
    if(response)form->generation=response->parts[4].x;
    if(!response||!refresh_form_watch())form->input_owned=0;
  }
  return form;
}
static struct NXSResponse *form_input_request(struct NativeForm *form,int operation,int focus,
    int type,unsigned logical,const char *text,const char *unmodified,unsigned modifiers,int repeat) {
  if(form->kind==NXS_WEBUI_MENU) {
    NXSKeyEvent key={.size=sizeof(key),.type=type,.key=logical,.text=text,.unmodified_text=unmodified,.modifiers=modifiers,.repeat=repeat};
    return operation==8?component_menu_key(form,&key):component_menu_request(form,5);
  }
  if(form->kind==NXS_LISTBOX){NXSKeyEvent key={.size=sizeof(key),.type=type,.key=logical,.text=text,.unmodified_text=unmodified,.modifiers=modifiers,.repeat=repeat};struct NXSResponse *r=native_list_input(form->control,focus,operation==8?&key:NULL);if(r&&operation==7){native_list_binding_snapshot(&form->list,r);form->list.focused=!!focus;}return r;}
  if(form->kind==NXS_RADIO&&forms_radio_groups_enabled&&operation==7)return radio_form_focus(form);
  size_t a=text?strlen(text):0,b=unmodified?strlen(unmodified):0;
  if(a+b>65536)return NULL;
  size_t size=sizeof(struct NXSControlInputRequest)+a+b;
  struct NXSControlInputRequest *req=calloc(1,size);if(!req)return NULL;
  *req=(struct NXSControlInputRequest){.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=operation,
    .process=identity(),.kind=form->kind,.control=form->control,.text_size=a,
    .type=type,.modifiers=modifiers,.key=logical,.repeat=repeat,.unmodified_size=b,.focused=focus};
  if(a)memcpy(req+1,text,a);
  if(b)memcpy((char *)(req+1)+a,unmodified,b);
  struct NXSResponse *response=exchange_bytes(req,size);free(req);return response;
}
static struct NXSResponse *sync_form_focus(struct NativeForm *form,struct NXSResponse *response) {
  if(form->kind==NXS_WEBUI_MENU||form->kind==NXS_LISTBOX||(form->kind==NXS_RADIO&&forms_radio_groups_enabled))return response;
  if(!forms_input_enabled||!(forms_input_capabilities&NXS_INPUT_FOCUS)||!response)return response;
  int focus=form_focused(form->node);
  if(!!response->parts[3].y==focus)return response;
  form_input_request(form,7,focus,0,0,NULL,NULL,0,0);
  return form_request(form,1,0,0,0);
}
static void element_focus(void *node,int focused,int type,int blur) {
  original_element_focus(node,focused,type,blur);
  struct NativeForm *form=find_form(node);
  if(!form&&form_focused(node))form=bind_input_form(node);
  if(form&&form->kind!=NXS_PROGRESS&&(form->painted||form->input_owned)) {
    if(form->text_tracking&&!form_focused(node))end_text_pointer(form,0);
    form_input_request(form,7,form_focused(node),0,0,NULL,NULL,0,0);
    invalidate_form(form);
  }
}
static int focus_ring(void *self,const void *node,const void *style) {
  struct NativeForm *form=find_form(node);
  if(form&&form->kind!=NXS_PROGRESS&&form->painted)return 0; /* NativeUI draws this control's own focus. */
  return original_focus_ring(self,node,style);
}
static unsigned logical_key(const char *key) {
  static const struct {const char *name;unsigned key;} names[]={
    {"Enter",NXS_KEY_ENTER},{"Tab",NXS_KEY_TAB},{"Backspace",NXS_KEY_BACKSPACE},
    {"Delete",NXS_KEY_DELETE},{"Escape",NXS_KEY_ESCAPE},{"ArrowLeft",NXS_KEY_LEFT},
    {"ArrowRight",NXS_KEY_RIGHT},{"ArrowUp",NXS_KEY_UP_ARROW},{"ArrowDown",NXS_KEY_DOWN_ARROW},
    {"Home",NXS_KEY_HOME},{"End",NXS_KEY_END},{"PageUp",NXS_KEY_PAGE_UP},
    {"PageDown",NXS_KEY_PAGE_DOWN},{"Insert",NXS_KEY_INSERT}
  };
  for(unsigned i=0;i<sizeof(names)/sizeof(*names);i++)if(!strcmp(key,names[i].name))return names[i].key;
  unsigned number;char extra;
  if(sscanf(key,"F%u%c",&number,&extra)==1&&number>=1&&number<=24)return NXS_KEY_F1+number-1;
  return NXS_KEY_TEXT;
}
static int advance_form_focus(void *node,const void *event,int direction) {
  void *document=node_document(node);
  void *window=document?decode_member((char *)document+264):NULL;
  void *frame=window?decode_member((char *)window+32):NULL;
  void *page=frame?decode_member((char *)frame+32):NULL;
  void *controller=page?decode_member((char *)page+88):NULL;
  if(!controller)return 0;
  void *capabilities=decode_member((const char *)event+104);
  /* Use the engine's real document/frame focus traversal, including tabindex
   * and disabled controls. NEXT/PREVIOUS was chosen by the native responder. */
  return ((int (*)(void *,int,int,void *))(base+0xe76403c))(controller,
    direction==NXS_INPUT_NEXT?2:3,0,capabilities);
}
static char *keyboard_text(const void *web,int offset,const char *fallback) {
  const uint16_t *units=(const uint16_t *)((const char *)web+offset);
  unsigned count=0;while(count<4&&units[count])count++;
  return count?encode_text(units,count,0):strdup(fallback);
}
static int default_form_key(void *node,void *event) {
  if(!forms_input_enabled||!(forms_input_capabilities&NXS_INPUT_KEYBOARD))return 0;
  struct NativeForm *text_form=find_form(node);
  if(text_form&&text_form->kind==NXS_COLORWELL)return 0;
  if(text_form&&text_form->kind==NXS_DATEPICKER)return date_default_key(node,event);
  if(text_form&&text_kind(text_form->kind))return default_text_key(node,event);
  unsigned short *flags=(unsigned short *)((char *)event+32);
  if(!(*flags&0x100)||(*flags&0x60))return 0;
  uintptr_t atom=*(const uintptr_t *)((char *)event+24);
  int down=same_atom(atom,0x123a55d8),up=same_atom(atom,0x123a55e8),press=same_atom(atom,0x123a55e0);
  if(!down&&!up&&!press)return 0;
  struct NativeForm *form=find_form(node);
  if(form_key_node==node&&form_key_event==event&&(!form||form->control!=form_key_control)) {
    *flags|=0x40;return 1;
  }
  if(!form||(!form->painted&&!form->input_owned)) {
    /* DOM handlers may detach or replace the control before default handling.
     * Keep ownership of that cancelled gesture instead of invoking Blink's
     * old widget implementation on the removed object. */
    if(form_key_node==node&&form_key_event==event){*flags|=0x40;return 1;}
    return 0;
  }
  /* Char events are already represented by the native key down/up stream. */
  if(press){*flags|=0x40;return 1;}
  if(!form_enabled(node)){*flags|=0x40;return 1;}
  if(*(const unsigned char *)((char *)event+140))return 1; /* IME contract remains open. */
  char *key=string_text(*(void **)((char *)event+128));
  if(!key){*flags|=0x40;return 1;}
  void *web=*(void **)((char *)event+112);
  if(!web){free(key);*flags|=0x40;return 1;}
  unsigned modifiers=event_modifiers(web);
  unsigned logical=logical_key(key);
  int modifier=!strcmp(key,"Shift")||!strcmp(key,"Control")||!strcmp(key,"Alt")||!strcmp(key,"Meta");
  char *text=keyboard_text(web,102,key),*unmodified=keyboard_text(web,110,key);
  free(key);
  if(!text||!unmodified){free(text);free(unmodified);*flags|=0x40;return 1;}
  if(form->kind==NXS_LISTBOX){int handled=list_key_input(form,event,modifier?NXS_KEY_MODIFIERS:down?NXS_KEY_DOWN:NXS_KEY_UP,modifier?NXS_KEY_TEXT:logical,modifier?"":text,modifier?"":unmodified,modifiers,!!(*(const unsigned *)((char *)event+108)&(1u<<5)));free(text);free(unmodified);return handled;}
  if(form->kind==NXS_RADIO&&forms_radio_groups_enabled) {
    int handled=radio_key_input(form,event,modifier?NXS_KEY_MODIFIERS:down?NXS_KEY_DOWN:NXS_KEY_UP,
      modifier?NXS_KEY_TEXT:logical,modifier?"":text,modifier?"":unmodified,modifiers,
      !!(*(const unsigned *)((char *)event+108)&(1u<<5)));
    free(text);free(unmodified);return handled;
  }
  form->enabled=1;form->state=form_state(node,form->kind);
  if(form->kind==NXS_SLIDER&&!sync_slider_model(form)){free(text);free(unmodified);*flags|=0x40;return 1;}
  struct NXSResponse *response=sync_form_focus(form,form_request(form,1,0,0,0));
  double before=response?response->parts[0].width:0;
  if(response)response=form_input_request(form,8,0,modifier?NXS_KEY_MODIFIERS:down?NXS_KEY_DOWN:NXS_KEY_UP,
    modifier?NXS_KEY_TEXT:logical,modifier?"":text,modifier?"":unmodified,modifiers,
    !!(*(const unsigned *)((char *)event+108)&(1u<<5)));
  free(text);free(unmodified);
  if(!response){*flags|=0x40;note("native keyboard transport unavailable; action cancelled");return 1;}
  int result=response->parts[3].x,action=response->parts[0].width>before;
  if(form->kind==NXS_WEBUI_MENU) {
    if(result!=NXS_INPUT_UNHANDLED||up)*flags|=0x40;
    return 1;
  }
  if(form->kind==NXS_TABVIEW||form->kind==NXS_OUTLINE) {
    if(result==NXS_INPUT_NEXT||result==NXS_INPUT_PREVIOUS)advance_form_focus(node,event,result);
    if(result!=NXS_INPUT_UNHANDLED||action||up)*flags|=0x40;
    if(form->kind==NXS_OUTLINE)component_outline_after_input(form);else component_tabs_after_input(form);return 1;
  }
  struct NXSControlAction checkbox_action;native_control_action_snapshot(response,before,&checkbox_action);
  invalidate_form(form);
  if(form->kind==NXS_POPUP){
    if(result==NXS_INPUT_NEXT||result==NXS_INPUT_PREVIOUS)advance_form_focus(node,event,result);
    if(result!=NXS_INPUT_UNHANDLED||action||up)*flags|=0x40;
    popup_after_input(form,response);return 1;
  }
  if(result==NXS_INPUT_NEXT||result==NXS_INPUT_PREVIOUS) {
    advance_form_focus(node,event,result);*flags|=0x40;
  } else if(result==NXS_INPUT_HANDLED||action||up)*flags|=0x40;
  if(action) {
    /* Native action, real trusted application activation. Chrome retains
     * preactivation, event cancellation, form submission and model rollback. */
    if(form->kind==NXS_SLIDER)apply_slider_value(form,response,3);
    else {
      struct NXSCheckboxActivation previous=native_checkbox_activation;
      if(form->kind==NXS_CHECKBOX)native_checkbox_enter(radio_node_id(node),form->control,checkbox_action);
      ((void (*)(void *,const void *,int))(base+0xdd1402c))(node,event,1);
      native_checkbox_activation=previous;
    }
    *flags|=0x40;
    note("native keyboard action applied");
  }
  return 1; /* Never run a second widget's default keyboard handler. */
}
static void button_default(void *node,void *event)
{if(!default_form_key(node,event))original_button_default(node,event);}
static void input_default(void *node,void *event)
{if(!slider_mouse_default(node,event)&&!default_form_key(node,event))color_input_default(node,event);}
static struct Detour form_input_detours[]={
 {NXS_ELEMENT_FOCUS_OFFSET,nxs_element_focus_bytes,element_focus,(void **)&original_element_focus},
 {NXS_BUTTON_DEFAULT_OFFSET,nxs_button_default_bytes,button_default,(void **)&original_button_default},
 {NXS_INPUT_DEFAULT_OFFSET,nxs_input_default_bytes,input_default,(void **)&original_input_default},
 {NXS_FOCUS_RING_OFFSET,nxs_focus_ring_bytes,focus_ring,(void **)&original_focus_ring}
};
static int prepare_form_input(void){return prepare_detours(form_input_detours,sizeof(form_input_detours)/sizeof(*form_input_detours));}
static void activate_form_input(void){activate_detours(form_input_detours,sizeof(form_input_detours)/sizeof(*form_input_detours));}
