/* libxul ace600697490ec169e3e371fb456dcb542e3abef.
 * All inlined IsScrollbarOnRight root tests, excluding the two detours.
 * Native UI uses NSScrollView policy for nested and root scroll containers. */
static const struct {uintptr_t offset;uint32_t original;uintptr_t target;} gecko_scroller_policy_sites[]={
  {0x6de7688ul,0x370803c9u,0x6de7700ul},
  {0x6de77fcul,0x370804a8u,0x6de7890ul},
  {0x6de7f60ul,0x37081928u,0x6de8284ul},
  {0x6de8604ul,0x3708046bu,0x6de8690ul},
  {0x6de9804ul,0x370801cau,0x6de983cul},
  {0x6deaf00ul,0x37080548u,0x6deafa8ul},
  {0x6dec1e0ul,0x37080169u,0x6dec20cul},
  {0x6df974cul,0x37080b08u,0x6df98acul},
  {0x6df9794ul,0x37080308u,0x6df97f4ul},
  {0x6df97c4ul,0x37080528u,0x6df9868ul},
  {0x6dfb70cul,0x374801e9u,0x6dfb748ul},
};
