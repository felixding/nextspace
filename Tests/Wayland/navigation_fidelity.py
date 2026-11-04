"""Preserve the original seven-point navigation arrows as smooth bevel geometry."""
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image,ImageOps,ImageFilter
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork,backing_size,DENSITIES
from artwork_reference import alpha_geometry,assert_vector_geometry,assert_not_enlarged,assert_svg_representations


def pixels(image):
    return [image.getpixel((x,y)) for y in range(image.height) for x in range(image.width)]


def compare(original,frames):
    assert len(frames)==5 and [p.size for p in frames]==[(backing_size(7,d),)*2 for d in DENSITIES[:5]]
    actual=frames[0];shape=alpha_geometry(original,actual)
    assert shape['original_bounds']==shape['reconstructed_bounds']==(0,0,7,7),'Arrow bounds changed'
    overlap=shape['shape_overlap'];assert overlap==1,('Arrow silhouette changed',overlap)
    old_mass,new_mass=shape['original_coverage'],shape['reconstructed_coverage'];assert abs(new_mass-old_mass)<.1,('Arrow ink weight changed',old_mass,new_mass)
    old_center,new_center=shape['original_center'],shape['reconstructed_center'];assert max(abs(a-b) for a,b in zip(old_center,new_center))<.05,'Arrow alignment changed'
    assert original.crop((0,0,1,7)).tobytes()==actual.crop((0,0,1,7)).tobytes(),'Arrow rear bevel changed'
    assert original.getpixel((6,3))==actual.getpixel((6,3)),'Arrow tip changed'
    means=[]
    for channel in range(3):
        old=sum(p[channel] for p in pixels(original.convert('RGBa')))/49
        new=sum(p[channel] for p in pixels(actual.convert('RGBa')))/49
        means.append(abs(old-new))
    assert max(means)<.75,('Arrow bevel palette changed',means)
    assert_not_enlarged(frames,'Navigation bevel')
    return dict(shape_overlap=overlap,original_coverage=old_mass,reconstructed_coverage=new_mass,
        original_center=old_center,reconstructed_center=new_center,channel_mean_difference=means,
        exact_rear_bevel_pixels=7,exact_tip_pixels=1)


def run(artifacts,repository=None,images=None):
    repository=repository or Path(__file__).resolve().parents[2];source=repository/'Applications/Artwork/Navigation.svg'
    art=Artwork(source);assert_vector_geometry(art.root);root=repository/'Tests/Wayland/artwork-originals/navigation'
    definition=json.loads((root/'references.json').read_text());cases={};rejected=[]
    for name,case in definition['cases'].items():
        assert hashlib.sha256((repository/case['source']).read_bytes()).hexdigest()==case['source_sha256']
        path=root/case['png'];assert hashlib.sha256(path.read_bytes()).hexdigest()==case['png_sha256']
        with Image.open(path) as image:original=image.convert('RGBA')
        frames=[art.render(case['symbol'],(backing_size(7,d),)*2) for d in DENSITIES[:5]]
        cases[name]=compare(original,frames)
        if images and name in images:assert_svg_representations(art,case['symbol'],images[name],(7,7))
        controls=[]
        def changed(label,action):
            candidate=[p.copy() for p in frames];action(candidate[0]);controls.append((label,candidate))
        changed('mirrored',lambda p:p.paste(ImageOps.mirror(p)))
        changed('missing-tip',lambda p:p.putpixel((6,3),(0,0,0,0)))
        changed('missing-rear',lambda p:p.paste((0,0,0,0),(0,0,1,7)))
        changed('palette',lambda p:p.paste((255,0,0,255),(0,0,1,7)))
        def shifted(p):
            copy=p.copy();p.paste((0,0,0,0),(0,0,7,7));p.paste(copy,(1,0))
        changed('translated',shifted)
        changed('thickened',lambda p:p.putalpha(p.getchannel('A').filter(ImageFilter.MaxFilter(3))))
        for label,method in [('nearest-enlargement',Image.Resampling.NEAREST),('lanczos-enlargement',Image.Resampling.LANCZOS)]:
            controls.append((label,[frames[0].resize(frame.size,method) for frame in frames]))
        for label,candidate in controls:
            try:compare(original,candidate)
            except AssertionError:rejected.append(name+'-'+label)
            else:raise AssertionError('Accepted altered navigation arrow: '+name+'-'+label)
    artifacts.mkdir(parents=True)
    for name,case in definition['cases'].items():
        art.render(case['symbol'],(7,7)).save(artifacts/(name+'-100.png'))
        art.render(case['symbol'],(224,224)).save(artifacts/(name+'-3200.png'))
    result=dict(passed=True,cases=cases,rejected_mutations=rejected,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        native_rendering_qualified=False,submitted_images_verified=images is not None,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Navigation arrows:',len(cases),'original references and',len(rejected),'negative controls PASS');return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,required=True);args=p.parse_args();run(args.artifacts)
