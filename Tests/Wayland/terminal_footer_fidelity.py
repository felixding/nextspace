#!/usr/bin/env python3
"""Preserve the original Terminal credit's two lettering styles and emboss."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, regional_error


GLYPHS = tuple(zip('DEVELOPEDWITHGNUSTEP',
    (0,6,12,18,24,30,37,43,49,56,66,69,75,83,92,99,106,111,117,122),
    (6,12,18,24,30,37,43,49,56,66,69,75,83,92,99,106,111,117,122,128)))


def foreground(original):
    """Recover coverage from black letters and their white (1,1) highlight."""
    result = Image.new('L',original.size);values = []
    for y in range(10):
        for x in range(128):
            r,g,b,a = original.getpixel((x,y));assert r==g==b and a==255
            shadow = values[(y-1)*128+x-1] if x and y else 0
            coverage = 1-r/(170+85*shadow)
            assert -.01 <= coverage <= 1
            values.append(max(0,coverage))
    result.putdata([round(value*255) for value in values])
    return result


def emboss(alpha, offset=(1,1), background=170):
    image = Image.new('RGBA',alpha.size);pixels = []
    for y in range(10):
        for x in range(128):
            sx,sy = x-offset[0],y-offset[1]
            shadow = alpha.getpixel((sx,sy))/255 if 0<=sx<128 and 0<=sy<10 else 0
            ink = alpha.getpixel((x,y))/255
            value = round((background+(255-background)*shadow)*(1-ink))
            pixels.append((value,value,value,255))
    image.putdata(pixels);return image


def compare(original,low,high,before,after,large_foreground):
    assert low.size==before.size==after.size==original.size==(128,10)
    assert high.size==large_foreground.size==(1024,80)
    assert low.getchannel('A').getextrema()==(255,255), 'The footer background must stay opaque'
    for point in ((0,0),(55,0),(56,4),(82,0),(127,0)):
        assert low.getpixel(point)==original.getpixel(point)==(170,170,170,255), 'Footer background changed'
    error = regional_error(original,low,((x,y) for y in range(10) for x in range(128)))
    assert error['mean']<=4 and error['channel_mean_difference']<=2, ('Emboss or lettering changed',error)
    records = []
    for index,(letter,left,right) in enumerate(GLYPHS):
        points = [(x,y) for y in range(10) for x in range(left,right)]
        old = [before.getpixel(p)/255 for p in points];new = [after.getpixel(p)/255 for p in points]
        total,actual = sum(old),sum(new);assert total>0 and actual>0, ('Missing letter',index,letter)
        ratio = actual/total;assert abs(ratio-1) <= (.03 if index<13 else .13), ('Letter weight changed',index,ratio)
        overlap = sum(min(a,b) for a,b in zip(old,new))/sum(max(a,b) for a,b in zip(old,new))
        assert overlap >= (.97 if index<13 else .83), ('Letter shape changed',index,letter,overlap)
        centers = []
        for axis in (0,1):
            first = sum(p[axis]*a for p,a in zip(points,old))/total
            second = sum(p[axis]*a for p,a in zip(points,new))/actual
            assert abs(second-first) <= .12, ('Letter position changed',index,letter,axis)
            centers.append(second-first)
        records.append(dict(letter=letter,slot=[left,right],ink_ratio=ratio,overlap=overlap,center_delta=centers))
    assert_not_enlarged([low,high],'Terminal footer')
    glyphs = Image.new('RGBA',after.size);glyphs.putalpha(after)
    assert_not_enlarged([glyphs,large_foreground],'Footer glyph geometry')
    return dict(pixel_error=error,glyphs=records)


def run(artifacts,source=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/Terminal/Artwork.svg'
    art = Artwork(source);assert_curve_arguments(art.root)
    symbol = art.symbols['DWG'];assert symbol.get('data-reconstructed')=='true' and symbol.get('data-logical-size')=='128 10'
    assert symbol.get('data-files')=='Resources/DWG.tiff English.lproj/Info.gorm/DWG.tiff'
    original,_ = artwork_original('terminal-footer','DWG');before = foreground(original)
    low,high = (art.render('DWG',size) for size in ((128,10),(1024,80)))
    # The shared glyph group uses the credit's coordinate system, independent
    # of the application's 48-point icon preview.
    art.viewbox = symbol.get('viewBox')
    after,large = (art.render('footer-lettering',size) for size in ((128,10),(1024,80)))
    alpha = after.getchannel('A');design = compare(original,low,high,before,alpha,large)
    shifted = Image.new('L',alpha.size);shifted.paste(alpha,(1,0))
    tracked = alpha.copy();tracked.paste(0,(83,0,128,10));tracked.paste(alpha.crop((83,0,128,10)),(84,0))
    missing = alpha.copy();missing.paste(0,(83,0,92,10))
    light = alpha.point(lambda value:round(value*.7))
    transparent = low.copy();transparent.putalpha(0)
    mutations = [('shifted-caption',emboss(shifted),shifted,high,large),
        ('wrong-word-spacing',emboss(tracked),tracked,high,large),('missing-letter',emboss(missing),missing,high,large),
        ('light-weight',emboss(light),light,high,large),('missing-highlight',emboss(alpha,(0,0)),alpha,high,large),
        ('wrong-highlight',emboss(alpha,(2,1)),alpha,high,large),('wrong-background',emboss(alpha,background=166),alpha,high,large),
        ('mirrored',ImageOps.mirror(low),ImageOps.mirror(alpha),high,large),('transparent',transparent,alpha,high,large)]
    mutations += [(method.name.lower()+'-enlargement',low,alpha,low.resize(high.size,method),after.resize(large.size,method))
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS)]
    rejected=[]
    for label,changed,coverage,big,big_foreground in mutations:
        try:compare(original,changed,big,before,coverage,big_foreground)
        except AssertionError:rejected.append(label)
        else:raise AssertionError('Accepted changed footer: '+label)
    artifacts.mkdir(parents=True)
    result=dict(passed=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),design=design,
        rejected_mutations=rejected,native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Terminal footer: 20 original glyph layouts and {len(rejected)} negative controls PASS')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True);parser.add_argument('--source',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source)
