# Firefox native UI integration

This is the Gecko side of the browser-first
[native application integration](../../docs/Native-Control-Integration.md).
Use the existing shared NativeUI provider and actual NEXTSPACE controls; keep
engine/frontend model and event adapters separate from the UI implementation.
Firefox, its derivatives and their application interfaces are part of the goal.

An unchanged Debian ARM64 Firefox ESR archive has been verified and extracted
in the private guest test directory `/var/tmp/nextspace-firefox-prototype/`.
[`binary-pin.json`](binary-pin.json) records its archive/executable/library
hashes, ELF build IDs and upstream revision declared by the package. No package
was installed and the installed package inventory is unchanged.

This is binary preparation only. Firefox has not been launched or connected to
NativeUI, and no Gecko hooks, native controls, menus, browser UI, input behavior
or derivative compatibility have been qualified. The adapter must preserve the
browser sandbox and its real application actions without rebuilding Firefox.
Inspect the matching engine/frontend interfaces and verify runtime behavior
before adding any accepted binary pin or native-support claim.
