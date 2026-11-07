/* Compare the shared binding with the original NSSearchField class and cell.
 * GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <objc/runtime.h>
#include <assert.h>
#include <stdio.h>
_Static_assert(offsetof(NXSNativeUIAPI,control_search_part)==584,"Preserve the existing provider prefix");
static IMP original_init;
static NSSearchField *observed;
static id witness_init(id self,SEL selector,NSRect frame)
{id result=((id (*)(id,SEL,NSRect))original_init)(self,selector,frame);observed=result;return result;}
int main(void)
{
 NSAutoreleasePool *pool=[NSAutoreleasePool new];
 SEL selector=@selector(initWithFrame:);Class klass=[NSSearchField class];
 Method method=class_getInstanceMethod(klass,selector);original_init=method_getImplementation(method);
 class_replaceMethod(klass,selector,(IMP)witness_init,method_getTypeEncoding(method));
 NXSControl *control=nxs_control_create(NXS_SEARCHFIELD,NULL,NULL,NULL);assert(control);
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
 assert(nxs_control_destroy(control));[reference release];
 puts("{\"original_search_field_class\":true,\"original_search_cell_class\":true,\"native_button_and_text_geometry\":true,\"native_preferred_size\":true,\"provider_prefix_preserved\":true}");
 [pool drain];return 0;
}
