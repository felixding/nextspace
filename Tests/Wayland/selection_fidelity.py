#!/usr/bin/env python3
"""Check the native original's card fan, hand, palette and rounded backdrop."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image,ImageChops,ImageFilter
from artwork_reference import assert_curve_arguments,assert_not_enlarged,assert_svg_representations,regional_error
from vector_art import Artwork,SVG

CARD_PATCHES = dict(pink=(5,32,8,35),purple=(3,25,5,28),blue=(4,18,8,21),
    cyan=(10,11,12,14),aqua=(17,7,20,11),green=(26,5,28,8),lime=(33,13,37,18),
    finger=(27,24,29,28),palm=(28,39,31,42),rear=(33,31,36,34),edge=(38,41,40,44))


def count(mask):return sum(mask.tobytes())//255


def check(art,originals):
    assert_curve_arguments(art.root)
    assert not any(e.tag.rsplit('}',1)[-1] in ('image','foreignObject') for e in art.root.iter())
    assert all('card-'+name in art.symbols for name in list(CARD_PATCHES)[:7])
    assert 'hand-face' in art.symbols and art.symbols['hand-face'].get('d')
    original=originals['MultipleSelection'];actual=art.render('MultipleSelection',48)
    assert actual.getchannel('A').getbbox()==original.getchannel('A').getbbox()==(0,0,47,48)
    mask=lambda image:image.getchannel('A').point(lambda v:255 if v>=120 else 0)
    before,after=mask(original),mask(actual)
    iou=count(ImageChops.darker(before,after))/count(ImageChops.lighter(before,after));assert iou>=.96,iou
    for a,b in [(before,after),(after,before)]:
        assert not count(ImageChops.subtract(a,b.filter(ImageFilter.MaxFilter(3)))), 'Outline moved beyond one original pixel'
    patches={}
    for name,(left,top,right,bottom) in CARD_PATCHES.items():
        error=regional_error(original,actual,[(x,y) for y in range(top,bottom) for x in range(left,right)])
        assert error['channel_mean_difference']<=13,(name,error)
        patches[name]=error
    def ink(image):
        pixels=image.load()
        # The hand overlaps the lower-right fan; measure the cards' ink away
        # from that separate shaded material.
        return sum(pixels[x,y][3]>=120 and max(pixels[x,y][:3])<100
            for y in range(32) for x in range(48) if y<20 or x<21)
    before_ink,after_ink=ink(original),ink(actual);assert abs(before_ink-after_ink)<=30,(before_ink,after_ink)
    assert max(actual.getchannel('A').getextrema())==240
    original=originals['SelectionHighlight'];actual=art.render('SelectionHighlight',(66,52))
    assert actual.getchannel('A').getextrema()==(255,255)
    white=lambda image:image.convert('RGB').getchannel('R').point(lambda v:255 if v>212 else 0)
    corner_changes=count(ImageChops.difference(white(original),white(actual)));assert corner_changes<=4,corner_changes
    for xy,color in [((0,0),170),((65,51),170),((20,20),255)]:assert actual.getpixel(xy)==(color,color,color,255)
    return dict(alpha_iou=iou,card_and_hand_regions=patches,original_ink_pixels=before_ink,
        reconstructed_ink_pixels=after_ink,rounded_backdrop_center_mask_differences=corner_changes)


def run(artifacts,images=None,repository=None):
    repository=repository or Path(__file__).resolve().parents[2]
    source=repository/'Applications/Artwork/Selection.svg';art=Artwork(source)
    reference=repository/'Tests/Wayland/artwork-originals/selection';manifest=json.loads((reference/'references.json').read_text());originals={}
    for name,case in manifest['cases'].items():
        assert hashlib.sha256((repository/case['source']).read_bytes()).hexdigest()==case['source_sha256']
        assert hashlib.sha256((reference/case['png']).read_bytes()).hexdigest()==case['png_sha256']
        for name_,h in case['equivalent_sources'].items():assert hashlib.sha256((repository/name_).read_bytes()).hexdigest()==h
        with Image.open(reference/case['png']) as image:originals[name]=image.convert('RGBA')
    result=check(art,originals);negatives=[]
    with tempfile.TemporaryDirectory(prefix='nextspace-selection-negative-') as temp:
        def reject(name,change):
            root=copy.deepcopy(art.root);nodes={e.get('id'):e for e in root.iter() if e.get('id')};change(root,nodes);p=Path(temp)/(name+'.svg');ET.ElementTree(root).write(p)
            try:check(Artwork(p),originals)
            except (AssertionError,ValueError):negatives.append(name)
            else:raise AssertionError('Accepted '+name)
        reject('missing-card',lambda r,n:n['card-blue'].set('id','missing-blue'))
        reject('front-card-palette',lambda r,n:n['lime'].find('{'+SVG+'}stop').set('stop-color','#ff7777'))
        reject('heavy-card-ink',lambda r,n:n['card-blue'].get('id') and next(e for e in r.iter() if e.get('stroke-width')=='.75').set('stroke-width','2'))
        reject('finger-pose',lambda r,n:n['hand-face'].set('transform','translate(3 0)'))
        reject('backdrop-radius',lambda r,n:n['highlight-white'].set('rx','3'))
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
            original=originals['MultipleSelection'];frames=[original.resize((n,n),method) for n in (48,60,72,84,96)]
            try:assert_not_enlarged(frames,'MultipleSelection')
            except AssertionError:negatives.append('bitmap-'+method.name.lower())
            else:raise AssertionError('Accepted bitmap enlargement')
    resources={}
    if images:
        for name,paths in {'MultipleSelection':['workspace/MultipleSelection.tiff','theme/common_MultipleSelection.tiff'],
                'SelectionHighlight':['workspace/hilite.tiff']}.items():
            for relative in paths:
                path=images/relative;assert_svg_representations(art,name,path,(48,48) if name=='MultipleSelection' else (66,52));resources[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    artifacts.mkdir(parents=True)
    result.update(passed=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),rejected_mutations=negatives,
        image_resources=resources,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Selection artwork: original shape, eleven palette regions and seven negative controls PASS')
    return result
