/* Compare provider dispatch with an independent ordinary native scroll view. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>

int main(int argc,char **argv)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NXSControl *control=nxs_control_create(NXS_TEXTAREA,NULL,NULL,NULL);assert(control);
  NXSWheelEvent input={.size=sizeof(input),.x=40,.y=12,.delta_y=1};
  if(argc>1&&!strcmp(argv[1],"--expect-no-wheel")){
    assert(!nxs_control_wheel_capabilities()&&!nxs_control_wheel(control,&input));
    assert(nxs_control_destroy(control));[pool drain];puts("{\"older_provider_without_wheel\":true}");return 0;
  }
  assert(nxs_control_wheel_capabilities()==NXS_WHEEL_EVENTS);
  assert(nxs_control_input_capabilities()==(NXS_INPUT_FOCUS|NXS_INPUT_KEYBOARD));
  NXSControlConfig config={.size=sizeof(config),.width=180,.height=96,.enabled=1};
  assert(nxs_control_sync(control,&config));
  const char *value="First\nSecond\nThird\nFourth\nFifth\nSixth\nSeventh\nEighth\nNinth\nTenth\n";
  NXSTextModel model={.size=sizeof(model),.text=value,.selection_start=0,.editable=1};
  assert(nxs_control_text_sync(control,&model));
  NSScrollView *scroll=[[NSScrollView alloc] initWithFrame:NSMakeRect(0,0,180,96)];
  [scroll setBorderType:NSBezelBorder];[scroll setHasVerticalScroller:YES];[scroll setAutohidesScrollers:YES];
  NSTextView *text=[[NSTextView alloc] initWithFrame:NSMakeRect(0,0,[scroll contentSize].width,[scroll contentSize].height)];
  [text setRichText:NO];[text setMinSize:NSZeroSize];[text setMaxSize:NSMakeSize(FLT_MAX,FLT_MAX)];
  [text setHorizontallyResizable:NO];[text setVerticallyResizable:YES];
  [text setAutoresizingMask:NSViewWidthSizable];[[text textContainer] setWidthTracksTextView:YES];
  [scroll setDocumentView:text];[text setString:[NSString stringWithUTF8String:value]];[text sizeToFit];
  NSWindow *window=[[NSWindow alloc] initWithContentRect:[scroll bounds] styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  [[window contentView] addSubview:scroll];
  if(argc>1&&!strcmp(argv[1],"--seat")){
    NSMutableString *lines=[NSMutableString string];for(unsigned i=0;i<60;i++)[lines appendFormat:@"Line %u\n",i];
    [text setString:lines];[text sizeToFit];[window setTitle:@"Native wheel seat reference"];
    [window makeKeyAndOrderFront:nil];fcntl(0,F_SETFL,fcntl(0,F_GETFL)|O_NONBLOCK);
    puts("{\"event\":\"native-wheel-ready\"}");fflush(stdout);BOOL done=NO;NSMutableData *pending=[NSMutableData data];
    while(!done){
      NSEvent *event=[NSApp nextEventMatchingMask:NSAnyEventMask untilDate:[NSDate dateWithTimeIntervalSinceNow:.01] inMode:NSDefaultRunLoopMode dequeue:YES];
      if(event)[NSApp sendEvent:event];[NSApp updateWindows];
      char bytes[512];ssize_t count=read(0,bytes,sizeof(bytes));if(count==0)break;if(count>0)[pending appendBytes:bytes length:count];
      for(;;){const char *start=[pending bytes],*end=memchr(start,'\n',[pending length]);if(!end)break;
        NSString *command=[[[NSString alloc] initWithBytes:start length:end-start encoding:NSUTF8StringEncoding] autorelease];
        if([command isEqualToString:@"quit"])done=YES;
        else if([command hasPrefix:@"reset "]){double y=[[command substringFromIndex:6] doubleValue];NSClipView *clip=[scroll contentView];[clip scrollToPoint:[clip constrainScrollPoint:NSMakePoint(0,y)]];[scroll reflectScrolledClipView:clip];}
        NSRect rect=[[scroll contentView] documentVisibleRect];printf("{\"x\":%.17g,\"y\":%.17g,\"height\":%.17g,\"content\":%.17g}\n",rect.origin.x,rect.origin.y,rect.size.height,[text bounds].size.height);fflush(stdout);
        [pending replaceBytesInRange:NSMakeRange(0,end-start+1) withBytes:NULL length:0];}
    }
    [window setReleasedWhenClosed:NO];[window close];[window release];[scroll release];[text release];assert(nxs_control_destroy(control));[pool drain];return 0;
  }
  NSUserDefaults *defaults=[NSUserDefaults standardUserDefaults];
  id previous=[[defaults objectForKey:@"GSMouseScrollMultiplier"] retain];
  id previousAlt=[[defaults objectForKey:@"GSFirstAlternateKey"] retain];
  [defaults setObject:@"Super_L" forKey:@"GSFirstAlternateKey"];
  const struct {double dx,dy;unsigned physical,native;int multiplier;} cases[]={
    {0,1,0,0,1},{0,-1,0,0,1},{0,.25,0,0,1},{0,1000,0,0,1},
    {0,-1000,0,0,1},{0,1,NXS_SHIFT,NSShiftKeyMask,1},
    {0,1,NXS_SUPER,NSAlternateKeyMask,1},{0,-1,0,0,1},
    {0,1,0,0,3},{0,-1,0,0,3},{0,.25,0,0,0}};
  for(unsigned i=0;i<sizeof(cases)/sizeof(*cases);i++){
    [defaults setInteger:cases[i].multiplier forKey:@"GSMouseScrollMultiplier"];
    input.delta_x=cases[i].dx;input.delta_y=cases[i].dy;input.modifiers=cases[i].physical;
    double multiplier=cases[i].multiplier?:1;
    NSEvent *event=[NSEvent mouseEventWithType:NSScrollWheel location:NSMakePoint(40,84)
      modifierFlags:cases[i].native timestamp:0 windowNumber:0 context:nil eventNumber:0
      clickCount:1 pressure:1 buttonNumber:0 deltaX:input.delta_x*multiplier
      deltaY:-input.delta_y*multiplier deltaZ:0];
    [scroll scrollWheel:event];assert(nxs_control_wheel(control,&input));
    NSRect expected=[[scroll contentView] documentVisibleRect];NXSTextViewport actual=nxs_control_text_viewport(control);
    if(fabs(expected.origin.x-actual.visible.x)>=.001||fabs(expected.origin.y-actual.visible.y)>=.001)
      fprintf(stderr,"Native wheel case=%u expected=%.3f,%.3f actual=%.3f,%.3f content=%.3f,%.3f reference=%.3f,%.3f\n",i,expected.origin.x,expected.origin.y,actual.visible.x,actual.visible.y,actual.content.width,actual.content.height,[text bounds].size.width,[text bounds].size.height);
    assert(fabs(expected.origin.x-actual.visible.x)<.001&&fabs(expected.origin.y-actual.visible.y)<.001);
    assert(!nxs_control_focused(control));
  }
  input.size=sizeof(input)-1;assert(!nxs_control_wheel(control,&input));input.size=sizeof(input);
  input.delta_y=NAN;assert(!nxs_control_wheel(control,&input));input.delta_y=0;input.x=-100;
  assert(!nxs_control_wheel(control,&input));assert(!nxs_control_wheel(control,NULL));
  NXSTextState state={.size=sizeof(state)};char buffer[512];assert(nxs_control_text_get(control,buffer,sizeof(buffer),&state));
  assert(!strcmp(buffer,value)&&state.selection_start==0&&!state.selection_length);
  if(previous)[defaults setObject:previous forKey:@"GSMouseScrollMultiplier"];else [defaults removeObjectForKey:@"GSMouseScrollMultiplier"];
  if(previousAlt)[defaults setObject:previousAlt forKey:@"GSFirstAlternateKey"];else [defaults removeObjectForKey:@"GSFirstAlternateKey"];
  [previous release];[previousAlt release];[window setReleasedWhenClosed:NO];[window close];[window release];
  [scroll release];[text release];assert(nxs_control_destroy(control));
  [pool drain];puts("{\"native_wheel_reference_cases\":11,\"unfocused_dispatch\":true,\"native_modifiers_and_preferences\":true,\"invalid_input_rejected\":true,\"text_unchanged\":true,\"keyboard_capabilities_unchanged\":true}");return 0;
}
