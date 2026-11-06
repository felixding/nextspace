/* Bind the existing NSToolbar and its native representation. No toolbar
 * drawing, item layout, hit testing or menu implementation. GPL-2.0-or-later. */
@interface NSToolbar (NXSNativeRepresentation)
- (NSView *)_toolbarView;
@end
@interface NSView (NXSNativeToolbarGeometry)
- (void)_reload;
- (CGFloat)_heightFromLayout;
- (NSToolbarItem *)toolbarItem;
@end
@interface NSToolbarItem (NXSNativeToolbarGeometry)
- (NSView *)_backView;
@end
@interface NXSToolbarAction : NXSControlAction {
 @public NSToolbar *toolbar;
  NSArray *models,*identifiers;
  NSDictionary *buttons;
  NSMenu *overflow_menu;
  uint64_t command;
}
- (void)toolbarAction:(id)sender;
- (void)prepareToolbarMenu:(NSNotification *)notification;
- (void)beginToolbarMenu:(NSNotification *)notification;
- (void)endToolbarMenu:(NSNotification *)notification;
@end
static NSUInteger toolbar_index(NXSToolbarAction *target,NSToolbarItem *item)
{return [[target->toolbar items] indexOfObjectIdenticalTo:item];}
@implementation NXSToolbarAction
- (void)dealloc
{
  [[NSNotificationCenter defaultCenter] removeObserver:self];
  [toolbar setDelegate:nil];[toolbar release];
  [models release];[identifiers release];[buttons release];[overflow_menu release];[super dealloc];
}
- (NSArray *)toolbarAllowedItemIdentifiers:(NSToolbar *)sender {return identifiers;}
- (NSArray *)toolbarDefaultItemIdentifiers:(NSToolbar *)sender {return identifiers;}
- (NSToolbarItem *)toolbar:(NSToolbar *)sender itemForItemIdentifier:(NSString *)key willBeInsertedIntoToolbar:(BOOL)insert
{return [buttons objectForKey:key];}
- (BOOL)validateToolbarItem:(NSToolbarItem *)item
{
  NSUInteger index=toolbar_index(self,item);
  return !control->destroying&&control->enabled&&index<[models count]&&[[[models objectAtIndex:index] objectForKey:@"enabled"] boolValue];
}
- (void)toolbarAction:(id)sender
{
  NSToolbarItem *item=[sender isKindOfClass:[NSToolbarItem class]]?sender:
    ([sender respondsToSelector:@selector(toolbarItem)]?[sender toolbarItem]:nil);
  NSUInteger index=toolbar_index(self,item);
  if(index>=[models count]||![self validateToolbarItem:item])return;
  command=[[[models objectAtIndex:index] objectForKey:@"id"] unsignedLongLongValue];
  if(control->changed){NXSControlState state=nxs_gnustep_control_state(control);control->changed(control->context,NXS_ACTIVATE,&state);}
}
- (BOOL)ownsMenu:(NSMenu *)menu
{
  for(NSMenuItem *item in [menu itemArray])if([[toolbar items] containsObject:[item target]])return YES;
  return NO;
}
- (void)prepareToolbarMenu:(NSNotification *)notification
{
  NSMenu *menu=[notification object];
  /* Transient placement queries the ordinary menu window before tracking.
   * Supply the owner's existing pointer source as native items are added. */
  if([self ownsMenu:menu])nxs_host_bind_input_window(control->host,[menu window]);
}
- (void)beginToolbarMenu:(NSNotification *)notification
{
  NSMenu *menu=[notification object];if(![self ownsMenu:menu])return;
  ASSIGN(overflow_menu,menu);nxs_host_bind_input_window(control->host,[menu window]);
}
- (void)endToolbarMenu:(NSNotification *)notification
{
  if([notification object]!=overflow_menu)return;
  nxs_host_unbind_input_windows(control->host);DESTROY(overflow_menu);
}
@end
static NSView *toolbar_create(NXSControl *control)
{
  NXSToolbarAction *target=[NXSToolbarAction new];target->control=control;
  target->models=[NSArray new];target->identifiers=[NSArray new];target->buttons=[NSDictionary new];
  target->toolbar=[[NSToolbar alloc] initWithIdentifier:[[NSProcessInfo processInfo] globallyUniqueString]];
  [target->toolbar setAllowsUserCustomization:NO];[target->toolbar setAutosavesConfiguration:NO];
  [target->toolbar setDelegate:(id)target];control->target=target;
  NSNotificationCenter *center=[NSNotificationCenter defaultCenter];
  [center addObserver:target selector:@selector(prepareToolbarMenu:) name:NSMenuDidAddItemNotification object:nil];
  [center addObserver:target selector:@selector(beginToolbarMenu:) name:NSMenuDidBeginTrackingNotification object:nil];
  [center addObserver:target selector:@selector(endToolbarMenu:) name:NSMenuDidEndTrackingNotification object:nil];
  return [[target->toolbar _toolbarView] retain];
}
static void toolbar_layout(NXSControl *control)
{
  NXSToolbarAction *target=control->target;
  [control->view _reload];[target->toolbar validateVisibleItems];
}
static NSView *toolbar_overflow_view(NSView *view)
{
  if([view isKindOfClass:NSClassFromString(@"GSToolbarClippedItemsButton")])return view;
  for(NSView *child in [view subviews]){NSView *found=toolbar_overflow_view(child);if(found)return found;}
  return nil;
}
int nxs_gnustep_control_toolbar_items(NXSControl *control,const NXSToolbarItem *items,uint32_t count,uint32_t display,uint32_t size)
{
  if(!control||control->kind!=NXS_TOOLBAR||control->destroying||count>4096||(count&&!items)||display>3||size>2||nxs_host_tracking(control->host))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMutableArray *models=[NSMutableArray arrayWithCapacity:count],*ids=[NSMutableArray arrayWithCapacity:count];
  NSMutableSet *seen=[NSMutableSet setWithCapacity:count];
  for(unsigned i=0;i<count;i++) {
    const NXSToolbarItem *item=&items[i];
    if(item->size<sizeof(*item)){[pool drain];return 0;}
    NSNumber *key=[NSNumber numberWithUnsignedLongLong:item->identifier];
    NSString *title=item->title?[NSString stringWithUTF8String:item->title]:@"";
    NSString *tip=item->tooltip?[NSString stringWithUTF8String:item->tooltip]:@"";
    NSString *image=item->image_name?[NSString stringWithUTF8String:item->image_name]:@"";
    if(!item->identifier||item->type>NXS_TOOLBAR_SEPARATOR||item->reserved||[seen containsObject:key]||!title||!tip||!image||([image length]&&![NSImage imageNamed:image])){[pool drain];return 0;}
    [seen addObject:key];
    NSString *identifier=item->type==NXS_TOOLBAR_SPACE?NSToolbarSpaceItemIdentifier:
      item->type==NXS_TOOLBAR_FLEXIBLE_SPACE?NSToolbarFlexibleSpaceItemIdentifier:
      item->type==NXS_TOOLBAR_SEPARATOR?NSToolbarSeparatorItemIdentifier:[NSString stringWithFormat:@"nxs.%llu",(unsigned long long)item->identifier];
    [ids addObject:identifier];
    [models addObject:@{@"id":key,@"type":@(item->type),@"title":title,@"tip":tip,@"image":image,@"enabled":@(!!item->enabled)}];
  }
  NXSToolbarAction *target=control->target;
  if([target->models isEqual:models]&&[target->toolbar displayMode]==display&&[target->toolbar sizeMode]==size){[pool drain];return 1;}
  NSMutableDictionary *buttons=[NSMutableDictionary dictionary];
  for(unsigned i=0;i<count;i++) {
    NSDictionary *data=[models objectAtIndex:i];if([[data objectForKey:@"type"] unsignedIntValue]!=NXS_TOOLBAR_ACTION)continue;
    NSString *identifier=[ids objectAtIndex:i];NSToolbarItem *item=[target->buttons objectForKey:identifier];
    if(!item)item=[[[NSToolbarItem alloc] initWithItemIdentifier:identifier] autorelease];
    [item setLabel:[data objectForKey:@"title"]];[item setPaletteLabel:[data objectForKey:@"title"]];[item setToolTip:[data objectForKey:@"tip"]];
    NSString *name=[data objectForKey:@"image"];NSImage *image=[name length]?[[[NSImage imageNamed:name] copy] autorelease]:nil;[item setImage:image];
    [item setTarget:target];[item setAction:@selector(toolbarAction:)];
    [item setEnabled:control->enabled&&[[data objectForKey:@"enabled"] boolValue]];[buttons setObject:item forKey:identifier];
  }
  NSSize hosting_size=[control->view frame].size;
  while([[target->toolbar items] count])[target->toolbar removeItemAtIndex:0];
  ASSIGN(target->models,models);ASSIGN(target->identifiers,ids);ASSIGN(target->buttons,buttons);
  if(![seen containsObject:@(target->command)])target->command=0;
  [target->toolbar setDisplayMode:(NSToolbarDisplayMode)display];[target->toolbar setSizeMode:(NSToolbarSizeMode)size];
  for(unsigned i=0;i<count;i++)[target->toolbar insertItemWithItemIdentifier:[ids objectAtIndex:i] atIndex:i];
  /* Mode changes also adjust a normal NSWindow's toolbar frame. This view is
   * embedded independently: retain its configured host extent and origin.
   * The original toolbar still supplies the preferred height and item layout. */
  nxs_host_resize(control->host,hosting_size);[control->view setFrameOrigin:NSZeroPoint];toolbar_layout(control);
  [pool drain];return 1;
}
NXSToolbarState nxs_gnustep_control_toolbar_state(NXSControl *control)
{
  NXSToolbarState state={.size=sizeof(state),.highlighted=-1};
  if(!control||control->kind!=NXS_TOOLBAR||control->destroying)return state;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];NXSToolbarAction *target=control->target;
  state.count=[[target->toolbar items] count];state.visible_count=[[target->toolbar visibleItems] count];state.command=target->command;
  state.preferred=(NXSSize){[control->view frame].size.width,[control->view _heightFromLayout]};
  NSView *overflow=toolbar_overflow_view(control->view);
  if(overflow)state.overflow=nxs_host_rect_from_view(control->host,overflow,[overflow bounds]);
  if(nxs_host_tracking(control->host))state.flags|=NXS_TOOLBAR_TRACKING;
  if(target->overflow_menu) {
    NSMenuView *view=[target->overflow_menu menuRepresentation];
    state.highlighted=[view highlightedItemIndex];
    if([[target->overflow_menu window] isVisible]){state.flags|=NXS_TOOLBAR_MENU_VISIBLE;state.menu=nxs_host_rect_from_view(control->host,view,[view bounds]);}
  }
  [pool drain];return state;
}
NXSRect nxs_gnustep_control_toolbar_item_rect(NXSControl *control,uint64_t identifier)
{
  if(!control||control->kind!=NXS_TOOLBAR||control->destroying||!identifier)return (NXSRect){0};
  NSAutoreleasePool *pool=[NSAutoreleasePool new];NXSToolbarAction *target=control->target;NXSRect rect={0};
  NSUInteger index=NSNotFound;
  for(unsigned i=0;i<[target->models count];i++)if([[[target->models objectAtIndex:i] objectForKey:@"id"] unsignedLongLongValue]==identifier){index=i;break;}
  if(index<[[target->toolbar items] count]) {
    NSToolbarItem *item=[[target->toolbar items] objectAtIndex:index];
    if([[target->toolbar visibleItems] containsObject:item]){NSView *view=[item _backView];rect=nxs_host_rect_from_view(control->host,view,[view bounds]);}
    else if(target->overflow_menu&&[[target->overflow_menu window] isVisible]) {
      NSInteger i=[target->overflow_menu indexOfItemWithTarget:item andAction:@selector(_sendAction:)];
      if(i>=0){NSMenuView *view=[target->overflow_menu menuRepresentation];rect=nxs_host_rect_from_view(control->host,view,[view rectOfItemAtIndex:i]);}
    }
  }
  [pool drain];return rect;
}
