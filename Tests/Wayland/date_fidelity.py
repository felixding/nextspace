"""Check the clock's original design independently of its SVG construction."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image,ImageDraw,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Tests/Wayland'))
from artwork_reference import assert_not_enlarged, assert_svg_representations, preferences_original


def compare(original,actual,higher):
    assert original.size==actual.size==(66,57) and higher.size==(528,456)
    assert_not_enlarged([actual,higher],'Date')
    pixels=lambda image:[image.getpixel((x,y)) for y in range(image.height) for x in range(image.width)]
    old,new=pixels(original),pixels(actual)
    foreground=lambda pixels:{i for i,p in enumerate(pixels) if p[3]>=128}
    silhouette=len(foreground(old)^foreground(new))
    assert silhouette<=16,('Clock outline changed',silhouette)
    def moments(pixels):
        area=sum(p[3]/255 for p in pixels)
        center=[sum((i%66+.5)*p[3]/255 for i,p in enumerate(pixels))/area,
                sum((i//66+.5)*p[3]/255 for i,p in enumerate(pixels))/area]
        return area,center
    area,center=moments(old);new_area,new_center=moments(new)
    assert abs(area-new_area)<=2 and max(abs(a-b) for a,b in zip(center,new_center))<=.1,('Clock proportions or position changed',area,new_area,center,new_center)
    radius=lambda i:math.hypot(i%66+.5-31.5,i//66+.5-29.5)
    ink={i for i,p in enumerate(old) if radius(i)<19.5 and p[3]==255 and max(p[:3])<=34}
    assert len(ink)==49
    darkest=max(max(new[i][:3]) for i in ink)
    assert all(new[i][3]==255 for i in ink) and darkest<=34,('Clock hands or markings changed',darkest)
    near={yy*66+xx for i in ink for yy in range(max(0,i//66-1),min(57,i//66+2)) for xx in range(max(0,i%66-1),min(66,i%66+2))}
    face=[i for i in range(66*57) if radius(i)<17.5 and i not in near]
    differences=[abs(a-b) for i in face for a,b in zip(old[i][:3],new[i][:3])]
    maximum,mean=max(differences),sum(differences)/len(differences)
    assert maximum<=20 and mean<=8.5,('Clock face palette or gradient changed',maximum,mean)
    # The original RGB palette has 17-level quantization and color dithering.
    # Compare each bevel band/lighting direction rather than its AA edge cells.
    bevel=[]
    visible=lambda p:[v*p[3]/255+170*(1-p[3]/255) for v in p[:3]]
    for low,high in ((19,20.5),(20.5,21.5),(21.5,23.5)):
        for sector in range(8):
            indices=[i for i,p in enumerate(old) if p[3]>=128 and low<=radius(i)<high and
                int(((math.atan2(i//66+.5-29.5,i%66+.5-31.5)+math.pi/8)%(2*math.pi))/(math.pi/4))==sector]
            before=[sum(visible(old[i])[c] for i in indices)/len(indices) for c in range(3)]
            after=[sum(visible(new[i])[c] for i in indices)/len(indices) for c in range(3)]
            delta=max(abs(a-b) for a,b in zip(before,after));bevel.append(delta)
            assert delta<=17,('Clock bevel palette or lighting changed',low,sector,delta)
    # Derive the filled ellipse from the ORIGINAL alpha moments. An enlarged
    # bitmap or traced pixel staircase cannot supply a smooth high-density rim.
    xx=sum((i%66+.5-center[0])**2*p[3]/255 for i,p in enumerate(old))*4/area
    yy=sum((i//66+.5-center[1])**2*p[3]/255 for i,p in enumerate(old))*4/area
    xy=sum((i%66+.5-center[0])*(i//66+.5-center[1])*p[3]/255 for i,p in enumerate(old))*4/area
    determinant=xx*yy-xy*xy;pixels=higher.getchannel('A');edge=[]
    for y in range(1,455):
        for x in range(1,527):
            if pixels.getpixel((x,y))>=128 and any(pixels.getpixel((x+dx,y+dy))<128 for dx,dy in ((-1,0),(1,0),(0,-1),(0,1))):
                dx,dy=(x+.5)/8-center[0],(y+.5)/8-center[1]
                q=(dx*dx*yy-2*dx*dy*xy+dy*dy*xx)/determinant
                edge.append(math.hypot(dx,dy)*abs(1-1/math.sqrt(q)))
    assert edge, 'Clock high-density outline is missing'
    rms=math.sqrt(sum(v*v for v in edge)/len(edge))
    assert max(edge)<=.25 and rms<=.1,('Clock rim has lost continuous curvature',max(edge),rms)
    return dict(silhouette_differences=silhouette,original_alpha_area=area,candidate_alpha_area=new_area,
        original_ink_anchors=len(ink),maximum_ink_anchor_value=darkest,face_pixels=len(face),
        maximum_face_difference=maximum,mean_face_difference=mean,
        maximum_bevel_region_difference=max(bevel),high_density_edge_samples=len(edge),
        maximum_ellipse_distance=max(edge),rms_ellipse_distance=rms)


def run(artifacts, source=None, image=None):
    repository=Path(__file__).resolve().parents[2]
    source=source or repository/'Applications/Preferences/Artwork.svg'
    original,fixture=preferences_original('Date',repository)
    artifacts.mkdir(parents=True)
    art=Artwork(source)
    if image:
        assert_svg_representations(art,'Date',image,(66,57))
    actual=art.render('Date',(66,57));higher=art.render('Date',(528,456))
    result=compare(original,actual,higher)
    shifted=Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
    gray=ImageOps.grayscale(actual).convert('RGBA');gray.putalpha(actual.getchannel('A'))
    flat=actual.copy()
    for y in range(57):
        for x in range(66):
            if math.hypot(x+.5-31.5,y+.5-29.5)<17 and max(original.getpixel((x,y))[:3])>110:flat.putpixel((x,y),(208,208,208,255))
    hand=actual.copy()
    for y in range(17,24):hand.putpixel((31,y),(221,221,221,255))
    tick=actual.copy()
    for y in range(11,15):tick.putpixel((31,y),(238,238,238,255))
    extra=actual.copy();ImageDraw.Draw(extra).line((41,13,39,17),fill=(0,0,0,255),width=1)
    staircase=higher.copy();staircase.putalpha(actual.getchannel('A').resize(higher.size,Image.Resampling.NEAREST))
    controls=[('extra-hour-mark',extra,higher),('traced-pixel-outline',actual,staircase),('translated',shifted,higher),('desaturated',gray,higher),('flat-face',flat,higher),
        ('short-hand',hand,higher),('missing-hour-mark',tick,higher),
        ('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),
        ('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))]
    rejected=[]
    for name,modified,large in controls:
        try:compare(original,modified,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful clock accepted',name))
    result.update(passed=True,rejected_mutations=rejected,native_density_qualification=False,
        reference_method='Pinned device-selected RGB original; source and PNG hashes verified',
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],submitted_image_verified=image is not None)
    actual.save(artifacts/'candidate-100.png');higher.save(artifacts/'candidate-800.png')
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts',type=Path,required=True)
    p.add_argument('--source',type=Path,help='Alternative SVG for original-design checks')
    p.add_argument('--image',type=Path,help='Require the submitted TIFF to match all five SVG representations')
    a=p.parse_args();run(a.artifacts,a.source,a.image)
