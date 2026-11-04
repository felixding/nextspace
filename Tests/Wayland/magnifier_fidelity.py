"""Protect the original magnifier's rim, split crosshair and shaded handle."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image,ImageDraw,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original,assert_curve_arguments,assert_not_enlarged,assert_svg_representations


def brown(image):
    weights={(x,y):max(0,min(r,g)-b)*a/255 for y in range(32) for x in range(32)
             for r,g,b,a in [image.getpixel((x,y))]}
    mass=sum(weights.values());assert mass>0,'Missing brown handle'
    center=[sum((p[c]+.5)*w for p,w in weights.items())/mass for c in (0,1)]
    xx=sum(w*(p[0]+.5-center[0])**2 for p,w in weights.items())
    yy=sum(w*(p[1]+.5-center[1])**2 for p,w in weights.items())
    xy=sum(w*(p[0]+.5-center[0])*(p[1]+.5-center[1]) for p,w in weights.items())
    angle=math.degrees(math.atan2(2*xy,xx-yy)/2)
    return mass,center,angle


def compare(original,low,high):
    assert original.size==low.size==(32,32) and high.size==(256,256)
    a,b=[list(im.getchannel('A').tobytes()) for im in (original,low)]
    overlap=sum(min(x,y) for x,y in zip(a,b))/sum(max(x,y) for x,y in zip(a,b))
    ratio=sum(b)/sum(a)
    error=sum(abs(x-y) for x,y in zip(original.convert('RGBa').tobytes(),low.convert('RGBa').tobytes()))/4096
    assert overlap>=.90 and abs(ratio-1)<=.03 and error<=1.65,('Magnifier silhouette or weight changed',overlap,ratio,error)
    boxes=[im.getchannel('A').point(lambda a:255 if a>16 else 0).getbbox() for im in (original,low)]
    assert max(abs(x-y) for x,y in zip(*boxes))<=1,'Magnifier footprint changed'
    counter=[(x,y) for y in range(32) for x in range(32) if math.hypot(x+.5-12.5,y+.5-12.2)<7.5]
    delta=[abs(original.getpixel(p)[3]-low.getpixel(p)[3]) for p in counter]
    assert max(delta)<=14 and sum(delta)/len(delta)<=1.5,'Crosshair width, position or center gap changed'
    for point in [(9,9),(15,7),(8,16),(17,15)]:assert low.getpixel(point)[3]<=5,'Transparent lens filled'
    ring=[(x,y) for y in range(32) for x in range(32) if 7.5<math.hypot(x+.5-12.5,y+.5-12.2)<12
          and abs(x+.5-12.5)>1.6 and abs(y+.5-12.5)>1.6 and not(x>17 and y>16)]
    before,after=[[im.getpixel(p)[3] for p in ring] for im in (original,low)]
    ring_overlap=sum(min(x,y) for x,y in zip(before,after))/sum(max(x,y) for x,y in zip(before,after))
    assert ring_overlap>=.87 and abs(sum(after)/sum(before)-1)<=.05,'Rim contour or ink weight changed'
    mass,center,angle=brown(original);weight,position,direction=brown(low)
    assert (abs(weight/mass-1)<=.05 and max(abs(a-b) for a,b in zip(center,position))<=.15 and abs(angle-direction)<=1), \
        ('Handle material, placement or angle changed',weight/mass,center,position,angle,direction)
    zones=[]
    for box in [(20,19,23,22),(23,22,27,26),(27,26,30,28),(28,27,31,30)]:
        left,top,right,bottom=box;points=[(x,y) for y in range(top,bottom) for x in range(left,right)]
        aa,bb=[im.convert('RGBa') for im in (original,low)]
        difference=[sum(bb.getpixel(p)[c]-aa.getpixel(p)[c] for p in points)/len(points) for c in range(3)]
        assert max(map(abs,difference))<=8,('Handle shaft, dark band or tip shading changed',box,difference)
        zones.append(dict(box=box,mean_associated_channel_delta=difference))
    assert_not_enlarged([low,high],'MagnifyGlass')
    return dict(weighted_alpha_overlap=overlap,alpha_mass_ratio=ratio,premultiplied_mean_error=error,
                crosshair_maximum_alpha_difference=max(delta),crosshair_mean_alpha_difference=sum(delta)/len(delta),
                rim_alpha_overlap=ring_overlap,brown_mass_ratio=weight/mass,brown_center_delta=[b-a for a,b in zip(center,position)],
                handle_angle_delta=direction-angle,material_zones=zones)


def run(artifacts,source=None,image=None):
    source=source or Path(__file__).resolve().parents[2]/'Libraries/gnustep/Artwork.svg'
    art=Artwork(source);assert_curve_arguments(art.root);artifacts.mkdir(parents=True)
    original,fixture=artwork_original('color-panel','MagnifyGlass')
    low,high=[art.render('MagnifyGlass',(size,size)) for size in (32,256)]
    design=compare(original,low,high)
    if image:assert_svg_representations(art,'MagnifyGlass',image,(32,32))
    shifted=Image.new('RGBA',low.size);shifted.paste(low,(1,0))
    opaque=low.copy();opaque.putalpha(255)
    r,g,b,a=low.split();palette=Image.merge('RGBA',(b,g,r,a))
    closed=low.copy();ImageDraw.Draw(closed).rectangle((12,11,13,13),fill=(0,0,0,128))
    mutations=[('shifted',shifted,high),('mirrored',ImageOps.mirror(low),high),('opaque',opaque,high),
               ('recolored-handle',palette,high),('closed-center',closed,high)]
    for name in ['magnifier-rim','magnifier-crosshair']:
        node=art.symbols[name];previous=node.get('opacity');node.set('opacity','0');art.cache.clear()
        mutations.append(('missing-'+name,art.render('MagnifyGlass',(32,32)),high))
        if previous is None:node.attrib.pop('opacity')
        else:node.set('opacity',previous)
        art.cache.clear()
    for index,label in [(1,'missing-dark-band'),(2,'missing-tip-shading')]:
        node=art.symbols['magnifier-shaft'][index];previous=node.get('opacity');node.set('opacity','0');art.cache.clear();mutations.append((label,art.render('MagnifyGlass',(32,32)),high))
        if previous is None:node.attrib.pop('opacity')
        else:node.set('opacity',previous)
        art.cache.clear()
    circle=art.symbols['magnifier-rim'][0];radius=circle.get('r');circle.set('r','9.6');art.cache.clear();mutations.append(('changed-rim-radius',art.render('MagnifyGlass',(32,32)),high));circle.set('r',radius);art.cache.clear()
    for method in [Image.Resampling.NEAREST,Image.Resampling.LANCZOS]:mutations.append((method.name.lower()+'-enlargement',low,low.resize(high.size,method)))
    negatives=[];reasons={}
    for name,candidate,big in mutations:
        try:compare(original,candidate,big)
        except AssertionError as failure:negatives.append(name);reasons[name]=str(failure)
        else:raise AssertionError('Magnifier mutation accepted: '+name)
    assert art.render('MagnifyGlass',(32,32)).tobytes()==low.tobytes(),'Fidelity mutations changed the master'
    low.save(artifacts/'base.png');high.save(artifacts/'high.png')
    result=dict(passed=True,design=design,negative_controls=negatives,negative_reasons=reasons,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                original_source_sha256=fixture['source_sha256'],native_display_qualified=False,screen_sampling_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Magnifier original design and twelve negative controls PASS.');return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['artifacts','source','image']:parser.add_argument('--'+name,type=Path,required=name=='artifacts')
    args=parser.parse_args();run(args.artifacts,args.source,args.image)
