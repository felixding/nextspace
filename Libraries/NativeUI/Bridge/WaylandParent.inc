/* Standard xdg-foreign ownership transport; no toolkit or window policy. MIT. */
static void parent_cancel(NXSGeometrySurface *surface,int valid)
{
  if(surface->exported&&valid)
    activation_destroy(surface->display,surface->exported,ZXDG_EXPORTED_V2_DESTROY);
  surface->exported=NULL;free(surface->parent_handle);surface->parent_handle=NULL;
}
static void parent_handle(void *data,struct zxdg_exported_v2 *exported,const char *handle)
{
  NXSGeometrySurface *surface=data;
  free(surface->parent_handle);surface->parent_handle=strdup(handle);
}
static const struct zxdg_exported_v2_listener parent_listener={.handle=parent_handle};
static void parent_attach(NXSGeometrySurface *surface)
{
  NXSGeometryDisplay *display=surface->display;
  if(!display->exporter||!surface->surface||surface->exported)return;
  surface->exported=(void *)display->api.marshal_flags((struct wl_proxy *)display->exporter,
    ZXDG_EXPORTER_V2_EXPORT_TOPLEVEL,&zxdg_exported_v2_interface,1,0,NULL,surface->surface);
  if(surface->exported)display->api.add_listener((struct wl_proxy *)surface->exported,
    (void (**)(void))&parent_listener,surface);
}
static int parent_global(NXSGeometryDisplay *display,struct wl_registry *registry,
    uint32_t name,const char *interface,uint32_t version)
{
  if(strcmp(interface,"zxdg_exporter_v2"))return 0;
  if(!display->exporter&&version>=1) {
    display->exporter=(void *)display->api.marshal_flags((struct wl_proxy *)registry,
      WL_REGISTRY_BIND,&zxdg_exporter_v2_interface,1,0,name,interface,1,NULL);
    for(NXSGeometrySurface *surface=display->surfaces;surface;surface=surface->next)parent_attach(surface);
    display->api.flush(display->wayland);
  }
  return 1;
}
const char *nxs_wayland_geometry_parent(NXSGeometrySurface *surface)
{return surface?surface->parent_handle:NULL;}
