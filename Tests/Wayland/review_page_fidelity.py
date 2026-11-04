#!/usr/bin/env python3
"""Preserve the four original Review page controls with real vector geometry."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageOps

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, assert_svg_representations

NAMES = ('PageUp','PageDown','PageUpH','PageDownH')


def compare(original, low, high, frame, arrow):
    assert original.size == low.size == (13,13) and high.size == (104,104)
    assert original.convert('RGBa').tobytes() == low.convert('RGBa').tobytes(), 'Page outline, arrow, palette or transparency changed'
    for frames,name in (([low,high],'Page control'),(frame,'Chamfered page outline'),(arrow,'Page triangle')):
        assert_not_enlarged(frames,name)


def run(artifacts, source=None, images=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/Review/Artwork.svg'
    art = Artwork(source); assert_curve_arguments(art.root)
    artifacts.mkdir(parents=True); records = []; negatives = []
    # The SVG root uses 48 points, while these shared definitions use 13 points.
    art.viewbox = '0 0 13 13'
    for name in NAMES:
        node = art.symbols[name]
        assert node.get('data-reconstructed') == 'true' and node.get('data-logical-size') == '13 13'
        original,fixture = artwork_original('review',name)
        low,high = [art.render(name,size) for size in (13,104)]
        frame = [art.render('review-page-frame',size) for size in (13,104)]
        arrow_name = 'review-page-highlight-arrow' if name.endswith('H') else 'review-page-arrow'
        arrow = [art.render(arrow_name,size) for size in (13,104)]
        compare(original,low,high,frame,arrow)
        if images: assert_svg_representations(art,name,images/(name+'.tiff'),(13,13))
        shifted = Image.new('RGBA',low.size); shifted.paste(low,(1,0))
        wrong = art.render(name.replace('Up','Down') if 'Up' in name else name.replace('Down','Up'),13)
        recolored = low.copy()
        for y in range(13):
            for x in range(13):
                r,g,b,a = recolored.getpixel((x,y))
                if a and r < 200: recolored.putpixel((x,y),(170,170,170,a))
        mutations = [('shifted',shifted,high,frame,arrow),('mirrored',ImageOps.mirror(low),high,frame,arrow),
            ('opposite-arrow',wrong,high,frame,arrow),('wrong-palette',recolored,high,frame,arrow)]
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
            mutations.extend([(method.name.lower()+'-enlargement',low,low.resize(high.size,method),frame,arrow),
                (method.name.lower()+'-frame-enlargement',low,high,[frame[0],frame[0].resize(frame[1].size,method)],arrow),
                (method.name.lower()+'-arrow-enlargement',low,high,frame,[arrow[0],arrow[0].resize(arrow[1].size,method)])])
        rejected = []
        for label,candidate,big,outline,triangle in mutations:
            try: compare(original,candidate,big,outline,triangle)
            except AssertionError: rejected.append(label)
            else: raise AssertionError('Design mutation accepted: '+name+' '+label)
        low.save(artifacts/(name+'-13.png')); high.save(artifacts/(name+'-104.png'))
        records.append(dict(name=name,base_pixels_identical=True,original_source_sha256=fixture['source_sha256'],negative_controls=rejected))
        negatives.extend(rejected)
    result = dict(passed=True,cases=records,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        negative_controls=len(negatives),native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Review page controls: four exact base-size matches and %d negative controls PASS.' % len(negatives))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',required=True,type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--images',type=Path)
    args = parser.parse_args(); run(args.artifacts,args.source,args.images)
