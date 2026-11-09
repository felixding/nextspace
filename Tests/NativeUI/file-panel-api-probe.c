/* ABI compatibility only; real native modal behavior is exercised through
 * the public portal and original browser inputs. GPL-2.0-or-later. */
#include "NativeUI.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
_Static_assert(offsetof(NXSNativeUIAPI,event_source_callback)==648,"Preserve the previous provider ABI");
_Static_assert(offsetof(NXSFilePanelConfig,parent_window)==80,"Preserve original file-panel model prefix");
_Static_assert(sizeof(NXSFilePanelConfig)==88,"Appended optional portal parent");
_Static_assert(offsetof(NXSNativeUIAPI,file_panel_parent_capabilities)==736,"Preserve auxiliary activation ABI");
_Static_assert(sizeof(NXSFileChoice)==32,"Native choice layout");
_Static_assert(sizeof(NXSFilePanelState)==16,"File-panel state layout");
int main(int argc,char **argv)
{
  int older=argc>1&&!strcmp(argv[1],"--older-provider");
  const NXSNativeUIAPI *api=nxs_native_ui_api();assert(api&&api->version==1);
  assert(nxs_native_ui_source_capabilities()==1);
  assert((nxs_file_panel_capabilities()&1)==!older);
  assert(nxs_native_ui_callback_source_capabilities()==!older);
  assert(!nxs_native_ui_source_callback(-1,NULL,NULL));
  assert(!nxs_file_panel_create(-1,NULL,NULL));
  assert(!nxs_file_panel_configure(NULL,NULL));
  assert(nxs_file_panel_run(NULL)==2&&!nxs_file_panel_cancel(NULL));
  NXSFilePanelState state=nxs_file_panel_state(NULL);assert(state.size==16&&state.result==2&&!state.count);
  assert(!nxs_file_panel_result(NULL,0,NULL,0)&&nxs_file_panel_choice(NULL,0)==-1);
  assert(!nxs_file_panel_destroy(NULL));
  if(argc>1&&!strcmp(argv[1],"--native-config")) {
    NXSFilePanel *panel=nxs_file_panel_create(NXS_FILE_OPEN,NULL,NULL);assert(panel);
    /* A real old-size consumer must not read the appended pointer at all. */
    NXSFilePanelConfig config={.size=offsetof(NXSFilePanelConfig,parent_window),
      .title="Native file model compatibility",.parent_window=(const char *)1};
    assert(nxs_file_panel_configure(panel,&config));
    config.size=sizeof(config);config.parent_window=NULL;
    assert(nxs_file_panel_configure(panel,&config));
    assert(nxs_file_panel_destroy(panel));
    puts("{\"legacy_80_byte_model\":true,\"current_88_byte_model\":true}");
  }
  printf("{\"older_provider\":%s,\"api_size\":%u,\"passed\":true}\n",older?"true":"false",api->size);
}
