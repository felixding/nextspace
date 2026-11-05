/* Existing NSScroller range/action binding. GPL-2.0-or-later. */
#import "ViewHost.h"
#include "Provider.h"
#include <math.h>
#include <stdlib.h>
struct NXSScroller {
  NSScroller *view;
  NXSViewHost *host;
  id target;
  double lower, upper, page, step, page_step, value;
  NXSChanged changed;
  void *context;
  BOOL horizontal;
};
@interface NXSAction : NSObject { @public NXSScroller *control; }
- (void)changed:(NSScroller *)sender;
@end
@implementation NXSAction
- (void)changed:(NSScroller *)sender
{
  double value = control->value;
  switch ([sender hitPart]) {
    case NSScrollerDecrementLine: value -= control->step; break;
    case NSScrollerIncrementLine: value += control->step; break;
    case NSScrollerDecrementPage: value -= control->page_step; break;
    case NSScrollerIncrementPage: value += control->page_step; break;
    default: value = control->lower + [sender doubleValue] *
      fmax(0, control->upper - control->lower - control->page); break;
  }
  control->value = fmax(control->lower, fmin(value, fmax(control->lower, control->upper - control->page)));
  if(control->changed)control->changed(control->context, control->value);
}
@end

double nxs_gnustep_scroller_width(void)
{return nxs_host_initialize()?[NSScroller scrollerWidth]:0;}
NXSScroller *nxs_gnustep_scroller_create(int horizontal,NXSChanged changed,NXSPump pump,void *context)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(!nxs_host_initialize()){[pool drain];return NULL;}
  NXSScroller *control=calloc(1,sizeof(*control));
  if(control) {
    double width=nxs_gnustep_scroller_width();
    NSScroller *view=[[NSScroller alloc] initWithFrame:
      NSMakeRect(0,0,horizontal?128:width,horizontal?width:128)];
    control->host=nxs_host_create(view,pump,context);control->view=view;[view release];
    if(!control->host){free(control);[pool drain];return NULL;}
    NXSAction *target=[NXSAction new];target->control=control;control->target=target;
    [view setTarget:target];[view setAction:@selector(changed:)];
    control->changed=changed;control->context=context;control->horizontal=horizontal;
  }
  [pool drain];return control;
}
void nxs_gnustep_scroller_destroy(NXSScroller *control)
{
  if(!control)return;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(nxs_host_destroy(control->host)){[control->target release];free(control);}
  [pool drain];
}
void nxs_gnustep_scroller_sync(NXSScroller *control, double length, double lower, double upper,
                       double page, double step, double page_step, double value, int enabled)
{
  if (!control || !isfinite(length) || length < 1 || length > 32768) return;
  NSAutoreleasePool *pool = [NSAutoreleasePool new];
  double width=nxs_gnustep_scroller_width();
  BOOL horizontal=control->horizontal;
  NSSize size=NSMakeSize(horizontal ? length : width,horizontal ? width : length);
  /* setFrameSize: resets NSScroller's hit part, even for an unchanged size. */
  nxs_host_resize(control->host,size);
  control->lower = lower; control->upper = upper; control->page = page;
  control->step = step; control->page_step = page_step; control->value = value;
  double extent = fmax(0, upper - lower), range = fmax(0, extent - page);
  [control->view setEnabled:enabled && range > 0];
  [control->view setFloatValue:range > 0 ? (value - lower) / range : 0
              knobProportion:extent > 0 ? fmin(1, page / extent) : 1];
  [pool drain];
}

NXSRect nxs_gnustep_scroller_part(NXSScroller *control, int part)
{
  NSRect rect = control ? [control->view rectForPart:(NSScrollerPart)part] : NSZeroRect;
  return (NXSRect){rect.origin.x, rect.origin.y, rect.size.width, rect.size.height};
}

NXSBitmap nxs_gnustep_scroller_draw(NXSScroller *c,double scale)
{return c?nxs_host_draw(c->host,scale):(NXSBitmap){0};}
void nxs_gnustep_scroller_track(NXSScroller *c,double x,double y,unsigned m)
{if(c&&[c->view isEnabled])nxs_host_track(c->host,x,y,m);}
void nxs_gnustep_scroller_send(NXSScroller *c,int event,double x,double y,unsigned m)
{if(c)nxs_host_send(c->host,event,x,y,m);}
int nxs_gnustep_scroller_tracking(NXSScroller *c){return c&&nxs_host_tracking(c->host);}
int nxs_gnustep_scroller_hit_part(NXSScroller *c){return c?[c->view hitPart]:NSScrollerNoPart;}
