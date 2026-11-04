"""Check the original Services stack, steel tray, supporting hand and blue cuff."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import assert_not_enlarged,assert_svg_representations,preferences_original,regional_error


REGIONS={
    'fingers':((10,26,36,33),(8,16,70,3)),
    'palm':((16,32,36,39),(12,20,80,3)),
    'wrist':((25,38,36,43),(8,14,48,2)),
    'tray':((0,22,48,26),(4.5,9,60,2)),
    'cuff':((25,43,38,48),(8,14,65,5)),
}
DETAILS={
    'finger':(16,27,19,33),'palm':(18,32,24,37),'wrist':(27,38,34,43),
    'tray':(3,23,45,25),'cuff':(25,44,35,48),'shadow':(15,34,24,39),
}


def points(box):
    x,y,r,b=box
    return [(px,py) for py in range(y,b) for px in range(x,r)]


def compare(original,actual,higher):
    assert original.size==actual.size==(48,48) and higher.size==(384,384)
    assert_not_enlarged([actual,higher],'Services')
    old,new=original.load(),actual.load();canvas=points((0,0,48,48))
    outline=len({p for p in canvas if old[p][3]>=128}^{p for p in canvas if new[p][3]>=128})
    assert outline<=4,('Services silhouette or finger opening changed',outline)
    old_area=sum(old[p][3]/255 for p in canvas);new_area=sum(new[p][3]/255 for p in canvas)
    assert abs(old_area-new_area)<=1,('Services opacity or shadow changed',old_area,new_area)
    stack=points((0,0,48,22));occupied=[p for p in stack if old[p][3]]
    assert len(occupied)==703
    assert all(old[p]==new[p] for p in stack),'Services panel stack changed'
    rim=[(x,22) for x in range(1,48)]
    assert all(old[p]==new[p]==(255,255,255,240) for p in rim),'Services tray rim changed'
    assert all(new[x,y][3]==old[x,y][3]==240 for y in range(43,48) for x in range(25,38)), 'Services cuff proportions changed'
    errors={}
    for name,(box,limits) in REGIONS.items():
        error=regional_error(original,actual,points(box));errors[name]=error
        assert all(error[key]<=limit for key,limit in zip(('mean','rms','maximum','channel_mean_difference'),limits)),('Services material changed',name,error)
    def shine(image,box):
        pixels=image.convert('RGBa').load();weights=[(x,y,max(sum(pixels[x,y][:3])/3-200,0)) for x,y in points(box)]
        mass=sum(w for x,y,w in weights);assert mass>0,'Services hand reflection disappeared'
        center=[sum((x if axis==0 else y)*w for x,y,w in weights)/mass for axis in (0,1)]
        return mass,center
    reflections={}
    for name in ('fingers','palm','wrist'):
        box=REGIONS[name][0];mass,center=shine(original,box);new_mass,new_center=shine(actual,box)
        assert abs(new_mass/mass-1)<=.05 and max(abs(a-b) for a,b in zip(center,new_center))<=.12,('Services hand reflection moved or changed size',name,mass,new_mass,center,new_center)
        reflections[name]=dict(original_mass=mass,reconstructed_mass=new_mass,original_center=center,reconstructed_center=new_center)
    for name,box in DETAILS.items():
        assert_not_enlarged([actual.crop(box),higher.crop(tuple(v*8 for v in box))],'Services '+name)
    pixels=higher.load();values=[pixels[x,188][:3] for x in range(32,352)]
    transitions=sum(a!=b for a,b in zip(values,values[1:]));step=max(abs(a-b) for p,q in zip(values,values[1:]) for a,b in zip(p,q))
    assert transitions>=40 and step<=2,('Services tray shading traces the source grid',transitions,step)
    return dict(outline_difference_pixels=outline,original_alpha_area=old_area,reconstructed_alpha_area=new_area,
        exact_stack_pixels=len(occupied),exact_white_rim_pixels=len(rim),material_errors=errors,reflections=reflections,
        high_density_tray_transitions=transitions,high_density_tray_maximum_step=step)


def run(artifacts,source=None,image=None):
    source=source or Path(__file__).resolve().parents[2]/'Applications/Preferences/Artwork.svg'
    original,fixture=preferences_original('Services');art=Artwork(source)
    actual,higher=art.render('Services',(48,48)),art.render('Services',(384,384));result=compare(original,actual,higher)
    if image:assert_svg_representations(art,'Services',image,(48,48))
    shifted=Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
    gray=ImageOps.grayscale(actual).convert('RGBA');gray.putalpha(actual.getchannel('A'))
    def paint(box,color):
        candidate=actual.copy();candidate.paste(color,box);return candidate
    opening=paint((8,1,37,6),(153,153,170,240));bevel=paint((37,1,38,7),(0,0,0,240))
    tray=paint((1,22,48,23),(170,170,170,240));finger=paint((16,27,20,34),(0,0,0,240))
    moved=actual.copy();moved.paste((0,0,0,240),(16,27,20,33));moved.paste(actual.crop((16,27,19,33)),(17,27))
    filled=paint((24,27,31,30),(128,136,128,240));palm=paint((22,34,34,39),(160,168,160,240))
    cuff=paint((25,44,35,48),(48,48,48,240));steel=paint((3,23,45,25),(119,119,119,240))
    shadow=actual.copy()
    for p in points((0,26,38,43)):
        if 0<shadow.getpixel(p)[3]<128:shadow.putpixel(p,(0,0,0,0))
    controls=[('translated',shifted,higher),('desaturated',gray,higher),('panel-opening',opening,higher),('panel-bevel',bevel,higher),
        ('tray-rim',tray,higher),('missing-finger-reflection',finger,higher),('finger-reflection-moved',moved,higher),
        ('finger-opening-filled',filled,higher),('flat-palm',palm,higher),('cuff-palette',cuff,higher),('tray-palette',steel,higher),('missing-shadow',shadow,higher)]
    for name,box in DETAILS.items():
        large=higher.copy();x,y,r,b=box;large.paste(actual.crop(box).resize(((r-x)*8,(b-y)*8),Image.Resampling.NEAREST),(x*8,y*8))
        controls.append(('traced-'+name,actual,large))
    controls.extend([('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))])
    rejected=[]
    for name,candidate,large in controls:
        try:compare(original,candidate,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful Services design accepted',name))
    artifacts.mkdir(parents=True);actual.save(artifacts/'candidate-100.png');higher.save(artifacts/'candidate-800.png')
    result.update(passed=True,rejected_mutations=rejected,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],submitted_image_verified=image is not None,native_density_qualification=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--source',type=Path);parser.add_argument('--image',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.image)
