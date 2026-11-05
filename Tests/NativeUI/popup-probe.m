/* Real native popup/menu actions through the public C ABI. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <fcntl.h>
#include <unistd.h>
static NXSControl *control;
static unsigned actions,pumps,phase;
static int destination=4,deferred;
static double pointer_x,pointer_y;
static void changed(void *unused,int event,const NXSControlState *state)
{
  assert(event==NXS_VALUE_CHANGED);assert(state->value==destination);actions++;
  assert(!nxs_control_destroy(control));deferred++;
}
static void pump(void *unused)
{
  assert(++pumps<1000);
  NXSPopupState state=nxs_control_popup_state(control);assert(state.visible);
  assert(!nxs_control_destroy(control));
  assert(!nxs_control_popup_items(control,NULL,0,-1));
  if(!phase) {
    NXSRect rect=nxs_control_popup_item_rect(control,destination);assert(rect.width>0&&rect.height>0);
    pointer_x=rect.x+rect.width/2;pointer_y=rect.y+rect.height/2;
    nxs_control_send(control,NXS_MOVE,pointer_x,pointer_y,0);phase=1;
  } else if(phase==1&&state.highlighted==destination) {
    NXSRect rect=nxs_control_popup_item_rect(control,destination);
    nxs_control_send(control,NXS_RELEASE,rect.x+rect.width/2,rect.y+rect.height/2,0);phase=2;
  } else if(phase==1) {
    /* The compositor can reposition an independently mapped menu after its
     * first configure. Follow the native item's current geometry in this
     * synthetic pointer probe; no item dimensions or placement are assumed. */
    NXSRect rect=nxs_control_popup_item_rect(control,destination);
    double x=rect.x+rect.width/2,y=rect.y+rect.height/2;
    if(x!=pointer_x||y!=pointer_y){pointer_x=x;pointer_y=y;nxs_control_send(control,NXS_MOVE,x,y,0);}
  }
}
static void hold(const char *stage)
{
  if(getenv("NXS_NATIVE_UI_POPUP_HOLD")){
    printf("{\"event\":\"%s\"}\n",stage);fflush(stdout);
    for(;;){fd_set input;FD_ZERO(&input);FD_SET(STDIN_FILENO,&input);struct timeval timeout={0};
      if(select(STDIN_FILENO+1,&input,NULL,NULL,&timeout)>0)break;
      nxs_native_ui_dispatch_events(.005);
    }
    assert(getchar()=='\n');
  }
}
static void key(unsigned logical,const char *text)
{
  NXSKeyEvent event={.size=sizeof(event),.type=NXS_KEY_DOWN,.key=logical,.text=text};
  assert(nxs_control_key(control,&event)==NXS_INPUT_HANDLED);
}
static void save(const char *directory,const char *name,double scale)
{
  if(!directory)return;
  NXSBitmap image=nxs_control_draw(control,scale);assert(image.pixels);
  char path[4096];snprintf(path,sizeof(path),"%s/%s.argb",directory,name);
  FILE *file=fopen(path,"wb");assert(file);assert(fwrite(image.pixels,image.stride,image.height,file)==(size_t)image.height);assert(!fclose(file));
}
int main(int argc,char **argv)
{
  if(argc>1&&!strcmp(argv[1],"--expect-no-popup")){
    assert(!nxs_control_popup_capabilities());assert(!nxs_control_create(NXS_POPUP,NULL,NULL,NULL));
    assert(!nxs_control_popup_items(NULL,NULL,0,-1));assert(!nxs_control_popup_state(NULL).visible);
    assert(nxs_control_popup_state(NULL).highlighted==-1);
    assert(!nxs_native_ui_source_capabilities()&&!nxs_native_ui_source_create(-1));
    puts("{\"older_provider_without_popup\":true}");return 0;
  }
  const char *directory=argc>1&&argv[1][0]!='-'?argv[1]:NULL;
  NSAutoreleasePool *pool=[NSAutoreleasePool new];
  assert(nxs_native_ui_source_capabilities()==1);
  int descriptors[2];assert(!pipe(descriptors));
  NXSEventSource *source=nxs_native_ui_source_create(descriptors[0]);assert(source);
  assert(!nxs_native_ui_source_create(descriptors[0])&&!nxs_native_ui_source_create(-1));
  assert(write(descriptors[1],"x",1)==1);nxs_native_ui_dispatch_events(.5);
  assert(nxs_native_ui_source_destroy(source));
  char byte;assert(read(descriptors[0],&byte,1)==1&&byte=='x');
  assert(fcntl(descriptors[0],F_GETFD)>=0);close(descriptors[0]);close(descriptors[1]);
  assert(nxs_control_popup_capabilities()==NXS_POPUP_ITEMS);
  control=nxs_control_create(NXS_POPUP,changed,pump,NULL);assert(control);
  NXSControlConfig config={.size=sizeof(config),.width=180,.height=24,.maximum=1,.value=0,.enabled=1};
  assert(nxs_control_sync(control,&config));assert(nxs_control_set_screen_origin(control,240,160));
  NXSPopupItem items[]={
    {sizeof(NXSPopupItem),"First",1,0},{sizeof(NXSPopupItem),"Disabled",0,0},
    {sizeof(NXSPopupItem),"",0,1},{sizeof(NXSPopupItem),"Repeated",1,0},
    {sizeof(NXSPopupItem),"First",1,0}};
  assert(nxs_control_popup_items(control,items,5,0));assert(nxs_control_state(control).value==0);
  NSPopUpButton *native=nil;
  for(NSWindow *window in [NSApp windows])for(NSView *view in [[window contentView] subviews])
    if([view isKindOfClass:[NSPopUpButton class]])native=(NSPopUpButton *)view;
  assert(native&&[native numberOfItems]==5);
  assert([[native itemTitleAtIndex:0] isEqual:[native itemTitleAtIndex:4]]);
  assert(![[native itemAtIndex:1] isEnabled]&&[[native itemAtIndex:2] isSeparatorItem]);
  assert(!nxs_control_popup_item_rect(control,0).width);
  assert(!nxs_control_set_screen_origin(control,NAN,0));
  assert(!nxs_control_popup_items(control,items,5,5));assert(!nxs_control_popup_items(control,items,5,2));
  NXSPopupItem bad={sizeof(bad),"\xff",1,0};assert(!nxs_control_popup_items(control,&bad,1,0));
  assert([native numberOfItems]==5&&[native indexOfSelectedItem]==0);
  save(directory,"popup-normal",1);save(directory,"popup-150",1.5);
  hold("host-live");
  assert(nxs_control_focus(control,1));save(directory,"popup-focused",1);
  key(NXS_KEY_TEXT," ");assert(nxs_control_popup_state(control).visible);
  assert([[[native menu] window] isVisible]);
  assert(nxs_control_popup_state(control).highlighted==[[[native menu] menuRepresentation] highlightedItemIndex]);
  assert(nxs_control_popup_state(control).frame.height>24);
  hold("popup-live");
  key(NXS_KEY_ESCAPE,NULL);assert(!nxs_control_popup_state(control).visible);assert(!actions);
  hold("popup-closed");
  key(NXS_KEY_TEXT," ");key(NXS_KEY_DOWN_ARROW,NULL);key(NXS_KEY_ENTER,NULL);
  assert(!actions&&nxs_control_state(control).value==0);key(NXS_KEY_ESCAPE,NULL);
  assert(nxs_control_popup_items(control,items,5,0));
  /* Native arrows define highlight movement. The bridge neither binds these
   * keys nor substitutes a widget selection algorithm. */
  key(NXS_KEY_TEXT," ");key(NXS_KEY_DOWN_ARROW,NULL);key(NXS_KEY_DOWN_ARROW,NULL);key(NXS_KEY_DOWN_ARROW,NULL);
  destination=nxs_control_popup_state(control).highlighted;
  assert(destination==3);key(NXS_KEY_ENTER,NULL);assert(actions==1&&deferred==1);
  assert([native indexOfSelectedItem]==destination&&!nxs_control_popup_state(control).visible);
  assert(nxs_control_popup_items(control,items,5,0));destination=4;
  nxs_control_track(control,18,12,0);
  assert(phase==2&&actions==2&&deferred==2&&nxs_control_state(control).value==4);
  assert(!nxs_control_popup_state(control).visible);
  config.enabled=0;config.value=4;assert(nxs_control_sync(control,&config));save(directory,"popup-disabled",1);
  unsigned before=actions;nxs_control_track(control,18,12,0);assert(actions==before);
  NXSKeyEvent disabled={.size=sizeof(disabled),.key=NXS_KEY_TEXT,.text=" "};
  assert(nxs_control_key(control,&disabled)==NXS_INPUT_UNHANDLED&&!nxs_control_popup_state(control).visible);
  config.enabled=1;assert(nxs_control_sync(control,&config));
  assert(nxs_control_popup_items(control,NULL,0,-1)&&nxs_control_state(control).value==-1);
  assert(nxs_control_popup_items(control,items,5,0));assert(nxs_control_focus(control,1));
  key(NXS_KEY_TEXT," ");assert(nxs_control_popup_state(control).visible);
  NSMenu *menu=[[native menu] retain];
  assert(nxs_control_destroy(control));control=NULL;
  assert(![[menu window] isVisible]);[menu release];
  puts("{\"native_popup\":true,\"duplicate_labels\":true,\"disabled_item_no_action\":true,\"separator\":true,\"keyboard_actions\":1,\"mouse_actions\":1,\"deferred_destruction\":2,\"empty_model\":true,\"invalid_model_atomic\":true,\"destroy_open_menu\":true,\"native_descriptor_wakeup\":true}");
  [pool drain];return 0;
}
