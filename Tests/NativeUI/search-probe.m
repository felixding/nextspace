/* Compare the shared binding with the original NSSearchField class and cell.
 * GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <objc/runtime.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
_Static_assert(offsetof(NXSNativeUIAPI,control_search_part)==584,"Preserve the existing provider prefix");
static IMP original_init;
static NSSearchField *observed;
static id witness_init(id self,SEL selector,NSRect frame)
{id result=((id (*)(id,SEL,NSRect))original_init)(self,selector,frame);observed=result;return result;}
static IMP original_perform;
static int original_clear_rects;
static void witness_perform(id self,SEL selector,NSRect rect,NSView *view)
{
 if(self==[[observed cell] cancelButtonCell]) {
  NSRect expected=[(NSSearchFieldCell *)[observed cell] cancelButtonRectForBounds:[observed bounds]];
  assert(view==observed&&NSEqualRects(rect,expected));original_clear_rects++;
 }
 ((void (*)(id,SEL,NSRect,NSView *))original_perform)(self,selector,rect,view);
}
struct Actions {NXSControl *control;double x,y;int released,actions,commands,clear_commands,defer_clear;};
static void changed(void *context,int event,const NXSControlState *state)
{struct Actions *p=context;assert(event==NXS_ACTIVATE&&state->tracking);p->actions++;}
static void release_pointer(void *context)
{struct Actions *p=context;if(!p->released){p->released=1;nxs_control_send(p->control,NXS_RELEASE,p->x,p->y,0);}}
static int command(void *context,const char *selector,unsigned phase)
{struct Actions *p=context;assert(phase==NXS_COMMAND_EXECUTE);
 if(!strcmp(selector,"clearSearch:")){p->clear_commands++;return p->defer_clear?1:-1;}
 assert(!strcmp(selector,"performClick:")&&p->actions==1);
 assert(!nxs_control_destroy(p->control));p->commands++;return 1;}
int main(int argc,char **argv)
{
 NSAutoreleasePool *pool=[NSAutoreleasePool new];
 struct Actions actions={0};
 SEL selector=@selector(initWithFrame:);Class klass=[NSSearchField class];
 Method method=class_getInstanceMethod(klass,selector);original_init=method_getImplementation(method);
 class_replaceMethod(klass,selector,(IMP)witness_init,method_getTypeEncoding(method));
 NXSControl *control=nxs_control_create(NXS_SEARCHFIELD,changed,release_pointer,&actions);assert(control);actions.control=control;
 NSSearchField *actual=observed;assert(actual&&[actual isKindOfClass:[NSSearchField class]]);
 assert([[actual cell] isKindOfClass:[NSSearchFieldCell class]]);
 class_replaceMethod(klass,selector,original_init,method_getTypeEncoding(method));
 NXSControlConfig config={.size=sizeof(config),.width=320,.height=24,.enabled=1};assert(nxs_control_sync(control,&config));
 NSSearchField *reference=[[NSSearchField alloc] initWithFrame:NSMakeRect(0,0,320,24)];
 NSSearchFieldCell *cell=[reference cell];NSRect bounds=[reference bounds];
 assert([actual class]==[reference class]&&[[actual cell] class]==[cell class]);
 NSRect parts[]={[cell searchButtonRectForBounds:bounds],[cell cancelButtonRectForBounds:bounds],[cell searchTextRectForBounds:bounds]};
 for(int index=0;index<3;index++) {
  NXSRect part=nxs_control_search_part(control,index+1);NSRect expected=parts[index];
  assert(part.x==expected.origin.x&&part.y==NSHeight(bounds)-NSMaxY(expected));
  assert(part.width==expected.size.width&&part.height==expected.size.height);
 }
 NXSSize size=nxs_control_size(control);NSSize expected=[cell cellSize];assert(size.width==expected.width&&size.height==expected.height);
 NXSRect invalid=nxs_control_search_part(control,0);assert(!invalid.width&&!invalid.height);
 if(argc>1&&!strcmp(argv[1],"--expect-no-search-action")) {
  assert(!(nxs_control_text_capabilities()&NXS_TEXT_SEARCH_ACTION));
  assert(nxs_control_destroy(control));[reference release];
  puts("{\"older_search_provider_without_activation\":true}");[pool drain];return 0;
 }
 assert(nxs_control_text_capabilities()&NXS_TEXT_SEARCH_ACTION);
 assert(nxs_control_command_filter(control,command,&actions));
 NXSRect button=nxs_control_search_part(control,NXS_SEARCH_BUTTON);
 actions.x=button.x+button.width/2;actions.y=button.y+button.height/2;
 nxs_control_track(control,actions.x,actions.y,0);
 assert(actions.released&&actions.actions==1&&actions.commands==1);
 if(argc>1&&!strcmp(argv[1],"--expect-no-clear-command")) {
  assert(!(nxs_control_text_capabilities()&NXS_TEXT_SEARCH_CLEAR_COMMAND));
  assert(nxs_control_destroy(control));[reference release];
  puts("{\"older_search_provider_without_clear_command\":true}");[pool drain];return 0;
 }
 assert(nxs_control_text_capabilities()&NXS_TEXT_SEARCH_CLEAR_COMMAND);
 NXSTextModel model={.size=sizeof(model),.text="Native clear",.selection_start=2,.editable=1};
 assert(nxs_control_text_sync(control,&model));
 button=nxs_control_search_part(control,NXS_SEARCH_CANCEL);
 actions.x=button.x+button.width/2;actions.y=button.y+button.height/2;
 actions.released=0;actions.defer_clear=1;nxs_control_track(control,actions.x,actions.y,0);
 char value[64];nxs_control_text_get(control,value,sizeof(value),NULL);
 assert(actions.released&&actions.actions==1&&actions.clear_commands==1&&!strcmp(value,"Native clear"));
 SEL perform=@selector(performClickWithFrame:inView:);
 Method perform_method=class_getInstanceMethod([NSButtonCell class],perform);
 original_perform=method_getImplementation(perform_method);
 class_replaceMethod([NSButtonCell class],perform,(IMP)witness_perform,method_getTypeEncoding(perform_method));
 assert(nxs_control_perform_click(control,NXS_SEARCH_CANCEL));
 class_replaceMethod([NSButtonCell class],perform,original_perform,method_getTypeEncoding(perform_method));
 assert(original_clear_rects==1);
 nxs_control_text_get(control,value,sizeof(value),NULL);
 assert(actions.actions==2&&actions.clear_commands==1&&!value[0]);
 assert(!nxs_control_perform_click(control,NXS_SEARCH_TEXT));
 model.text="Fallback";assert(nxs_control_text_sync(control,&model));
 actions.released=0;actions.defer_clear=0;nxs_control_track(control,actions.x,actions.y,0);
 nxs_control_text_get(control,value,sizeof(value),NULL);
 assert(actions.actions==3&&actions.clear_commands==2&&!value[0]);

 assert(nxs_control_destroy(control));[reference release];
 puts("{\"original_search_field_class\":true,\"original_search_cell_class\":true,\"native_button_and_text_geometry\":true,\"native_preferred_size\":true,\"provider_prefix_preserved\":true,\"original_button_action_forwarded_once\":true,\"native_activation_command_once\":true,\"native_clear_deferred_until_commit\":true,\"native_clear_commit_once\":true,\"native_clear_uses_original_button_rect\":true,\"unknown_clear_command_keeps_original_action\":true}");
 [pool drain];return 0;
}
