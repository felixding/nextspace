project('nextspace-compositor', 'c', version: '0.1.0',
  meson_version: '>=0.63', default_options: ['c_std=c11', 'warning_level=2'])

cc = meson.get_compiler('c')
wlroots = dependency('wlroots-0.18', version: '=0.18.2')
wayland = dependency('wayland-server', version: '>=1.23')
title_dependencies = [dependency('pangocairo'), dependency('pangofc', version: '>=1.48'), dependency('fontconfig')]
scanner = find_program('wayland-scanner')
python = find_program('python3')
test('artwork-fidelity', python, args: [files('../../Tests/Wayland/artwork_fidelity.py'),
  '--artifacts', meson.current_build_dir() / 'artwork-fidelity-results'])
capture_png_probe = executable('capture-png-probe', '../../Tests/Wayland/capture-png.c',
  include_directories: include_directories('../../Libraries/gnustep/back/Source/cairo'),
  dependencies: [dependency('cairo'), dependency('libpng')])
test('capture-png', python, args: [files('../../Tests/Wayland/capture_png.py'), '--probe',
  capture_png_probe, '--artifacts', meson.current_build_dir() / 'capture-png-results'])
frame_controls = custom_target('frame-controls',
  input: files('../../Libraries/gnustep/nextspace-theme/Resources/ThemeImages/WindowControls.svg'),
  output: 'frame-controls.h',
  command: [python, files('generate-frame-controls.py'), '@OUTPUT@', '@INPUT@'])
color_cursor = custom_target('color-cursor',
  input: files('../../Libraries/gnustep/Artwork.svg'),
  depend_files: files('../../Packaging/Sources/vector_art.py', '../../Libraries/gnustep/SliderKnobs.svg',
    '../../Libraries/gnustep/PageOrientation.svg', '../../Libraries/gnustep/TabEdges.svg',
    '../../Libraries/gnustep/StepperButtons.svg', '../../Libraries/gnustep/RulerMarkers.svg', '../../Libraries/gnustep/ProgressSpinners.svg', '../../Libraries/gnustep/ProgressStripes.svg'),
  output: 'color-cursor.h',
  command: [python, files('generate-color-cursor.py'), '@OUTPUT@', '@INPUT@'])
title_controls_probe = executable('title-controls-probe',
  ['../../Tests/Wayland/title-controls.c', frame_controls],
  include_directories: [include_directories('src'), include_directories('../../Protocols')],
  dependencies: [dependency('cairo'), cc.find_library('m')])
test('title-controls', python, args: [files('../../Tests/Wayland/title_controls.py'),
  '--probe', title_controls_probe, '--artifacts', meson.current_build_dir() / 'title-controls-results'])
xdg_shell = custom_target('xdg-shell-server-header',
  input: '../../Libraries/gnustep/back/Source/wayland/protocols/xdg-shell.xml',
  output: 'xdg-shell-protocol.h', command: [scanner, 'server-header', '@INPUT@', '@OUTPUT@'])
xdg_client_header = custom_target('xdg-shell-client-header',
  input: '../../Libraries/gnustep/back/Source/wayland/protocols/xdg-shell.xml',
  output: 'xdg-shell-client-protocol.h', command: [scanner, 'client-header', '@INPUT@', '@OUTPUT@'])
xdg_code = custom_target('xdg-shell-code',
  input: '../../Libraries/gnustep/back/Source/wayland/protocols/xdg-shell.xml',
  output: 'xdg-shell-protocol.c', command: [scanner, 'private-code', '@INPUT@', '@OUTPUT@'])
decoration_xml = '../../Libraries/gnustep/back/Source/wayland/protocols/xdg-decoration-unstable-v1.xml'
decoration_server_header = custom_target('xdg-decoration-server-header', input: decoration_xml,
  output: 'xdg-decoration-unstable-v1-server-protocol.h', command: [scanner, 'server-header', '@INPUT@', '@OUTPUT@'])
decoration_client_header = custom_target('xdg-decoration-client-header', input: decoration_xml,
  output: 'xdg-decoration-unstable-v1-client-protocol.h', command: [scanner, 'client-header', '@INPUT@', '@OUTPUT@'])
decoration_code = custom_target('xdg-decoration-code', input: decoration_xml,
  output: 'xdg-decoration-unstable-v1-protocol.c', command: [scanner, 'private-code', '@INPUT@', '@OUTPUT@'])
activation_xml = '../../Libraries/gnustep/back/Source/wayland/protocols/xdg-activation-v1.xml'
activation_header = custom_target('xdg-activation-client-header', input: activation_xml,
  output: 'xdg-activation-v1-client-protocol.h', command: [scanner, 'client-header', '@INPUT@', '@OUTPUT@'])
activation_code = custom_target('xdg-activation-code', input: activation_xml,
  output: 'xdg-activation-v1-protocol.c', command: [scanner, 'private-code', '@INPUT@', '@OUTPUT@'])
primary_xml = '../../Libraries/gnustep/back/Source/wayland/protocols/primary-selection-unstable-v1.xml'
primary_header = custom_target('primary-selection-client-header', input: primary_xml,
  output: 'primary-selection-unstable-v1-client-protocol.h', command: [scanner, 'client-header', '@INPUT@', '@OUTPUT@'])
primary_code = custom_target('primary-selection-code', input: primary_xml,
  output: 'primary-selection-unstable-v1-protocol.c', command: [scanner, 'private-code', '@INPUT@', '@OUTPUT@'])
geometry = include_directories('../../Protocols')
application_xml = '../../Libraries/gnustep/back/Source/wayland/protocols/nextspace-application-v1.xml'
application_header = custom_target('nextspace-application-server-header', input: application_xml,
  output: 'nextspace-application-v1-server-protocol.h', command: [scanner, 'server-header', '@INPUT@', '@OUTPUT@'])
application_code = custom_target('nextspace-application-code', input: application_xml,
  output: 'nextspace-application-v1-protocol.c', command: [scanner, 'private-code', '@INPUT@', '@OUTPUT@'])
application_client_header = custom_target('nextspace-application-client-header', input: application_xml,
  output: 'nextspace-application-v1-client-protocol.h', command: [scanner, 'client-header', '@INPUT@', '@OUTPUT@'])
shell_xml = '../../Protocols/nextspace-shell-v1.xml'
shell_header = custom_target('nextspace-shell-server-header', input: shell_xml,
  output: 'nextspace-shell-v1-server-protocol.h', command: [scanner, 'server-header', '@INPUT@', '@OUTPUT@'])
shell_client_header = custom_target('nextspace-shell-client-header', input: shell_xml,
  output: 'nextspace-shell-v1-client-protocol.h', command: [scanner, 'client-header', '@INPUT@', '@OUTPUT@'])
shell_code = custom_target('nextspace-shell-code', input: shell_xml,
  output: 'nextspace-shell-v1-protocol.c', command: [scanner, 'private-code', '@INPUT@', '@OUTPUT@'])
compositor = executable('nextspace-compositor', ['src/main.c', frame_controls, color_cursor, xdg_shell, decoration_server_header, application_header, application_code,
  shell_header, shell_code],
  include_directories: geometry, c_args: ['-DWLR_USE_UNSTABLE'],
  dependencies: [wlroots, wayland, dependency('xkbcommon'), dependency('threads'), dependency('libinput')] + title_dependencies + [cc.find_library('m')],
  install: true, install_rpath: get_option('wlroots_rpath'))
executable('nextspace-session', '../Session/main.c', dependencies: dependency('libsystemd'), install: true)
install_data('../../OS/Linux/usr/NextSpace/bin/nextspace-wayland-session',
  '../../OS/Linux/usr/NextSpace/bin/nextspace-wayland-greeter',
  '../../OS/Linux/usr/NextSpace/bin/nextspace-wayland-locker',
  '../../OS/Linux/usr/NextSpace/bin/nextspace-wayland-capture',
  install_dir: get_option('bindir'), install_mode: 'rwxr-xr-x')
test('geometry', executable('test-geometry', '../../Tests/Wayland/geometry.c',
  include_directories: geometry, dependencies: cc.find_library('m')))
test('gamma', executable('test-gamma', '../../Tests/Wayland/gamma.c',
  c_args: ['-DWLR_USE_UNSTABLE'], dependencies: [wlroots, cc.find_library('m')]))
executable('title-layout-probe', '../../Tests/Wayland/title-layout-probe.c', dependencies: title_dependencies[0])
executable('title-font-probe', '../../Tests/Wayland/title-font-probe.c',
  dependencies: title_dependencies)
executable('decoration-probe', ['../../Tests/Wayland/decoration-probe.c', xdg_client_header,
  xdg_code, decoration_client_header, decoration_code, application_client_header, application_code],
  dependencies: dependency('wayland-client'))
input_protocols = []
foreach name, path : {
  'text-input-unstable-v3': '../../Libraries/gnustep/back/Source/wayland/protocols/text-input-unstable-v3.xml',
  'input-method-unstable-v2': '../../Protocols/input-method-unstable-v2.xml',
  'virtual-keyboard-unstable-v1': '../../Protocols/virtual-keyboard-unstable-v1.xml',
}
  input_protocols += custom_target(name + '-client-header', input: path,
    output: name + '-client-protocol.h', command: [scanner, 'client-header', '@INPUT@', '@OUTPUT@'])
  input_protocols += custom_target(name + '-code', input: path,
    output: name + '-protocol.c', command: [scanner, 'private-code', '@INPUT@', '@OUTPUT@'])
endforeach
executable('registry-probe', ['../../Tests/Wayland/registry-probe.c', input_protocols, application_client_header, application_code,
  xdg_client_header, xdg_code, activation_header, activation_code, primary_header, primary_code],
  dependencies: dependency('wayland-client'))
lock_protocols = []
foreach name, path : {
  'ext-session-lock-v1': '../../Protocols/ext-session-lock-v1.xml',
  'fractional-scale-v1': '../../Libraries/gnustep/back/Source/wayland/protocols/fractional-scale-v1.xml',
  'viewporter': '../../Libraries/gnustep/back/Source/wayland/protocols/viewporter.xml',
}
  lock_protocols += custom_target(name + '-lock-client-header', input: path,
    output: name + '-client-protocol.h', command: [scanner, 'client-header', '@INPUT@', '@OUTPUT@'])
  lock_protocols += custom_target(name + '-lock-client-code', input: path,
    output: name + '-protocol.c', command: [scanner, 'private-code', '@INPUT@', '@OUTPUT@'])
endforeach
executable('lock-probe', ['../../Tests/Wayland/lock-probe.c', lock_protocols], dependencies: dependency('wayland-client'))
capture_xml = '../../Protocols/wlr-screencopy-unstable-v1.xml'
capture_header = custom_target('screencopy-client-header', input: capture_xml,
  output: 'wlr-screencopy-unstable-v1-client-protocol.h', command: [scanner, 'client-header', '@INPUT@', '@OUTPUT@'])
capture_code = custom_target('screencopy-client-code', input: capture_xml,
  output: 'wlr-screencopy-unstable-v1-protocol.c', command: [scanner, 'private-code', '@INPUT@', '@OUTPUT@'])
executable('capture-probe', ['../../Tests/Wayland/capture-probe.c', capture_header, capture_code],
  dependencies: dependency('wayland-client'))
executable('shell-probe', ['../../Tests/Wayland/shell-probe.c', shell_client_header, shell_code],
  dependencies: dependency('wayland-client'))
executable('logind-service-probe', '../../Tests/Wayland/logind-service-probe.c', dependencies: dependency('gio-unix-2.0'))
if get_option('comparators')
  add_languages('cpp', native: false)
  executable('gtk-probe', '../../Tests/Wayland/gtk-probe.c', dependencies: dependency('gtk4'))
  executable('qt-probe', '../../Tests/Wayland/qt-probe.cpp', dependencies: dependency('qt6', modules: ['Widgets']))
endif
if get_option('portals')
  executable('pipewire-probe', '../../Tests/Wayland/pipewire-probe.c', dependencies: dependency('libpipewire-0.3'))
endif
