/* Native slider binding: application data/events only, no widget rules. */
#include "pinned-sliders.h"
struct EngineDecimal {uint64_t opaque[3];};
struct EngineStepRange {struct EngineDecimal maximum,minimum,step,base;uint32_t description[4];unsigned char flags[8];};
_Static_assert(sizeof(struct EngineStepRange)==120,"Pinned StepRange return layout");
static void *range_type(void *node){return decode_member((char *)node+272);}
static double range_value(void *node)
{return ((double (*)(const void *))(base+0xe7334c4))(range_type(node));}
static int sync_slider_model(struct NativeForm *form) {
  void *type=range_type(form->node);if(!type)return 0;
  struct EngineStepRange range=((struct EngineStepRange (*)(const void *,int))(base+0xe733610))(type,0);
  form->minimum=((double (*)(const void *))(base+0xe0f0e64))(&range.minimum);
  form->maximum=((double (*)(const void *))(base+0xe0f0e64))(&range.maximum);
  form->step=range.flags[0]?((double (*)(const void *))(base+0xe0f0e64))(&range.step):0;
  if(form->step>0&&isfinite(form->step)){
    struct EngineDecimal minimum=((struct EngineDecimal (*)(const void *,const void *))(base+0xe71cac0))(&range,&range.minimum);
    struct EngineDecimal maximum=((struct EngineDecimal (*)(const void *))(base+0xe71d220))(&range);
    double a=((double (*)(const void *))(base+0xe0f0e64))(&minimum);
    double b=((double (*)(const void *))(base+0xe0f0e64))(&maximum);
    if(isfinite(a)&&isfinite(b)&&a<=b){form->minimum=a;form->maximum=b;}else form->step=0;
  }
  form->value=range_value(form->node);
  return isfinite(form->minimum)&&isfinite(form->maximum)&&isfinite(form->value)&&form->minimum<form->maximum;
}
static void apply_slider_value(struct NativeForm *form,struct NXSResponse *response,int behavior) {
  if(!response||form->kind!=NXS_SLIDER||response->parts[0].width<=form->actions_seen)return;
  double value=response->parts[0].x;form->actions_seen=response->parts[0].width;
  if(!isfinite(value))return;
  /* Use the real engine serialization, validation and trusted input/change
   * dispatch. Decimal/StepRange are opaque application-model ABI data here. */
  struct EngineDecimal decimal=((struct EngineDecimal (*)(double))(base+0xe0f05c4))(value);
  ((void (*)(void *,const void *,int))(base+0xe709f74))(range_type(form->node),&decimal,behavior);
}
static int slider_mouse_default(void *node,void *event) {
  if(!forms_sliders_enabled)return 0;
  uintptr_t atom=*(const uintptr_t *)((char *)event+24);
  if(!same_atom(atom,0x123a55f8)&&!same_atom(atom,0x123a5600)&&!same_atom(atom,0x123a5608))return 0;
  struct NativeForm *form=form_ancestor(node);
  if(!form||form->kind!=NXS_SLIDER)return 0;
  *(unsigned short *)((char *)event+32)|=0x40;return 1;
}
static int (*original_slider_track)(void *,const void *,const void *,const void *,const struct Rect *,const void *);
static int (*original_slider_thumb)(void *,const void *,const void *,const void *,const struct Rect *);
static void (*original_slider_default)(void *,void *);
static int paint_slider_track(void *self,const void *element,const void *layout,const void *info,const struct Rect *rect,const void *style) {
  if(input_form_kind((void *)element)==NXS_SLIDER)
    if(!paint_form(NXS_SLIDER,self,element,NULL,style,info,rect))return 0;
  return original_slider_track(self,element,layout,info,rect,style);
}
static int paint_slider_thumb(void *self,const void *element,const void *style,const void *info,const struct Rect *rect) {
  struct NativeForm *form=form_ancestor((void *)element);
  if(form&&form->kind==NXS_SLIDER&&form->painted)return 0;
  return original_slider_thumb(self,element,style,info,rect);
}
static void slider_default(void *node,void *event)
{if(!slider_mouse_default(node,event))original_slider_default(node,event);}
static struct Detour slider_detours[]={
 {NXS_SLIDER_TRACK_OFFSET,nxs_slider_track_bytes,paint_slider_track,(void **)&original_slider_track},
 {NXS_SLIDER_THUMB_OFFSET,nxs_slider_thumb_bytes,paint_slider_thumb,(void **)&original_slider_thumb},
 {NXS_SLIDER_DEFAULT_OFFSET,nxs_slider_default_bytes,slider_default,(void **)&original_slider_default}
};
