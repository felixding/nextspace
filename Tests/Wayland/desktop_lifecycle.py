#!/usr/bin/env python3
"""Qualify complete desktop packages in a clean disposable Debian consumer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

from integration import run as native, until
from package_snapshot import snapshot
from workspace import run as workspace
from greeter_profile import run as greeter
from process_failure import run as process_failure

NAMES = ('nextspace-runtime', 'nextspace-session-wayland', 'nextspace-wayland-compositor')
PREFIX = Path('/usr/NextSpace')


def cohort(receipt):
    desktop = json.loads(receipt.read_text())
    compositor = json.loads((receipt.parent / Path(desktop['compositor_receipt']).name).read_text())
    packages = {item['package']: item for item in [*desktop['packages'], compositor]}
    assert set(packages) == set(NAMES), packages.keys()
    for name, item in packages.items():
        binary = receipt.parent / Path(item['binary']).name
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == item['binary_sha256'], binary
        assert subprocess.check_output(['dpkg-deb', '-f', str(binary), 'Package'], text=True).strip() == name
        assert subprocess.check_output(['dpkg-deb', '-f', str(binary), 'Version'], text=True).strip() == desktop['version']
        item['binary'] = str(binary)
    return desktop['version'], packages


def payload(packages, names, changed=()):
    report = {}
    for name in names:
        item = packages[name]
        for relative, expected in item['payload_hashes'].items():
            if relative in changed:
                continue
            path = Path('/') / relative
            assert path.is_file() and not path.is_symlink(), path
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual == expected, path
            report[relative] = actual
        for relative, target in item.get('payload_links', {}).items():
            path = Path('/') / relative
            assert path.is_symlink() and os.readlink(path) == target, path
            report[relative] = 'link:' + target
    return report


def capture_libraries(artifacts):
    """Retain external ELF bytes; private ELF versions remain in the two debs."""
    paths = set()
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'libraries' and isinstance(item, list):
                    paths.update(path for path in item if isinstance(path, str) and path.startswith('/'))
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
    for path in artifacts.rglob('*.json'):
        # Pinned artwork provenance contains historical library paths. Only
        # libraries observed by this consumer belong in its runtime capsule.
        if path.is_relative_to(artifacts / 'validation-sources'):
            continue
        collect(json.loads(path.read_text()))
    directory = artifacts / 'runtime-libraries'; directory.mkdir()
    report = {}
    for value in sorted(paths):
        path = Path(value)
        if path.is_relative_to('/Library') or path.is_relative_to(PREFIX):
            continue
        data = path.read_bytes()
        assert data[:4] == b'\x7fELF', path
        checksum = hashlib.sha256(data).hexdigest()
        target = directory / checksum
        if not target.exists(): shutil.copyfile(path, target)
        report[value] = dict(sha256=checksum, resolved=str(path.resolve()))
    (artifacts / 'runtime-libraries.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def run(first, second, probes, artifacts):
    if not Path('/.dockerenv').is_file() or os.geteuid() != 0 or os.environ.get('NEXTSPACE_PACKAGE_TEST_DISPOSABLE') != '1':
        raise RuntimeError('Use a clean disposable root container with NEXTSPACE_PACKAGE_TEST_DISPOSABLE=1')
    if PREFIX.exists():
        raise RuntimeError('The consumer must start without an installed NEXTSPACE prefix')
    artifacts.mkdir(parents=True)
    process_failure(artifacts / 'process-failure')
    validation = {}
    source = Path(__file__).parent
    for path in sorted(source.rglob('*')):
        if path.is_file() and not {'__pycache__', 'obj'}.intersection(path.relative_to(source).parts):
            relative = path.relative_to(source)
            target = artifacts / 'validation-sources/Tests/Wayland' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            validation[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
    (artifacts / 'validation-sources.json').write_text(json.dumps(validation, indent=2) + '\n')
    version, packages = cohort(first)
    upgraded_version, upgraded = cohort(second)
    subprocess.run(['dpkg', '--compare-versions', version, 'lt', upgraded_version], check=True)
    for key in ('LD_LIBRARY_PATH', 'GNUSTEP_CONFIG_FILE', 'GNUSTEP_MAKEFILES', 'DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'NEXTSPACE_SESSION_ID'):
        os.environ.pop(key, None)
    os.environ['PATH'] = '/usr/NextSpace/bin:/Library/bin:/usr/NextSpace/sbin:/Library/sbin:' + os.environ['PATH']
    desktop_paths = [Path('/etc/greetd/config.toml'), Path('/etc/systemd/system/display-manager.service')]
    original = snapshot(desktop_paths)
    (artifacts / 'display-manager-before.json').write_text(json.dumps(original, indent=2) + '\n')

    def install(values, names, label):
        with (artifacts / (label + '.log')).open('w') as log:
            subprocess.run(['apt-get', '-y', '--no-install-recommends', '-o', 'Dpkg::Options::=--force-confold',
                '-o', 'Dpkg::Options::=--path-include=*',
                'install', *[values[name]['binary'] for name in names]],
                env=dict(os.environ, DEBIAN_FRONTEND='noninteractive'), stdout=log, stderr=log, check=True)
        assert snapshot(desktop_paths) == original, 'Changed display-manager configuration'

    def remove(names, label):
        with (artifacts / (label + '.log')).open('w') as log:
            subprocess.run(['dpkg', '--remove', *names], stdout=log, stderr=log, check=True)
        assert snapshot(desktop_paths) == original

    def installed_payload(values, names, label, changed=()):
        report = payload(values, names, changed)
        (artifacts / (label + '-payload.json')).write_text(json.dumps(report, indent=2) + '\n')

    compositor = str(PREFIX / 'bin/nextspace-compositor')
    def applications(label, during_upgrade=None, full=True):
        programs = dict(terminal='/Applications/Terminal.app/Terminal', textedit='/Applications/TextEdit.app/TextEdit',
            review='/Applications/Review.app/Review', review_probe=str(probes / 'WorkspaceProbe'),
            timemon='/Applications/TimeMon.app/TimeMon', pasteboard=str(probes / 'PasteboardProbe')) if full else None
        native(compositor, str(probes / 'WaylandProbe'), artifacts / label,
            registry_probe=str(probes / 'registry-probe'), pasteboard_probe=str(probes / 'PasteboardProbe'),
            pasteboard_server='/Library/bin/gpbs-wayland', applications=programs, server_frames=True,
            during_upgrade=during_upgrade)

    def shell(label):
        workspace(compositor, str(PREFIX / 'Apps/Workspace.app/Workspace'), str(probes / 'WorkspaceProbe'),
            artifacts / label, gui_probe=str(probes / 'WaylandProbe'), display_probe=str(probes / 'DisplayModelProbe'),
            alert_probe=str(probes / 'AlertProbe'), preferences='/Applications/Preferences.app/Preferences',
            openup='/Applications/OpenUp.app/OpenUp')

    def login(label):
        greeter(PREFIX / 'bin/nextspace-compositor', PREFIX / 'bin/nextspace-session',
            PREFIX / 'bin/nextspace-display-profile', PREFIX / 'Apps/Login.app/Login', artifacts / label)

    def toolkit_models(label):
        for name, record in (('GammaModelProbe', 'gamma-model'), ('OutputResultProbe', 'output-results')):
            with (artifacts / (label + '-' + record + '.log')).open('w') as log:
                subprocess.run([str(probes / name)], stdout=log, stderr=log, check=True)
        with (artifacts / (label + '-run-loop-timers.log')).open('w') as log:
            subprocess.run([str(probes / 'RunLoopTimerProbe'),'--bounded'],stdout=log,stderr=log,check=True)

    def name_server_lock(label):
        from name_server_lock import run
        run(str(probes / 'NameServerLockProbe'), artifacts / (label + '-name-server-lock'))
        from pasteboard import stop_during_defaults_write
        stop_during_defaults_write('/Library/bin/gpbs-wayland', probes / 'defaults-lock-delay.so',
            artifacts / (label + '-pasteboard-stop'))

    def file_conflicts(label):
        from file_operation_conflicts import run
        result = run(PREFIX / 'Apps/Workspace.app/Resources/FileMover.tool',
            artifacts / (label + '-file-operation-conflicts'))
        assert result['passed'], result

    def event_delivery(label):
        from event_queue import run
        run(Path(compositor), probes / 'EventQueueProbe', artifacts / (label + '-event-queue'))

    def drag_start(label):
        from drag_start import run
        run(Path(compositor), probes / 'DragProbe', Path('/Library/bin/gpbs-wayland'),
            probes / 'PasteboardProbe', artifacts / (label + '-drag-start'))

    def buffer_lifetime(label):
        from buffer_stress import run
        run(Path(compositor), probes / 'WaylandProbe', Path('/Library/bin/gpbs-wayland'),
            probes / 'PasteboardProbe', artifacts / (label + '-buffer-stress'))

    def reconstructed_cursors(label):
        from cursor_artwork import run
        run(Path(compositor), probes / 'WaylandProbe', Path('/usr/share/icons/NextSpace'),
            artifacts / (label + '-cursor-artwork'),
            images=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages'),
            pasteboard_server=Path('/Library/bin/gpbs-wayland'))

    def printing(label):
        from printing import run
        from printing_textedit import run as textedit_printing
        root = artifacts / (label + '-printing')
        root.mkdir()
        storage = dict(pasteboard_server=Path('/Library/bin/gpbs-wayland'),
            pasteboard_probe=probes / 'PasteboardProbe')
        for profile in ('portrait', 'crop', 'landscape'):
            for unflipped in (False, True):
                name = profile + ('-unflipped' if unflipped else '-flipped')
                flat = root / name
                run(Path(compositor), probes / 'PrintingProbe', flat,
                    unflipped=unflipped, profile=profile, **storage)
                run(Path(compositor), probes / 'PrintingProbe', root / (name + '-nested'),
                    unflipped=unflipped, profile=profile, nested=True, reference_directory=flat, **storage)
        textedit_printing(Path(compositor), Path('/Applications/TextEdit.app/TextEdit'),
            probes / 'WorkspaceProbe', root / 'textedit', **storage)
        from textedit_panels import run as textedit_panels
        textedit_panels(Path(compositor), Path('/Applications/TextEdit.app/TextEdit'),
            probes / 'WorkspaceProbe', root / 'textedit-panels', **storage)
        from page_layout import run as page_layout
        page_layout(Path(compositor), probes / 'PrintingProbe',
            artifacts=root / 'page-layout', **storage)
        from tab_views import run as tab_views
        tab_views(Path(compositor), probes / 'ArtworkProbe',
            artifacts=root / 'tab-views', **storage)
        from stepper_views import run as stepper_views
        stepper_views(Path(compositor), probes / 'ArtworkProbe',
            artifacts=root / 'stepper-views', **storage)

    def portal(label):
        from portal import run
        run(compositor, str(probes / 'registry-probe'), str(probes / 'pipewire-probe'),
            str(PREFIX / 'bin/nextspace-screencast-chooser'), str(probes / 'decoration-probe'),
            artifacts / (label + '-portal'),
            backend=str(PREFIX / 'libexec/nextspace-wayland/portal/xdg-desktop-portal-wlr'),
            native_chooser=True, supervisor=str(PREFIX / 'bin/nextspace-session'),
            workspace_probe=str(probes / 'ShellConnectionProbe'), lock_probe=str(probes / 'lock-probe'),
            portal_configuration='/usr/share/xdg-desktop-portal/nextspace-portals.conf',
            capture_launcher=str(PREFIX / 'bin/nextspace-wayland-capture'))

    def locked_shutdown(label):
        from locked_shutdown import run
        run(compositor, str(probes / 'lock-probe'), str(probes / 'decoration-probe'),
            artifacts / (label + '-locked-shutdown'))

    def user_hooks(label):
        from session_hooks import run
        run(PREFIX / 'bin/nextspace-session', Path(compositor), PREFIX / 'bin/nextspace-session-hook',
            probes / 'ShellConnectionProbe', artifacts / (label + '-session-hooks'))

    def cursors(label):
        from cursors import run
        run(compositor, str(probes / 'WaylandProbe'), artifacts / (label + '-cursors'))

    def image_formats(label):
        from application_artwork import run as application_artwork
        from pattern_fill import run as pattern_fill
        pattern_fill(Path(compositor), probes / 'ArtworkProbe', Path('/Library/bin/gpbs-wayland'),
            probes / 'PasteboardProbe', artifacts / (label + '-pattern-fill'))
        from progress_views import run as progress_views
        progress_views(Path(compositor), probes / 'ArtworkProbe', Path('/Library/bin/gpbs-wayland'),
            probes / 'PasteboardProbe', artifacts / (label + '-progress-views'))
        progress_views(Path(compositor), probes / 'ArtworkProbe', Path('/Library/bin/gpbs-wayland'),
            probes / 'PasteboardProbe', artifacts / (label + '-spinner-views'), spinner=True)
        from slider_knob_fidelity import run as slider_knob_fidelity, SIZES as slider_knobs
        from tab_artwork import run as tab_artwork, SIZES as tabs
        from page_orientation import run as page_orientation, SIZES as pages
        from stepper_artwork import run as stepper_artwork, SIZES as steppers
        from ruler_artwork import run as ruler_artwork, SIZES as ruler_markers
        from progress_artwork import run as progress_artwork, SIZES as progress_stripes
        from spinner_artwork import run as spinner_artwork, SIZES as progress_spinners
        for category, check, sizes in (('slider-knob', slider_knob_fidelity, slider_knobs),
                ('tab', tab_artwork, tabs), ('page-orientation', page_orientation, pages),
                ('stepper', stepper_artwork, steppers), ('ruler', ruler_artwork, ruler_markers),
                ('progress-stripes', progress_artwork, progress_stripes),
                ('progress-spinners', spinner_artwork, progress_spinners)):
            check(artifacts / (label + '-' + category + '-fidelity'), images=Path('/Library/Images'))
            for name, logical in sizes.items():
                resource = Path('/Library/Images') / (name + '.tiff')
                application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe', resource,
                    artifacts / (label + '-' + category + '-' + name), theme='/Library/Themes/NextSpace.theme',
                    named_image=name, logical=logical, canvas=True)
        from return_fidelity import run as return_fidelity
        from checkmark_artwork import run as checkmark_artwork
        checkmark_resource=PREFIX / 'Apps/Workspace.app/Resources/CheckMark.tiff'
        checkmark_artwork(artifacts / (label+'-checkmark-fidelity'), images=checkmark_resource.parent)
        application_artwork(Path(compositor),probes / 'ArtworkProbe',probes / 'WaylandProbe',checkmark_resource,
            artifacts / (label+'-checkmark-artwork'),theme='/Library/Themes/NextSpace.theme',logical=(10,10),canvas=True)
        return_resource=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_ret.tiff')
        return_fidelity(artifacts / (label+'-return-fidelity'),image=return_resource)
        application_artwork(Path(compositor),probes / 'ArtworkProbe',probes / 'WaylandProbe',return_resource,
            artifacts / (label+'-return-artwork'),theme='/Library/Themes/NextSpace.theme',
            named_image='common_ret',logical=(15,10),canvas=True)
        from debian_fidelity import run as debian_fidelity
        debian_resource=PREFIX / 'Apps/Workspace.app/Resources/app-debian-48.tiff'
        debian_fidelity(artifacts / (label+'-debian-fidelity'),image=debian_resource)
        application_artwork(Path(compositor),probes / 'ArtworkProbe',probes / 'WaylandProbe',debian_resource,
            artifacts / (label+'-debian-artwork'),theme='/Library/Themes/NextSpace.theme',logical=(52,64),canvas=True)
        from navigation_fidelity import run as navigation_fidelity
        navigation_fidelity(artifacts / (label+'-navigation-fidelity'),images={
            'PathArrow':PREFIX / 'Apps/Workspace.app/Resources/RightArrow.tiff',
            'BrowserArrow':Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_3DArrowRight.tiff'),
            'BrowserArrowHighlighted':Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_3DArrowRightH.tiff')})
        for name,resource,lookup in [('path',PREFIX / 'Apps/Workspace.app/Resources/RightArrow.tiff',None),
                ('browser',Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_3DArrowRight.tiff'),'GSMenuArrow'),
                ('browser-highlighted',Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_3DArrowRightH.tiff'),'NSHighlightedMenuArrow')]:
            application_artwork(Path(compositor),probes / 'ArtworkProbe',probes / 'WaylandProbe',resource,
                artifacts / (label+'-navigation-'+name),theme='/Library/Themes/NextSpace.theme',
                named_image=lookup,logical=(7,7),canvas=True)
        with (artifacts / (label + '-clock-notifications.log')).open('w') as log:
            subprocess.run([str(probes / 'ClockNotificationProbe')], stdout=log, stderr=log, check=True)
        from image_formats import run
        run(str(probes / 'WaylandProbe'), artifacts / (label + '-image-formats'))
        from artwork_reference import run as artwork_reference
        artwork_reference(probes / 'WaylandProbe', artifacts / (label + '-original-artwork'), preferences=True, login=True, sound_controls=True, folders=True, textedit=True, review=True, openup=True, timemon=True, color_panel=True)
        from date_fidelity import run as date_fidelity
        date_fidelity(artifacts / (label + '-date-fidelity'),
            image=Path('/Applications/Preferences.app/Resources/Date.preferences/Resources/Date.tiff'))
        from screen_fidelity import run as screen_fidelity
        screen_fidelity(artifacts / (label + '-screen-fidelity'),
            image=Path('/Applications/Preferences.app/Resources/Screen.preferences/Resources/Screen.tiff'))
        from keyboard_fidelity import run as keyboard_fidelity
        keyboard_fidelity(artifacts / (label + '-keyboard-fidelity'),
            image=Path('/Applications/Preferences.app/Resources/Keyboard.preferences/Resources/Keyboard.tiff'))
        from mouse_fidelity import run as mouse_fidelity
        mouse_fidelity(artifacts / (label + '-mouse-fidelity'),
            image=Path('/Applications/Preferences.app/Resources/Mouse.preferences/Resources/Mouse.tiff'))
        from sound_fidelity import run as sound_fidelity
        sound_fidelity(artifacts / (label + '-sound-fidelity'),
            image=Path('/Applications/Preferences.app/Resources/Sound.preferences/Resources/Sound.tiff'))
        from services_fidelity import run as services_fidelity
        services_fidelity(artifacts / (label + '-services-fidelity'),
            image=Path('/Applications/Preferences.app/Resources/Services.preferences/Resources/Services.tiff'))
        from localization_fidelity import run as localization_fidelity
        localization_fidelity(artifacts / (label + '-localization-fidelity'),
            image=Path('/Applications/Preferences.app/Resources/Localization.preferences/Resources/Localization.tiff'))
        from expert_fidelity import run as expert_fidelity
        expert_fidelity(artifacts / (label + '-expert-fidelity'),
            image=Path('/Applications/Preferences.app/Resources/Expert.preferences/Resources/Expert.tiff'))
        from sound_controls_fidelity import run as sound_controls_fidelity
        sound_controls_fidelity(artifacts / (label + '-sound-controls-fidelity'),
            images=Path('/Applications/Preferences.app/Resources/Sound.preferences/Resources'))
        from folder_fidelity import run as folder_fidelity
        folder_fidelity(artifacts / (label + '-folder-fidelity'))
        from theme_images import run as theme_images
        theme_images(str(probes / 'WaylandProbe'), Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages'),
            artifacts / (label + '-theme-images'))
        from login_fidelity import run as login_fidelity
        login_fidelity(artifacts / (label + '-login-fidelity'),
            images=PREFIX / 'Apps/Login.app/Resources/Login.gorm')
        from login_fields import run as login_fields
        login_fields(Path(compositor), PREFIX / 'Apps/Login.app/Login',
            (PREFIX / 'Frameworks/SystemKit.framework/Versions/0.3/libSystemKit.so.0.3').resolve(),
            probes / 'WorkspaceProbe', probes / 'WaylandProbe', artifacts / (label + '-login-fields'))
        from login_artwork import run as login_artwork
        login_artwork(probes / 'WaylandProbe', PREFIX / 'Apps/Login.app/Resources/Login.gorm',
            artifacts / (label + '-login-artwork'))
        textedit = Path('/Applications/TextEdit.app')
        from textedit_fidelity import run as textedit_fidelity
        textedit_fidelity(artifacts / (label + '-textedit-fidelity'), image=textedit / 'Resources/Edit.tiff')
        from textedit_title_fidelity import run as textedit_title_fidelity
        textedit_title_fidelity(artifacts / (label + '-textedit-title-fidelity'), image=textedit / 'Resources/EditTitle.tiff')
        from textedit_document_fidelity import run as textedit_document_fidelity
        textedit_document_fidelity(artifacts / (label + '-textedit-document-fidelity'), images=textedit / 'Resources')
        application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe',
            textedit / 'Resources/Edit.tiff', artifacts / (label + '-application-artwork'),
            textedit / 'TextEdit', probes / 'WorkspaceProbe',
            Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff'))
        application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe',
            Path('/Applications/Terminal.app/Resources/Terminal.tiff'),
            artifacts / (label + '-terminal-artwork'),
            tile=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff'),
            scroller_images=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages'),
            control_images=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages'))
        application_artwork(Path(compositor), probes / 'TerminalArtworkProbe', probes / 'WaylandProbe',
            Path('/Applications/Terminal.app/Resources/Terminal.tiff'),
            artifacts / (label + '-terminal-icon-view'))
        for strip in ('ScrollingMach', 'ScrollingOutput'):
            application_artwork(Path(compositor), probes / 'TerminalArtworkProbe', probes / 'WaylandProbe',
                Path('/Applications/Terminal.app/Resources/Terminal.tiff'),
                artifacts / (label + '-terminal-' + strip),
                strip=Path('/Applications/Terminal.app/Resources') / (strip + '.tiff'))
        from application_artwork import resources
        repository = Path(__file__).resolve().parents[2]
        resources(probes / 'WaylandProbe', repository / 'Applications/TextEdit', textedit / 'Resources',
            artifacts / (label + '-textedit-document-resources'), ('text.tiff', 'rtf.tiff', 'rtfd.tiff'))
        for name in ('text', 'rtf', 'rtfd'):
            application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe',
                textedit / 'Resources' / (name + '.tiff'), artifacts / (label + '-textedit-document-' + name),
                tile=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff'))
        preferences = Path('/Applications/Preferences.app')
        from clock_tile_fidelity import run as clock_tile_fidelity
        clock_tile_fidelity(artifacts / (label + '-clock-tile-fidelity'),
            image=preferences / 'Resources/English.lproj/ClockViewTile.tiff')
        from clock_atlas_fidelity import run as clock_atlas_fidelity
        clock_atlas_fidelity(artifacts / (label + '-clock-atlas-fidelity'),
            images=PREFIX / 'Frameworks/DesktopKit.framework/Versions/0.6/Resources')
        resources(probes / 'WaylandProbe', repository / 'Applications/Preferences/English.lproj',
            preferences / 'Resources/English.lproj', artifacts / (label + '-preferences-resources'),
            ('Preferences.tiff', 'ClockViewTile.tiff'))
        application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe',
            preferences / 'Resources/English.lproj/Preferences.tiff', artifacts / (label + '-preferences-artwork'),
            application=preferences / 'Preferences', workspace_probe=probes / 'WorkspaceProbe',
            tile=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff'),
            clock_atlas=PREFIX / 'Frameworks/DesktopKit.framework/Versions/0.6/Resources/English.lproj/clockbits.tiff',
            clock_language='English')
        from preferences_artwork import run as preferences_artwork
        preferences_artwork(Path(compositor), preferences / 'Preferences', probes / 'WorkspaceProbe',
            probes / 'WaylandProbe', artifacts / (label + '-preferences-modules-artwork'))
        from sound_artwork import run as sound_artwork
        sound_artwork(Path(compositor), preferences / 'Preferences', probes / 'WorkspaceProbe',
            probes / 'WaylandProbe', artifacts / (label + '-sound-mixer-artwork'))
        from folder_artwork import run as folder_artwork
        folder_options = dict(root_artwork=True)
        artist_sources = repository / 'Applications/Artwork/NeXTSpirit'
        if artist_sources.is_dir():
            from nextspirit import run as nextspirit_sources
            from nextspirit_art import NextSpiritArtwork, NextSpiritFolders
            nextspirit_sources(artist_sources, artifacts / (label + '-nextspirit-sources'))
            folder_options.update(artwork=NextSpiritFolders(repository / 'Applications/Artwork/Folder.svg',artist_sources),
                workspace_artwork=NextSpiritArtwork(artist_sources,'workspace_icons'),drag_probe=probes / 'DragProbe')
        folder_artwork(Path(compositor), PREFIX / 'Apps/Workspace.app/Workspace',
            probes / 'WorkspaceProbe', probes / 'WaylandProbe',
            PREFIX / 'Frameworks/DesktopKit.framework/Resources/Images',
            Path('/Library/Themes/NextSpace.theme'), Path('/Library/bin/gpbs-wayland'),
            probes / 'PasteboardProbe', artifacts / (label + '-workspace-folder-artwork'), **folder_options)
        from filepanel_artwork import run as filepanel_artwork
        filepanel_artwork(Path(compositor), Path('/Applications/Review.app/Review'),
            probes / 'WorkspaceProbe', probes / 'WaylandProbe', probes / 'image-usage-trace.so',
            PREFIX / 'Frameworks/DesktopKit.framework/Resources/Images',
            Path('/Library/Themes/NextSpace.theme'), Path('/Library/bin/gpbs-wayland'),
            probes / 'PasteboardProbe', artifacts / (label + '-filepanel-artwork'))
        from help_artwork import run as help_artwork
        help_artwork(Path(compositor), probes / 'HelpAttachmentProbe', probes / 'image-usage-trace.so',
            probes / 'WaylandProbe', Path('/Library/Themes/NextSpace.theme'),
            Path('/Library/bin/gpbs-wayland'), probes / 'PasteboardProbe', artifacts / (label + '-help-artwork'))
        from track_pattern import run as track_pattern
        track_pattern(Path(compositor),probes / 'TrackPatternProbe',Path('/Library/Themes/NextSpace.theme'),
            Path('/Library/bin/gpbs-wayland'),probes / 'PasteboardProbe',artifacts / (label + '-track-pattern'))
        for name,resource in [('NXUnknown',PREFIX / 'Images/NXUnknown.tiff'),
                ('common_Unknown',Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Unknown.tiff')),
                ('common_MultipleSelection',Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_MultipleSelection.tiff'))]:
            application_artwork(Path(compositor),probes / 'ArtworkProbe',probes / 'WaylandProbe',
                resource,artifacts / (label + '-named-image-' + name),
                theme='/Library/Themes/NextSpace.theme',named_image=name)
        from terminal_animation import run as terminal_animation
        terminal_animation(Path(compositor), Path('/Applications/Terminal.app/Terminal'),
            probes / 'WorkspaceProbe', probes / 'WaylandProbe', Path('/Library/bin/gpbs-wayland'),
            probes / 'PasteboardProbe', artifacts / (label + '-terminal-animation'),
            theme=Path('/Library/Themes/NextSpace.theme'))
        for language in ('French','German','Italian','Spanish','Dutch','Hungarian','Slovak','Russian','Ukrainian'):
            application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe',
                preferences / 'Resources/English.lproj/Preferences.tiff',
                artifacts / (label + '-clock-' + language),
                application=preferences / 'Preferences', workspace_probe=probes / 'WorkspaceProbe',
                tile=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff'),
                clock_atlas=PREFIX / ('Frameworks/DesktopKit.framework/Versions/0.6/Resources/' + language + '.lproj/clockbits.tiff'),
                clock_language=language)
        from review_photo_fidelity import run as review_photo_fidelity
        review_photo_fidelity(artifacts / (label + '-review-photo-fidelity'))
        from review_document_fidelity import NAMES as review_documents, run as review_document_fidelity
        review = Path('/Applications/Review.app/Resources')
        review_document_fidelity(artifacts / (label + '-review-document-fidelity'), images=review)
        for name in review_documents:
            application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe',
                review / (name + '.tiff'), artifacts / (label + '-review-document-' + name),
                tile=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff'))
        from review_page_fidelity import run as review_page_fidelity
        from review_page_artwork import run as review_page_artwork
        review_page_fidelity(artifacts / (label + '-review-page-fidelity'), images=review)
        review_page_artwork(Path(compositor), review.parent / 'Review', probes / 'WorkspaceProbe',
            probes / 'WaylandProbe', artifacts / (label + '-review-page-artwork'))
        from openup_fidelity import run as openup_fidelity
        openup = Path('/Applications/OpenUp.app/Resources')
        openup_fidelity(artifacts / (label + '-openup-fidelity'), images=openup)
        from openup_logo_fidelity import run as openup_logo_fidelity
        openup_logo_fidelity(artifacts / (label + '-openup-logo-fidelity'), image=openup / 'narrow.tiff')
        from timemon_pause_fidelity import run as timemon_pause_fidelity
        from timemon_pause import run as timemon_pause
        from timemon_static_fidelity import run as timemon_static_fidelity
        from timemon_static_artwork import run as timemon_static_artwork
        from timemon_workflow import run as timemon_workflow
        timemon = Path('/Applications/TimeMon.app')
        timemon_static_fidelity(artifacts / (label + '-timemon-static-fidelity'), images=timemon / 'Resources/TimeMon.gorm')
        application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe',
            timemon / 'Resources/TM-app.tiff', artifacts / (label + '-timemon-static-icon'),
            tile=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff'))
        timemon_static_artwork(compositor, timemon / 'TimeMon', probes / 'WorkspaceProbe', probes / 'WaylandProbe',
                               timemon / 'Resources', artifacts / (label + '-timemon-info'))
        timemon_pause_fidelity(artifacts / (label + '-timemon-pause-fidelity'), image=timemon / 'Resources/TimeMonP.tiff')
        timemon_pause(compositor, timemon / 'TimeMon', probes / 'WorkspaceProbe', timemon / 'Resources',
                      artifacts / (label + '-timemon-pause'))
        timemon_workflow(Path(compositor), timemon / 'TimeMon', probes / 'WorkspaceProbe', probes / 'DragProbe',
                         Path('/Library/bin/gpbs-wayland'), probes / 'PasteboardProbe',
                         artifacts / (label + '-timemon-workflow'))
        from color_wheel import run as color_wheel
        color_wheel(Path(compositor), timemon / 'TimeMon', probes / 'WorkspaceProbe',
                    artifacts / (label + '-color-wheel'))
        from color_picker_fidelity import run as color_picker_fidelity
        from color_picker_artwork import run as color_picker_artwork
        color_picker_fidelity(artifacts / (label + '-color-picker-fidelity'),
                              images=Path('/Library/ColorPickers/StandardPicker.bundle/Resources'))
        color_picker_artwork(Path(compositor), timemon / 'TimeMon', probes / 'WorkspaceProbe',
                             probes / 'WaylandProbe', artifacts / (label + '-color-picker-artwork'))
        from picker_icons_fidelity import run as picker_icons_fidelity
        from picker_icons_artwork import run as picker_icons_artwork
        picker_icons_fidelity(artifacts / (label + '-picker-icons-fidelity'),
                              images=Path('/Library/ColorPickers'))
        picker_icons_artwork(Path(compositor), timemon / 'TimeMon', probes / 'WorkspaceProbe',
                             probes / 'WaylandProbe', artifacts / (label + '-picker-icons-artwork'))
        from magnifier_fidelity import run as magnifier_fidelity
        from magnifier_artwork import run as magnifier_artwork
        magnifier_fidelity(artifacts / (label + '-magnifier-fidelity'),
                           image=Path('/Library/Images/MagnifyGlass.tiff'))
        magnifier_artwork(Path(compositor), timemon / 'TimeMon', probes / 'WorkspaceProbe',
                          probes / 'WaylandProbe', artifacts / (label + '-magnifier-artwork'))
        from color_pick import run as color_pick
        from color_pick_native import run as color_pick_native
        color_pick(Path(compositor), probes / 'registry-probe', probes / 'shell-probe',
                   probes / 'lock-probe', artifacts / (label + '-color-pick-protocol'),
                   capture_probe=probes / 'capture-probe')
        color_pick_native(Path(compositor), timemon / 'TimeMon', probes / 'WorkspaceProbe',
                          probes / 'registry-probe', artifacts / (label + '-color-pick-native'))
        application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe',
            openup / 'documents.tiff', artifacts / (label + '-openup-document-artwork'),
            tile=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff'))
        for name, directory, icon in (('Review', 'Resources', 'Review'), ('OpenUp', 'Images', 'application')):
            bundle = Path('/Applications') / (name + '.app')
            resources(probes / 'WaylandProbe', repository / 'Applications' / name / directory,
                bundle / 'Resources', artifacts / (label + '-' + name.lower() + '-resources'))
            application_artwork(Path(compositor), probes / 'ArtworkProbe', probes / 'WaylandProbe',
                bundle / 'Resources' / (icon + '.tiff'), artifacts / (label + '-' + name.lower() + '-artwork'),
                application=bundle / name if name == 'OpenUp' else None,
                workspace_probe=probes / 'WorkspaceProbe' if name == 'OpenUp' else None,
                tile=Path('/Library/Themes/NextSpace.theme/Resources/ThemeImages/common_Tile.tiff'))

    def input_methods(label):
        from text_input import run as protocol
        from fcitx5 import run as engine
        terminal = Path('/Applications/Terminal.app/Terminal')
        query = probes / 'WorkspaceProbe'
        pasteboard = dict(pasteboard_server=Path('/Library/bin/gpbs-wayland'),
            pasteboard_probe=probes / 'PasteboardProbe')
        protocol(compositor, str(probes / 'registry-probe'), artifacts / (label + '-text-input'),
            str(probes / 'WaylandProbe'), str(terminal), str(query),
            str(pasteboard['pasteboard_server']), str(pasteboard['pasteboard_probe']))
        for name in ('pinyin', 'hangul'):
            engine(Path(compositor), probes / 'WaylandProbe', artifacts / (label + '-fcitx5-' + name),
                nested=True, terminal=terminal, workspace_probe=query, engine_name=name,
                replace_selection=True, wire_trace=name == 'pinyin', **pasteboard)

    for package in ('xwayland', 'xserver-xorg-core'):
        state = subprocess.run(['dpkg-query', '-W', '-f=${Status}', package], capture_output=True, text=True)
        assert 'install ok installed' not in state.stdout, package
    install(packages, NAMES, 'installed-native')
    assert not Path('/Library/Bundles/libgnustep-x11-032.bundle').exists()
    installed_payload(packages, NAMES, 'installed')
    toolkit_models('installed')
    name_server_lock('installed')
    event_delivery('installed')
    reconstructed_cursors('installed')
    defaults = plistlib.loads(Path('/Library/Preferences/GlobalDefaults.plist').read_bytes())
    defaults['NextSpacePackageUpgradeFixture'] = True
    settings = {
        'Library/Preferences/GNUstep.conf': Path('/Library/Preferences/GNUstep.conf').read_bytes() + b'\n# package-upgrade preservation fixture\n',
        'Library/Preferences/GlobalDefaults.plist': plistlib.dumps(defaults),
        'etc/fonts/conf.d/25-nextspace-fonts.conf': Path('/etc/fonts/conf.d/25-nextspace-fonts.conf').read_bytes().replace(
            b'</fontconfig>', b'<!-- package-upgrade preservation fixture -->\n</fontconfig>')}
    for relative, value in settings.items():
        (Path('/') / relative).write_bytes(value)
    with (artifacts / 'bus.log').open('w') as log:
        bus = subprocess.Popen(['dbus-daemon', '--system', '--nofork', '--nopidfile',
            '--address=unix:path=' + str(artifacts / 'bus')], stdout=log, stderr=log)
    try:
        until(lambda: (artifacts / 'bus').exists(), 'owned package-test system bus')
        os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = 'unix:path=' + str(artifacts / 'bus')
        file_conflicts('installed')
        applications('installed-applications')
        drag_start('installed')
        buffer_lifetime('installed')
        printing('installed')
        cursors('installed')
        image_formats('installed')
        shell('installed-workspace')
        login('installed-greeter')
        portal('installed')
        locked_shutdown('installed')
        user_hooks('installed')
        input_methods('installed')
        applications('live-upgrade', lambda: install(upgraded, NAMES, 'upgraded'), full=False)
        assert all((Path('/') / relative).read_bytes() == value for relative, value in settings.items())
        installed_payload(upgraded, NAMES, 'upgraded', changed=settings)
        toolkit_models('upgraded')
        name_server_lock('upgraded')
        file_conflicts('upgraded')
        event_delivery('upgraded')
        reconstructed_cursors('upgraded')
        applications('upgraded-applications')
        drag_start('upgraded')
        buffer_lifetime('upgraded')
        printing('upgraded')
        cursors('upgraded')
        image_formats('upgraded')
        shell('upgraded-workspace')
        login('upgraded-greeter')
        portal('upgraded')
        locked_shutdown('upgraded')
        user_hooks('upgraded')
        input_methods('upgraded')
        for package in ('xwayland', 'xserver-xorg-core'):
            state = subprocess.run(['dpkg-query', '-W', '-f=${Status}', package], capture_output=True, text=True)
            assert 'install ok installed' not in state.stdout, package
    finally:
        if bus.poll() is None: bus.terminate(); bus.wait(timeout=5)
    libraries = capture_libraries(artifacts)
    for name in settings:
        target = artifacts / 'preserved-configurations' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path('/') / name, target)
    assert all(hashlib.sha256((source / name).read_bytes()).hexdigest() == checksum
        for name, checksum in validation.items()), 'Validation sources changed during the run'
    (artifacts / 'preserved-configurations.json').write_text(json.dumps(
        {name: hashlib.sha256((Path('/') / name).read_bytes()).hexdigest() for name in settings}, indent=2) + '\n')
    remove(list(reversed(NAMES)), 'removed-native')
    assert not (PREFIX / 'bin/nextspace-compositor').exists()
    assert not (PREFIX / 'Apps/Workspace.app/Workspace').exists()
    assert not Path('/usr/share/icons/NextSpace/cursors/left_ptr').exists()
    assert all((Path('/') / name).read_bytes() == value for name, value in settings.items())
    (artifacts / 'results.json').write_text(json.dumps(dict(versions=[version, upgraded_version],
        clean_install=True, live_toolkit_upgrade=True, preferences_preserved=True,
        wayland_only=True, gamma_model=True, name_server_lock=True, portals=True, locked_shutdown=True,
        input_methods=True, cursors=True, output_results=True, image_formats=True,
        display_manager_unchanged=True, user_hooks=True, external_libraries=len(libraries),
        bus_reaped=bus.poll() is not None), indent=2) + '\n')
    print('Wayland-only desktop install/live-upgrade and native applications: PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipts', type=Path, nargs=2, required=True)
    parser.add_argument('--probes', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    run(*[path.resolve() for path in args.receipts], args.probes.resolve(), args.artifacts.resolve())
