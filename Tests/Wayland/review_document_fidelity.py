#!/usr/bin/env python3
"""Preserve Review's paper frames, serif labels, purple gradient and torn edge."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, assert_svg_representations

LABELS = {
    'GIF': ((10,22), (22,27), (27,36)),
    'JPEG': ((4,12), (12,21), (21,30), (30,42)),
    'PNG': ((6,16), (16,28), (28,40)),
    'TIFF': ((4,16), (16,22), (22,32), (32,42)),
    'XPM': ((4,16), (16,25), (25,42)),
}
NAMES = ('GenericImage', *(label + 'Image' for label in LABELS), 'NotImageable')


def ink(image, left, right):
    return {(x,y): 255-image.getpixel((x,y))[0]
        for y in range(3,19) for x in range(left,right)}


def compare(original, low, high, name, lettering=None):
    assert original.size == low.size == (48,48) and high.size == (384,384)
    torn = name == 'NotImageable'
    label = name.removesuffix('Image') if name not in ('GenericImage', 'NotImageable') else None
    before, after = original.convert('RGBa'), low.convert('RGBa')
    error = sum(abs(a[c]-b[c]) for a,b in zip(before.getdata(),after.getdata()) for c in range(3))/(48*48*3)
    alpha_error = sum(abs(a[3]-b[3]) for a,b in zip(before.getdata(),after.getdata()))/(48*48)
    assert error <= (2 if torn else 5.1), ('Document composition changed',name,error)
    assert alpha_error <= (4 if torn else .2), ('Paper transparency changed',name,alpha_error)
    if torn:
        old = {p for p in ((x,y) for y in range(48) for x in range(48)) if original.getpixel(p)[3] > 100}
        new = {p for p in ((x,y) for y in range(48) for x in range(48)) if low.getpixel(p)[3] > 100}
        overlap = len(old & new)/len(old | new)
        assert overlap >= .98, ('Torn paper silhouette changed',overlap)
    else:
        overlap = 1
        for y in range(48):
            for x in range(48):
                if 18 <= x < 43 and 20 <= y < 44 or label and 3 <= x < 43 and 3 <= y < 19:
                    continue
                assert max(abs(a-b) for a,b in zip(original.getpixel((x,y)),low.getpixel((x,y)))) <= 1, \
                    ('Paper frame, shadow or paragraph gap changed',name,(x,y))
    tones = []
    for y in (20,24,28,32,36,40):
        # Avoid the torn edge while retaining the same gradient coordinate space.
        right = 20 if torn and y >= 36 else 24 if torn and y >= 32 else 29 if torn else 43
        points = [(x,yy) for yy in range(y,y+2) for x in range(18,right)]
        delta = [sum(low.getpixel(p)[c]-original.getpixel(p)[c] for p in points)/len(points) for c in range(3)]
        assert max(map(abs,delta)) <= 10, ('Gradient position or palette changed',name,y,delta)
        assert all(low.getpixel(p)[3] == 240 for p in points), ('Gradient opacity changed',name,y)
        tones.append(dict(row=y,mean_channel_delta=delta))
    characters = []
    if label:
        a,b = ink(original,3,43),ink(low,3,43)
        coverage = sum(min(a[p],b[p]) for p in a)/sum(max(a[p],b[p]) for p in a)
        assert coverage >= .78, ('Serif letter contours changed',label,coverage)
        for letter,(left,right) in zip(label,LABELS[label]):
            a,b = ink(original,left,right),ink(low,left,right)
            mass = sum(a.values()),sum(b.values())
            ratio = mass[1]/mass[0]
            center = [sum(p[axis]*b[p] for p in b)/mass[1]-sum(p[axis]*a[p] for p in a)/mass[0] for axis in (0,1)]
            assert abs(ratio-1) <= .12 and max(map(abs,center)) <= .4, ('Serif weight, spacing or baseline changed',label,letter,ratio,center)
            characters.append(dict(letter=letter,ink_ratio=ratio,center_delta=center))
        assert_not_enlarged(lettering,label+' serif contours')
    assert_not_enlarged([low,high],name)
    return dict(premultiplied_rgb_mean_error=error,alpha_mean_error=alpha_error,
        silhouette_overlap=overlap,gradient_zones=tones,characters=characters)


def run(artifacts, source=None, images=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/Review/Artwork.svg'
    art = Artwork(source); assert_curve_arguments(art.root)
    artifacts.mkdir(parents=True)
    records = []; negatives = []
    for name in NAMES:
        symbol = art.symbols[name]
        assert symbol.get('data-reconstructed') == 'true' and symbol.get('data-logical-size') == '48 48'
        original,fixture = artwork_original('review',name)
        low,high = [art.render(name,size) for size in (48,384)]
        label = name.removesuffix('Image') if name not in ('GenericImage','NotImageable') else None
        lettering = [art.render('review-label-'+label,size) for size in (48,384)] if label else None
        design = compare(original,low,high,name,lettering)
        if images: assert_svg_representations(art,name,images/(name+'.tiff'),(48,48))
        shifted = Image.new('RGBA',low.size); shifted.paste(low,(1,0))
        opaque = low.copy(); opaque.putalpha(255)
        r,g,b,a = low.split(); wrong = Image.merge('RGBA',(b,r,g,a))
        blank = low.copy(); blank.paste((255,255,255,240),(18,20,43,44))
        mutations = [('shifted',shifted,high,lettering), ('mirrored',ImageOps.mirror(low),high,lettering),
            ('opaque',opaque,high,lettering), ('wrong-palette',wrong,high,lettering), ('missing-gradient',blank,high,lettering)]
        if label:
            node = art.symbols['review-label-'+label]
            for index,glyph in enumerate(node):
                glyph.set('opacity','0'); art.cache.clear()
                mutations.append(('missing-letter-'+str(index),art.render(name,48),high,lettering))
                glyph.attrib.pop('opacity'); art.cache.clear()
        if name == 'NotImageable':
            mutations.append(('straight-edge',art.render('GenericImage',48),high,lettering))
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
            mutations.append((method.name.lower()+'-enlargement',low,low.resize(high.size,method),lettering))
            if label: mutations.append((method.name.lower()+'-letter-enlargement',low,high,[lettering[0],lettering[0].resize(lettering[1].size,method)]))
        rejected = []
        for mutation,candidate,big,letters in mutations:
            try: compare(original,candidate,big,name,letters)
            except AssertionError: rejected.append(mutation)
            else: raise AssertionError('Design mutation accepted: '+name+' '+mutation)
        low.save(artifacts/(name+'-48.png')); high.save(artifacts/(name+'-384.png'))
        records.append(dict(name=name,design=design,original_source_sha256=fixture['source_sha256'],negative_controls=rejected))
        negatives.extend(rejected)
    result = dict(passed=True,cases=records,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        gradient_zones=42,serif_characters=17,negative_controls=len(negatives),
        native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Review documents: seven designs, 17 serif characters, 42 gradient zones and %d negative controls PASS.' % len(negatives))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',required=True,type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--images',type=Path)
    args = parser.parse_args(); run(args.artifacts,args.source,args.images)
