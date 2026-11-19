/* Application command ownership through actual native menus/responders. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct Probe {NXSControl *control;int enabled,queries,executed,rejected;};
static int command(void *context,const char *selector,unsigned phase)
{
  struct Probe *p=context;
  if(strcmp(selector,"paste:")&&strcmp(selector,"undo:")&&strcmp(selector,"redo:"))return -1;
  assert(phase<=NXS_COMMAND_EXECUTE);
  assert(!nxs_control_destroy(p->control));
  assert(!nxs_control_command_filter(p->control,NULL,NULL));
  NXSTextModel model={.size=sizeof(model),.text="Reentrant",.editable=1};
  assert(!nxs_control_text_sync(p->control,&model));
  if(phase==NXS_COMMAND_VALIDATE){p->queries++;return p->enabled;}
  if(p->enabled)p->executed++;else p->rejected++;
  return p->enabled;
}
static void key(NXSControl *control,const char *text,unsigned modifiers)
{
  NXSKeyEvent event={.size=sizeof(event),.type=NXS_KEY_DOWN,.key=NXS_KEY_TEXT,
    .text=text,.unmodified_text=text,.modifiers=modifiers};
  assert(nxs_control_key(control,&event)==NXS_INPUT_HANDLED);
}
static void value(NXSControl *control,const char *expected)
{
  char data[64];NXSTextState state={.size=sizeof(state)};
  assert(nxs_control_text_get(control,data,sizeof(data),&state)==strlen(expected)+1);
  assert(!strcmp(data,expected));
}
int main(int argc,char **argv)
{
  if(argc>1&&!strcmp(argv[1],"--expect-no-command-filter")) {
    assert(!nxs_control_command_capabilities());assert(!nxs_control_command_filter(NULL,NULL,NULL));
    puts("{\"unsupported_command_filter_rejected\":true}");return 0;
  }
  assert(nxs_control_command_capabilities()==1);
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  for(int kind=NXS_TEXTFIELD;kind<=NXS_PASSWORD;kind++) {
    struct Probe p={.control=nxs_control_create(kind,NULL,NULL,NULL),.enabled=1};assert(p.control);
    NXSControlConfig config={.size=sizeof(config),.width=180,.height=24,.enabled=1};
    assert(nxs_control_sync(p.control,&config));
    NXSTextModel model={.size=sizeof(model),.text="Hello",.selection_start=1,.selection_length=2,.editable=1};
    assert(nxs_control_text_sync(p.control,&model));assert(nxs_control_focus(p.control,1));
    [[NSPasteboard generalPasteboard] declareTypes:@[] owner:nil];
    assert(![[[NSPasteboard generalPasteboard] types] count]);
    assert(nxs_control_command_filter(p.control,command,&p));key(p.control,"v",NXS_ALT);
    assert(p.queries>0&&p.executed==1);value(p.control,"Hello");
    assert(![[[NSPasteboard generalPasteboard] types] count]);
    p.enabled=0;key(p.control,"v",NXS_ALT);assert(p.executed==1);value(p.control,"Hello");
    /* Unclaimed native Copy retains its original validation and behavior. */
    key(p.control,"c",NXS_ALT);
    NSString *copied=[[NSPasteboard generalPasteboard] stringForType:NSStringPboardType];
    assert(kind==NXS_PASSWORD?!copied:[copied isEqual:@"el"]);
    /* Original NSWindow owns these responder actions. The external editor
     * owns its history, so the shared command binding must cover that target
     * as well as the first responder's clipboard actions. */
    p.enabled=1;p.executed=0;
    key(p.control,"z",NXS_ALT);assert(p.executed==1);value(p.control,"Hello");
    key(p.control,"Z",NXS_ALT|NXS_SHIFT);assert(p.executed==2);value(p.control,"Hello");
    assert(nxs_control_command_filter(p.control,NULL,NULL));
    model.selection_start=5;model.selection_length=0;assert(nxs_control_text_sync(p.control,&model));
    key(p.control,"X",0);value(p.control,"HelloX");assert(nxs_control_destroy(p.control));
  }
  [pool drain];puts("{\"native_controls\":2,\"empty_clipboard_command\":true,\"application_validation\":true,\"native_window_undo_redo_binding\":true,\"native_copy_fallback\":true,\"secure_copy_protected\":true,\"no_second_edit\":true,\"reentrant_mutation_deferred\":true,\"filter_removal\":true}");
  return 0;
}
