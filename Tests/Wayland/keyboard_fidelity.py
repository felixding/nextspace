"""Check Keyboard geometry, key layout and lighting against the selected TIFF."""
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
    assert original.size==actual.size==(66,57) and higher.size==(528,456)
    assert_not_enlarged([actual,higher],'Keyboard')
    points=[(x,y) for y in range(57) for x in range(66)]
    old,new=original.load(),actual.load()
    solid=lambda pixels:{p for p in points if pixels[p][3]>=128}
    outline=len(solid(old)^solid(new))
    assert outline<=4,('Keyboard silhouette changed',outline)
    old_area=sum(old[p][3]/255 for p in points);new_area=sum(new[p][3]/255 for p in points)
    assert abs(old_area-new_area)<=1,('Keyboard opacity changed',old_area,new_area)
    allowed={(x+dx,y+dy) for x,y in points if old[x,y][3] for dx in (-1,0,1) for dy in (-1,0,1)}
    assert all(p in allowed for p in points if new[p][3]>12),'Keyboard cable or chassis moved'
    assert all(new[x,y][3]==old[x,y][3]==240 for y in range(19,41) for x in range(4,62)), 'Keyboard face opacity changed'
    frame={(x,17) for x in range(2,63) if x not in (31,32,33)}
    frame|={(2,y) for y in range(18,41)}|{(x,18) for x in range(3,62)}
    frame|={(3,y) for y in range(19,39)}|{(62,y) for y in range(19,41)}
    frame|={(x,41) for x in range(6,62)}|{(62,18),(63,18)}
    assert len(frame)==240 and all(new[p]==old[p] for p in frame),'Keyboard frame or bevel changed'
    keyboard={(x,y) for y in range(23,39) for x in (*range(6,45),*range(47,59))}
    black={p for p in keyboard if old[p]==(0,0,0,240)}
    white={p for p in keyboard if old[p]==(255,255,255,240)}
    assert len(black)==240 and len(white)==68
    assert {p for p in keyboard if new[p]==(0,0,0,240)}==black,'Keyboard key layout or black faces changed'
    assert {p for p in keyboard if new[p]==(255,255,255,240)}==white,'Keyboard key highlights changed'
    indicators={(x,y) for y in range(23,26) for x in range(47,59) if min(old[x,y][:3])>=150}
    assert len(indicators)==6
    assert {(x,y) for y in range(23,26) for x in range(47,59) if min(new[x,y][:3])>=150}==indicators,'Keyboard indicators moved'
    def error(region):
        return regional_error(original,actual,region)
    key_error=error(keyboard)
    assert key_error['mean']<=3.8 and key_error['rms']<=6 and key_error['maximum']<=24,('Keyboard cap palette changed',key_error)
    face={(x,y) for y in (*range(19,23),26,39) for x in range(4,61)}
    face|={(x,y) for y in range(23,39) for x in (4,5,45,46,59,60)}
    face_error=error(face)
    assert face_error['mean']<=5.5 and face_error['rms']<=8.5 and face_error['maximum']<=40,('Keyboard face lighting changed',face_error)
    cable_error=error([(x,y) for y in range(4,18) for x in range(30,39)])
    assert cable_error['mean']<=7 and cable_error['rms']<=20 and cable_error['maximum']<=100,('Keyboard cable changed',cable_error)
    pixels=higher.load();minimum_levels=1000;maximum_step=0
    for x,y in white:
        height=next(at+1 for at in range(2,6) if old[x+1,y+at]==(0,0,0,240))
        values=[pixels[x*8+12,v][:3] for v in range(y*8,(y+height)*8)]
        levels=len(set(values));step=max(abs(a-b) for p,q in zip(values,values[1:]) for a,b in zip(p,q))
        minimum_levels=min(minimum_levels,levels);maximum_step=max(maximum_step,step)
        assert levels>=14 and step<=18,('Keyboard cap shading traces source pixels',x,y,levels,step)
    values=[pixels[x,164][:3] for x in range(40,488)]
    changes=[x for x,(a,b) in enumerate(zip(values,values[1:]),40) if a!=b]
    step=max(abs(a-b) for p,q in zip(values,values[1:]) for a,b in zip(p,q))
    assert step<=2 and len(changes)>50 and sum((x+1)%8!=0 for x in changes)>len(changes)*.5,'Keyboard face traces dither cells'
    return dict(outline_difference_pixels=outline,original_alpha_area=old_area,reconstructed_alpha_area=new_area,
        exact_frame_pixels=len(frame),exact_black_key_pixels=len(black),exact_white_key_pixels=len(white),indicator_pixels=len(indicators),
        key_error=key_error,face_error=face_error,cable_error=cable_error,
        high_density_cap_minimum_levels=minimum_levels,high_density_cap_maximum_step=maximum_step,
        high_density_face_transitions=len(changes),high_density_face_maximum_step=step)


def run(artifacts,source=None,image=None):
    source=source or Path(__file__).resolve().parents[2]/'Applications/Preferences/Artwork.svg'
    original,fixture=preferences_original('Keyboard');art=Artwork(source)
    actual,higher=art.render('Keyboard',(66,57)),art.render('Keyboard',(528,456))
    result=compare(original,actual,higher)
    if image:assert_svg_representations(art,'Keyboard',image,(66,57))
    shifted=Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
    gray=ImageOps.grayscale(actual).convert('RGBA');gray.putalpha(actual.getchannel('A'))
    cable=actual.copy();cable.paste((0,0,0,0),(29,4,39,17))
    row=actual.copy();row.paste(actual.crop((6,27,45,30)),(7,27))
    missing=actual.copy();missing.paste((220,230,230,240),(12,27,15,30))
    lights=actual.copy();lights.paste((67,61,105,240),(47,23,59,26))
    flat=actual.copy();flat.paste((220,230,230,240),(4,19,61,23))
    traced=higher.copy();traced.paste(actual.crop((6,27,9,30)).resize((24,24),Image.Resampling.NEAREST),(48,216))
    controls=[('translated',shifted,higher),('desaturated',gray,higher),('missing-cable',cable,higher),
        ('key-row-shift',row,higher),('missing-key',missing,higher),('missing-indicators',lights,higher),('flat-face',flat,higher),
        ('traced-key-shading',actual,traced),('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),
        ('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))]
    rejected=[]
    for name,candidate,large in controls:
        try:compare(original,candidate,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful Keyboard design accepted',name))
    artifacts.mkdir(parents=True)
    actual.save(artifacts/'candidate-100.png');higher.save(artifacts/'candidate-800.png')
    result.update(passed=True,rejected_mutations=rejected,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],submitted_image_verified=image is not None,native_density_qualification=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--source',type=Path);parser.add_argument('--image',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.image)
