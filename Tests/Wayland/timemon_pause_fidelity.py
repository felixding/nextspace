#!/usr/bin/env python3
"""Preserve TimeMon's red stipple, round counter and diagonal pause slash."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_not_enlarged, assert_svg_representations


def compare(original, low, high):
    assert original.size == low.size == (48,48) and high.size == (384,384)
    a,b = [list(im.getchannel('A').tobytes()) for im in (original,low)]
    ratio = sum(b)/sum(a)
    overlap = sum(min(x,y) for x,y in zip(a,b))/sum(max(x,y) for x,y in zip(a,b))
    error = sum(abs(x-y) for x,y in zip(a,b))/len(a)
    assert abs(ratio-1) <= .05 and overlap >= .9 and error <= 8, ('Pause contours changed',ratio,overlap,error)
    material = []
    for y in range(48):
        for x in range(48):
            distance = ((x+.5-24)**2+(y+.5-24)**2)**.5
            if 17 <= distance <= 19:
                before, after = original.getpixel((x,y)), low.getpixel((x,y))
                assert max(abs(c-d) for c,d in zip(before,after)) <= 1, ('Red stipple changed',x,y,before,after)
                material.append((x,y))
    for point in ((16,18),(18,16),(30,32),(32,30)):
        assert low.getpixel(point)[3] == original.getpixel(point)[3] == 0, ('Pause counter filled',point)
    for point in ((18,29),(24,23),(29,18)):
        assert low.getpixel(point)[3] == original.getpixel(point)[3], ('Pause diagonal changed',point)
    assert_not_enlarged([low,high],'TimeMon pause mark')
    return dict(ink_ratio=ratio,weighted_overlap=overlap,alpha_mean_error=error,stipple_points=len(material))


def run(artifacts, source=None, image=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/TimeMon/Artwork.svg'
    art = Artwork(source); original, fixture = artwork_original('timemon','TimeMonP')
    low,high = [art.render('TimeMonP',size) for size in (48,384)]
    design = compare(original,low,high)
    if image: assert_svg_representations(art,'TimeMonP',image,(48,48))
    shifted = Image.new('RGBA',low.size); shifted.paste(low,(1,0))
    opaque = low.copy(); opaque.putalpha(255)
    r,g,b,a = low.split()
    mutations = [('shifted',shifted,high),('reversed-diagonal',ImageOps.mirror(low),high),
        ('opaque',opaque,high),('wrong-palette',Image.merge('RGBA',(b,g,r,a)),high)]
    node = art.symbols['pause-mark'][-1]; saved = node.get('d'); node.set('d','M0 0'); art.cache.clear()
    mutations.append(('missing-diagonal',art.render('TimeMonP',48),high));node.set('d',saved);art.cache.clear()
    for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
        mutations.append((method.name.lower()+'-enlargement',low,low.resize(high.size,method)))
    negatives = []
    for name,candidate,big in mutations:
        try: compare(original,candidate,big)
        except AssertionError: negatives.append(name)
        else: raise AssertionError('Pause mutation accepted: '+name)
    artifacts.mkdir(parents=True)
    low.save(artifacts/'TimeMonP-48.png');high.save(artifacts/'TimeMonP-384.png')
    result = dict(passed=True,design=design,negative_controls=negatives,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('TimeMon pause fidelity: original red stipple, circle/slash and seven negative controls PASS.')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',required=True,type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--image',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.image)
