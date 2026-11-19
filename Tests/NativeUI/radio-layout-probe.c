/* Source layout metadata must survive translation, zoom and fractional scale. */
#include <assert.h>
#include <math.h>
#include <stddef.h>
#include "../../Libraries/NativeUI/Bridge/Protocol.h"
#include "../../Libraries/NativeUI/Bridge/RadioLayout.inc"
int main(void)
{
  for(unsigned columns=1;columns<=5;columns++)
    for(unsigned count=columns;count<17;count++)
      for(unsigned step=1;step<=100;step++) {
        double scale=step*.037;struct NXSRectD positions[16];
        for(unsigned i=0;i<count;i++) positions[i]=(struct NXSRectD){
          -73.125+(i%columns)*61.7*scale,417.375+(i/columns)*29.2*scale,
          13.2*scale,16.4*scale};
        assert(native_radio_columns(positions,count)==columns);
      }
  assert(native_radio_columns(NULL,0)==1);
  return 0;
}
