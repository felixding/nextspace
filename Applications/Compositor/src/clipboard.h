/* Bounded, asynchronous clipboard ownership. SPDX-License-Identifier: MIT */
#include <pthread.h>

#define CLIPBOARD_LIMIT (64 * 1024 * 1024)

struct clipboard_item {
  struct wl_list link;
  struct clipboard_snapshot *snapshot;
  char *mime;
  unsigned char *bytes;
  size_t length, capacity;
  int fd;
  struct wl_event_source *reader;
};

struct clipboard_snapshot {
  struct wlr_data_source source;
  struct nextspace_server *server;
  struct wl_list items;
  struct wlr_data_source *original;
  struct wl_listener original_destroy;
  struct wl_event_source *timeout;
  unsigned pending, refs;
};

struct clipboard_write {
  struct wl_list link;
  struct clipboard_snapshot *snapshot;
  struct clipboard_item *item;
  size_t offset;
  int fd;
  struct wl_event_source *writer, *timeout;
};

static void clipboard_unref(struct clipboard_snapshot *snapshot)
{
  if (--snapshot->refs) return;
  struct clipboard_item *item, *next;
  wl_list_for_each_safe(item, next, &snapshot->items, link) {
    snapshot->server->clipboard_bytes -= item->capacity;
    wl_list_remove(&item->link);
    free(item->bytes); free(item);
  }
  free(snapshot);
}

static void clipboard_write_finish(struct clipboard_write *transfer)
{
  if (transfer->writer) wl_event_source_remove(transfer->writer);
  if (transfer->timeout) wl_event_source_remove(transfer->timeout);
  close(transfer->fd);
  wl_list_remove(&transfer->link);
  clipboard_unref(transfer->snapshot);
  free(transfer);
}

/* Suppress only this write's SIGPIPE without changing child-process policy. */
static ssize_t clipboard_write_bytes(int fd, const void *bytes, size_t length)
{
  sigset_t blocked, previous, pending;
  sigemptyset(&blocked); sigaddset(&blocked, SIGPIPE);
  pthread_sigmask(SIG_BLOCK, &blocked, &previous);
  sigpending(&pending);
  ssize_t count = write(fd, bytes, length);
  int saved_errno = errno;
  if (count < 0 && saved_errno == EPIPE && !sigismember(&pending, SIGPIPE)) {
    const struct timespec zero = {0};
    while (sigtimedwait(&blocked, NULL, &zero) < 0 && errno == EINTR) {}
  }
  pthread_sigmask(SIG_SETMASK, &previous, NULL);
  errno = saved_errno;
  return count;
}

static int clipboard_write_ready(int fd, uint32_t mask, void *data)
{
  struct clipboard_write *transfer = data;
  size_t budget = 65536;
  while (transfer->offset < transfer->item->length && budget) {
    size_t length = transfer->item->length - transfer->offset;
    if (length > budget) length = budget;
    ssize_t count = clipboard_write_bytes(fd, transfer->item->bytes + transfer->offset, length);
    if (count < 0 && errno == EINTR) continue;
    if (count < 0 && errno == EAGAIN) return 0;
    if (count <= 0) { clipboard_write_finish(transfer); return 0; }
    transfer->offset += count; budget -= count;
  }
  if (transfer->offset == transfer->item->length) clipboard_write_finish(transfer);
  return 0;
}

static int clipboard_write_timeout(void *data)
{
  clipboard_write_finish(data);
  return 0;
}

static void clipboard_send(struct wlr_data_source *source, const char *mime, int32_t fd)
{
  struct clipboard_snapshot *snapshot = wl_container_of(source, snapshot, source);
  if (wl_list_length(&snapshot->server->clipboard_writes) >= 16) { close(fd); return; }
  struct clipboard_item *item;
  wl_list_for_each(item, &snapshot->items, link) {
    if (strcmp(item->mime, mime) != 0) continue;
    struct clipboard_write *transfer = calloc(1, sizeof(*transfer));
    if (!transfer) { close(fd); return; }
    transfer->snapshot = snapshot; transfer->item = item; transfer->fd = fd;
    snapshot->refs++;
    wl_list_insert(&snapshot->server->clipboard_writes, &transfer->link);
    fcntl(fd, F_SETFD, FD_CLOEXEC);
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
      clipboard_write_finish(transfer); return;
    }
    struct wl_event_loop *loop = wl_display_get_event_loop(snapshot->server->wl_display);
    transfer->writer = wl_event_loop_add_fd(loop, fd, WL_EVENT_WRITABLE, clipboard_write_ready, transfer);
    transfer->timeout = wl_event_loop_add_timer(loop, clipboard_write_timeout, transfer);
    if (!transfer->writer || !transfer->timeout) { clipboard_write_finish(transfer); return; }
    wl_event_source_timer_update(transfer->timeout, 5000);
    clipboard_write_ready(fd, WL_EVENT_WRITABLE, transfer);
    return;
  }
  close(fd);
}

static void clipboard_stop_reading(struct clipboard_snapshot *snapshot)
{
  if (snapshot->timeout) wl_event_source_remove(snapshot->timeout);
  snapshot->timeout = NULL;
  if (snapshot->original) wl_list_remove(&snapshot->original_destroy.link);
  snapshot->original = NULL;
  struct clipboard_item *item;
  wl_list_for_each(item, &snapshot->items, link) {
    if (item->reader) wl_event_source_remove(item->reader);
    item->reader = NULL;
    if (item->fd >= 0) close(item->fd);
    item->fd = -1;
  }
}

static void clipboard_destroy(struct wlr_data_source *source)
{
  struct clipboard_snapshot *snapshot = wl_container_of(source, snapshot, source);
  if (snapshot->server->clipboard_copy == snapshot) snapshot->server->clipboard_copy = NULL;
  clipboard_stop_reading(snapshot);
  clipboard_unref(snapshot);
}

static const struct wlr_data_source_impl clipboard_impl = {
  .send = clipboard_send, .destroy = clipboard_destroy
};

static void clipboard_cancel_copy(struct nextspace_server *server)
{
  if (server->clipboard_copy) wlr_data_source_destroy(&server->clipboard_copy->source);
}

static int clipboard_read_timeout(void *data)
{
  struct clipboard_snapshot *snapshot = data;
  wlr_data_source_destroy(&snapshot->source);
  return 0;
}

static int clipboard_read_ready(int fd, uint32_t mask, void *data)
{
  struct clipboard_item *item = data;
  struct clipboard_snapshot *snapshot = item->snapshot;
  unsigned char bytes[16384];
  for (unsigned batch = 0; batch < 4; batch++) {
    ssize_t count = read(fd, bytes, sizeof(bytes));
    if (count < 0 && errno == EINTR) continue;
    if (count < 0 && errno == EAGAIN) return 0;
    if (count < 0) { wlr_data_source_destroy(&snapshot->source); return 0; }
    if (count == 0) {
      wl_event_source_remove(item->reader); item->reader = NULL;
      close(item->fd); item->fd = -1;
      if (--snapshot->pending == 0) {
        clipboard_stop_reading(snapshot);
        snapshot->server->clipboard_copy = NULL;
        wlr_seat_set_selection(snapshot->server->seat, &snapshot->source,
          snapshot->server->seat->selection_serial);
      }
      return 0;
    }
    size_t needed = item->length + count;
    if (needed > item->capacity) {
      size_t capacity = item->capacity ? item->capacity * 2 : sizeof(bytes);
      if (capacity < needed) capacity = needed;
      size_t extra = capacity - item->capacity;
      if (extra > CLIPBOARD_LIMIT - snapshot->server->clipboard_bytes) {
        wlr_data_source_destroy(&snapshot->source); return 0;
      }
      unsigned char *resized = realloc(item->bytes, capacity);
      if (!resized) { wlr_data_source_destroy(&snapshot->source); return 0; }
      snapshot->server->clipboard_bytes += extra;
      item->bytes = resized; item->capacity = capacity;
    }
    memcpy(item->bytes + item->length, bytes, count);
    item->length += count;
  }
  return 0;
}

static void clipboard_original_destroy(struct wl_listener *listener, void *data)
{
  struct clipboard_snapshot *snapshot = wl_container_of(listener, snapshot, original_destroy);
  wl_list_remove(&snapshot->original_destroy.link);
  snapshot->original = NULL;
  /* Requests already in flight can still finish after the producer exits. */
}

static void clipboard_changed(struct wl_listener *listener, void *data)
{
  struct nextspace_server *server = wl_container_of(listener, server, clipboard_selection);
  struct wlr_data_source *source = server->seat->selection_source;
  if (source && source->impl == &clipboard_impl) return;
  if (server->clipboard_copy && !source && !server->clipboard_copy->original) return;
  clipboard_cancel_copy(server);
  if (!source || source->mime_types.size == 0 || source->mime_types.size / sizeof(char *) > 64) return;
  struct clipboard_snapshot *snapshot = calloc(1, sizeof(*snapshot));
  if (!snapshot) return;
  wlr_data_source_init(&snapshot->source, &clipboard_impl);
  snapshot->server = server; snapshot->refs = 1; snapshot->original = source;
  wl_list_init(&snapshot->items);
  snapshot->original_destroy.notify = clipboard_original_destroy;
  /* Observe destruction before the seat emits its empty-selection update. */
  wl_list_insert(&source->events.destroy.listener_list, &snapshot->original_destroy.link);
  server->clipboard_copy = snapshot;
  struct wl_event_loop *loop = wl_display_get_event_loop(server->wl_display);
  snapshot->timeout = wl_event_loop_add_timer(loop, clipboard_read_timeout, snapshot);
  if (!snapshot->timeout) { clipboard_cancel_copy(server); return; }
  wl_event_source_timer_update(snapshot->timeout, 5000);
  char **mime;
  wl_array_for_each(mime, &source->mime_types) {
    if (strlen(*mime) > 4096) { clipboard_cancel_copy(server); return; }
    struct clipboard_item *item = calloc(1, sizeof(*item));
    char **entry = wl_array_add(&snapshot->source.mime_types, sizeof(char *));
    if (entry) *entry = NULL;
    if (!item || !entry || !(*entry = strdup(*mime))) {
      free(item); clipboard_cancel_copy(server); return;
    }
    item->snapshot = snapshot; item->mime = *entry; item->fd = -1;
    wl_list_insert(snapshot->items.prev, &item->link);
    int fds[2];
    if (pipe(fds) != 0) { clipboard_cancel_copy(server); return; }
    fcntl(fds[0], F_SETFD, FD_CLOEXEC); fcntl(fds[1], F_SETFD, FD_CLOEXEC);
    fcntl(fds[0], F_SETFL, O_NONBLOCK);
    item->fd = fds[0];
    item->reader = wl_event_loop_add_fd(loop, item->fd, WL_EVENT_READABLE, clipboard_read_ready, item);
    if (!item->reader) { close(fds[1]); clipboard_cancel_copy(server); return; }
    snapshot->pending++;
    wlr_data_source_send(source, item->mime, fds[1]);
  }
}

static void clipboard_init(struct nextspace_server *server)
{
  wl_list_init(&server->clipboard_writes);
  server->clipboard_selection.notify = clipboard_changed;
  wl_signal_add(&server->seat->events.set_selection, &server->clipboard_selection);
}

static void clipboard_finish(struct nextspace_server *server)
{
  wl_list_remove(&server->clipboard_selection.link);
  clipboard_cancel_copy(server);
  if (server->seat->selection_source && server->seat->selection_source->impl == &clipboard_impl)
    wlr_seat_set_selection(server->seat, NULL, server->seat->selection_serial);
  struct clipboard_write *transfer, *next;
  wl_list_for_each_safe(transfer, next, &server->clipboard_writes, link)
    clipboard_write_finish(transfer);
}
