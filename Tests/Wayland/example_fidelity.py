"""Measure the shaded GNUstep example against its bundled original."""
import copy
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps
from artwork_reference import artwork_original, alpha_geometry, assert_not_enlarged, assert_vector_geometry, regional_error
from vector_art import Artwork


def verify(repository):
    original,fixture=artwork_original('workspace-directory-states','GNUstepExample',repository)
    import hashlib
    assert hashlib.sha256((repository/'Frameworks/DesktopKit/Resources/Images/GNUstep48x48.tiff').read_bytes()).hexdigest()==fixture['source_sha256']
    regions={'dark':[(x,y) for y in range(8,23) for x in range(8,28)],'highlight':[(x,y) for y in range(10,23) for x in range(33,42)],'gray-front':[(x,y) for y in range(28,42) for x in range(18,38)]}

    def compare(frames):
        geometry=alpha_geometry(original,frames[0])
        assert geometry['shape_overlap']>=.995 and geometry['alpha_rms_difference']<=9
        assert .99<=geometry['reconstructed_coverage']/geometry['original_coverage']<=1.01
        assert max(abs(a-b) for a,b in zip(geometry['original_center'],geometry['reconstructed_center']))<=.08
        materials={name:regional_error(original,frames[0],points) for name,points in regions.items()}
        for name,mean,rms,bias in [('dark',3,4,1),('highlight',4,5,4),('gray-front',1.5,2,1)]:
            error=materials[name];assert error['mean']<=mean and error['rms']<=rms and error['channel_mean_difference']<=bias,(name,error)
        for y,x0,x1 in [(12,28,33),(16,28,33),(20,28,33),(28,13,17),(32,13,17),(36,13,17)]:
            minimum=lambda image:min(range(x0,x1),key=lambda x:sum(image.getpixel((x,y))[:3]))
            assert minimum(frames[0])==minimum(original),(y,'Black bevel shifted')
            assert max(frames[0].getpixel((minimum(original),y))[:3])<=20
        assert_not_enlarged(frames,'Continuous shaded GNUstep circle and step geometry')
        return dict(geometry=geometry,materials=materials)

    art=Artwork(repository/'Applications/Artwork/GNUstepExample.svg');assert_vector_geometry(art.root)
    frames=[art.render('GNUstepExample',(n,n)) for n in (48,60,72,84,96)];metrics=compare(frames)
    shift=Image.new('RGBA',(48,48));shift.paste(frames[0],(1,0))
    candidates=[('shift',[shift,*frames[1:]]),('mirror',[ImageOps.mirror(frames[0]),*frames[1:]])]
    for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
        candidates.append((method.name,[frames[0],*(frames[0].resize(frame.size,method) for frame in frames[1:])]))
    with tempfile.TemporaryDirectory(prefix='nextspace-gnustep-example-control-') as directory:
        for name,attribute,value in [('missing-side-bevel','filter','url(#example-side-softness)'),('missing-rim','filter','url(#example-rim-softness)'),('flat-front','fill','url(#example-light)'),('missing-disc','fill','url(#example-dark)'),('missing-matte','opacity','.995'),('missing-top-shade','fill','url(#example-dark-top)')]:
            tree=ET.ElementTree(copy.deepcopy(art.root));node=next(n for n in tree.getroot().iter() if n.get(attribute)==value)
            if name=='flat-front':node.set('fill','#898989')
            else:node.set('opacity','0')
            path=Path(directory)/(name+'.svg');tree.write(path,encoding='unicode');candidate=Artwork(path)
            candidates.append((name,[candidate.render('GNUstepExample',(n,n)) for n in (48,60,72,84,96)]))
    for label,candidate in candidates:
        try:compare(candidate)
        except AssertionError:pass
        else:raise AssertionError('GNUstep logo source mutation accepted: '+label)
    return dict(passed=True,negative_controls=len(candidates),original_rgba_exact=False,six_black_bevel_positions_exact=True,**metrics)
