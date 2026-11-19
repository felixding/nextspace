/* Native menu matching at Gecko's existing global-command boundary. Content
 * cancellation and remote-event reply ordering remain Gecko's implementation. */
static int menu_keys_requested;
static uint64_t (*original_global_key_walk)(void *,unsigned,void *);
static uint64_t global_key_walk(void *listener,unsigned purpose,void *dom_event)
{
  if(application_menu_keys&&purpose<=1&&((int (*)(void))(base+0x7546c5c))()) {
    void *event=((void *(*)(void *))(base+0x34fce18))(dom_event);
    uint32_t flags=*(uint32_t *)((char *)event+48);
    /* eKeyDown=4. Trust/default-prevention/APZ are also checked by Gecko's
     * callers; keep them explicit before crossing the independent UI bridge. */
    if(*(uint16_t *)((char *)event+18)==4&&(flags&1)&&!(flags&((1u<<9)|(1u<<23)))&&
       !text_modifier_event(event)&&ensure_widget_lifetime()) {
      char *text=key_text(event);
      if(text) {
        NXSKeyEvent key={.size=sizeof(key),.type=NXS_KEY_DOWN,.text=text,.unmodified_text=text,
          .key=logical_key(*(uint32_t *)((char *)event+200)),.modifiers=widget_modifiers(event),
          .repeat=!!*((uint8_t *)event+223)};
        /* Modal menu input precedes the retained chrome field's handlers.
         * Preventing this original event also prevents a second walk from
         * dispatching its action again. NSMenu owns matching and commands. */
        int modal=gtk_context_owns_keys();
        int execute=purpose==0||modal;
        int accepted=native_application_menu_key(&key,execute);free(text);
        if(accepted||modal) {
          if(execute)((void (*)(void *))(base+0x56ff600))(dom_event);
          if(log_fd>=0)dprintf(log_fd,"%d native-global-menu-key execute=%d\n",getpid(),execute);
          /* WalkHandlersResult: meaningful=true, reserved=false, disabled=false,
           * no relevant engine command. LookForCommand therefore uses Gecko's
           * normal remote-reply wait without reserving the key against content. */
          return 1;
        }
      }
    }
  }
  return original_global_key_walk(listener,purpose,dom_event);
}
static const unsigned char global_key_walk_bytes[]={0x3f,0x23,0x03,0xd5,0xff,0x43,0x03,0xd1,0xfd,0x7b,0x07,0xa9,0xfc,0x6f,0x08,0xa9,0xfa,0x67,0x09,0xa9};
static struct Detour global_key_detours[]={
  {0x5710c10,global_key_walk_bytes,global_key_walk,(void **)&original_global_key_walk}
};
static int prepare_global_keys(void)
{
  static const unsigned char prevent[]={0x5f,0x24,0x03,0xd5,0x21,0x00,0x80,0x52,0xe2,0x03,0x1f,0xaa,0x01,0x00,0x00,0x14};
  static const unsigned char pointer[]={0x5f,0x24,0x03,0xd5,0x00,0x14,0x40,0xf9,0xc0,0x03,0x5f,0xd6};
  static const unsigned char parent[]={0x5f,0x24,0x03,0xd5,0xe8,0x6c,0x01,0xd0,0x08,0xad,0x40,0xf9,0x08,0x01,0x40,0xb9,0x1f,0x01,0x00,0x71};
  return !menu_keys_requested||(prepare_key_registry()&&!memcmp((void *)(base+0x56ff600),prevent,sizeof(prevent))&&
    !memcmp((void *)(base+0x34fce18),pointer,sizeof(pointer))&&
    !memcmp((void *)(base+0x7546c5c),parent,sizeof(parent))&&
    prepare_detours(global_key_detours,sizeof(global_key_detours)/sizeof(*global_key_detours)));
}
