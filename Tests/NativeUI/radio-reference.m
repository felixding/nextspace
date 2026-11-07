/* Observe ordinary AppKit radio groups without the NativeUI provider.
 * GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include <assert.h>
#include <poll.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>

static NSWindow *window;
static NSMatrix *matrix;
static NSButton *next;
static NSArray *members;
static unsigned actions,keys,releases;

static NSInteger index_of(id cell)
{
  NSUInteger index=[members indexOfObjectIdenticalTo:cell];
  return index==NSNotFound?-1:(NSInteger)index;
}
static void report(NSString *event,NSEvent *input)
{
  NSMutableArray *states=[NSMutableArray array],*frames=[NSMutableArray array],*objects=[NSMutableArray array];
  BOOL identical=[[matrix cells] count]==[members count];
  NSInteger rows=0,columns=0;[matrix getNumberOfRows:&rows columns:&columns];
  for(NSCell *cell in members) {
    NSInteger row,column;assert([matrix getRow:&row column:&column ofCell:cell]);
    identical=identical&&[matrix cellAtRow:row column:column]==cell;
    [objects addObject:@((uintptr_t)cell)];
    [states addObject:@{ @"state":@([cell state]),@"enabled":@([cell isEnabled]),
      @"focusable":@([cell acceptsFirstResponder]) }];
    NSRect frame=[matrix convertRect:[matrix cellFrameAtRow:row column:column] toView:nil];
    /* The wire uses top-left window coordinates; AppKit supplies cell geometry. */
    [frames addObject:@[@(frame.origin.x),@([window frame].size.height-NSMaxY(frame)),
      @(frame.size.width),@(frame.size.height)]];
  }
  id responder=[window firstResponder];
  NSMutableDictionary *value=[NSMutableDictionary dictionaryWithDictionary:@{
    @"event":event,@"selected":@(index_of([matrix selectedCell])),
    @"key_cell":@(index_of([matrix keyCell])),@"actions":@(actions),
    @"keys":@(keys),@"releases":@(releases),@"rows":@(rows),@"columns":@(columns),
    @"same_cells":@(identical),@"cell_objects":objects,@"matrix_class":NSStringFromClass([matrix class]),
    @"states":states,@"frames":frames,
    @"responder":responder==matrix?@"matrix":responder==next?@"next":@"other",
    @"tab_traverses":@([matrix tabKeyTraversesCells]),@"key_window":@([window isKeyWindow]) }];
  if(input) {
    [value setObject:@([input type]) forKey:@"input_type"];
    [value setObject:@([input modifierFlags]) forKey:@"modifiers"];
    if([input type]==NSKeyDown||[input type]==NSKeyUp) {
      NSString *text=[input characters];
      [value setObject:@([text length]?[text characterAtIndex:0]:0) forKey:@"character"];
    }
  }
  NSData *json=[NSJSONSerialization dataWithJSONObject:value options:0 error:NULL];
  assert(json);fwrite([json bytes],1,[json length],stdout);putchar('\n');fflush(stdout);
}

@interface ReferenceApp : NSApplication
@end
@implementation ReferenceApp
- (void)sendEvent:(NSEvent *)event
{
  [super sendEvent:event];
  if([event type]==NSKeyDown){keys++;report(@"key",event);}
  if([event type]==NSKeyUp){releases++;report(@"release",event);}
  if([event type]==NSLeftMouseDown||[event type]==NSLeftMouseUp)report(@"pointer",event);
}
@end
@interface Actions : NSObject
- (void)changed:(id)sender;
@end
@implementation Actions
- (void)changed:(id)sender {actions++;report(@"action",nil);}
@end

static void model(NSInteger rows,NSInteger columns,NSInteger selected,
                  NSInteger focused,unsigned disabled,BOOL tab,Actions *target)
{
  assert(rows>0&&columns>0&&rows*columns<=16);
  assert(selected>=-1&&selected<rows*columns&&focused>=-1&&focused<rows*columns);
  if(matrix){[matrix removeFromSuperview];[matrix release];[members release];}
  matrix=[[NSMatrix alloc] initWithFrame:NSZeroRect mode:NSRadioModeMatrix
    cellClass:[NSButtonCell class] numberOfRows:0 numberOfColumns:columns];
  [matrix setAllowsEmptySelection:YES];
  NSMutableArray *cells=[NSMutableArray array];
  for(NSInteger row=0;row<rows;row++) {
    NSMutableArray *line=[NSMutableArray array];
    for(NSInteger column=0;column<columns;column++) {
      NSInteger index=row*columns+column;
      NSButtonCell *cell=[[NSButtonCell alloc] initTextCell:[NSString stringWithFormat:@"Choice %ld",(long)index+1]];
      [cell setButtonType:NSRadioButton];[cell setBordered:NO];
      [cell setEnabled:!(disabled&(1u<<index))];
      [line addObject:cell];[cells addObject:cell];[cell release];
    }
    /* Supply the original cells. No prototype copies or parallel button views. */
    [matrix addRowWithCells:line];
  }
  members=[cells copy];[matrix setAutosizesCells:NO];
  [matrix setCellSize:NSMakeSize(104,24)];[matrix setIntercellSpacing:NSMakeSize(8,6)];
  [matrix sizeToCells];[matrix setFrameOrigin:NSMakePoint(12,12)];
  [matrix setTabKeyTraversesCells:tab];[matrix setTarget:target];[matrix setAction:@selector(changed:)];
  if(selected>=0)[matrix selectCellAtRow:selected/columns column:selected%columns];
  else [matrix deselectAllCells];
  [matrix setAllowsEmptySelection:NO];
  if(focused>=0)[matrix setKeyCell:[members objectAtIndex:focused]];
  NSSize size=[matrix frame].size;
  [next setFrame:NSMakeRect(12,size.height+24,104,24)];
  [window setContentSize:NSMakeSize(MAX(140,size.width+24),size.height+60)];
  [[window contentView] addSubview:matrix];[matrix setNextKeyView:next];[next setNextKeyView:matrix];
  [window makeFirstResponder:matrix];[window makeKeyAndOrderFront:nil];
  actions=keys=releases=0;[window display];report(@"model",nil);
}

int main(void)
{
  NSAutoreleasePool *pool=[NSAutoreleasePool new];[ReferenceApp sharedApplication];
  [NSApp finishLaunching];[NSApp activateIgnoringOtherApps:YES];
  window=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,180,180)
    styleMask:NSTitledWindowMask backing:NSBackingStoreBuffered defer:NO];
  [window setReleasedWhenClosed:NO];[window setTitle:@"Native radio reference"];
  next=[[NSButton alloc] initWithFrame:NSZeroRect];[next setTitle:@"Next control"];
  [[window contentView] addSubview:next];Actions *target=[Actions new];
  model(4,1,0,0,2,YES,target);
  setvbuf(stdin,NULL,_IONBF,0);BOOL running=YES;
  while(running) {
    NSAutoreleasePool *iteration=[NSAutoreleasePool new];
    NSEvent *event=[NSApp nextEventMatchingMask:NSAnyEventMask
      untilDate:[NSDate dateWithTimeIntervalSinceNow:.005] inMode:NSDefaultRunLoopMode dequeue:YES];
    if(event)[NSApp sendEvent:event];[NSApp updateWindows];
    struct pollfd input={STDIN_FILENO,POLLIN,0};
    if(poll(&input,1,0)>0) {
      char line[256];if(!fgets(line,sizeof(line),stdin)){running=NO;}
      else if(!strcmp(line,"quit\n"))running=NO;
      else if(!strcmp(line,"sync\n"))report(@"sync",nil);
      else if(!strcmp(line,"draw\n")){[window display];[window flushWindow];report(@"draw",nil);}
      else if(!strcmp(line,"focus-next\n")){[window makeFirstResponder:next];report(@"focus",nil);}
      else if(!strncmp(line,"enabled ",8)) {
        unsigned index,enabled;assert(sscanf(line,"enabled %u %u",&index,&enabled)==2&&index<[members count]);
        [[members objectAtIndex:index] setEnabled:enabled];[matrix setNeedsDisplay:YES];report(@"enabled",nil);
      }
      else {
        long rows,columns,selected,focused;unsigned disabled,tab;
        assert(sscanf(line,"model %ld %ld %ld %ld %u %u",&rows,&columns,&selected,&focused,&disabled,&tab)==6);
        model(rows,columns,selected,focused,disabled,tab,target);
      }
    }
    [iteration drain];
  }
  [window close];[matrix release];[members release];[next release];[target release];[window release];[pool drain];
  return 0;
}
