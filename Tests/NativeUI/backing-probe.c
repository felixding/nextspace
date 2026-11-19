/* Repeated native draws must not accumulate fractional-edge alpha. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned fractional_snapshots(void) {
  const int kinds[]={NXS_BUTTON,NXS_CHECKBOX,NXS_SLIDER,NXS_PROGRESS,NXS_POPUP};
  /* Gecko quantizes app units to 34 at a 175% output, then returns float.
   * Test the observed value, not a neighboring convenient scale. */
  const double scales[]={1,1.25,1.5,1.75,(double)(float)(60./34.),(double)(float)1.1,(double)(float)1.3,2};
  unsigned cases=0;
  for(unsigned k=0;k<sizeof(kinds)/sizeof(*kinds);k++)for(unsigned s=0;s<sizeof(scales)/sizeof(*scales);s++) {
    NXSControl *control=nxs_control_create(kinds[k],NULL,NULL,NULL);assert(control);
    NXSControlConfig config={.size=sizeof(config),.width=103/scales[s],.height=36/scales[s],
      .maximum=1,.value=.5,.enabled=1,.title="Native"};
    assert(nxs_control_sync(control,&config));
    NXSBitmap first=nxs_control_draw(control,scales[s]);assert(first.pixels);
    size_t bytes=first.stride*first.height;unsigned char *saved=malloc(bytes);assert(saved);memcpy(saved,first.pixels,bytes);
    for(unsigned read=0;read<3;read++) {
      NXSBitmap cached=nxs_control_draw(control,scales[s]);
      int equal=cached.pixels&&first.width==cached.width&&first.height==cached.height&&
        first.stride==cached.stride&&!memcmp(saved,cached.pixels,bytes);
      if(!equal)fprintf(stderr,"fractional native snapshot changed kind=%d scale=%.17g first=%dx%d cached=%dx%d\n",
        kinds[k],scales[s],first.width,first.height,cached.width,cached.height);
      assert(equal);
    }
    free(saved);assert(nxs_control_destroy(control));cases++;
  }
  return cases;
}
static unsigned resized_editors(void) {
  unsigned cases=0;
  const int kinds[]={NXS_TEXTFIELD,NXS_PASSWORD,NXS_SEARCHFIELD};
  const double widths[]={292.+22./60.,298.+22./60.,326.+22./60.,298.+22./60.};
  for(unsigned k=0;k<3;k++)for(int scale=1;scale<=2;scale++) {
    NXSControlConfig config={.size=sizeof(config),.width=212,.height=18.5,.enabled=1};
    NXSTextModel model={.size=sizeof(model),.text="Alpha beta",.selection_start=0,.selection_length=10,.editable=1};
    NXSControl *field=nxs_control_create(kinds[k],NULL,NULL,NULL);assert(field);
    assert(nxs_control_sync(field,&config)&&nxs_control_focus(field,1)&&nxs_control_text_sync(field,&model));
    for(unsigned i=0;i<4;i++) {
      config.width=widths[i];assert(nxs_control_sync(field,&config)&&nxs_control_text_sync(field,&model));
      assert(nxs_control_draw(field,scale).pixels);
    }
    NXSBitmap resized=nxs_control_draw(field,scale);size_t bytes=resized.stride*resized.height;
    unsigned char *saved=malloc(bytes);assert(saved);memcpy(saved,resized.pixels,bytes);
    NXSControl *fresh=nxs_control_create(kinds[k],NULL,NULL,NULL);assert(fresh);
    assert(nxs_control_sync(fresh,&config)&&nxs_control_focus(fresh,1)&&nxs_control_text_sync(fresh,&model));
    NXSBitmap expected=nxs_control_draw(fresh,scale);
    int equal=expected.pixels&&expected.width==resized.width&&expected.height==resized.height&&
      expected.stride==resized.stride&&!memcmp(saved,expected.pixels,bytes);
    if(!equal)fprintf(stderr,"resized native editor differs from fresh control kind=%d scale=%d\n",kinds[k],scale);
    assert(equal);free(saved);assert(nxs_control_destroy(field)&&nxs_control_destroy(fresh));cases++;
  }
  return cases;
}
int main(void) {
  unsigned fractional_cases=fractional_snapshots();
  unsigned resize_cases=resized_editors();
  const double widths[]={739.+22./60.,180.5,180};
  const int text_kinds[]={NXS_TEXTFIELD,NXS_PASSWORD,NXS_SEARCHFIELD,NXS_TEXTAREA};
  unsigned cases=0,draws=0;
  for(unsigned k=0;k<sizeof(text_kinds)/sizeof(*text_kinds);k++)for(unsigned n=0;n<3;n++) {
    int kind=text_kinds[k];
    NXSControl *field=nxs_control_create(kind,NULL,NULL,NULL);assert(field);
    NXSControlConfig config={.size=sizeof(config),.width=widths[n],.height=n?24:19,.enabled=1};
    assert(nxs_control_sync(field,&config)&&nxs_control_focus(field,1));
    NXSTextModel model={.size=sizeof(model),.text="Alpha beta",.selection_start=1,.selection_length=2,.editable=1};
    assert(nxs_control_text_sync(field,&model));
    NXSBitmap first=nxs_control_draw(field,1);assert(first.pixels&&first.width>0&&first.height>0);
    size_t bytes=first.stride*first.height;unsigned char *reference=malloc(bytes);assert(reference);
    memcpy(reference,first.pixels,bytes);
    for(int i=0;i<5;i++) {
      assert(nxs_control_sync(field,&config));
      assert(nxs_control_text_sync(field,&model));
      assert(!nxs_control_needs_display(field));
      NXSBitmap next=nxs_control_draw(field,1);
      assert(next.width==first.width&&next.height==first.height&&next.stride==first.stride);
      if(memcmp(reference,next.pixels,bytes))fprintf(stderr,"unstable native backing kind=%d width=%.17g redraw=%d\n",kind,widths[n],i+1);
      assert(!memcmp(reference,next.pixels,bytes));draws++;
    }
    NXSTextState state={.size=sizeof(state)};assert(nxs_control_text_get(field,NULL,0,&state));
    assert(state.selection_start==1&&state.selection_length==2);
    model.text="Different text";model.selection_start=0;model.selection_length=0;
    assert(nxs_control_text_sync(field,&model)&&nxs_control_needs_display(field));
    NXSBitmap changed=nxs_control_draw(field,1);
    assert(changed.width==first.width&&changed.height==first.height&&memcmp(reference,changed.pixels,bytes));
    free(reference);assert(nxs_control_destroy(field));cases++;
  }
  for(int kind=NXS_COLORWELL;kind<=NXS_DATEPICKER;kind++) {
    NXSControl *field=nxs_control_create(kind,NULL,NULL,NULL);assert(field);
    NXSControlConfig config={.size=sizeof(config),.width=180,.height=32,.enabled=1};
    NXSColorModel color={.size=sizeof(color),.red=.2,.green=.4,.blue=.6,.alpha=1};
    NXSDateModel date={.size=sizeof(date),.elements=NXS_DATE_YEAR_MONTH_DAY,.style=NXS_DATE_TEXT,
      .flags=NXS_DATE_UTC|NXS_DATE_PROLEPTIC_GREGORIAN,.value=1700000000};
    assert(nxs_control_sync(field,&config));
    assert(kind==NXS_COLORWELL?nxs_control_color_sync(field,&color):nxs_control_date_sync(field,&date));
    NXSBitmap first=nxs_control_draw(field,1);assert(first.pixels);
    size_t bytes=first.stride*first.height;unsigned char *reference=malloc(bytes);assert(reference);
    memcpy(reference,first.pixels,bytes);
    for(int i=0;i<20;i++) {
      assert(nxs_control_sync(field,&config));
      assert(kind==NXS_COLORWELL?nxs_control_color_sync(field,&color):nxs_control_date_sync(field,&date));
      if(nxs_control_needs_display(field))fprintf(stderr,"unchanged auxiliary model requests repaint kind=%d iteration=%d\n",kind,i);
      assert(!nxs_control_needs_display(field));
      NXSBitmap next=nxs_control_draw(field,1);assert(next.pixels&&!memcmp(reference,next.pixels,bytes));draws++;
    }
    color.red=.8;date.value+=86400;
    assert(kind==NXS_COLORWELL?nxs_control_color_sync(field,&color):nxs_control_date_sync(field,&date));
    assert(nxs_control_needs_display(field));
    NXSBitmap next=nxs_control_draw(field,1);assert(next.pixels&&memcmp(reference,next.pixels,bytes));
    free(reference);assert(nxs_control_destroy(field));cases++;
  }
  const int configured[]={NXS_BUTTON,NXS_CHECKBOX,NXS_RADIO,NXS_SLIDER,NXS_PROGRESS,NXS_POPUP,NXS_RADIOGROUP,NXS_LISTBOX,NXS_STEPPER};
  unsigned dirty=0;
  for(unsigned i=0;i<sizeof(configured)/sizeof(*configured);i++) {
    int kind=configured[i];NXSControl *field=nxs_control_create(kind,NULL,NULL,NULL);assert(field);
    NXSControlConfig config={.size=sizeof(config),.width=180,.height=64,.enabled=1,.maximum=100,.title="Native"};
    assert(nxs_control_sync(field,&config));
    if(kind==NXS_RADIOGROUP) {
      NXSRadioItem items[]={{sizeof(*items),1,"One",1},{sizeof(*items),2,"Two",1}};
      assert(nxs_control_radio_items(field,items,2,1,1,1));
    }
    if(kind==NXS_LISTBOX) {
      NXSListItem items[]={{.size=sizeof(*items),.identifier=1,.title="One",.enabled=1,.selected=1},
        {.size=sizeof(*items),.identifier=2,.title="Two",.enabled=1}};
      assert(nxs_control_list_items(field,items,2,0,1));
    }
    assert(nxs_control_sync(field,&config));
    assert(nxs_control_draw(field,1).pixels);
    for(int n=0;n<3;n++) {
      assert(nxs_control_sync(field,&config));
      if(nxs_control_needs_display(field)){fprintf(stderr,"unchanged control configuration repaints kind=%d iteration=%d\n",kind,n);dirty++;}
      assert(nxs_control_draw(field,1).pixels);draws++;
    }
    assert(nxs_control_destroy(field));cases++;
  }
  assert(!dirty);
  printf("{\"native_cases\":%u,\"identical_redraws\":%u,\"fractional_snapshots_stable\":%u,\"resized_editors_match_fresh_native_controls\":%u,\"selection_retained\":true,\"unchanged_sync_stays_clean\":true,\"unchanged_text_models_stay_clean\":true,\"unchanged_auxiliary_models_stay_clean\":true,\"all_static_page_control_configurations_stay_clean\":true,\"model_change_repaints\":true}\n",cases,draws,fractional_cases,resize_cases);
  return 0;
}
