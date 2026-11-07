/* Application list data for an ordinary one-column NSBrowser. Native cells,
 * selection, key interpretation, scrolling and drawing stay in AppKit.
 * GPL-2.0-or-later. */
@interface NXSListAction : NSObject {
 @public NXSControl *control;NSArray *models;unsigned flags;uint64_t actions;BOOL syncing;
}
- (void)changed:(id)sender;
@end
static NSMatrix *list_matrix(NXSControl *control)
{return [(NSBrowser *)control->view matrixInColumn:0];}
static uint64_t list_identifier(NXSControl *control,NSCell *cell)
{
  NSInteger row,column;NXSListAction *target=control->target;
  return cell&&[list_matrix(control) getRow:&row column:&column ofCell:cell]&&row>=0&&row<[target->models count]?
    [[[target->models objectAtIndex:row] objectForKey:@"id"] unsignedLongLongValue]:0;
}
@implementation NXSListAction
- (void)dealloc {[models release];[super dealloc];}
- (NSInteger)browser:(NSBrowser *)browser numberOfRowsInColumn:(NSInteger)column
{return column==0?[models count]:0;}
- (void)browser:(NSBrowser *)browser willDisplayCell:(NSBrowserCell *)cell atRow:(NSInteger)row column:(NSInteger)column
{
  NSDictionary *model=[models objectAtIndex:row];
  [cell setStringValue:[model objectForKey:@"title"]];[cell setLeaf:YES];
  [cell setEnabled:control->enabled&&[[model objectForKey:@"enabled"] boolValue]];
}
- (void)changed:(id)sender
{
  if(syncing||control->destroying)return;
  actions++;
  if(control->changed) {
    NXSControlState state=nxs_gnustep_control_state(control);
    control->changed(control->context,NXS_VALUE_CHANGED,&state);
  }
}
@end
static NSView *list_create(NXSControl *control)
{
  NSBrowser *browser=[[NSBrowser alloc] initWithFrame:NSMakeRect(0,0,180,96)];
  NXSListAction *target=[NXSListAction new];target->control=control;target->models=[NSArray new];control->target=target;
  [browser setMaxVisibleColumns:1];[browser setMinColumnWidth:1];
  [browser setTitled:NO];[browser setSeparatesColumns:NO];[browser setHasHorizontalScroller:NO];
  [browser setAllowsEmptySelection:YES];[browser setAllowsMultipleSelection:NO];
  [browser setDelegate:target];[browser setTarget:target];[browser setAction:@selector(changed:)];
  [browser loadColumnZero];return browser;
}
static void list_enabled(NXSControl *control)
{
  NSBrowser *browser=(NSBrowser *)control->view;NXSListAction *target=control->target;
  [browser setEnabled:control->enabled];NSMatrix *matrix=list_matrix(control);[matrix setEnabled:control->enabled];
  for(NSUInteger i=0;i<[target->models count];i++)
    [[matrix cellAtRow:i column:0] setEnabled:control->enabled&&[[[target->models objectAtIndex:i] objectForKey:@"enabled"] boolValue]];
  [browser setNeedsDisplay:YES];
}
int nxs_gnustep_control_list_items(NXSControl *control,const NXSListItem *items,uint32_t count,unsigned flags,uint64_t key)
{
  if(!control||control->kind!=NXS_LISTBOX||control->destroying||nxs_host_tracking(control->host)||
     count>65536||(!items&&count)||(flags&~NXS_LIST_MULTIPLE))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMutableArray *models=[NSMutableArray array];NSMutableSet *unique=[NSMutableSet set];unsigned selected=0;
  for(uint32_t i=0;i<count;i++) {
    if(items[i].size<sizeof(items[i])||!items[i].identifier){[pool drain];return 0;}
    NSNumber *identifier=@(items[i].identifier);NSString *title=items[i].title?[NSString stringWithUTF8String:items[i].title]:@"";
    if(!title||[unique containsObject:identifier]){[pool drain];return 0;}
    [unique addObject:identifier];selected+=!!items[i].selected;
    [models addObject:@{@"id":identifier,@"title":title,@"enabled":@(!!items[i].enabled)}];
  }
  if((!(flags&NXS_LIST_MULTIPLE)&&selected>1)||(key&&![unique containsObject:@(key)])){[pool drain];return 0;}
  NXSListAction *target=control->target;NSBrowser *browser=(NSBrowser *)control->view;
  BOOL rows_changed=![models isEqualToArray:target->models],changed=rows_changed||flags!=target->flags;
  NSMatrix *matrix=list_matrix(control);NSArray *selection=[matrix selectedCells];
  for(uint32_t i=0;i<count&&!changed;i++)changed=!!items[i].selected!=[selection containsObject:[matrix cellAtRow:i column:0]];
  if(!changed&&(!key||key==list_identifier(control,[matrix keyCell]))){[pool drain];return 1;}
  BOOL focused=nxs_host_focused(control->host);target->syncing=YES;
  [target->models release];target->models=[models copy];target->flags=flags;
  [browser setAllowsMultipleSelection:!!(flags&NXS_LIST_MULTIPLE)];
  if(rows_changed)[browser reloadColumn:0];
  matrix=list_matrix(control);[matrix deselectAllCells];
  for(uint32_t i=0;i<count;i++)if(items[i].selected)[matrix selectCellAtRow:i column:0];
  if(key)for(uint32_t i=0;i<count;i++)if(items[i].identifier==key)[matrix setKeyCell:[matrix cellAtRow:i column:0]];
  list_enabled(control);if(focused)nxs_host_focus(control->host,1);
  target->syncing=NO;[pool drain];return 1;
}
NXSListState nxs_gnustep_control_list_state(NXSControl *control)
{
  NXSListState state={.size=sizeof(state)};
  if(!control||control->kind!=NXS_LISTBOX||control->destroying)return state;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];NXSListAction *target=control->target;
  NSMatrix *matrix=list_matrix(control);NSRect visible=[matrix visibleRect];NSSize content=[matrix bounds].size;
  state.count=[target->models count];state.flags=target->flags;state.selected_count=[[matrix selectedCells] count];
  state.primary=list_identifier(control,[matrix selectedCell]);state.key_cell=list_identifier(control,[matrix keyCell]);state.actions=target->actions;
  state.visible=(NXSRect){visible.origin.x,visible.origin.y,visible.size.width,visible.size.height};state.content=(NXSSize){content.width,content.height};
  [pool drain];return state;
}
size_t nxs_gnustep_control_list_selection(NXSControl *control,uint64_t *items,size_t capacity)
{
  if(!control||control->kind!=NXS_LISTBOX||control->destroying||(!items&&capacity))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];NSArray *selection=[list_matrix(control) selectedCells];size_t count=[selection count];
  if(items&&capacity>=count)for(size_t i=0;i<count;i++)items[i]=list_identifier(control,[selection objectAtIndex:i]);
  [pool drain];return count;
}
NXSRect nxs_gnustep_control_list_item_rect(NXSControl *control,uint64_t identifier)
{
  if(!control||control->kind!=NXS_LISTBOX||control->destroying||!identifier)return (NXSRect){0};
  NXSListAction *target=control->target;NSMatrix *matrix=list_matrix(control);
  for(NSUInteger i=0;i<[target->models count];i++)if([[[target->models objectAtIndex:i] objectForKey:@"id"] unsignedLongLongValue]==identifier)
    return nxs_host_rect_from_view(control->host,matrix,[matrix cellFrameAtRow:i column:0]);
  return (NXSRect){0};
}
int nxs_gnustep_control_list_scroll(NXSControl *control,double x,double y)
{
  if(!control||control->kind!=NXS_LISTBOX||control->destroying||!isfinite(x)||!isfinite(y)||nxs_host_tracking(control->host))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];NSMatrix *matrix=list_matrix(control);NSClipView *clip=(NSClipView *)[matrix superview];
  [clip scrollToPoint:[clip constrainScrollPoint:NSMakePoint(x,y)]];[(NSScrollView *)[clip superview] reflectScrolledClipView:clip];
  [control->view setNeedsDisplay:YES];[pool drain];return 1;
}
