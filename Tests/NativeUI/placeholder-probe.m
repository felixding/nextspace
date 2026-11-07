/* Original native field placeholders, with independent desktop references.
 * GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <objc/runtime.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <poll.h>
#include <unistd.h>
_Static_assert(offsetof(NXSNativeUIAPI,control_text_placeholder)==592,"Preserve provider prefix");
static IMP original_init;
static NSTextField *observed;
static unsigned checks,images,actions,busy_rejections;
static id witness_init(id self,SEL selector,NSRect frame)
{id result=((id (*)(id,SEL,NSRect))original_init)(self,selector,frame);observed=result;return result;}
static void check(const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);checks++;}
static void changed(void *context,int event,const NXSControlState *state)
{
  assert(event==NXS_TEXT_CHANGED||event==NXS_ACTIVATE);
  if(event==NXS_TEXT_CHANGED)actions++;
  if(state->tracking){assert(!nxs_control_text_placeholder(*(NXSControl **)context,"Busy"));busy_rejections++;}
}
static void compare(NXSControl *control,Class klass,const char *directory,const char *name,
                    const char *placeholder,const char *value,int enabled,int editable,double scale)
{
  NSTextField *reference=[[klass alloc] initWithFrame:NSMakeRect(0,0,260,24)];
  [[reference cell] setPlaceholderString:placeholder?[NSString stringWithUTF8String:placeholder]:nil];
  [reference setStringValue:[NSString stringWithUTF8String:value]];
  [reference setEnabled:enabled];[reference setEditable:editable];
  NSWindow *window=[[NSWindow alloc] initWithContentRect:[reference bounds] styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setReleasedWhenClosed:NO];[[window contentView] addSubview:reference];
  [window setTitle:[NSString stringWithFormat:@"Native placeholder reference %s",name]];
  [window orderFront:nil];[window display];
  NXSBitmap bitmap=nxs_control_draw(control,scale);assert(bitmap.pixels);
  char path[1024];snprintf(path,sizeof(path),"%s/%s-native.argb",directory,name);
  FILE *file=fopen(path,"wb");assert(file&&fwrite(bitmap.pixels,bitmap.stride,bitmap.height,file)==(size_t)bitmap.height);fclose(file);
  printf("{\"event\":\"reference\",\"pid\":%d,\"name\":\"%s\",\"pixel_width\":%d,\"pixel_height\":%d,\"stride\":%d}\n",getpid(),name,bitmap.width,bitmap.height,bitmap.stride);fflush(stdout);
  struct pollfd input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));images++;
  [window close];[window release];[reference release];
}
int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(argc>1&&!strcmp(argv[1],"--expect-no-placeholder")) {
    assert(!(nxs_control_text_capabilities()&NXS_TEXT_PLACEHOLDER));
    NXSControl *control=nxs_control_create(NXS_TEXTFIELD,NULL,NULL,NULL);assert(control);
    assert(!nxs_control_text_placeholder(control,"Unsupported")&&!nxs_control_text_placeholder(control,NULL));
    assert(nxs_control_destroy(control));puts("{\"older_provider_without_placeholder\":true}");[pool drain];return 0;
  }
  assert(argc>2);double scale=atof(argv[2]);
  check("placeholder-capability",!!(nxs_control_text_capabilities()&NXS_TEXT_PLACEHOLDER));
  int kinds[]={NXS_TEXTFIELD,NXS_PASSWORD,NXS_SEARCHFIELD};
  Class classes[]={[NSTextField class],[NSSecureTextField class],[NSSearchField class]};
  for(unsigned i=0;i<3;i++) {
    actions=busy_rejections=0;
    Method init=class_getInstanceMethod(classes[i],@selector(initWithFrame:));
    original_init=method_getImplementation(init);
    class_replaceMethod(classes[i],@selector(initWithFrame:),(IMP)witness_init,method_getTypeEncoding(init));
    NXSControl *control=NULL;control=nxs_control_create(kinds[i],changed,NULL,&control);assert(control);
    NSTextField *actual=observed;
    class_replaceMethod(classes[i],@selector(initWithFrame:),original_init,method_getTypeEncoding(init));
    check("unchanged-original-native-class",[actual class]==classes[i]);
    struct {const char *label,*placeholder,*value;int enabled,editable;} cases[]={
      {"ascii","Find a word","",1,1},{"unicode","検索α","",1,1},
      {"value","Hidden while populated","Existing",1,1},{"empty","","",1,1},
      {"removed",NULL,"",1,1},{"disabled","Unavailable","",0,1},
      {"readonly","Read only hint","",1,0},{"restored","Restored hint","",1,1}};
    for(unsigned n=0;n<sizeof(cases)/sizeof(*cases);n++) {
      NXSControlConfig config={.size=sizeof(config),.width=260,.height=24,.enabled=cases[n].enabled};
      NXSTextModel model={.size=sizeof(model),.text=cases[n].value,.selection_start=0,.editable=cases[n].editable};
      assert(nxs_control_sync(control,&config)&&nxs_control_text_sync(control,&model));
      assert(nxs_control_text_placeholder(control,cases[n].placeholder));
      NSString *expected=cases[n].placeholder?[NSString stringWithUTF8String:cases[n].placeholder]:nil;
      check("original-cell-placeholder",[[[actual cell] placeholderString] isEqual:expected]||(!expected&&![[actual cell] placeholderString]));
      check("invalid-utf8-is-atomic",!nxs_control_text_placeholder(control,"\xff")&&
        ([[[actual cell] placeholderString] isEqual:expected]||(!expected&&![[actual cell] placeholderString])));
      NXSTextState state={.size=sizeof(state)};char buffer[64];
      assert(nxs_control_text_get(control,buffer,sizeof(buffer),&state));
      check("placeholder-preserves-value-selection-editability",!strcmp(buffer,cases[n].value)&&!state.selection_start&&!state.selection_length&&state.editable==cases[n].editable&&!actions);
      char name[64];snprintf(name,sizeof(name),"kind-%d-%s",kinds[i],cases[n].label);
      compare(control,classes[i],argv[1],name,cases[n].placeholder,cases[n].value,cases[n].enabled,cases[n].editable,scale);
    }
    assert(nxs_control_focus(control,1));
    NXSTextState before={.size=sizeof(before)},after={.size=sizeof(after)};char buffer[64];
    assert(nxs_control_text_get(control,buffer,sizeof(buffer),&before));
    assert(nxs_control_text_placeholder(control,"Focused update"));
    assert(nxs_control_text_get(control,buffer,sizeof(buffer),&after));
    check("focused-placeholder-preserves-editor-selection",before.editing&&after.editing&&before.selection_start==after.selection_start&&before.selection_length==after.selection_length&&!actions);
    NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.key=NXS_KEY_TEXT,.text="x",.unmodified_text="x"};
    assert(nxs_control_key(control,&key)==NXS_INPUT_HANDLED);
    assert(nxs_control_text_get(control,buffer,sizeof(buffer),&after));
    check("native-edit-rejects-placeholder-reentry",actions==1&&busy_rejections&&!strcmp(buffer,"x")&&[[[actual cell] placeholderString] isEqualToString:@"Focused update"]);
    assert(nxs_control_focus(control,0)&&nxs_control_destroy(control));
  }
  NXSControl *multiline=nxs_control_create(NXS_TEXTAREA,NULL,NULL,NULL);assert(multiline);
  check("unsupported-controls-reject-placeholder",!nxs_control_text_placeholder(NULL,"Invalid")&&!nxs_control_text_placeholder(multiline,"Unsupported"));
  assert(nxs_control_destroy(multiline));
  printf("{\"passed\":%u,\"images\":%u,\"api_bytes\":%zu}\n",checks,images,sizeof(NXSNativeUIAPI));
  [pool drain];return 0;
}
