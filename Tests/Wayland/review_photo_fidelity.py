#!/usr/bin/env python3
"""Check the reconstructed photograph against Review's original RGB artwork."""
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image,ImageChops,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork,DENSITIES,backing_size
from artwork_reference import artwork_original,assert_not_enlarged

ZONES=((0,0,33,6),(0,6,11,11),(11,6,22,11),(22,6,33,11),
       (0,11,16,14),(17,11,33,14),(0,14,33,24))


def compare(original,actual):
    assert original.size==actual.size==(33,24)
    before,after=original.convert('RGB'),actual.convert('RGB');zones=[]
    for box in ZONES:
        a=list(before.crop(box).getdata());b=list(after.crop(box).getdata())
        difference=max(abs(sum(x[c]-y[c] for x,y in zip(a,b)))/len(a) for c in range(3))
        assert difference<=10,('Original photo palette changed',box,difference)
        zones.append(dict(box=box,maximum_mean_channel_difference=difference))
    error=sum(abs(a-b) for x,y in zip(before.getdata(),after.getdata()) for a,b in zip(x,y))/(33*24*3)
    assert error<=13,('Original photo composition changed',error)
    masks=[{(x,y) for y in range(11,14) for x in range(16)
        if all(v<t for v,t in zip(image.getpixel((x,y)),(70,75,65)))} for image in (before,after)]
    assert all(masks)
    overlap=len(masks[0]&masks[1])/len(masks[0]|masks[1])
    assert overlap>=.85,('Original headland silhouette changed',overlap)
    distance=max(min((x-u)**2+(y-v)**2 for u,v in masks[1-side])
        for side in (0,1) for x,y in masks[side])
    assert distance<=1,('Original coastline moved',distance)
    return dict(zones=zones,mean_absolute_channel_error=error,headland_overlap=overlap,
        maximum_headland_edge_distance=distance**.5)


def run(artifacts,repository=None):
    repository=repository or Path(__file__).resolve().parents[2]
    original,_=artwork_original('review','Review',repository);original=original.crop((7,7,40,31))
    folder=repository/'Applications/Artwork';metadata=json.loads((folder/'ReviewCoast.json').read_text())
    source=folder/'ReviewCoast.png';assert hashlib.sha256(source.read_bytes()).hexdigest()==metadata['source_sha256']
    with Image.open(source) as image:assert image.size==tuple(metadata['source_pixels']) and min(image.size)>=1024
    art=Artwork(folder/'ReviewScreen.svg');frames=[art.render('review-photograph',tuple(backing_size(p,d) for p in (33,24))) for d in DENSITIES[:5]]
    metrics=compare(original,frames[0]);assert_not_enlarged(frames,'Review photograph')
    controls=[('mirrored-coast',ImageOps.mirror(frames[0])),('missing-land',Image.new('RGB',(33,24),(85,119,170)))]
    for name,box,color in [('changed-sky',(0,0,33,6),(10,90,220)),('cyan-water',(0,14,33,24),(10,190,210)),('missing-clouds',(0,6,33,11),(30,65,130))]:
        candidate=frames[0].copy();candidate.paste(color,box);controls.append((name,candidate))
    candidate=frames[0].copy();candidate.paste((85,119,170),(0,11,16,14));controls.append(('removed-coastline',candidate))
    rejected=[]
    for name,candidate in controls:
        try:compare(original,candidate)
        except AssertionError:rejected.append(name)
        else:raise AssertionError('Accepted altered photograph: '+name)
    for name,method in [('nearest-enlargement',Image.Resampling.NEAREST),('lanczos-enlargement',Image.Resampling.LANCZOS)]:
        try:assert_not_enlarged([frames[0].resize(frame.size,method) for frame in frames],name)
        except AssertionError:rejected.append(name)
        else:raise AssertionError('Accepted enlarged photograph: '+name)
    artifacts.mkdir(parents=True);result=dict(passed=True,metrics=metrics,rejected_mutations=rejected,
        high_resolution_master_pixels=metadata['source_pixels'],original_photo_all_pixels_identical=False,
        native_qualified=False,full_package_lifecycle_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Review photograph: original palette/coastline, high-resolution master and',len(rejected),'negative controls PASS')
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,required=True);a=p.parse_args();run(a.artifacts)
