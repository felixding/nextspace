"""Check the original Expert certificate, foil seal, ribbon and visible ink contours."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork
from artwork_reference import (assert_curve_arguments, assert_not_enlarged,
    assert_svg_representations, preferences_original, regional_error)


REGIONS={
    'seal':((0,0,29,27),(12,25,160,3.5)),
    'ribbon':((4,27,24,46),(12,25,180,3)),
    'paper':((28,9,57,39),(8,20,160,4)),
    'first-ink-row':((22,25,53,27),(18,25,90,8)),
    'second-ink-row':((22,28,53,31),(15,23,100,8)),
    'third-ink-row':((22,31,37,34),(10,16,50,4)),
    'signature':((38,31,52,35),(18,30,110,5)),
}
FEATURES={
    'foil':((1,1,28,27),'gold',.15),
    'ruby':((6,6,24,24),'red',.15),
    'dark-center':((9,8,21,21),'dark',.15),
    'green-mark':((12,13,18,19),'green',.15),
    'first-ink-row':((22,25,53,27),'ink',.15),
    'second-ink-row':((22,28,53,31),'ink',.15),
    'third-ink-row':((22,31,37,34),'ink',.15),
    'signature':((38,31,52,35),'red',.15),
    'N':((33,11,41,23),'ink',.1),
    'I':((42,11,44,23),'ink',.1),
    'X':((45,11,53,23),'ink',.1),
}
DETAILS={
    'foil':(2,2,27,26),'ruby':(7,7,23,23),'center':(10,9,20,21),
    'green':(12,13,18,19),'ribbon':(5,26,24,46),
    'small-ink':(22,25,53,27),'signature':(38,31,52,35),
    'paper-bevel':(27,36,55,39),'N':(33,11,41,23),'X':(45,11,53,23),
}


def points(box):
    left,top,right,bottom=box
    return [(x,y) for y in range(top,bottom) for x in range(left,right)]


def feature(image,box,kind):
    pixels=image.convert('RGBa').load();samples=[]
    for x,y in points(box):
        r,g,b,a=pixels[x,y]
        if kind=='gold':weight=max(min(r,g)-b,0)
        elif kind=='red':weight=max(r-g,0)
        elif kind=='green':weight=max(g-max(r,b),0)
        elif kind=='dark':weight=max(60-max(r,g,b),0)
        else:weight=255-(r+g+b)/3
        samples.append((x,y,weight))
    mass=sum(w for x,y,w in samples)
    assert mass>0,('Expert feature disappeared',kind,box)
    center=[sum((x if axis==0 else y)*w for x,y,w in samples)/mass for axis in (0,1)]
    return mass,center


def compare(original,actual,higher):
    assert original.size==actual.size==(60,49) and higher.size==(480,392)
    assert_not_enlarged([actual,higher],'Expert')
    old,new=original.load(),actual.load();canvas=points((0,0,60,49))
    outline=len({p for p in canvas if old[p][3]>=128}^{p for p in canvas if new[p][3]>=128})
    # The original has quantized, dithered alpha along its small foil tips.
    assert outline<=12,('Expert foil tips, ribbon fork or paper outline changed',outline)
    old_area=sum(old[p][3]/255 for p in canvas);new_area=sum(new[p][3]/255 for p in canvas)
    assert abs(old_area-new_area)<=1.5,('Expert opacity or cast-shadow area changed',old_area,new_area)
    frame=[(55,y) for y in range(11,37)];white=[(54,y) for y in range(11,36)]
    assert all(new[p]==old[p]==(0,0,0,255) for p in frame),'Expert right paper frame changed'
    assert all(new[p]==old[p]==(255,255,255,255) for p in white),'Expert white paper changed'
    errors={}
    for name,(box,limits) in REGIONS.items():
        error=regional_error(original,actual,points(box));errors[name]=error
        assert all(error[key]<=limit for key,limit in zip(('mean','rms','maximum','channel_mean_difference'),limits)),('Expert original material or ink contours changed',name,error)
    features={}
    for name,(box,kind,tolerance) in FEATURES.items():
        mass,center=feature(original,box,kind);new_mass,new_center=feature(actual,box,kind)
        assert abs(new_mass/mass-1)<=.05 and max(abs(a-b) for a,b in zip(center,new_center))<=tolerance,('Expert feature weight or position changed',name,mass,new_mass,center,new_center)
        features[name]=dict(original_mass=mass,reconstructed_mass=new_mass,original_center=center,reconstructed_center=new_center)
    for name,box in DETAILS.items():
        assert_not_enlarged([actual.crop(box),higher.crop(tuple(v*8 for v in box))],'Expert '+name)
    return dict(outline_difference_pixels=outline,original_alpha_area=old_area,reconstructed_alpha_area=new_area,
        exact_frame_pixels=len(frame),exact_white_pixels=len(white),material_errors=errors,features=features)


def run(artifacts,source=None,image=None):
    source=source or Path(__file__).resolve().parents[2]/'Applications/Preferences/Artwork.svg'
    original,fixture=preferences_original('Expert');art=Artwork(source);assert_curve_arguments(art.root)
    actual,higher=art.render('Expert',(60,49)),art.render('Expert',(480,392));result=compare(original,actual,higher)
    if image:assert_svg_representations(art,'Expert',image,(60,49))
    shifted=Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
    gray=ImageOps.grayscale(actual).convert('RGBA');gray.putalpha(actual.getchannel('A'))
    def paint(box,color):
        candidate=actual.copy();candidate.paste(color,box);return candidate
    def moved(box):
        candidate=paint(box,(0,0,0,255));x,y,r,b=box;candidate.paste(actual.crop(box),(x+1,y));return candidate
    controls=[('translated',shifted,higher),('desaturated',gray,higher),
        ('missing-seal',paint((2,2,27,25),(255,255,255,0)),higher),
        ('ribbon-fork-filled',paint((11,42,21,45),(187,187,34,255)),higher),
        ('ribbon-palette',paint((10,28,18,40),(128,128,128,255)),higher),
        ('flat-ruby',paint((8,8,22,22),(187,51,85,255)),higher),
        ('green-mark-moved',moved((12,13,18,19)),higher),
        ('missing-violet-contour',paint((16,12,19,14),(0,0,0,255)),higher),
        ('paper-frame',paint((55,12,56,36),(119,119,119,255)),higher),
        ('heading-filled',paint((35,12,39,23),(0,0,0,255)),higher),
        ('missing-signature',paint((38,31,52,35),(255,255,255,255)),higher)]
    for name,(box,limits) in REGIONS.items():
        if 'ink-row' not in name:continue
        candidate=paint(box,(255,255,255,255));left,top,right,bottom=box
        candidate.paste((119,119,119,255),(left,top+1,right,top+2))
        controls.append(('plain-rule-'+name,candidate,higher))
    for name,box in DETAILS.items():
        large=higher.copy();x,y,r,b=box
        large.paste(actual.crop(box).resize(((r-x)*8,(b-y)*8),Image.Resampling.NEAREST),(x*8,y*8))
        controls.append(('traced-'+name,actual,large))
    controls.extend([('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),
        ('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))])
    rejected=[]
    for name,candidate,large in controls:
        try:compare(original,candidate,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful Expert design accepted',name))
    artifacts.mkdir(parents=True);actual.save(artifacts/'candidate-100.png');higher.save(artifacts/'candidate-800.png')
    result.update(passed=True,rejected_mutations=rejected,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],submitted_image_verified=image is not None,
        native_density_qualification=False,text_transcription_established=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--source',type=Path);parser.add_argument('--image',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.image)
