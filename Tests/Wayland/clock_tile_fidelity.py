"""Preserve the original clock geometry while recovering its smooth shading."""
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image,ImageOps,ImageStat
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork,DENSITIES,backing_size
from artwork_reference import assert_not_enlarged,assert_svg_representations,assert_vector_geometry


def compare(original,frames,reference):
    assert [p.size for p in frames]==[tuple(backing_size(64,d) for _ in range(2)) for d in DENSITIES[:5]]
    actual=frames[0];a=list(original.getdata());b=list(actual.getdata());exact=0
    assert actual.getchannel('A').tobytes()==original.getchannel('A').tobytes()
    for color in reference['flat_colors']:
        target=tuple(color)
        before=[p[:3]==target for p in a];after=[p[:3]==target for p in b]
        assert before==after,'Clock face, bevel or display geometry/palette changed'
        exact+=sum(before)
    regions={}
    for name,box in reference['metal_regions'].items():
        source=original.crop(tuple(box)).convert('RGB');current=actual.crop(tuple(box)).convert('RGB')
        assert all(v%reference['source_metal_quantization_step']==0 for p in source.getdata() for v in p)
        expected_mean=ImageStat.Stat(source).mean;actual_mean=ImageStat.Stat(current).mean
        delta=max(abs(x-y) for x,y in zip(expected_mean,actual_mean))
        assert delta<=reference['gradient_mean_channel_tolerance'],(name,delta)
        regions[name]=dict(original_mean=expected_mean,reconstructed_mean=actual_mean,maximum_mean_channel_difference=delta)
    assert_not_enlarged(frames,'Preferences clock tile')
    return dict(exact_original_flat_color_pixels=exact,metal_regions=regions,all_original_pixels_identical=False,source_dithering_replaced_by_continuous_gradients=True)


def run(artifacts,repository=None,image=None):
    repository=repository or Path(__file__).resolve().parents[2];fixture=repository/'Tests/Wayland/artwork-originals/clock-tile'
    reference=json.loads((fixture/'reference.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(repository/reference['source'])==reference['source_sha256']
    assert sha(fixture/reference['png'])==reference['png_sha256']
    with Image.open(fixture/reference['png']) as p:original=p.convert('RGBA')
    art=Artwork(repository/'Applications/Artwork/ClockTile.svg');assert_vector_geometry(art.root)
    frames=[art.render('clock-tile-original',tuple(backing_size(64,d) for _ in range(2))) for d in DENSITIES[:5]]
    metrics=compare(original,frames,reference);controls=[];rejected=[]
    def changed(name,action):
        copy=[p.copy() for p in frames];action(copy[0]);controls.append((name,copy))
    changed('mirrored',lambda p:p.paste(ImageOps.mirror(p)))
    changed('display-palette',lambda p:p.paste((34,36,90,255),(5,5,58,21)))
    changed('display-height',lambda p:p.paste((34,36,75,255),(5,21,58,22)))
    changed('missing-shadow',lambda p:p.paste((90,90,100,255),(47,27,50,60)))
    changed('clock-face-inset',lambda p:p.paste((85,85,85,255),(14,24,15,51)))
    changed('outer-bevel-width',lambda p:p.paste((255,255,255,255),(2,2,3,62)))
    changed('flat-metal',lambda p:p.paste((128,128,144,255),(3,24,11,60)))
    changed('metal-palette',lambda p:p.paste((155,155,165,255),(55,24,62,60)))
    for name,method in [('nearest-enlargement',Image.Resampling.NEAREST),('lanczos-enlargement',Image.Resampling.LANCZOS)]:
        controls.append((name,[frames[0].resize(p.size,method) for p in frames]))
    for name,candidate in controls:
        try:compare(original,candidate,reference)
        except AssertionError:rejected.append(name)
        else:raise AssertionError('Accepted altered clock tile: '+name)
    if image:assert_svg_representations(art,'clock-tile-original',image,(64,64))
    artifacts.mkdir(parents=True);frames[0].save(artifacts/'reconstruction-100.png');art.render('clock-tile-original',(512,512)).save(artifacts/'reconstruction-800.png')
    result=dict(passed=True,metrics=metrics,rejected_mutations=rejected,submitted_image_verified=image is not None,native_rendering_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Clock tile: original geometry and',len(rejected),'negative controls PASS');return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--image',type=Path);a=p.parse_args();run(a.artifacts,image=a.image)
