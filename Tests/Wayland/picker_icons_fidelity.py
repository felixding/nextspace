"""Protect the original named-color diagram and static color-wheel design."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image,ImageDraw,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original,assert_curve_arguments,assert_not_enlarged,assert_svg_representations,regional_error

NAMES=('GSNamedColorPicker','GSWheelColorPicker')
SIZES=((36,24),(24,24))


def ink(original,actual,points):
    before,after=[[image.getpixel(p)[3] for p in points] for image in (original,actual)]
    masses=[sum(before),sum(after)];assert min(masses)>0,'Missing artwork ink'
    centers=[[sum(p[c]*a for p,a in zip(points,values))/mass for c in (0,1)]
             for values,mass in zip((before,after),masses)]
    return dict(overlap=sum(min(a,b) for a,b in zip(before,after))/sum(max(a,b) for a,b in zip(before,after)),
                mass_ratio=masses[1]/masses[0],center_delta=[b-a for a,b in zip(*centers)])


def compare(name,original,low,high):
    assert low.size==original.size and high.size==(low.width*8,low.height*8)
    assert_not_enlarged([low,high],name)
    if name=='GSNamedColorPicker':
        assert low.crop((0,10,36,24)).tobytes()==original.crop((0,10,36,24)).tobytes(),'Purple swatch or pseudo-text layout/palette changed'
        assert all(low.getpixel((x,y))[:3]==(0,0,0) for y in range(10) for x in range(36) if low.getpixel((x,y))[3]),'Heading recolored'
        letters=[]
        for char,(left,right) in zip('NAMED',[(3,9),(9,14),(14,21),(21,26),(26,32)]):
            points=[(x,y) for y in range(2,10) for x in range(left,right)];check=ink(original,low,points)
            assert check['overlap']>=.72 and abs(check['mass_ratio']-1)<=.03 and max(map(abs,check['center_delta']))<=.3,('Heading contour/weight/placement changed',char,check)
            letters.append(dict(letter=char,**check))
        assert low.getpixel((28,6))[3]<=10,'D counter filled'
        return dict(letters=letters,footer_pixels_identical=504)
    points=[(x,y) for y in range(24) for x in range(24)];shape=ink(original,low,points)
    assert shape['overlap']>=.97 and abs(shape['mass_ratio']-1)<=.02 and max(map(abs,shape['center_delta']))<=.15,('Wheel outline or footprint changed',shape)
    radius=lambda x,y:math.hypot(x+.5-12.333,y+.5-12.333)
    inside=[p for p in points if 1.8<radius(*p)<9.8]
    assert all(low.getpixel(p)[3]==255 for p in inside),'Wheel interior made translucent'
    interior=regional_error(original,low,inside)
    assert interior['mean']<=1.5 and interior['maximum']<=15,('Wheel hue order, saturation or white center changed',interior)
    center=regional_error(original,low,[p for p in points if radius(*p)<1.8])
    assert center['mean']<=3 and center['maximum']<=10 and abs(low.getpixel((12,12))[3]-original.getpixel((12,12))[3])<=6,('Wheel center mark/hole changed',center)
    rim=[]
    for sector in range(8):
        region=[(x,y) for x,y in points if 9.8<radius(x,y)<12.3 and int((math.atan2(y+.5-12.333,x+.5-12.333)%(2*math.pi))/(math.pi/4))==sector]
        check=regional_error(original,low,region)
        assert check['mean']<=17 and check['channel_mean_difference']<=12,('Wheel rim shading/palette changed',sector,check)
        rim.append(check)
    return dict(shape=shape,interior=interior,center=center,rim=rim)


def run(artifacts,source=None,images=None):
    source=source or Path(__file__).resolve().parents[2]/'Libraries/gnustep/Artwork.svg'
    art=Artwork(source);assert_curve_arguments(art.root);artifacts.mkdir(parents=True)
    cases=[]
    for name,size in zip(NAMES,SIZES):
        original,fixture=artwork_original('color-panel',name);low=art.render(name,size);high=art.render(name,tuple(v*8 for v in size))
        check=compare(name,original,low,high)
        if images:
            resource,=images.rglob(name+'.tiff');assert_svg_representations(art,name,resource,size)
        shifted=Image.new('RGBA',size);shifted.paste(low,(1,0));opaque=low.copy();opaque.putalpha(255)
        r,g,b,a=low.split();mutations=[('shifted',shifted,high),('mirrored',ImageOps.mirror(low),high),('opaque-background',opaque,high),('recolored',Image.merge('RGBA',(b,g,r,a)),high)]
        if name=='GSNamedColorPicker':
            for label,box,color in [('missing-swatch',(5,14,8,18),(0,0,0,0)),('missing-bar',(11,14,11,18),(0,0,0,0)),('filled-D-counter',(28,5,28,6),(0,0,0,255))]:
                image=low.copy();ImageDraw.Draw(image).rectangle(box,fill=color);mutations.append((label,image,high))
            hidden=['named-N']
        else:hidden=['picker-wheel-rim-shading','picker-wheel-center-mark','picker-wheel-center-hole']
        for identifier in hidden:
            node=art.symbols[identifier];previous=node.get('opacity');node.set('opacity','0');art.cache.clear()
            mutations.append(('missing-'+identifier,art.render(name,size),high))
            if previous is None:node.attrib.pop('opacity')
            else:node.set('opacity',previous)
            art.cache.clear()
        for method in [Image.Resampling.NEAREST,Image.Resampling.LANCZOS]:mutations.append((method.name.lower()+'-enlargement',low,low.resize(high.size,method)))
        rejected={}
        for label,image,big in mutations:
            try:compare(name,original,image,big)
            except AssertionError as failure:rejected[label]=str(failure)
            else:raise AssertionError('Picker icon mutation accepted: '+name+' '+label)
        assert art.render(name,size).tobytes()==low.tobytes(),'Fidelity mutations changed the master'
        low.save(artifacts/(name+'-base.png'));high.save(artifacts/(name+'-high.png'))
        cases.append(dict(name=name,design=check,original_source_sha256=fixture['source_sha256'],negative_controls=rejected))
    result=dict(passed=True,cases=cases,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),native_display_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Named-color and static wheel originals and negative controls PASS.');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['artifacts','source','images']:p.add_argument('--'+name,type=Path,required=name=='artifacts')
    a=p.parse_args();run(a.artifacts,a.source,a.images)
