"""Preserve the four original shared slider diagrams as continuous SVG ramps."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image,ImageChops,ImageDraw,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original,assert_not_enlarged,assert_svg_representations

NAMES=('GSRGBColorPicker','GSHSBColorPicker','GSCMYKColorPicker','GSGrayColorPicker')


def compare(original,low,high,name):
    assert original.size==low.size==(36,24) and high.size==(288,192)
    assert original.getchannel('A').tobytes()==low.getchannel('A').tobytes(),'Slider footprint changed'
    maximum=max(v[1] for v in ImageChops.difference(original,low).getextrema())
    assert maximum<=1,('Slider palette, gradient, marker or swatch changed',name,maximum)
    assert_not_enlarged([low,high],name)
    samples=[high.getpixel((x,6*8)) for x in range(8*8,9*8)]
    assert len(set(samples))>=6,'Gradient retains the old raster color steps'
    assert max(abs(a-b) for p,q in zip(samples,samples[1:]) for a,b in zip(p,q))<=8,'Gradient is discontinuous'
    return dict(alpha_identical=True,maximum_original_channel_difference=maximum,
                continuous_subpixel_colors=len(set(samples)))


def run(artifacts,source=None,images=None):
    source=source or Path(__file__).resolve().parents[2]/'Libraries/gnustep/Artwork.svg'
    art=Artwork(source);artifacts.mkdir(parents=True);cases=[]
    for name in NAMES:
        assert art.symbols[name].get('data-reconstructed')=='true'
        original,fixture=artwork_original('color-panel',name)
        low,high=[art.render(name,size) for size in [(36,24),(288,192)]]
        design=compare(original,low,high,name)
        if images:assert_svg_representations(art,name,images/(name+'.tiff'),(36,24))
        shifted=Image.new('RGBA',low.size);shifted.paste(low,(1,0))
        opaque=low.copy();opaque.putalpha(255)
        changed=low.copy()
        for y in range(24):
            for x in range(36):
                r,g,b,a=changed.getpixel((x,y))
                if a:changed.putpixel((x,y),(min(255,r+8),g,b,a))
        missing=low.copy()
        if name=='GSGrayColorPicker':ImageDraw.Draw(missing).rectangle((3,10,7,14),fill=(0,0,0,0))
        else:
            knob={'GSRGBColorPicker':22,'GSHSBColorPicker':23,'GSCMYKColorPicker':24}[name]
            for x in range(knob,knob+2):
                for y in range(4,8):missing.putpixel((x,y),low.getpixel((x,8)))
        flat=low.copy();ImageDraw.Draw(flat).rectangle((3,4,31,8),fill=low.getpixel((12,8)))
        mutations=[('shifted',shifted,high),('mirrored',ImageOps.mirror(low),high),('opaque',opaque,high),
                   ('changed-palette',changed,high),('missing-marker-or-swatch',missing,high),('flat-gradient',flat,high)]
        for method in [Image.Resampling.NEAREST,Image.Resampling.LANCZOS]:
            mutations.append((method.name.lower()+'-enlargement',low,low.resize(high.size,method)))
        negatives=[]
        for label,candidate,big in mutations:
            try:compare(original,candidate,big,name)
            except AssertionError:negatives.append(label)
            else:raise AssertionError('Color-picker mutation accepted: '+name+' '+label)
        low.save(artifacts/(name+'-base.png'));high.save(artifacts/(name+'-high.png'))
        cases.append(dict(name=name,design=design,negative_controls=negatives,original_source_sha256=fixture['source_sha256']))
    result=dict(passed=True,cases=cases,negative_controls=sum(len(c['negative_controls']) for c in cases),
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Shared slider artwork: four original designs and 32 negative controls PASS.')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['artifacts','source','images']:parser.add_argument('--'+name,type=Path,required=name=='artifacts')
    args=parser.parse_args();run(args.artifacts,args.source,args.images)
