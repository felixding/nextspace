"""Compare the original three Localization flags, metal poles and globe contours."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from PIL import Image,ImageDraw,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import assert_curve_arguments,assert_not_enlarged,assert_svg_representations,preferences_original,regional_error


REGIONS={
    'globe':((26,13,45,33),(10,22,8.5)),
    'western-contour':((29,15,34,31),(10,22,5)),
    'inner-contours':((34,16,42,30),(8.5,17,6.5)),
    'blue-flag':((19,8,51,38),(10,23,4)),
    'green-flag':((19,34,45,43),(8,17,4)),
    'orange-flag':((19,39,39,48),(7.5,15,4)),
    'poles':((0,0,17,49),(3.5,8,2)),
    'left-glow':((24,9,29,13),(6,9,8.5)),
    'right-glow':((45,13,49,31),(6,9,8.5)),
    'green-glow':((35,38,40,40),(6,9,8.5)),
    'orange-glow':((32,43,37,45),(6,9,8.5)),
}
CONTOURS={'western':(30,16,34,26),'inner':(34,16,42,30),'right':(41,18,45,30)}
DETAILS={'sphere':(12,0,17,5),'shaft':(13,14,17,33),'crescent':(26,14,30,28),
    'western-contour':(30,16,34,26),'inner-contours':(34,16,42,30),'right-contour':(41,18,45,30),
    'field':(23,9,30,13),'bevel':(34,36,49,37),'shadow':(28,47,37,48)}


def points(box):
    x,y,r,b=box
    return [(px,py) for py in range(y,b) for px in range(x,r)]


def landmarks():
    result={(x,y) for x,start in ((2,17),(8,12),(14,7)) for y in range(start,49)}
    result.update([(1,11),(7,6),(13,1),(19,9),(19,10),(11,41),(11,42)])
    for dx,dy in ((0,0),(-6,5),(-12,10)):
        result.update((17+dx,y+dy) for y in (8,9))
        result.update((18+dx,y+dy) for y in (12,13,30,31,36,37))
        result.update((15+dx,y+dy) for y in (5,6))
    result.update([(12,44),(12,45),(11,43),(11,46),(11,47),(11,48),(6,48),
        (18,38),(18,39),(18,40),(17,38),(19,38)])
    assert len(result)==160
    return result


def ink(image,box,threshold):
    pixels=image.convert('RGBa').load();values=[(x,y,max(pixels[x,y][0]-threshold,0)) for x,y in points(box)]
    mass=sum(w for x,y,w in values);assert mass>0,'Localization globe contour disappeared'
    center=[sum((x if axis==0 else y)*w for x,y,w in values)/mass for axis in (0,1)]
    return mass,center


def compare(original,actual,higher):
    assert original.size==actual.size==(52,49) and higher.size==(416,392)
    assert_not_enlarged([actual,higher],'Localization')
    old,new=original.load(),actual.load();canvas=points((0,0,52,49))
    outline=len({p for p in canvas if old[p][3]>=128}^{p for p in canvas if new[p][3]>=128})
    assert outline<=4,('Localization flag, pole or shadow outline changed',outline)
    old_area=sum(old[p][3]/255 for p in canvas);new_area=sum(new[p][3]/255 for p in canvas)
    assert abs(old_area-new_area)<=1,('Localization coverage changed',old_area,new_area)
    assert all(old[p]==new[p] for p in landmarks()),'Localization metalwork or upper fold changed'
    errors={}
    for name,(box,limits) in REGIONS.items():
        result=regional_error(original,actual,points(box));errors[name]=result
        assert all(result[key]<=limit for key,limit in zip(('mean','rms','channel_mean_difference'),limits)),('Localization geometry or material changed',name,result)
    neck=[(x+dx,y+dy) for dx,dy in ((0,0),(-6,5),(-12,10)) for x in (14,15) for y in (5,6)]
    neck_error=regional_error(original,actual,neck)
    assert neck_error['mean']<=4 and neck_error['rms']<=7 and neck_error['maximum']<=18,('Localization neck material changed',neck_error)
    caps=[]
    for dx,dy in ((0,0),(-6,5),(-12,10)):
        region=points((12+dx,dy,17+dx,5+dy));result=regional_error(original,actual,region)
        assert result['mean']<=10 and result['rms']<=16 and result['maximum']<=60,('Localization sphere changed',dx,result)
        solid=[p for p in region if old[p][3]>=128]
        before=sum(old[p][2]-old[p][0] for p in solid)/len(solid);after=sum(new[p][2]-new[p][0] for p in solid)/len(solid)
        assert abs(before-after)<=5,('Localization sphere tint changed',before,after)
        caps.append(dict(error=result,original_blue_tint=before,reconstructed_blue_tint=after))
    features={}
    for name,box,threshold,center_limit in [('crescent',(25,13,34,31),200,.1)]+[(name,box,25,.25) for name,box in CONTOURS.items()]:
        mass,center=ink(original,box,threshold);new_mass,new_center=ink(actual,box,threshold)
        assert abs(new_mass/mass-1)<=.05 and max(abs(a-b) for a,b in zip(center,new_center))<=center_limit,('Localization contour weight or position changed',name,mass,new_mass,center,new_center)
        features[name]=dict(original_mass=mass,reconstructed_mass=new_mass,original_center=center,reconstructed_center=new_center)
    for name,box in DETAILS.items():
        assert_not_enlarged([actual.crop(box),higher.crop(tuple(v*8 for v in box))],'Localization '+name)
    high=higher.convert('RGBa').load();values=[high[x,76][:3] for x in range(168,248)]
    transitions=sum(p!=q for p,q in zip(values,values[1:]));step=max(abs(a-b) for p,q in zip(values,values[1:]) for a,b in zip(p,q))
    assert transitions>=30 and step<=5,('Localization face lighting traces the raster grid',transitions,step)
    alpha=[high[x,380][3] for x in range(224,288)]
    levels=len(set(alpha));alpha_step=max(abs(a-b) for a,b in zip(alpha,alpha[1:]))
    assert levels>=45 and alpha_step<=5,('Localization shadow traces the raster grid',levels,alpha_step)
    return dict(outline_difference_pixels=outline,original_alpha_area=old_area,reconstructed_alpha_area=new_area,
        exact_landmark_pixels=160,exact_white_shaft_pixels=111,material_errors=errors,neck_error=neck_error,sphere_errors=caps,contours=features,
        high_density_field_transitions=transitions,high_density_field_maximum_step=step,
        high_density_shadow_levels=levels,high_density_shadow_maximum_step=alpha_step)


def run(artifacts,source=None,image=None):
    source=source or Path(__file__).resolve().parents[2]/'Applications/Preferences/Artwork.svg'
    original,fixture=preferences_original('Localization');art=Artwork(source);assert_curve_arguments(art.root)
    actual,higher=art.render('Localization',(52,49)),art.render('Localization',(416,392));result=compare(original,actual,higher)
    if image:assert_svg_representations(art,'Localization',image,(52,49))
    assert_curve_arguments(ET.fromstring('<svg><path d="M.5 -.25 c1e0 -2 3 4 5 6 7 8 9 10 11 12 q2 2 3 3 t4 4 s1 2 3 4"/></svg>'))
    curve_rejected=[]
    for command in ('C0 0 1 1 2','S0 0 1','Q32 16.231 17.3','T0'):
        try:assert_curve_arguments(ET.fromstring('<svg><path d="M0 0 '+command+'"/></svg>'))
        except AssertionError:curve_rejected.append(command[0])
        else:raise AssertionError(('Truncated curve accepted',command))
    def paint(box,color):
        im=actual.copy();im.paste(color,box);return im
    shifted=Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
    gray=ImageOps.grayscale(actual).convert('RGBA');gray.putalpha(actual.getchannel('A'))
    sphere=actual.copy()
    for box in ((12,0,17,5),(6,5,11,10),(0,10,5,15)):
        patch=sphere.crop(box);g=ImageOps.grayscale(patch).convert('RGBA');g.putalpha(patch.getchannel('A'));sphere.paste(g,box[:2])
    neck=paint((14,5,15,7),(255,255,255,240))
    changed=actual.copy()
    for p in points((17,13,45,43)):
        r,g,b,a=changed.getpixel(p)
        if g>r*2 and g>b*2:changed.putpixel(p,(g,r,b,a))
    graticule=paint(CONTOURS['inner'],(0,85,119,240));draw=ImageDraw.Draw(graticule)
    draw.ellipse((34,17,41,28),outline=(153,153,153,240),width=1)
    for y in (20,23,26):draw.line((34,y,41,y),fill=(153,153,153,240))
    moved=paint((26,15,30,28),(0,153,204,240));moved.paste(actual.crop((26,15,30,28)),(27,15))
    controls=[('translated',shifted,higher),('desaturated',gray,higher),('missing-pole',paint((13,7,17,49),(0,0,0,0)),higher),
        ('missing-sphere',paint((12,0,17,5),(0,0,0,0)),higher),('sphere-tint',sphere,higher),('neck-highlight',neck,higher),
        ('binding-variant',paint((12,44,13,46),(255,255,255,240)),higher),('flag-palette',changed,higher),
        ('flat-face',paint((23,9,30,13),(0,153,204,240)),higher),
        ('missing-inner-contours',paint(CONTOURS['inner'],(0,85,119,240)),higher),('generic-graticule',graticule,higher),
        ('missing-western-contour',paint(CONTOURS['western'],(0,85,119,240)),higher),
        ('missing-right-contour',paint(CONTOURS['right'],(0,85,119,240)),higher),('crescent-moved',moved,higher),
        ('missing-shadow',paint((26,47,39,48),(0,0,0,0)),higher),('flat-shadow',paint((26,47,39,48),(0,0,0,128)),higher),
        ('rear-corner-filled',paint((19,44,23,47),(153,85,0,240)),higher),('missing-bevel',paint((22,46,38,47),(221,119,0,240)),higher)]
    for name,box in DETAILS.items():
        large=higher.copy();x,y,r,b=box;large.paste(actual.crop(box).resize(((r-x)*8,(b-y)*8),Image.Resampling.NEAREST),(x*8,y*8));controls.append(('traced-'+name,actual,large))
    controls.extend([('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))])
    rejected=[]
    for name,candidate,large in controls:
        try:compare(original,candidate,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful Localization design accepted',name))
    artifacts.mkdir(parents=True);actual.save(artifacts/'candidate-100.png');higher.save(artifacts/'candidate-800.png')
    result.update(passed=True,rejected_mutations=rejected,rejected_curve_mutations=curve_rejected,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),original_source_sha256=fixture['source_sha256'],
        submitted_image_verified=image is not None,native_density_qualification=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--source',type=Path);parser.add_argument('--image',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.image)
