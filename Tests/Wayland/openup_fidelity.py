#!/usr/bin/env python3
"""Preserve OpenUp's closed carton, shaded document and opposite arrow designs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageOps

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, assert_svg_representations

NAMES = ('application','documents')
CARTON_ZONES = ((10,14,16,17),(20,12,26,15),(30,16,36,19),(8,20,11,26),
    (13,25,16,31),(18,29,21,35),(24,26,28,33),(31,23,35,30),(37,22,41,29))
PAPER_ZONES = ((15,12,19,14),(22,12,26,14),(29,12,33,14),(15,32,19,35),
    (22,32,26,35),(29,32,33,35),(29,18,33,20))


def feature(image, points, kind):
    values = {}
    for p in points:
        r,g,b,a = image.getpixel(p)
        values[p] = (max(0,r-max(g,b)) if kind == 'red' else max(0,min(r,g)-b))*a/255
    mass = sum(values.values()); assert mass > 0, ('Missing arrow color',kind)
    return mass,[sum(p[k]*w for p,w in values.items())/mass for k in (0,1)]


def compare(original, low, high, name, arrow, body):
    assert original.size == low.size == (48,48) and high.size == (384,384)
    assert all(abs(a-b) <= 1 for a,b in zip(original.getchannel('A').getbbox(),low.getchannel('A').getbbox())), 'Icon footprint changed'
    boxes = ((0,0,12,13),(36,0,48,13),(0,35,12,48),(36,35,48,48)) if name == 'application' else \
        ((0,0,13,14),(35,0,48,14),(0,33,13,48),(35,33,48,48))
    arrows = []
    for box in boxes:
        left,top,right,bottom = box
        points = [(x,y) for y in range(top,bottom) for x in range(left,right)]
        a,b = [{p for p in points if image.getpixel(p)[3] > 127} for image in (original,low)]
        overlap = len(a & b)/len(a | b)
        assert overlap >= .88, ('Arrow silhouette changed',name,box,overlap)
        colors = {}
        for kind in ('red','yellow'):
            mass,center = feature(original,points,kind); weight,position = feature(low,points,kind)
            ratio = weight/mass; delta = [b-a for a,b in zip(center,position)]
            assert abs(ratio-1) <= .10 and max(map(abs,delta)) <= .3, ('Arrow weight, direction or position changed',name,box,kind,ratio,delta)
            colors[kind] = dict(ink_ratio=ratio,center_delta=delta)
        arrows.append(dict(box=box,silhouette_overlap=overlap,colors=colors))
    zones = []
    for box in CARTON_ZONES if name == 'application' else PAPER_ZONES:
        left,top,right,bottom = box
        points = [(x,y) for y in range(top,bottom) for x in range(left,right)
            if name == 'application' or max(original.getpixel((x,y))[:3]) >= 160]
        delta = [sum(low.getpixel(p)[c]-original.getpixel(p)[c] for p in points)/len(points) for c in range(3)]
        assert max(map(abs,delta)) <= 10, ('Carton or paper shading changed',name,box,delta)
        zones.append(dict(box=box,mean_channel_delta=delta))
    rows = []
    if name == 'application':
        points = [(x,y) for y in range(9,43) for x in range(6,43) if 14 <= y < 34 or 13 <= x < 35]
        a,b = [{p for p in points if image.getpixel(p)[3] > 127} for image in (original,low)]
        overlap = len(a & b)/len(a | b)
        ratio = sum(low.getpixel(p)[3] for p in points)/sum(original.getpixel(p)[3] for p in points)
        assert overlap >= .985 and abs(ratio-1) <= .03, ('Closed carton proportions changed',overlap,ratio)
    else:
        overlap = 1
        for p in ((13,11),(24,11),(13,24),(33,24),(13,35),(14,36),(25,36),(33,36)):
            assert original.getpixel(p) == low.getpixel(p), ('Paper frame changed',p)
        for y in range(15,32,2):
            a,b = [[x for x in range(15,32) if max(image.getpixel((x,y))[:3]) < 160] for image in (original,low)]
            assert a == b, ('Miniature text footprint changed',y)
            ratio = sum(255-low.getpixel((x,y))[0] for x in a)/sum(255-original.getpixel((x,y))[0] for x in a)
            assert abs(ratio-1) <= .05, ('Miniature text weight changed',y,ratio)
            rows.append(dict(row=y,ink_pixels=len(a),ink_ratio=ratio))
    for frames,label in (([low,high],name),(arrow,name+' arrow geometry'),(body,name+' carton or lettering')):
        assert_not_enlarged(frames,label)
    return dict(arrows=arrows,color_zones=zones,body_silhouette_overlap=overlap,text_rows=rows)


def run(artifacts, source=None, images=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/OpenUp/Artwork.svg'
    art = Artwork(source); assert_curve_arguments(art.root); artifacts.mkdir(parents=True)
    records = []; negatives = []
    for name in NAMES:
        node = art.symbols[name]
        assert node.get('data-reconstructed') == 'true' and node.get('data-logical-size') == '48 48'
        original,fixture = artwork_original('openup',name)
        low,high = [art.render(name,size) for size in (48,384)]
        arrow_name = 'unpack-original-arrow' if name == 'application' else 'unpack-document-arrow'
        body_name = 'carton-original' if name == 'application' else 'archive-original-paragraph'
        arrow = [art.render(arrow_name,size) for size in (48,384)]
        body = [art.render(body_name,size) for size in (48,384)]
        design = compare(original,low,high,name,arrow,body)
        if images: assert_svg_representations(art,name,images/(name+'.tiff'),(48,48))
        shifted = Image.new('RGBA',low.size); shifted.paste(low,(1,0))
        opaque = low.copy(); opaque.putalpha(255)
        r,g,b,a = low.split(); palette = Image.merge('RGBA',(b,g,r,a))
        mutations = [('shifted',shifted,high,arrow,body),('mirrored',ImageOps.mirror(low),high,arrow,body),
            ('opaque',opaque,high,arrow,body),('wrong-palette',palette,high,arrow,body)]
        corners = [n for n in node if n.get('href') == '#'+arrow_name]
        assert len(corners) == 4
        for i,corner in enumerate(corners):
            corner.set('opacity','0'); art.cache.clear()
            mutations.append(('missing-arrow-'+str(i),art.render(name,48),high,arrow,body))
            corner.attrib.pop('opacity'); art.cache.clear()
        saved = [n.get('transform','') for n in corners]
        for n,transform in zip(corners,saved): n.set('transform',transform+' translate(12 15) rotate(180)')
        art.cache.clear(); mutations.append(('reversed-arrows',art.render(name,48),high,arrow,body))
        for n,transform in zip(corners,saved): n.set('transform',transform)
        art.cache.clear()
        hidden = [art.symbols['carton-original']] if name == 'application' else list(node)[:3]
        for n in hidden: n.set('opacity','0')
        art.cache.clear(); mutations.append(('missing-body',art.render(name,48),high,arrow,body))
        for n in hidden: n.attrib.pop('opacity')
        art.cache.clear()
        if name == 'documents':
            missing = low.copy(); missing.paste((230,235,238,255),(15,15,32,16))
            mutations.append(('missing-line',missing,high,arrow,body))
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
            mutations.extend([(method.name.lower()+'-enlargement',low,low.resize(high.size,method),arrow,body),
                (method.name.lower()+'-arrow-enlargement',low,high,[arrow[0],arrow[0].resize(arrow[1].size,method)],body),
                (method.name.lower()+'-body-enlargement',low,high,arrow,[body[0],body[0].resize(body[1].size,method)])])
        rejected = []
        for label,candidate,big,arrows,contents in mutations:
            try: compare(original,candidate,big,name,arrows,contents)
            except AssertionError: rejected.append(label)
            else: raise AssertionError('Design mutation accepted: '+name+' '+label)
        low.save(artifacts/(name+'-48.png')); high.save(artifacts/(name+'-384.png'))
        records.append(dict(name=name,design=design,original_source_sha256=fixture['source_sha256'],negative_controls=rejected)); negatives.extend(rejected)
    result = dict(passed=True,cases=records,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        arrows=8,arrow_color_features=16,color_zones=16,text_rows=9,negative_controls=len(negatives),
        miniature_wording_recovered=False,narrow_logo_qualified=False,native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('OpenUp artwork: eight arrows, 16 color zones, nine text rows and %d negative controls PASS.' % len(negatives))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',required=True,type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--images',type=Path)
    args = parser.parse_args(); run(args.artifacts,args.source,args.images)
