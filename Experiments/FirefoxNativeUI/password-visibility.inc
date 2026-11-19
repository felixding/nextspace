/* Bind Firefox's original reveal state to existing native plain/secure fields.
 * Its Reveal Password action changes ElementState::REVEALED, not editor echo. */
static const unsigned char password_reveal_bytes[20]={0x5f,0x24,0x03,0xd5,0x08,0x38,0x40,0xf9,0x09,0x40,0x42,0x39,0x08,0xb9,0x6e,0xd3,0x3f,0x31,0x02,0x71};
static const unsigned char password_set_reveal_bytes[20]={0x3f,0x23,0x03,0xd5,0xff,0x03,0x01,0xd1,0xfe,0x57,0x02,0xa9,0xf4,0x4f,0x03,0xa9,0xa8,0x52,0x02,0xb0};
static int guard_password_visibility(void)
{return !memcmp((void *)(base+0x588f094),password_reveal_bytes,20);}
static int password_presentation_kind(void *node)
{
  int kind=node_kind(node);
  return kind==NXS_PASSWORD&&((uint8_t (*)(const void *))(base+0x588f094))(node)?NXS_TEXTFIELD:kind;
}
static void (*original_password_set_reveal)(void *,int);
static void password_set_reveal(void *node,int revealed)
{
  original_password_set_reveal(node,revealed);
  /* Preserve Firefox's own cancellable authentication/policy event. Read its
   * resulting state during paint, including when the source rejects reveal. */
  struct Widget *w=widget_for_node(node);if(w&&text_kind(w->kind))invalidate_widget(w);
}
