/* Standard xdg-activation requests using the owning client's public C API.
 * Included by WaylandGeometry.c; no event reader, focus policy or UI. MIT. */
struct NXSActivationRequest {
  struct NXSActivationRequest *next;
  NXSGeometrySurface *surface;
  struct xdg_activation_token_v1 *token;
  NXSWaylandActivationToken callback;
  void *context;
};
static void activation_destroy(NXSGeometryDisplay *display,void *resource,uint32_t opcode)
{display->api.marshal_flags(resource,opcode,NULL,1,WL_MARSHAL_FLAG_DESTROY);}
static void activation_cancel(NXSGeometrySurface *surface,int proxies_valid)
{
  while(surface->tokens) {
    struct NXSActivationRequest *request=surface->tokens;surface->tokens=request->next;
    if(proxies_valid)activation_destroy(surface->display,request->token,XDG_ACTIVATION_TOKEN_V1_DESTROY);
    free(request);
  }
}
static void activation_done(void *data,struct xdg_activation_token_v1 *token,const char *name)
{
  struct NXSActivationRequest *request=data;
  struct NXSActivationRequest **link=&request->surface->tokens;
  while(*link&&*link!=request)link=&(*link)->next;
  if(*link)*link=request->next;
  NXSWaylandActivationToken callback=request->callback;void *context=request->context;
  char *copy=name?strdup(name):NULL;
  activation_destroy(request->surface->display,token,XDG_ACTIVATION_TOKEN_V1_DESTROY);free(request);
  /* The callback may destroy its observation and connection. */
  if(copy)callback(context,copy);
  free(copy);
}
static const struct xdg_activation_token_v1_listener activation_listener={.done=activation_done};
static void activation_seat_capabilities(void *data,struct wl_seat *seat,uint32_t capabilities) {}
static const struct wl_seat_listener activation_seat_listener={.capabilities=activation_seat_capabilities};
static int activation_global(NXSGeometryDisplay *display,struct wl_registry *registry,
    uint32_t name,const char *interface,uint32_t version)
{
  if(!strcmp(interface,"xdg_activation_v1")) {
    if(!display->activation&&version>=1)
      display->activation=(void *)display->api.marshal_flags((struct wl_proxy *)registry,
          WL_REGISTRY_BIND,&xdg_activation_v1_interface,1,0,name,interface,1,NULL);
    return 1;
  }
  if(strcmp(interface,"wl_seat"))return 0;
  display->seat_count++;
  if(!display->seat&&version>=1) {
    display->seat=(void *)display->api.marshal_flags((struct wl_proxy *)registry,
        WL_REGISTRY_BIND,&wl_seat_interface,1,0,name,interface,1,NULL);
    if(display->seat) {
      display->seat_name=name;
      display->api.add_listener((struct wl_proxy *)display->seat,(void (**)(void))&activation_seat_listener,display);
    }
  }
  return 1;
}
int nxs_wayland_activation_request(NXSGeometrySurface *surface,struct wl_seat *seat,uint32_t serial,
                                   NXSWaylandActivationToken callback,void *context)
{
  if(!surface||!surface->surface||!surface->received||!surface->value.mapped||!serial||!callback)return 0;
  NXSGeometryDisplay *display=surface->display;
  if(!seat&&display->seat_count==1)seat=display->seat;
  if(!display->activation||!seat)return 0;
  struct NXSActivationRequest *request=calloc(1,sizeof(*request));if(!request)return 0;
  request->surface=surface;request->callback=callback;request->context=context;
  request->token=(void *)display->api.marshal_flags((struct wl_proxy *)display->activation,
      XDG_ACTIVATION_V1_GET_ACTIVATION_TOKEN,&xdg_activation_token_v1_interface,1,0,NULL);
  if(!request->token){free(request);return 0;}
  request->next=surface->tokens;surface->tokens=request;
  display->api.add_listener((struct wl_proxy *)request->token,(void (**)(void))&activation_listener,request);
  display->api.marshal_flags((struct wl_proxy *)request->token,XDG_ACTIVATION_TOKEN_V1_SET_SURFACE,NULL,1,0,surface->surface);
  display->api.marshal_flags((struct wl_proxy *)request->token,XDG_ACTIVATION_TOKEN_V1_SET_SERIAL,NULL,1,0,serial,seat);
  display->api.marshal_flags((struct wl_proxy *)request->token,XDG_ACTIVATION_TOKEN_V1_COMMIT,NULL,1,0);
  display->api.flush(display->wayland);return 1;
}
int nxs_wayland_activation_apply(NXSGeometryDisplay *display,struct wl_surface *surface,const char *token)
{
  if(!display||!display->activation||!surface||!token||!*token||strlen(token)>4096)return 0;
  display->api.marshal_flags((struct wl_proxy *)display->activation,XDG_ACTIVATION_V1_ACTIVATE,NULL,1,0,token,surface);
  display->api.flush(display->wayland);return 1;
}
