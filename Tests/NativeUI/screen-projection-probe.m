/* Foreign screen bounds affect original AppKit conversions, while the same
 * native control retains its local input and complete raster image. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <objc/runtime.h>
static NSWindow *created_window;
static id (*window_init)(id,SEL,NSRect,NSUInteger,NSBackingStoreType,BOOL);
static id observe_window(id object,SEL selector,NSRect rect,NSUInteger style,NSBackingStoreType backing,BOOL defer)
{
  id result=window_init(object,selector,rect,style,backing,defer);
  created_window=result;return result;
}
static unsigned current_kind,current_projection;
static void close_value_at(double actual,double expected,unsigned line)
{
  if(fabs(actual-expected)>=1e-7)
    fprintf(stderr,"kind=%u projection=%u line=%u actual=%.17g expected=%.17g\n",
      current_kind,current_projection,line,actual,expected);
  assert(fabs(actual-expected)<1e-7);
}
#define close_value(actual,expected) close_value_at(actual,expected,__LINE__)
int main(void)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  assert(nxs_native_ui_api());
  /* Unmapped backing windows are intentionally absent from NSApp.windows.
   * Observe the real constructor, forwarding it unchanged; do not map a
   * private window or repair focus merely to obtain test visibility. */
  Class backing=NSClassFromString(@"NXSBackingWindow");assert(backing);
  SEL initialize=@selector(initWithContentRect:styleMask:backing:defer:);
  Method method=class_getInstanceMethod(backing,initialize);assert(method);
  window_init=(void *)method_getImplementation(method);
  assert(class_addMethod(backing,initialize,(IMP)observe_window,method_getTypeEncoding(method)));
  const int kinds[]={NXS_BUTTON,NXS_TEXTFIELD,NXS_TEXTAREA,NXS_POPUP,NXS_DATEPICKER};
  const NXSRect projections[]={{31.25,48.75,59.3,12.8},{210.4,130.2,137.4,23.7},
    {15.125,300.625,281.175,73.725},{402.8,70.4,93.125,58.375}};
  unsigned cases=0;
  for(unsigned k=0;k<sizeof(kinds)/sizeof(*kinds);k++) {
    current_kind=kinds[k];current_projection=0;
    created_window=nil;
    NXSControl *control=nxs_control_create(kinds[k],NULL,NULL,NULL);assert(control);
    NXSControlConfig config={.size=sizeof(config),.width=137.4,.height=23.7,
      .maximum=1,.enabled=1,.title="Native projection"};
    assert(nxs_control_sync(control,&config));
    if(kinds[k]==NXS_DATEPICKER) {
      NXSDateModel model={.size=sizeof(model),.flags=NXS_DATE_UTC,
        .elements=NXS_DATE_YEAR_MONTH_DAY,.style=NXS_DATE_TEXT_AND_STEPPER,.value=1794268800};
      assert(nxs_control_date_sync(control,&model));
    }
    NSWindow *window=created_window;
    assert(window);NSView *view=[[[window contentView] subviews] objectAtIndex:0];
    NSRect local=[view convertRect:[view bounds] toView:nil];
    double scale=nxs_control_backing_scale(control);
    NXSBitmap before=nxs_control_draw(control,scale);assert(before.pixels);
    size_t bytes=before.stride*before.height;void *saved=malloc(bytes);assert(saved);
    memcpy(saved,before.pixels,bytes);
    for(unsigned p=0;p<sizeof(projections)/sizeof(*projections);p++) {
      current_projection=p;
      NXSRect source=projections[p];assert(nxs_control_set_screen_bounds(control,source));
      NSRect screen=[[NSScreen mainScreen] frame],converted=[window convertRectToScreen:local];
      close_value(converted.origin.x,NSMinX(screen)+source.x);
      close_value(converted.origin.y,NSMaxY(screen)-source.y-source.height);
      close_value(converted.size.width,source.width);close_value(converted.size.height,source.height);
      NSRect back=[window convertRectFromScreen:converted];
      close_value(back.origin.x,local.origin.x);close_value(back.origin.y,local.origin.y);
      close_value(back.size.width,local.size.width);close_value(back.size.height,local.size.height);
      NSPoint point=NSMakePoint(NSMidX(local)+.137,NSMidY(local)-.293);
      NSPoint roundtrip=[window convertScreenToBase:[window convertBaseToScreen:point]];
      close_value(roundtrip.x,point.x);close_value(roundtrip.y,point.y);
      [view setNeedsDisplay:YES];[window setViewsNeedDisplay:YES];
      NXSBitmap after=nxs_control_draw(control,scale);
      assert(after.pixels&&after.width==before.width&&after.height==before.height&&
        after.stride==before.stride&&!memcmp(saved,after.pixels,bytes));cases++;
    }
    assert(!nxs_control_set_screen_bounds(control,(NXSRect){0,0,-1,2}));
    assert(!nxs_control_set_screen_bounds(control,(NXSRect){NAN,0,1,2}));
    assert(nxs_control_set_screen_origin(control,44.25,66.875));
    NSRect reset=[window convertRectToScreen:local];
    /* Legacy origins retain NSWindow's own backing-pixel quantization. Reset
     * must restore that original conversion, not invent fractional rounding. */
    NSRect (*original_rect)(id,SEL,NSRect)=(void *)class_getMethodImplementation(
      [NSWindow class],@selector(convertRectToScreen:));
    NSRect original=original_rect(window,@selector(convertRectToScreen:),local);
    close_value(reset.origin.x,original.origin.x);close_value(reset.origin.y,original.origin.y);
    close_value(reset.size.width,original.size.width);close_value(reset.size.height,original.size.height);
    free(saved);assert(nxs_control_destroy(control));
  }
  printf("{\"complete\":true,\"projected_native_controls\":%u}\n",cases);
  [pool drain];return 0;
}
