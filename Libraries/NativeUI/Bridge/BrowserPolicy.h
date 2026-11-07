/* Shared bridge scope. Browser-owned UI is preserved by default.
 * A later, explicitly requested app-specific patch may opt into replacement;
 * such a patch still uses the shared NativeUI provider, never copied widgets. */
#ifndef NXS_BROWSER_POLICY_H
#define NXS_BROWSER_POLICY_H
#ifndef NXS_BROWSER_UI_PATCH
#define NXS_BROWSER_UI_PATCH 0
#endif
#endif
