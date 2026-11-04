"""Preserve the original question-mark and UNIX screen designs as SVG geometry."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image, ImageChops, ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import artwork_original, assert_vector_geometry, assert_not_enlarged


INK = {
    'question': dict(whole=(16,8,31,30), body=(16,8,31,25), bulb=(18,10,22,16),
        arc=(25,11,30,18), stem=(22,19,26,25), dot=(20,25,27,30)),
    'unix': dict(whole=(13,18,31,24), U=(13,18,19,24), N=(19,18,24,24),
        I=(24,18,26,24), X=(26,18,31,24)),
    'bundle': {},
}
PAPER = {'question': ((8,8,16,20),(29,9,35,20),(9,25,19,31),(28,25,35,31)),
    'unix': ((8,8,16,13),(29,9,35,13),(9,28,19,31),(28,28,35,31)),
    'bundle': ((8,8,24,16),(8,16,25,28),(8,28,24,31),(29,8,35,15),(34,24,36,31))}
BUNDLE_WINDOW=(26,16,34,29)


def colors(image):
    pixels=image.load()
    return [pixels[x,y] for y in range(image.height) for x in range(image.width)]


def feature(image, box, symbol):
    pixels=image.load();samples=[]
    for y in range(box[1],box[3]):
        for x in range(box[0],box[2]):
            r,g,b,a=pixels[x,y]
            weight=max(0,g-max(r,b)) if symbol=='question' else max(0,b-max(r,g))
            samples.append((x,y,weight))
    mass=sum(w for x,y,w in samples);assert mass>0,(symbol,'missing ink',box)
    return mass,[sum((x if axis==0 else y)*w for x,y,w in samples)/mass for axis in (0,1)]


def checker_contrast(image, boxes):
    pixels=image.load();samples=[]
    for x,y,right,bottom in boxes:
        for py in range(y+(y%2),bottom-1,2):
            for px in range(x+(x%2),right-1,2):
                samples.append([(pixels[px,py][k]+pixels[px+1,py+1][k]-
                    pixels[px+1,py][k]-pixels[px,py+1][k])/4 for k in range(3)])
    return [sum(p[k] for p in samples)/len(samples) for k in range(3)]


def ink_overlap(original, actual, box, symbol):
    weights=[]
    for image in (original,actual):
        pixels=image.load();values=[]
        for y in range(box[1],box[3]):
            for x in range(box[0],box[2]):
                r,g,b,a=pixels[x,y]
                values.append(max(0,g-max(r,b)) if symbol=='question' else max(0,b-max(r,g)))
        weights.append(values)
    return sum(min(a,b) for a,b in zip(*weights))/min(map(sum,weights))


def compare(symbol, original, actual, high):
    assert actual.size==original.size==(48,48) and high.size==(384,384)
    assert actual.getchannel('A').getbbox()==(6,6,41,33),(symbol,'screen layer escaped the glass')
    features={}
    for name,box in INK[symbol].items():
        mass,center=feature(original,box,symbol);weight,position=feature(actual,box,symbol)
        assert abs(weight/mass-1)<=.05,(symbol,name,'ink weight changed',mass,weight)
        assert max(abs(a-b) for a,b in zip(center,position))<=.2,(symbol,name,'position changed',center,position)
        overlap=ink_overlap(original,actual,box,symbol)
        assert overlap>=(.9 if symbol=='unix' and name=='N' else .75),(symbol,name,'stroke shape changed',overlap)
        assert_not_enlarged([actual.crop(box),high.crop(tuple(p*8 for p in box))],symbol+' '+name)
        features[name]=dict(original_weight=mass,reconstructed_weight=weight,ink_overlap=overlap,
            original_center=center,reconstructed_center=position)
    if symbol=='bundle':
        assert original.crop(BUNDLE_WINDOW).tobytes()==actual.crop(BUNDLE_WINDOW).tobytes(),'Bundle window layout, colors or title buttons changed'
        box=(25,15,35,30)
        assert_not_enlarged([actual.crop(box),high.crop(tuple(p*8 for p in box))],'Bundle screen geometry')
        features['window']=dict(bounds=BUNDLE_WINDOW,exact_original_pixels=104)
    paper=[]
    for box in PAPER[symbol]:
        before=original.crop(box).convert('RGB');after=actual.crop(box).convert('RGB')
        pairs=list(zip(colors(before),colors(after)))
        rms=math.sqrt(sum((a-b)**2 for first,second in pairs for a,b in zip(first,second))/(len(pairs)*3))
        means=[abs(sum(a[k]-b[k] for a,b in pairs)/len(pairs)) for k in range(3)]
        assert rms<=12 and max(means)<=5,(symbol,'paper lighting or checker changed',box,rms,means)
        paper.append(dict(box=box,rms=rms,channel_mean_difference=means))
    old_checker=checker_contrast(original,PAPER[symbol]);new_checker=checker_contrast(actual,PAPER[symbol])
    assert all(abs(a-b)<=max(1.5,abs(a)*.5) for a,b in zip(old_checker,new_checker)),(symbol,'checker texture changed',old_checker,new_checker)
    anchors=[(x,y) for y in range(8,23) for x in range(37,40)]
    if symbol=='unix':
        anchors.extend((x,y) for x in range(11,33) for y in (13,14,15,26))
        anchors.extend((x,y) for y in range(13,27) for x in (11,32))
        anchors.extend((x,y) for y in (16,17,24,25) for x in range(12,32))
    error=max(abs(a-b) for p in anchors for a,b in zip(original.getpixel(p)[:3],actual.getpixel(p)[:3]))
    assert error<=1,(symbol,'Dock or window detail changed',error)
    return dict(features=features,paper=paper,original_checker_contrast=old_checker,
        reconstructed_checker_contrast=new_checker,detail_anchors=len(anchors),maximum_detail_error=error)


def run(artifacts,source=None,pack=None):
    repository=Path(__file__).resolve().parents[2]
    source=source or repository/'Applications/Artwork/MonitorScreens.svg'
    art=Artwork(source);assert_vector_geometry(art.root);cases={};rejected=[];housing=[]
    for symbol in INK:
        original,fixture=artwork_original('monitor-screens',symbol)
        low,high=art.render(symbol,48),art.render(symbol,384)
        cases[symbol]=compare(symbol,original,low,high)
        shifted=Image.new('RGBA',low.size);shifted.paste(low,(1,0))
        gray=ImageOps.grayscale(low).convert('RGBA');gray.putalpha(low.getchannel('A'))
        controls=[('translated',shifted,high),('desaturated',gray,high),
            ('enlarged-bitmap',low,low.resize(high.size,Image.Resampling.NEAREST))]
        missing=low.copy()
        if symbol=='bundle':
            missing.paste((50,45,75,255),BUNDLE_WINDOW);controls.append(('missing-window',missing,high))
        else:
            box=INK[symbol]['dot' if symbol=='question' else 'I']
            missing.paste((50,45,75,255) if symbol=='question' else (255,255,255,255),box)
            controls.append(('missing-dot' if symbol=='question' else 'missing-letter',missing,high))
        missing=low.copy();missing.paste((40,35,60,255),(37,14,39,16));controls.append(('missing-Dock-mark',missing,high))
        escaped=low.copy();escaped.putpixel((0,0),(255,0,0,255));controls.append(('outside-glass',escaped,high))
        flat=low.copy()
        for box in PAPER[symbol]:
            region=colors(low.crop(box).convert('RGB'));mean=tuple(round(sum(c[k] for c in region)/len(region)) for k in range(3));flat.paste((*mean,255),box)
        controls.append(('flat-paper',flat,high))
        if symbol=='unix':
            missing=low.copy();missing.paste((0,0,0,255),(18,14,26,15));controls.append(('missing-title-strip',missing,high))
            mirrored=low.copy();box=(19,18,23,24);mirrored.paste(ImageOps.mirror(low.crop(box)),box);controls.append(('mirrored-letter',mirrored,high))
        if symbol=='bundle':
            missing=low.copy();missing.putpixel((27,17),(0,0,0,255));controls.append(('missing-title-button',missing,high))
            dimmed=low.copy();dimmed.paste((235,235,235,255),(27,19,33,28));controls.append(('dimmed-window',dimmed,high))
            enlarged=low.copy();enlarged.putpixel((26,20),(255,255,255,255));controls.append(('enlarged-window',enlarged,high))
        for label,changed,large in controls:
            try:compare(symbol,original,changed,large)
            except AssertionError:rejected.append(symbol+'-'+label)
            else:raise AssertionError('Accepted changed screen: '+symbol+'-'+label)
    if pack is not None:
        from nextspirit_art import NextSpiritArtwork
        imported=NextSpiritArtwork(pack,'workspace_icons')
        for name in ('UnknownApplication','UnixTool','Bundle'):
            master,screen,symbol=imported.overlay_layers[name]
            for size in (48,60,72,84,96,384,1024):
                overlay=screen.render(symbol,size);outside=overlay.getchannel('A').point(lambda a:255 if a==0 else 0)
                body=master.resize((size,size),Image.Resampling.LANCZOS);actual=imported.render(name,size)
                difference=Image.composite(ImageChops.difference(body,actual),Image.new('RGBA',actual.size),outside)
                assert max(hi for lo,hi in difference.getextrema())==0,(name,size,'housing changed')
                housing.append(dict(name=name,size=size,maximum_outside_screen_difference=0))
    artifacts.mkdir(parents=True)
    result=dict(passed=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),cases=cases,
        rejected_mutations=rejected,unmodified_housing_frames=housing,
        native_rendering_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Original monitor screens: {len(cases)} designs, {len(rejected)} negative controls and {len(housing)} housing frames PASS')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--pack',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.pack)
