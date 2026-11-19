/* Native snapshots enter Gecko through its original image API. No control
 * drawing, image sampler, transform or clipping implementation is copied. */
struct GeckoImageSize {int32_t width,height;};
struct GeckoSurfaceOptions {int8_t filter,bounds;};
static struct RectF gecko_image_part(const struct RectF *destination,
  double width,double height,struct NXSRectD part)
{
  return (struct RectF){destination->x+part.x*destination->width/width,
    destination->y+part.y*destination->height/height,
    part.width*destination->width/width,part.height*destination->height/height};
}
static int guard_native_image_calls(void)
{
  const uintptr_t *vtable=(const uintptr_t *)(base+0x9e22190+16);
  static const uint32_t lifetime[]={0xd503233f,0xf81e0ffe,0xa9014ff4,0xf9401014,
    0xb40001d4,0xf9400688,0xaa0003f3,0x92800000,0x91002101};
  return vtable[17]==base+0x3fc20a4&&vtable[27]==base+0x3fc3108&&
    vtable[50]==base+0x3fc5ba4&&!memcmp((void *)(base+0x406b920),lifetime,sizeof(lifetime));
}
static void gecko_image_release(void *surface)
{
  /* Pinned SupportsThreadSafeWeakPtr<SourceSurface> ABI. Only bridge-owned
   * image references are released here; the original virtual destructor
   * owns the surface, backing store and weak-reference allocation. */
  void *weak=*(void **)((char *)surface+8);
  _Atomic uint64_t *strong=(_Atomic uint64_t *)((char *)weak+8);
  if(atomic_fetch_sub_explicit(strong,1,memory_order_acq_rel)==1)
    ((void (*)(void *))(*(uintptr_t **)surface)[1])(surface);
}
static void draw_bitmap(void *target,const struct RectF *rect,const uint32_t *pixels,int width,int height)
{
  if(!target||!pixels||width<1||height<1||!isfinite(rect->width)||!isfinite(rect->height)||
     rect->width<=0||rect->height<=0)return;
  struct GeckoImageSize size={width,height};
  uintptr_t *vtable=*(uintptr_t **)target;
  void *surface=((void *(*)(void *,const uint32_t *,const struct GeckoImageSize *,int,int))vtable[50])
    (target,pixels,&size,width*4,0); /* original B8G8R8A8 */
  if(!surface){note("original Gecko image creation failed");return;}
  if(log_fd>=0&&getenv("NEXTSPACE_FIREFOX_TRACE_SCALE"))
    dprintf(log_fd,"%d native-image source=%dx%d destination=%.9g,%.9g %.9gx%.9g\n",
      getpid(),width,height,rect->x,rect->y,rect->width,rect->height);
  struct RectF source={0,0,width,height};
  struct GeckoSurfaceOptions sampling={1,0}; /* original LINEAR, UNBOUNDED */
  struct DrawOptions options={.alpha=1,.composition=1,.antialias=3};
  ((void (*)(void *,void *,const struct RectF *,const struct RectF *,
    const struct GeckoSurfaceOptions *,const struct DrawOptions *))vtable[17])
    (target,surface,rect,&source,&sampling,&options);
  gecko_image_release(surface);
}
