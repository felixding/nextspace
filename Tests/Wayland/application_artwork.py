#!/usr/bin/env python3
"""Compare the production Workspace icon view with vector-derived TIFF pixels."""
import argparse
import ctypes
import ctypes.util
import json
import math
import os
from pathlib import Path
import select
import socket
import subprocess
import tempfile

from PIL import Image, ImageChops
from gnustep import private_defaults, process_runtime
from integration import read_json_lines, until
from theme_images import CONTROL_SIZES
from artwork_reference import assert_not_enlarged


def image_view_clip(bounds, window_height, density):
    """Match CairoGState's pixel clip for an integral NSImageCell view."""
    x,y,width,height = bounds; factor = density/120
    edges = (x*factor,(window_height-y-height)*factor,(x+width)*factor,(window_height-y)*factor)
    if all(value == math.floor(value) for value in bounds):
        edges = tuple(math.floor(value+.5) for value in edges)
    return edges


def placed_reference(reference, origin, background, directory, density, size=None, clip=None, pad=False, opacity=1, source_clip=None, native_rep_size=None):
    """Match Cairo's fractional placement using independently decoded TIFF pixels."""
    source = directory / f'info-source-{density}.png'; reference.save(source)
    destination = directory / f'info-expected-{density}.png'
    cairo = ctypes.CDLL(ctypes.util.find_library('cairo'))
    pointer, number = ctypes.c_void_p, ctypes.c_double
    def call(name, arguments, result=None):
        method = getattr(cairo, 'cairo_' + name)
        method.argtypes = arguments; method.restype = result
        return method
    load = call('image_surface_create_from_png', [ctypes.c_char_p], pointer)
    create = call('image_surface_create', [ctypes.c_int, ctypes.c_int, ctypes.c_int], pointer)
    context = call('create', [pointer], pointer)
    color = call('set_source_rgba', [pointer, number, number, number, number])
    paint = call('paint', [pointer])
    paint_alpha = call('paint_with_alpha', [pointer, number])
    place = call('set_source_surface', [pointer, pointer, number, number])
    pattern = call('get_source', [pointer], pointer)
    extend = call('pattern_set_extend', [pointer, ctypes.c_int])
    write = call('surface_write_to_png', [pointer, ctypes.c_char_p], ctypes.c_int)
    destroy = call('destroy', [pointer]); release = call('surface_destroy', [pointer])
    translate = call('translate', [pointer, number, number]); scale = call('scale', [pointer, number, number])
    rectangle = call('rectangle', [pointer, number, number, number, number]); crop = call('clip', [pointer])
    save = call('save', [pointer]); restore = call('restore', [pointer])
    push = call('push_group', [pointer]); pop = call('pop_group', [pointer], pointer)
    source_pattern = call('set_source', [pointer, pointer]); release_pattern = call('pattern_destroy', [pointer])
    image = load(os.fsencode(source))
    canvas = background.size if isinstance(background, Image.Image) else reference.size
    surface = create(0, *canvas); background_surface = None
    device_scale = call('surface_set_device_scale', [pointer, number, number])
    factor = density/120
    if native_rep_size:
        assert isinstance(background,Image.Image) and size and clip and not source_clip and opacity==1
        device_scale(surface,factor,factor)
    drawing = context(surface)
    try:
        if isinstance(background, Image.Image):
            background_path = directory / f'animation-background-{density}.png'; background.save(background_path)
            background_surface = load(os.fsencode(background_path))
            if native_rep_size: device_scale(background_surface,factor,factor)
            place(drawing, background_surface, 0, 0)
        else: color(drawing, *(value/255 for value in background))
        paint(drawing)
        if native_rep_size:
            # Keep the backend's logical transforms and intermediate group:
            # flattening them into one physical scale can change filter rounding.
            matrix = lambda *values: (number*6)(*values)
            set_matrix = call('set_matrix',[pointer,pointer])
            transform = call('transform',[pointer,pointer])
            pattern_matrix = call('pattern_set_matrix',[pointer,pointer])
            operator = call('set_operator',[pointer,ctypes.c_int])
            reset_clip = call('reset_clip',[pointer])
            set_matrix(drawing,matrix(1,0,0,-1,0,canvas[1]/factor))
            x,y,width,height = clip[0]/factor,(canvas[1]-clip[1]-clip[3])/factor,clip[2]/factor,clip[3]/factor
            save(drawing);reset_clip(drawing)
            rectangle(drawing,x-2/factor,y-2/factor,width+4/factor,height+4/factor);crop(drawing)
            push(drawing);save(drawing)
            logical_width,logical_height=native_rep_size
            transform(drawing,matrix(size[0]/factor/logical_width,0,0,size[1]/factor/logical_height,
                origin[0]/factor,(canvas[1]-origin[1]-size[1])/factor))
            transform(drawing,matrix(logical_width/reference.width,0,0,logical_height/reference.height,0,0))
            place(drawing,image,0,0);pattern_matrix(pattern(drawing),matrix(1,0,0,-1,0,reference.height))
            if pad:extend(pattern(drawing),3)
            rectangle(drawing,0,0,*reference.size);crop(drawing);operator(drawing,1);paint(drawing)
            restore(drawing);grouped=pop(drawing);restore(drawing)
            rectangle(drawing,x,y,width,height);crop(drawing)
            source_pattern(drawing,grouped);release_pattern(grouped);operator(drawing,2);paint(drawing)
        elif source_clip:
            save(drawing); push(drawing)
            rectangle(drawing, *source_clip); crop(drawing)
        if not native_rep_size:
            if clip and not source_clip: rectangle(drawing, *clip); crop(drawing)
            translate(drawing, *origin)
            if size: scale(drawing, size[0]/reference.width, size[1]/reference.height)
            place(drawing, image, 0, 0)
            if pad: extend(pattern(drawing), 3)  # CAIRO_EXTEND_PAD, as in the bitmap backend.
            if source_clip or opacity == 1: paint(drawing)
            else: paint_alpha(drawing, opacity)
            if source_clip:
                # Keep associated-alpha pixels in Cairo through the second clip.
                grouped = pop(drawing); restore(drawing)
                if clip: rectangle(drawing, *clip); crop(drawing)
                source_pattern(drawing, grouped); release_pattern(grouped)
                if opacity == 1: paint(drawing)
                else: paint_alpha(drawing, opacity)
        assert write(surface, os.fsencode(destination)) == 0
    finally:
        destroy(drawing); release(surface); release(image)
        if background_surface: release(background_surface)
    with Image.open(destination) as result: return result.convert('RGBA')


def info_panel(command, env, application, workspace_probe, density_probe, source, references, artifacts, theme='NextSpace', clock_atlas=None, clock_language=None):
    name = application.name
    assert name in ('TextEdit', 'OpenUp', 'Preferences'), name
    if name == 'TextEdit':
        document = artifacts / 'document.txt'; document.write_text('Native artwork check\n')
        arguments = ['-GSFilePath', str(document)]; caption = 'Info'
        secondary, logical = 'EditTitle', (232, 56)
    elif name == 'OpenUp':
        temporary = artifacts / 'archives'; temporary.mkdir()
        arguments = ['-NSUseRunningCopy', 'NO', '-TempFilesDirectory', str(temporary)]; caption = ''
        secondary, logical = 'narrow', (184, 19)
    else:
        arguments = []; caption = 'Info Panel'; secondary = None
    log_path = artifacts / 'application.log'
    with log_path.open('w') as log:
        app = subprocess.Popen([str(application), '-GSBackend', 'libgnustep-wayland',
            '-GSTheme', str(theme), *arguments], env=env, stdout=log, stderr=log)
    try:
        def ready():
            assert app.poll() is None, log_path.read_text()
            if name == 'OpenUp':
                return subprocess.run([str(workspace_probe), '--openup', 'state'], env=env,
                    capture_output=True, timeout=15).returncode == 0
            return any(w['pid'] == app.pid and w['width'] > 300 for w in command('windows'))
        until(ready, name + ' application startup', timeout=20)
        clock_state = None; atlas_images = []
        if name == 'Preferences':
            process = subprocess.run([str(workspace_probe), '--preferences-clock',
                *([clock_language] if clock_language else [])], env=env,
                capture_output=True, text=True, timeout=15)
            (artifacts / 'clock-query.log').write_text(process.stdout + process.stderr)
            assert process.returncode == 0, process.stderr
            clock_state = json.loads(process.stdout)
            (artifacts / 'clock-state.json').write_text(json.dumps(clock_state, indent=2) + '\n')
            assert {key: clock_state[key] for key in ('hour','minute','day','month')} == dict(hour=13,minute=47,day=31,month=10)
            assert clock_state['format24'], clock_state
            if clock_atlas:
                atlas_images, density = representations(density_probe, clock_atlas, artifacts, logical=(255,80))
                assert clock_state['representations'] == [[r['width'],r['height']] for r in density['representations']]
        (artifacts / 'info-runtime.json').write_text(json.dumps(process_runtime(app.pid), indent=2) + '\n')
        process = subprocess.run([str(workspace_probe), '--info-artwork', name, caption],
            env=env, capture_output=True, text=True, timeout=15)
        (artifacts / 'info-query.log').write_text(process.stdout + process.stderr)
        (artifacts / 'info-windows.json').write_text(json.dumps(
            [w for w in command('windows') if w['pid'] == app.pid], indent=2) + '\n')
        assert process.returncode == 0, process.stderr
        state = json.loads(process.stdout)
        (artifacts / 'info-state.json').write_text(json.dumps(state, indent=2) + '\n')
        icon, = [image for image in state['images'] if image['width'] == image['height'] == 48]
        assert icon['representations'] == [[size, size] for size in (48, 60, 72, 84, 96)], icon
        title_density = None
        if secondary:
            title_images, title_density = representations(density_probe, source.with_name(secondary + '.tiff'),
                artifacts, logical=logical)
            title, = [image for image in state['images'] if (image['width'], image['height']) == logical]
            assert title['representations'] == [list(image.size) for image in title_images], title
        clock_tiles, clock_density = representations(density_probe, source.with_name('ClockViewTile.tiff'),
            artifacts, logical=(64, 64)) if name == 'Preferences' else ([], None)
        target = command('outputs')[0]; records = []
        if secondary:
            title_artifacts = artifacts / 'title'; title_artifacts.mkdir()
        for density, reference in zip((120, 150, 180, 210, 240), references):
            assert command(f"test-scale {target['name']} {density} 10000")['ok']
            assert command('confirm')['ok']
            def window():
                return next(w for w in command('windows') if w['pid'] == app.pid and w['client_id'] == state['window'])
            w = window()
            assert command(f"move {w['id']} {target['x']+10} {target['y']+10}")['ok']
            if clock_tiles:
                clock, = [w for w in command('windows') if w['pid'] == app.pid and w['style'] == 64]
                assert command(f"move {clock['id']} {target['x']+100} {target['y']+10}")['ok']
            def captured():
                w = window(); path = artifacts / 'captures' / f"window-{w['client_id']}-{density}.png"
                if w['preferred_scale'] != density or w['buffer_width'] != (w['width']*density+60)//120:
                    return False
                try:
                    with Image.open(path) as image: actual = image.convert('RGBA')
                except OSError: return False
                if actual.size != (w['buffer_width'], w['buffer_height']): return False
                return w, actual
            w, actual = until(captured, 'native ' + name + ' Info panel density')
            actual.save(artifacts / f'info-{density}.png')
            panel_pixels = actual
            process = subprocess.run([str(workspace_probe),'--info-artwork',name,caption],
                env=env,capture_output=True,text=True,timeout=15)
            query_log = title_artifacts / f'query-{density}.log' if secondary else artifacts / f'info-query-{density}.log'
            query_log.write_text(process.stdout+process.stderr)
            assert process.returncode == 0, process.stderr
            current_images = json.loads(process.stdout)['images']
            current_icon, = [entry for entry in current_images if (entry['width'],entry['height']) == (48,48)]
            # centerScanRect: aligns the image at the current backing density.
            x,y,width,height = current_icon['drawing_base']; factor = density/120
            origin_x,origin_y = x*factor,(w['height']-y-height)*factor
            left = math.floor(origin_x + 0.5); top = math.floor(origin_y + 0.5)
            actual = actual.crop((left, top, left+reference.width, top+reference.height))
            vx,vy,vr,vb = image_view_clip(current_icon['base'],w['height'],density)
            placement = dict(size=(width*factor,height*factor),
                clip=(vx-left,vy-top,vr-vx,vb-vy))
            expected = placed_reference(reference, (origin_x-left, origin_y-top),
                actual.getpixel((0, 0)), artifacts, density, **placement)
            actual.save(artifacts / f'info-icon-{density}.png')
            expected.save(artifacts / f'info-expected-{density}.png')
            maximum = max(channel[1] for channel in ImageChops.difference(actual, expected).getextrema())
            assert maximum <= 1, (density, maximum, icon, w)
            records.append(dict(scale=density, maximum_channel_difference=maximum, window=w))
            records[-1]['icon'] = dict(image_view=current_icon,origin=[origin_x,origin_y],crop=[left,top],
                view_clip=list(placement['clip']),background=list(actual.getpixel((0,0))))
            if secondary:
                # Preserve the archived cell's image placement, clipping and
                # centerScanRect behavior at each backing density.
                current_title, = [entry for entry in current_images
                    if (entry['width'],entry['height']) == logical]
                x,y,width,height = current_title['drawing_base']; factor = density/120
                tx,ty = x*factor,(w['height']-y-height)*factor
                left, top = math.floor(tx+.5), math.floor(ty+.5)
                title_reference = title_images[len(records)-1]
                crop = panel_pixels.crop((left,top,left+title_reference.width,top+title_reference.height))
                vx,vy,vr,vb = image_view_clip(current_title['base'],w['height'],density)
                view_clip = (vx-left,vy-top,vr-vx,vb-vy)
                expected = placed_reference(title_reference,(tx-left,ty-top),crop.getpixel((0,0)),title_artifacts,density,
                    size=(width*factor,height*factor),clip=view_clip)
                crop.save(title_artifacts / f'actual-{density}.png')
                maximum = max(channel[1] for channel in ImageChops.difference(crop,expected).getextrema())
                assert maximum <= 1, (name+' title',density,maximum,title,w)
                records[-1]['title'] = dict(maximum_channel_difference=maximum,origin=[tx,ty],crop=[left,top],
                    background=list(crop.getpixel((0,0))),image_view=current_title,view_clip=list(view_clip))
            if clock_tiles:
                def clock_capture():
                    current, = [w for w in command('windows') if w['pid'] == app.pid and w['style'] == 64]
                    if current['preferred_scale'] != density or current['buffer_width'] != 64*density//120:
                        return False
                    try:
                        with Image.open(artifacts / 'captures' / f"window-{current['client_id']}-{density}.png") as image:
                            pixels = image.convert('RGBA')
                    except OSError: return False
                    return (current, pixels) if pixels.size == (64*density//120,)*2 else False
                current, pixels = until(clock_capture, 'Preferences clock tile density')
                pixels.save(artifacts / f'clock-{density}.png')
                difference = ImageChops.difference(pixels, clock_tiles[len(records)-1])
                # The clock atlas is qualified separately; check the new tile
                # outside the time/day/month drawing rectangles.
                for x, y, width, height in ((5,7,53,11), (14,25,33,6), (14,32,33,17), (14,49,31,6)):
                    factor = density/120
                    difference.paste((0,0,0,0), (math.floor(x*factor)-2, math.floor(y*factor)-2,
                        math.ceil((x+width)*factor)+2, math.ceil((y+height)*factor)+2))
                maximum = max(channel[1] for channel in difference.getextrema())
                assert maximum <= 1, (density, maximum, current)
                records[-1]['clock_tile'] = dict(window=current, maximum_channel_difference=maximum,
                    glyph_regions_excluded=True)
                if atlas_images and density in (120,240):
                    # Independent sprite reference for the fixed Saturday,
                    # October 31, 13:47 fixture, using the public atlas layout.
                    factor = density//120; expected = clock_tiles[len(records)-1].copy()
                    atlas = atlas_images[len(records)-1]
                    sprites = ((0,39,19,6,21,25), (40,62,22,6,19,49),
                        (88,49,12,17,20,32), (64,49,12,17,30,32),
                        (83,13,4,11,16,7), (95,13,8,11,20,7),
                        (159,13,3,11,28,7), (103,13,8,11,31,7), (126,13,7,11,39,7))
                    for x,y,width,height,dx,dy in sprites:
                        sprite = atlas.crop((x*factor,y*factor,(x+width)*factor,(y+height)*factor))
                        layer = Image.new('RGBA', expected.size); layer.paste(sprite,(dx*factor,dy*factor))
                        expected = Image.alpha_composite(expected,layer)
                    expected.save(artifacts / f'clock-expected-{density}.png')
                    maximum = max(channel[1] for channel in ImageChops.difference(pixels,expected).getextrema())
                    assert maximum <= 1, (density,clock_language,maximum)
                    records[-1]['clock_pixels'] = dict(maximum_channel_difference=maximum,language=clock_language or 'English')
        return dict(cases=records, images=state['images'], title_density=title_density, clock_density=clock_density,
            clock_state=clock_state, clock_atlas_checked=bool(clock_atlas))
    finally:
        if app.poll() is None: app.terminate(); app.wait(timeout=5)


def representations(probe, source, artifacts, logical=(48, 48)):
    process = subprocess.run([str(probe), '--image-density', str(source)],
        capture_output=True, text=True, timeout=15)
    (artifacts / (source.stem + '-density.log')).write_text(process.stdout + process.stderr)
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    assert result['ok'] and len(result['representations']) == 5, result
    images = []
    with Image.open(source) as image:
        assert image.n_frames == 5, source
        for index, density in enumerate((120, 150, 180, 210, 240)):
            image.seek(index)
            pixels = image.convert('RGBA')
            assert pixels.size == tuple((points*density+60)//120 for points in logical), pixels.size
            assert all(math.isclose(value, 72*count/points, abs_tol=0.00001)
                for value, count, points in zip(image.info['dpi'], pixels.size, logical)), image.info
            rep = result['representations'][index]
            assert all(math.isclose(rep['logical_' + axis], points, abs_tol=.00001)
                for axis, points in zip(('width', 'height'), logical)), rep
            selected = result['density_selections'][index]
            assert (selected['width'], selected['height']) == pixels.size, selected
            images.append(pixels)
    assert_not_enlarged(images, source.name)
    return images, result


def resources(probe, references, installed, artifacts, names=None):
    """Preserve legacy logical sizes while qualifying every replacement resource."""
    artifacts.mkdir(parents=True)
    records = []
    paths = (references / name for name in names) if names else references.glob('*.tiff')
    for reference in sorted(path for path in paths if not path.name.startswith('.')):
        with Image.open(reference) as image:
            logical = tuple(float(pixels*72/dpi) for pixels, dpi in zip(image.size, image.info.get('dpi', (72, 72))))
        _, result = representations(probe, installed / reference.name, artifacts, logical)
        records.append(dict(name=reference.name, logical=logical, **result))
    assert records
    (artifacts / 'results.json').write_text(json.dumps(dict(cases=records, complete=True), indent=2) + '\n')
    print(f'Vector resources: {len(records)*5} AppKit selections with original logical dimensions PASS')


def control_artwork(command, env, probe, images, artifacts, theme, kind='scrollers', names=None, decorated=False):
    """Exercise density-specific artwork through real AppKit controls."""
    assert kind in ('scrollers','buttons','dimples')
    titles = dict(scrollers='ScrollerArtwork', buttons='ButtonArtwork', dimples='DimpleArtwork')
    flags = dict(scrollers='ArtworkScrollers', buttons='ArtworkButtons', dimples='ArtworkDimples')
    directory = artifacts / kind; directory.mkdir()
    captures = directory / 'captures'; captures.mkdir()
    client_env = dict(env, NEXTSPACE_WAYLAND_CAPTURE_DIR=str(captures))
    with (directory / 'probe.log').open('w') as log, (directory / 'probe.stderr').open('w') as errors:
        client = subprocess.Popen([str(probe), '-GSBackend', 'libgnustep-wayland',
            '-GSTheme', str(theme), '-'+flags[kind], 'YES', '-ArtworkDecorations', 'YES' if decorated else 'NO',
            '-GSWaylandServerDecorations', 'YES' if decorated else 'NO'], env=client_env, stdout=log, stderr=errors)
    try:
        def window():
            assert client.poll() is None, (directory / 'probe.stderr').read_text()
            return next((w for w in command('windows') if w['pid'] == client.pid
                and w['title'] == titles[kind]), None)
        initial = until(window, 'production '+kind)
        assert initial['server_decorated'] == decorated, initial
        arrows = json.loads((directory / 'probe.log').read_text())
        count = dict(scrollers=8, buttons=4, dimples=2)[kind]
        assert len(arrows) == count and len({arrow['name'] for arrow in arrows}) == count
        if names:
            assert not set(names) - {arrow['name'] for arrow in arrows}, names
            arrows = [arrow for arrow in arrows if arrow['name'] in names]
            count = len(arrows)
        logical_sizes = {row['name']:(9,9) if kind=='scrollers' else (6,6) if kind=='dimples' else
            CONTROL_SIZES[row['name']] for row in arrows}
        for arrow in arrows:
            sizes = [[math.floor(point*scale+.5) for point in logical_sizes[arrow['name']]]
                for scale in (1,1.25,1.5,1.75,2,3,4,5,6,7,8)]
            assert arrow['representations'] == sizes, arrow
        (directory / 'runtime.json').write_text(json.dumps(process_runtime(client.pid), indent=2) + '\n')
        target = command('outputs')[0]; records = []
        for index, density in enumerate((120, 150, 180, 210, 240)):
            assert command(f"test-scale {target['name']} {density} 10000")['ok']
            assert command('confirm')['ok']
            assert command(f"move {window()['id']} {target['x']+10} {target['y']+10}")['ok']
            def captured():
                w = window()
                if w['preferred_scale'] != density or w['buffer_width'] != (w['width']*density+60)//120:
                    return False
                try:
                    with Image.open(captures / f"window-{w['client_id']}-{density}.png") as image:
                        actual = image.convert('RGBA')
                except OSError: return False
                if actual.size != (w['buffer_width'], w['buffer_height']): return False
                return w, actual
            w, actual = until(captured, 'native scroller density')
            actual.save(directory / f'actual-{density}.png')
            comparisons = []
            for arrow in arrows:
                x, y, width, height = arrow['base']; factor = density / 120
                logical = logical_sizes[arrow['name']]
                if kind in ('scrollers','dimples'):
                    # NSButtonCell centers in the flipped scroller's coordinates.
                    origin_x = math.floor(x + (width-logical[0])/2)*factor
                    origin_y = (w['height'] - math.ceil(y + (height-logical[1])/2) - logical[1])*factor
                else:
                    assert all(math.isclose(value,point,abs_tol=.00001) for value,point in zip((width,height),logical))
                    origin_x = x*factor; origin_y = (w['height']-y-height)*factor
                if density != 120:
                    # centerScanRect aligns centered image bounds to backing
                    # pixels. Compare the selected representation directly;
                    # reproducing the old interpolation would hide blur.
                    if kind in ('scrollers', 'dimples'):
                        dx, dy, dw, dh = arrow['drawing_base']
                        origin_x = (dx+(dw-logical[0])/2)*factor
                        origin_y = (w['height']-dy-(dh+logical[1])/2)*factor
                    origin_x = math.floor(origin_x + .5)
                    origin_y = math.floor(origin_y + .5)
                left, top = math.floor(origin_x), math.floor(origin_y)
                size = (math.ceil(logical[0]*factor + origin_x-left), math.ceil(logical[1]*factor + origin_y-top))
                if density != 120:
                    size = tuple(math.floor(point*factor+.5) for point in logical)
                with Image.open(images / (arrow['name'] + '.tiff')) as image:
                    image.seek(index); reference = image.convert('RGBA')
                crop = actual.crop((left, top, left+size[0], top+size[1]))
                background = (255,255,255,255) if arrow['name'].endswith('H') else (170,170,170,255)
                if kind == 'buttons' and density == 120:
                    # AppKit's 1x bitmap cache preserves native pixels at an
                    # integral origin, including legacy fractional point sizes.
                    layer = Image.new('RGBA', size)
                    layer.paste(reference, (round(origin_x)-left, round(origin_y)-top))
                    expected = Image.alpha_composite(Image.new('RGBA', size, background), layer)
                elif density != 120:
                    expected = Image.alpha_composite(Image.new('RGBA', size, background), reference)
                else:
                    expected = placed_reference(reference, (origin_x-left, origin_y-top),
                        Image.new('RGBA', size, background), directory, density,
                        size=tuple(point*factor for point in logical), pad=True,
                        clip=(origin_x-left, origin_y-top, width*factor, height*factor) if kind=='buttons' else None)
                crop.save(directory / f"{arrow['name']}-{density}-actual.png")
                expected.save(directory / f"{arrow['name']}-{density}-expected.png")
                difference = ImageChops.difference(crop, expected)
                # Fractional clipping has its own backend fixtures. Here compare
                # the artwork interior, excluding its one-pixel bounding edge.
                inset = 0 if density in (120, 240) else 1
                difference = difference.crop((inset, inset, size[0]-inset, size[1]-inset))
                maximum = max(channel[1] for channel in difference.getextrema())
                tolerance = 1
                assert maximum <= tolerance, (density, arrow['name'], maximum)
                comparisons.append(dict(name=arrow['name'], maximum_channel_difference=maximum,
                    excluded_bounding_pixels=inset, rounding_tolerance=tolerance))
            records.append(dict(scale=density, window=w, comparisons=comparisons))
        result = dict(cases=records, complete=True, requested_names=names, image_alignment='backing_pixels', decorated=decorated,
            **{'arrows' if kind=='scrollers' else kind:arrows})
        (directory / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
        print(f'Vector {kind}: {count*5} native control-artwork pixel checks PASS')
        return result
    finally:
        if client.poll() is None: client.terminate(); client.wait(timeout=5)


def run(compositor, probe, density_probe, source, artifacts, application=None, workspace_probe=None, tile=None, theme='NextSpace', strip=None, scroller_images=None, clock_atlas=None, clock_language=None, control_images=None, named_image=None, logical=(48,48), canvas=False):
    artifacts.mkdir(parents=True)
    canvas_size = tuple(max(64, points+16) for points in logical) if canvas else (64,64)
    images, density_result = representations(density_probe, source, artifacts, logical)
    strip_images = []; strip_density = None; strip_size = None
    if strip:
        with Image.open(strip) as image:
            strip_size = tuple(round(count*72/dpi) for count, dpi in zip(image.size, image.info['dpi']))
        strip_images, strip_density = representations(density_probe, strip, artifacts, strip_size)
    tile_images = []
    if tile:
        with Image.open(tile) as image:
            assert image.n_frames == 11
            for index in range(5):
                image.seek(index); tile_images.append(image.convert('RGBA'))
    records = []
    with tempfile.TemporaryDirectory(prefix='nextspace-artwork-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, WLR_BACKENDS='headless',
            WLR_HEADLESS_OUTPUTS='2', WLR_RENDERER='pixman')
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET'): env.pop(key, None)
        private_defaults(env, runtime)
        captures = artifacts / 'captures'; captures.mkdir()
        env['NEXTSPACE_WAYLAND_CAPTURE_DIR'] = str(captures)
        control, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        control.settimeout(5)
        with (artifacts / 'compositor.log').open('w') as log:
            server = subprocess.Popen([str(compositor), '-c', str(child.fileno())], env=env,
                pass_fds=[child.fileno()], stdout=subprocess.PIPE, stderr=log, text=True)
        child.close(); client = None
        def command(value):
            control.sendall(value.encode()); return json.loads(control.recv(65536))
        try:
            assert select.select([server.stdout], [], [], 10)[0]
            line = server.stdout.readline().strip()
            assert line.startswith('WAYLAND_DISPLAY='), line
            env['WAYLAND_DISPLAY'] = line.split('=', 1)[1]
            (artifacts / 'compositor-runtime.json').write_text(json.dumps(process_runtime(server.pid), indent=2) + '\n')
            with (artifacts / 'probe.log').open('w') as log, (artifacts / 'probe.stderr').open('w') as errors:
                client = subprocess.Popen([str(probe), '-GSBackend', 'libgnustep-wayland',
                    '-GSTheme', str(theme), '-ArtworkImage', str(source),
                    *(['-ArtworkImageName', named_image] if named_image else []),
                    *(['-ArtworkCanvas', 'YES'] if canvas else []),
                    *(['-ArtworkStrip', str(strip)] if strip else [])],
                    env=env, stdout=log, stderr=errors)
            def windows():
                assert client.poll() is None, (client.returncode, (artifacts / 'probe.stderr').read_text()[-4000:])
                return {w['title']: w for w in command('windows') if w['pid'] == client.pid and w['style'] == 0
                    and w['title'] in ('ArtworkProbe', 'ArtworkBackground')}
            until(lambda: len(windows()) == 2, 'production icon views')
            assert not any(w['legacy'] for w in windows().values())
            (artifacts / 'runtime.json').write_text(json.dumps(process_runtime(client.pid), indent=2) + '\n')
            target = command('outputs')[0]
            for density, reference in zip((120, 150, 180, 210, 240), images):
                assert command(f"test-scale {target['name']} {density} 10000")['ok']
                assert command('confirm')['ok']
                for index, window in enumerate(windows().values()):
                    assert command(f"move {window['id']} {target['x']+10+index*80} {target['y']+10}")['ok']
                def matching():
                    current = windows()
                    decoded = {}
                    for name, window in current.items():
                        if window['preferred_scale'] != density or window['buffer_width'] != math.floor(canvas_size[0]*density/120+.5):
                            return False
                        path = captures / f"window-{window['client_id']}-{density}.png"
                        try:
                            with Image.open(path) as image: decoded[name] = image.convert('RGBA')
                        except OSError: return False
                    if len(decoded) != 2: return False
                    background = decoded['ArtworkBackground']
                    if tile_images:
                        expected_tile = tile_images[len(records)]
                        assert background.size == expected_tile.size
                        if max(channel[1] for channel in ImageChops.difference(background, expected_tile).getextrema()) > 1:
                            background.save(artifacts / f'old-tile-{density}.png')
                            return False
                    expected = background.copy()
                    layer = Image.new('RGBA', expected.size)
                    layer.paste(reference, (8*density//120, 8*density//120))
                    expected = Image.alpha_composite(expected, layer)
                    if canvas:
                        factor=density/120;origin=(8*factor,(canvas_size[1]-8-logical[1])*factor);size=tuple(value*factor for value in logical)
                        # ArtworkCanvas draws directly, without NSImageCell's
                        # backing-pixel alignment. Keep its fractional edges.
                        left,top=origin;right=left+size[0];bottom=top+size[1]
                        expected=placed_reference(reference,origin,background,artifacts,density,size=size,pad=True,
                            clip=(left,top,right-left,bottom-top),native_rep_size=tuple(
                                density_result['representations'][len(records)]['logical_'+axis]
                                for axis in ('width','height')) if density>120 else None)
                    if strip_images:
                        factor = density/120
                        expected = placed_reference(strip_images[len(records)],
                            (21*factor, (16-(strip_size[1]-7-23))*factor), expected, artifacts, density,
                            size=tuple(value*factor for value in strip_size),
                            # Cropped compositing preserves fractional destination edges.
                            clip=tuple(value*factor for value in (21,16,27,23)),
                            pad=density>120,native_rep_size=tuple(
                                strip_density['representations'][len(records)]['logical_'+axis]
                                for axis in ('width','height')) if density>120 else None)
                    actual = decoded['ArtworkProbe']
                    difference = ImageChops.difference(actual, expected)
                    maximum = max(channel[1] for channel in difference.getextrema())
                    # Independent Pillow and Cairo alpha rounding can differ by one unit.
                    if maximum > 1:
                        actual.save(artifacts / f'actual-{density}.png')
                        expected.save(artifacts / f'expected-{density}.png')
                        return False
                    actual.save(artifacts / f'actual-{density}.png')
                    expected.save(artifacts / f'expected-{density}.png')
                    background.save(artifacts / f'background-{density}.png')
                    return dict(scale=density, maximum_channel_difference=maximum, windows=current)
                records.append(until(matching, 'icon pixels match the native density representation'))
            events = read_json_lines(artifacts / 'probe.log', '{')
            assert len(events)==1,events
            event=events[0]
            assert tuple(event['logical_'+axis] for axis in ('width','height'))==tuple(logical),event
            if named_image:
                assert event['requested_name']==named_image,event
                assert Path(event['resource']).resolve()==source.resolve(),event
            # Capture names contain window IDs local to each application.
            if application or scroller_images or control_images: client.terminate(); client.wait(timeout=5)
            info_records = info_panel(command, env, application, workspace_probe, density_probe,
                source, images, artifacts, theme, clock_atlas, clock_language) if application else None
            scroller_records = control_artwork(command, env, probe, scroller_images, artifacts, theme) if scroller_images else None
            button_records = control_artwork(command, env, probe, control_images, artifacts, theme, 'buttons') if control_images else None
            dimple_records = control_artwork(command, env, probe, control_images, artifacts, theme, 'dimples') if control_images else None
            (artifacts / 'results.json').write_text(json.dumps(dict(cases=records, info_panel=info_records,
                scrollers=scroller_records, buttons=button_records, dimples=dimple_records, density=density_result, strip_density=strip_density,
                vector_tile_checked=bool(tile_images), named_image=event if named_image else None,
                logical_size=list(logical),canvas_draw=canvas,complete=True), indent=2) + '\n')
            print('Vector application icon: five native Workspace captures match density-specific pixels PASS')
            if application: print(application.name + ' Info panel: five native icon pixel checks and loaded artwork representations PASS')
        except BaseException:
            (artifacts / 'failure.json').write_text(json.dumps(dict(windows=command('windows'),
                records=records), indent=2) + '\n')
            raise
        finally:
            if client and client.poll() is None: client.terminate(); client.wait(timeout=5)
            if server.poll() is None: control.sendall(b'quit'); server.wait(timeout=5)
            server.stdout.close(); control.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('compositor', 'probe', 'density-probe', 'source', 'artifacts'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--application', type=Path)
    parser.add_argument('--workspace-probe', type=Path)
    parser.add_argument('--tile', type=Path)
    parser.add_argument('--theme', default='NextSpace')
    parser.add_argument('--strip', type=Path)
    parser.add_argument('--scroller-images', type=Path)
    parser.add_argument('--clock-atlas', type=Path)
    parser.add_argument('--clock-language')
    parser.add_argument('--control-images', type=Path)
    args = parser.parse_args()
    assert bool(args.application) == bool(args.workspace_probe), 'Application and Workspace probe are required together'
    run(*(getattr(args, name).resolve() for name in ('compositor', 'probe', 'density_probe', 'source', 'artifacts')),
        args.application.resolve() if args.application else None,
        args.workspace_probe.resolve() if args.workspace_probe else None,
        args.tile.resolve() if args.tile else None, args.theme, args.strip.resolve() if args.strip else None,
        args.scroller_images.resolve() if args.scroller_images else None,
        args.clock_atlas.resolve() if args.clock_atlas else None, args.clock_language,
        args.control_images.resolve() if args.control_images else None)
