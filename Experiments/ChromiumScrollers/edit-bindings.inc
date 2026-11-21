/* GTK's existing LinuxUi command boundary feeds the stock Chromium editor.
 * GNUstep supplies only command selection. GPL-2.0-or-later. */
#include "../../Libraries/NativeUI/Bridge/EditBindings.inc"
#include "../../Libraries/NativeUI/Bridge/EditorActions.inc"
#include "pinned-edit-commands.h"

static int (*original_linux_edit_key)(void *,const void *,int);

static int chromium_edit_command(const char *selector)
{
  if(!strcmp(selector,"pageDown:"))selector="movePageDown:";
  else if(!strcmp(selector,"pageUp:"))selector="movePageUp:";
  for(int i=0;i<CHROMIUM_EDIT_INVALID;i++)
    if(!strcmp(selector,chromium_edit_selectors[i]))return i;
  return CHROMIUM_EDIT_INVALID;
}

static __thread char *blink_killed_text;

static int blink_editor_transport_ready(void)
{
  /* Renderer text controls keep their original UI, so there may be no
   * native form watching for paint invalidations in this process. Register
   * it with the same checked lifetime protocol before resolving a key. */
  static __thread uint32_t owner;
  static __thread int descriptor=-1;
  uint32_t process=identity();
  if(form_watch.wake_fd>=0)return 1;
  if(owner==process&&descriptor>=0)return 1;
  if(descriptor>=0)close(descriptor);
  owner=process;
  descriptor=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);
  if(descriptor<0)return 0;
  struct NXSControlRequest request={.magic=NXS_CHROMIUM_CONTROL_MAGIC,.operation=15,.process=process};
  struct NXSResponse *response=exchange_bytes_descriptor(&request,sizeof(request),descriptor);
  if(response&&response->parts[3].x==1)return 1;
  close(descriptor);descriptor=-1;
  return 0;
}

static int browser_edit_key_preflight(void *view,const void *event)
{
  if(!browser_editor_keys||!(views_modifiers(event)&(NXS_CONTROL|NXS_ALT|NXS_SUPER))||
     (*(const unsigned *)((const char *)event+80)&((1u<<6)|(1u<<16)))||!native_form_events_ready())
    return 0;
  NXSKeyEvent key=chromium_key_event(event);
  int deferred=key.text&&key.unmodified_text&&browser_editor_actions((uintptr_t)view,&key).count;
  chromium_key_event_free(key);
  return deferred;
}

static int blink_execute_edit(void *frame,void *event,const char *command,const char *text)
{
  void *(*string)(const char *,size_t)=(void *)(base+NXS_CHROMIUM_TEXT_FROM_UTF8_OFFSET);
  void (*destroy)(void *)=(void *)(base+NXS_CHROMIUM_TEXT_STRING_DESTROY_OFFSET);
  void *name=string(command,strlen(command)),*value=text?string(text,strlen(text)):NULL;
  struct BlinkEditorCommand action={
    .command=((void *(*)(const void *))(base+NXS_CHROMIUM_TEXT_COMMAND_OFFSET))(&name),
    .source=0,.frame=frame};
  int handled=action.command&&((int (*)(const void *,const void *,void *))
    (base+NXS_CHROMIUM_TEXT_EXECUTE_OFFSET))(&action,&value,event);
  destroy(&value);destroy(&name);
  return handled;
}

static int blink_text_input(void *node)
{
  const void *atom=((const void *(*)(const void *))(base+0xefa0da4))(node);
  char *type=atom?string_text(*(void *const *)atom):NULL;
  int kind=type&&(!strcmp(type,"text")||!strcmp(type,"search")||
                 !strcmp(type,"url")||!strcmp(type,"tel"))?NXS_TEXTFIELD:0;
  free(type);return kind;
}

static void blink_center_selection(void *frame)
{
  /* Same scroll alignment and extent as WebLocalFrameImpl::CenterSelection.
   * FrameSelection also handles collapsed selections in text controls. */
  static const int center_always[]={1,1,1};
  void *selection=decode_member((const char *)frame+588);
  if(selection)((void (*)(void *,const void *,int))(base+0xde0345c))(selection,center_always,1);
}

static int browser_text_default(void *node,void *event,int multiline)
{
  if(!browser_editor_keys||forms_text_enabled||context_menu_owns_keys())return 0;
  unsigned short *flags=(unsigned short *)((char *)event+32);
  if(!(*flags&0x100)||(*flags&0x60)||
     !same_atom(*(const uintptr_t *)((char *)event+24),0x123a55d8)||
     *(const unsigned char *)((char *)event+140)||!form_focused(node))return 0;
  const void *web=*(void *const *)((const char *)event+112);
  unsigned modifiers=web?event_modifiers(web):0;
  if(!(modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))||!blink_editor_transport_ready())return 0;
  int kind=multiline?NXS_TEXTAREA:blink_text_input(node);
  if(!kind)return 0;
  char *text=string_text(*(void **)((char *)event+128));
  if(!text)return 0;
  NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.modifiers=modifiers,
    .key=logical_key(text),.text=text,.unmodified_text=text};
  struct BrowserEditActions plan=browser_editor_actions((uintptr_t)node,&key);
  free(text);
  if(!plan.count)return 0;
  void *frame=text_frame(node);
  if(!frame)return 0;
  *flags|=0x40;
  for(unsigned i=0;i<plan.count&&form_focused(node)&&text_frame(node)==frame;i++) {
    switch(plan.actions[i]) {
      case BrowserCenter:
        if(multiline)blink_center_selection(frame);
        break;
      case BrowserKill: {
        struct BlinkTextModel before={0},after={0};
        if(text_model_as(node,kind,&before)&&before.editable&&
           blink_execute_edit(frame,event,"DeleteToEndOfLine",NULL)&&
           text_frame(node)==frame&&text_model_as(node,kind,&after))
          browser_remember_kill(&blink_killed_text,before.value,after.value,before.start);
        free(before.value);free(after.value);
        break;
      }
      case BrowserYank:
        if(blink_killed_text)blink_execute_edit(frame,event,"InsertText",blink_killed_text);
        break;
      case BrowserTranspose:
        blink_execute_edit(frame,event,"Transpose",NULL);
        break;
      case BrowserNewline:
        if(!multiline||!blink_execute_edit(frame,event,"InsertNewline",NULL))return 1;
        break;
      case BrowserBackward:
        blink_execute_edit(frame,event,"MoveBackward",NULL);
        break;
    }
  }
  return 1;
}

static struct Detour blink_browser_editor_detours[]={
  {NXS_TEXTAREA_DEFAULT_OFFSET,nxs_textarea_default_bytes,textarea_default,(void **)&original_textarea_default},
  {NXS_INPUT_DEFAULT_OFFSET,nxs_input_default_bytes,input_default,(void **)&original_input_default},
};
static int prepare_blink_browser_editor(void)
{
  static const unsigned char reveal[]={0x3f,0x23,0x03,0xd5,0xff,0xc3,0x01,0xd1,0xfd,0x7b,0x03,0xa9};
  if(forms_text_enabled)return 0;
  return !memcmp((void *)(base+0xde0345c),reveal,sizeof(reveal))&&guard_text_calls()&&
    !memcmp((void *)(base+NXS_TEXTAREA_VALUE_OFFSET),nxs_textarea_value_bytes,20)&&
    prepare_detours(blink_browser_editor_detours,forms_input_enabled?1:2);
}

static int linux_edit_key(void *self,const void *event,int flags)
{
  unsigned key_flags=*(const unsigned *)((const char *)event+80);
  /* Keep the existing handling of AltGr, IME keys and vertical writing. */
  if(*(const int *)((const char *)event+8)!=7||
     !(views_modifiers(event)&(NXS_CONTROL|NXS_ALT|NXS_SUPER))||
     (key_flags&((1u<<6)|(1u<<16)))||(flags&(1u<<13))||
     context_menu_owns_keys()||!native_form_events_ready())
    return original_linux_edit_key(self,event,flags);

  NXSKeyEvent key=chromium_key_event(event);
  struct NXSResponse *response=key.text&&key.unmodified_text?
    native_edit_binding_request((uintptr_t)self,&key):NULL;
  chromium_key_event_free(key);
  if(response&&response->parts[3].x==NXS_EDIT_SEQUENCE) {
    /* LinuxUi returns a single command. Preserve Chromium's stock handling
     * for sequences that this boundary cannot deliver atomically. */
    native_edit_binding_request((uintptr_t)self,NULL);
  } else if(response&&response->parts[3].x==NXS_EDIT_COMMANDS&&response->size>sizeof(*response)) {
    const char *selector=(const char *)(response+1);
    size_t length=response->size-sizeof(*response);
    if(memchr(selector,0,length)==selector+length-1) {
      int command=chromium_edit_command(selector);
      if(command!=CHROMIUM_EDIT_INVALID)return command;
    }
  }
  return original_linux_edit_key(self,event,flags);
}

/* Actual GTK implementation reached through LinuxUi's virtual edit method. */
static const unsigned char linux_edit_key_bytes[20]={
  0x3f,0x23,0x03,0xd5,0xfd,0x7b,0xbd,0xa9,0xf4,0x4f,
  0x02,0xa9,0xf3,0x03,0x01,0xaa,0xf4,0x03,0x00,0xaa
};
static struct Detour linux_edit_key_detour={
  0x10e60104,linux_edit_key_bytes,linux_edit_key,(void **)&original_linux_edit_key
};
