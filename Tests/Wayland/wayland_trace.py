"""Read native client focus from opt-in, post-authentication Wayland diagnostics."""
import re


def native_window_focus(trace, number):
    """Inspect one rendering client's log; protocol object IDs are not global."""
    proxies, windows, focused = {}, {}, None
    for line in trace.splitlines():
        match = re.search(r'nextspace_application_v1#\d+\.get_window\(new id nextspace_window_v1#(\d+), wl_surface#(\d+)\)', line)
        if match:
            proxies[int(match[1])] = int(match[2])
        match = re.search(r'nextspace_window_v1#(\d+)\.set_metadata\((\d+),', line)
        if match and int(match[1]) in proxies:
            windows[int(match[2])] = proxies[int(match[1])]
        match = re.search(r'wl_keyboard#\d+\.enter\(\d+, wl_surface#(\d+),', line)
        if match:
            focused = int(match[1])
        match = re.search(r'wl_keyboard#\d+\.leave\(\d+, wl_surface#(\d+)\)', line)
        if match and focused == int(match[1]):
            focused = None
    surface = windows.get(number)
    return dict(window_number=number, window_surface=surface,
                keyboard_surface=focused, focused=surface is not None and surface == focused)
