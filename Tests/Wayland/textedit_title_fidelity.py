#!/usr/bin/env python3
"""Preserve TextEdit's original italic title, spacing and layered shadow."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, assert_svg_representations


def letters(image):
    """Separate the eight light letter faces and the i's dot from their shadow."""
    pixels = image.load()
    remaining = {(x,y) for y in range(image.height) for x in range(image.width)
        if pixels[x,y][0] > 128 and pixels[x,y][3] > 128}
    groups = []
    while remaining:
        first = min(remaining);remaining.remove(first);todo = [first];points = {first}
        while todo:
            x,y = todo.pop()
            for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if point in remaining:
                    remaining.remove(point);points.add(point);todo.append(point)
        if len(points) > 10:groups.append(points)
    return sorted(groups, key=lambda points:min(x for x,y in points))


def compare(original, low, high, face, large_face):
    assert original.size == low.size == face.size == (232,56)
    assert high.size == large_face.size == (1856,448)
    pairs = list(zip(original.getdata(),low.getdata()))
    error = sum(abs(a[c]*a[3]-b[c]*b[3])/255 for a,b in pairs for c in range(3))/(232*56*3)
    alpha_error = sum(abs(a[3]-b[3]) for a,b in pairs)/(232*56)
    assert error <= 6 and alpha_error <= 9.5, ('Title face, palette or shadow changed',error,alpha_error)
    assert all(max(p[:3])-min(p[:3]) <= 1 for p in low.getdata()), 'The monochrome title changed color'
    assert all(abs(a-b) <= 1 for a,b in zip(original.getchannel('A').getbbox(),low.getchannel('A').getbbox())), 'Title footprint changed'
    before,after = letters(original),letters(low)
    assert len(before) == len(after) == 9, 'A letter, counter or i-dot is missing or joined'
    records = []
    for label,old,new in zip(('T','e','x','t','E','d','i-stem','i-dot','t'),before,after):
        ratio = len(new)/len(old)
        assert abs(ratio-1) <= .05, ('Letter weight changed',label,ratio)
        overlap = len(old & new)/len(old | new)
        assert overlap >= .86, ('Letter silhouette changed',label,overlap)
        delta = [sum(p[axis] for p in new)/len(new)-sum(p[axis] for p in old)/len(old) for axis in (0,1)]
        assert max(map(abs,delta)) <= .4, ('Letter spacing or baseline changed',label,delta)
        records.append(dict(letter=label,ink_ratio=ratio,overlap=overlap,center_delta=delta))
    shadow = []
    for x,y in ((20,49),(20,50),(20,51),(20,52),(25,30),(26,30),(27,30)):
        a,b = original.getpixel((x,y)),low.getpixel((x,y))
        assert abs(a[3]-b[3]) <= 20 and max(abs(a[c]-b[c]) for c in range(3)) <= 15, ('Soft shadow changed',(x,y),a,b)
        shadow.append(dict(point=[x,y],maximum_channel_difference=max(abs(a[c]-b[c]) for c in range(4))))
    for point in ((20,47),(20,48),(23,30),(24,30)):
        assert max(low.getpixel(point)[:3]) <= 32 and low.getpixel(point)[3] == 255, ('Dark extrusion changed',point)
    assert_not_enlarged([low,high],'TextEdit title')
    assert_not_enlarged([face,large_face],'Italic letter contours')
    return dict(premultiplied_rgb_mean_error=error,alpha_mean_error=alpha_error,letters=records,shadow_zones=shadow)


def run(artifacts, source=None, image=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/TextEdit/Artwork.svg'
    art = Artwork(source);assert_curve_arguments(art.root)
    symbol = art.symbols['EditTitle']
    assert symbol.get('data-reconstructed') == 'true' and symbol.get('data-logical-size') == '232 56'
    original,fixture = artwork_original('textedit','EditTitle')
    low,high = [art.render('EditTitle',size) for size in ((232,56),(1856,448))]
    face,large = [art.render('title-face',size) for size in ((232,56),(1856,448))]
    design = compare(original,low,high,face,large)
    if image:assert_svg_representations(art,'EditTitle',image,(232,56))
    shifted = Image.new('RGBA',low.size);shifted.paste(low,(1,0))
    opaque = low.copy();opaque.putalpha(255)
    flat = Image.new('RGBA',face.size,'white');flat.putalpha(face.getchannel('A'))
    mutations = [('shifted-title',shifted,high,face,large),('mirrored-title',ImageOps.mirror(low),high,face,large),
        ('opaque-background',opaque,high,face,large),('missing-shadow',flat,high,face,large)]
    for letter in 'TextEdi':
        node = art.symbols['title-glyph-'+letter];saved = dict(node.attrib);node.set('opacity','0');art.cache.clear()
        mutations.append(('missing-'+letter,art.render('EditTitle',(232,56)),high,face,large))
        node.attrib.clear();node.attrib.update(saved);art.cache.clear()
    node = art.symbols['title-face'][3];saved = node.get('transform');node.set('transform','translate(1 0) '+saved);art.cache.clear()
    mutations.append(('changed-word-spacing',art.render('EditTitle',(232,56)),high,face,large));node.set('transform',saved);art.cache.clear()
    for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
        mutations.append((method.name.lower()+'-enlargement',low,low.resize(high.size,method),face,large))
        mutations.append((method.name.lower()+'-letter-enlargement',low,high,face,face.resize(large.size,method)))
    rejected = []
    for name,candidate,big,letters_image,big_letters in mutations:
        try:compare(original,candidate,big,letters_image,big_letters)
        except AssertionError:rejected.append(name)
        else:raise AssertionError('Design mutation accepted: '+name)
    artifacts.mkdir(parents=True)
    low.save(artifacts/'EditTitle-232.png');high.save(artifacts/'EditTitle-1856.png')
    result = dict(passed=True,design=design,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],negative_controls=rejected,
        native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('TextEdit title fidelity: nine letter parts, seven shadow zones and %d negative controls PASS.' % len(rejected))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',required=True,type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--image',type=Path)
    args = parser.parse_args();run(args.artifacts,args.source,args.image)
