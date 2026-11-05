#!/usr/bin/env python3
"""Preserve the original MACH/OUT scrolling strips as high-resolution geometry."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_curve_arguments, assert_not_enlarged, regional_error


GLYPHS = {'ScrollingMach': {'prompt':(1,3,3,6),'M':(4,3,9,6),'A':(10,3,15,6),'C':(16,3,19,6),'H':(20,3,24,6)},
    'ScrollingOutput': {'prompt':(1,3,3,6),'O':(5,3,9,6),'U':(10,3,14,6),'T':(15,3,20,6)}}
BACKGROUNDS = {'ScrollingMach':(51,51,85,255),'ScrollingOutput':(0,17,17,255)}


def ink(image,box,channel,background):
    left,top,right,bottom = box;pixels = image.load()
    weights = [(x,y,max(0,pixels[x,y][channel]-background)) for y in range(top,bottom) for x in range(left,right)]
    mass = sum(w for x,y,w in weights);assert mass > 0, 'Missing glyph'
    return mass,[sum((x if axis==0 else y)*w for x,y,w in weights)/mass for axis in (0,1)],weights


def compare(name,original,low,high):
    width = 27 if name == 'ScrollingMach' else 28
    assert original.size == low.size == (width,35) and high.size == (width*8,280)
    assert low.getchannel('A').getextrema() == (255,255)
    channel = int(name == 'ScrollingMach');background = BACKGROUNDS[name]
    glyphs = []
    for row in range(5):
        offset = row*7
        for label,box in GLYPHS[name].items():
            box = (box[0],box[1]+offset,box[2],box[3]+offset)
            mass,center,before = ink(original,box,channel,background[channel])
            weight,position,after = ink(low,box,channel,background[channel])
            assert abs(weight/mass-1) <= .08,(name,row,label,'ink weight changed',mass,weight)
            assert max(abs(a-b) for a,b in zip(center,position)) <= .15,(name,row,label,'position changed',center,position)
            overlap = sum(min(a[2],b[2]) for a,b in zip(before,after))/min(mass,weight)
            # The one-pixel diagonal prompt gains antialiasing at 100%.
            assert overlap >= (.8 if label=='prompt' else .82),(name,row,label,'glyph shape changed',overlap)
            assert_not_enlarged([low.crop(box),high.crop(tuple(n*8 for n in box))],name+' '+label)
            glyphs.append(dict(row=row,glyph=label,original_weight=mass,reconstructed_weight=weight,
                original_center=center,reconstructed_center=position,overlap=overlap))
        assert low.crop((0,offset,width,offset+7)).tobytes() == low.crop((0,0,width,7)).tobytes(), 'Row spacing changed'
        for y in (offset,offset+1,offset+2,offset+6):
            assert all(low.getpixel((x,y)) == background for x in range(width)), (name,'screen background changed')
    error = regional_error(original,low,((x,y) for y in range(35) for x in range(width)))
    assert error['mean'] <= 3.5,(name,'palette or lettering changed',error)
    return dict(glyphs=glyphs,error=error,rows=5,period=7)


def run(artifacts,source=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/Terminal/Artwork.svg'
    art = Artwork(source);assert_curve_arguments(art.root);cases = {};rejected = []
    for name in GLYPHS:
        original,_ = artwork_original('terminal-strips',name);width = original.width
        low,high = art.render(name,(width,35)),art.render(name,(width*8,280))
        cases[name] = compare(name,original,low,high)
        shifted = Image.new('RGBA',low.size,BACKGROUNDS[name]);shifted.paste(low,(1,0))
        gray = ImageOps.grayscale(low).convert('RGBA')
        controls = [('translated',shifted,high),('desaturated',gray,high),
            ('enlarged-bitmap',low,low.resize(high.size,Image.Resampling.NEAREST))]
        for label,box in (('missing-letter',GLYPHS[name]['M' if name=='ScrollingMach' else 'T']),('missing-row',(0,14,width,21))):
            changed = low.copy();changed.paste(BACKGROUNDS[name],box);controls.append((label,changed,high))
        mirrored = low.copy();box = GLYPHS[name]['C' if name=='ScrollingMach' else 'prompt'];mirrored.paste(ImageOps.mirror(low.crop(box)),box)
        controls.append(('mirrored-glyph',mirrored,high))
        for label,changed,large in controls:
            try: compare(name,original,changed,large)
            except AssertionError: rejected.append(name+'-'+label)
            else: raise AssertionError('Accepted changed Terminal strip: '+name+'-'+label)
    artifacts.mkdir(parents=True)
    result = dict(passed=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),cases=cases,
        rejected_mutations=rejected,native_animation_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Terminal scrolling strips: 45 glyph checks and {len(rejected)} negative controls PASS')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True);parser.add_argument('--source',type=Path)
    args = parser.parse_args();run(args.artifacts,args.source)
