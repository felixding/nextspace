"""Keep the compact file-panel artwork faithful to the loaded originals."""
from PIL import Image,ImageOps
from artwork_reference import artwork_original,alpha_geometry,assert_not_enlarged,assert_vector_geometry,regional_error
from nextspirit_art import NextSpiritArtwork
from vector_art import Artwork


def verify(repository,home=None):
    originals={name:artwork_original('file-panel',name,repository)[0] for name in ('PanelHome','PanelMount','PanelUnmount')}
    media=Artwork(repository/'Applications/Artwork/FilePanel.svg');assert_vector_geometry(media.root)
    frames={name:[media.render(name,(n,n)) for n in (24,30,36,42,48)] for name in ('PanelMount','PanelUnmount')}
    regions=dict(rail=(3,10,5,20),metal=(9,3,13,7),front=(8,10,18,12),paper=(7,14,17,20))

    def compare(name,candidate):
     original=originals[name];low=candidate[0];geometry=alpha_geometry(original,low)
     assert geometry['original_bounds']==geometry['reconstructed_bounds']
     if name=='PanelMount':
      assert low.getchannel('A').tobytes()==original.getchannel('A').tobytes(),'Original housing/shadow alpha changed'
      for label,box in regions.items():
       if label=='paper':assert low.crop(box).tobytes()==original.crop(box).tobytes(),'Original white label changed'
       x0,y0,x1,y1=box;error=regional_error(original,low,[(x,y) for y in range(y0,y1) for x in range(x0,x1)])
       assert error['mean']<=10 and error['rms']<=14 and error['channel_mean_difference']<=4,(label,error)
      assert low.getpixel((2,2))==original.getpixel((2,2)) and low.getpixel((2,21))==original.getpixel((2,21))
      for y in range(3,21):assert low.getpixel((2,y))==original.getpixel((2,y))==(255,255,255,255)
      for y in range(4,21):assert low.getpixel((21,y))==original.getpixel((21,y))==(0,0,0,255)
     else:
      assert geometry['shape_overlap']>=.99 and geometry['alpha_rms_difference']<=16
      assert .98<=geometry['reconstructed_coverage']/geometry['original_coverage']<=1.02
      assert max(abs(a-b) for a,b in zip(geometry['original_center'],geometry['reconstructed_center']))<=.12
      red=lambda image:{(x,y) for y in range(24) for x in range(24) if image.getpixel((x,y))==(102,0,17,255)}
      assert red(low)==red(original) and len(red(low))==56,'Original maroon arrow geometry/palette changed'
     assert_not_enlarged(candidate,name)
     return geometry
    metrics={name:compare(name,images) for name,images in frames.items()};controls=[]
    for name,images in frames.items():
     shifted=Image.new('RGBA',(24,24));shifted.paste(images[0],(1,0));candidates=[('shift',[shifted,*images[1:]]),('mirror',[ImageOps.mirror(images[0]),*images[1:]])]
     for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):candidates.append((method.name,[images[0],*(images[0].resize(frame.size,method) for frame in images[1:])]))
     if name=='PanelMount':
      for label,point,color in [('lost-purple-junction',(2,2),(255,255,255,255)),('lost-left-bevel',(2,10),(51,34,68,255)),('wrong-metal',(10,5),(255,0,0,255)),('wrong-paper',(10,16),(170,170,170,255))]:
       altered=images[0].copy();altered.putpixel(point,color);candidates.append((label,[altered,*images[1:]]))
      changed=images[0].copy();changed.putalpha(changed.getchannel('A').point(lambda a:255 if a else 0));candidates.append(('opaque-shadow',[changed,*images[1:]]))
     else:
      candidates.append(('missing-arrow',frames['PanelMount']))
      altered=images[0].copy()
      for y in range(24):
       for x in range(24):
        if altered.getpixel((x,y))==(102,0,17,255):altered.putpixel((x,y),(204,0,0,255))
      candidates.append(('wrong-red',[altered,*images[1:]]))
     for label,candidate in candidates:
      try:compare(name,candidate)
      except AssertionError:controls.append(name+':'+label)
      else:raise AssertionError('Accepted panel source mutation '+name+':'+label)
    home=home or NextSpiritArtwork(repository/'Applications/Artwork/NeXTSpirit','workspace_icons')
    entry=home.entries['PanelHome'];assert entry['source']=='set1/Home01.icns' and entry['pixels']==1024 and entry['logical']==[24,24] and tuple(entry['content_bounds'])==originals['PanelHome'].getbbox()
    master=home.source_layers['Home'];padded=home.source_layers['PanelHome'];assert padded.crop(padded.getbbox()).tobytes()==master.crop(master.getbbox()).tobytes()
    home_frames=[home.render('PanelHome',(n,n)) for n in (24,30,36,42,48)];assert_not_enlarged(home_frames,'Unchanged artist house in the original panel footprint');assert home_frames[0].getbbox()==originals['PanelHome'].getbbox()
    return dict(passed=True,original_rgba_exact=False,mount_original_alpha_exact=True,original_arrow_maroon_pixels_exact=56,negative_controls=len(controls),rejected_mutations=controls,house_artist_master_pixels_unchanged=True,house_original_occupied_bounds_exact=True,geometry=metrics)
