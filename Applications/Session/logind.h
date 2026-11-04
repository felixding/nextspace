/* Session-owned logind lock notifications. SPDX-License-Identifier: GPL-2.0-or-later */
#include <systemd/sd-bus.h>

struct session_logind {
  sd_bus *bus;
  sd_bus_slot *lock_match;
  sd_bus_slot *sleep_match;
  sd_bus_slot *owner_match;
  char *path;
  bool lock_requested;
  bool preparing_sleep, sleep_begin_pending, sleep_resume_pending, sleep_protected, inhibit_pending;
  bool inhibit_refresh;
  int sleep_inhibitor;
  bool reconnect;
  bool owner_changed;
  bool publish_hint;
  int64_t reconnect_at;
};

static void session_logind_inhibit(struct session_logind *state);

static void session_logind_set_sleep(struct session_logind *state, bool active)
{
  state->preparing_sleep = active;
  if (active) {
    state->sleep_begin_pending = true;
    state->sleep_resume_pending = false;
    state->sleep_protected = false;
  } else state->sleep_resume_pending = true;
}

static void session_logind_disconnect(struct session_logind *state)
{
  state->lock_match = sd_bus_slot_unref(state->lock_match);
  state->sleep_match = sd_bus_slot_unref(state->sleep_match);
  state->owner_match = sd_bus_slot_unref(state->owner_match);
  state->bus = sd_bus_unref(state->bus);
  state->inhibit_pending = false; state->inhibit_refresh = true;
  free(state->path); state->path = NULL;
}

static void session_logind_finish(struct session_logind *state)
{
  session_logind_disconnect(state);
  if (state->sleep_inhibitor >= 0) close(state->sleep_inhibitor);
  state->sleep_inhibitor = -1;
}

static int session_logind_owner(sd_bus_message *message, void *data, sd_bus_error *error)
{
  struct session_logind *state = data;
  const char *name, *old_owner, *new_owner;
  if (sd_bus_message_read(message, "sss", &name, &old_owner, &new_owner) > 0)
    state->owner_changed = true;
  return 0;
}

static int session_logind_sleep(sd_bus_message *message, void *data, sd_bus_error *error)
{
  struct session_logind *state = data;
  int active;
  if (sd_bus_message_read(message, "b", &active) <= 0) return 0;
  session_logind_set_sleep(state, active);
  return 0;
}

static int session_logind_lock(sd_bus_message *message, void *data, sd_bus_error *error)
{
  struct session_logind *state = data;
  state->lock_requested = true;
  return 0;
}

static bool session_logind_init(struct session_logind *state)
{
  sd_bus_message *reply = NULL;
  const char *path = NULL;
  int status = sd_bus_open_system(&state->bus);
  if (status >= 0) status = sd_bus_set_method_call_timeout(state->bus, 1000000);
  /* The daemon resolves this process's PAM/logind session. An inherited
     XDG_SESSION_ID must never select another session's lock notifications. */
  if (status >= 0) status = sd_bus_call_method(state->bus, "org.freedesktop.login1",
    "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "GetSessionByPID",
    NULL, &reply, "u", (uint32_t)getpid());
  if (status >= 0) status = sd_bus_message_read(reply, "o", &path);
  if (status > 0 && !(state->path = strdup(path))) status = -ENOMEM;
  sd_bus_message_unref(reply);
  if (status > 0) status = sd_bus_match_signal(state->bus, &state->lock_match,
    "org.freedesktop.login1", state->path, "org.freedesktop.login1.Session", "Lock",
    session_logind_lock, state);
  if (status >= 0 && state->path) status = sd_bus_match_signal(state->bus, &state->sleep_match,
    "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "PrepareForSleep",
    session_logind_sleep, state);
  if (status >= 0 && state->path) status = sd_bus_add_match(state->bus, &state->owner_match,
    "type='signal',sender='org.freedesktop.DBus',path='/org/freedesktop/DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.freedesktop.login1'",
    session_logind_owner, state);
  int preparing = 0;
  if (status >= 0 && state->path) status = sd_bus_get_property_trivial(state->bus, "org.freedesktop.login1",
    "/org/freedesktop/login1", "org.freedesktop.login1.Manager", "PreparingForSleep", NULL, 'b', &preparing);
  if (status < 0 || !state->path) { session_logind_disconnect(state); return false; }
  if (preparing || state->preparing_sleep) session_logind_set_sleep(state, preparing);
  state->reconnect = false;
  state->publish_hint = true;
  session_logind_inhibit(state);
  return true;
}

static int session_logind_inhibit_reply(sd_bus_message *message, void *data, sd_bus_error *error)
{
  struct session_logind *state = data;
  state->inhibit_pending = false;
  int fd;
  if (sd_bus_message_get_error(message) || sd_bus_message_read(message, "h", &fd) <= 0) {
    fprintf(stderr, "[session] Cannot obtain the logind sleep delay inhibitor.\n"); return 0;
  }
  /* The received descriptor belongs to the reply. Retain a private CLOEXEC
     duplicate only while suspend still needs confirmed blank frames. */
  if (state->preparing_sleep && state->sleep_protected) return 0;
  int retained = fcntl(fd, F_DUPFD_CLOEXEC, 3);
  if (retained < 0) { fprintf(stderr, "[session] Cannot retain the sleep inhibitor.\n"); return 0; }
  if (state->sleep_inhibitor >= 0) close(state->sleep_inhibitor);
  state->sleep_inhibitor = retained; state->inhibit_refresh = false;
  return 0;
}

static void session_logind_inhibit(struct session_logind *state)
{
  if (!state->bus || (state->sleep_inhibitor >= 0 && !state->inhibit_refresh) || state->inhibit_pending) return;
  state->inhibit_pending = true;
  if (sd_bus_call_method_async(state->bus, NULL, "org.freedesktop.login1", "/org/freedesktop/login1",
      "org.freedesktop.login1.Manager", "Inhibit", session_logind_inhibit_reply, state,
      "ssss", "sleep", "NEXTSPACE", "Protect the desktop before suspend", "delay") < 0) {
    state->inhibit_pending = false;
    fprintf(stderr, "[session] Cannot request the logind sleep delay inhibitor.\n");
  }
}

static void session_logind_sleep_protected(struct session_logind *state)
{
  if (!state->preparing_sleep) return;
  state->sleep_protected = true;
  if (state->sleep_inhibitor >= 0) close(state->sleep_inhibitor);
  state->sleep_inhibitor = -1;
}

static int session_logind_hint_reply(sd_bus_message *message, void *data, sd_bus_error *error)
{
  const sd_bus_error *failure = sd_bus_message_get_error(message);
  if (failure) fprintf(stderr, "[session] Cannot publish logind lock hint: %s\n", failure->message ?: failure->name);
  return 0;
}

static void session_logind_hint(struct session_logind *state, bool locked)
{
  if (!state->bus) return;
  if (sd_bus_call_method_async(state->bus, NULL, "org.freedesktop.login1", state->path,
      "org.freedesktop.login1.Session", "SetLockedHint", session_logind_hint_reply, NULL, "b", locked) < 0)
    fprintf(stderr, "[session] Cannot queue logind lock hint.\n");
}

static void session_logind_process(struct session_logind *state)
{
  if (!state->bus) {
    if (state->reconnect && milliseconds() >= state->reconnect_at) {
      state->reconnect_at = milliseconds() + 2000;
      session_logind_init(state);
    }
    if (!state->bus) return;
  }
  int status;
  while ((status = sd_bus_process(state->bus, NULL)) > 0) {}
  if (status < 0 || state->owner_changed) {
    state->owner_changed = false;
    fprintf(stderr, "[session] Logind connection lost; retrying while the desktop lock is preserved.\n");
    session_logind_disconnect(state);
    /* Losing the monitor must not leave an unlocked desktop across an
       unobserved suspend. Retain the delay FD until protected-frame ack. */
    session_logind_set_sleep(state, true);
    state->reconnect = true; state->reconnect_at = milliseconds() + 1000;
  }
}

static struct pollfd session_logind_poll(struct session_logind *state, int *timeout)
{
  struct pollfd result = {.fd = -1};
  if (!state->bus) {
    if (state->reconnect) {
      int64_t delay = state->reconnect_at - milliseconds();
      int bounded = delay <= 0 ? 0 : delay > INT_MAX ? INT_MAX : (int)delay;
      if (*timeout < 0 || bounded < *timeout) *timeout = bounded;
    }
    return result;
  }
  result.fd = sd_bus_get_fd(state->bus);
  int events = sd_bus_get_events(state->bus);
  if (result.fd < 0 || events < 0) {
    session_logind_disconnect(state); result.fd = -1;
    session_logind_set_sleep(state, true);
    state->reconnect = true; state->reconnect_at = milliseconds() + 1000;
    return result;
  }
  result.events = events;
  uint64_t deadline;
  if (sd_bus_get_timeout(state->bus, &deadline) >= 0 && deadline != UINT64_MAX) {
    uint64_t now = (uint64_t)milliseconds() * 1000;
    uint64_t delay = deadline > now ? (deadline - now + 999) / 1000 : 0;
    int bounded = delay > INT_MAX ? INT_MAX : (int)delay;
    if (*timeout < 0 || bounded < *timeout) *timeout = bounded;
  }
  return result;
}
