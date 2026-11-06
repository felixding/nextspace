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
  BOOL cancelled,querying;
  NXSMenuLoop loop;
  NXSMenuLifecycle lifecycle;
  void *lifecycleContext;
  NSMenu *preparing;
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
{
 @public NXSMenu *owner;
  uint64_t identifier;
  BOOL lifecycleActive,opening,pendingClose;
}
- (BOOL)prepareLifecycle;
- (void)finishLifecycle;
@end
/* Only lifecycle and query actuation are added. Inherited NSMenuView owns every
 * aspect of layout, hit testing, submenu placement and event tracking. */
@interface NXSModelMenuView : NSMenuView
@end
static void lifecycle_view(NSMenu *part);
@implementation NXSModelMenuView
- (void)performActionWithHighlightingForItemAtIndex:(NSInteger)index
{
  NXSModelMenu *part=(NXSModelMenu *)[self menu];
  /* NSMenu has already matched and validated its own key equivalent. A
   * reservation query must not flash/highlight or execute that native action. */
  if(part->owner&&part->owner->querying)return;
  [super performActionWithHighlightingForItemAtIndex:index];
}
- (void)attachSubmenuForItemAtIndex:(NSInteger)index
{
  if(index<0||index>=[[self menu] numberOfItems])return;
  NXSModelMenu *part=(NXSModelMenu *)[[[self menu] itemAtIndex:index] submenu];
  if([part isKindOfClass:[NXSModelMenu class]]&&![part prepareLifecycle])return;
  [super attachSubmenuForItemAtIndex:index];
}
@end
static int lifecycle_callback(NXSModelMenu *part,unsigned phase)
{
  NXSMenu *menu=part->owner;
  NXSMenuLoop scope={.pump=menu->loop.pump,.context=menu->loop.context};
  menu->depth++;nxs_host_menu_begin(&scope);
  @try {return menu->lifecycle(menu->lifecycleContext,part->identifier,phase);}
  @finally {nxs_host_menu_end(&scope);menu->depth--;}
}
@implementation NXSModelMenu
- (void)setMain:(BOOL)flag
{
  [super setMain:flag];
  /* NSMenu may replace its representation when adopting the system's menu
   * interface style. Keep the adapter's lifecycle/query hooks on that view. */
  lifecycle_view(self);
}
- (BOOL)validateMenuItem:(NSMenuItem *)item
{
  unsigned flags=[[[item representedObject] objectForKey:@"flags"] unsignedIntValue];
  return !(flags&NXS_MENU_DISABLED)&&((owner&&owner->lifecycle)||[[item submenu] numberOfItems]>0);
}
- (BOOL)prepareLifecycle
{
  if(!owner||!owner->lifecycle||!identifier)return YES;
  if(owner->cancelled)return NO;
  if(lifecycleActive)return !pendingClose;
  lifecycleActive=YES;opening=YES;
  NSMenu *previous=owner->preparing;owner->preparing=self;
  int accepted=0;
  @try {accepted=lifecycle_callback(self,NXS_MENU_WILL_OPEN);}
  @finally {owner->preparing=previous;opening=NO;}
  if(accepted!=1||owner->cancelled||pendingClose){[self finishLifecycle];return NO;}
  return YES;
}
- (void)finishLifecycle
{
  if(!lifecycleActive)return;
  if(opening){pendingClose=YES;return;}
  lifecycleActive=NO;pendingClose=NO;
  lifecycle_callback(self,NXS_MENU_DID_CLOSE);
}
- (void)display
{if([self prepareLifecycle])[super display];}
- (void)displayTransient
{if([self prepareLifecycle])[super displayTransient];}
- (void)close
{[super close];[self finishLifecycle];}
- (void)closeTransient
{[super closeTransient];[self finishLifecycle];}
@end
static void lifecycle_view(NSMenu *part)
{
  NSMenuView *previous=[part menuRepresentation];
  if([previous isKindOfClass:[NXSModelMenuView class]])return;
  NSMenuView *view=[[[NXSModelMenuView alloc] initWithFrame:NSZeroRect] autorelease];
  [view setHorizontal:[previous isHorizontal]];
  [view setInterfaceStyle:[previous interfaceStyle]];
  [part setMenuRepresentation:view];
}
static NSMenu *model_menu(NXSMenu *owner,NSString *title,uint64_t identifier)
{
  NXSModelMenu *part=[[NXSModelMenu alloc] initWithTitle:title];
  part->owner=owner;part->identifier=identifier;
  lifecycle_view(part);
  return part;
}
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
  if(menu->querying)return;
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
  menu->root=model_menu(menu,name,0);
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
static BOOL validate_model(NXSMenu *menu,const NXSMenuItem *items,uint32_t count,
    NSMutableArray *titles,NSMutableArray *keys,NSMutableSet *identifiers)
{
  if(count>4096||(count&&!items))return NO;
  for(uint32_t i=0;i<count;i++) {
    const NXSMenuItem *item=&items[i];
    if(item->size<sizeof(*item))return NO;
    NSString *title=item->title?[NSString stringWithUTF8String:item->title]:@"";
    NSString *key=item->key_equivalent?[NSString stringWithUTF8String:item->key_equivalent]:@"";
    if(!title||!key||(item->flags&~31u)||(item->modifiers&~15u)||
       item->parent< -1||(item->parent>=0&&((uint32_t)item->parent>=i||!(items[item->parent].flags&NXS_MENU_SUBMENU)))||
       ((item->flags&NXS_MENU_SEPARATOR)&&((item->flags&NXS_MENU_SUBMENU)||item->command||[key length]))||
       (!(item->flags&(NXS_MENU_SEPARATOR|NXS_MENU_SUBMENU))&&!item->command)||
       ((item->flags&NXS_MENU_CHECKED)&&(item->flags&NXS_MENU_MIXED)))return NO;
    if(menu->lifecycle&&!(item->flags&NXS_MENU_SEPARATOR)) {
      NSNumber *identity=@(item->command);
      if(!item->command||[identifiers containsObject:identity])return NO;
      [identifiers addObject:identity];
    }
    [titles addObject:title];[keys addObject:key];
  }
  return YES;
}
static void build_model(NXSMenu *menu,NSMenu *root,const NXSMenuItem *items,uint32_t count,
    NSArray *titles,NSArray *keys,NSMutableArray *native_items,NSMutableArray *menus)
{
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
      NSMenu *sub=model_menu(menu,[titles objectAtIndex:i],data->command);
      [item setSubmenu:sub];[menus addObject:sub];[sub release];
    }
  }
}
static void collect_model(NSMenu *part,NSMutableArray *items,NSMutableArray *menus)
{
  [menus addObject:part];
  for(NSMenuItem *item in [part itemArray]) {
    [items addObject:item];
    if([item submenu])collect_model([item submenu],items,menus);
  }
}
static void replace_children(NSMenu *target,NSMenu *temporary)
{
  while([target numberOfItems])[target removeItemAtIndex:0];
  while([temporary numberOfItems]) {
    NSMenuItem *item=[[temporary itemAtIndex:0] retain];
    [temporary removeItemAtIndex:0];[target addItem:item];[item release];
  }
}
int nxs_gnustep_menu_items(NXSMenu *menu,const NXSMenuItem *items,uint32_t count)
{
  if(!owns(menu)||busy(menu))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMutableArray *titles=[NSMutableArray array],*keys=[NSMutableArray array];
  if(!validate_model(menu,items,count,titles,keys,[NSMutableSet set])){[pool drain];return 0;}
  NSMenu *root=model_menu(menu,[menu->root title],0);
  NSMutableArray *native_items=[NSMutableArray array],*menus=[NSMutableArray arrayWithObject:root];
  build_model(menu,root,items,count,titles,keys,native_items,menus);
  BOOL visible=[[menu->root window] isVisible];
  /* Preserve the native main menu/window and its input association. Replacing
   * that surface for an application model update can lose an arriving press. */
  for(NSMenu *part in menu->menus)if(part!=menu->root)[part close];
  replace_children(menu->root,root);
  [menus replaceObjectAtIndex:0 withObject:menu->root];[root release];
  [menu->items release];menu->items=[native_items copy];
  [menu->menus release];menu->menus=[menus copy];
  if(visible)[menu->root display];
  [pool drain];return 1;
}
int nxs_gnustep_menu_lifecycle(NXSMenu *menu,NXSMenuLifecycle callback,void *context)
{
  if(!owns(menu)||busy(menu))return 0;
  for(NXSModelMenu *part in menu->menus)
    if([[part window] isVisible]||part->lifecycleActive)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(callback) {
    NSMutableSet *identifiers=[NSMutableSet set];
    for(NSMenuItem *item in menu->items) {
      NSDictionary *data=[item representedObject];
      if([[data objectForKey:@"flags"] unsignedIntValue]&NXS_MENU_SEPARATOR)continue;
      NSNumber *identity=[data objectForKey:@"command"];
      if(![identity unsignedLongLongValue]||[identifiers containsObject:identity]){[pool drain];return 0;}
      [identifiers addObject:identity];
    }
  }
  menu->lifecycle=callback;menu->lifecycleContext=context;
  if(callback)for(NSMenu *part in menu->menus)lifecycle_view(part);
  [pool drain];return 1;
}
int nxs_gnustep_menu_branch_items(NXSMenu *menu,uint64_t branch,const NXSMenuItem *items,uint32_t count)
{
  if(!owns(menu)||!menu->lifecycle||!branch)return 0;
  NXSModelMenu *target=nil;
  for(NXSModelMenu *part in menu->menus)if(part->identifier==branch){target=part;break;}
  if(!target||[[target window] isVisible]||(busy(menu)&&menu->preparing!=target))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMutableArray *old_items=[NSMutableArray array],*old_menus=[NSMutableArray array];
  collect_model(target,old_items,old_menus);
  if(count>4096||[menu->items count]-[old_items count]+count>4096){[pool drain];return 0;}
  NSMutableSet *identifiers=[NSMutableSet set];
  for(NSMenuItem *item in menu->items)if(![old_items containsObject:item]) {
    NSNumber *identity=[[item representedObject] objectForKey:@"command"];
    if([identity unsignedLongLongValue])[identifiers addObject:identity];
  }
  NSMutableArray *titles=[NSMutableArray array],*keys=[NSMutableArray array];
  if(!validate_model(menu,items,count,titles,keys,identifiers)){[pool drain];return 0;}
  NSMenu *temporary=model_menu(menu,@"",0);
  NSMutableArray *new_items=[NSMutableArray array],*new_menus=[NSMutableArray array];
  build_model(menu,temporary,items,count,titles,keys,new_items,new_menus);
  replace_children(target,temporary);
  [temporary release];
  NSMutableArray *all_items=[NSMutableArray array],*all_menus=[NSMutableArray array];
  collect_model(menu->root,all_items,all_menus);
  [menu->items release];menu->items=[all_items copy];
  [menu->menus release];menu->menus=[all_menus copy];
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
int nxs_gnustep_menu_key_query(NXSMenu *menu,const NXSKeyEvent *input)
{
  if(!owns(menu)||busy(menu))return 0;
  int handled;menu->querying=YES;
  @try {handled=nxs_gnustep_menu_key(menu,input);}
  @finally {menu->querying=NO;}
  return handled;
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
