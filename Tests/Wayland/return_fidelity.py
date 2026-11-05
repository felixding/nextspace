"""Check the original Return glyph's bevel, silhouette and weight after redrawing."""
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image,ImageFilter,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork,DENSITIES,backing_size
from artwork_reference import alpha_geometry,assert_not_enlarged,assert_svg_representations,assert_vector_geometry


def compare(original,frames):
    assert [p.size for p in frames]==[tuple(backing_size(v,d) for v in (15,10)) for d in DENSITIES[:5]]
    actual=frames[0];assert actual.tobytes()==original.tobytes(),'Original Return glyph pixels changed'
    assert_not_enlarged(frames,'Return glyph')
    for frame in frames[1:]:
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
            assert actual.resize(frame.size,method).tobytes()!=frame.tobytes(),'Return density is bitmap enlargement'
    return dict(**alpha_geometry(original,actual),exact_original_pixels=150,exact_stem_and_bevel_pixels=30)


def run(artifacts,repository=None,image=None):
    repository=repository or Path(__file__).resolve().parents[2];fixture=repository/'Tests/Wayland/artwork-originals/return'
    reference=json.loads((fixture/'reference.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert sha(fixture/reference['source'])==reference['source_sha256']==reference['upstream_sha256']
    assert sha(fixture/reference['png'])==reference['png_sha256']
    art=Artwork(repository/'Applications/Artwork/Navigation.svg');assert_vector_geometry(art.root)
    with Image.open(fixture/reference['png']) as p:original=p.convert('RGBA')
    frames=[art.render('ReturnGlyph',tuple(backing_size(v,d) for v in (15,10))) for d in DENSITIES[:5]]
    metrics=compare(original,frames);controls=[];rejected=[]
    def changed(label,action):
        copy=[p.copy() for p in frames];action(copy[0]);controls.append((label,copy))
    changed('mirrored',lambda p:p.paste(ImageOps.mirror(p)))
    changed('missing-tip',lambda p:p.putpixel((0,5),(0,0,0,0)))
    changed('missing-stem',lambda p:p.paste((0,0,0,0),(14,1,15,8)))
    changed('palette',lambda p:p.putpixel((14,4),(255,0,0,255)))
    changed('thickened',lambda p:p.putalpha(p.getchannel('A').filter(ImageFilter.MaxFilter(3))))
    def shifted(p):
        copy=p.copy();p.paste((0,0,0,0),(0,0,*p.size));p.paste(copy,(1,0))
    changed('translated',shifted)
    for label,method in [('nearest-enlargement',Image.Resampling.NEAREST),('lanczos-enlargement',Image.Resampling.LANCZOS)]:
        controls.append((label,[frames[0].resize(p.size,method) for p in frames]))
    for label,candidate in controls:
        try:compare(original,candidate)
        except AssertionError:rejected.append(label)
        else:raise AssertionError('Accepted altered Return glyph: '+label)
    if image:assert_svg_representations(art,'ReturnGlyph',image,(15,10))
    artifacts.mkdir(parents=True);frames[0].save(artifacts/'reconstruction-100.png');art.render('ReturnGlyph',(480,320)).save(artifacts/'reconstruction-3200.png')
    result=dict(passed=True,metrics=metrics,rejected_mutations=rejected,submitted_image_verified=image is not None,
        native_rendering_qualified=False,full_plan_complete=False);(artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Return glyph: original bevel and',len(rejected),'negative controls PASS');return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,required=True);args=p.parse_args();run(args.artifacts)
