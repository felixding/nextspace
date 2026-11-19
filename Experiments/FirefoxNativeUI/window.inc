/* Shared original document/window ownership. No focus or window policy. */
static void gecko_release_window(void *window)
{if(window)((unsigned (*)(void *))(*(uintptr_t **)window)[2])(window);}
static void *gecko_node_owner_inner(void *node)
{
  /* Original ShowPicker loads OwnerDoc from NodeInfo +8, GetInnerWindow
   * from Document +1128 (unless removed from its docshell), and its original
   * WindowGlobalChild from inner +200. The guarded instruction span and exact
   * nsPIDOMWindow header establish inner.mDoc +16 and mOuterWindow +112.
   * Only object ownership is adapted; the original focus manager supplies
   * this window's remembered focus even while the global focus is in transit. */
  void *info=*(void **)((char *)node+40);
  void *document=info?*(void **)((char *)info+8):NULL;
  if(!document||(*((unsigned char *)document+763)&2))return NULL;
  void *inner=*(void **)((char *)document+1128);
  if(!inner||*(void **)((char *)inner+16)!=document)return NULL;
  ((unsigned (*)(void *))(*(uintptr_t **)inner)[1])(inner);
  return inner;
}
static void *gecko_node_owner_window(void *node)
{
  void *inner=gecko_node_owner_inner(node);if(!inner)return NULL;
  void *window=*(void **)((char *)inner+112);
  if(window)((unsigned (*)(void *))(*(uintptr_t **)window)[1])(window);
  gecko_release_window(inner);
  return window;
}
