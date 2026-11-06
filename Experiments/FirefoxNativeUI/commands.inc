/* Bind native selectors to Gecko's own text-control command callback.
 * That callback performs controller lookup, availability checks and dispatch;
 * the address bar's registered custom controller stays authoritative. */
static const struct {const char *selector,*name;uint8_t command;} text_commands[]={
  {"copy:","cmd_copy",5},{"cut:","cmd_cut",6},{"paste:","cmd_paste",24}
};
static int guard_text_commands(void) {
  static const unsigned char callback[20]={0x3f,0x23,0x03,0xd5,0xff,0x43,0x01,0xd1,0xfe,0x57,0x03,0xa9,0xf4,0x4f,0x04,0xa9,0xe8,0x50,0x02,0xd0};
  static const unsigned char names[20]={0x5f,0x24,0x03,0xd5,0x08,0x1c,0x00,0x12,0x1f,0x39,0x02,0x71,0xe2,0x00,0x00,0x54,0x08,0x1c,0x40,0x92};
  static const unsigned char modifiers[20]={0x5f,0x24,0x03,0xd5,0x08,0x0c,0x00,0x51,0x09,0x3d,0x00,0x12,0x3f,0x35,0x00,0x71,0xc8,0x00,0x00,0x54};
  static const unsigned char key_name_copy[8]={0x88,0xba,0x41,0x79,0x68,0xba,0x01,0x79};
  static const unsigned char controllers[20]={0x3f,0x23,0x03,0xd5,0xff,0x03,0x01,0xd1,0xfe,0x57,0x02,0xa9,0xf4,0x4f,0x03,0xa9,0x88,0x52,0x02,0xd0};
  if(memcmp((void *)(base+0x58c5a78),callback,20)||memcmp((void *)(base+0x6a67864),names,20)||
     memcmp((void *)(base+0x6a65f94),modifiers,20)||memcmp((void *)(base+0x4849be0),key_name_copy,8)||
     memcmp((void *)(base+0x589119c),controllers,20))return 0;
  for(unsigned n=0;n<sizeof(text_commands)/sizeof(*text_commands);n++) {
    const char *name=((const char *(*)(uint8_t))(base+0x6a67864))(text_commands[n].command);
    if(strcmp(name,text_commands[n].name))return 0;
  }
  return 1;
}
static int text_modifier_event(const void *event) {
  /* Gecko owns the modifier-key classification; use its actual key name,
   * rather than maintaining another key-code or shortcut table. */
  return ((unsigned (*)(uint16_t))(base+0x6a65f94))(*(const uint16_t *)((const char *)event+220))!=0;
}
static int application_text_command(void *node,const char *selector) {
  if(!selector)return 0;
  for(unsigned n=0;n<sizeof(text_commands)/sizeof(*text_commands);n++)if(!strcmp(selector,text_commands[n].selector)) {
    ((void (*)(uint8_t,void *))(base+0x58c5a78))(text_commands[n].command,node);
    if(log_fd>=0)dprintf(log_fd,"%d native-text-command command=%s\n",getpid(),text_commands[n].name);
    return 1;
  }
  return 0;
}
static int application_text_command_enabled(void *node,const char *selector) {
  const char *name=NULL;
  for(unsigned n=0;n<sizeof(text_commands)/sizeof(*text_commands);n++)
    if(!strcmp(selector,text_commands[n].selector)){name=text_commands[n].name;break;}
  if(!name)return -1;
  void *controllers=NULL,*controller=NULL;uint8_t enabled=0;
  uintptr_t getter=node_kind(node)==NXS_TEXTAREA?NXS_GECKO_MULTILINE_CONTROLLERS_OFFSET:0x589119c;
  uint32_t status=((uint32_t (*)(void *,void **))(base+getter))(node,&controllers);
  if(!(status&0x80000000u)&&controllers) {
    status=((uint32_t (*)(void *,const char *,void **))(*(uintptr_t **)controllers)[3])(controllers,name,&controller);
    if(!(status&0x80000000u)&&controller) {
      status=((uint32_t (*)(void *,const char *,uint8_t *))(*(uintptr_t **)controller)[3])(controller,name,&enabled);
      if(status&0x80000000u)enabled=0;
    }
  }
  if(controller)((unsigned (*)(void *))(*(uintptr_t **)controller)[2])(controller);
  if(controllers)((unsigned (*)(void *))(*(uintptr_t **)controllers)[2])(controllers);
  return !!enabled;
}
