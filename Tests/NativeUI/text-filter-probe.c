/* Native editor pre-edit proposals and cancellation. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct Probe {
  NXSControl *control;
  const char *before,*replacement,*command;
  uint64_t start,length,selection,selected;
  int allow,proposals,changes;
};
static void value(struct Probe *p,const char *expected)
{
  char text[128];NXSTextState state={.size=sizeof(state)};
  assert(nxs_control_text_get(p->control,text,sizeof(text),&state)==strlen(expected)+1);
  assert(!strcmp(text,expected));
}
static int filter(void *context,const NXSTextEdit *edit)
{
  struct Probe *p=context;p->proposals++;
  if(edit->range_start!=p->start||edit->range_length!=p->length)
    fprintf(stderr,"Native proposal %d range %llu:%llu expected %llu:%llu command %s\n",p->proposals,
      (unsigned long long)edit->range_start,(unsigned long long)edit->range_length,
      (unsigned long long)p->start,(unsigned long long)p->length,edit->command?edit->command:"insertion");
  assert(edit->size==sizeof(*edit)&&edit->range_start==p->start&&edit->range_length==p->length);
  assert(edit->selection_start==p->selection&&edit->selection_length==p->selected);
  assert(!strcmp(edit->replacement,p->replacement));
  assert(p->command?(edit->command&&!strcmp(edit->command,p->command)):!edit->command);
  value(p,p->before); /* The proposal precedes mutation. */
  assert(!nxs_control_destroy(p->control));
  assert(!nxs_control_text_filter(p->control,NULL,NULL));
  NXSTextModel model={.size=sizeof(model),.text="Reentrant",.editable=1};
  assert(!nxs_control_text_sync(p->control,&model));
  return p->allow;
}
static void changed(void *context,int event,const NXSControlState *state)
{struct Probe *p=context;assert(event==NXS_TEXT_CHANGED&&state->tracking);p->changes++;}
static void model(struct Probe *p,const char *text,uint64_t selection,uint64_t length)
{
  NXSTextModel m={.size=sizeof(m),.text=text,.selection_start=selection,.selection_length=length,.editable=1};
  assert(nxs_control_text_sync(p->control,&m));p->before=text;p->selection=selection;p->selected=length;
}
static void key(struct Probe *p,int logical,const char *text,unsigned modifiers)
{
  NXSKeyEvent event={.size=sizeof(event),.type=NXS_KEY_DOWN,.key=logical,.text=text,.unmodified_text=text,.modifiers=modifiers};
  assert(nxs_control_key(p->control,&event)==NXS_INPUT_HANDLED);
}
int main(int argc,char **argv)
{
  if(argc>1&&!strcmp(argv[1],"--expect-no-command")) {
    assert(!(nxs_control_text_capabilities()&NXS_TEXT_COMMAND));
    assert(!nxs_control_text_command(NULL));
    puts("{\"previous_text_provider_without_command\":true}");return 0;
  }
  if(argc>1&&!strcmp(argv[1],"--expect-no-filter")) {
    assert(nxs_control_text_capabilities()==NXS_TEXT_EDITING);
    assert(!nxs_control_text_filter(NULL,NULL,NULL));
    puts("{\"previous_text_provider_without_filter\":true}");return 0;
  }
  assert((nxs_control_text_capabilities()&(NXS_TEXT_EDITING|NXS_TEXT_FILTER))==(NXS_TEXT_EDITING|NXS_TEXT_FILTER));
  for(int kind=NXS_TEXTFIELD;kind<=NXS_PASSWORD;kind++) {
    struct Probe p={0};p.control=nxs_control_create(kind,changed,NULL,&p);assert(p.control);
    NXSControlConfig config={.size=sizeof(config),.width=180,.height=24,.enabled=1};assert(nxs_control_sync(p.control,&config));
    assert(nxs_control_text_filter(p.control,filter,&p));
    model(&p,"Hello",1,2);assert(nxs_control_focus(p.control,1));
    p.start=1;p.length=2;p.replacement="X";
    key(&p,NXS_KEY_TEXT,"X",0);value(&p,"Hello");assert(p.proposals==1&&p.changes==0);
    p.allow=1;key(&p,NXS_KEY_TEXT,"X",0);value(&p,"HXlo");assert(p.proposals==2&&p.changes==1);
    model(&p,"Alpha beta",3,0);p.start=2;p.length=1;p.replacement="";p.command="deleteBackward:";p.allow=0;
    key(&p,NXS_KEY_BACKSPACE,NULL,0);value(&p,"Alpha beta");assert(p.proposals==3&&p.changes==1);
    if(nxs_control_text_capabilities()&NXS_TEXT_COMMAND)assert(!strcmp(nxs_control_text_command(p.control),"deleteBackward:"));
    p.allow=1;key(&p,NXS_KEY_BACKSPACE,NULL,0);value(&p,"Alha beta");assert(p.proposals==4&&p.changes==2);
    model(&p,"日本語Café🙂",9,0);p.start=9;p.length=0;p.replacement="X";p.command=NULL;p.allow=0;
    key(&p,NXS_KEY_TEXT,"X",0);value(&p,"日本語Café🙂");assert(p.proposals==5&&p.changes==2);
    assert(nxs_control_focus(p.control,0));assert(nxs_control_focus(p.control,1));
    model(&p,"日本語Café🙂",9,0); /* Refocus uses the native select-all policy. */
    p.allow=1;key(&p,NXS_KEY_TEXT,"X",0);value(&p,"日本語Café🙂X");assert(p.proposals==6&&p.changes==3);
    if(kind==NXS_TEXTFIELD) {
      model(&p,"Copy me",0,7);key(&p,NXS_KEY_TEXT,"c",NXS_ALT);assert(p.proposals==6);
      p.start=0;p.length=7;p.replacement="";p.command="cut:";p.allow=0;
      key(&p,NXS_KEY_TEXT,"x",NXS_ALT);value(&p,"Copy me");assert(p.proposals==7&&p.changes==3);
      if(nxs_control_text_capabilities()&NXS_TEXT_COMMAND)assert(!strcmp(nxs_control_text_command(p.control),"cut:"));
      model(&p,"Paste here",10,0);p.start=10;p.length=0;p.replacement="Copy me";p.command="paste:";p.allow=1;
      key(&p,NXS_KEY_TEXT,"v",NXS_ALT);value(&p,"Paste hereCopy me");assert(p.proposals==8&&p.changes==4);
      if(nxs_control_text_capabilities()&NXS_TEXT_COMMAND)assert(!strcmp(nxs_control_text_command(p.control),"paste:"));
    }
    int count=p.proposals;assert(nxs_control_text_filter(p.control,NULL,NULL));
    model(&p,"Plain",5,0);key(&p,NXS_KEY_TEXT,"X",0);value(&p,"PlainX");assert(p.proposals==count);
    assert(nxs_control_destroy(p.control));
  }
  puts("{\"native_filter_controls\":2,\"pre_mutation_value\":true,\"native_ranges_and_selectors\":true,\"typing_veto\":true,\"deletion_veto\":true,\"cut_veto\":true,\"paste_proposal\":true,\"unicode\":true,\"focus_transfer\":true,\"model_rebind\":true,\"reentrant_mutation_deferred\":true,\"filter_removal\":true}");
}
