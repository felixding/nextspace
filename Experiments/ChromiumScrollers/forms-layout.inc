/* Engine layout adapters consume full native cell metrics. No widget layout,
 * font measurement, CSS constraint resolution or reflow policy is copied. */
#include "pinned-layout.h"
struct NativeBoxStrut {int top,right,bottom,left;};
_Static_assert(sizeof(struct NativeBoxStrut)==16,"Pinned Blink physical box strut ABI");
static int (*original_form_inline_size)(const void *);
static int (*original_form_block_size)(const void *,int);
static int native_button_preferred(const void *,const void *,struct SizeI *);
static int popup_preferred(void *,const void *,struct SizeI *);
static __thread int native_layout_work_pending;
static void native_layout_changed(struct NativeForm *form) {
  form->layout_pending=1;native_layout_work_pending=1;
  if(current_controller)((void (*)(void *))(base+NXS_LAYOUT_SCHEDULE_OFFSET))(current_controller);
}
static void native_layout_work(void) {
  if(!native_layout_work_pending)return;native_layout_work_pending=0;
  for(struct NativeForm *form=native_forms;form;form=form->next) {
    if(!form->layout_pending)continue;form->layout_pending=0;
    void *layout=decode_member((char *)form->node+48);
    if(layout)((void (*)(void *,const char *))(base+NXS_LAYOUT_INVALIDATE_OFFSET))(layout,"Native control geometry changed");
  }
}
static int native_layout_unit_scale(const void *node,const void *layout) {
  if(!node||!layout||decode_member((const char *)node+48)!=layout||!(*((const unsigned char *)layout+22)&32))return 0;
  /* Read the audited zoom storage. The DOM currentCSSZoom getter flushes
   * layout and cannot run inside a layout transaction. */
  const void *style=decode_member((const char *)layout+32);
  const void *inherited=style?decode_member(style):NULL;
  const void *font=inherited?decode_member((const char *)inherited+4):NULL;
  float zoom=font?*(const float *)((const char *)font+48):0;
  return isfinite(zoom)&&fabsf(zoom-1)<0.000001f;
}
static int native_content_size(const void *layout,int preferred,int block) {
  struct NativeBoxStrut border=((struct NativeBoxStrut (*)(const void *))(base+NXS_LAYOUT_BORDER_OFFSET))(layout);
  struct NativeBoxStrut padding=((struct NativeBoxStrut (*)(const void *))(base+NXS_LAYOUT_PADDING_OFFSET))(layout);
  int offsets=block?border.top+border.bottom+padding.top+padding.bottom:border.left+border.right+padding.left+padding.right;
  int content=preferred*64-offsets;return content>0?content:0;
}
static int form_inline_size(const void *layout) {
  int original=original_form_inline_size(layout);if(original>=0)return original;
  void *node=((void *(*)(const void *))(base+NXS_LAYOUT_NODE_OFFSET))(layout);struct SizeI preferred;
  /* Grid bypasses the default-content getter, but honors this existing
   * intrinsic override. Preserve original containment values before supplying
   * the native control metric; outer CSS sizing stays in Blink. */
  return native_button_preferred(node,layout,&preferred)?native_content_size(layout,preferred.width,0):original;
}
static int form_block_size(const void *layout,int geometry) {
  void *node=((void *(*)(const void *))(base+NXS_LAYOUT_NODE_OFFSET))(layout);struct SizeI preferred;
  if(native_button_preferred(node,layout,&preferred))return native_content_size(layout,preferred.height,1);
  int original=original_form_block_size(layout,geometry);
  return original>=0&&forms_popups_enabled&&node&&popup_preferred(node,layout,&preferred)?native_content_size(layout,preferred.height,1):original;
}
static int guard_form_layout(void) {
  return !memcmp((void *)(base+NXS_LAYOUT_BORDER_OFFSET),nxs_layout_border_bytes,20)&&
    !memcmp((void *)(base+NXS_LAYOUT_PADDING_OFFSET),nxs_layout_padding_bytes,20)&&
    !memcmp((void *)(base+NXS_LAYOUT_NODE_OFFSET),nxs_layout_node_bytes,20)&&
    !memcmp((void *)(base+NXS_LAYOUT_INVALIDATE_OFFSET),nxs_layout_invalidate_bytes,20)&&
    !memcmp((void *)(base+NXS_LAYOUT_SCHEDULE_OFFSET),nxs_layout_schedule_bytes,20);
}
static struct Detour form_layout_detours[]={
 {NXS_LAYOUT_INLINE_OFFSET,nxs_layout_inline_bytes,form_inline_size,(void **)&original_form_inline_size},
 {NXS_LAYOUT_BLOCK_OFFSET,nxs_layout_block_bytes,form_block_size,(void **)&original_form_block_size}
};
