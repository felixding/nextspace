/* Application menu data bound to installed NSMenu/NSMenuItem controls.
 * No menu drawing, geometry, key matching or tracking implementation.
 * GPL-2.0-or-later. */
#import "ViewHost.h"
#include "Provider.h"
#include <stdlib.h>
struct NXSMenu {
  NSMenu *root;
  NSArray *items,*menus;
  id target;
  NSThread *thread;
  NXSMenuCommand command;
  void *context;
  unsigned depth,tracking;
  BOOL cancelled;
  NXSMenuLoop loop;
};
static int owns(NXSMenu *menu)
{return menu&&menu->thread==[NSThread currentThread];}
static int busy(NXSMenu *menu) {return menu->depth||menu->tracking;}
static int application_command(NXSMenu *menu,uint64_t command,unsigned phase)
{
  NXSMenuLoop scope={.pump=menu->loop.pump,.context=menu->loop.context};
  menu->depth++;nxs_host_menu_begin(&scope);
  @try {return menu->command(menu->context,command,phase);}
  @finally {nxs_host_menu_end(&scope);menu->depth--;}
}
/* Submenu target/action remain NSMenu's own submenuAction:. Only application
 * model availability is added, as for an ordinary native menu validator. */
@interface NXSModelMenu : NSMenu
@end
@implementation NXSModelMenu
- (BOOL)validateMenuItem:(NSMenuItem *)item
{
  unsigned flags=[[[item representedObject] objectForKey:@"flags"] unsignedIntValue];
  return !(flags&NXS_MENU_DISABLED)&&[[item submenu] numberOfItems]>0;
}
@end
@interface NXSMenuAction : NSObject {
 @public NXSMenu *menu;
}
- (void)invoke:(NSMenuItem *)item;
- (void)beginTracking:(NSNotification *)notification;
- (void)endTracking:(NSNotification *)notification;
@end
@implementation NXSMenuAction
- (BOOL)validateMenuItem:(NSMenuItem *)item
{
  NSDictionary *data=[item representedObject];
  if(!owns(menu)||menu->cancelled||([[data objectForKey:@"flags"] unsignedIntValue]&NXS_MENU_DISABLED))return NO;
  return application_command(menu,[[data objectForKey:@"command"] unsignedLongLongValue],NXS_COMMAND_VALIDATE)==1;
}
- (void)invoke:(NSMenuItem *)item
{
  if(![self validateMenuItem:item])return;
  application_command(menu,[[[item representedObject] objectForKey:@"command"] unsignedLongLongValue],NXS_COMMAND_EXECUTE);
}
- (void)beginTracking:(NSNotification *)notification
{if([menu->menus containsObject:[notification object]]&&!menu->tracking++)nxs_host_menu_begin(&menu->loop);}
- (void)endTracking:(NSNotification *)notification
{if([menu->menus containsObject:[notification object]]&&menu->tracking&&!--menu->tracking)nxs_host_menu_end(&menu->loop);}
@end
static NSUInteger menu_modifiers(unsigned value)
{
  return ((value&NXS_MENU_COMMAND)?NSCommandKeyMask:0)|((value&NXS_MENU_SHIFT)?NSShiftKeyMask:0)|
    ((value&NXS_MENU_CONTROL)?NSControlKeyMask:0)|((value&NXS_MENU_ALTERNATE)?NSAlternateKeyMask:0);
}
NXSMenu *nxs_gnustep_menu_create(const char *title,NXSMenuCommand command,NXSPump pump,void *context)
{
  if(!command)return NULL;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSString *name=title?[NSString stringWithUTF8String:title]:@"";
  if(!name||!nxs_host_initialize()){[pool drain];return NULL;}
  NXSMenu *menu=calloc(1,sizeof(*menu));if(!menu){[pool drain];return NULL;}
  menu->root=[[NXSModelMenu alloc] initWithTitle:name];
  menu->items=[NSArray new];menu->menus=[[NSArray alloc] initWithObjects:menu->root,nil];
  menu->thread=[[NSThread currentThread] retain];menu->command=command;menu->context=context;
  menu->loop.pump=pump;menu->loop.context=context;
  NXSMenuAction *target=[NXSMenuAction new];target->menu=menu;menu->target=target;
  NSNotificationCenter *center=[NSNotificationCenter defaultCenter];
  [center addObserver:target selector:@selector(beginTracking:) name:NSMenuDidBeginTrackingNotification object:nil];
  [center addObserver:target selector:@selector(endTracking:) name:NSMenuDidEndTrackingNotification object:nil];
  [pool drain];return menu;
}
int nxs_gnustep_menu_destroy(NXSMenu *menu)
{
  if(!menu)return 1;
  if(!owns(menu)||busy(menu))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  [[NSNotificationCenter defaultCenter] removeObserver:menu->target];
  for(NSMenu *part in menu->menus)[part close];
  if([NSApp mainMenu]==menu->root)[NSApp setMainMenu:nil];
  [menu->items release];[menu->menus release];[menu->root release];
  [menu->target release];[menu->thread release];free(menu);[pool drain];return 1;
}
int nxs_gnustep_menu_items(NXSMenu *menu,const NXSMenuItem *items,uint32_t count)
{
  if(!owns(menu)||busy(menu)||count>4096||(count&&!items))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMutableArray *titles=[NSMutableArray array],*keys=[NSMutableArray array];
  for(uint32_t i=0;i<count;i++) {
    const NXSMenuItem *item=&items[i];
    if(item->size<sizeof(*item)){[pool drain];return 0;}
    NSString *title=item->title?[NSString stringWithUTF8String:item->title]:@"";
    NSString *key=item->key_equivalent?[NSString stringWithUTF8String:item->key_equivalent]:@"";
    if(!title||!key||(item->flags&~31u)||(item->modifiers&~15u)||
       item->parent< -1||(item->parent>=0&&((uint32_t)item->parent>=i||!(items[item->parent].flags&NXS_MENU_SUBMENU)))||
       ((item->flags&NXS_MENU_SEPARATOR)&&((item->flags&NXS_MENU_SUBMENU)||item->command||[key length]))||
       (!(item->flags&(NXS_MENU_SEPARATOR|NXS_MENU_SUBMENU))&&!item->command)||
       ((item->flags&NXS_MENU_CHECKED)&&(item->flags&NXS_MENU_MIXED))) {
      [pool drain];return 0;
    }
    [titles addObject:title];[keys addObject:key];
  }
  NSMenu *root=[[NXSModelMenu alloc] initWithTitle:[menu->root title]];
  NSMutableArray *native_items=[NSMutableArray array],*menus=[NSMutableArray arrayWithObject:root];
  for(uint32_t i=0;i<count;i++) {
    const NXSMenuItem *data=&items[i];
    NSMenu *parent=data->parent<0?root:[[native_items objectAtIndex:data->parent] submenu];
    NSMenuItem *item=data->flags&NXS_MENU_SEPARATOR?(NSMenuItem *)[NSMenuItem separatorItem]:
      [[[NSMenuItem alloc] initWithTitle:[titles objectAtIndex:i] action:@selector(invoke:) keyEquivalent:[keys objectAtIndex:i]] autorelease];
    [item setRepresentedObject:@{@"flags":@(data->flags),@"command":@(data->command)}];
    [item setTarget:menu->target];[item setKeyEquivalentModifierMask:menu_modifiers(data->modifiers)];
    [item setState:data->flags&NXS_MENU_MIXED?NSMixedState:data->flags&NXS_MENU_CHECKED?NSOnState:NSOffState];
    [parent addItem:item];[native_items addObject:item];
    if(data->flags&NXS_MENU_SUBMENU) {
      NSMenu *sub=[[[NXSModelMenu alloc] initWithTitle:[titles objectAtIndex:i]] autorelease];
      [item setSubmenu:sub];[menus addObject:sub];
    }
  }
  BOOL main=[NSApp mainMenu]==menu->root,visible=[[menu->root window] isVisible];
  NSPoint origin=[[menu->root window] frame].origin;
  for(NSMenu *part in menu->menus)[part close];
  if(main)[NSApp setMainMenu:nil];
  [menu->root release];menu->root=root;
  [menu->items release];menu->items=[native_items copy];
  [menu->menus release];menu->menus=[menus copy];
  if(main)[NSApp setMainMenu:root];
  if(visible){[[root window] setFrameOrigin:origin];[root display];}
  [pool drain];return 1;
}
int nxs_gnustep_menu_show(NXSMenu *menu,int visible)
{
  if(!owns(menu)||busy(menu))return 0;
  if(visible&&[NSApp mainMenu]&&[NSApp mainMenu]!=menu->root)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];menu->depth++;
  @try {
    if(visible){menu->cancelled=NO;[NSApp setMainMenu:menu->root];[menu->root display];}
    else {
      for(NSMenu *part in menu->menus)[part close];
      if([NSApp mainMenu]==menu->root)[NSApp setMainMenu:nil];
    }
  } @finally {menu->depth--;}
  [pool drain];return 1;
}
int nxs_gnustep_menu_key(NXSMenu *menu,const NXSKeyEvent *input)
{
  if(!owns(menu)||busy(menu))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];menu->depth++;int handled;
  @try {handled=nxs_host_menu_key(menu->root,input);}
  @finally {menu->depth--;}
  [pool drain];return handled;
}
static NXSRect screen_rect(NSRect rect,NSWindow *window)
{
  NSRect screen=[[window screen] frame];
  return (NXSRect){rect.origin.x-screen.origin.x,NSMaxY(screen)-NSMaxY(rect),rect.size.width,rect.size.height};
}
NXSMenuState nxs_gnustep_menu_state(NXSMenu *menu,int index)
{
  NXSMenuState state={.size=sizeof(state),.highlighted=-1};
  if(!owns(menu)||index< -1||(index>=0&&(NSUInteger)index>=[menu->items count]))return state;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMenuItem *item=index>=0?[menu->items objectAtIndex:index]:nil;
  NSMenu *part=item?[item menu]:menu->root;
  if(!busy(menu)){menu->depth++;@try {[part update];}@finally {menu->depth--;}}
  NSWindow *window=[part window];NSMenuView *view=[part menuRepresentation];
  state.tracking=busy(menu);state.enabled=item?[item isEnabled]:1;
  state.highlighted=[view highlightedItemIndex];state.visible=[window isVisible];
  if(state.visible) {
    state.frame=screen_rect([window frame],window);
    if(item) {
      NSRect rect=[view rectOfItemAtIndex:[part indexOfItem:item]];
      rect=[view convertRect:rect toView:nil];rect.origin=[window convertBaseToScreen:rect.origin];
      state.item_frame=screen_rect(rect,window);
    }
  }
  [pool drain];return state;
}
int nxs_gnustep_menu_cancel(NXSMenu *menu)
{
  if(!owns(menu))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];menu->cancelled=YES;
  for(NSMenu *part in menu->menus)[part close];
  if([NSApp mainMenu]==menu->root)[NSApp setMainMenu:nil];
  /* NSMenu owns its tracking loop. End it with an ordinary native release;
   * cancelled validation prevents the highlighted command from executing. */
  if(menu->tracking) {
    NSEvent *release=[NSEvent mouseEventWithType:NSLeftMouseUp location:NSZeroPoint modifierFlags:0
      timestamp:[NSDate timeIntervalSinceReferenceDate] windowNumber:[[menu->root window] windowNumber]
      context:nil eventNumber:0 clickCount:1 pressure:0];
    [NSApp postEvent:release atStart:YES];
  }
  [pool drain];return 1;
}
