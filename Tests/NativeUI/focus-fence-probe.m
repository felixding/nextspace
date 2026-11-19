/* Observe the original application's activation while its compositor pauses.
 * No backend, window, control or focus implementation is copied. */
#import <AppKit/AppKit.h>
#import <GNUstepGUI/GSDisplayServer.h>
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int queued_enter_probe(void)
{
  NXSControl *control=nxs_control_create(NXS_DATEPICKER,NULL,NULL,NULL);assert(control);
  NXSControlConfig config={.size=sizeof(config),.width=260,.height=30,.enabled=1};
  assert(nxs_control_sync(control,&config));
  NXSDateModel model={.size=sizeof(model),.flags=NXS_DATE_UTC,.elements=NXS_DATE_YEAR_MONTH_DAY,.value=1794009600};
  assert(nxs_control_date_sync(control,&model));
  NSWindow *window=[[NSWindow alloc] initWithContentRect:NSMakeRect(40,40,240,120)
    styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setReleasedWhenClosed:NO];[window setTitle:@"Queued focus source"];
  [window makeKeyAndOrderFront:nil];
  assert(nxs_control_popup_open(control,1));
  NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:.5];
  while([deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  assert(nxs_control_popup_open(control,0));[window makeKeyAndOrderFront:nil];
  deadline=[NSDate dateWithTimeIntervalSinceNow:.5];
  while([deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  puts("{\"phase\":\"ready\"}");fflush(stdout);
  char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"paused\n"));
  /* This is the original event the protocol callback queues before AppKit
   * receives a newer application request. The compositor is deliberately
   * paused so its acknowledgement cannot accidentally hide the ordering bug. */
  NSEvent *event=[NSEvent otherEventWithType:NSAppKitDefined location:NSZeroPoint
    modifierFlags:0 timestamp:0 windowNumber:[window windowNumber]
    context:GSCurrentContext() subtype:GSAppKitWindowFocusIn data1:0 data2:0];
  [GSCurrentServer() postEvent:event atStart:NO];
  assert(nxs_control_popup_open(control,1));
  deadline=[NSDate dateWithTimeIntervalSinceNow:.25];
  while([deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  if(!nxs_control_popup_state(control).visible) {
    fputs("Queued old enter closed the newly requested native calendar before acknowledgement.\n",stderr);return 1;
  }
  puts("{\"phase\":\"waiting-for-ack\"}");fflush(stdout);
  assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"resumed\n"));
  deadline=[NSDate dateWithTimeIntervalSinceNow:.5];
  while([deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  assert(nxs_control_popup_state(control).visible);
  assert(nxs_control_destroy(control));[window orderOut:nil];[window release];
  puts("{\"phase\":\"passed\",\"queued_enter_fenced\":true}");fflush(stdout);return 0;
}

int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  for(int index=1;index<argc;index++)if(!strcmp(argv[index],"--queued-enter")){int result=queued_enter_probe();[pool drain];return result;}
  NXSControl *control=nxs_control_create(NXS_BUTTON,NULL,NULL,NULL);assert(control);
  [NSApp activateIgnoringOtherApps:YES];assert([NSApp isActive]);
  puts("{\"phase\":\"ready\"}");fflush(stdout);
  char reply[32];assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"paused\n"));
  [GSCurrentServer() performSelector:@selector(deactivateIfUnfocused:) withObject:nil];
  NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:.25];
  while([deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  if(![NSApp isActive]) {
    fputs("Application deactivated before the compositor acknowledged pending requests.\n",stderr);
    return 1;
  }
  puts("{\"phase\":\"waiting-for-ack\"}");fflush(stdout);
  assert(fgets(reply,sizeof(reply),stdin)&&!strcmp(reply,"resumed\n"));
  deadline=[NSDate dateWithTimeIntervalSinceNow:3];
  while([NSApp isActive]&&[deadline timeIntervalSinceNow]>0)nxs_native_ui_dispatch_events(.01);
  assert(![NSApp isActive]);
  assert(nxs_control_destroy(control));[pool drain];
  puts("{\"phase\":\"passed\",\"acknowledgement_required\":true,\"real_deactivation_preserved\":true}");
  return 0;
}
