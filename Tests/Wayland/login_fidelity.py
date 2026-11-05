"""Check reconstructed Login artwork against device-selected original designs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageFilter, ImageChops
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'Packaging/Sources'))
from vector_art import Artwork, SVG
from artwork_reference import artwork_original, assert_not_enlarged, assert_svg_representations


def compare_fields(original, actual, higher):
    assert original.size == actual.size == (328,63) and higher.size == (2624,504)
    assert actual.getchannel('A').tobytes() == original.getchannel('A').tobytes(), 'Login field geometry or gap changed'
    assert actual.crop((0,0,328,29)).tobytes() == actual.crop((0,34,328,63)).tobytes(), 'Login field insets differ'
    old, new = original.tobytes(), actual.tobytes()
    shade, exact, transparent = [], 0, 0
    for offset in range(0,len(old),4):
        a,b = old[offset:offset+4],new[offset:offset+4]
        if a[3]==0:
            assert b==a, 'Transparent Login field gap changed'
            transparent += 1
        elif a[:3] in (bytes((255,255,255)),bytes((169,169,169))):
            assert b==a, 'Login field fill or bevel changed'
            exact += 1
        else:
            shade.extend(abs(x-y) for x,y in zip(a[:3],b[:3]))
    assert exact==17608 and transparent==1640
    assert max(shade)<=4 and sum(shade)/len(shade)<=.5, 'Login field shading changed'
    assert_not_enlarged([actual,higher], 'Login Fields')
    pixels = higher.load()
    smoothness = max(abs(pixels[x+1,0][channel]-pixels[x,0][channel])
        for x in range(higher.width-1) for channel in range(3))
    assert smoothness<=1, 'Login field shade retains enlarged raster steps'
    return dict(exact_fill_and_bevel_pixels=exact,exact_transparent_pixels=transparent,
        maximum_shade_difference=max(shade),mean_shade_difference=sum(shade)/len(shade),
        maximum_high_density_shade_neighbor_difference=smoothness)



def panel_delta(original, actual, box):
    old,new = (image.crop(box).convert('RGB').tobytes() for image in (original,actual))
    differences = [abs(a-b) for a,b in zip(old,new)]
    return dict(mean=sum(differences)/len(differences),
        rms=(sum(value*value for value in differences)/len(differences))**.5,
        maximum=max(differences))


def panel_shape(original, actual, box, threshold):
    width,height = box[2]-box[0],box[3]-box[1]
    masks=[]
    for image in (original,actual):
        pixels=image.crop(box).convert('RGB').tobytes()
        masks.append(Image.frombytes('L',(width,height),bytes(
            255 if max(pixels[i:i+3])<threshold else 0 for i in range(0,len(pixels),3))))
    old,new = (mask.tobytes() for mask in masks)
    old_expanded,new_expanded = (mask.filter(ImageFilter.MaxFilter(3)).tobytes() for mask in masks)
    return dict(mismatch=sum(a!=b for a,b in zip(old,new))/sum(bool(a or b) for a,b in zip(old,new)),
        outside_one_pixel=sum(bool(a and not b) for a,b in zip(old,new_expanded))+
            sum(bool(a and not b) for a,b in zip(new,old_expanded)),
        bounds=[mask.getbbox() for mask in masks])


def panel_inks(image):
    result={name:dict(mass=0,bounds=[462,260,0,0],peak=[0,0,0]) for name in ('N','e','X','T')}
    for y in range(178,252):
        for x in range(198,265):
            r,g,b,_=image.getpixel((x,y))
            conditions=dict(N=r>40 and r>g*1.6 and r>b*1.8,
                e=g>40 and g>.55*r and r>.6*g and r>1.6*b and g>1.6*b,
                X=g>40 and g>r*1.8 and g>b*1.5,
                T=r>40 and b>40 and r>g*2 and b>g*2 and r>.55*b and b>.55*r)
            for name,yes in conditions.items():
                if not yes:continue
                row=result[name];row['mass']+=dict(N=r-g,e=g-b,X=g-b,T=b-g)[name]
                a,c,d,e=row['bounds'];row['bounds']=[min(a,x),min(c,y),max(d,x+1),max(e,y+1)]
                row['peak']=[max(a,v) for a,v in zip(row['peak'],(r,g,b))]
    return result


def compare_panel(original, actual, higher):
    assert original.size==actual.size==(462,260) and higher.size==(3696,2080)
    assert original.getchannel('A').tobytes()==actual.getchannel('A').tobytes(), 'Login panel opacity changed'
    # These regions separate contour antialiasing from the original material.
    wordmark=panel_delta(original,actual,(105,12,357,70))
    cube=panel_delta(original,actual,(192,174,275,256))
    assert wordmark['mean']<=4.2 and wordmark['rms']<=9.5, ('Login wordmark changed',wordmark)
    assert cube['mean']<=3.5 and cube['rms']<=8, ('Login cube changed',cube)
    contours={}
    for name,box,threshold,mismatch,outside in (
            ('wordmark',(105,12,357,70),125,.05,0),('cube',(192,174,275,256),95,.07,12)):
        shape=panel_shape(original,actual,box,threshold)
        assert shape['mismatch']<=mismatch and shape['outside_one_pixel']<=outside, (name,shape)
        assert all(abs(a-b)<=1 for a,b in zip(*shape['bounds'])), (name,shape)
        contours[name]=shape
    for box in ((184,22,190,61),(298,22,304,61)):
        stem=panel_delta(original,actual,box)
        assert stem['mean']<=.85 and stem['maximum']<=3, ('Login letter face material changed',stem)
    frames={}
    for name,box in dict(top=(5,0,455,3),left=(0,5,3,254),bottom=(5,256,455,260),right=(458,5,462,254),
            upper_separator=(3,88,458,90),lower_separator=(3,169,458,171)).items():
        delta=panel_delta(original,actual,box)
        assert delta['mean']<=1.1 and delta['rms']<=1.5, ('Login frame or separator changed',name,delta)
        frames[name]=delta
    background=[]
    for y in range(3,256):
        if y in (88,89,169,170):continue
        for x in range(3,458):
            if 105<=x<357 and 12<=y<70 or 192<=x<275 and y>=174:continue
            background.extend(abs(a-b) for a,b in zip(original.getpixel((x,y))[:3],actual.getpixel((x,y))[:3]))
    shade=dict(mean=sum(background)/len(background),rms=(sum(v*v for v in background)/len(background))**.5,maximum=max(background))
    assert shade['mean']<=.8 and shade['rms']<=1.2 and shade['maximum']<=6, ('Login background lighting changed',shade)
    old_ink,new_ink=panel_inks(original),panel_inks(actual)
    for name,old in old_ink.items():
        new=new_ink[name]
        assert old['bounds']==new['bounds'], ('Login cube letter bounds changed',name,new)
        assert abs(new['mass']/old['mass']-1)<=.025, ('Login cube letter weight changed',name,new)
        assert all(abs(a-b)<=1 for a,b in zip(old['peak'],new['peak'])), ('Login cube letter palette changed',name,new)
    assert_not_enlarged([actual,higher], 'Login Panel')
    pixels=higher.load()
    smoothness=max(abs(pixels[x+1,95*8][c]-pixels[x,95*8][c]) for x in range(24,458*8-1) for c in range(3))
    assert smoothness<=1, 'Login panel retains enlarged raster shading steps'
    changes=[x for x in range(24,458*8-1) if pixels[x,95*8]!=pixels[x+1,95*8]]
    away=sum((x+1)%8!=0 for x in changes)
    assert len(changes)>=30 and away/len(changes)>=.6, 'Login panel shade follows the original raster grid'
    return dict(wordmark=wordmark,cube=cube,contours=contours,frames=frames,background=shade,
        original_ink=old_ink,actual_ink=new_ink,maximum_high_density_background_neighbor_difference=smoothness,
        high_density_background_changes=len(changes),background_changes_away_from_original_grid=away)


def panel_fidelity(art, original):
    actual,higher=art.render('Panel',(462,260)),art.render('Panel',(3696,2080))
    result=compare_panel(original,actual,higher)
    wordmark=actual.copy();wordmark.paste(actual.crop((105,12,357,70)),(106,12))
    cube=actual.copy();cube.paste(actual.crop((192,174,275,256)),(194,174))
    blank=actual.copy();blank.paste((145,146,149,255),(105,12,357,70))
    frame=actual.copy();frame.paste((0,0,0,255),(0,0,462,3))
    flat=actual.copy();flat.paste((135,135,137,255),(4,91,458,96))
    palette=actual.copy()
    for y in range(178,252):
        for x in range(198,265):
            r,g,b,a=palette.getpixel((x,y))
            if r>40 and r>g*1.6 and r>b*1.8:palette.putpixel((x,y),(b,g,r,a))
    traced=higher.copy();raster=original.resize(higher.size,Image.Resampling.NEAREST)
    traced.paste(raster.crop((24,95*8,458*8,96*8)),(24,95*8))
    controls=[('wordmark-shift',wordmark,higher),('cube-shift',cube,higher),('missing-wordmark',blank,higher),
        ('frame-palette',frame,higher),('flat-lighting',flat,higher),('cube-letter-palette',palette,higher),
        ('traced-background',actual,traced),
        ('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),
        ('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))]
    rejected=[]
    for name,candidate,large in controls:
        try:compare_panel(original,candidate,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful Login Panel accepted',name))
    result['rejected_mutations']=rejected
    return result,actual,higher



def compare_labels(original, actual, higher):
    assert original.size==actual.size==(115,63) and higher.size==(920,504)
    assert actual.crop((0,23,115,40)).getbbox() is None, 'Login label spacing changed'
    errors={}
    for name,box in dict(Name=(60,5,112,25),Password=(29,39,112,59)).items():
        a,b=(image.crop(box).convert('RGBa').tobytes() for image in (original,actual))
        delta=[abs(x-y) for x,y in zip(a,b)]
        row=dict(mean=sum(delta)/len(delta),rms=(sum(v*v for v in delta)/len(delta))**.5,maximum=max(delta))
        assert row['mean']<=4.4 and row['rms']<=11.5 and row['maximum']<=100, ('Login lettering changed',name,row)
        errors[name]=row
    masks=[image.getchannel('A').point(lambda value:255 if value>127 else 0) for image in (original,actual)]
    a,b=(image.tobytes() for image in masks);ad,bd=(image.filter(ImageFilter.MaxFilter(3)).tobytes() for image in masks)
    mismatch=sum(x!=y for x,y in zip(a,b))/sum(bool(x or y) for x,y in zip(a,b))
    assert mismatch<=.05 and masks[0].getbbox()==masks[1].getbbox(), 'Login label contours or placement changed'
    assert not any(x and not y for x,y in zip(a,bd)) and not any(x and not y for x,y in zip(b,ad)), 'Login label contours moved beyond one source pixel'
    assert_not_enlarged([actual,higher],'Login FieldNames')
    return dict(words=errors,alpha_contour_mismatch=mismatch,alpha_contour_bounds=masks[0].getbbox())


def caption_mask(image):
    rgba=image.tobytes()
    return Image.frombytes('L',image.size,bytes(255 if rgba[i:i+4]==bytes((0,0,0,255)) else 0
        for i in range(0,len(rgba),4)))


def compare_button(name, original, actual, higher):
    assert original.size==actual.size==(48,48) and higher.size==(384,384)
    assert actual.getchannel('A').getextrema()==(255,255), 'Login button opacity changed'
    up=name.endswith('up')
    frame_pixels=0
    for y in range(48):
        for x in range(48):
            if x==0 or y==0 or x>=46 or y>=46:
                assert actual.getpixel((x,y))==original.getpixel((x,y)), ('Login button frame changed',name,x,y)
                frame_pixels+=1
    assert frame_pixels==279
    box=(3,34,45,45);old_caption,new_caption=(caption_mask(image.crop(box)) for image in (original,actual))
    assert old_caption.tobytes()==new_caption.tobytes(), ('Original monochrome caption changed',name)
    if not up:assert original.crop(box).tobytes()==actual.crop(box).tobytes(), ('Pressed caption/background changed',name)
    assert_not_enlarged([new_caption.convert('RGBA'),caption_mask(higher.crop(tuple(v*8 for v in box))).convert('RGBA')],name+' caption')
    figure=panel_delta(original,actual,(6,1,43,33))
    assert figure['mean']<=(4.2 if up else 3.1) and figure['rms']<=(9.8 if up else 9.5) and figure['maximum']<=115, ('Login button symbol material changed',name,figure)
    background=[]
    if up:
        for y in range(1,46):
            for x in range(1,46):
                if 7<=x<42 and y<34 or 5<=x<44 and 34<=y<44:continue
                background.extend(abs(a-b) for a,b in zip(original.getpixel((x,y))[:3],actual.getpixel((x,y))[:3]))
        shade=dict(mean=sum(background)/len(background),rms=(sum(v*v for v in background)/len(background))**.5,maximum=max(background))
        assert shade['mean']<=1.8 and shade['rms']<=2.3 and shade['maximum']<=7, ('Login button surface lighting changed',name,shade)
        peak=max(max(actual.getpixel((x,y))[:3]) for y in range(2,34) for x in range(6,43))
        assert peak<=245, ('Login bevel palette changed',name,peak)
    else:
        def ink(image):
            mass=0;bounds=[48,48,0,0];colors=[]
            for y in range(1,34):
                for x in range(3,45):
                    r,g,b,_=image.getpixel((x,y))
                    if r<=80 or r<=g*1.6 or r<=b*1.8:continue
                    mass+=r-g;a,c,d,e=bounds;bounds=[min(a,x),min(c,y),max(d,x+1),max(e,y+1)];colors.append((r,g,b))
            return mass,bounds,max(set(colors),key=colors.count)
        before,after=ink(original),ink(actual)
        assert all(abs(a-b)<=1 for a,b in zip(before[1],after[1])) and abs(after[0]/before[0]-1)<=.025, ('Login button symbol shape/weight changed',name,before,after)
        assert before[2]==after[2]==(240,56,37), ('Login button ink palette changed',name,before,after)
        shade=dict(original_chroma_mass=before[0],actual_chroma_mass=after[0],original_ink_bounds=before[1],actual_ink_bounds=after[1])
    assert_not_enlarged([actual,higher],name)
    return dict(exact_frame_pixels=frame_pixels,exact_original_caption_pixels=sum(v==255 for v in new_caption.tobytes()),figure=figure,surface=shade)


def controls_fidelity(art, artifacts=None):
    cases={};rejected={}
    names=['FieldNames','powerbuttonup','powerbuttondown','restartbuttonup','restartbuttondown']
    for name in names:
        original,fixture=artwork_original('login',name)
        size=original.size;actual=art.render(name,size);higher=art.render(name,tuple(v*8 for v in size))
        compare=(lambda a,b:compare_labels(original,a,b)) if name=='FieldNames' else (lambda a,b:compare_button(name,original,a,b))
        result=compare(actual,higher);result['original_source_sha256']=fixture['source_sha256'];cases[name]=result
        shifted=Image.new('RGBA',size);shifted.paste(actual,(1,0))
        palette=actual.copy()
        if name=='FieldNames':
            rgba=bytearray(palette.tobytes())
            for i in range(0,len(rgba),4):rgba[i:i+3]=bytes(255-v for v in rgba[i:i+3])
            palette=Image.frombytes('RGBA',size,bytes(rgba))
            changed=actual.resize((125,63),Image.Resampling.BICUBIC).crop((0,0,115,63))
        else:
            for y in range(2,33):
                for x in range(6,43):
                    r,g,b,a=palette.getpixel((x,y));palette.putpixel((x,y),(min(255,r+45),g,b,a))
            changed=actual.copy();changed.paste((255,255,255,255),(3,34,45,45))
        controls=[('translated',shifted,higher),('palette',palette,higher),('lettering',changed,higher),
            ('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),
            ('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))]
        if name!='FieldNames':
            traced=higher.copy();traced.paste(actual.crop((3,34,45,45)).resize((336,88),Image.Resampling.NEAREST),(24,272));controls.append(('traced-caption',actual,traced))
        failures=[]
        for label,candidate,large in controls:
            try:compare(candidate,large)
            except AssertionError:failures.append(label)
            else:raise AssertionError(('Unfaithful Login control accepted',name,label))
        rejected[name]=failures
        if artifacts:
            actual.save(artifacts/(name+'-100.png'));higher.save(artifacts/(name+'-800.png'))
    return dict(cases=cases,rejected_mutations=rejected,negative_controls=sum(len(v) for v in rejected.values()))


def run(artifacts, source=None, images=None):
    source = source or Path(__file__).resolve().parents[2]/'Applications/Login/Resources/LoginArtwork.svg'
    art = Artwork(source)
    enabled = [name for name,node in art.symbols.items()
        if node.tag==f'{{{SVG}}}symbol' and node.get('data-reconstructed')=='true']
    assert enabled==['Panel','Fields','FieldNames','powerbuttonup','powerbuttondown','restartbuttonup','restartbuttondown'], ('Unqualified Login design enabled',enabled)
    original,fixture = artwork_original('login','Fields')
    if images: assert_svg_representations(art,'Fields',images/'Fields.tiff',(328,63))
    actual,higher = art.render('Fields',(328,63)),art.render('Fields',(2624,504))
    result = compare_fields(original,actual,higher)
    panel_original,panel_fixture=artwork_original('login','Panel')
    if images:assert_svg_representations(art,'Panel',images/'Panel.tiff',(462,260))
    panel_result,panel,panel_higher=panel_fidelity(art,panel_original)
    control_result=controls_fidelity(art)
    if images:
        for name in control_result['cases']:
            logical=(115,63) if name=='FieldNames' else (48,48)
            assert_svg_representations(art,name,images/(name+'.tiff'),logical)
    shifted = Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
    gap = actual.copy();gap.paste((255,255,255,255),(0,29,328,34))
    bevel = actual.copy();flat = actual.copy();height = actual.copy()
    for y in range(63):
        for x in range(328):
            p = original.getpixel((x,y))
            if p==(169,169,169,255):bevel.putpixel((x,y),(128,128,128,255))
            elif p[3] and p[:3]!=(255,255,255):flat.putpixel((x,y),(34,34,34,255))
    height.paste((255,255,255,255),(0,29,328,30))
    exchanged = actual.copy();exchanged.paste((169,169,169,255),(2,2,326,27))
    traced = higher.copy();raster = original.resize(higher.size,Image.Resampling.NEAREST)
    traced.paste(raster.crop((0,0,2624,8)),(0,0))
    field_mutations=[('translated',shifted,higher),('opaque-gap',gap,higher),('bevel-color',bevel,higher),
        ('flat-shade',flat,higher),('field-height',height,higher),('reversed-fill',exchanged,higher),
        ('traced-shade',actual,traced),('nearest-enlargement',actual,actual.resize(higher.size,Image.Resampling.NEAREST)),
        ('lanczos-enlargement',actual,actual.resize(higher.size,Image.Resampling.LANCZOS))]
    rejected=[]
    for name,candidate,large in field_mutations:
        try:compare_fields(original,candidate,large)
        except AssertionError:rejected.append(name)
        else:raise AssertionError(('Unfaithful Login Fields accepted',name))
    result.update(passed=True,designs=enabled,rejected_mutations=rejected,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        original_source_sha256=fixture['source_sha256'],submitted_image_verified=images is not None,
        native_density_qualification=False,remaining_login_designs=0,controls=control_result,
        negative_artwork_controls=len(rejected)+len(panel_result['rejected_mutations'])+control_result['negative_controls'],
        panel=panel_result,panel_original_source_sha256=panel_fixture['source_sha256'])
    artifacts.mkdir(parents=True)
    actual.save(artifacts/'Fields-100.png');higher.save(artifacts/'Fields-800.png')
    panel.save(artifacts/'Panel-100.png');panel_higher.save(artifacts/'Panel-800.png')
    for name in control_result['cases']:
        logical=(115,63) if name=='FieldNames' else (48,48)
        art.render(name,logical).save(artifacts/(name+'-100.png'))
        art.render(name,tuple(v*8 for v in logical)).save(artifacts/(name+'-800.png'))
    (artifacts/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path,required=True);parser.add_argument('--source',type=Path)
    parser.add_argument('--images',type=Path)
    args=parser.parse_args();run(args.artifacts,args.source,args.images)
