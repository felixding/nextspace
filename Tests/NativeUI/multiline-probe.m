/* Multiline contract and independent native-reference fixture. GPL-2.0-or-later. */
#import <AppKit/AppKit.h>
#include "NativeUI.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct Probe {NXSControl *control;unsigned changes,proposals;int allow,release;double x,y;const char *selector;};
static void pump(void *context)
{struct Probe *p=context;if(p->release){p->release=0;nxs_control_send(p->control,NXS_RELEASE,p->x,p->y,0);}}
static void click(struct Probe *p,double x,double y,unsigned clicks)
{p->x=x;p->y=y;p->release=1;assert(nxs_control_track_clicks(p->control,x,y,0,clicks));assert(!p->release);}
static void changed(void *context,int event,const NXSControlState *state)
{
  struct Probe *p=context;assert(event==NXS_TEXT_CHANGED&&state->tracking);
  assert(!nxs_control_destroy(p->control));p->changes++;
}
static int proposal(void *context,const NXSTextEdit *edit)
{
  struct Probe *p=context;p->proposals++;
  assert(!nxs_control_destroy(p->control));
  if(p->selector)assert(edit->command&&!strcmp(edit->command,p->selector));
  return p->allow;
}
static void model(struct Probe *p,const char *value,uint64_t start,uint64_t length,int editable)
{
  NXSTextModel m={.size=sizeof(m),.text=value,.selection_start=start,.selection_length=length,.editable=editable};
  assert(nxs_control_text_sync(p->control,&m));
}
static NXSTextState value(struct Probe *p,const char *expected)
{
  char text[4096];NXSTextState state={.size=sizeof(state)};
  size_t count=nxs_control_text_get(p->control,text,sizeof(text),&state);
  if(count!=strlen(expected)+1||strcmp(text,expected))
    fprintf(stderr,"Synthetic multiline fixture expected <%s>, got <%s>\n",expected,text);
  assert(count==strlen(expected)+1&&!strcmp(text,expected));return state;
}
static void key(struct Probe *p,unsigned logical,const char *text,unsigned modifiers)
{
  NXSKeyEvent e={.size=sizeof(e),.type=NXS_KEY_DOWN,.key=logical,.text=text,.unmodified_text=text,.modifiers=modifiers};
  int result=nxs_control_key(p->control,&e);
  if(result!=NXS_INPUT_HANDLED)fprintf(stderr,"Synthetic multiline key logical=%u modifiers=%u result=%d\n",logical,modifiers,result);
  assert(result==NXS_INPUT_HANDLED);
}
static void save(const char *directory,const char *name,NXSBitmap bitmap)
{
  assert(bitmap.pixels&&bitmap.width>0&&bitmap.height>0);
  char path[1024];snprintf(path,sizeof(path),"%s/%s.argb",directory,name);
  FILE *file=fopen(path,"wb");assert(file);
  assert(fwrite(bitmap.pixels,bitmap.stride,bitmap.height,file)==(size_t)bitmap.height);fclose(file);
}
static const char *long_text="First line\nSecond line\nThird line\nFourth line\nFifth line\nSixth line\nSeventh line\nEighth line\nNinth line\nTenth line\n";
static const char *wrapped="An ordinary native multiline editor wraps this sentence using its own text layout and scroll view.";
static void reference(const char *directory)
{
  [NSApplication sharedApplication];
  NSScrollView *scroll=[[NSScrollView alloc] initWithFrame:NSMakeRect(0,0,180,96)];
  [scroll setBorderType:NSBezelBorder];[scroll setHasVerticalScroller:YES];[scroll setAutohidesScrollers:YES];
  NSTextView *text=[[NSTextView alloc] initWithFrame:NSMakeRect(0,0,[scroll contentSize].width,[scroll contentSize].height)];
  [text setRichText:NO];[text setAllowsUndo:YES];
  [text setMinSize:NSZeroSize];[text setMaxSize:NSMakeSize(FLT_MAX,FLT_MAX)];
  [text setHorizontallyResizable:NO];[text setVerticallyResizable:YES];
  [text setAutoresizingMask:NSViewWidthSizable];[[text textContainer] setWidthTracksTextView:YES];
  [scroll setDocumentView:text];
  NSWindow *window=[[NSWindow alloc] initWithContentRect:[scroll bounds] styleMask:NSBorderlessWindowMask backing:NSBackingStoreBuffered defer:NO];
  [[window contentView] addSubview:scroll];
  const char *values[]={"Alpha\nBeta",long_text,wrapped};const char *names[]={"short","scrolling","wrapped"};
  for(unsigned i=0;i<3;i++) {
    if(i==2){[window setContentSize:NSMakeSize(100,96)];[scroll setFrameSize:NSMakeSize(100,96)];}
    [text setString:[NSString stringWithUTF8String:values[i]]];[text sizeToFit];[text setSelectedRange:NSMakeRange(0,0)];
    if(i==1)assert([text frame].size.height>[scroll contentSize].height);
    if(i==1) {
      NSScroller *bar=[scroll verticalScroller];NSRect arrow=[bar rectForPart:NSScrollerIncrementLine];
      NSPoint point=[scroll convertPoint:NSMakePoint(NSMidX(arrow),NSMidY(arrow)) fromView:bar];
      char path[1024];snprintf(path,sizeof(path),"%s/scrollbar-point.txt",directory);FILE *file=fopen(path,"w");assert(file);
      fprintf(file,"%.17g %.17g\n",point.x,[scroll isFlipped]?point.y:[scroll bounds].size.height-point.y);fclose(file);
    }
    [[window contentView] lockFocus];[[NSColor controlBackgroundColor] set];NSRectFill([scroll frame]);[[window contentView] unlockFocus];
    [scroll displayRectIgnoringOpacity:[scroll bounds]];[scroll lockFocus];
    NSBitmapImageRep *image=[[NSBitmapImageRep alloc] initWithFocusedViewRect:[scroll bounds]];[scroll unlockFocus];
    int width=[image pixelsWide],height=[image pixelsHigh];unsigned char *pixels=malloc((size_t)width*height*4);assert(pixels);
    for(int y=0;y<height;y++)for(int x=0;x<width;x++) {
      unsigned char *p=[image bitmapData]+y*[image bytesPerRow]+4*x;
      ((uint32_t *)pixels)[y*width+x]=((uint32_t)p[3]<<24)|((uint32_t)p[0]<<16)|((uint32_t)p[1]<<8)|p[2];
    }
    save(directory,names[i],(NXSBitmap){width,height,width*4,pixels});free(pixels);[image release];
  }
  [window setReleasedWhenClosed:NO];[window close];[window release];[text release];[scroll release];
}
int main(int argc,char **argv)
{
  assert(argc>=2);NSAutoreleasePool *pool=[NSAutoreleasePool new];
  if(!strcmp(argv[1],"--reference")){assert(argc>=3);reference(argv[2]);[pool drain];puts("{\"native_reference_images\":3}");return 0;}
  if(!strcmp(argv[1],"--expect-no-multiline")) {
    assert(!(nxs_control_text_capabilities()&NXS_TEXT_MULTILINE));
    assert(!nxs_control_create(NXS_TEXTAREA,NULL,NULL,NULL));
    assert(!nxs_control_text_viewport(NULL).size&&!nxs_control_text_scroll(NULL,0,0));
    [pool drain];puts("{\"older_provider_rejects_multiline\":true}");return 0;
  }
  assert(nxs_control_text_capabilities()&NXS_TEXT_MULTILINE);
  if(!strcmp(argv[1],"--expect-no-geometry")){
    assert(!(nxs_control_text_capabilities()&NXS_TEXT_GEOMETRY));
    NXSControl *old=nxs_control_create(NXS_TEXTAREA,NULL,NULL,NULL);assert(old);
    NXSTextGeometry geometry={.size=sizeof(geometry)};
    assert(!nxs_control_text_geometry(old,&geometry));
    assert(nxs_control_text_viewport(old).size==sizeof(NXSTextViewport));
    assert(nxs_control_destroy(old));[pool drain];puts("{\"previous_multiline_provider_without_geometry\":true}");return 0;
  }
  struct Probe p={.allow=1};p.control=nxs_control_create(NXS_TEXTAREA,changed,pump,&p);assert(p.control);
  NXSControlConfig c={.size=sizeof(c),.width=180,.height=96,.enabled=1};assert(nxs_control_sync(p.control,&c));
  const char *values[]={"Alpha\nBeta",long_text,wrapped};const char *names[]={"short","scrolling","wrapped"};
  for(unsigned i=0;i<3;i++) {
    if(i==2){c.width=100;assert(nxs_control_sync(p.control,&c));}
    model(&p,values[i],0,0,1);value(&p,values[i]);save(argv[1],names[i],nxs_control_draw(p.control,1));
  }
  assert(nxs_control_text_capabilities()&NXS_TEXT_VIEWPORT);
  assert(nxs_control_text_capabilities()&NXS_TEXT_GEOMETRY);
  c.width=180;assert(nxs_control_sync(p.control,&c));model(&p,long_text,0,0,1);
  NXSTextGeometry geometry={.size=sizeof(geometry)};
  assert(!nxs_control_text_geometry(p.control,NULL));
  geometry.size=sizeof(geometry)-1;assert(!nxs_control_text_geometry(p.control,&geometry));
  geometry.size=sizeof(geometry);assert(nxs_control_text_geometry(p.control,&geometry));
  NXSTextViewport viewport=nxs_control_text_viewport(p.control);
  assert(viewport.size==sizeof(viewport)&&viewport.content.height>viewport.visible.height&&viewport.visible.y==0);
  assert(geometry.clip.width==viewport.visible.width&&geometry.clip.height==viewport.visible.height);
  assert(geometry.clip.x>0&&geometry.client.width>=geometry.clip.width);
  assert(nxs_control_text_scroll(p.control,1e9,1e9));viewport=nxs_control_text_viewport(p.control);
  assert(viewport.visible.x==geometry.maximum.x&&viewport.visible.y==geometry.maximum.y);
  assert(viewport.visible.y>0&&fabs(viewport.visible.y+viewport.visible.height-viewport.content.height)<.001);
  assert(!nxs_control_text_scroll(p.control,NAN,0));
  assert(nxs_control_text_scroll(p.control,-10,-10));viewport=nxs_control_text_viewport(p.control);
  assert(viewport.visible.x==geometry.minimum.x&&viewport.visible.y==geometry.minimum.y);
  assert(viewport.visible.x==0&&viewport.visible.y==0);value(&p,long_text);
  char point_path[1024];snprintf(point_path,sizeof(point_path),"%s/../reference/scrollbar-point.txt",argv[1]);
  FILE *point_file=fopen(point_path,"r");assert(point_file);double x,y;assert(fscanf(point_file,"%lf %lf",&x,&y)==2);fclose(point_file);
  click(&p,x,y,1);assert(nxs_control_text_viewport(p.control).visible.y>0);value(&p,long_text);
  model(&p,"Alpha\nBeta",0,0,1);assert(nxs_control_focus(p.control,1));
  click(&p,20,12,2);NXSTextState selected=value(&p,"Alpha\nBeta");assert(selected.selection_start==0&&selected.selection_length==5);
  click(&p,20,12,3);selected=value(&p,"Alpha\nBeta");assert(selected.selection_start==0&&selected.selection_length==6);
  assert(nxs_control_focus(p.control,0));
  model(&p,"Alpha\nBeta",8,0,1);assert(!value(&p,"Alpha\nBeta").editing);
  assert(nxs_control_focus(p.control,1)&&nxs_control_focused(p.control));
  key(&p,NXS_KEY_TEXT,"a",NXS_CONTROL);assert(value(&p,"Alpha\nBeta").selection_start==6);
  key(&p,NXS_KEY_TEXT,"e",NXS_CONTROL);assert(value(&p,"Alpha\nBeta").selection_start==10);
  assert(nxs_control_text_filter(p.control,proposal,&p));p.selector="insertNewline:";
  key(&p,NXS_KEY_ENTER,NULL,0);value(&p,"Alpha\nBeta\n");assert(p.changes==1&&p.proposals==1);
  p.allow=0;key(&p,NXS_KEY_ENTER,NULL,0);value(&p,"Alpha\nBeta\n");assert(p.changes==1&&p.proposals==2);
  p.allow=1;p.selector="insertTab:";key(&p,NXS_KEY_TAB,NULL,0);value(&p,"Alpha\nBeta\n\t");
  p.selector=NULL;model(&p,"日本語Café🙂\nNext",9,0,1);
  key(&p,NXS_KEY_TEXT,"X",0);assert(value(&p,"日本語Café🙂X\nNext").selection_start==10);
  /* A filtered external edit must finish the same native reveal as a local
   * edit, while a vetoed or unrelated programmatic model update must not. */
  char appended[2048];snprintf(appended,sizeof(appended),"%sZ",long_text);
  p.allow=1;model(&p,long_text,strlen(long_text),0,1);assert(nxs_control_text_scroll(p.control,0,0));
  key(&p,NXS_KEY_TEXT,"Z",0);value(&p,appended);
  double native_reveal=nxs_control_text_viewport(p.control).visible.y;assert(native_reveal>0);
  p.allow=0;model(&p,long_text,strlen(long_text),0,1);assert(nxs_control_text_scroll(p.control,0,0));
  key(&p,NXS_KEY_TEXT,"Z",0);value(&p,long_text);assert(nxs_control_text_viewport(p.control).visible.y==0);
  model(&p,appended,strlen(appended),0,1);value(&p,appended);
  assert(nxs_control_text_viewport(p.control).visible.y==native_reveal);
  model(&p,long_text,strlen(long_text),0,1);assert(nxs_control_text_scroll(p.control,0,0));
  key(&p,NXS_KEY_TEXT,"Z",0);model(&p,long_text,strlen(long_text),0,1);
  assert(nxs_control_text_viewport(p.control).visible.y==0);
  model(&p,appended,strlen(appended),0,1);assert(nxs_control_text_viewport(p.control).visible.y==0);
  p.allow=1;
  model(&p,"Read only\nSecond line",0,0,0);unsigned before=p.changes;
  NXSKeyEvent readonly={.size=sizeof(readonly),.type=NXS_KEY_DOWN,.text="Y",.unmodified_text="Y"};
  assert(nxs_control_key(p.control,&readonly)==NXS_INPUT_UNHANDLED);
  value(&p,"Read only\nSecond line");assert(p.changes==before);
  c.enabled=0;assert(nxs_control_sync(p.control,&c));assert(!nxs_control_focus(p.control,1));
  NXSKeyEvent e={.size=sizeof(e),.type=NXS_KEY_DOWN,.text="Z"};assert(nxs_control_key(p.control,&e)==NXS_INPUT_UNHANDLED);
  assert(nxs_control_focus(p.control,0)&&nxs_control_destroy(p.control));
  [pool drain];puts("{\"native_multiline\":true,\"images\":3,\"native_viewport_and_clamping\":true,\"native_scrollbar_pointer\":true,\"native_double_triple_click\":true,\"line_navigation\":true,\"newline\":true,\"native_tab\":true,\"preedit_veto\":true,\"utf16\":true,\"read_only\":true,\"disabled\":true,\"busy_destruction_rejected\":true}");return 0;
}
