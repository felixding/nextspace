"""Check the original speaker cabinet, recessed grille and two illuminated cones."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import assert_not_enlarged,assert_svg_representations,preferences_original,regional_error


DRIVERS=((16,12,28,23),(14,24,31,38))


def compare(original,actual,higher):
    assert original.size==actual.size==(44,46) and higher.size==(352,368)
    assert_not_enlarged([actual,higher],'Sound')
    old,new=original.load(),actual.load();points=[(x,y) for y in range(46) for x in range(44)]
    outline=len({p for p in points if old[p][3]>=128}^{p for p in points if new[p][3]>=128})
    assert outline<=4,('Sound silhouette changed',outline)
    old_area=sum(old[p][3]/255 for p in points);new_area=sum(new[p][3]/255 for p in points)
    assert abs(old_area-new_area)<=1,('Sound body/shadow opacity changed',old_area,new_area)
    allowed={(x+dx,y+dy) for x,y in points if old[x,y][3] for dx in (-1,0,1) for dy in (-1,0,1)}
    assert all(p in allowed for p in points if new[p][3]>12),'Sound cabinet or shadow moved'
    gray={(7,y) for y in range(7,42)}|{(x,2) for x in range(12,31)}|{(14-y,y) for y in range(3,7)}|{(x,6) for x in range(12,33)}
    white={p for p in points if old[p]==(255,255,255,255)}
    black={(31,y) for y in range(10,40)}|{(x,39) for x in range(12,31)}
    blue={(35,y) for y in range(7,42) if old[35,y]==(0,0,34,255)}|{(x,41) for x in range(9,36)}
    assert (len(gray),len(white),len(black),len(blue))==(79,65,49,52)
    assert all(old[p]==new[p] for p in gray|white|black|blue),'Sound frame or aperture changed'
    assert all(new[x,y][3]==old[x,y][3]==255 for y in range(7,41) for x in range(8,35)), 'Sound face opacity changed'
    face={(x,y) for y in (8,40) for x in range(9,34)}|{(x,y) for y in range(9,40) for x in (9,10,33)}
    face_error=regional_error(original,actual,face)
    assert face_error['mean']<=6.5 and face_error['rms']<=10 and face_error['maximum']<=48,('Sound cabinet lighting changed',face_error)
    grille=[]
    for y in range(10,39):
        for x in range(12,31):
            if ((x+.5-22)/4.5)**2+((y+.5-17.5)/4.5)**2<1 or ((x+.5-22.5)/6.5)**2+((y+.5-30.5)/6)**2<1:continue
            grille.append((x,y))
    grille_error=regional_error(original,actual,grille)
    assert grille_error['mean']<=7 and grille_error['rms']<=10 and grille_error['maximum']<=34,('Sound grille palette changed',grille_error)
    patches=[]
    for top,bottom in ((10,14),(21,25),(36,39)):
        patch=[p for p in grille if top<=p[1]<bottom]
        result=regional_error(original,actual,patch)
        assert result['channel_mean_difference']<=3,('Sound grille illumination changed',top,result)
        patches.append(result['channel_mean_difference'])
    def feature(pixels,box,light):
        x0,y0,x1,y1=box
        values=[]
        for y in range(y0,y1):
            for x in range(x0,x1):
                value=sum(pixels[x,y][:3])/3
                weight=max(value-80,0) if light else max(32-value,0)
                values.append((x,y,weight))
        mass=sum(w for x,y,w in values);assert mass>0,'Sound driver disappeared'
        center=[sum((x if axis==0 else y)*w for x,y,w in values)/mass for axis in (0,1)]
        return mass,center
    drivers=[]
    for index,box in enumerate(DRIVERS):
        x0,y0,x1,y1=box;region=[(x,y) for y in range(y0,y1) for x in range(x0,x1)]
        result=regional_error(original,actual,region)
        assert result['mean']<=7 and result['rms']<=12 and result['maximum']<=75,('Sound driver material changed',index,result)
        features={}
        for label,light in (('highlight',True),('shadow',False)):
            mass,center=feature(old,box,light);new_mass,new_center=feature(new,box,light)
            assert abs(new_mass/mass-1)<=.05 and max(abs(a-b) for a,b in zip(center,new_center))<=.1,('Sound driver proportions or placement changed',index,label,mass,new_mass,center,new_center)
            features[label]=dict(original_mass=mass,reconstructed_mass=new_mass,original_center=center,reconstructed_center=new_center)
        assert_not_enlarged([actual.crop(box),higher.crop(tuple(v*8 for v in box))],'Sound driver '+str(index))
        drivers.append(dict(error=result,**features))
    pixels=higher.load();values=[pixels[268,y][:3] for y in range(80,312)]
    changes=sum(a!=b for a,b in zip(values,values[1:]));step=max(abs(a-b) for p,q in zip(values,values[1:]) for a,b in zip(p,q))
    assert changes>40 and step<=2,'Sound cabinet shading traces the source grid'
    alpha=[pixels[292,y][3] for y in range(316,340)]
    shadow_step=max(abs(a-b) for a,b in zip(alpha,alpha[1:]))
    assert max(alpha)-min(alpha)>=40 and shadow_step<=8,('Sound shadow traces the source grid',len(set(alpha)),shadow_step)
    return dict(outline_difference_pixels=outline,original_alpha_area=old_area,reconstructed_alpha_area=new_area,
        exact_gray_frame_pixels=len(gray),exact_white_highlights=len(white),exact_black_aperture_pixels=len(black),exact_blue_edge_pixels=len(blue),
        face_error=face_error,grille_error=grille_error,grille_patch_channel_mean_difference=patches,drivers=drivers,
        high_density_cabinet_transitions=changes,high_density_cabinet_maximum_step=step,
        high_density_shadow_levels=len(set(alpha)),high_density_shadow_maximum_step=shadow_step)


def run(artifacts,source=None,image=None):
    source=source or Path(__file__).resolve().parents[2]/'Applications/Preferences/Artwork.svg'
    original,fixture=preferences_original('Sound');art=Artwork(source)
    actual,higher=art.render('Sound',(44,46)),art.render('Sound',(352,368));result=compare(original,actual,higher)
    if image:assert_svg_representations(art,'Sound',image,(44,46))
    shifted=Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
    gray=ImageOps.grayscale(actual).convert('RGBA');gray.putalpha(actual.getchannel('A'))
    missing=[]
    for box in DRIVERS:
        candidate=actual.copy();candidate.paste((38,35,43,255),box);missing.append(candidate)
    moved=actual.copy();moved.paste((38,35,43,255),(19,15,25,21));moved.paste(actual.crop((19,15,25,21)),(20,15))
    frame=actual.copy();frame.paste((221,221,221,255),(8,10,9,40))
    edge=actual.copy();edge.paste((34,34,34,255),(35,8,36,40))
    flat=actual.copy();flat.paste((190,190,190,255),(9,10,11,39))
    cloth=actual.copy()
    for y in range(10,39):
        for x in range(12,31):
            if ((x+.5-22)/4.5)**2+((y+.5-17.5)/4.5)**2>=1 and ((x+.5-22.5)/6.5)**2+((y+.5-30.5)/6)**2>=1:cloth.putpixel((x,y),(40,40,40,255))
    def trace(box):
        large=higher.copy();x,y,r,b=box;large.paste(actual.crop(box).resize(((r-x)*8,(b-y)*8),Image.Resampling.NEAREST),(x*8,y*8));return large
    controls=[('translated',shifted,higher),('desaturated',gray,higher),('missing-tweeter',missing[0],higher),('missing-woofer',missing[1],higher),
        ('driver-moved',moved,higher),('highlight-darkened',frame,higher),('edge-palette',edge,higher),('flat-cabinet',flat,higher),('flat-grille',cloth,higher),
        ('traced-tweeter',actual,trace(DRIVERS[0])),('traced-woofer',actual,trace(DRIVERS[1])),
        ('traced-cabinet-shading',actual,trace((32,10,34,39))),('traced-shadow',actual,trace((36,36,40,43))),
        ('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))]
    rejected=[]
    for name,candidate,large in controls:
        try:compare(original,candidate,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful Sound design accepted',name))
    artifacts.mkdir(parents=True);actual.save(artifacts/'candidate-100.png');higher.save(artifacts/'candidate-800.png')
    result.update(passed=True,rejected_mutations=rejected,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],submitted_image_verified=image is not None,native_density_qualification=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--source',type=Path);parser.add_argument('--image',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.image)
