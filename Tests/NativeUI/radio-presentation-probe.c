/* Compare a retained native group with a fresh group at the same density. */
#define _GNU_SOURCE
#include "NativeUI.h"
#include "Bridge/Protocol.h"
#include <assert.h>
#include <stdio.h>
static void note(const char *message){fprintf(stderr,"%s\n",message);}
#include "Bridge/Transport.inc"
#include "Bridge/Radios.inc"
#ifndef NXS_RADIO_BINDING_HEADER
#define NXS_RADIO_BINDING_HEADER "Bridge/RadioBinding.inc"
#endif
#include NXS_RADIO_BINDING_HEADER
int main(int argc,char **argv)
{
  setvbuf(stdout,NULL,_IOLBF,0);assert(argc==2&&bridge_connect(argv[1]));
  struct NXSRequest bootstrap={.magic=NXS_CHROMIUM_MAGIC,.operation=7};assert(exchange(bootstrap));
  NXSRadioItem items[]={{sizeof(NXSRadioItem),1,"",1},{sizeof(NXSRadioItem),2,"",1}};
  struct NXSRadioBinding warm={.control=16};
  const double densities[]={1,1.75,1,2,1.25};int valid=1;
  for(unsigned i=0;i<sizeof(densities)/sizeof(*densities);i++) {
    double scale=densities[i];
    struct NXSRadioBinding cold={.control=32+i};
    assert(native_control_presentation(NXS_RADIOGROUP,warm.control,scale));
    assert(native_radio_binding_sync(&warm,items,2,1,2,0,scale));
    for(unsigned member=1;member<=2;member++) {
      struct NXSResponse *r=native_radio_item_draw(warm.control,member,18*scale,15*scale);
      if(!r||!r->width||!r->height) {
        printf("{\"case\":\"retained-radio-snapshot-available\",\"scale\":%g,\"member\":%u,\"passed\":false}\n",scale,member);
        valid=0;continue;
      }
      size_t size=r->size;void *saved=malloc(size);assert(saved);memcpy(saved,r,size);
      assert(native_control_presentation(NXS_RADIOGROUP,cold.control,scale));
      assert(native_radio_binding_sync(&cold,items,2,1,2,0,scale));
      struct NXSResponse *fresh=native_radio_item_draw(cold.control,member,18*scale,15*scale);assert(fresh);
      struct NXSResponse *previous=saved;
      int same=previous->width==fresh->width&&previous->height==fresh->height&&previous->stride==fresh->stride&&
        size==fresh->size&&!memcmp(previous+1,fresh+1,size-sizeof(*fresh));
      printf("{\"case\":\"retained-radio-matches-fresh-native-group\",\"scale\":%g,\"member\":%u,\"passed\":%s}\n",scale,member,same?"true":"false");
      valid&=same;free(saved);
    }
    native_radio_binding_destroy(&cold);
  }
  native_radio_binding_destroy(&warm);return valid?0:1;
}
