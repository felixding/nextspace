"""Check the original closed and unavailable leather portfolio folder designs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image,ImageDraw,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import (artwork_original,assert_curve_arguments,
    assert_not_enlarged,assert_svg_representations,regional_error)


NAMES=('closed','bad')
SURFACES={
    'upper-left':((13,16),(22,11),(26,9),(26,13),(18,20)),
    'upper-right':((31,7),(40,2),(42,4),(42,9),(35,12)),
    'flap-left':((14,17),(25,11),(26,13),(26,25),(15,31)),
    'flap-right':((31,9),(41,4),(42,13),(44,16),(31,23)),
    'body-left':((14,36),(25,30),(26,34),(14,41)),
    'body-right':((31,27),(40,22),(40,28),(31,32)),
}
BANDS={'bottom-edge':(((9,43),(42,27),(44,30),(11,47)),(10,24,160,6)),
    'flap-fold':(((12,32),(45,15),(47,19),(14,37)),(12,24,160,6)),
    'top-bevel':(((9,14),(40,0),(44,2),(12,19)),(16,30,180,5))}
DETAILS={'upper-left':(12,8,27,21),'upper-right':(30,1,44,13),'flap-left':(13,10,27,33),'flap-right':(30,3,46,24),
    'body-left':(13,30,27,42),'body-right':(30,21,41,33),'binding':(26,6,31,38),'fold':(13,16,46,36),
    'top-bevel':(9,0,44,19),'bottom-edge':(9,27,45,47)}
ANCHORS=tuple([(7,y) for y in range(20,42)]+[(8,y) for y in range(19,42)]+[(29,y) for y in range(10,19)])
INK_POINTS=tuple((x,int(40-x*.5)) for x in (14,16,18,20,22,24,26,32,34,36,38,40,42))
CANVAS=tuple((x,y) for y in range(48) for x in range(48))


def region(polygon):
    mask=Image.new('L',(48,48));ImageDraw.Draw(mask).polygon(polygon,fill=255)
    return [p for p in CANVAS if mask.getpixel(p)]


def feature(image,points,kind):
    pixels=image.convert('RGBa').load();straight=image.convert('RGBA').load();samples=[]
    for x,y in points:
        r,g,b,a=pixels[x,y]
        weight=max(r-b,0) if kind=='warmth' else min(r,g,b) if kind=='neutral' else max((125 if kind=='muted-darkness' else 80)-max(straight[x,y][:3]),0)*a/255 if kind in ('darkness','muted-darkness') else a
        samples.append((x,y,weight))
    mass=sum(w for x,y,w in samples);assert mass>0,('Folder feature missing',kind)
    return mass,[sum((x if axis==0 else y)*w for x,y,w in samples)/mass for axis in (0,1)]


def compare(name,original,actual,higher,shadow):
    assert original.size==actual.size==(48,48) and higher.size==(384,384)
    assert_not_enlarged([actual,higher],name)
    old,new=original.load(),actual.load()
    assert original.getchannel('A').getbbox()==actual.getchannel('A').getbbox(),(name,'occupied bounds changed')
    before={p for p in CANVAS if old[p][3]>=128};after={p for p in CANVAS if new[p][3]>=128};outline=len(before^after)
    assert outline<=math.ceil(len(before)*.05),(name,'contour changed',outline)
    old_area=sum(old[p][3] for p in CANVAS)/255;new_area=sum(new[p][3] for p in CANVAS)/255
    assert abs(new_area/old_area-1)<=.01,(name,'covered area changed',old_area,new_area)
    for first,second in ((before,after),(after,before)):
        assert all(any((x+dx,y+dy) in second for dx in (-1,0,1) for dy in (-1,0,1)) for x,y in first),(name,'silhouette moved')
    anchor_error=max(max(abs(a-b) for a,b in zip(old[p],new[p])) for p in ANCHORS)
    # The original unavailable-state tint rounds its halved colors to integers.
    assert anchor_error<=(1 if name=='bad' else 0),(name,'spine or binding changed',anchor_error)
    materials={};features={}
    def check_feature(key,points,kind,position=.2):
        mass,center=feature(original,points,kind);new_mass,new_center=feature(actual,points,kind)
        assert abs(new_mass/mass-1)<=.05 and max(abs(a-b) for a,b in zip(center,new_center))<=position,(name,key,kind,'weight or position changed',mass,new_mass,center,new_center)
        features[key+'-'+kind]=dict(original_mass=mass,reconstructed_mass=new_mass,original_center=center,reconstructed_center=new_center)
    for key,polygon in SURFACES.items():
        points=region(polygon);error=regional_error(original,actual,points);materials[key]=error
        limits=(6,12,70,3) if name=='bad' else (8,14,70,3)
        assert all(error[field]<=limit for field,limit in zip(('mean','rms','maximum','channel_mean_difference'),limits)),(name,key,'leather material changed',error)
        for kind in ('warmth','neutral'):check_feature(key,points,kind)
    for key,(polygon,limits) in BANDS.items():
        points=region(polygon);error=regional_error(original,actual,points);materials[key]=error
        assert all(error[field]<=limit for field,limit in zip(('mean','rms','maximum','channel_mean_difference'),limits)),(name,key,'fold or bevel material changed',error)
        if key!='top-bevel':check_feature(key,points,'muted-darkness' if name=='bad' else 'darkness')
        if key!='bottom-edge':check_feature(key,points,'neutral',.25 if key=='top-bevel' else .2)
    check_feature('cast-shadow',shadow,'alpha')
    binding=[(x,y) for y in range(9,36) for x in range(27,31)];check_feature('binding',binding,'neutral')
    ink=[]
    for x,y in INK_POINTS:
        sample=min(higher.crop((x*8+1,y*8+1,x*8+7,y*8+7)).getdata(),key=lambda rgba:max(rgba[:3]));r,g,b,a=sample
        low,high,tolerance=(4,13,1) if name=='bad' else (8,25,2)
        assert a==255 and low<=r-g<=high and abs(g-b)<=tolerance,(name,'maroon fold ink changed',x,y,sample)
        ink.append(dict(point=[x,y],rgba=sample))
    for key,box in DETAILS.items():assert_not_enlarged([actual.crop(box),higher.crop(tuple(v*8 for v in box))],name+' '+key)
    return dict(outline_difference_pixels=outline,original_alpha_area=old_area,reconstructed_alpha_area=new_area,spine_and_binding_landmarks=len(ANCHORS),maximum_anchor_difference=anchor_error,material_errors=materials,features=features,maroon_crease_samples=ink)


def run(artifacts,source=None,images=None):
    source=source or Path(__file__).resolve().parents[2]/'Applications/Artwork/Folder.svg'
    art=Artwork(source);assert_curve_arguments(art.root);originals={name:artwork_original('folders',name) for name in NAMES}
    closed=originals['closed'][0];unavailable=originals['bad'][0];old=closed.load();bad=unavailable.load()
    shadow=[p for p in CANVAS if 0<old[p][3]<200 and sum(old[p][:3])<3]
    tint_error=0
    for p in CANVAS:
        assert abs(old[p][3]-bad[p][3])<=1,('Original unavailable alpha relationship changed',p)
        if old[p][3]>=32:tint_error=max(tint_error,max(abs(int(c*.5+85)-b) for c,b in zip(old[p][:3],bad[p][:3])))
    assert tint_error<=3,('Original unavailable tint relationship changed',tint_error)
    cases={};frames={};rejected=[]
    for name in NAMES:
        original,fixture=originals[name];actual=art.render(name,48);higher=art.render(name,384);cases[name]=compare(name,original,actual,higher,shadow);frames[name]=(actual,higher)
        if images:assert_svg_representations(art,name,images/(name+'.tiff'),(48,48))
        shifted=Image.new('RGBA',actual.size);shifted.paste(actual,(1,0));gray=ImageOps.grayscale(actual).convert('RGBA');gray.putalpha(actual.getchannel('A'));controls=[('translated',shifted,higher),('desaturated',gray,higher)]
        for key,box in DETAILS.items():
            missing=actual.copy();missing.paste((0,0,0,0),box);controls.append(('missing-'+key,missing,higher))
            large=higher.copy();x,y,r,b=box;large.paste(actual.crop(box).resize(((r-x)*8,(b-y)*8),Image.Resampling.NEAREST),(x*8,y*8));controls.append(('traced-'+key,actual,large))
        missing=actual.copy()
        for p in shadow:missing.putpixel(p,(0,0,0,0))
        controls.append(('missing-shadow',missing,higher));missing=actual.copy();missing.paste((0,0,0,0),(7,20,9,42));controls.append(('missing-spine',missing,higher))
        green=higher.copy()
        x,y,r,b=DETAILS['fold']
        for py in range(y*8,b*8):
            for px in range(x*8,r*8):
                red,g,blue,alpha=green.getpixel((px,py))
                if alpha==255 and red<(130 if name=='bad' else 90):green.putpixel((px,py),(red,max(red-1,0),max(red-30,0),alpha))
        controls.append(('olive-fold-ink',actual,green))
        controls.extend([('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))])
        for label,candidate,large in controls:
            try:compare(name,original,candidate,large,shadow)
            except AssertionError:rejected.append(name+'-'+label)
            else:raise AssertionError(('Unfaithful folder accepted',name,label))
        cases[name]['original_source_sha256']=fixture['source_sha256']
    repository=Path(__file__).resolve().parents[2];group=json.loads((repository/'Tests/Wayland/artwork-originals/manifest.json').read_text())['folders'];closed_pixels=hashlib.sha256(closed.tobytes()).hexdigest()
    for case in group['aliases'].values():
        assert case['reference']=='closed' and hashlib.sha256((repository/case['source']).read_bytes()).hexdigest()==case['source_sha256']
        assert case['pixel_sha256']==closed_pixels
    artifacts.mkdir(parents=True)
    for name,(actual,higher) in frames.items():actual.save(artifacts/(name+'-100.png'));higher.save(artifacts/(name+'-800.png'))
    result=dict(passed=True,cases=cases,rejected_mutations=rejected,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),suite_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),closed_resource_paths=1+len(group['aliases']),original_unavailable_tint_maximum_error=tint_error,submitted_images_verified=images is not None,native_density_qualification=False,open_and_deposit_qualified=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True);parser.add_argument('--source',type=Path);parser.add_argument('--images',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.images)
