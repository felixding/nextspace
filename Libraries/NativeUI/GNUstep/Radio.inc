/* Group models bind actual AppKit cells to NSMatrix. No widget, navigation,
 * selection, drawing or tracking implementation lives here. GPL-2.0-or-later. */
@interface NXSRadioAction : NSObject {
 @public NXSControl *control;NSArray *identifiers;NSDictionary *models;
 NSSize preferred;uint64_t actions;
}
- (void)changed:(id)sender;
@end
static NSInteger radio_index(NXSControl *control,NSCell *cell)
{
  if(!cell)return -1;
  NSMatrix *matrix=(NSMatrix *)control->view;NSInteger row,column,rows,columns;
  if(![matrix getRow:&row column:&column ofCell:cell])return -1;
  [matrix getNumberOfRows:&rows columns:&columns];return row*columns+column;
}
static uint64_t radio_identifier(NXSControl *control,NSCell *cell)
{
  NSInteger index=radio_index(control,cell);NXSRadioAction *target=control->target;
  return index>=0&&index<[target->identifiers count]?[[target->identifiers objectAtIndex:index] unsignedLongLongValue]:0;
}
@implementation NXSRadioAction
- (void)dealloc {[identifiers release];[models release];[super dealloc];}
- (void)changed:(id)sender
{
  actions++;
  if(control->changed) {
    NXSControlState state=nxs_gnustep_control_state(control);
    control->changed(control->context,NXS_ACTIVATE,&state);
  }
}
@end
static NSView *radio_create(NXSControl *control)
{
  NSMatrix *matrix=[[NSMatrix alloc] initWithFrame:NSMakeRect(0,0,120,24)
    mode:NSRadioModeMatrix cellClass:[NSButtonCell class] numberOfRows:0 numberOfColumns:1];
  [matrix setAllowsEmptySelection:YES];
  NXSRadioAction *target=[NXSRadioAction new];target->control=control;
  target->identifiers=[NSArray new];target->models=[NSDictionary new];
  control->target=target;[matrix setTarget:target];[matrix setAction:@selector(changed:)];
  return matrix;
}
static void radio_enabled(NXSControl *control)
{
  NXSRadioAction *target=control->target;
  for(NSNumber *identifier in target->identifiers) {
    NSDictionary *model=[target->models objectForKey:identifier];
    [[model objectForKey:@"cell"] setEnabled:control->enabled&&[[model objectForKey:@"enabled"] boolValue]];
  }
  [control->view setNeedsDisplay:YES];
}
int nxs_gnustep_control_radio_items(NXSControl *control,const NXSRadioItem *items,
  uint32_t count,uint32_t columns,uint64_t selected,uint64_t key_cell)
{
  if(!control||control->kind!=NXS_RADIOGROUP||control->destroying||nxs_host_tracking(control->host)||
     count>65536||(!items&&count)||!columns||columns>65536||count%columns||
     (count&&columns>count))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSMutableArray *identifiers=[NSMutableArray array],*titles=[NSMutableArray array];
  NSMutableSet *unique=[NSMutableSet set];
  /* Validate the entire application model before touching any retained cell. */
  for(uint32_t i=0;i<count;i++) {
    if(items[i].size<sizeof(items[i])||!items[i].identifier){[pool drain];return 0;}
    NSNumber *identifier=@(items[i].identifier);
    NSString *title=items[i].title?[NSString stringWithUTF8String:items[i].title]:@"";
    if(!title||[unique containsObject:identifier]){[pool drain];return 0;}
    [identifiers addObject:identifier];[titles addObject:title];[unique addObject:identifier];
  }
  if((selected&&![unique containsObject:@(selected)])||(key_cell&&![unique containsObject:@(key_cell)])) {
    [pool drain];return 0;
  }
  NXSRadioAction *target=control->target;
  /* Let the original owner clear its native selection bookkeeping before
   * handing the same cells to a new matrix. Adding existing cells alone does
   * not import their selected flags into NSMatrix's selection model. */
  NSMatrix *previous=(NSMatrix *)control->view;
  [previous setAllowsEmptySelection:YES];[previous deselectAllCells];
  NSMatrix *matrix=[[NSMatrix alloc] initWithFrame:NSZeroRect mode:NSRadioModeMatrix
    cellClass:[NSButtonCell class] numberOfRows:0 numberOfColumns:columns];
  [matrix setAllowsEmptySelection:YES];
  NSMutableDictionary *models=[NSMutableDictionary dictionary];
  for(uint32_t row=0;row<count/columns;row++) {
    NSMutableArray *cells=[NSMutableArray array];
    for(uint32_t column=0;column<columns;column++) {
      uint32_t index=row*columns+column;NSNumber *identifier=[identifiers objectAtIndex:index];
      NSButtonCell *cell=[[target->models objectForKey:identifier] objectForKey:@"cell"];
      if(!cell) {
        cell=[[[NSButtonCell alloc] initTextCell:[titles objectAtIndex:index]] autorelease];
        [cell setButtonType:NSRadioButton];[cell setBordered:NO];
      }
      [cell setTitle:[titles objectAtIndex:index]];
      [cell setEnabled:control->enabled&&items[index].enabled];
      [cells addObject:cell];
      [models setObject:@{@"cell":cell,@"enabled":@(!!items[index].enabled)} forKey:identifier];
    }
    /* Original cells are retained, including after reorder/title changes. */
    [matrix addRowWithCells:cells];
  }
  /* NSActionCell retains a non-owning controlView for invalidation. Transfer
   * that association before releasing the old matrix; the cells themselves
   * remain the same native objects. */
  for(NSNumber *identifier in target->identifiers)if(![models objectForKey:identifier])
    [[[target->models objectForKey:identifier] objectForKey:@"cell"] setControlView:nil];
  for(NSCell *cell in [matrix cells])[cell setControlView:matrix];
  if(selected) {
    NSCell *cell=[[models objectForKey:@(selected)] objectForKey:@"cell"];NSInteger row,column;
    if([matrix getRow:&row column:&column ofCell:cell])[matrix selectCellAtRow:row column:column];
  }
  [matrix setAllowsEmptySelection:NO];
  if(key_cell)[matrix setKeyCell:[[models objectForKey:@(key_cell)] objectForKey:@"cell"]];
  [matrix sizeToFit];NSSize preferred=[matrix frame].size;
  [matrix setTarget:target];[matrix setAction:@selector(changed:)];
  if(!nxs_host_replace_view(control->host,matrix)){[matrix release];[pool drain];return 0;}
  control->view=matrix;[matrix release];
  [target->identifiers release];target->identifiers=[identifiers copy];
  [target->models release];target->models=[models copy];target->preferred=preferred;
  [pool drain];return 1;
}
NXSRadioState nxs_gnustep_control_radio_state(NXSControl *control)
{
  NXSRadioState state={.size=sizeof(state)};
  if(!control||control->kind!=NXS_RADIOGROUP||control->destroying)return state;
  NSMatrix *matrix=(NSMatrix *)control->view;NXSRadioAction *target=control->target;
  NSInteger rows,columns;[matrix getNumberOfRows:&rows columns:&columns];
  state.count=[target->identifiers count];state.rows=rows;state.columns=columns;
  state.selected=radio_identifier(control,[matrix selectedCell]);
  state.key_cell=radio_identifier(control,[matrix keyCell]);state.actions=target->actions;
  return state;
}
NXSRect nxs_gnustep_control_radio_item_rect(NXSControl *control,uint64_t identifier)
{
  if(!control||control->kind!=NXS_RADIOGROUP||control->destroying||!identifier)return (NXSRect){0};
  NXSRadioAction *target=control->target;NSMatrix *matrix=(NSMatrix *)control->view;
  NSCell *cell=[[target->models objectForKey:@(identifier)] objectForKey:@"cell"];
  NSInteger row,column;
  return cell&&[matrix getRow:&row column:&column ofCell:cell]?
    nxs_host_rect_from_view(control->host,matrix,[matrix cellFrameAtRow:row column:column]):(NXSRect){0};
}
