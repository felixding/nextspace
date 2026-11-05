"""Keep directory hover details faithful to the bundled original artwork."""
import copy
import math
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps
from artwork_reference import artwork_original, assert_not_enlarged, assert_vector_geometry
from vector_art import Artwork

DENSITIES = (48, 60, 72, 84, 96)
GROUP = 'workspace-directory-states'


def reject_controls(compare, candidates):
    for label, frames in candidates:
        try:
            compare(frames)
        except (AssertionError, ZeroDivisionError):
            pass
        else:
            raise AssertionError('Directory source mutation accepted: '+label)
    return len(candidates)


def enlargement_controls(frames):
    return [(method.name, [frames[0], *(frames[0].resize(frame.size, method) for frame in frames[1:])])
            for method in (Image.Resampling.NEAREST, Image.Resampling.LANCZOS)]


def verify_home(art, repository):
    overlay=Artwork(repository/'Applications/Artwork/HomeStates.svg')
    assert_vector_geometry(overlay.root)
    original,_=artwork_original(GROUP,'HomeHover',repository)
    panes=[(x,y) for y in (12,16) for x in (20,22,26,28)]
    entrance=[(20,30),(28,30),(24,25),(23,29),(23,33)]
    yellow=lambda p:p[0]>200 and p[1]>180 and p[2]<80 and p[3]>250
    assert all(yellow(original.getpixel(p)) for p in panes+entrance)
    assert max(original.getpixel((26,32))[:3])<20

    smoke_box=(27,0,43,3)
    assert overlay.render('HomeHover',(48,48)).crop(smoke_box).tobytes()==original.crop(smoke_box).tobytes()
    smoke=Image.new('RGBA',(48,48));smoke.paste(original.crop(smoke_box),smoke_box[:2])
    expected_smoke=Image.alpha_composite(art.render('Home',(48,48)),smoke).crop(smoke_box)

    def compare(frames):
        for n,frame in zip((48,60,72,84,96),frames):
            before=art.render('Home',(n,n))
            for y in range(n):
                for x in range(n):
                    x0,x1,y0,y1=x*48/n,(x+1)*48/n,y*48/n,(y+1)*48/n
                    if not (x0<30 and x1>18.8 and y0<18.4 and y1>10.8 or x0<29.8 and x1>18.9 and y0<39 and y1>24.6 or x0<43 and x1>27 and y0<3):
                        assert frame.getpixel((x,y))==before.getpixel((x,y)),('Unrelated master pixels changed',n,x,y)
        assert frames[0].crop(smoke_box).tobytes()==expected_smoke.tobytes(), 'Original smoke changed'
        assert all(yellow(frames[0].getpixel(p)) for p in panes+entrance)
        assert max(frames[0].getpixel((26,32))[:3])<20
        assert_not_enlarged(frames,'High-resolution artist house with reconstructed original hover details')

    frames=[art.render('HomeHover',(n,n)) for n in DENSITIES]
    for n,frame in zip((48,60,72,84,96),frames):
        assert frame.tobytes()==Image.alpha_composite(art.render('Home',(n,n)),overlay.render('HomeHover',(n,n))).tobytes()
    compare(frames)
    shift=Image.new('RGBA',(48,48));shift.paste(frames[0],(1,0))
    candidates=[('shift',[shift,*frames[1:]]),('mirror',[ImageOps.mirror(frames[0]),*frames[1:]]),('closed-house',[art.render('Home',(n,n)) for n in (48,60,72,84,96)])]
    for point in panes+entrance:
        image=frames[0].copy();image.putpixel(point,art.render('Home',(48,48)).getpixel(point))
        candidates.append(('lost-original-lit-detail-'+str(point),[image,*frames[1:]]))
    black=frames[0].copy();black.putpixel((26,32),(255,253,0,255));candidates.append(('missing-open-door-interior',[black,*frames[1:]]))
    missing=frames[0].copy();missing.paste(art.render('Home',(48,48)).crop(smoke_box),smoke_box[:2]);candidates.append(('missing-smoke',[missing,*frames[1:]]))
    wrong=frames[0].copy();wrong.putpixel((30,0),(255,0,255,255));candidates.append(('wrong-smoke-palette',[wrong,*frames[1:]]))
    for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
        candidates.append((method.name,[frames[0],*(frames[0].resize(frame.size,method) for frame in frames[1:])]))
    controls=reject_controls(compare,candidates)
    return dict(passed=True,negative_controls=controls,original_smoke_rgba_exact=True,original_rgba_exact=False)


def verify_root(repository):
    original,_=artwork_original(GROUP,'RootOpen',repository)
    closed,_=artwork_original(GROUP,'RootClosed',repository)
    def coverage(image):
        values=[]
        for a,b in zip(image.convert('RGBa').getdata(),closed.convert('RGBa').getdata()):
            delta=[v-u for v,u in zip((255,255,0,255),b)];den=sum(v*v for v in delta)
            values.append(max(0,min(1,sum((v-u)*d for v,u,d in zip(a,b,delta))/den)) if den else 0)
        return values

    reference=coverage(original)
    def compare(frames):
        low=Image.alpha_composite(closed,frames[0]);values=coverage(low)
        mass=sum(reference),sum(values)
        center=lambda row:[sum((i%48 if axis==0 else i//48)*v for i,v in enumerate(row))/sum(row) for axis in (0,1)]
        centers=center(reference),center(values)
        rms=math.sqrt(sum((a-b)**2 for a,b in zip(reference,values))/len(values))
        assert .98<=mass[1]/mass[0]<=1.02,('Flash coverage changed',mass)
        assert max(abs(a-b) for a,b in zip(*centers))<=.1,('Flash position changed',centers)
        assert rms<=.04,('Flash ray geometry changed',rms)
        masks=[{(i%48,i//48) for i,v in enumerate(row) if v>.5} for row in [reference,values]]
        distances=[max(min(max(abs(x-u),abs(y-v)) for u,v in b) for x,y in a) for a,b in [masks,masks[::-1]]]
        assert distances[0]<=2 and distances[1]<=1,('Flash boundary moved',distances)
        assert_not_enlarged(frames,'Eight continuous root-highlight rays')
        return dict(original_coverage=mass[0],new_coverage=mass[1],original_center=centers[0],new_center=centers[1],alpha_rms=rms,maximum_pixel_distances=distances)

    art=Artwork(repository/'Applications/Artwork/RootStates.svg');assert_vector_geometry(art.root);ns='{http://www.w3.org/2000/svg}'
    tree=ET.ElementTree(copy.deepcopy(art.root));node=tree.getroot().find(ns+"symbol[@id='RootOpen']");node.remove(next(n for n in node if n.get('href')=='#root'))
    temporary=tempfile.TemporaryDirectory(prefix='nextspace-root-rays-')
    flash=Path(temporary.name)/'rays.svg';tree.write(flash,encoding='unicode');rays=Artwork(flash)
    frames=[rays.render('RootOpen',(n,n)) for n in [48,60,72,84,96]];metrics=compare(frames)
    shift=Image.new('RGBA',(48,48));shift.paste(frames[0],(1,0))
    candidates=[('shift',[shift,*frames[1:]]),('mirror',[ImageOps.mirror(frames[0]),*frames[1:]])]
    for method in [Image.Resampling.NEAREST,Image.Resampling.LANCZOS]:
        candidates.append((method.name,[frames[0],*(frames[0].resize(frame.size,method) for frame in frames[1:])]))
    with tempfile.TemporaryDirectory(prefix='nextspace-root-highlight-') as directory:
        for index in range(8):
            altered=ET.ElementTree(copy.deepcopy(rays.root));group=altered.getroot().find(ns+"defs/"+ns+"g[@id='root-hover-flash']");group.remove(list(group)[index]);path=Path(directory)/f'missing-arm-{index}.svg';altered.write(path,encoding='unicode');candidate=Artwork(path)
            candidates.append(('missing-arm-'+str(index),[candidate.render('RootOpen',(n,n)) for n in [48,60,72,84,96]]))
    controls=reject_controls(compare,candidates)
    temporary.cleanup()
    return dict(passed=True,negative_controls=controls,original_rgba_exact=False,**metrics)


def verify_neighborhood(art,repository):
    originals={name:artwork_original(GROUP,symbol,repository)[0] for name,symbol in [('neighbor.tiff','Neighbor'),('openNeighbor.tiff','NeighborOpen')]}
    original=Image.new('RGBA',(48,48))
    for y in range(12):
        for x in range(28,44):
            before=originals['neighbor.tiff'].getpixel((x,y));after=originals['openNeighbor.tiff'].getpixel((x,y))
            if before!=after:original.putpixel((x,y),after)
    smoke_art=Artwork(repository/'Applications/Artwork/Neighborhood.svg');assert_vector_geometry(smoke_art.root)
    frames=[smoke_art.render('NeighborSmoke',(n,n)) for n in DENSITIES]
    def geometry(image):
     pixels=list(image.getdata());mass=sum(p[3] for p in pixels)
     return mass/255,[sum((i%48 if ax==0 else i//48)*p[3] for i,p in enumerate(pixels))/mass for ax in (0,1)]

    mass,center=geometry(original)
    def compare_smoke(candidate):
     m,c=geometry(candidate[0]);assert abs(m/mass-1)<.035 and math.dist(c,center)<.2
     assert candidate[0].getbbox() in ((30,3,41,11),(30,3,42,11))
     assert candidate[0].getpixel((40,10))[3]>0,'Original chimney stem missing'
     assert_not_enlarged(candidate,'Neighborhood chimney vapor')
    compare_smoke(frames)
    candidates=[]
    shift=Image.new('RGBA',(48,48));shift.paste(frames[0],(1,0));candidates.extend([('shift',[shift,*frames[1:]]),('mirror',[ImageOps.mirror(frames[0]),*frames[1:]])])
    for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):candidates.append((method.name,[frames[0],*(frames[0].resize(frame.size,method) for frame in frames[1:])]))
    controls=reject_controls(compare_smoke,candidates)
    # Original illuminated panes and entrance stay in the same two-house layout.
    yellow=lambda p:p[0]>195 and p[1]>175 and p[2]<85 and p[3]>245
    anchors=[(13,9),(15,9),(17,9),(19,8),(29,19),(31,19),(33,19),(35,18),(16,19),(32,31)]
    closed=[art.render('Neighbor',(n,n)) for n in (48,60,72,84,96)]
    opened=[art.render('NeighborOpen',(n,n)) for n in (48,60,72,84,96)]
    for p in anchors:assert yellow(originals['openNeighbor.tiff'].getpixel(p)) and yellow(opened[0].getpixel(p)),p
    assert_not_enlarged(closed,'NeXTSpirit two-house closed construction');assert_not_enlarged(opened,'NeXTSpirit two-house open construction')
    # The original reflection remains unlit below the foreground house.
    assert closed[0].crop((0,42,48,48)).tobytes()==opened[0].crop((0,42,48,48)).tobytes()
    return dict(passed=True,negative_controls=controls,original_rgba_exact=False,original_smoke_coverage=mass,reconstructed_smoke_coverage=geometry(frames[0])[0],original_lighting_samples=len(anchors))


def verify(art, repository):
    cases=dict(home=verify_home(art,repository),root=verify_root(repository),neighborhood=verify_neighborhood(art,repository))
    return dict(passed=True,negative_controls=sum(case['negative_controls'] for case in cases.values()),cases=cases)
