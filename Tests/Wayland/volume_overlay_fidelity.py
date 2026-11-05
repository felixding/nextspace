"""Compare reconstructed volume marks with the native RGB originals."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image,ImageChops,ImageFilter
from artwork_reference import assert_curve_arguments,assert_not_enlarged,regional_error
from vector_art import Artwork,SVG


def count(mask):return sum(mask.tobytes())//255


def highlight_coverage(plain,highlight):
    result=Image.new('L',plain.size)
    for y in range(14,48):
        for x in range(48):
            b=plain.getpixel((x,y));p=highlight.getpixel((x,y))
            if max(p[:2])<153:continue
            channels=[(p[0]-b[0])/(255-b[0]+.00255),(p[1]-b[1])/(255-b[1]+.00255),
                (b[2]-p[2])/(b[2]+.00255)]
            result.putpixel((x,y),round(max(0,min(1,sorted(channels)[1]))*255))
    return result


def check(art,originals):
    assert_curve_arguments(art.root)
    assert not any(e.tag.rsplit('}',1)[-1] in ('image','foreignObject') for e in art.root.iter())
    assert 'shine' in art.symbols and len(art.symbols['shine'].get('d','').split())<45
    mask=lambda image:image.point(lambda v:255 if v>127 else 0)
    before=mask(highlight_coverage(originals['HDD.fs'],originals['HDD.openfs']))
    after=mask(art.render('highlight',48).getchannel('A'))
    overlap=count(ImageChops.darker(before,after))/count(ImageChops.lighter(before,after));assert overlap>=.84,overlap
    # The original has 4-bit colors and a quantized glow. Compare the fitted
    # continuous rays with their yellow coverage, independently of the disc.
    assert count(ImageChops.subtract(before,after.filter(ImageFilter.MaxFilter(3))))<=3
    assert count(ImageChops.subtract(after,before.filter(ImageFilter.MaxFilter(3))))<=3
    original=originals['NTFS_HDD.fs'];actual=art.render('ntfs',48);regions={}
    for name,(left,top,right,bottom) in dict(red=(24,19,26,21),green=(31,21,33,23),
            blue=(22,26,24,28),yellow=(28,28,30,30)).items():
        assert 'flag-'+name in art.symbols
        error=regional_error(original,actual,[(x,y) for y in range(top,bottom) for x in range(left,right)])
        assert error['channel_mean_difference']<=7,(name,error);regions[name]=error
    def ink(image):
        pixels=image.load();mask=Image.new('L',image.size)
        for y in range(15,36):
            for x in range(17,38):
                if pixels[x,y][3]>127 and max(pixels[x,y][:3])<96:mask.putpixel((x,y),255)
        return mask
    old,new=ink(original),ink(actual);rim=count(ImageChops.darker(old,new))/count(ImageChops.lighter(old,new));assert rim>=.68,rim
    assert abs(count(old)-count(new))<=18
    assert all(key in art.symbols for key in ['flag-outline','flag-trail','red-trail','blue-trail'])
    return dict(highlight_coverage_overlap=overlap,flag_ink_overlap=rim,original_flag_ink_pixels=count(old),
        reconstructed_flag_ink_pixels=count(new),flag_palette_regions=regions)


def run(pack,artifacts,repository=None):
    repository=repository or Path(__file__).resolve().parents[2];source=repository/'Applications/Artwork/VolumeOverlays.svg'
    references=repository/'Tests/Wayland/artwork-originals/volume-overlays';manifest=json.loads((references/'references.json').read_text());originals={}
    for name,case in manifest['cases'].items():
        assert hashlib.sha256((repository/case['source']).read_bytes()).hexdigest()==case['source_sha256']
        assert hashlib.sha256((references/case['png']).read_bytes()).hexdigest()==case['png_sha256']
        with Image.open(references/case['png']) as image:originals[name]=image.convert('RGBA')
    art=Artwork(source);result=check(art,originals);negatives=[]
    with tempfile.TemporaryDirectory(prefix='nextspace-volume-marks-') as directory:
        for label,key,attribute,value in [('moved-highlight','shine','transform','translate(3 0)'),
                ('wrong-red','flag-red','fill','#00ff00'),('flag-shape','flag-outline','transform','translate(3 0)'),
                ('missing-blue','flag-blue','opacity','0')]:
            root=copy.deepcopy(art.root);next(e for e in root.iter() if e.get('id')==key).set(attribute,value);p=Path(directory)/(label+'.svg');ET.ElementTree(root).write(p)
            try:check(Artwork(p),originals)
            except AssertionError:negatives.append(label)
            else:raise AssertionError('Accepted '+label)
        for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
            low=art.render('highlight',48)
            try:assert_not_enlarged([low,low.resize((96,96),method)],'highlight')
            except AssertionError:negatives.append('bitmap-'+method.name.lower())
            else:raise AssertionError('Accepted bitmap enlargement')
    from nextspirit_art import NextSpiritArtwork
    imported=NextSpiritArtwork(pack,'workspace_icons');frames=[]
    for name in ['VolumeHighlighted','VolumeNTFS']:
        master,overlay,symbol=imported.overlay_layers[name]
        assert master.tobytes()==imported.images['VolumeDisk'].tobytes()
        for size in [48,60,72,84,96,384,1024]:
            base=master.resize((size,size),Image.Resampling.LANCZOS);mark=overlay.render(symbol,size);actual=imported.render(name,size)
            assert actual.tobytes()==Image.alpha_composite(base,mark).tobytes()
            outside=mark.getchannel('A').point(lambda a:255 if a==0 else 0)
            difference=Image.composite(ImageChops.difference(actual,base),Image.new('RGBA',actual.size),outside)
            assert max(hi for _,hi in difference.getextrema())==0
            frames.append(dict(name=name,size=size,pixel_sha256=hashlib.sha256(actual.tobytes()).hexdigest(),
                maximum_difference_outside_mark=0))
    artifacts.mkdir(parents=True);result.update(passed=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        frames=frames,rejected_mutations=negatives,unrestricted_redistribution_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Volume marks: original rays, four flag colors, six negative controls and fourteen unchanged-disc checks PASS');return result
