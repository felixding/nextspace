"""Protect the original Mouse silhouette, button joints and illuminated faces."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import assert_not_enlarged,assert_svg_representations,preferences_original,regional_error


def compare(original,actual,higher):
    assert original.size==actual.size==(44,44) and higher.size==(352,352)
    assert_not_enlarged([actual,higher],'Mouse')
    old,new=original.load(),actual.load();points=[(x,y) for y in range(44) for x in range(44)]
    outline=len({p for p in points if old[p][3]>=128}^{p for p in points if new[p][3]>=128})
    assert outline<=4,('Mouse silhouette changed',outline)
    old_area=sum(old[p][3]/255 for p in points);new_area=sum(new[p][3]/255 for p in points)
    assert abs(old_area-new_area)<=1,('Mouse opacity changed',old_area,new_area)
    allowed={(x+dx,y+dy) for x,y in points if old[x,y][3] for dx in (-1,0,1) for dy in (-1,0,1)}
    assert all(p in allowed for p in points if new[p][3]>12),'Mouse shape or cable moved'
    gray={(12,y) for y in range(11,34)}|{(x,11) for x in range(12,31) if x not in (20,21,22)}
    white={(x,y) for y in range(12,19) for x in (13,14)}|{(x,y) for y in range(20,34) for x in (13,14)}
    white|={(x,y) for y in (12,13) for x in (*range(15,21),*range(22,29))}|{(x,20) for x in range(15,29)}
    black={(30,y) for y in range(13,33)}
    assert len(gray)==38 and len(white)==82 and len(black)==20
    assert all(new[p]==old[p] for p in gray|white|black),'Mouse frame, highlights or black edge changed'
    upper=[(x,y) for y in range(14,19) for x in (*range(15,21),*range(23,29))]
    palm=[(x,y) for y in range(21,34) for x in range(15,29)]
    assert all(old[p][3]==new[p][3]==240 for p in upper+palm),'Mouse face opacity changed'
    def error(region):
        return regional_error(original,actual,region)
    upper_error,palm_error=error(upper),error(palm)
    assert upper_error['mean']<=4.5 and upper_error['rms']<=6.5 and upper_error['maximum']<=24 and upper_error['channel_mean_difference']<=2.5,('Mouse button lighting changed',upper_error)
    assert palm_error['mean']<=5 and palm_error['rms']<=7 and palm_error['maximum']<=24 and palm_error['channel_mean_difference']<=2.5,('Mouse palm lighting changed',palm_error)
    divider=error([(21,y) for y in range(12,19)])
    joint=error([(x,19) for x in range(14,30)])
    assert divider['mean']<=4.5 and divider['maximum']<=24 and joint['mean']<=5 and joint['maximum']<=20,'Mouse button divisions changed'
    cable=error([(x,y) for y in range(3,9) for x in range(19,35)])
    lower=error([(x,y) for y in range(34,39) for x in range(12,32)])
    assert cable['mean']<=9 and cable['rms']<=20 and cable['maximum']<=100,('Mouse cable material changed',cable)
    assert lower['mean']<=8 and lower['rms']<=17 and lower['maximum']<=120,('Mouse lower bevel changed',lower)
    pixels=higher.load();curves={}
    for name,(left,top,right,bottom) in dict(cable=(152,24,280,72),lower=(88,264,256,312)).items():
        edges=[(x,y) for y in range(top,bottom) for x in range(left,right) if pixels[x,y][3]>=128 and
            any(pixels[x+dx,y+dy][3]<128 for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)))]
        free=sum(x%8 not in (0,7) and y%8 not in (0,7) for x,y in edges)
        assert free>=30,('Mouse outline traces source pixels',name,len(edges),free)
        curves[name]=dict(edge_pixels=len(edges),away_from_original_grid=free)
    values=[pixels[x,204][:3] for x in range(124,232)]
    changes=[x for x,(a,b) in enumerate(zip(values,values[1:]),124) if a!=b]
    step=max(abs(a-b) for p,q in zip(values,values[1:]) for a,b in zip(p,q))
    assert step<=2 and len(changes)>35 and sum((x+1)%8!=0 for x in changes)>len(changes)*.5,'Mouse lighting traces dither cells'
    return dict(outline_difference_pixels=outline,original_alpha_area=old_area,reconstructed_alpha_area=new_area,
        exact_gray_frame_pixels=len(gray),exact_white_highlights=len(white),exact_black_edge_pixels=len(black),
        upper_error=upper_error,palm_error=palm_error,divider_error=divider,joint_error=joint,cable_error=cable,lower_error=lower,
        high_density_curves=curves,high_density_face_transitions=len(changes),high_density_face_maximum_step=step)


def run(artifacts,source=None,image=None):
    source=source or Path(__file__).resolve().parents[2]/'Applications/Preferences/Artwork.svg'
    original,fixture=preferences_original('Mouse');art=Artwork(source)
    actual,higher=art.render('Mouse',(44,44)),art.render('Mouse',(352,352));result=compare(original,actual,higher)
    if image:assert_svg_representations(art,'Mouse',image,(44,44))
    shifted=Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
    gray=ImageOps.grayscale(actual).convert('RGBA');gray.putalpha(actual.getchannel('A'))
    cable=actual.copy();cable.paste((0,0,0,0),(19,3,35,9))
    divider=actual.copy();divider.paste((255,255,255,240),(21,12,22,19));divider.paste(actual.crop((21,12,22,19)),(20,12))
    joint=actual.copy();joint.paste(actual.crop((13,20,30,21)),(13,19));joint.paste(actual.crop((13,19,30,20)),(13,20))
    flat=actual.copy();flat.paste((195,198,195,240),(15,21,29,34))
    highlight=actual.copy();highlight.paste((221,221,221,240),(13,21,14,34))
    def trace(box):
        large=higher.copy();x,y,right,bottom=box
        large.paste(actual.crop(box).resize(((right-x)*8,(bottom-y)*8),Image.Resampling.NEAREST),(x*8,y*8));return large
    controls=[('translated',shifted,higher),('desaturated',gray,higher),('missing-cable',cable,higher),
        ('divider-moved',divider,higher),('joint-moved',joint,higher),('flat-face',flat,higher),('highlight-darkened',highlight,higher),
        ('traced-cable',actual,trace((19,3,35,9))),('traced-lower-outline',actual,trace((11,33,32,39))),
        ('traced-face-shading',actual,trace((15,21,29,34))),
        ('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),
        ('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))]
    rejected=[]
    for name,candidate,large in controls:
        try:compare(original,candidate,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful Mouse design accepted',name))
    artifacts.mkdir(parents=True);actual.save(artifacts/'candidate-100.png');higher.save(artifacts/'candidate-800.png')
    result.update(passed=True,rejected_mutations=rejected,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],submitted_image_verified=image is not None,native_density_qualification=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--source',type=Path);parser.add_argument('--image',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.image)
