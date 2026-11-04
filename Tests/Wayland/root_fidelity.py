#!/usr/bin/env python3
"""Preserve the original root computer's housing, screen, stand and drives."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, regional_error


REGIONS = {
    'monitor': ((4,1,43,32), 3),
    'glass': ((10,7,38,27), 3),
    'stand': ((8,33,40,39), 12),
    'drives': ((1,40,46,47), 7),
}


def compare(original, low, high):
    assert original.size == low.size == (48,48) and high.size == (384,384)
    assert low.getchannel('A').getbbox() == original.getchannel('A').getbbox() == (0,0,47,48)
    mass = lambda image: sum(a*n for a,n in enumerate(image.getchannel('A').histogram()))/255
    assert abs(mass(low)/mass(original)-1) < .01, 'Computer silhouette changed'
    regions = {}
    for name,(box,limit) in REGIONS.items():
        left,top,right,bottom = box
        error = regional_error(original,low,((x,y) for y in range(top,bottom) for x in range(left,right)))
        assert error['mean'] <= limit, (name,'original shading or geometry changed',error)
        assert_not_enlarged([low.crop(box),high.crop(tuple(n*8 for n in box))], name)
        regions[name] = error
    points = [(x,29) for x in (37,38)]+[(x,43) for x in (4,5)]
    points += [(x,42) for x in range(32,43)]
    points += [(x,43) for x in (*range(32,36),*range(40,43))]
    points += [(x,36) for x in range(13,36)]
    points += [(x,38) for x in range(13,36)]
    maximum = max(abs(a-b) for p in points for a,b in zip(original.getpixel(p),low.getpixel(p)))
    assert maximum <= 1, ('Drive, indicator or stand detail changed',maximum)
    return dict(regions=regions,original_alpha_area=mass(original),reconstructed_alpha_area=mass(low),
        detail_anchors=len(points),maximum_detail_error=maximum)


def run(artifacts, source=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/Artwork/Root.svg'
    art = Artwork(source);assert_curve_arguments(art.root)
    original,_ = artwork_original('root','computer')
    low,high = art.render('root',48),art.render('root',384)
    design = compare(original,low,high)
    shifted = Image.new('RGBA',low.size);shifted.paste(low,(1,0))
    gray = ImageOps.grayscale(low).convert('RGBA');gray.putalpha(low.getchannel('A'))
    controls = [('translated',shifted,high),('desaturated',gray,high),('mirrored',ImageOps.mirror(low),high),
        ('enlarged-bitmap',low,low.resize(high.size,Image.Resampling.NEAREST))]
    for name,box,color in (('missing-drive',(32,42,43,43),(170,170,170,255)),
            ('missing-indicator',(37,29,39,30),(170,170,170,255)),
            ('missing-stand',(10,33,39,39),(170,170,170,255)),
            ('flat-glass',(10,7,38,27),(42,37,63,255))):
        changed = low.copy();changed.paste(color,box);controls.append((name,changed,high))
    rejected = []
    for name,changed,large in controls:
        try: compare(original,changed,large)
        except AssertionError: rejected.append(name)
        else: raise AssertionError('Accepted changed root computer: '+name)
    artifacts.mkdir(parents=True)
    result = dict(passed=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),design=design,
        rejected_mutations=rejected,native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Original root computer: four design regions and {len(rejected)} negative controls PASS')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--source',type=Path)
    args = parser.parse_args();run(args.artifacts,args.source)
