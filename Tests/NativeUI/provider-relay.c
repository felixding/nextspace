/* Test provider selection while retaining the real native UI implementation.
 * No control is implemented here. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
const NXSNativeUIAPI *nxs_native_ui_provider(uint32_t version)
{
#ifdef TEST_BAD_ABI
  static const NXSNativeUIAPI incompatible={.version=99,.size=sizeof(NXSNativeUIAPI)};
  return &incompatible;
#else
  const char *path=getenv("NXS_TEST_REAL_PROVIDER");
  void *library=path?dlopen(path,RTLD_NOW|RTLD_LOCAL):NULL;
  const NXSNativeUIAPI *(*provider)(uint32_t)=library?dlsym(library,"nxs_native_ui_provider"):NULL;
  if(!provider)return NULL;
  fprintf(stderr,"native-ui-test-provider-selected\n");
  return provider(version);
#endif
}
