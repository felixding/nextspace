"""Preserve the existing Workspace Debian swirl using its original vector paths."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from PIL import Image,ImageFilter,ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork,DENSITIES,backing_size
from artwork_reference import alpha_geometry,assert_not_enlarged,assert_svg_representations,assert_vector_geometry


def compare(original,frames):
    assert [p.size for p in frames]==[tuple(backing_size(v,d) for v in (52,64)) for d in DENSITIES[:5]]
    actual=frames[0];shape=alpha_geometry(original,actual)
    assert shape['original_bounds']==shape['reconstructed_bounds']==(1,1,51,63),'Debian canvas bounds changed'
    points=[(x,y) for y in range(64) for x in range(52)]
    overlap=shape['shape_overlap'];assert overlap>=.98,('Debian silhouette changed',overlap)
    old_mass,new_mass=shape['original_coverage'],shape['reconstructed_coverage'];assert abs(old_mass-new_mass)<.5,'Debian ink weight changed'
    old_center,new_center=shape['original_center'],shape['reconstructed_center'];assert max(abs(a-b) for a,b in zip(old_center,new_center))<.03,'Debian alignment changed'
    rms=shape['alpha_rms_difference']
    assert rms<1.5,('Debian outline changed',rms)
    assert {actual.getpixel(p)[:3] for p in points if actual.getpixel(p)[3]==255}=={(215,7,81)},'Original Debian palette changed'
    assert_not_enlarged(frames,'Debian swirl')
    return dict(shape_overlap=overlap,alpha_rms_difference=rms,original_bounds=shape['original_bounds'],
        reconstructed_bounds=shape['reconstructed_bounds'],original_coverage=old_mass,reconstructed_coverage=new_mass,
        original_center=old_center,reconstructed_center=new_center,opaque_color='#d70751')


def run(artifacts,repository=None,image=None):
    repository=repository or Path(__file__).resolve().parents[2];fixture=repository/'Tests/Wayland/artwork-originals/debian'
    reference=json.loads((fixture/'reference.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for path,h in [(repository/reference['source'],reference['source_sha256']),
            (fixture/reference['png'],reference['png_sha256']),(fixture/reference['upstream'],reference['upstream_sha256'])]:assert sha(path)==h
    art=Artwork(repository/'Applications/Artwork/Debian.svg');assert_vector_geometry(art.root)
    paths=lambda root:[' '.join(p.get('d').split()) for p in root.iter() if p.tag.rsplit('}',1)[-1]=='path']
    original_paths=paths(ET.parse(fixture/reference['upstream']).getroot());assert len(original_paths)==12 and paths(art.root)==original_paths,'Original Debian vector paths changed'
    with Image.open(fixture/reference['png']) as p:original=p.convert('RGBA')
    frames=[art.render('WorkspaceDebian',tuple(backing_size(v,d) for v in (52,64))) for d in DENSITIES[:5]]
    metrics=compare(original,frames);rejected=[];controls=[]
    def changed(label,action):
        copy=[p.copy() for p in frames];action(copy[0]);controls.append((label,copy))
    changed('mirrored',lambda p:p.paste(ImageOps.mirror(p)))
    changed('missing-inner-tip',lambda p:p.paste((0,0,0,0),(27,31,35,36)))
    changed('palette',lambda p:p.paste(Image.new('RGBA',p.size,(168,0,48,255)),mask=p.getchannel('A')))
    changed('thickened',lambda p:p.putalpha(p.getchannel('A').filter(ImageFilter.MaxFilter(3))))
    def shifted(p):
        copy=p.copy();p.paste((0,0,0,0),(0,0,*p.size));p.paste(copy,(1,0))
    changed('translated',shifted)
    for label,method in [('nearest-enlargement',Image.Resampling.NEAREST),('lanczos-enlargement',Image.Resampling.LANCZOS)]:
        controls.append((label,[frames[0].resize(p.size,method) for p in frames]))
    for label,candidate in controls:
        try:compare(original,candidate)
        except AssertionError:rejected.append(label)
        else:raise AssertionError('Accepted altered Debian swirl: '+label)
    if image:assert_svg_representations(art,'WorkspaceDebian',image,(52,64))
    artifacts.mkdir(parents=True);frames[0].save(artifacts/'reconstruction-100.png');art.render('WorkspaceDebian',(832,1024)).save(artifacts/'reconstruction-1600.png')
    result=dict(passed=True,metrics=metrics,original_vector_paths=12,rejected_mutations=rejected,
        submitted_image_verified=image is not None,native_rendering_qualified=False,full_plan_complete=False)
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print('Debian swirl: original vector paths and',len(rejected),'negative controls PASS');return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--artifacts',type=Path,required=True);args=p.parse_args();run(args.artifacts)
