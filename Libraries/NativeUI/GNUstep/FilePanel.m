/* Original native file panels and accessory controls. No file browser,
 * editor, modal loop, selection or overwrite-confirmation UI is copied.
 * GPL-2.0-or-later. */
#import "ViewHost.h"
#include "Provider.h"
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <GNUstepGUI/GSDisplayServer.h>
@interface NSObject (NXSForeignParent)
- (BOOL)setforeignparent:(NSString *)handle forwindow:(int)window;
@end
@interface NSWindow (NXSDeferredNativeWindow)
- (void)_initBackendWindow;
@end
@class NXSFileDelegate;
struct NXSFilePanel {
  NSSavePanel *panel;
  NXSFileDelegate *delegate;
  NSArray *choices,*uris,*batch;
  NSString *directory,*name;
  NXSFileAllows allows;
  void *context;
  pthread_t owner;
  unsigned depth,filter;
  int mode,running,cancelled,configured,result;
};
static NXSFilePanel *current_panel,*running_panel;
static int owned(NXSFilePanel *p)
{return p&&p==current_panel&&pthread_equal(p->owner,pthread_self());}
static NSString *text(const char *value)
{return value&&strnlen(value,65537)<=65536?[NSString stringWithUTF8String:value]:nil;}
@interface NXSFileDelegate : NSObject { @public NXSFilePanel *owner; }
- (void)filterChanged:(id)sender;
- (void)continueCancellation;
@end
@implementation NXSFileDelegate
- (BOOL)panel:(id)sender shouldShowFilename:(NSString *)filename
{
  BOOL directory=NO;
  if([[NSFileManager defaultManager] fileExistsAtPath:filename isDirectory:&directory]&&directory)return YES;
  if(!owner->allows)return YES;
  owner->depth++;
  int accepted=0;
  @try {accepted=owner->allows(owner->context,[filename UTF8String],owner->filter);}
  @finally {owner->depth--;}
  return !!accepted;
}
- (BOOL)panel:(id)sender isValidFilename:(NSString *)filename
{return owner->mode==NXS_FILE_SAVE||[self panel:sender shouldShowFilename:filename];}
- (void)filterChanged:(id)sender
{
  owner->filter=(unsigned)[sender indexOfSelectedItem];
  [owner->panel validateVisibleColumns];
}
- (void)continueCancellation
{
  if(!owner->running||!owner->cancelled)return;
  NSWindow *modal=[NSApp modalWindow];
  if(modal==owner->panel)[owner->panel cancel:nil];
  else {
    if(modal)[NSApp stopModalWithCode:NSCancelButton];
    /* AppKit restores the previous modal window when an alert finishes.
     * Defer cancelling that original window until its own session resumes. */
    [self performSelector:@selector(continueCancellation) withObject:nil afterDelay:.001
      inModes:@[NSModalPanelRunLoopMode]];
  }
  /* stopModal changes session state but does not wake a pending DPSPeekEvent. */
  [NSApp postEvent:[NSEvent otherEventWithType:NSApplicationDefined location:NSZeroPoint
    modifierFlags:0 timestamp:0 windowNumber:0 context:nil subtype:0 data1:0 data2:0] atStart:NO];
}
@end
static NSButton *accept_button(NSView *view,id panel)
{
  if([view isKindOfClass:[NSButton class]]&&[(NSButton *)view target]==panel&&[(NSButton *)view action]==@selector(ok:))return (NSButton *)view;
  for(NSView *child in [view subviews]){NSButton *button=accept_button(child,panel);if(button)return button;}
  return nil;
}
static void add_title(NSPopUpButton *popup,NSString *title)
{NSMenuItem *item=[[NSMenuItem alloc] initWithTitle:title action:NULL keyEquivalent:@""];[[popup menu] addItem:item];[item release];}
static NSTextField *label(NSString *title)
{
  NSTextField *view=[[[NSTextField alloc] initWithFrame:NSZeroRect] autorelease];
  [view setStringValue:title];[view setEditable:NO];[view setSelectable:NO];
  [view setBordered:NO];[view setDrawsBackground:NO];[view sizeToFit];return view;
}
int nxs_gnustep_file_panel_active(void){return running_panel!=NULL;}
unsigned nxs_gnustep_file_panel_parent_capabilities(void)
{return [GSCurrentServer() respondsToSelector:@selector(setforeignparent:forwindow:)]?1:0;}
NXSFilePanel *nxs_gnustep_file_panel_create(int mode,NXSFileAllows allows,void *context)
{
  if(current_panel||(mode!=NXS_FILE_OPEN&&mode!=NXS_FILE_SAVE))return NULL;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(!nxs_host_initialize()){[pool drain];return NULL;}
  NXSFilePanel *p=calloc(1,sizeof(*p));if(!p){[pool drain];return NULL;}
  p->mode=mode;p->allows=allows;p->context=context;p->owner=pthread_self();p->result=-1;
  /* The original factory selects the native theme's panel class and resets
   * that shared panel's original defaults for each request. */
  p->panel=[(mode==NXS_FILE_OPEN?[NSOpenPanel openPanel]:[NSSavePanel savePanel]) retain];
  [p->panel setReleasedWhenClosed:NO];
  p->delegate=[NXSFileDelegate new];p->delegate->owner=p;current_panel=p;
  [pool drain];return p;
}
int nxs_gnustep_file_panel_configure(NXSFilePanel *p,const NXSFilePanelConfig *c)
{
  if(!owned(p)||p->running||p->depth||!c||c->size<offsetof(NXSFilePanelConfig,parent_window)||c->flags&~7u||
     c->filter_count>64||c->choice_count>64||(c->filter_count&&(!c->filter_titles||c->selected_filter>=c->filter_count))||
     (c->choice_count&&!c->choices)||c->batch_count>4096||(c->batch_count&&(!c->batch_names||p->mode!=NXS_FILE_OPEN||(c->flags&3)!=NXS_FILE_DIRECTORY))||(p->mode==NXS_FILE_SAVE&&(c->flags&3)))return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  NSString *title=c->title?text(c->title):@"",*directory=c->directory?text(c->directory):nil;
  NSString *name=c->name?text(c->name):@"",*accept=c->accept_label?text(c->accept_label):nil;
  const char *identifier=c->size>=sizeof(*c)?c->parent_window:NULL;
  NSString *parent=identifier?text(identifier):nil;
  if(identifier&&!parent){[pool drain];return 0;}
  if([parent length]&&![parent hasPrefix:@"wayland:"]){[pool drain];return 0;}
  if(!title||!name||(c->directory&&!directory)||(c->accept_label&&!accept)){[pool drain];return 0;}
  NSMutableArray *filterTitles=[NSMutableArray array];
  for(unsigned i=0;i<c->filter_count;i++){NSString *value=text(c->filter_titles[i]);if(!value){[pool drain];return 0;}[filterTitles addObject:value];}
  NSMutableArray *choices=[NSMutableArray array],*labels=[NSMutableArray array];
  for(unsigned i=0;i<c->choice_count;i++) {
    const NXSFileChoice *choice=&c->choices[i];NSString *title=text(choice->label);
    if(choice->size<sizeof(*choice)||!title||choice->reserved||choice->count>64||
       (choice->count&&(!choice->options||choice->selected>=choice->count))||(!choice->count&&choice->selected>1)){[pool drain];return 0;}
    if(!choice->count) {
      NSButton *button=[[[NSButton alloc] initWithFrame:NSZeroRect] autorelease];
      [button setButtonType:NSSwitchButton];[button setTitle:title];[button setState:choice->selected];[button sizeToFit];
      [choices addObject:button];[labels addObject:[NSNull null]];
    } else {
      NSPopUpButton *popup=[[[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO] autorelease];
      for(unsigned j=0;j<choice->count;j++){NSString *option=text(choice->options[j]);if(!option){[pool drain];return 0;}add_title(popup,option);}
      [popup selectItemAtIndex:choice->selected];[popup sizeToFit];[choices addObject:popup];[labels addObject:label(title)];
    }
  }
  NSMutableArray *batch=[NSMutableArray array];
  for(unsigned i=0;i<c->batch_count;i++) {
    NSString *value=text(c->batch_names[i]);
    if(![value length]||[value isAbsolutePath]||![value isEqual:[value lastPathComponent]]||[value isEqual:@"."]||[value isEqual:@".."]) {[pool drain];return 0;}
    [batch addObject:value];
  }
  id server=GSCurrentServer();
  if([server respondsToSelector:@selector(setforeignparent:forwindow:)]) {
    /* The original file-panel factory defers its native window. Initialize
     * that original window without presenting it, so the imported parent is
     * installed before its first show. No window or panel is recreated. */
    if(![p->panel windowNumber]) {
      if(![p->panel respondsToSelector:@selector(_initBackendWindow)]){[pool drain];return 0;}
      [p->panel _initBackendWindow];
    }
    if(![server setforeignparent:[parent length]?[parent substringFromIndex:8]:nil forwindow:(int)[p->panel windowNumber]]) {
      [pool drain];return 0;
    }
  } else if([parent length]){[pool drain];return 0;}
  p->depth++;
  @try {
    [p->batch release];p->batch=[batch copy];
    p->filter=c->selected_filter;[p->directory release];p->directory=[directory copy];[p->name release];p->name=[name copy];
    [p->choices release];p->choices=[choices copy];[p->uris release];p->uris=nil;
    [p->panel setDelegate:p->delegate];
    if([title length])[p->panel setTitle:title];
    [p->panel setShowsHiddenFiles:!!(c->flags&NXS_FILE_HIDDEN)];
    if(p->mode==NXS_FILE_OPEN) {
      NSOpenPanel *open=(NSOpenPanel *)p->panel;
      [open setCanChooseFiles:!(c->flags&NXS_FILE_DIRECTORY)];[open setCanChooseDirectories:!!(c->flags&NXS_FILE_DIRECTORY)];
      [open setAllowsMultipleSelection:!!(c->flags&NXS_FILE_MULTIPLE)];
    }
    if([accept length])[accept_button([p->panel contentView],p->panel) setTitle:accept];
    NSUInteger rows=c->choice_count+(c->filter_count?1:0);
    NSView *accessory=[[[NSView alloc] initWithFrame:NSMakeRect(0,0,420,rows*30)] autorelease];
    unsigned row=0;
    if(c->filter_count) {
      NSPopUpButton *popup=[[[NSPopUpButton alloc] initWithFrame:NSMakeRect(0,(rows-1)*30,420,26) pullsDown:NO] autorelease];
      for(NSString *title in filterTitles)add_title(popup,title);[popup selectItemAtIndex:p->filter];
      [popup setTarget:p->delegate];[popup setAction:@selector(filterChanged:)];[accessory addSubview:popup];row++;
    }
    for(unsigned i=0;i<c->choice_count;i++,row++) {
      NSControl *control=[choices objectAtIndex:i];id title=[labels objectAtIndex:i];CGFloat y=(rows-row-1)*30;
      if(title!=[NSNull null]){[title setFrameOrigin:NSMakePoint(0,y+4)];[accessory addSubview:title];[control setFrame:NSMakeRect(180,y,240,26)];}
      else [control setFrame:NSMakeRect(0,y,420,26)];
      [accessory addSubview:control];
    }
    [p->panel setAccessoryView:rows?accessory:nil];p->configured=1;p->result=-1;
  } @finally {p->depth--;}
  [pool drain];return 1;
}
int nxs_gnustep_file_panel_run(NXSFilePanel *p)
{
  if(!owned(p)||!p->configured||p->running||p->depth||running_panel)return 2;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];p->running=1;p->cancelled=0;running_panel=p;
  @try {
    /* A portal backend runs outside the requesting application's process.
     * Re-enter native application activation for each user-requested panel,
     * including after the previous panel returned focus to its caller. */
    [NSApp activateIgnoringOtherApps:YES];
    NSInteger code=p->mode==NXS_FILE_OPEN?[(NSOpenPanel *)p->panel runModalForDirectory:p->directory file:p->name types:nil]:
      [p->panel runModalForDirectory:p->directory file:p->name];
    p->result=code==NSOKButton&&!p->cancelled?0:1;
    if(!p->result) {
      NSArray *paths=p->mode==NXS_FILE_OPEN?[(NSOpenPanel *)p->panel filenames]:@[[p->panel filename]];
      if([p->batch count]) {
        NSString *directory=[paths count]==1?[paths objectAtIndex:0]:nil;
        NSMutableArray *targets=[NSMutableArray array];unsigned existing=0;
        for(NSString *name in p->batch) {
          NSString *target=[directory stringByAppendingPathComponent:name];if(!target)continue;
          if([[NSFileManager defaultManager] fileExistsAtPath:target])existing++;
          [targets addObject:target];
        }
        if(existing&&NSRunAlertPanel(@"Replace files?",@"The selected folder contains %u of the files to save. Replace them?",@"Replace",@"Cancel",nil,existing)!=NSAlertDefaultReturn)p->result=1;
        paths=targets;
      }
      if(p->cancelled)p->result=1;
      NSMutableArray *uris=[NSMutableArray array];
      for(NSString *path in paths){NSURL *url=[NSURL fileURLWithPath:path];if([url isFileURL])[uris addObject:[url absoluteString]];}
      [p->uris release];p->uris=p->result?nil:[uris copy];if(!p->result&&![uris count])p->result=2;
    }
  } @catch(NSException *exception){p->result=2;}
  @finally {
    [NSObject cancelPreviousPerformRequestsWithTarget:p->delegate selector:@selector(continueCancellation) object:nil];
    running_panel=NULL;p->running=0;
    if([p->panel isKeyWindow])[p->panel resignKeyWindow];
    [p->panel orderOut:nil];
  }
  int result=p->result;[pool drain];return result;
}
int nxs_gnustep_file_panel_cancel(NXSFilePanel *p)
{
  if(!owned(p)||!p->running)return 0;
  p->cancelled=1;
  [NSObject cancelPreviousPerformRequestsWithTarget:p->delegate selector:@selector(continueCancellation) object:nil];
  [p->delegate continueCancellation];
  return 1;
}
NXSFilePanelState nxs_gnustep_file_panel_state(NXSFilePanel *p)
{
  return owned(p)?(NXSFilePanelState){.size=sizeof(NXSFilePanelState),.result=p->running?-1:p->result,.count=(uint32_t)[p->uris count],.selected_filter=p->filter}:
    (NXSFilePanelState){.size=sizeof(NXSFilePanelState),.result=2};
}
size_t nxs_gnustep_file_panel_result(NXSFilePanel *p,uint32_t index,char *buffer,size_t capacity)
{
  if(!owned(p)||p->running||p->result||index>=[p->uris count])return 0;
  const char *value=[[p->uris objectAtIndex:index] UTF8String];size_t required=strlen(value)+1;
  if(buffer&&capacity>=required)memcpy(buffer,value,required);return required;
}
int nxs_gnustep_file_panel_choice(NXSFilePanel *p,uint32_t index)
{
  if(!owned(p)||index>=[p->choices count])return -1;
  id control=[p->choices objectAtIndex:index];
  return [control isKindOfClass:[NSPopUpButton class]]?(int)[control indexOfSelectedItem]:!![control state];
}
int nxs_gnustep_file_panel_destroy(NXSFilePanel *p)
{
  if(!owned(p)||p->running||p->depth)return 0;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];[p->panel setDelegate:nil];[p->panel setAccessoryView:nil];
  [p->panel orderOut:nil];[p->panel release];[p->delegate release];[p->choices release];[p->uris release];[p->batch release];
  [p->directory release];[p->name release];current_panel=NULL;free(p);[pool drain];return 1;
}
