"""Preserve the original unknown-document sheet, text marks and question shape."""
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork,backing_size,DENSITIES
from artwork_reference import assert_not_enlarged,assert_svg_representations,regional_error,assert_vector_geometry

QUESTION_NAMES=('Unknown','UnknownTheme','BadFile')
NAMES=QUESTION_NAMES+('TextFile',)
HOOK=(15,7,33,30)
PERIOD=(20,31,27,38)


def original_references(repository=None):
    repository=repository or Path(__file__).resolve().parents[2]
    root=repository/'Tests/Wayland/artwork-originals/documents'
    definition=json.loads((root/'references.json').read_text());images={}
    for name,case in definition['cases'].items():
        assert hashlib.sha256((repository/case['source']).read_bytes()).hexdigest()==case['source_sha256'],name
        path=root/case['png'];assert hashlib.sha256(path.read_bytes()).hexdigest()==case['png_sha256'],name
        with Image.open(path) as image:images[name]=image.convert('RGBA')
    coverage=definition['question_coverage'];path=root/coverage['png']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==coverage['png_sha256']
    with Image.open(path) as image:ink=image.convert('L')
    return images,ink,definition


def points(box):
    x,y,r,b=box
    return {(px,py) for py in range(y,b) for px in range(x,r)}


def question_shape(original,actual):
    assert original.size==actual.size==(48,48)
    old,new=original.load(),actual.load();result={}
    for name,box,minimum in [('hook',HOOK,.92),('period',PERIOD,.98)]:
        region=points(box);a={p for p in region if old[p]>=128};b={p for p in region if new[p]>=128}
        overlap=len(a&b)/len(a|b)
        assert overlap>=minimum,('Document question shape changed',name,overlap)
        for source,target in [(a,b),(b,a)]:
            assert all(any((x+dx,y+dy) in target for dx in (-1,0,1) for dy in (-1,0,1))
                for x,y in source),('Document question boundary moved',name)
        mass=sum(old[p] for p in region);new_mass=sum(new[p] for p in region)
        assert abs(new_mass/mass-1)<(.04 if name=='hook' else .02),('Question ink weight changed',name,mass,new_mass)
        center=lambda pixels,total:[sum(p[axis]*pixels[p] for p in region)/total for axis in (0,1)]
        before,after=center(old,mass),center(new,new_mass)
        assert max(abs(a-b) for a,b in zip(before,after))<=.2,('Question lettering moved',name,before,after)
        result[name]=dict(shape_overlap=overlap,original_coverage_area=mass/255,
            reconstructed_coverage_area=new_mass/255,original_center=before,reconstructed_center=after)
    return result


def compare(originals,coverage,cases,ink,higher):
    shape=question_shape(coverage,ink.getchannel('A'))
    assert_not_enlarged([ink,higher],'Document question lettering')
    for name,box in [('hook',HOOK),('period',PERIOD)]:
        assert_not_enlarged([ink.crop(box),higher.crop(tuple(v*8 for v in box))],'Document '+name)
    lettering=points(HOOK)|points(PERIOD);outside=points((0,0,48,48))-lettering;errors={}
    for name in QUESTION_NAMES:
        original,actual=originals[name],cases[name]
        assert actual.size==original.size==(48,48)
        assert actual.getchannel('A').tobytes()==original.getchannel('A').tobytes(),('Document silhouette, opacity or shadow changed',name)
        old,new=original.convert('RGBa').load(),actual.convert('RGBa').load()
        assert all(old[p]==new[p] for p in outside),('Document paper, border or text marks changed',name)
        error=regional_error(original,actual,lettering);errors[name]=error
        assert error['mean']<7 and error['rms']<32 and error['channel_mean_difference']<2,('Document lettering appearance changed',name,error)
    return dict(question=shape,exact_nonlettering_pixels_per_design=len(outside),lettering_errors=errors)


def compare_text(original,frames):
    assert len(frames)==5
    assert [frame.size for frame in frames]==[(backing_size(48,d),)*2 for d in DENSITIES[:5]]
    assert frames[0].getchannel('A').tobytes()==original.getchannel('A').tobytes(),'Text sheet opacity or silhouette changed'
    assert frames[0].convert('RGBa').tobytes()==original.convert('RGBa').tobytes(),'Text sheet colors, marks or shading changed'
    assert_not_enlarged(frames,'Plain-text document geometry')
    return dict(exact_original_pixels=48*48,native_densities=list(DENSITIES[:5]))


def run(artifacts,repository=None,images=None):
    repository=repository or Path(__file__).resolve().parents[2]
    source=repository/'Applications/Artwork/Documents.svg';art=Artwork(source)
    assert_vector_geometry(art.root)
    originals,coverage,definition=original_references(repository)
    actual={name:art.render(name,(48,48)) for name in NAMES}
    ink=art.render('document-question-ink',(48,48));higher=art.render('document-question-ink',(384,384))
    result=compare(originals,coverage,actual,ink,higher)
    text_frames=[actual['TextFile']]+[art.render('TextFile',(backing_size(48,d),)*2) for d in DENSITIES[1:5]]
    result['text_marks']=compare_text(originals['TextFile'],text_frames)
    if images:
        for name,path in images.items():assert_svg_representations(art,name,path,(48,48))
    controls=[]
    moved=Image.new('RGBA',ink.size);moved.paste(ink,(1,0));controls.append(('question-shift',actual,moved,higher))
    missing=Image.new('RGBA',ink.size);controls.append(('missing-question',actual,missing,higher))
    dot=ink.copy();dot.paste((0,0,0,255),(21,32,26,37));controls.append(('square-period',actual,dot,higher))
    period=ink.copy();period.paste((0,0,0,0),PERIOD);controls.append(('missing-period',actual,period,higher))
    def changed(name,box,color):
        cases={key:image.copy() for key,image in actual.items()};cases[name].paste(color,box);return cases
    controls.extend([
        ('paper-palette',changed('Unknown',(8,4,40,6),(235,235,235,240)),ink,higher),
        ('missing-text',changed('Unknown',(7,18,16,19),(255,255,255,240)),ink,higher),
        ('border-palette',changed('Unknown',(3,2,45,3),(0,0,0,240)),ink,higher),
        ('shadow-opacity',changed('Unknown',(46,4,47,46),(0,0,0,160)),ink,higher),
        ('theme-opacity',dict(actual,UnknownTheme=actual['Unknown']),ink,higher),
        ('disabled-palette',dict(actual,BadFile=actual['Unknown']),ink,higher),
        ('nearest-enlargement',actual,ink,ink.resize(higher.size,Image.Resampling.NEAREST)),
        ('lanczos-enlargement',actual,ink,ink.resize(higher.size,Image.Resampling.LANCZOS))])
    rejected=[]
    for name,cases,candidate,large in controls:
        try:compare(originals,coverage,cases,candidate,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful document artwork accepted',name))
    text_controls=[]
    def text_changed(name,change):
        frames=[frame.copy() for frame in text_frames];change(frames[0]);text_controls.append((name,frames))
    text_changed('text-missing-row',lambda image:image.paste((255,255,255,240),(7,8,42,9)))
    text_changed('text-purple-palette',lambda image:image.paste((102,17,85,240),(7,8,9,9)))
    def missing_accents(image):
        original=originals['TextFile']
        for y in range(8,39):
            for x in range(7,42):
                if original.getpixel((x,y))[:3] not in [(255,255,255),(85,17,119)]:image.putpixel((x,y),(85,17,119,240))
    text_changed('text-missing-accents',missing_accents)
    def shifted_text(image):
        marks=image.crop((7,8,42,39));image.paste((255,255,255,240),(7,8,43,39));image.paste(marks,(8,8))
    text_changed('text-shift',shifted_text)
    for name,method in [('text-nearest-enlargement',Image.Resampling.NEAREST),('text-lanczos-enlargement',Image.Resampling.LANCZOS)]:
        text_controls.append((name,[text_frames[0].resize(frame.size,method) for frame in text_frames]))
    for name,frames in text_controls:
        try:compare_text(originals['TextFile'],frames)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful text document accepted',name))
    artifacts.mkdir(parents=True)
    for name,image in actual.items():
        image.save(artifacts/(name+'-100.png'));art.render(name,(384,384)).save(artifacts/(name+'-800.png'))
    result.update(passed=True,rejected_mutations=rejected,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256={name:r['source_sha256'] for name,r in definition['cases'].items()},
        native_consumer_qualified=False,submitted_images_verified=images is not None)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',type=Path,required=True)
    args=parser.parse_args();run(args.artifacts)
