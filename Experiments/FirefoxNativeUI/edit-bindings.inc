/* Gecko's GTK NativeKeyBindings already supplies command arrays to the
 * editor. Delegate key matching to GNUstep and keep that dispatch intact. */
#include "../../Libraries/NativeUI/Bridge/EditBindings.inc"
#include "pinned-edit-commands.h"

struct GeckoEditArray {
  uint32_t length,capacity;
  uint8_t commands[];
};
static void (*original_gecko_edit_keys)(void *,const void *,const uint8_t *,struct GeckoEditArray **);

static int gecko_event_has_edit_commands(const void *event)
{
  /* These are the three arrays Gecko initializes on WidgetKeyboardEvent
   * for single-line, multiline and rich-text editors. */
  const struct GeckoEditArray *const *arrays=(const void *)((const char *)event+232);
  return arrays[0]->length||arrays[1]->length||arrays[2]->length;
}

static unsigned gecko_edit_command(const char *selector,int single_line)
{
  for(unsigned i=0;i<sizeof(gecko_edit_commands)/sizeof(*gecko_edit_commands);i++)
    if(!strcmp(selector,gecko_edit_commands[i].selector))
      return single_line?gecko_edit_commands[i].single_line:gecko_edit_commands[i].command;
  return 0;
}

static size_t gecko_edit_binding(void *self,const NXSKeyEvent *key,uint8_t *commands,size_t capacity)
{
  struct NXSResponse *response=native_edit_binding_request((uintptr_t)self,key);
  if(!response)return 0;
  if(response->parts[3].x==NXS_EDIT_SEQUENCE) {
    /* One physical key can request arrays for three Gecko editor types.
     * Until that boundary carries focus identity, keep sequences native to
     * Gecko rather than advancing the shared interpreter multiple times. */
    native_edit_binding_request((uintptr_t)self,NULL);
    return 0;
  }
  if(response->parts[3].x!=NXS_EDIT_COMMANDS||response->size<=sizeof(*response))return 0;
  const char *selector=(const char *)(response+1);
  const char *end=selector+response->size-sizeof(*response);
  size_t count=0;
  int single_line=self==*(void **)(base+0xa480620);
  while(selector<end&&count<capacity) {
    const char *next=memchr(selector,0,end-selector);
    if(!next)return 0;
    unsigned command=gecko_edit_command(selector,single_line);
    if(!command)return 0;
    commands[count++]=command;
    selector=next+1;
  }
  return selector==end?count:0;
}

static void gecko_edit_keys(void *self,const void *event,const uint8_t *writing_mode,struct GeckoEditArray **array)
{
  unsigned modifiers=widget_modifiers(event);
  if((modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))&&
     (*(const uint8_t *)((const char *)event+48)&1)&&
     !(*(const uint16_t *)((const char *)event+144)&2)&&
     *(void *const *)((const char *)event+192)&&
     !(writing_mode[1]&&(writing_mode[0]&1))&&
     !(*array)->length&&ensure_widget_lifetime()) {
    char *text=key_text(event);
    if(text) {
      NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.modifiers=modifiers,
        .key=logical_key(*(const uint32_t *)((const char *)event+200)),
        .repeat=!!*((const uint8_t *)event+223),.text=text,.unmodified_text=text};
      uint8_t commands[64];
      size_t count=gecko_edit_binding(self,&key,commands,sizeof(commands));
      free(text);
      if(count) {
        /* The original infallible nsTArray allocator owns storage. The same
         * command-array ABI is used by Gecko's GTK edit action callbacks. */
        ((void (*)(void *,size_t,size_t))(base+0x32ddeb0))(array,count,1);
        memcpy((*array)->commands,commands,count);
        (*array)->length=count;
        return;
      }
    }
  }
  original_gecko_edit_keys(self,event,writing_mode,array);
}

static const unsigned char gecko_edit_keys_bytes[20]={
  0x3f,0x23,0x03,0xd5,0xfe,0x0f,0x1b,0xf8,0xfa,0x67,
  0x01,0xa9,0xf8,0x5f,0x02,0xa9,0xf6,0x57,0x03,0xa9
};
static struct Detour gecko_edit_key_detour={
  0x6af905c,gecko_edit_keys_bytes,gecko_edit_keys,(void **)&original_gecko_edit_keys
};
static int prepare_gecko_edit_keys(void)
{
  static const unsigned char allocator[]={
    0x3f,0x23,0x03,0xd5,0xfe,0x0f,0x1c,0xf8,0xf8,0x5f,0x01,0xa9,
    0xf6,0x57,0x02,0xa9,0xf4,0x4f,0x03,0xa9
  };
  static const unsigned char single_line[]={0x28,0xcc,0x01,0xf0,0x08,0x11,0x43,0xf9,0x1f,0x01,0x16,0xeb};
  static const unsigned char names[]={
    0x5f,0x24,0x03,0xd5,0x08,0x1c,0x00,0x12,0x1f,0x39,
    0x02,0x71,0xe2,0x00,0x00,0x54,0x08,0x1c,0x40,0x92
  };
  if(memcmp((void *)(base+0x32ddeb0),allocator,sizeof(allocator))||
     memcmp((void *)(base+0x6af919c),single_line,sizeof(single_line))||
     memcmp((void *)(base+0x6a67864),names,sizeof(names)))return 0;
  const char *(*name)(uint8_t)=(void *)(base+0x6a67864);
  for(unsigned i=0;i<sizeof(gecko_edit_commands)/sizeof(*gecko_edit_commands);i++) {
    const char *actual=name(gecko_edit_commands[i].command);
    if(!actual||strcmp(actual,gecko_edit_commands[i].name))return 0;
  }
  return prepare_detours(&gecko_edit_key_detour,1);
}
