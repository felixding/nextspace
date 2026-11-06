/* Private session/host descriptor handoff. No native UI or application data.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef NXS_NATIVE_ACTIVATION_H
#define NXS_NATIVE_ACTIVATION_H
#define NXS_ACTIVATION_MAGIC 0x4e584146u
enum { NXS_ACTIVATION_PREPARED=1, NXS_ACTIVATION_CLIENT,
  NXS_ACTIVATION_OWNER, NXS_ACTIVATION_REMOVE,
  NXS_ACTIVATION_EPOCH, NXS_ACTIVATION_READY, NXS_ACTIVATION_STOP };
enum { NXS_ACTIVATION_NOTIFY=1, NXS_ACTIVATION_FILTER=2,
  NXS_ACTIVATION_COMMANDS=4, NXS_ACTIVATION_MENUS=8 };
struct nxs_activation {
  uint32_t magic, operation;
  uint64_t client;
  uint32_t process;
  int32_t pid;
  uint32_t flags, epoch;
};
_Static_assert(sizeof(struct nxs_activation)==32, "Private native activation envelope");
#endif
