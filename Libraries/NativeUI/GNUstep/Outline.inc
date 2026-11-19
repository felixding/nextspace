/* Application data source for the original GNUstep NSOutlineView.
 * No disclosure, selection, keyboard, scrolling, drawing or hit-test rules.
 * GPL-2.0-or-later. */
@interface NXSOutlineAction : NSObject {
 @public NXSControl *control; NSArray *models; NSDictionary *byID,*children;
 BOOL syncing; NSInteger actionIndex; int actionState;
}
- (void)emit:(id)item state:(int)state;
@end
static NSOutlineView *outline_view(NXSControl *control)
{return (NSOutlineView *)[(NSScrollView *)control->view documentView];}
@implementation NXSOutlineAction
- (void)dealloc {[models release];[byID release];[children release];[super dealloc];}
- (NSInteger)outlineView:(NSOutlineView *)view numberOfChildrenOfItem:(id)item
{return [[children objectForKey:item?:@0] count];}
- (id)outlineView:(NSOutlineView *)view child:(NSInteger)index ofItem:(id)item
{return [[children objectForKey:item?:@0] objectAtIndex:index];}
- (BOOL)outlineView:(NSOutlineView *)view isItemExpandable:(id)item
{return [[children objectForKey:item] count]>0||[[[byID objectForKey:item] objectForKey:@"flags"] unsignedIntValue]&NXS_OUTLINE_EXPANDABLE;}
- (id)outlineView:(NSOutlineView *)view objectValueForTableColumn:(NSTableColumn *)column byItem:(id)item
{return [[byID objectForKey:item] objectForKey:@"title"];}
- (BOOL)outlineView:(NSOutlineView *)view shouldSelectItem:(id)item
{return control->enabled&&([[[byID objectForKey:item] objectForKey:@"flags"] unsignedIntValue]&NXS_OUTLINE_ENABLED);}
- (BOOL)outlineView:(NSOutlineView *)view shouldExpandItem:(id)item
{return [self outlineView:view shouldSelectItem:item];}
- (BOOL)outlineView:(NSOutlineView *)view shouldCollapseItem:(id)item
{return [self outlineView:view shouldSelectItem:item];}
- (void)outlineView:(NSOutlineView *)view willDisplayCell:(id)cell forTableColumn:(NSTableColumn *)column item:(id)item
{[cell setEnabled:[self outlineView:view shouldSelectItem:item]];}
- (void)emit:(id)item state:(int)value
{
 if(syncing||control->destroying||!item)return;
 NSDictionary *model=[byID objectForKey:item];if(!model)return;
 actionIndex=[models indexOfObjectIdenticalTo:model];actionState=value;
 if(actionIndex==NSNotFound)return;
 if(control->changed){NXSControlState state=nxs_gnustep_control_state(control);control->changed(control->context,NXS_VALUE_CHANGED,&state);}
}
- (void)outlineViewSelectionDidChange:(NSNotification *)notification
{NSOutlineView *view=[notification object];if([view selectedRow]>=0)[self emit:[view itemAtRow:[view selectedRow]] state:0];}
- (void)outlineViewItemDidExpand:(NSNotification *)notification
{[self emit:[[notification userInfo] objectForKey:@"NSObject"] state:1];}
- (void)outlineViewItemDidCollapse:(NSNotification *)notification
{[self emit:[[notification userInfo] objectForKey:@"NSObject"] state:-1];}
@end
static NSView *outline_create(NXSControl *control)
{
 NSScrollView *scroll=[[NSScrollView alloc] initWithFrame:NSMakeRect(0,0,180,96)];
 [scroll setBorderType:NSBezelBorder];[scroll setHasVerticalScroller:YES];[scroll setHasHorizontalScroller:YES];[scroll setAutohidesScrollers:YES];
 NSOutlineView *view=[[NSOutlineView alloc] initWithFrame:NSMakeRect(0,0,[scroll contentSize].width,[scroll contentSize].height)];
 NSTableColumn *column=[[NSTableColumn alloc] initWithIdentifier:@"title"];
 [column setResizingMask:NSTableColumnAutoresizingMask];[column setEditable:NO];[column setWidth:[scroll contentSize].width];[view addTableColumn:column];[view setOutlineTableColumn:column];[column release];
 [view setColumnAutoresizingStyle:NSTableViewLastColumnOnlyAutoresizingStyle];
 [view setHeaderView:nil];[view setAllowsEmptySelection:YES];[view setAllowsMultipleSelection:NO];[view setAutoresizingMask:NSViewWidthSizable];
 NXSOutlineAction *target=[NXSOutlineAction new];target->control=control;target->models=[NSArray new];target->byID=[NSDictionary new];target->children=[NSDictionary new];target->actionIndex=-1;control->target=target;
 [view setDataSource:(id)target];[view setDelegate:(id)target];[scroll setDocumentView:view];[view release];return scroll;
}
int nxs_gnustep_control_outline_items(NXSControl *control,const NXSOutlineItem *items,uint32_t count)
{
 if(!control||control->kind!=NXS_OUTLINE||control->destroying||nxs_host_tracking(control->host)||count>4096||(!items&&count))return 0;
 NSAutoreleasePool *pool=[NSAutoreleasePool new];NSMutableArray *models=[NSMutableArray array];NSMutableDictionary *byID=[NSMutableDictionary dictionary],*children=[NSMutableDictionary dictionary];unsigned selected=0;
 for(uint32_t i=0;i<count;i++) {
  const NXSOutlineItem *item=items+i;NSNumber *identifier=@(item->identifier),*parent=@(item->parent);
  if(item->size<sizeof(*item)||!item->identifier||item->flags&~15||[byID objectForKey:identifier]||(item->parent&&![byID objectForKey:parent])||((item->flags&NXS_OUTLINE_EXPANDED)&&!(item->flags&NXS_OUTLINE_EXPANDABLE))){[pool drain];return 0;}
  NSString *title=item->title?[NSString stringWithUTF8String:item->title]:@"";if(!title){[pool drain];return 0;}
  NSDictionary *model=@{@"id":identifier,@"parent":parent,@"title":title,@"flags":@(item->flags)};
  [models addObject:model];[byID setObject:model forKey:identifier];
  NSMutableArray *siblings=[children objectForKey:parent];if(!siblings){siblings=[NSMutableArray array];[children setObject:siblings forKey:parent];}[siblings addObject:identifier];
  selected+=!!(item->flags&NXS_OUTLINE_SELECTED);
 }
 if(selected>1){[pool drain];return 0;}
 NXSOutlineAction *target=control->target;if([models isEqualToArray:target->models]){[pool drain];return 1;}
 NSArray *positions=nxs_host_document_positions(control->host);NSOutlineView *view=outline_view(control);target->syncing=YES;
 [target->models release];target->models=[models copy];[target->byID release];target->byID=[byID copy];[target->children release];target->children=[children copy];
 [view reloadData];[view deselectAll:nil];
 for(NSDictionary *model in models) {
  id item=[model objectForKey:@"id"];unsigned flags=[[model objectForKey:@"flags"] unsignedIntValue];
  if(flags&NXS_OUTLINE_EXPANDED)[view expandItem:item];else [view collapseItem:item];
  if(flags&NXS_OUTLINE_SELECTED){NSInteger row=[view rowForItem:item];if(row>=0)[view selectRow:row byExtendingSelection:NO];}
 }
 target->syncing=NO;nxs_host_restore_document_positions(control->host,positions);[control->view setNeedsDisplay:YES];[pool drain];return 1;
}
