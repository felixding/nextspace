/* Independent ordinary native window for real-seat gesture comparison.
 * No provider list implementation participates. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <poll.h>
#include <stdio.h>
#include <unistd.h>
@interface Data : NSObject
@end
@implementation Data
- (NSInteger)browser:(NSBrowser *)browser numberOfRowsInColumn:(NSInteger)column{return 4;}
- (void)browser:(NSBrowser *)browser willDisplayCell:(NSBrowserCell *)cell atRow:(NSInteger)row column:(NSInteger)column
{[cell setStringValue:[@[@"Alpha",@"Bravo",@"Another title",@"Delta"] objectAtIndex:row]];[cell setLeaf:YES];[cell setEnabled:row!=1];}
@end
int main(void)
{
 NSAutoreleasePool *pool=[NSAutoreleasePool new];NXSControl *bootstrap=nxs_control_create(NXS_BUTTON,NULL,NULL,NULL);nxs_control_destroy(bootstrap);
 NSBrowser *browser=[[NSBrowser alloc] initWithFrame:NSMakeRect(0,0,180,96)];Data *data=[Data new];
 [browser setMaxVisibleColumns:1];[browser setMinColumnWidth:1];[browser setTitled:NO];[browser setSeparatesColumns:NO];[browser setHasHorizontalScroller:NO];
 [browser setAllowsEmptySelection:YES];[browser setAllowsMultipleSelection:NO];[browser setDelegate:data];[browser loadColumnZero];
 NSMatrix *matrix=[browser matrixInColumn:0];[matrix selectCellAtRow:0 column:0];
 NSWindow *window=[[NSWindow alloc] initWithContentRect:[browser bounds] styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
 [window setReleasedWhenClosed:NO];[[window contentView] addSubview:browser];[window setTitle:@"Original native list gesture"];[window makeKeyAndOrderFront:nil];[window makeFirstResponder:browser];
 printf("{\"ready\":true,\"pid\":%d,\"rects\":[",getpid());
 for(int row=0;row<4;row++) {
  NSRect rect=[matrix convertRect:[matrix cellFrameAtRow:row column:0] toView:browser];
  printf("%s{\"x\":%g,\"y\":%g,\"width\":%g,\"height\":%g}",row?",":"",rect.origin.x,
    [browser isFlipped]?rect.origin.y:NSHeight([browser bounds])-NSMaxY(rect),rect.size.width,rect.size.height);
 }
 puts("]}");fflush(stdout);
 for(;;) {
  struct pollfd input={STDIN_FILENO,POLLIN,0};while(!poll(&input,1,0))nxs_native_ui_dispatch_events(.01);
  char command[32];if(!fgets(command,sizeof(command),stdin)||command[0]=='q')break;
  nxs_native_ui_dispatch_events(.05);[browser displayRectIgnoringOpacity:[browser bounds]];
  printf("{\"selected\":%ld,\"cells\":[",(long)[matrix selectedRow]);
  for(int row=0;row<4;row++){NSCell *cell=[matrix cellAtRow:row column:0];printf("%s{\"state\":%ld,\"highlighted\":%s,\"selected\":%s}",row?",":"",(long)[cell state],[cell isHighlighted]?"true":"false",[[matrix selectedCells] containsObject:cell]?"true":"false");}
  puts("]}");fflush(stdout);
 }
 [window close];[pool drain];return 0;
}
