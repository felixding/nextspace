#!/usr/bin/env python3
"""Protect TextEdit's original paper-and-pencil composition and real detail."""
import argparse
import json
from pathlib import Path
import sys
from PIL import Image, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, assert_svg_representations


def pigment(image):
    values = [min((max(p[:3])-min(p[:3]))/85, 1) for p in image.getdata()]
    mass = sum(values)
    assert mass > 0, 'The warm pencil material is missing'
    center = [sum(((i % 48 if axis == 0 else i // 48)+.5)*v
        for i,v in enumerate(values))/mass for axis in (0,1)]
    return values,mass,center


def lettering(original, low):
    # Read the line pattern from the unobstructed left margin. Exclude the
    # pencil and its antialiased neighborhood from the full-row comparison.
    chroma = Image.new('L', original.size)
    chroma.putdata([255 if max(p[:3])-min(p[:3]) > 15 else 0 for p in original.getdata()])
    material = chroma.filter(ImageFilter.MaxFilter(5))
    rows = [y for y in range(5,40) if sum((255-original.getpixel((x,y))[0])/255
        for x in range(6,15)) >= 1]
    assert rows == list(range(8,39,2)), 'Original paragraph reference changed'
    records = []
    for y in rows:
        points = [x for x in range(6,42) if not material.getpixel((x,y)) and
            not (y >= 32 and 15 <= x < 24)]
        before = [(255-original.getpixel((x,y))[0])/255 for x in points]
        after = [(255-low.getpixel((x,y))[0])/255 for x in points]
        old,new = sum(before),sum(after)
        assert old and new, ('Missing paragraph line',y)
        ratio = new/old
        assert abs(ratio-1) <= .15, ('Paragraph weight changed',y,ratio)
        old_shape,new_shape = [[v > .2 for v in values] for values in (before,after)]
        # Glyph antialiasing changes ink weights inside an unchanged word.
        # Measure position from its footprint, and check density separately.
        delta = sum(x*v for x,v in zip(points,new_shape))/sum(new_shape) - sum(x*v for x,v in zip(points,old_shape))/sum(old_shape)
        assert abs(delta) <= .25, ('Paragraph placement changed',y,delta)
        overlap = sum(a and b for a,b in zip(old_shape,new_shape))/sum(a or b for a,b in zip(old_shape,new_shape))
        assert overlap >= .96, ('Word footprints changed',y,overlap)
        records.append(dict(row=y,ink_ratio=ratio,center_delta=delta,footprint_overlap=overlap))
    for y in set(range(5,39))-set(rows):
        assert sum((255-low.getpixel((x,y))[0])/255 for x in range(6,15)) < .05, ('Extra paragraph line',y)
    return records


def compare(original, low, high, text_images, pencil_images):
    assert original.size == low.size == (48,48) and high.size == (384,384)
    pairs = list(zip(original.getdata(),low.getdata()))
    alpha_error = sum(abs(a[3]-b[3]) for a,b in pairs)/(48*48)
    alpha_overlap = sum(min(a[3],b[3]) for a,b in pairs)/sum(max(a[3],b[3]) for a,b in pairs)
    assert alpha_error <= .5 and alpha_overlap >= .995, 'Canvas, opacity or outer silhouette changed'
    frame = ((2,4),(2,20),(2,42),(3,2),(20,2),(42,2),(3,3),(4,30),
        (10,42),(40,40),(30,5),(43,25),(43,40),(20,43),(42,43),
        (44,25),(20,44),(45,25),(20,45),(3,44))
    for point in frame:
        assert low.getpixel(point) == original.getpixel(point), ('Paper frame or shadow changed',point)
    rgb_error = sum(abs(a[c]-b[c]) for a,b in pairs for c in range(3))/(48*48*3)
    assert rgb_error <= 9, ('The original palette or composition changed',rgb_error)
    first,mass,center = pigment(original);second,actual,position = pigment(low)
    assert abs(actual/mass-1) <= .1, 'Pencil material coverage changed'
    assert all(abs(a-b) <= .5 for a,b in zip(center,position)), 'Pencil proportions or material placement changed'
    overlap = sum(min(a,b) for a,b in zip(first,second))/sum(max(a,b) for a,b in zip(first,second))
    assert overlap >= .8, ('Pencil shape or shading changed',overlap)
    zones = []
    for x,y in ((40,8),(44,8),(47,10),(26,25),(24,29),(27,32),(31,29)):
        points = [(xx,yy) for yy in range(y-1,y+2) for xx in range(x-1,min(x+2,48))]
        before = [sum(original.getpixel(p)[c] for p in points)/len(points) for c in range(3)]
        after = [sum(low.getpixel(p)[c] for p in points)/len(points) for c in range(3)]
        error = max(abs(a-b) for a,b in zip(before,after))
        assert error <= 25, ('Pencil light, shadow or wood material changed',(x,y),error)
        zones.append(dict(center=[x,y],maximum_mean_channel_difference=error))
    for point in ((18,33),(17,35),(16,37)):
        assert max(low.getpixel(point)[:3]) <= 110, ('Graphite point changed',point)
    lines = lettering(original,low)
    assert_not_enlarged([low,high], 'TextEdit application icon')
    assert_not_enlarged(text_images, 'Miniature letter contours')
    assert_not_enlarged(pencil_images, 'Pencil geometry and material')
    return dict(rgb_mean_error=rgb_error,alpha_mean_error=alpha_error,
        alpha_overlap=alpha_overlap,pigment_overlap=overlap,pigment_ink_ratio=actual/mass,
        pigment_center_delta=[b-a for a,b in zip(center,position)],paragraph_lines=lines,material_zones=zones)


def run(artifacts, source=None, image=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/TextEdit/Artwork.svg'
    art = Artwork(source);assert_curve_arguments(art.root)
    original,fixture = artwork_original('textedit','Edit')
    low,high = [art.render('Edit',size) for size in (48,384)]
    text = [art.render('edit-page-microtext',size) for size in (48,384)]
    pencil = [art.render('edit-pencil-placement',size) for size in (48,384)]
    design = compare(original,low,high,text,pencil)
    if image:assert_svg_representations(art,'Edit',image,(48,48))
    shifted = Image.new('RGBA',low.size);shifted.paste(low,(1,0))
    opaque = low.copy();opaque.putalpha(255)
    blue = low.copy();r,g,b,a=blue.split();blue=Image.merge('RGBA',(b,g,r,a))
    gray = ImageOps.grayscale(low).convert('RGBA');gray.putalpha(low.getchannel('A'))
    mutations = [('shifted-artwork',shifted,high,text,pencil),('mirrored-artwork',ImageOps.mirror(low),high,text,pencil),
        ('opaque-background',opaque,high,text,pencil),('blue-pencil',blue,high,text,pencil),('desaturated-pencil',gray,high,text,pencil)]
    for name in ('edit-pencil-placement','edit-page-microtext','edit-paper'):
        node=art.symbols[name];saved=dict(node.attrib);node.set('opacity','0');art.cache.clear()
        mutations.append(('missing-'+name,art.render('Edit',48),high,text,pencil));node.attrib.clear();node.attrib.update(saved);art.cache.clear()
    for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
        mutations.append((method.name.lower()+'-enlargement',low,low.resize(high.size,method),text,pencil))
        mutations.append((method.name.lower()+'-text-enlargement',low,high,[text[0],text[0].resize(text[1].size,method)],pencil))
        mutations.append((method.name.lower()+'-pencil-enlargement',low,high,text,[pencil[0],pencil[0].resize(pencil[1].size,method)]))
    rejected = []
    for name,candidate,big,letters,material in mutations:
        try:compare(original,candidate,big,letters,material)
        except AssertionError:rejected.append(name)
        else:raise AssertionError('Design mutation accepted: '+name)
    artifacts.mkdir(parents=True)
    low.save(artifacts/'Edit-48.png');high.save(artifacts/'Edit-384.png')
    result = dict(passed=True,design=design,source_sha256=__import__('hashlib').sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],negative_controls=rejected,
        original_wording_recovered=False,miniature_lettering='Illustrative outlines preserve the original line and word footprints.',
        native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'TextEdit icon: 16 paragraph lines, 7 material zones and {len(rejected)} negative controls PASS')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,required=True);parser.add_argument('--source',type=Path);parser.add_argument('--image',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.image)
