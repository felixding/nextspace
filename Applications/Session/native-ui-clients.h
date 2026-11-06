/* Retain connected sockets and owner capabilities across native-host loss.
 * This supervisor never reads browser requests or stores control/text models.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include <sys/epoll.h>
#include "../../Libraries/NativeUI/Host/Activation.h"
struct native_ui_owner {
  struct native_ui_owner *next;
  uint32_t process, flags;
  pid_t pid;
  int descriptors[3]; /* eventfd, original pidfd, optional callback endpoint */
  bool sent;
};
struct native_ui_client {
  struct native_ui_client *next;
  struct native_ui_owner *owners;
  uint64_t id;
  int descriptor;
  bool sent;
};
struct native_ui_connections {
  struct native_ui_client *clients;
  uint64_t serial;
  uint32_t epoch;
  unsigned count, owner_count;
  int listener, role, epoll;
  pid_t host;
  bool prepared, restored, ready;
  struct native_ui_watch *watches;
  uint64_t watch_serial;
};
struct native_ui_watch {
  struct native_ui_watch *next;
  int descriptor;
  uint64_t token;
};
static bool native_connections_watch(struct native_ui_connections *state, int operation, int descriptor, uint32_t mask)
{
  struct native_ui_watch **slot = &state->watches;
  while (*slot && (*slot)->descriptor != descriptor) slot = &(*slot)->next;
  if (operation == EPOLL_CTL_DEL) {
    epoll_ctl(state->epoll, operation, descriptor, NULL);
    if (*slot) { struct native_ui_watch *old = *slot; *slot = old->next; free(old); }
    return true;
  }
  struct native_ui_watch *watch = *slot;
  if (!watch) {
    watch = calloc(1, sizeof(*watch)); if (!watch) return false;
    watch->descriptor = descriptor; watch->token = ++state->watch_serial;
  }
  struct epoll_event event = {.events=mask, .data.u64=watch->token};
  if (epoll_ctl(state->epoll, operation, descriptor, &event) < 0) {
    if (!*slot) free(watch); return false;
  }
  *slot = watch; return true;
}
static void native_connections_owner_remove(struct native_ui_connections *state, struct native_ui_owner **slot)
{
  struct native_ui_owner *owner = *slot;
  *slot = owner->next;
  native_connections_watch(state, EPOLL_CTL_DEL, owner->descriptors[1], 0);
  for (int index = 0; index < 3; index++) if (owner->descriptors[index] >= 0) close(owner->descriptors[index]);
  state->owner_count--; free(owner);
}
static void native_connections_client_remove(struct native_ui_connections *state, struct native_ui_client **slot)
{
  struct native_ui_client *client = *slot;
  *slot = client->next;
  while (client->owners) native_connections_owner_remove(state, &client->owners);
  native_connections_watch(state, EPOLL_CTL_DEL, client->descriptor, 0);
  close(client->descriptor); state->count--; free(client);
}
static bool native_connections_prepare(struct native_ui_connections *state, const char *path)
{
  state->listener = socket(AF_UNIX, SOCK_SEQPACKET|SOCK_CLOEXEC|SOCK_NONBLOCK, 0);
  state->epoll = epoll_create1(EPOLL_CLOEXEC);
  state->role = -1;
  if (state->listener < 0 || state->epoll < 0) return false;
  int enabled = 1;
  struct sockaddr_un address = {.sun_family=AF_UNIX};
  strcpy(address.sun_path, path);
  return setsockopt(state->listener, SOL_SOCKET, SO_PASSCRED, &enabled, sizeof(enabled)) == 0 &&
    bind(state->listener, (struct sockaddr *)&address, sizeof(address)) == 0 && chmod(path, 0600) == 0 &&
    listen(state->listener, 32) == 0 &&
    native_connections_watch(state, EPOLL_CTL_ADD, state->listener, EPOLLIN);
}
static void native_connections_child_closed(struct native_ui_connections *state)
{
  if (state->role >= 0) {
    native_connections_watch(state, EPOLL_CTL_DEL, state->role, 0);
    close(state->role);
  }
  state->role = -1; state->prepared = state->restored = state->ready = false;
  for (struct native_ui_client *client = state->clients; client; client = client->next) {
    client->sent = false;
    for (struct native_ui_owner *owner = client->owners; owner; owner = owner->next) owner->sent = false;
  }
}
static int native_connections_child(struct native_ui_connections *state)
{
  native_connections_child_closed(state);
  int pair[2], enabled = 1;
  if (socketpair(AF_UNIX, SOCK_SEQPACKET|SOCK_CLOEXEC|SOCK_NONBLOCK, 0, pair) < 0) return -1;
  if (setsockopt(pair[0], SOL_SOCKET, SO_PASSCRED, &enabled, sizeof(enabled)) < 0 ||
      !native_connections_watch(state, EPOLL_CTL_ADD, pair[0], EPOLLIN)) {
    close(pair[0]); close(pair[1]); return -1;
  }
  state->role = pair[0]; state->epoch++;
  return pair[1];
}
static bool native_connections_send(struct native_ui_connections *state, struct nxs_activation *packet, const int *descriptors, unsigned count)
{
  packet->magic = NXS_ACTIVATION_MAGIC;
  packet->epoch = state->epoch;
  struct iovec data = {.iov_base=packet, .iov_len=sizeof(*packet)};
  char ancillary[CMSG_SPACE(sizeof(int)*3)] = {0};
  struct msghdr message = {.msg_iov=&data, .msg_iovlen=1};
  if (count) {
    message.msg_control = ancillary; message.msg_controllen = CMSG_SPACE(sizeof(int)*count);
    struct cmsghdr *header = CMSG_FIRSTHDR(&message);
    header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
    header->cmsg_len = CMSG_LEN(sizeof(int)*count); memcpy(CMSG_DATA(header), descriptors, sizeof(int)*count);
  }
  return sendmsg(state->role, &message, MSG_DONTWAIT|MSG_NOSIGNAL) == sizeof(*packet);
}
static void native_connections_flush(struct native_ui_connections *state)
{
  if (!state->prepared || state->role < 0) return;
  for (struct native_ui_client *client = state->clients; client; client = client->next) {
    struct nxs_activation packet = {.operation=NXS_ACTIVATION_CLIENT, .client=client->id};
    if (!client->sent) {
      if (!native_connections_send(state, &packet, &client->descriptor, 1)) goto pending;
      client->sent = true;
    }
    for (struct native_ui_owner *owner = client->owners; owner; owner = owner->next) if (!owner->sent) {
      struct pollfd life = {.fd=owner->descriptors[1], .events=POLLIN};
      if (poll(&life, 1, 0) != 0) continue;
      packet = (struct nxs_activation){.operation=NXS_ACTIVATION_OWNER, .client=client->id,
        .process=owner->process, .pid=owner->pid, .flags=owner->flags};
      if (!native_connections_send(state, &packet, owner->descriptors, owner->flags&NXS_ACTIVATION_FILTER ? 3 : 2)) goto pending;
      owner->sent = true;
    }
  }
  if (!state->restored) {
    struct nxs_activation packet = {.operation=NXS_ACTIVATION_EPOCH};
    if (!native_connections_send(state, &packet, NULL, 0)) goto pending;
    state->restored = true;
  }
  native_connections_watch(state, EPOLL_CTL_MOD, state->role, EPOLLIN);
  return;
pending:
  native_connections_watch(state, EPOLL_CTL_MOD, state->role, EPOLLIN|EPOLLOUT);
}
static bool native_connections_receive(struct native_ui_connections *state)
{
  struct nxs_activation packet;
  char ancillary[CMSG_SPACE(sizeof(int)*8)+CMSG_SPACE(sizeof(struct ucred))];
  struct iovec data = {.iov_base=&packet, .iov_len=sizeof(packet)};
  struct msghdr message = {.msg_iov=&data, .msg_iovlen=1, .msg_control=ancillary, .msg_controllen=sizeof(ancillary)};
  ssize_t size = recvmsg(state->role, &message, MSG_DONTWAIT|MSG_CMSG_CLOEXEC);
  if (size < 0 && (errno == EAGAIN || errno == EINTR)) return true;
  int descriptors[8], count = 0; bool credentials = false;
  for (struct cmsghdr *header = CMSG_FIRSTHDR(&message); size >= 0 && header; header = CMSG_NXTHDR(&message, header)) {
    if (header->cmsg_level != SOL_SOCKET) continue;
    if (header->cmsg_type == SCM_CREDENTIALS && header->cmsg_len == CMSG_LEN(sizeof(struct ucred))) {
      struct ucred peer; memcpy(&peer, CMSG_DATA(header), sizeof(peer));
      credentials = peer.pid == state->host && peer.uid == getuid();
    } else if (header->cmsg_type == SCM_RIGHTS) {
      unsigned number = (header->cmsg_len-CMSG_LEN(0))/sizeof(int);
      int *fds = (int *)CMSG_DATA(header);
      for (unsigned index = 0; index < number; index++) {
        if (count < 8) descriptors[count++] = fds[index]; else close(fds[index]);
      }
    }
  }
  bool valid = size == sizeof(packet) && !(message.msg_flags&(MSG_TRUNC|MSG_CTRUNC)) &&
    credentials && packet.magic == NXS_ACTIVATION_MAGIC;
  if (!valid) goto finish;
  if (packet.operation == NXS_ACTIVATION_PREPARED && !count && !state->prepared) state->prepared = true;
  else if (packet.operation == NXS_ACTIVATION_READY && !count && state->restored && packet.epoch == state->epoch) state->ready = true;
  else if ((packet.operation == NXS_ACTIVATION_OWNER || packet.operation == NXS_ACTIVATION_REMOVE) && packet.process) {
    struct native_ui_client *client = state->clients;
    while (client && client->id != packet.client) client = client->next;
    if (!client) goto finish;
    struct native_ui_owner **slot = &client->owners;
    while (*slot && (*slot)->process != packet.process) slot = &(*slot)->next;
    if (packet.operation == NXS_ACTIVATION_REMOVE && !count) {
      if (*slot) native_connections_owner_remove(state, slot);
    } else if (packet.operation == NXS_ACTIVATION_OWNER && packet.pid > 0 && (packet.flags&1) && !(packet.flags&~15u) &&
               count == (packet.flags&NXS_ACTIVATION_FILTER ? 3 : 2) && (state->owner_count < 1024 || *slot)) {
      if (*slot) native_connections_owner_remove(state, slot);
      struct native_ui_owner *owner = calloc(1, sizeof(*owner));
      if (!owner) { valid = false; goto finish; }
      *owner = (struct native_ui_owner){.process=packet.process, .pid=packet.pid, .flags=packet.flags,
        .descriptors={descriptors[0],descriptors[1],count==3 ? descriptors[2] : -1}, .sent=true, .next=*slot};
      if (!native_connections_watch(state, EPOLL_CTL_ADD, owner->descriptors[1], EPOLLIN)) {
        free(owner); valid = false; goto finish;
      }
      count = 0; *slot = owner; state->owner_count++;
    } else valid = false;
  } else valid = false;
finish:
  for (int index = 0; index < count; index++) close(descriptors[index]);
  if (!valid) fprintf(stderr, "[session] Native activation rejected: bytes=%zd credentials=%d descriptors=%d.\n", size, credentials, count);
  return valid;
}
static bool native_connections_dispatch(struct native_ui_connections *state)
{
  if (state->epoll < 0) return true;
  struct epoll_event events[32];
  int count = epoll_wait(state->epoll, events, 32, 0);
  if (count < 0) return errno == EINTR;
  for (int index = 0; index < count; index++) {
    struct native_ui_watch *watch = state->watches;
    while (watch && watch->token != events[index].data.u64) watch = watch->next;
    if (!watch) continue; /* Removed/replaced while this batch was pending. */
    int descriptor = watch->descriptor;
    if (descriptor == state->listener) {
      int incoming = accept4(state->listener, NULL, NULL, SOCK_CLOEXEC);
      if (incoming < 0) continue;
      if (state->count >= 128) { close(incoming); continue; }
      struct native_ui_client *client = calloc(1, sizeof(*client));
      if (!client || !native_connections_watch(state, EPOLL_CTL_ADD, incoming, EPOLLRDHUP)) {
        free(client); close(incoming); continue;
      }
      *client = (struct native_ui_client){.next=state->clients, .id=++state->serial, .descriptor=incoming};
      state->clients = client; state->count++;
    } else if (descriptor == state->role) {
      if (events[index].events&EPOLLIN && !native_connections_receive(state)) return false;
      if (events[index].events&(EPOLLERR|EPOLLHUP)) return false;
    } else {
      struct native_ui_client **slot = &state->clients;
      while (*slot) {
        if ((*slot)->descriptor == descriptor) { native_connections_client_remove(state, slot); break; }
        struct native_ui_owner **owner = &(*slot)->owners;
        while (*owner) {
          if ((*owner)->descriptors[1] == descriptor) { native_connections_owner_remove(state, owner); break; }
          owner = &(*owner)->next;
        }
        slot = &(*slot)->next;
      }
    }
  }
  native_connections_flush(state); return true;
}
static void native_connections_finish(struct native_ui_connections *state)
{
  native_connections_child_closed(state);
  while (state->clients) native_connections_client_remove(state, &state->clients);
  if (state->listener >= 0) close(state->listener);
  if (state->epoll >= 0) close(state->epoll);
  state->listener = state->epoll = -1;
  while (state->watches) { struct native_ui_watch *next = state->watches->next; free(state->watches); state->watches = next; }
}
