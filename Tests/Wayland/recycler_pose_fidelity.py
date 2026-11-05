#!/usr/bin/env python3
"""Preserve the three missing Recycler poses' ribbons, palette and fold shading."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageChops, ImageFilter, ImageOps
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, regional_error


POSES = tuple('recycler-'+str(i) for i in range(2,5))


def ribbons(image):
    alpha = image.getchannel('A')
    remaining = {(x,y) for y in range(image.height) for x in range(image.width)
        if alpha.getpixel((x,y)) > 127}
    result = []
    while remaining:
        queue = deque([remaining.pop()]); points = set(queue)
        while queue:
            x,y = queue.popleft()
            for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if point in remaining:
                    remaining.remove(point); points.add(point); queue.append(point)
        if len(points) > 100:
            result.append(points)
    assert len(result) == 3, 'The three ribbon arrows must remain separate'
    return sorted(result, key=lambda points:(min(y for x,y in points),min(x for x,y in points)))


def compare(original, low, high):
    assert original.size == low.size == (64,64) and high.size == (512,512)
    assert low.getchannel('A').getbbox() == original.getchannel('A').getbbox(), 'Pose footprint changed'
    before,after = original.getchannel('A'),low.getchannel('A')
    mass = lambda image: sum(value*count for value,count in enumerate(image.histogram()))/255
    overlap = mass(ImageChops.darker(before,after))/mass(ImageChops.lighter(before,after))
    assert overlap >= .93, ('Ribbon silhouettes changed',overlap)
    ratio = mass(after)/mass(before)
    assert abs(ratio-1) <= .04, ('Ribbon ink weight changed',ratio)
    expected,actual = ribbons(original),ribbons(low)
    regions = []
    for index,points in enumerate(expected):
        match = max(actual,key=lambda other:len(points & other))
        actual.remove(match)
        silhouette = len(points & match)/len(points | match)
        assert silhouette >= .90, ('Individual arrow changed',index,silhouette)
        mask = Image.new('L',low.size)
        mask.putdata([255 if (x,y) in points else 0 for y in range(64) for x in range(64)])
        mask = mask.filter(ImageFilter.MinFilter(3))
        interior = [(x,y) for y in range(64) for x in range(64) if mask.getpixel((x,y))==255]
        error = regional_error(original,low,interior)
        assert error['mean'] <= 10 and error['channel_mean_difference'] <= 8.5, ('Original palette changed',index,error)
        ordered = sorted(interior,key=lambda p:original.getpixel(p)[1]);count = len(ordered)//4
        tones = {}
        for name,region in (('shadow',ordered[:count]),('highlight',ordered[-count:])):
            tone = regional_error(original,low,region)
            # The native original uses 17-level color steps; retain each zone
            # within one step while replacing its dither with continuous light.
            assert tone['mean'] <= 12 and tone['channel_mean_difference'] <= 17, (index,name,tone)
            tones[name] = tone
        regions.append(dict(silhouette_overlap=silhouette,interior=error,tones=tones))
    assert_not_enlarged([low,high],'Recycler pose')
    return dict(alpha_overlap=overlap,alpha_area_ratio=ratio,ribbons=regions)


def run(artifacts, source=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/Workspace/Artwork.svg'
    art = Artwork(source); assert_curve_arguments(art.root)
    designs = {}; rejected = []
    lows = {name:art.render(name,64) for name in POSES}
    for index,name in enumerate(POSES):
        symbol = art.symbols[name]
        assert symbol.get('data-logical-size') == '64 64' and symbol.get('data-reconstructed') == 'true'
        assert symbol.get('data-file') == 'Resources/'+name+'.tiff'
        original,_ = artwork_original('recycler','pose-'+name[-1]);low,high = lows[name],art.render(name,512)
        designs[name] = compare(original,low,high)
        shifted = Image.new('RGBA',low.size);shifted.paste(low,(1,0))
        gray = ImageOps.grayscale(low).convert('RGBA');gray.putalpha(low.getchannel('A'))
        red,green,blue,alpha = low.split();blue_ribbon = Image.merge('RGBA',(red,blue,green,alpha))
        flat = Image.new('RGBA',low.size,(51,170,68));flat.putalpha(alpha)
        erased = low.copy()
        for point in ribbons(original)[0]:erased.putpixel(point,(0,0,0,0))
        mutations = [('translated',shifted,high),('mirrored',ImageOps.mirror(low),high),
            ('wrong-pose',lows[POSES[(index+1)%len(POSES)]],high),('gray',gray,high),
            ('blue',blue_ribbon,high),('flat-lighting',flat,high),('missing-arrow',erased,high)]
        mutations += [(method.name.lower()+'-enlargement',low,low.resize(high.size,method))
            for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS)]
        for label,changed,large in mutations:
            try: compare(original,changed,large)
            except AssertionError: rejected.append(name+'-'+label)
            else: raise AssertionError('Accepted changed Recycler pose: '+name+'-'+label)
    artifacts.mkdir(parents=True)
    result = dict(passed=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        designs=designs,rejected_mutations=rejected,native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Recycler poses: nine original ribbon silhouettes, 18 light/shadow zones and {len(rejected)} negative controls PASS')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True);parser.add_argument('--source',type=Path)
    args = parser.parse_args();run(args.artifacts,args.source)
