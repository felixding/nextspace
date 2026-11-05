/* Read-only application model binding. NSProgressIndicator owns its pixels. */
#include "pinned-progress.h"
static int (*original_progress)(void *,const void *,const void *,const void *,const struct Rect *,const void *);
static int paint_progress(void *self,const void *element,const void *layout,
    const void *info,const struct Rect *rect,const void *style) {
  if(*(const uintptr_t *)element!=base+0x11d4a168+16)
    return original_progress(self,element,layout,info,rect,style);
  /* Chromium already validates value/max and returns their normalized ratio.
   * Indeterminate animation needs the native timer/invalidation contract; do
   * not replace it with a bridge animation or label it as native yet. */
  double position=((double (*)(const void *))(base+0xe7bb2e8))(element);
  if(isfinite(position)&&position>=0&&position<=1) {
    if(!paint_form(NXS_PROGRESS,self,element,NULL,style,info,rect))return 0;
  } else {
    struct NativeForm *form=find_form(element);if(form)form->painted=0;
  }
  return original_progress(self,element,layout,info,rect,style);
}
static struct Detour progress_detour={NXS_PROGRESS_OFFSET,nxs_progress_bytes,
  paint_progress,(void **)&original_progress};
