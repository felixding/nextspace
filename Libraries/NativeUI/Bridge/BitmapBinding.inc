/* Retained native snapshots only; no widget drawing or input policy.
 * Include after Transport.inc. GPL-2.0-or-later. */
struct NXSBitmapBinding {
  uint32_t *pixels;
  int width,height;
  uint32_t epoch;
};
static int __attribute__((unused)) native_bitmap_response_valid(const struct NXSResponse *response)
{
  return response&&response->width>=1&&response->height>=1&&response->width<=8192&&response->height<=8192&&
    (size_t)response->width*response->height<=8*1024*1024&&response->stride==response->width*4&&
    sizeof(*response)+(size_t)response->stride*response->height==response->size;
}
static int __attribute__((unused)) native_bitmap_store(struct NXSBitmapBinding *image,const struct NXSResponse *response)
{
  if(!native_bitmap_response_valid(response))return 0;
  uint32_t *pixels=malloc((size_t)response->stride*response->height);if(!pixels)return 0;
  memcpy(pixels,response+1,(size_t)response->stride*response->height);free(image->pixels);
  *image=(struct NXSBitmapBinding){pixels,response->width,response->height,atomic_load(&native_host_epoch)};return 1;
}
static int __attribute__((unused)) native_bitmap_available(const struct NXSBitmapBinding *image)
{return image&&image->pixels&&image->epoch==atomic_load(&native_host_epoch);}
static void __attribute__((unused)) native_bitmap_retire(struct NXSBitmapBinding *image)
{free(image->pixels);memset(image,0,sizeof(*image));}
