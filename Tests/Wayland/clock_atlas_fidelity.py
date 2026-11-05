#!/usr/bin/env python3
"""Keep the clock's original lettering, palette, sprite packing and tile shape."""
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image, ImageOps
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Packaging/Sources'))
from vector_art import Artwork, DENSITIES, backing_size
from artwork_reference import assert_not_enlarged, assert_svg_representations, assert_vector_geometry


COLORS = ((255,255,255,255), (0,0,0,255), (34,36,75,255),
          (85,85,85,255), (170,170,170,255))
YEARS = ((12,66,6,6),(0,54,2,6),(2,54,5,6),(7,54,5,6),(12,54,6,6),
         (0,60,5,6),(5,60,6,6),(11,60,5,6),(0,66,6,6),(6,66,6,6))
SMALL_DATES = ((65,31,8,17),(73,31,9,17),(82,31,9,17),(90,31,10,17),
               (100,31,9,17),(108,31,10,17),(118,31,9,17),(126,31,10,17),
               (135,31,10,17),(144,31,10,17))
TIMES = ((150,13,9,11),(83,13,4,11),(87,13,8,11),(95,13,8,11),
         (103,13,8,11),(111,13,7,11),(118,13,8,11),(126,13,7,11),
         (133,13,9,11),(142,13,8,11),(159,13,3,11),
         (162,18,13,6),(175,18,12,6))


def ink(image, green=False, background=255):
    channel = image.convert('RGB').getchannel('G' if green else 'R')
    return [max(0,min(1,(v-36)/219 if green else (background-v)/background))
            for v in channel.getdata()]


def geometry(original, actual, green=False, background=255):
    before,after=ink(original,green,background),ink(actual,green,background)
    width=original.width;points=[(i%width,i//width) for i in range(len(before))]
    masks=[{p for p,v in zip(points,row) if v>=.5} for row in (before,after)]
    assert all(masks) and all(sum(row)>0 for row in (before,after))
    centers=[[sum(p[axis]*v for p,v in zip(points,row))/sum(row) for axis in (0,1)]
             for row in (before,after)]
    distance=max(min((x-u)**2+(y-v)**2 for u,v in masks[1-side])
                 for side in (0,1) for x,y in masks[side])
    return dict(overlap=len(masks[0]&masks[1])/len(masks[0]|masks[1]),
        ink_mass_ratio=sum(after)/sum(before),
        center_distance=math.dist(*centers),maximum_mask_distance=math.sqrt(distance),
        mean_squared_ink_error=sum((a-b)**2 for a,b in zip(before,after))/len(before))


def compare(original, actual):
    assert original.size==actual.size==(255,80)
    # The clock face and bevels have no lettering or photographic ambiguity.
    before=list(original.crop((191,0,255,64)).getdata())
    after=list(actual.crop((191,0,255,64)).getdata())
    for color in COLORS:
        assert [p==color for p in before]==[p==color for p in after],('Default clock tile changed',color)
    records=[]
    for kind,x,width,start,count in (('weekday',0,19,9,7),('month',20,19,8,12),('italic',40,22,8,12)):
        for index in range(count):
            y=start+index*6;box=(x,y,x+width,y+6)
            metrics=geometry(original.crop(box),actual.crop(box))
            if kind!='italic':
                assert metrics['overlap']==1,('Original upright lettering changed',kind,index,metrics)
                assert .98<=metrics['ink_mass_ratio']<=1.10 and metrics['center_distance']<=.25
            else:
                # Five-pixel italic strokes have quantized old antialiasing.
                # Allow adjacent edge pixels while preserving weight and registration.
                assert metrics['overlap']>=.8-1e-9 and metrics['maximum_mask_distance']<=math.sqrt(2)
                assert .875<=metrics['ink_mass_ratio']<=1.10 and metrics['center_distance']<=.6
                assert metrics['mean_squared_ink_error']<=.051
            records.append(dict(kind=kind,index=index+1,**metrics))
    for index in range(10):
        box=(64+index*12,49,76+index*12,66)
        metrics=geometry(original.crop(box),actual.crop(box))
        assert metrics['overlap']>=.95 and metrics['mean_squared_ink_error']<=.013,('Date outline changed',index,metrics)
    for name,boxes,background,overlap in (('year',YEARS,170,.8),('small date',SMALL_DATES,255,.78)):
        for index,(x,y,width,height) in enumerate(boxes):
            box=(x,y,x+width,y+height)
            metrics=geometry(original.crop(box),actual.crop(box),background=background)
            assert metrics['overlap']>=overlap and metrics['maximum_mask_distance']<=math.sqrt(2),(name,index,metrics)
            assert .8<=metrics['ink_mass_ratio']<=1.2 and metrics['center_distance']<=.5,(name,index,metrics)
    for x,y,width,height in TIMES:
        box=(x,y,x+width,y+height);metrics=geometry(original.crop(box),actual.crop(box),green=True)
        assert metrics['overlap']>=.84 and metrics['maximum_mask_distance']<=math.sqrt(2),('Time outline changed',box,metrics)
        assert .80<=metrics['ink_mass_ratio']<=1.20 and metrics['center_distance']<=.5
    return records


def run(artifacts,repository=None,images=None):
    repository=repository or Path(__file__).resolve().parents[2]
    fixture=repository/'Tests/Wayland/artwork-originals/clock-atlas'
    reference=json.loads((fixture/'reference.json').read_text())
    art=Artwork(repository/'Frameworks/DesktopKit/Artwork.svg');assert_vector_geometry(art.root)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();cases=[];english=None
    for language,item in reference['cases'].items():
        assert sha(repository/item['source'])==item['source_sha256']
        assert sha(fixture/item['png'])==item['png_sha256']
        with Image.open(fixture/item['png']) as p:original=p.convert('RGBA')
        frames=[art.render('clockbits-'+language,(backing_size(255,d),backing_size(80,d))) for d in DENSITIES[:5]]
        metrics=compare(original,frames[0]);assert_not_enlarged(frames,language+' clock atlas')
        if images:assert_svg_representations(art,'clockbits-'+language,images/(language+'.lproj/clockbits.tiff'),(255,80))
        cases.append(dict(language=language,words=metrics))
        if language=='English':english=original,frames
    original,frames=english;controls=[]
    for name,item in reference['rejected_substitute_font_controls'].items():
        assert sha(fixture/item['png'])==item['png_sha256'];candidate=frames[0].copy()
        with Image.open(fixture/item['png']) as p:candidate.paste(p.convert('RGBA'),tuple(item['box'][:2]))
        controls.append((name,candidate))
    candidate=frames[0].copy();candidate.paste((34,36,90,255),(196,5,249,21));controls.append(('display-palette',candidate))
    candidate=frames[0].copy();candidate.paste((85,85,85,255),(205,24,206,51));controls.append(('paper-face-inset',candidate))
    candidate=frames[0].copy();candidate.paste((255,255,255,255),(0,10,1,15));controls.append(('missing-letter-stem',candidate))
    candidate=frames[0].copy();candidate.paste(ImageOps.mirror(candidate.crop((191,0,255,64))),(191,0));controls.append(('mirrored-tile',candidate))
    candidate=frames[0].copy();candidate.paste(candidate.crop((12,66,18,72)),(0,66));controls.append(('wrong-year-digit',candidate))
    rejected=[]
    for name,candidate in controls:
        try:compare(original,candidate)
        except AssertionError:rejected.append(name)
        else:raise AssertionError('Accepted altered clock artwork: '+name)
    for name,method in [('nearest-enlargement',Image.Resampling.NEAREST),('lanczos-enlargement',Image.Resampling.LANCZOS)]:
        try:assert_not_enlarged([frames[0].resize(p.size,method) for p in frames],name)
        except AssertionError:rejected.append(name)
        else:raise AssertionError('Accepted enlarged clock artwork: '+name)
    artifacts.mkdir(parents=True);result=dict(passed=True,locales=cases,rejected_mutations=rejected,
        original_upright_word_masks_identical=190,default_tile_flat_color_masks_identical=True,
        all_original_pixels_identical=False,submitted_images_verified=images is not None,
        native_rendering_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Clock atlas:',len(cases),'original locales, 190 exact upright word masks and',len(rejected),'negative controls PASS')
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--images',type=Path);a=p.parse_args();run(a.artifacts,images=a.images)
