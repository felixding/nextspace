#!/usr/bin/env python3
"""Preserve TextEdit's document frames, colored paragraphs and abstract inset."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, assert_svg_representations


def rows(image, name):
    result = {}
    for y in range(7,40):
        if name == 'rtfd' and 26 <= y <= 36:continue
        points = [(x,y) for x in range(7,42) if min(image.getpixel((x,y))[:3]) < 220]
        if points:result[y] = points
    return result


def compare(original, low, high, name, lettering, inset):
    assert original.size == low.size == (48,48) and high.size == (384,384)
    before,after = rows(original,name),rows(low,name)
    assert len(before) == dict(text=16,rtf=14,rtfd=9)[name] and before.keys() == after.keys(), 'Paragraph line pattern changed'
    records = [];occupied = set()
    for y,points in before.items():
        assert points == after[y], ('Word footprints changed',name,y)
        occupied.update(points)
        old = [original.getpixel(p) for p in points];new = [low.getpixel(p) for p in points]
        ratio = sum(255-min(p[:3]) for p in new)/sum(255-min(p[:3]) for p in old)
        assert abs(ratio-1) <= .05, ('Miniature type weight changed',name,y,ratio)
        color = [sum(b[c]-a[c] for a,b in zip(old,new))/len(points) for c in range(3)]
        assert max(map(abs,color)) <= 15, ('Paragraph palette or heading hierarchy changed',name,y,color)
        records.append(dict(row=y,word_pixels=len(points),ink_ratio=ratio,mean_channel_delta=color))
    zones = []
    if name == 'rtfd':
        for y in (27,30,33):
            for x in (10,15,20):
                points = [(xx,yy) for yy in range(y,y+3) for xx in range(x,x+5)]
                color = [sum(low.getpixel(p)[c]-original.getpixel(p)[c] for p in points)/len(points) for c in range(3)]
                assert max(map(abs,color)) <= 20, ('Inset palette or contours changed',(x,y),color)
                zones.append(dict(origin=[x,y],mean_channel_delta=color))
        occupied.update((x,y) for y in range(27,36) for x in range(10,25))
        assert_not_enlarged(inset,'RTFD inset geometry')
    for y in range(48):
        for x in range(48):
            if (x,y) not in occupied:
                assert max(abs(a-b) for a,b in zip(original.getpixel((x,y)),low.getpixel((x,y)))) <= 1, ('Paper, frame, alpha, shadow or paragraph gap changed',name,(x,y))
    error = sum(abs(a[c]-b[c]) for a,b in zip(original.getdata(),low.getdata()) for c in range(4))/(48*48*4)
    assert error <= 2, ('Overall document composition changed',name,error)
    assert_not_enlarged([low,high],name+' document')
    assert_not_enlarged(lettering,name+' miniature letter contours')
    return dict(mean_channel_error=error,lines=records,inset_zones=zones)


def run(artifacts, source=None, images=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/TextEdit/Artwork.svg'
    art = Artwork(source);assert_curve_arguments(art.root);results = [];negative = []
    for name in ('text','rtf','rtfd'):
        symbol = art.symbols[name]
        assert symbol.get('data-reconstructed') == 'true' and symbol.get('data-logical-size') == '48 48'
        original,fixture = artwork_original('textedit',name)
        low,high = [art.render(name,size) for size in (48,384)]
        # Paragraph and inset definitions use the same 48-point coordinate space.
        art.viewbox = '0 0 48 48'
        letters = [art.render('doc-'+name+'-paragraph',size) for size in (48,384)]
        inset = [art.render('doc-inset',size) for size in (48,384)] if name == 'rtfd' else []
        design = compare(original,low,high,name,letters,inset)
        if images:assert_svg_representations(art,name,images/(name+'.tiff'),(48,48))
        shifted = Image.new('RGBA',low.size);shifted.paste(low,(1,0))
        opaque = low.copy();opaque.putalpha(255)
        r,g,b,a = low.split();wrong_color = Image.merge('RGBA',(b,g,r,a))
        missing = low.copy();y = next(iter(rows(original,name)));missing.paste((255,255,255,240),(7,y,42,y+1))
        mutations = [('shifted',shifted,high,letters,inset),('mirrored',ImageOps.mirror(low),high,letters,inset),
            ('opaque',opaque,high,letters,inset),('wrong-palette',wrong_color,high,letters,inset),('missing-line',missing,high,letters,inset)]
        if name == 'rtfd':
            missing = low.copy();missing.paste((255,255,255,240),(10,27,25,36));mutations.append(('missing-inset',missing,high,letters,inset))
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
            mutations.append((method.name.lower()+'-enlargement',low,low.resize(high.size,method),letters,inset))
            mutations.append((method.name.lower()+'-letter-enlargement',low,high,[letters[0],letters[0].resize(letters[1].size,method)],inset))
            if inset:mutations.append((method.name.lower()+'-inset-enlargement',low,high,letters,[inset[0],inset[0].resize(inset[1].size,method)]))
        rejected = []
        for label,candidate,big,type_images,picture in mutations:
            try:compare(original,candidate,big,name,type_images,picture)
            except AssertionError:rejected.append(label)
            else:raise AssertionError('Design mutation accepted: '+name+' '+label)
        directory = artifacts/name;directory.mkdir(parents=True)
        low.save(directory/'48.png');high.save(directory/'384.png')
        results.append(dict(name=name,design=design,original_source_sha256=fixture['source_sha256'],negative_controls=rejected))
        negative.extend(rejected)
    result = dict(passed=True,cases=results,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        paragraph_lines=39,inset_zones=9,negative_controls=len(negative),original_wording_recovered=False,
        inset_semantics_recovered=False,native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('TextEdit documents: 39 lines, nine inset zones and %d negative controls PASS.' % len(negative))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',required=True,type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--images',type=Path)
    args = parser.parse_args();run(args.artifacts,args.source,args.images)
