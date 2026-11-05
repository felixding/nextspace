"""Compare the help diamond's visible RGBA against its bundled original."""
import copy
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from PIL import Image,ImageOps
from artwork_reference import artwork_original,assert_not_enlarged,assert_vector_geometry
from vector_art import Artwork


def verify(repository):
    art=Artwork(repository/'Applications/Artwork/Navigation.svg');assert_vector_geometry(art.root)
    original,_=artwork_original('help-link','HelpLink',repository)
    frames=[art.render('HelpLink',(n,n)) for n in (12,15,18,21,24)]
    def compare(candidate):
     assert candidate[0].convert('RGBa').tobytes()==original.convert('RGBa').tobytes(),'Original visible help symbol changed'
     assert_not_enlarged(candidate,'Continuous beveled help diamond')
    compare(frames);shifted=Image.new('RGBA',(12,12));shifted.paste(frames[0],(1,0));candidates=[('shift',[shifted,*frames[1:]]),('mirror',[ImageOps.mirror(frames[0]),*frames[1:]])]
    for method in [Image.Resampling.NEAREST,Image.Resampling.LANCZOS]:candidates.append((method.name,[frames[0],*(frames[0].resize(f.size,method) for f in frames[1:])]))
    with tempfile.TemporaryDirectory(prefix='nextspace-help-controls-') as directory:
     for index in range(5):
      tree=ET.ElementTree(copy.deepcopy(art.root));symbol=next(n for n in tree.getroot().iter() if n.get('id')=='HelpLink');symbol.remove(list(symbol)[index]);path=Path(directory)/f'missing-plane-{index}.svg';tree.write(path,encoding='unicode');altered=Artwork(path);candidates.append(('missing-plane-'+str(index),[altered.render('HelpLink',(n,n)) for n in [12,15,18,21,24]]))
     for color in ['#110099','#4455ff','#ddddff','#ccbbee']:
      tree=ET.ElementTree(copy.deepcopy(art.root));node=next(n for n in tree.getroot().iter() if n.get('fill')==color or n.get('stroke')==color);node.set('fill' if node.get('fill')==color else 'stroke','#ff0000');path=Path(directory)/('wrong-'+color[1:]+'.svg');tree.write(path,encoding='unicode');altered=Artwork(path);candidates.append(('wrong-color-'+color,[altered.render('HelpLink',(n,n)) for n in [12,15,18,21,24]]))
    for name,candidate in candidates:
     try:compare(candidate)
     except AssertionError:pass
     else:raise AssertionError('Help source mutation accepted: '+name)
    return dict(passed=True,original_visible_rgba_exact=True,original_alpha_exact=True,negative_controls=len(candidates))
