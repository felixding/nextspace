#!/usr/bin/env python3
"""Preserve Recycler's original occupied bounds when importing NeXTSpirit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from nextspirit_art import NextSpiritArtwork, fit_source
from artwork_reference import artwork_original


def area(image):
    return sum(a*n for a,n in enumerate(image.getchannel('A').histogram()))/255


def source_placement(master,padded,bounds,logical=(64,64)):
    cropped = master.crop(master.getchannel('A').getbbox())
    box = padded.getchannel('A').getbbox();copied = padded.crop(box)
    assert copied.size == cropped.size and copied.tobytes() == cropped.tobytes(), 'Artist pixels were modified'
    pixel = [points/count for points,count in zip(logical,padded.size)]
    actual = [(box[axis]+box[axis+2])/2*pixel[axis] for axis in (0,1)]
    expected = [(bounds[axis]+bounds[axis+2])/2 for axis in (0,1)]
    assert all(abs(a-b)<=step*.51 for a,b,step in zip(actual,expected,pixel)), 'Artist master is off-center'
    return dict(source_size=cropped.size,source_center_logical=actual,original_center_logical=expected)


def compare(original,actual):
    assert actual.size == original.size == (64,64)
    expected = original.getchannel('A').getbbox()
    assert actual.getchannel('A').getbbox() == expected, 'Recycler footprint changed'
    assert abs(area(actual)/area(original)-1) <= .15, 'Recycler visible area changed'
    return dict(bounds=expected,original_alpha_area=area(original),imported_alpha_area=area(actual))


def run(artifacts,pack=None):
    repo = Path(__file__).resolve().parents[2]
    manifest_path = repo/'Applications/Artwork/NextSpirit.json';manifest = json.loads(manifest_path.read_text())
    art = NextSpiritArtwork(pack,'workspace_icons') if pack is not None else None
    cases = {};rejected = [];preserved = []
    for name,reference in (('RecyclerEmpty','empty'),('RecyclerFull','full')):
        original,_ = artwork_original('recycler',reference)
        entry = manifest['workspace_icons'][name]
        assert entry['logical'] == [64,64] and entry['content_bounds'] == list(original.getchannel('A').getbbox())
        if name == 'RecyclerEmpty':
            pose,_ = artwork_original('recycler','pose-1')
            assert original.getchannel('A').tobytes() == pose.getchannel('A').tobytes(), 'First pose has a different silhouette'
            assert entry['targets']['workspace'] == ['recycler.tiff','recycler-1.tiff']
        low = art.render(name,64) if art else original
        cases[name] = compare(original,low)
        shifted = Image.new('RGBA',low.size);shifted.paste(low,(2,0))
        full = Image.new('RGBA',low.size,(0,255,0,255))
        for label,changed in (('translated',shifted),('full-canvas',full)):
            try:compare(original,changed)
            except AssertionError:rejected.append(name+'-'+label)
            else:raise AssertionError('Accepted changed Recycler footprint')
        if art:
            with Image.open(pack/entry['source']) as source:
                source.size = (1024,1024);source.load();raw = source.convert('RGBA')
            cropped = raw.crop(raw.getchannel('A').getbbox());padded = art.layout_layers[name]
            placement = source_placement(raw,padded,entry['content_bounds'])
            for size in (64,80,96,112,128):
                actual = art.render(name,size);factor = size/64
                box = actual.getchannel('A').getbbox();expected = entry['content_bounds']
                assert all(abs(value/factor-target)<=1 for value,target in zip(box,expected)),(name,size,box)
                preserved.append(dict(name=name,size=size,bounds=box,**placement))
    sample = Image.new('RGBA',(101,97));sample.paste((18,220,90,255),(3,5,96,91))
    for label,bounds in (('negative',(-1,9,56,58)),('outside',(7,9,65,58)),('empty',(7,9,7,58)),('non-finite',(7,float('nan'),56,58))):
        try:fit_source(sample,bounds,(64,64))
        except ValueError:rejected.append(label)
        else:raise AssertionError('Accepted invalid icon bounds: '+label)
    fitted = fit_source(sample,(7,9,56,58),(64,64))
    source_placement(sample,fitted,(7,9,56,58))
    biased = Image.new('RGBA',fitted.size);biased.paste(fitted,(2,0))
    try:source_placement(sample,biased,(7,9,56,58))
    except AssertionError:rejected.append('off-center-padding')
    else:raise AssertionError('Accepted biased source padding')
    artifacts.mkdir(parents=True)
    result = dict(passed=True,cases=cases,rejected_mutations=rejected,source_pixel_preservation=preserved,
        source_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Recycler footprint: two original layouts, {len(rejected)} negative controls and {len(preserved)} source-preserving frames PASS')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True);parser.add_argument('--pack',type=Path)
    args = parser.parse_args();run(args.artifacts,args.pack)
