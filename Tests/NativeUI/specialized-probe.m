/* Original specialized controls through the common provider, with independent
 * ordinary AppKit windows as image references. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <objc/runtime.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <poll.h>
#include <unistd.h>
_Static_assert(offsetof(NXSNativeUIAPI,control_specialized_capabilities)==600,"Preserve provider prefix");
_Static_assert(offsetof(NXSNativeUIAPI,control_color_open)==640,"Preserve specialized provider prefix");
struct Probe {NXSControl *control;NSControl *native;int kind,actions,released;double x,y,scale;const char *directory;};
static unsigned checks,images;static IMP original_init;static NSControl *observed;
static id witness_init(id self,SEL selector,NSRect rect)
{id result=((id (*)(id,SEL,NSRect))original_init)(self,selector,rect);observed=result;return result;}
static void check(const char *name,BOOL passed)
{printf("{\"case\":\"%s\",\"passed\":%s}\n",name,passed?"true":"false");fflush(stdout);assert(passed);checks++;}
static void changed(void *context,int event,const NXSControlState *state)
{
  struct Probe *p=context;p->actions++;
  assert(event==NXS_VALUE_CHANGED&&state->tracking&&!nxs_control_destroy(p->control));
  NXSControlConfig config={.size=sizeof(config),.width=260,.height=24,.enabled=1};
  assert(!nxs_control_sync(p->control,&config));
  if(p->kind==NXS_STEPPER)assert(!nxs_control_set_step(p->control,2));
  if(p->kind==NXS_COLORWELL){NXSColorModel m={.size=sizeof(m)};assert(nxs_control_color_get(p->control,&m));assert(!nxs_control_color_sync(p->control,&m));assert(!nxs_control_perform_click(p->control,0));assert(!nxs_control_color_open(p->control,1));}
  if(p->kind==NXS_DATEPICKER){NXSDateModel m={.size=sizeof(m)};assert(nxs_control_date_get(p->control,&m));assert(!nxs_control_date_sync(p->control,&m));}
}
static void release_pointer(void *context)
{struct Probe *p=context;if(!p->released){p->released=1;nxs_control_send(p->control,NXS_RELEASE,p->x,p->y,0);}}
static void compare(struct Probe *p,NSControl *reference,const char *name)
{
  NSWindow *window=[[NSWindow alloc] initWithContentRect:[reference bounds] styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setReleasedWhenClosed:NO];[[window contentView] addSubview:reference];
  [window setTitle:[NSString stringWithFormat:@"Native specialized reference %s",name]];[window orderFront:nil];[window display];
  NXSBitmap bitmap=nxs_control_draw(p->control,p->scale);assert(bitmap.pixels);
  char path[1024];snprintf(path,sizeof(path),"%s/%s-native.argb",p->directory,name);FILE *out=fopen(path,"wb");assert(out);
  assert(fwrite(bitmap.pixels,bitmap.stride,bitmap.height,out)==(size_t)bitmap.height);fclose(out);
  printf("{\"event\":\"reference\",\"pid\":%d,\"name\":\"%s\",\"pixel_width\":%d,\"pixel_height\":%d,\"stride\":%d}\n",getpid(),name,bitmap.width,bitmap.height,bitmap.stride);fflush(stdout);
  struct pollfd input={STDIN_FILENO,POLLIN,0};NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:10];
  while(poll(&input,1,0)==0&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"captured\n"));images++;
  [window close];[window release];
}
static struct Probe create(int kind,Class klass,const char *directory,double scale)
{
  struct Probe p={.kind=kind,.directory=directory,.scale=scale};
  Method method=class_getInstanceMethod(klass,@selector(initWithFrame:));original_init=method_getImplementation(method);
  class_replaceMethod(klass,@selector(initWithFrame:),(IMP)witness_init,method_getTypeEncoding(method));
  p.control=nxs_control_create(kind,NULL,NULL,NULL);assert(p.control);p.native=observed;
  class_replaceMethod(klass,@selector(initWithFrame:),original_init,method_getTypeEncoding(method));
  check("original-native-control-class",[p.native class]==klass);
  return p;
}
static void configure(struct Probe *p,double width,double height,int enabled)
{
  NXSControlConfig c={.size=sizeof(c),.width=width,.height=height,.minimum=-10,.maximum=10,.value=2,.enabled=enabled};
  assert(nxs_control_sync(p->control,&c));
}
int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(argc>1&&!strcmp(argv[1],"--expect-no-specialized")) {
    assert(!nxs_control_specialized_capabilities());
    for(int k=NXS_STEPPER;k<=NXS_DATEPICKER;k++)assert(!nxs_control_create(k,NULL,NULL,NULL));
    NXSControl *plain=nxs_control_create(NXS_TEXTFIELD,NULL,NULL,NULL);assert(plain);
    NXSColorModel color={.size=sizeof(color)};NXSDateModel date={.size=sizeof(date)};
    assert(!nxs_control_color_sync(plain,&color)&&!nxs_control_color_get(plain,&color));
    assert(!nxs_control_date_sync(plain,&date)&&!nxs_control_date_get(plain,&date));
    assert(nxs_control_destroy(plain));puts("{\"older_provider_without_specialized_controls\":true}");[pool drain];return 0;
  }
  assert(argc>2);double scale=atof(argv[2]);
  check("specialized-capabilities",(nxs_control_specialized_capabilities()&7)==7);
  struct Probe step=create(NXS_STEPPER,[NSStepper class],argv[1],scale);configure(&step,24,26,1);
  assert(nxs_control_set_step(step.control,.5));
  NSStepper *reference=[[NSStepper alloc] initWithFrame:NSMakeRect(0,0,24,26)];
  [reference setMinValue:-10];[reference setMaxValue:10];[reference setIncrement:.5];[reference setDoubleValue:2];
  NXSSize preferred=nxs_control_size(step.control);NSSize expected=[[reference cell] cellSize];
  check("original-stepper-cell-metrics-and-defaults",[[step.native cell] class]==[[reference cell] class]&&preferred.width==expected.width&&preferred.height==expected.height&&[(NSStepper *)step.native valueWraps]==[reference valueWraps]&&[(NSStepper *)step.native autorepeat]==[reference autorepeat]);
  compare(&step,reference,"stepper");[reference setEnabled:NO];configure(&step,24,26,0);assert(nxs_control_set_step(step.control,.5));compare(&step,reference,"stepper-disabled");
  check("stepper-invalid-increment-is-atomic",!nxs_control_set_step(step.control,0)&&!nxs_control_set_step(step.control,NAN)&&[(NSStepper *)step.native increment]==.5);
  assert(nxs_control_destroy(step.control));[reference release];

  struct Probe color=create(NXS_COLORWELL,[NSColorWell class],argv[1],scale);configure(&color,120,24,1);
  NSColorWell *well=[[NSColorWell alloc] initWithFrame:NSMakeRect(0,0,120,24)];
  NXSColorModel colors[]={{sizeof(NXSColorModel),1,0,0,1},{sizeof(NXSColorModel),.25,.5,.75,.5},{sizeof(NXSColorModel),0,1,0,1}};
  for(unsigned i=0;i<3;i++) {
    if(i==2){configure(&color,120,24,0);[well setEnabled:NO];}
    assert(nxs_control_color_sync(color.control,&colors[i]));
    [well setColor:[NSColor colorWithCalibratedRed:colors[i].red green:colors[i].green blue:colors[i].blue alpha:colors[i].alpha]];
    NXSColorModel actual={.size=sizeof(actual)};assert(nxs_control_color_get(color.control,&actual));
    check("native-color-components-round-trip",fabs(actual.red-colors[i].red)<.000001&&fabs(actual.green-colors[i].green)<.000001&&fabs(actual.blue-colors[i].blue)<.000001&&fabs(actual.alpha-colors[i].alpha)<.000001);
    NXSColorModel invalid=colors[i];invalid.red=NAN;check("invalid-color-rejected",!nxs_control_color_sync(color.control,&invalid));
    char name[32];snprintf(name,sizeof(name),"color-%u",i);compare(&color,well,name);
  }
  check("native-color-panel-capability",nxs_control_color_panel_capabilities()&NXS_COLOR_PANEL);
  check("disabled-native-color-panel-rejected",!nxs_control_color_open(color.control,1));
  configure(&color,120,24,1);
  check("explicit-open-uses-original-color-panel",nxs_control_color_open(color.control,1)&&[(NSColorWell *)color.native isActive]&&[[NSColorPanel sharedColorPanel] isVisible]);
  struct Probe other=create(NXS_COLORWELL,[NSColorWell class],argv[1],scale);configure(&other,120,24,1);
  assert(nxs_control_color_open(other.control,1));
  check("closing-inactive-well-preserves-current-owner",nxs_control_color_open(color.control,0)&&![(NSColorWell *)color.native isActive]&&[(NSColorWell *)other.native isActive]&&[[NSColorPanel sharedColorPanel] isVisible]);
  check("closing-current-owner-hides-original-panel",nxs_control_color_open(other.control,0)&&![(NSColorWell *)other.native isActive]&&![[NSColorPanel sharedColorPanel] isVisible]);
  assert(nxs_control_destroy(other.control));
  assert(nxs_control_destroy(color.control));[well release];

  struct Probe date=create(NXS_DATEPICKER,[NSDatePicker class],argv[1],scale);configure(&date,260,24,1);
  NSDatePicker *picker=[[NSDatePicker alloc] initWithFrame:NSMakeRect(0,0,260,24)];
  NSDatePickerElementFlags native_elements[]={0,NSYearMonthDatePickerElementFlag,NSYearMonthDayDatePickerElementFlag,NSHourMinuteDatePickerElementFlag,NSHourMinuteSecondDatePickerElementFlag,NSYearMonthDayDatePickerElementFlag|NSHourMinuteSecondDatePickerElementFlag};
  for(unsigned i=1;i<=7;i++) {
    unsigned element=i>5?NXS_DATE_YEAR_MONTH_DAY:i,style=i==6?NXS_DATE_CALENDAR:i==7?NXS_DATE_TEXT:NXS_DATE_TEXT_AND_STEPPER;
    NXSDateModel model={.size=sizeof(model),.flags=NXS_DATE_UTC|NXS_DATE_MINIMUM|NXS_DATE_MAXIMUM,.elements=element,.style=style,.value=1700000000,.minimum=1600000000,.maximum=1800000000};
    assert(nxs_control_date_sync(date.control,&model));
    [picker setDatePickerElements:native_elements[element]];[picker setDatePickerStyle:style];[picker setTimeZone:[NSTimeZone timeZoneForSecondsFromGMT:0]];
    [picker setMinDate:[NSDate dateWithTimeIntervalSince1970:model.minimum]];[picker setMaxDate:[NSDate dateWithTimeIntervalSince1970:model.maximum]];[picker setDateValue:[NSDate dateWithTimeIntervalSince1970:model.value]];
    NXSDateModel actual={.size=sizeof(actual)};assert(nxs_control_date_get(date.control,&actual));
    check("native-date-model-round-trip",actual.elements==model.elements&&actual.style==model.style&&actual.flags==model.flags&&actual.value==model.value&&actual.minimum==model.minimum&&actual.maximum==model.maximum);
    NXSDateModel invalid=model;invalid.minimum=model.maximum+1;check("invalid-date-range-rejected",!nxs_control_date_sync(date.control,&invalid));
    char name[32];snprintf(name,sizeof(name),"date-%u",i);compare(&date,picker,name);
  }
  assert(nxs_control_destroy(date.control));[picker release];
  /* Actions use each original NSControl's target/action method. Separate from
   * image references; the provider must retain native object lifetime here. */
  for(int kind=NXS_STEPPER;kind<=NXS_DATEPICKER;kind++) {
    struct Probe p={.kind=kind};
    Class klass=kind==NXS_STEPPER?[NSStepper class]:kind==NXS_COLORWELL?[NSColorWell class]:[NSDatePicker class];
    Method init=class_getInstanceMethod(klass,@selector(initWithFrame:));original_init=method_getImplementation(init);
    class_replaceMethod(klass,@selector(initWithFrame:),(IMP)witness_init,method_getTypeEncoding(init));
    p.control=nxs_control_create(kind,changed,release_pointer,&p);assert(p.control);p.native=observed;
    class_replaceMethod(klass,@selector(initWithFrame:),original_init,method_getTypeEncoding(init));
    configure(&p,kind==NXS_STEPPER?24:260,26,1);
    if(kind==NXS_DATEPICKER){NXSDateModel m={.size=sizeof(m),.flags=NXS_DATE_UTC,.elements=NXS_DATE_YEAR_MONTH_DAY,.value=1700000000};assert(nxs_control_date_sync(p.control,&m));}
    if(kind==NXS_STEPPER){p.x=9;p.y=5;nxs_control_track(p.control,p.x,p.y,0);check("native-stepper-pointer-action",p.released&&p.actions>0);}
    if(kind==NXS_COLORWELL) {
      p.x=130;p.y=13;nxs_control_track(p.control,p.x,p.y,0);
      check("native-color-well-keeps-event-pointer-lifetime",nxs_control_state(p.control).tracking&&!nxs_control_destroy(p.control));
      nxs_control_send(p.control,NXS_RELEASE,p.x,p.y,0);p.released=1;
      NSColorPanel *panel=[NSColorPanel sharedColorPanel];
      fprintf(stderr,"native-color-panel released=%d active=%d visible=%d class=%s\n",p.released,[(NSColorWell *)p.native isActive],[panel isVisible],object_getClassName(panel));
      check("original-color-well-opens-original-color-panel",p.released&&[(NSColorWell *)p.native isActive]&&[panel isVisible]&&[panel class]==[NSColorPanel class]);
      [panel setColor:[NSColor colorWithCalibratedRed:.125 green:.375 blue:.625 alpha:1]];
      NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:2];
      while(!p.actions&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
      NXSColorModel actual={.size=sizeof(actual)};assert(nxs_control_color_get(p.control,&actual));
      check("original-color-panel-delivers-native-action",p.actions>0&&fabs(actual.red-.125)<.000001&&fabs(actual.green-.375)<.000001&&fabs(actual.blue-.625)<.000001);
      [panel orderOut:nil];
    }
    /* Color-panel and date editor action provenance need actual dialog/input
     * witnesses in the next browser bindings; no synthetic action is counted. */
    assert(nxs_control_destroy(p.control));
  }
  printf("{\"passed\":%u,\"images\":%u,\"api_bytes\":%zu}\n",checks,images,sizeof(NXSNativeUIAPI));
  [pool drain];return 0;
}
