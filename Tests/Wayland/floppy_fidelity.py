"""Check the original floppy case, lettering, shutter states and highlight."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image,ImageChops,ImageFilter
from artwork_reference import assert_curve_arguments,assert_not_enlarged,regional_error
from vector_art import Artwork


REGIONS=dict(metal=(14,3,25,13),case=(14,16,36,20),rail=(3,17,7,43),paper=(11,39,37,43))
LETTERS=dict(D=(11,29,18,38),O=(20,29,27,38),S=(28,29,37,38))


def count(mask):return sum(mask.tobytes())//255


def opened_reference(closed):
    """Recover the original bare shutter pose before measuring its shine."""
    result=closed.copy();result.paste(closed.crop((12,1,34,15)),(8,1))
    for y in range(1,15):
        for x in range(30,34):
            # The exposed cavity repeats the original purple rail material;
            # its top bevel belongs to the case rather than the moving metal.
            result.putpixel((x,y),closed.getpixel((x-22,y)) if y>1 else closed.getpixel((x-27,y)))
    return result


def shine_coverage(closed,opened):
    bare=opened_reference(closed).convert('RGBa');opened=opened.convert('RGBa');coverage=Image.new('L',bare.size)
    for y in range(48):
        for x in range(48):
            if y>=32 and x>=9:continue
            b,p=bare.getpixel((x,y)),opened.getpixel((x,y))
            channels=[(p[0]-b[0])/(255-b[0]+.00255),(p[1]-b[1])/(255-b[1]+.00255),
                (b[2]-p[2])/(b[2]+.00255)]
            coverage.putpixel((x,y),round(max(0,min(1,sorted(channels)[1]))*255))
    return coverage


def check(art,originals):
    assert_curve_arguments(art.root)
    assert not any(e.tag.rsplit('}',1)[-1] in ('image','foreignObject','text') for e in art.root.iter())
    regions={};shapes={};letters={};mask=lambda i:i.getchannel('A').point(lambda v:255 if v>127 else 0)
    for name in ['Floppy','FloppyOpen']:
        original=originals[name];actual=art.render(name,48)
        bounds=(2,1,47,47) if name=='Floppy' else (0,0,47,47)
        assert original.getchannel('A').getbbox()==actual.getchannel('A').getbbox()==bounds
        before,after=mask(original),mask(actual);overlap=count(ImageChops.darker(before,after))/count(ImageChops.lighter(before,after));assert overlap>=.99,(name,overlap);shapes[name]=overlap
        assert actual.getpixel((46,30))==(0,0,0,85),'Preserve the separate translucent shadow'
    original=originals['Floppy'];actual=art.render('Floppy',48)
    for name,(left,top,right,bottom) in REGIONS.items():
        error=regional_error(original,actual,[(x,y) for y in range(top,bottom) for x in range(left,right)])
        assert error['channel_mean_difference']<=8,(name,error);regions[name]=error
    for name,(left,top,right,bottom) in LETTERS.items():
        coords=[(x,y) for y in range(top,bottom) for x in range(left,right)]
        error=regional_error(original,actual,coords);assert error['channel_mean_difference']<=8,(name,error)
        before={p for p in coords if max(original.getpixel(p)[:3])<200};after={p for p in coords if max(actual.getpixel(p)[:3])<200}
        overlap=len(before&after)/len(before|after);assert overlap>=.76,(name,overlap)
        letters[name]=dict(ink_overlap=overlap,**error)
    opened=art.render('FloppyOpen',48)
    assert actual.getpixel((12,6))==(255,255,255,255)
    assert opened.getpixel((8,6))==(255,255,255,255)
    assert max(opened.getpixel((31,6))[:3])<130,'Open shutter must expose its right-hand cavity'
    coverage=shine_coverage(originals['Floppy'],originals['FloppyOpen']);before=coverage.point(lambda v:255 if v>127 else 0)
    after=mask(art.render('floppy-shine',48));overlap=count(ImageChops.darker(before,after))/count(ImageChops.lighter(before,after));assert overlap>=.84,overlap
    assert count(ImageChops.subtract(before,after.filter(ImageFilter.MaxFilter(3))))<=4
    assert count(ImageChops.subtract(after,before.filter(ImageFilter.MaxFilter(3))))<=1
    return dict(shape_overlaps=shapes,material_regions=regions,letters=letters,
        original_shutter_translation=[-4,0],shine_coverage_overlap=overlap,
        original_partial_shadow_preserved=True)


def run(artifacts,source=None,repository=None):
    repository=repository or Path(__file__).resolve().parents[2];source=source or repository/'Applications/Artwork/Floppy.svg';art=Artwork(source)
    references=repository/'Tests/Wayland/artwork-originals/floppy';manifest=json.loads((references/'references.json').read_text());originals={}
    for name,case in manifest['cases'].items():
        assert hashlib.sha256((repository/case['source']).read_bytes()).hexdigest()==case['source_sha256']
        assert hashlib.sha256((references/case['png']).read_bytes()).hexdigest()==case['png_sha256']
        with Image.open(references/case['png']) as image:originals[name]=image.convert('RGBA')
    result=check(art,originals);negatives=[]
    with tempfile.TemporaryDirectory(prefix='nextspace-floppy-negative-') as directory:
        changes=[('missing-letter','letter-s','opacity','0'),('moved-letter','letter-o','transform','translate(3 0)'),
            ('metal-color','shutter','fill','#ff0000'),('missing-shine','floppy-shine','d','M0 0Z'),
            ('opaque-shadow','shadow','opacity','1')]
        for label,key,attribute,value in changes:
            root=copy.deepcopy(art.root);next(e for e in root.iter() if e.get('id')==key).set(attribute,value)
            p=Path(directory)/(label+'.svg');ET.ElementTree(root).write(p)
            try:check(Artwork(p),originals)
            except AssertionError:negatives.append(label)
            else:raise AssertionError('Accepted '+label)
        root=copy.deepcopy(art.root);symbol=next(e for e in root.iter() if e.get('id')=='FloppyOpen')
        next(e for e in symbol if e.get('href')=='#floppy-shutter').attrib.pop('transform')
        p=Path(directory)/'unmoved-shutter.svg';ET.ElementTree(root).write(p)
        try:check(Artwork(p),originals)
        except AssertionError:negatives.append('unmoved-shutter')
        else:raise AssertionError('Accepted unchanged open shutter')
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
            low=art.render('Floppy',48)
            try:assert_not_enlarged([low,low.resize((96,96),method)],'Floppy')
            except AssertionError:negatives.append('bitmap-'+method.name.lower())
            else:raise AssertionError('Accepted bitmap enlargement')
    artifacts.mkdir(parents=True);result.update(passed=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        rejected_mutations=negatives,native_rendering_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Floppy: original case, DOS letters, two shutter poses, yellow shine and eight negative controls PASS');return result
