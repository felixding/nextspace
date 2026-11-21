/* Gecko's GTK NativeKeyBindings already supplies command arrays to the
 * editor. Delegate key matching to GNUstep and keep that dispatch intact. */
#include "../../Libraries/NativeUI/Bridge/EditBindings.inc"
#include "../../Libraries/NativeUI/Bridge/EditorActions.inc"
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
  if(browser_editor_keys&&capacity&&browser_editor_plan(response).count) {
    /* Gecko checks whether the focused editor has native commands before
     * reserving a shortcut for chrome. Register Command::DoNothing here.
     * The focused control's default handler applies the actual selectors. */
    commands[0]=0;
    return 1;
  }
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

static __thread char *gecko_killed_text;

static int gecko_editor_kind(void *node)
{
  uintptr_t table=*(const uintptr_t *)node;
  if(table==base+NXS_GECKO_TEXTAREA_VTABLE_OFFSET+16)return NXS_TEXTAREA;
  if(table!=base+0xa00fc30+16)return 0;
  unsigned kind=*((const unsigned char *)node+144);
  return kind==133||kind==142||kind==144||kind==147?NXS_TEXTFIELD:0;
}

static void gecko_center_selection(void *node)
{
  void *state=*(void **)((char *)node+304);
  void *controller=state?((void *(*)(void *))(base+NXS_GECKO_VIEWPORT_SELECTION_CONTROLLER_OFFSET))(state):NULL;
  void *selection=controller?((void *(*)(void *,short))(base+NXS_GECKO_VIEWPORT_SELECTION_GET_OFFSET))(controller,1):NULL;
  if(!selection)return;
  /* AxisScrollParams: Maybe<int16_t> percentage, auto alignment, when.
   * Center vertically, reveal horizontally only as needed. */
  union ScrollAxis {
    uint64_t value;
    struct {int16_t percent;uint8_t some,padding,automatic,padding2,when,padding3;} axis;
  };
  const union ScrollAxis vertical={.axis={.percent=50,.some=1}};
  const union ScrollAxis horizontal={.axis={.when=2}};
  ((uint32_t (*)(void *,short,uint64_t,uint64_t,unsigned,unsigned))
    (base+NXS_GECKO_VIEWPORT_SELECTION_SCROLL_OFFSET))(selection,1,vertical.value,horizontal.value,3,2);
}

static uint32_t gecko_insert(void *editor,const uint16_t *data,uint32_t length)
{
  struct GeckoString value={.data=data,.length=length,.flags=1};
  return ((uint32_t (*)(void *,const void *,void *))(base+NXS_GECKO_TEXT_INSERT_ACTION_OFFSET))(editor,&value,NULL);
}

static void gecko_transpose(void *node,int kind,void *editor)
{
  struct TextModel before={0};
  if(!text_model_as(node,kind,&before))return;
  if(before.editable&&before.start&&before.start==before.end) {
    uint32_t length=0;
    uint16_t *text=text_utf16(before.value,&length);
    if(text&&before.start<=length) {
      uint32_t right=before.start;
      if(right<length&&text[right]!='\n') {
        if(text[right]>=0xd800&&text[right]<=0xdbff&&right+1<length)right++;
        right++;
      }
      uint32_t middle=right-1;
      if(middle&&text[middle]>=0xdc00&&text[middle]<=0xdfff)middle--;
      if(middle&&text[middle-1]!='\n') {
        uint32_t left=middle-1;
        if(left&&text[left]>=0xdc00&&text[left]<=0xdfff)left--;
        uint16_t swapped[5]={0};
        memcpy(swapped,text+middle,(right-middle)*sizeof(*text));
        memcpy(swapped+right-middle,text+left,(middle-left)*sizeof(*text));
        if(text_selection_as(node,kind,left,right-left)) {
          gecko_insert(editor,swapped,right-left);
          struct TextModel after={0};
          if(text_model_as(node,kind,&after)&&after.start==left&&after.end==right&&
             !strcmp(before.value,after.value))
            text_selection_as(node,kind,before.start,0);
          free(after.value);
        }
      }
    }
    free(text);
  }
  free(before.value);
}

static int gecko_browser_editor_key(void *node,void *visitor)
{
  if(!browser_editor_keys)return 0;
  void *event=*(void **)((char *)visitor+8);
  int *status=(int *)((char *)visitor+24);
  if(*(const uint16_t *)((char *)event+18)!=4||*status==1)return 0;
  unsigned modifiers=widget_modifiers(event);
  if(!(modifiers&(NXS_CONTROL|NXS_ALT|NXS_SUPER))||
     !(*(const uint8_t *)((char *)event+48)&1)||
     (*(const uint8_t *)((char *)event+49)&2)||
     (*(const uint16_t *)((char *)event+144)&2)||text_modifier_event(event))return 0;
  void *manager=*(void **)(base+0xa439c38);
  int kind=gecko_editor_kind(node);
  if(!kind||!manager||node!=*(void **)((char *)manager+128)||!ensure_widget_lifetime())return 0;
  char *text=key_text(event);
  if(!text)return 0;
  NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.modifiers=modifiers,.text=text,.unmodified_text=text,
    .key=logical_key(*(const uint32_t *)((char *)event+200))};
  struct BrowserEditActions plan=browser_editor_actions((uintptr_t)node,&key);
  free(text);
  if(!plan.count)return 0;
  uintptr_t getter=kind==NXS_TEXTAREA?NXS_GECKO_MULTILINE_EDITOR_OFFSET:NXS_GECKO_TEXT_EDITOR_OFFSET;
  void *editor=((void *(*)(void *))(base+getter))(node);
  if(!editor)return 0;
  ((void (*)(void *))(base+NXS_GECKO_TEXT_EDITOR_ADDREF_OFFSET))(editor);
  *status=1;
  ((void (*)(void *,int,void *))(base+NXS_GECKO_TEXT_PREVENT_DEFAULT_OFFSET))(event,1,NULL);
  for(unsigned i=0;i<plan.count&&node==*(void **)((char *)manager+128);i++) {
    switch(plan.actions[i]) {
      case BrowserCenter:
        if(kind==NXS_TEXTAREA)gecko_center_selection(node);
        break;
      case BrowserKill: {
        struct TextModel before={0},after={0};
        if(text_model_as(node,kind,&before)&&before.editable&&
           !((uint32_t (*)(void *,short,short,void *))(base+NXS_GECKO_TEXT_DELETE_ACTION_OFFSET))(editor,6,1,NULL)&&
           text_model_as(node,kind,&after))
          browser_remember_kill(&gecko_killed_text,before.value,after.value,before.start);
        free(before.value);free(after.value);
        break;
      }
      case BrowserYank:
        if(gecko_killed_text) {
          uint32_t length=0;uint16_t *data=text_utf16(gecko_killed_text,&length);
          if(data)gecko_insert(editor,data,length);
          free(data);
        }
        break;
      case BrowserTranspose:
        gecko_transpose(node,kind,editor);
        break;
      case BrowserNewline:
        if(kind!=NXS_TEXTAREA||
           ((uint32_t (*)(void *,void *))(base+NXS_GECKO_MULTILINE_NEWLINE_OFFSET))(editor,NULL))
          i=plan.count;
        break;
      case BrowserBackward:
        ((void (*)(uint8_t,void *))(base+0x58c5a78))(4,node); /* cmd_charPrevious */
        break;
    }
  }
  ((void (*)(void *))(base+NXS_GECKO_TEXT_EDITOR_RELEASE_OFFSET))(editor);
  return 1;
}

static struct Detour gecko_browser_editor_detour={
  NXS_GECKO_MULTILINE_POST_OFFSET,gecko_multiline_post_bytes,textarea_post,(void **)&original_textarea_post
};
static int prepare_gecko_browser_editor(void)
{
  return widgets_enabled&&guard_text_calls()&&guard_text_commands()&&
    guard_multiline_calls()&&guard_viewport_calls()&&prepare_detours(&gecko_browser_editor_detour,1);
}
