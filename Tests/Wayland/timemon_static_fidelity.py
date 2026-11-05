#!/usr/bin/env python3
"""Preserve TimeMon's transparent startup rings and colored Info diagram."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image, ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, assert_svg_representations

SIZES = {'TM-app':48,'TM-info':50}
COLORS = ((255,0,0,255),(0,249,122,255),(255,204,229,255),(255,255,255,255))


def compare(name, original, low, high):
    size = SIZES[name]
    assert original.size == low.size == (size,size) and high.size == (size*8,)*2
    assert original.getbbox() == low.getbbox(), 'Ring bounds changed'
    a,b = [list(im.getchannel('A').tobytes()) for im in (original,low)]
    overlap = sum(min(x,y) for x,y in zip(a,b))/sum(max(x,y) for x,y in zip(a,b))
    error = sum(abs(x-y) for x,y in zip(original.convert('RGBa').tobytes(),low.convert('RGBa').tobytes()))/(size*size*4)
    zones = []
    if name == 'TM-app':
        assert overlap >= .84 and error <= 1.6, ('Transparent ring contours changed',overlap,error)
        assert all(r==g==b==0 for r,g,b,alpha in low.getdata() if alpha), 'Startup rings recolored'
        for point in ((0,23),(6,23),(12,23),(23,6),(23,12),(24,3),(24,18),(24,23)):
            assert abs(original.getpixel(point)[3]-low.getpixel(point)[3]) <= 15, ('Ring/axis weight changed',point)
        assert low.getpixel((24,24))[3] == low.getpixel((30,24))[3] == 0, 'Transparent counter filled'
    else:
        # The old Info image uses a binary alpha mask around antialiased RGB
        # edges. Continuous new edges are compared separately from its colors.
        assert overlap >= .96 and error <= 10, ('Info contours changed',overlap,error)
        for point in ((25,3),(25,18),(25,23)):
            assert original.getpixel(point) == low.getpixel(point) == (0,0,0,255), ('Info axis changed',point)
        for lower,upper in ((18.8,22),(12.8,16),(1.4,10.1)):
            for color in COLORS:
                points = [(x,y) for y in range(size) for x in range(size)
                    if lower < math.hypot(x+.5-25,y+.5-25) < upper and original.getpixel((x,y)) == color]
                assert points and all(low.getpixel(p) == color for p in points), ('Ring sector/palette changed',lower,color)
                zones.append(dict(radius=[lower,upper],rgba=color,exact_original_pixels=len(points)))
    assert_not_enlarged([low,high],name)
    return dict(weighted_alpha_overlap=overlap,premultiplied_mean_error=error,zones=zones)


def run(artifacts, source=None, images=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/TimeMon/Artwork.svg'
    art = Artwork(source);assert_curve_arguments(art.root)
    artifacts.mkdir(parents=True);records=[]
    for name,size in SIZES.items():
        original,fixture = artwork_original('timemon',name)
        low,high = [art.render(name,n) for n in (size,size*8)]
        design = compare(name,original,low,high)
        if images:assert_svg_representations(art,name,images/(name+'.tiff'),(size,size))
        shifted = Image.new('RGBA',low.size);shifted.paste(low,(1,0))
        opaque = low.copy();opaque.putalpha(255)
        mutations = [('shifted',shifted,high),('mirrored',ImageOps.mirror(low),high),('opaque',opaque,high)]
        node = art.symbols['timemon-rings'][-1];saved=node.get('d');node.set('d','M0 0');art.cache.clear()
        mutations.append(('missing-axis',art.render(name,size),high));node.set('d',saved);art.cache.clear()
        node = art.symbols['timemon-rings'];saved=node.get('stroke-width');node.set('stroke-width','.8');art.cache.clear()
        mutations.append(('lighter-rings',art.render(name,size),high));node.set('stroke-width',saved);art.cache.clear()
        node = art.symbols['timemon-rings'][1];saved=node.get('r');node.set('r','18.5');art.cache.clear()
        mutations.append(('changed-radius',art.render(name,size),high));node.set('r',saved);art.cache.clear()
        if name == 'TM-info':
            node=art.symbols['info-1-1'];saved=node.get('fill');node.set('fill','#00ff7f');art.cache.clear()
            mutations.append(('changed-green',art.render(name,size),high));node.set('fill',saved);art.cache.clear()
            saved=node.get('d');node.set('d','M0 0');art.cache.clear()
            mutations.append(('missing-sector',art.render(name,size),high));node.set('d',saved);art.cache.clear()
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
            mutations.append((method.name.lower()+'-enlargement',low,low.resize(high.size,method)))
        negatives=[]
        for label,candidate,big in mutations:
            try:compare(name,original,candidate,big)
            except AssertionError:negatives.append(label)
            else:raise AssertionError('TimeMon mutation accepted: '+name+' '+label)
        low.save(artifacts/(name+'-base.png'));high.save(artifacts/(name+'-high.png'))
        records.append(dict(name=name,design=design,negative_controls=negatives,original_source_sha256=fixture['source_sha256']))
    result = dict(passed=True,cases=records,negative_controls=sum(len(v['negative_controls']) for v in records),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('TimeMon static artwork: three rings, twelve exact color regions and %d negative controls PASS.'%result['negative_controls'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',required=True,type=Path)
    parser.add_argument('--source',type=Path);parser.add_argument('--images',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.images)
