"""Check the overlapping Screen panels against the device-selected original."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image, ImageOps
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import assert_not_enlarged, assert_svg_representations, preferences_original


def compare(original, actual, higher):
    assert original.size == actual.size == (60,48) and higher.size == (480,384)
    assert_not_enlarged([actual,higher], 'Screen')
    points = [(x,y) for y in range(48) for x in range(60)]
    old, new = original.load(), actual.load()
    foreground = lambda pixels: {p for p in points if pixels[p][3]>=128}
    outline = len(foreground(old)^foreground(new))
    assert outline<=4, ('Screen panel outline changed',outline)
    def shape(pixels):
        area = sum(pixels[p][3]/255 for p in points)
        center = [sum(p[i]*pixels[p][3]/255 for p in points)/area for i in (0,1)]
        return area,center
    area,center = shape(old); new_area,new_center = shape(new)
    assert abs(area-new_area)<=2 and max(abs(a-b) for a,b in zip(center,new_center))<=.1, 'Screen proportions or overlap changed'
    black,white = set(),set()
    regions = defaultdict(list)
    glass = []
    for panel,(ox,oy) in enumerate(((1,0),(11,9))):
        for u,v in [(u,6) for u in range(6,41)]+[(6,v) for v in range(7,32)]:
            p = u+ox,v+oy
            if old[p]==(0,0,0,255): black.add(p)
        for u,v in [(41,v) for v in range(7,33)]+[(u,32) for u in range(7,42)]:
            p = u+ox,v+oy
            if old[p]==(255,255,255,255): white.add(p)
        for v in range(2,36):
            for u in range(2,45):
                p = u+ox,v+oy
                if panel==0 and p[0]>=11 and p[1]>=9: continue
                if old[p][3]!=255: continue
                if 7<=u<41 and 7<=v<32:
                    glass.append(p)
                    regions['glass',panel,(u-7)//4,(v-7)//4].append(p)
                elif not (6<=u<=41 and 6<=v<=32 or 38<=u<=41 and 33<=v<=35 or v<4 and (u<4 or u>42)):
                    regions['bezel',panel,u//4,v//4].append(p)
    assert len(black)==120 and len(white)==69
    assert all(new[p]==old[p] for p in black|white), 'Screen bevel or aperture borders changed'
    indicator = lambda pixels: {p for p in points if pixels[p][0]<80 and pixels[p][1]>200 and pixels[p][3]>=128}
    lights = indicator(old)
    assert len(lights)==2 and indicator(new)==lights and all(new[p]==old[p] for p in lights), 'Screen power indicator changed'
    opaque = [p for p in points if old[p][3]==new[p][3]==255]
    differences = [abs(a-b) for p in opaque for a,b in zip(old[p][:3],new[p][:3])]
    assert max(differences)<=34 and sum(differences)/len(differences)<=8.5, 'Screen palette changed'
    region_errors = []
    for key,patch in regions.items():
        if len(patch)<12: continue
        delta = max(abs(sum(old[p][c] for p in patch)-sum(new[p][c] for p in patch))/len(patch) for c in range(3))
        region_errors.append(delta)
        assert delta<=8.5, ('Screen shading or glow changed',key,delta)
    # The original has coarse ordered color dithering. Genuine backing-density
    # gradients must not redraw its enlarged color cells inside the glass.
    pixels = higher.load(); smoothness = 0
    for y in range(17*8,40*8-1):
        for x in range(19*8,51*8-1):
            for dx,dy in ((1,0),(0,1)):
                smoothness = max(smoothness,*(abs(a-b) for a,b in zip(pixels[x,y][:3],pixels[x+dx,y+dy][:3])))
    assert smoothness<=3, ('Screen glass retains enlarged dither cells',smoothness)
    return dict(outline_threshold_differences=outline,original_alpha_area=area,candidate_alpha_area=new_area,
        black_border_anchors=len(black),white_border_anchors=len(white),exact_indicator_pixels=len(lights),
        maximum_opaque_color_difference=max(differences),mean_opaque_color_difference=sum(differences)/len(differences),
        color_regions=len(region_errors),maximum_region_mean_difference=max(region_errors),
        maximum_high_density_glass_neighbor_difference=smoothness)


def run(artifacts, source=None, image=None):
    repository = Path(__file__).resolve().parents[2]
    source = source or repository/'Applications/Preferences/Artwork.svg'
    original,fixture = preferences_original('Screen',repository)
    artwork = Artwork(source)
    if image: assert_svg_representations(artwork,'Screen',image,(60,48))
    actual = artwork.render('Screen',(60,48)); higher = artwork.render('Screen',(480,384))
    result = compare(original,actual,higher)
    shifted = Image.new('RGBA',actual.size); shifted.paste(actual,(1,0))
    gray = ImageOps.grayscale(actual).convert('RGBA'); gray.putalpha(actual.getchannel('A'))
    flat = actual.copy(); dark = actual.copy()
    for y in range(16,41):
        for x in range(18,52): flat.putpixel((x,y),(64,55,93,255))
    for y in range(11,15):
        for x in range(15,52):
            p=dark.getpixel((x,y));dark.putpixel((x,y),(*(round(c*.8) for c in p[:3]),p[3]))
    light = actual.copy(); moved = actual.copy()
    for x in (50,51): light.putpixel((x,43),(136,136,136,255));moved.putpixel((x,43),(136,136,136,255))
    for x in (51,52): moved.putpixel((x,43),(0,255,34,255))
    missing = actual.copy()
    for y in range(10,47):
        for x in range(12,58): missing.putpixel((x,y),(0,0,0,0))
    traced = higher.copy(); enlarged = original.resize(higher.size,Image.Resampling.NEAREST)
    traced.paste(enlarged.crop((18*8,16*8,52*8,41*8)),(18*8,16*8))
    controls = [('translated',shifted,higher),('desaturated',gray,higher),('flat-glass',flat,higher),
        ('bezel-darkened',dark,higher),('indicator-removed',light,higher),('indicator-moved',moved,higher),
        ('front-panel-missing',missing,higher),('traced-dither',actual,traced),
        ('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),
        ('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))]
    rejected = []
    for name,modified,large in controls:
        try: compare(original,modified,large)
        except AssertionError: rejected.append(name)
        else: raise AssertionError(('Unfaithful Screen design accepted',name))
    result.update(passed=True,rejected_mutations=rejected,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],submitted_image_verified=image is not None,native_density_qualification=False)
    artifacts.mkdir(parents=True)
    actual.save(artifacts/'candidate-100.png');higher.save(artifacts/'candidate-800.png')
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,required=True)
    p.add_argument('--source',type=Path);p.add_argument('--image',type=Path)
    args=p.parse_args();run(args.artifacts,args.source,args.image)
