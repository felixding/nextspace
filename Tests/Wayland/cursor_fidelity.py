#!/usr/bin/env python3
"""Compare reconstructed cursor geometry with the original cursor resources."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

from artwork_reference import assert_not_enlarged
from cursor_assets import frames

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO/'Packaging/Sources'))
from vector_art import Artwork, backing_sizes, premultiplied_bgra

BLACK, GREEN, DARK_GREEN, WHITE, PINK = (0,0,0), (102,255,102), (0,170,0), (255,255,255), (255,133,133)
PALETTES = {
    'dnd-move': (BLACK,GREEN), 'dnd-copy': (BLACK,GREEN,DARK_GREEN,WHITE),
    'dnd-link': (BLACK,GREEN), 'dnd-no-drop': (BLACK,PINK),
    'dnd-ask': (BLACK,GREEN),
}


def region(pixel, palette=None):
    if not palette:
        return pixel[0]*255 >= pixel[3]*128
    if len(palette) == 2 and palette[0] == BLACK:
        # Use the pigment's strongest contrast channel. Neutral gray edge
        # samples in the green question mark belong to its dark outline.
        axis = palette[1].index(max(palette[1]))
        return pixel[axis]*255 >= pixel[3]*128
    color = tuple(channel*255/pixel[3] for channel in pixel[:3])
    return min(range(len(palette)),key=lambda i:sum((a-b)**2 for a,b in zip(color,palette[i])))


def compare_original(before, after, name):
    """Keep design regions fixed while permitting antialiased diagonal edges."""
    assert before.size == after.size == (24,24), name
    old_pixels, new_pixels = list(before.getdata()), list(after.getdata())
    if name in ('cross','plus'):
        maximum = opaque = 0
        for old,new in zip(old_pixels,new_pixels):
            assert (old[3] == 255) == (new[3] == 255), name
            if old[3] == 255:
                assert old == new, (name,old,new)
                opaque += 1
            else:
                assert old[:3] == new[:3] == (0,0,0), (name,old,new)
                maximum = max(maximum,abs(old[3]-new[3]))
        assert maximum <= 5, (name,maximum)
        return dict(reference_check='opaque-pixels',opaque_pixels=opaque,
            maximum_shadow_alpha_difference=maximum)
    foreground = {i for i,pixel in enumerate(old_pixels) if pixel[3] >= 128}
    assert foreground == {i for i,pixel in enumerate(new_pixels) if pixel[3] >= 128}, name
    palette = PALETTES.get(name)
    maximum = composite = ambiguous = ambiguous_delta = 0
    for index,(old,new) in enumerate(zip(old_pixels,new_pixels)):
        if not palette:
            assert old[0] == old[1] == old[2] and new[0] == new[1] == new[2], name
        if index in foreground:
            # Cursor files contain premultiplied channels. Classify white/black
            # after accounting for coverage rather than darkening edge pixels.
            if name == 'pencil' and old[3] < 255 and abs(old[0]*255/old[3]-128) <= 8 \
                    and region(old,palette) != region(new,palette):
                # These partially covered bevel edges lie at the black/white
                # threshold. Bound visible antialiasing instead of forcing a
                # binary ink label; solid body regions retain exact labels.
                delta = max(*(abs(a-b) for a,b in zip(old[:3],new[:3])),
                    *(abs((a-old[3])-(b-new[3])) for a,b in zip(old[:3],new[:3])))
                assert delta <= 64, (name,index,delta)
                ambiguous += 1
                ambiguous_delta = max(ambiguous_delta,delta)
            else:
                assert region(old,palette) == region(new,palette), (name,index)
        x,y = index%24,index//24
        if all(yy*24+xx not in foreground for yy in range(max(0,y-2),min(24,y+3))
                for xx in range(max(0,x-2),min(24,x+3))):
            maximum = max(maximum,abs(old[3]-new[3]))
            # Compare associated pixels over black and white backgrounds. These
            # endpoints bound the visible difference over every background and
            # account for the faint gray halo present in some original cursors.
            composite = max(composite,*(abs(a-b) for a,b in zip(old[:3],new[:3])),
                *(abs((a-old[3])-(b-new[3])) for a,b in zip(old[:3],new[:3])))
    assert composite <= 8, (name,maximum,composite)
    result = dict(reference_check='foreground-and-ink-regions',foreground_pixels=len(foreground),
        maximum_far_shadow_alpha_difference=maximum,maximum_far_shadow_composite_difference=composite)
    if ambiguous:
        result.update(antialias_edge_anchors=ambiguous,maximum_antialias_composite_difference=ambiguous_delta)
    if palette:
        anchors = []
        for color in palette:
            eligible = [i for i in foreground if old_pixels[i] == (*color,255)]
            assert eligible and any(max(abs(a*255/new_pixels[i][3]-b)
                for a,b in zip(new_pixels[i][:3],color)) <= 5 for i in eligible), (name,color)
            anchors.extend(i for i in eligible if 0 < i%24 < 23 and 0 < i//24 < 23 and
                all(old_pixels[i+offset] == old_pixels[i] for offset in (-25,-24,-23,-1,1,23,24,25)))
        if name == 'dnd-ask':
            anchors = [y*24+x for y in (17,18) for x in (11,12)]
            assert all(old_pixels[i] == (*GREEN,255) for i in anchors), name
        assert anchors, name
        delta = max(abs(a-b) for i in anchors for a,b in zip(old_pixels[i],new_pixels[i]))
        assert delta <= 5, (name,delta)
        result.update(palette=[list(color) for color in palette],palette_anchors=len(anchors),
            maximum_palette_anchor_difference=delta)
        if len(palette) == 2:
            color = palette[1]
            axis = color.index(max(color))
            span = max(abs(new_pixels[i][channel]-new_pixels[i][axis]*color[channel]/color[axis])
                for i in foreground for channel in range(3))
            # Filter conversion and antialiasing quantize partially covered
            # colors; fully covered palette anchors still use the tighter bound.
            assert span <= 8, (name,span)
            result['maximum_palette_span_difference'] = span
    if name == 'dnd-copy':
        assert all(old_pixels[i] == new_pixels[i] for i in foreground), name
        result['opaque_pixels_exact'] = len(foreground)
    if name == 'dnd-none':
        axes = [i for i in foreground if 0 < i%24 < 23 and 0 < i//24 < 23 and any(
            all(old_pixels[i+offset] == (0,0,0,255) for offset in (-step,0,step)) for step in (1,24))]
        assert axes and all(old_pixels[i] == new_pixels[i] for i in axes), name
        result['solid_axis_anchors'] = len(axes)
    if name == 'context-menu':
        shades = [y*24+x for y in range(13,20) for x in range(13,18)]
        delta = max(abs(a-b) for i in shades for a,b in zip(old_pixels[i],new_pixels[i]))
        assert delta <= 5, (name,delta)
        result.update(menu_shade_anchors=len(shades),maximum_menu_shade_difference=delta)
    if name in ('pirate','pencil'):
        value = 85 if name == 'pirate' else 153
        shades = [i for i,pixel in enumerate(old_pixels) if pixel == (value,value,value,255)
            and (name == 'pirate' or i//24 < 16)]
        assert len(shades) == (12 if name == 'pirate' else 10), name
        delta = max(abs(a-b) for i in shades for a,b in zip(old_pixels[i],new_pixels[i]))
        assert delta <= 5, (name,delta)
        result.update(detail_shade_anchors=len(shades),maximum_detail_shade_difference=delta)
    if name.endswith('_tee') or name in ('ul_angle','ur_angle','ll_angle','lr_angle','tcross'):
        assert all(old_pixels[i][3] == new_pixels[i][3] == 255 for i in foreground), name
        palette_delta = max(abs(a-b) for i in foreground for a,b in zip(old_pixels[i][:3],new_pixels[i][:3]))
        assert palette_delta <= 5, (name,palette_delta)
        result.update(opaque_pixels_exact=sum(old_pixels[i] == new_pixels[i] for i in foreground),
            maximum_foreground_palette_difference=palette_delta)
    if name in ('hand1','hand2','grabbing'):
        # Preserve the original gray palm creases as well as its silhouette.
        # Fully covered pixels avoid comparing antialiasing at curved edges.
        shades = [i for i,pixel in enumerate(old_pixels) if pixel[3] == 255 and 20 <= pixel[0] <= 80]
        white = [i for i,pixel in enumerate(old_pixels) if pixel == (255,255,255,255)
            and 0 < i%24 < 23 and 0 < i//24 < 23
            and all(old_pixels[i+offset] == pixel for offset in (-24,-1,1,24))]
        assert shades and white, name
        shade_delta = max(abs(old_pixels[i][0]-new_pixels[i][0]) for i in shades)
        white_delta = max(255-new_pixels[i][0] for i in white)
        assert all(new_pixels[i][3] == 255 for i in shades+white), name
        assert shade_delta <= 12 and white_delta <= 5, (name,shade_delta,white_delta)
        result.update(shade_anchors=len(shades),white_anchors=len(white),
            maximum_shade_difference=shade_delta,maximum_white_difference=white_delta)
    return result


def check_representations(cursor, artwork, installed, index=0):
    images = []
    for size in backing_sizes(24):
        dense = frames(installed/cursor['name'],size)
        assert len(dense)==len(cursor['frames']), (cursor['name'],size)
        frame = dense[index]
        assert (frame['width'],frame['height'])==(size,size), (cursor['name'],size)
        assert (frame['hotspot_x'],frame['hotspot_y'],frame['delay']) == (
            (cursor['hotspot'][0]*size+12)//24,(cursor['hotspot'][1]*size+12)//24,
            cursor['frames'][index]['duration_ms']), (cursor['name'],size,index)
        image = artwork.render(cursor['frames'][index]['symbol'],size)
        assert frame['pixels']==premultiplied_bgra(image), (cursor['name'],size,index)
        images.append(image)
    assert_not_enlarged(images[:5],cursor['name'])
    return images


def run(theme, artifacts, source=None):
    source = source or REPO/'OS/Linux/usr/share/icons/NextSpace'
    artwork = Artwork(source/'scalable/cursors.svg')
    specification = json.loads((source/'scalable/cursors.json').read_text())
    reconstructed = [cursor for cursor in specification['cursors'] if
        all(artwork.symbols[frame['symbol']].get('data-reconstructed') == 'true'
            for frame in cursor['frames'])]
    assert {cursor['name'] for cursor in reconstructed} == {
        'cross','plus','left_ptr','right_ptr','xterm','hand1','hand2','grabbing','tcross','vertical-text',
        'X_cursor','all-scroll','move','zoom-in','zoom-out','context-menu','question_arrow',
        'pencil','pirate','dnd-ask','watch',
        'wm_up_arrow','wm_down_arrow','wm_left_arrow','wm_right_arrow','wm_h_double_arrow','wm_v_double_arrow',
        'left_side','right_side','top_side','bottom_side','top_tee','bottom_tee','left_tee','right_tee',
        'ul_angle','ur_angle','ll_angle','lr_angle','top_left_corner','top_right_corner','bottom_left_corner','bottom_right_corner',
        'sb_h_double_arrow','sb_v_double_arrow','sb_up_arrow','sb_down_arrow','sb_left_arrow','sb_right_arrow',
        'bd_double_arrow','fd_double_arrow','dnd-none','dnd-move','dnd-copy','dnd-link','dnd-no-drop','crossed_circle'}
    selected = {cursor['name'] for cursor in reconstructed}
    artifacts.mkdir(parents=True, exist_ok=True)
    originals = source/'cursors'
    installed = theme/'cursors'
    assert {p.name for p in originals.iterdir()} == {p.name for p in installed.iterdir()}
    fallbacks = aliases = 0
    for original in originals.iterdir():
        actual = installed/original.name
        if original.is_symlink():
            assert actual.is_symlink() and actual.readlink() == original.readlink(), original.name
            aliases += 1
        elif original.name not in selected:
            assert not actual.is_symlink() and actual.read_bytes() == original.read_bytes(), original.name
            fallbacks += 1
    records = []
    for cursor in reconstructed:
        name = cursor['name']
        original_frames, installed_frames = frames(originals/name, 24), frames(installed/name, 24)
        if name == 'watch':
            from watch_fidelity import compare, negative_controls
            assert len(original_frames)==len(installed_frames)==len(cursor['frames'])==3
            before = [Image.frombytes('RGBA',(24,24),frame['pixels'],'raw','BGRA') for frame in original_frames]
            after = [Image.frombytes('RGBA',(24,24),frame['pixels'],'raw','BGRA') for frame in installed_frames]
            phases = []
            for index,(original,actual) in enumerate(zip(original_frames,installed_frames)):
                for key in ('width','height','hotspot_x','hotspot_y','delay'):
                    assert original[key]==actual[key], (name,index,key)
                fidelity = compare(before[index],after[index],before)
                fidelity['negative_controls'] = negative_controls(before[index],after[index],before,after[(index+1)%3])
                images = check_representations(cursor,artwork,installed,index)
                for label,image in (('original',before[index]),('vector',after[index])):
                    Image.frombytes('RGBa',image.size,image.tobytes()).convert('RGBA').save(
                        artifacts/f'watch-{index+1}-{label}.png')
                images[-1].save(artifacts/f'watch-{index+1}-192.png')
                phases.append(dict(index=index,**fidelity,representations=len(images)))
            records.append(dict(name=name,original_sha256=hashlib.sha256((originals/name).read_bytes()).hexdigest(),
                reference_check='animated-color-field',frame_count=3,frames=phases,representations=33))
            continue
        assert len(original_frames) == len(installed_frames) == 1, name
        original, actual = original_frames[0], installed_frames[0]
        for key in ('width','height','hotspot_x','hotspot_y','delay'):
            assert actual[key] == original[key], (name,key)
        before = Image.frombytes('RGBA', (24,24), original['pixels'], 'raw', 'BGRA')
        after = Image.frombytes('RGBA', (24,24), actual['pixels'], 'raw', 'BGRA')
        fidelity = compare_original(before,after,name)
        if fidelity['reference_check'] == 'foreground-and-ink-regions':
            shifted = Image.new('RGBA',after.size)
            shifted.paste(after,(1,0))
            changed_ink = after.copy()
            palette = PALETTES.get(name)
            index = next(i for i,pixel in enumerate(before.getdata())
                if pixel[3] >= 128 and region(pixel,palette) == 0)
            x,y = index%24,index//24
            alpha = after.getpixel((x,y))[3]
            changed_ink.putpixel((x,y),(alpha,alpha,alpha,alpha))
            controls = [('translated',shifted),('ink-changed',changed_ink)]
            tinted_shadow = after.copy()
            tinted_shadow.putpixel((0,0),(9,9,9,9))
            controls.append(('shadow-tinted',tinted_shadow))
            if palette:
                recolored = after.copy()
                recolored.putdata([(*(round(value*.75) for value in pixel[:3]),pixel[3]) for pixel in after.getdata()])
                controls.append(('palette-changed',recolored))
            if 'solid_axis_anchors' in fidelity:
                faded = after.copy()
                faded.putpixel((6,10),(0,0,0,230))
                controls.append(('axis-opacity-changed',faded))
            if 'shade_anchors' in fidelity:
                tinted = after.copy()
                index = next(i for i,p in enumerate(before.getdata()) if p[3] == 255 and 20 <= p[0] <= 80)
                x,y = index%24,index//24
                value = after.getpixel((x,y))[0]+32
                tinted.putpixel((x,y),(value,value,value,255))
                controls.append(('crease-palette-changed',tinted))
            if 'menu_shade_anchors' in fidelity:
                tinted = after.copy()
                value = after.getpixel((14,19))[0]+32
                tinted.putpixel((14,19),(value,value,value,255))
                controls.append(('menu-palette-changed',tinted))
            if 'detail_shade_anchors' in fidelity:
                value = 85 if name == 'pirate' else 153
                index = next(i for i,pixel in enumerate(before.getdata()) if pixel == (value,value,value,255))
                tinted = after.copy()
                tinted.putpixel((index%24,index//24),(value+32,value+32,value+32,255))
                controls.append(('detail-shade-changed',tinted))
            if 'antialias_edge_anchors' in fidelity:
                tinted = after.copy()
                tinted.putpixel((10,17),(255,255,255,255))
                controls.append(('antialias-edge-tinted',tinted))
            for label,changed in controls:
                try:
                    compare_original(before,changed,name)
                except AssertionError:
                    pass
                else:
                    raise AssertionError((name,label,'Unfaithful design was accepted'))
            fidelity['negative_controls'] = [label for label,_ in controls]
        representations = check_representations(cursor,artwork,installed)
        for label,image in (('original',before),('vector',after)):
            # Xcursor channels are associated with alpha; PNG stores straight
            # channels. Avoid darkening antialiased edges in review previews.
            Image.frombytes('RGBa',image.size,image.tobytes()).convert('RGBA').save(
                artifacts/(name+'-'+label+'.png'))
        representations[-1].save(artifacts/(name+'-192.png'))
        records.append(dict(name=name,original_sha256=hashlib.sha256((originals/name).read_bytes()).hexdigest(),
            **fidelity,representations=len(representations)))
    report = dict(passed=True,cases=records,original_fallback_files=fallbacks,
        preserved_aliases=aliases,full_cursor_library_qualified=(fallbacks==0 and len(records)==57))
    (artifacts/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f"Faithful cursor reconstruction: {len(records)} designs; {fallbacks} original fallbacks preserved")
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--theme',type=Path,required=True)
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--source',type=Path)
    args = parser.parse_args()
    run(args.theme,args.artifacts,args.source)

