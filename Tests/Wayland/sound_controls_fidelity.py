"""Check the original speaker, microphone, acoustic arcs and chrome level dots."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import (artwork_original,assert_curve_arguments,
    assert_not_enlarged,assert_svg_representations,regional_error)


NAMES=('volMute','volLoud','micMute','micLoud')
REGIONS={
    'volMute':{'body':((0,0,24,36),(8,20,150,3)),
        'wave':((24,8,30,25),(9,22,125,4))},
    'volLoud':{'body':((0,0,21,36),(8,20,150,3)),
        'waves':((21,7,31,28),(11,25,155,4))},
    'micMute':{'capsule':((11,3,21,24),(14,24,150,4)),
        'fork':((9,13,24,27),(15,26,150,4)),
        'pedestal':((12,26,22,32),(16,28,130,4)),
        'dot':((24,25,31,32),(12,24,130,4))},
    'micLoud':{'capsule':((11,3,21,24),(14,24,150,4)),
        'fork':((9,13,24,27),(15,26,150,4)),
        'pedestal':((12,26,22,32),(16,28,130,4)),
        'dots':((24,4,31,32),(14,26,130,5))},
}


def points(box):
    x,y,r,b=box
    return [(px,py) for py in range(y,b) for px in range(x,r)]


def feature(image,box,kind):
    pixels=image.convert('RGBa').load();samples=[]
    for x,y in points(box):
        r,g,b,a=pixels[x,y]
        weight=max(b-max(r,g),0) if kind=='blue' else min(r,g,b)
        samples.append((x,y,weight))
    mass=sum(w for x,y,w in samples);assert mass>0,('Sound control material missing',kind)
    return mass,[sum((x if axis==0 else y)*w for x,y,w in samples)/mass for axis in (0,1)]


def compare(name,original,actual,higher):
    assert original.size==actual.size==(36,36) and higher.size==(288,288)
    assert_not_enlarged([actual,higher],name)
    old,new=original.load(),actual.load();canvas=points((0,0,36,36))
    assert original.getchannel('A').getbbox()==actual.getchannel('A').getbbox(),(name,'occupied bounds changed')
    before={p for p in canvas if old[p][3]>=128};after={p for p in canvas if new[p][3]>=128}
    outline=len(before^after)
    # The originals have quantized alpha on their small chrome strokes. Protect
    # contour agreement and covered area independently of the material checks.
    assert outline<=math.ceil(len(before)*.08),(name,'contour changed',outline)
    old_area=sum(old[p][3]/255 for p in canvas);new_area=sum(new[p][3]/255 for p in canvas)
    assert abs(new_area/old_area-1)<=.01,(name,'opacity or covered area changed',old_area,new_area)
    for first,second in ((before,after),(after,before)):
        assert all(any((x+dx,y+dy) in second for dx in (-1,0,1) for dy in (-1,0,1)) for x,y in first),(name,'silhouette moved')
    materials={};features={}
    for key,(box,limits) in REGIONS[name].items():
        error=regional_error(original,actual,points(box));materials[key]=error
        assert all(error[field]<=limit for field,limit in zip(('mean','rms','maximum','channel_mean_difference'),limits)),(name,key,'original material changed',error)
        for kind in ('blue','neutral'):
            mass,center=feature(original,box,kind);new_mass,new_center=feature(actual,box,kind)
            assert abs(new_mass/mass-1)<=.05 and max(abs(a-b) for a,b in zip(center,new_center))<=.15,(name,key,kind,'weight or position changed',mass,new_mass,center,new_center)
            features[key+'-'+kind]=dict(original_mass=mass,reconstructed_mass=new_mass,original_center=center,reconstructed_center=new_center)
        assert_not_enlarged([actual.crop(box),higher.crop(tuple(v*8 for v in box))],name+' '+key)
    return dict(outline_difference_pixels=outline,original_alpha_area=old_area,reconstructed_alpha_area=new_area,material_errors=materials,features=features)


def run(artifacts,source=None,images=None):
    source=source or Path(__file__).resolve().parents[2]/'Applications/Preferences/Artwork.svg'
    art=Artwork(source);assert_curve_arguments(art.root);cases={};originals={};frames={};rejected=[]
    for name in NAMES:
        original,fixture=artwork_original('sound_controls',name);actual=art.render(name,(36,36));higher=art.render(name,(288,288))
        cases[name]=compare(name,original,actual,higher);originals[name]=original;frames[name]=(actual,higher)
        if images:assert_svg_representations(art,name,images/(name+'.tiff'),(36,36))
        shifted=Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
        gray=ImageOps.grayscale(actual).convert('RGBA');gray.putalpha(actual.getchannel('A'))
        controls=[('translated',shifted,higher),('desaturated',gray,higher)]
        for key,(box,limits) in REGIONS[name].items():
            missing=actual.copy();missing.paste((0,0,0,0),box);controls.append(('missing-'+key,missing,higher))
            large=higher.copy();x,y,r,b=box;large.paste(actual.crop(box).resize(((r-x)*8,(b-y)*8),Image.Resampling.NEAREST),(x*8,y*8));controls.append(('traced-'+key,actual,large))
        controls.extend([('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))])
        for label,candidate,large in controls:
            try:compare(name,original,candidate,large)
            except AssertionError:rejected.append(name+'-'+label)
            else:raise AssertionError(('Unfaithful Sound control accepted',name,label))
        cases[name]['original_source_sha256']=fixture['source_sha256']
    box=(0,0,24,36)
    assert originals['micMute'].crop(box).tobytes()==originals['micLoud'].crop(box).tobytes()
    for at in (0,1):
        multiplier=1 if at==0 else 8;region=tuple(v*multiplier for v in box)
        assert frames['micMute'][at].crop(region).tobytes()==frames['micLoud'][at].crop(region).tobytes(),'Sound microphone geometry diverged between states'
    artifacts.mkdir(parents=True)
    for name,(actual,higher) in frames.items():actual.save(artifacts/(name+'-100.png'));higher.save(artifacts/(name+'-800.png'))
    result=dict(passed=True,cases=cases,rejected_mutations=rejected,shared_microphone_pixels_verified=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),submitted_images_verified=images is not None,native_density_qualification=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True);parser.add_argument('--source',type=Path);parser.add_argument('--images',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.images)
