/* Repeated native draws must not accumulate fractional-edge alpha. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
  const double widths[]={739.+22./60.,180.5,180};
  unsigned cases=0,draws=0;
  for(int kind=NXS_TEXTFIELD;kind<=NXS_PASSWORD;kind++)for(unsigned n=0;n<3;n++) {
    NXSControl *field=nxs_control_create(kind,NULL,NULL,NULL);assert(field);
    NXSControlConfig config={.size=sizeof(config),.width=widths[n],.height=n?24:19,.enabled=1};
    assert(nxs_control_sync(field,&config)&&nxs_control_focus(field,1));
    NXSTextModel model={.size=sizeof(model),.text="Alpha beta",.selection_start=1,.selection_length=2,.editable=1};
    assert(nxs_control_text_sync(field,&model));
    NXSBitmap first=nxs_control_draw(field,1);assert(first.pixels&&first.width>0&&first.height>0);
    size_t bytes=first.stride*first.height;unsigned char *reference=malloc(bytes);assert(reference);
    memcpy(reference,first.pixels,bytes);
    for(int i=0;i<5;i++) {
      NXSBitmap next=nxs_control_draw(field,1);
      assert(next.width==first.width&&next.height==first.height&&next.stride==first.stride);
      if(memcmp(reference,next.pixels,bytes))fprintf(stderr,"unstable native backing kind=%d width=%.17g redraw=%d\n",kind,widths[n],i+1);
      assert(!memcmp(reference,next.pixels,bytes));draws++;
    }
    NXSTextState state={.size=sizeof(state)};assert(nxs_control_text_get(field,NULL,0,&state));
    assert(state.selection_start==1&&state.selection_length==2);
    free(reference);assert(nxs_control_destroy(field));cases++;
  }
  printf("{\"native_cases\":%u,\"identical_redraws\":%u,\"selection_retained\":true}\n",cases,draws);
  return 0;
}
