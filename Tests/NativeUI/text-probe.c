/* Native text editing through the C-only contract. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
struct Probe {NXSControl *control;int edits,actions;};
static void changed(void *context,int event,const NXSControlState *state)
{
  struct Probe *p=context;assert(state->tracking);assert(!nxs_control_destroy(p->control));
  NXSTextModel model={.size=sizeof(model),.text="Busy",.selection_start=0,.editable=1};
  assert(!nxs_control_text_sync(p->control,&model));
  if(event==NXS_TEXT_CHANGED)p->edits++;else {assert(event==NXS_ACTIVATE);p->actions++;}
}
static int key(struct Probe *p,int logical,const char *text,unsigned modifiers)
{
  NXSKeyEvent e={.size=sizeof(e),.type=NXS_KEY_DOWN,.key=logical,.text=text,.unmodified_text=text,.modifiers=modifiers};
  return nxs_control_key(p->control,&e);
}
static NXSTextState value(struct Probe *p,const char *expected)
{
  NXSTextState state={.size=sizeof(state)};char buffer[256];
  size_t required=nxs_control_text_get(p->control,NULL,0,&state);
  if(required!=strlen(expected)+1) {
    nxs_control_text_get(p->control,buffer,sizeof(buffer),NULL);
    fprintf(stderr,"Synthetic native-text fixture: expected '%s', got '%s'\n",expected,buffer);
  }
  assert(required==strlen(expected)+1);
  char short_buffer[1]={'x'};assert(nxs_control_text_get(p->control,short_buffer,1,NULL)==required&&!short_buffer[0]);
  assert(nxs_control_text_get(p->control,buffer,sizeof(buffer),&state)==required&&!strcmp(buffer,expected));
  return state;
}
static void model(struct Probe *p,const char *text,uint64_t start,uint64_t length,int editable)
{
  NXSTextModel m={.size=sizeof(m),.text=text,.selection_start=start,.selection_length=length,.editable=editable};
  assert(nxs_control_text_sync(p->control,&m));
}
static void image(struct Probe *p,const char *directory,const char *name)
{
  NXSBitmap b=nxs_control_draw(p->control,1);assert(b.pixels&&b.width==180&&b.height==24);
  if(!directory)return;
  char filename[1024];snprintf(filename,sizeof(filename),"%s/text-%s.argb",directory,name);
  FILE *f=fopen(filename,"wb");assert(f);assert(fwrite(b.pixels,b.stride,b.height,f)==(size_t)b.height);fclose(f);
}
static double now(void)
{struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return t.tv_sec+t.tv_nsec/1e9;}
static void caret(struct Probe *p)
{
  model(p,"Caret",5,0,1);
  NXSBitmap b=nxs_control_draw(p->control,1);assert(b.pixels);
  size_t size=(size_t)b.stride*b.height;unsigned char *before=malloc(size);assert(before);
  memcpy(before,b.pixels,size);
  int invalidated=0,different=0;double deadline=now()+2;
  while(now()<deadline&&!different) {
    nxs_native_ui_dispatch_events(.05);
    if(nxs_control_needs_display(p->control)) {
      invalidated++;
      b=nxs_control_draw(p->control,1);assert(b.pixels);
      different=memcmp(before,b.pixels,size)!=0;
    }
  }
  free(before);assert(invalidated&&different);
}
int main(int argc,char **argv)
{
  if(argc>1&&!strcmp(argv[1],"--expect-no-text")) {
    assert(!nxs_control_text_capabilities());assert(!nxs_control_text_sync(NULL,NULL));
    assert(!nxs_control_text_get(NULL,NULL,0,NULL));
    assert(!nxs_control_create(NXS_TEXTFIELD,NULL,NULL,NULL));
    puts("{\"previous_provider_without_text\":true}");return 0;
  }
  assert(nxs_control_text_capabilities()==NXS_TEXT_EDITING);
  const char *directory=argc>1&&argv[1][0]!='-'?argv[1]:NULL;
  for(int kind=NXS_TEXTFIELD;kind<=NXS_PASSWORD;kind++) {
    struct Probe p={0};p.control=nxs_control_create(kind,changed,NULL,&p);assert(p.control);
    NXSControlConfig c={.size=sizeof(c),.width=180,.height=24,.enabled=1};assert(nxs_control_sync(p.control,&c));
    model(&p,"Hello",1,2,1);assert(!p.edits&&!p.actions);
    NXSTextState state=value(&p,"Hello");assert(!state.editing&&state.editable&&state.secure==(kind==NXS_PASSWORD));
    image(&p,directory,kind==NXS_PASSWORD?"secure-normal":"normal");
    assert(nxs_control_focus(p.control,1)&&nxs_control_focused(p.control));
    state=value(&p,"Hello");assert(state.editing&&state.selection_start==1&&state.selection_length==2);
    image(&p,directory,kind==NXS_PASSWORD?"secure-focused":"focused");
    if(kind==NXS_TEXTFIELD&&getenv("NXS_NATIVE_UI_TEXT_HOLD")) {
      puts("{\"event\":\"host-live\"}");fflush(stdout);assert(getchar()=='\n');
    }
    assert(key(&p,NXS_KEY_TEXT,"X",0)==NXS_INPUT_HANDLED);state=value(&p,"HXlo");
    assert(p.edits==1&&state.selection_start==2&&!state.selection_length);
    image(&p,directory,kind==NXS_PASSWORD?"secure-edited":"edited");
    assert(key(&p,NXS_KEY_BACKSPACE,NULL,0)==NXS_INPUT_HANDLED);value(&p,"Hlo");assert(p.edits==2);
    assert(key(&p,NXS_KEY_TAB,NULL,0)==NXS_INPUT_NEXT);
    assert(key(&p,NXS_KEY_TAB,NULL,NXS_SHIFT)==NXS_INPUT_PREVIOUS);
    assert(nxs_control_focus(p.control,0)&&!nxs_control_focused(p.control));value(&p,"Hlo");
    model(&p,"日本語Café🙂",9,0,1);assert(nxs_control_focus(p.control,1));
    state=value(&p,"日本語Café🙂");assert(state.selection_start==9);
    key(&p,NXS_KEY_TEXT,"X",0);value(&p,"日本語Café🙂X");
    if(kind==NXS_TEXTFIELD) {
      caret(&p);
      model(&p,"Alpha beta",5,0,1);key(&p,NXS_KEY_TEXT,"a",NXS_CONTROL);
      state=value(&p,"Alpha beta");assert(state.selection_start==0&&!state.selection_length);
      key(&p,NXS_KEY_TEXT,"e",NXS_CONTROL);state=value(&p,"Alpha beta");assert(state.selection_start==10);
      model(&p,"Copy me",0,7,1);key(&p,NXS_KEY_TEXT,"c",NXS_ALT);value(&p,"Copy me");
      model(&p,"Destination",11,0,1);key(&p,NXS_KEY_TEXT,"v",NXS_ALT);value(&p,"DestinationCopy me");
    } else {
      model(&p,"Protected",0,9,1);key(&p,NXS_KEY_TEXT,"c",NXS_ALT);
      model(&p,"",0,0,1);key(&p,NXS_KEY_TEXT,"v",NXS_ALT);value(&p,"Copy me");
    }
    int actions=p.actions;key(&p,NXS_KEY_ENTER,NULL,0);assert(p.actions==actions+1);
    int edits=p.edits;model(&p,"Read only",0,9,0);assert(p.edits==edits);
    key(&p,NXS_KEY_TEXT,"Y",0);value(&p,"Read only");assert(p.edits==edits);
    NXSTextModel bad={.size=sizeof(bad),.text="x",.selection_start=2,.editable=1};
    assert(!nxs_control_text_sync(p.control,&bad));value(&p,"Read only");
    bad.text="\xc0";bad.selection_start=0;assert(!nxs_control_text_sync(p.control,&bad));value(&p,"Read only");
    c.enabled=0;assert(nxs_control_sync(p.control,&c));assert(!nxs_control_focus(p.control,1));
    assert(key(&p,NXS_KEY_TEXT,"Z",0)==NXS_INPUT_UNHANDLED);value(&p,"Read only");
    assert(nxs_control_focus(p.control,0));assert(nxs_control_destroy(p.control));
  }
  puts("{\"native_text_controls\":2,\"selection_replace\":true,\"delete\":true,\"unicode\":true,\"read_only\":true,\"disabled\":true,\"native_navigation\":true,\"deferred_destruction\":true,\"emacs_control_a_e\":true,\"alt_copy_paste\":true,\"secure_copy_blocked\":true,\"native_return_action\":true,\"native_caret_invalidation_and_pixels\":true}");
}
