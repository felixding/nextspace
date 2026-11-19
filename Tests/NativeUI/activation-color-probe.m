/* Real GNUstep panel lifetime while the original toolkit catches up. */
#import <AppKit/AppKit.h>
#include "../../Libraries/NativeUI/NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void pump(double seconds)
{NSDate *end=[NSDate dateWithTimeIntervalSinceNow:seconds];while([end timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);}
int main(int argc,char **argv)
{
  BOOL cancelBeforeMap=argc>1&&!strcmp(argv[1],"--cancel-before-map");
  BOOL firstMap=cancelBeforeMap||(argc>1&&!strcmp(argv[1],"--first-map"));
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NXSControl *well=nxs_control_create(NXS_COLORWELL,NULL,NULL,NULL);assert(well);
  NXSControlConfig config={.size=sizeof(config),.width=80,.height=24,.enabled=1};assert(nxs_control_sync(well,&config));
  assert(nxs_control_color_open(well,1));pump(.5);
  NSWindow *panel=[NSColorPanel sharedColorPanel];[panel makeKeyWindow];[NSApp activateIgnoringOtherApps:YES];
  assert([NSApp isActive]);puts("{\"phase\":\"warm\"}");fflush(stdout);
  char line[8192];assert(fgets(line,sizeof(line),stdin)&&!strcmp(line,"reopen\n"));
  assert(nxs_control_color_open(well,0));
  NXSControl *date=NULL;
  if(firstMap) {
    date=nxs_control_create(NXS_DATEPICKER,NULL,NULL,NULL);assert(date);
    assert(nxs_control_sync(date,&config));
    NXSDateModel model={.size=sizeof(model),.flags=NXS_DATE_UTC,
      .elements=NXS_DATE_YEAR_MONTH_DAY,.value=1794009600};
    assert(nxs_control_date_sync(date,&model));
    assert(nxs_control_popup_open(date,1));
    for(NSWindow *window in [NSApp windows])
      if([[window title] isEqualToString:@"Date and Time"])panel=window;
  } else assert(nxs_control_color_open(well,1));
  assert([NSApp isActive]&&[panel isVisible]);puts("{\"phase\":\"reopened\"}");fflush(stdout);
  assert(fgets(line,sizeof(line),stdin));line[strcspn(line,"\n")]=0;
  int accepted=nxs_control_auxiliary_activate(date?:well,line);assert(accepted);
  if(cancelBeforeMap)assert(nxs_control_popup_open(date,0));
  pump(.6);
  printf("{\"phase\":\"result\",\"accepted\":%d,\"well_active\":%s,\"panel_visible\":%s,\"application_active\":%s}\n",accepted,
    (date?nxs_control_popup_state(date).visible:nxs_control_state(well).state)?"true":"false",
    [panel isVisible]?"true":"false",[NSApp isActive]?"true":"false");fflush(stdout);
  assert(fgets(line,sizeof(line),stdin));if(date)assert(nxs_control_destroy(date));
  assert(nxs_control_destroy(well));[pool drain];return 0;
}
