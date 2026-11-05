"""Preserve the Login module's original monitor, fields, bevel and materials."""
import copy
from PIL import Image, ImageOps
from artwork_reference import artwork_original, alpha_geometry, assert_not_enlarged, assert_vector_geometry, regional_error
from vector_art import Artwork, backing_size


def verify(repository):
    artwork = Artwork(repository/'Applications/Login/Preferences/Artwork.svg')
    assert_vector_geometry(artwork.root)
    original, _ = artwork_original('login-preferences', 'LoginPreferences', repository)
    display = Artwork(repository/'Applications/Preferences/Artwork.svg')
    sizes = [tuple(backing_size(v, density) for v in (66,57)) for density in (120,150,180,210,240)]
    frames = [artwork.render('LoginPreferences', size) for size in sizes]
    housing = [display.render('DisplayMonitor', size) for size in sizes]
    exact = dict(first_field=(29,21,41,23), second_field=(29,24,41,26),
        top_bevel=(21,16,43,17), left_bevel=(21,17,22,29))
    materials = dict(panel=(23,18,27,28), upper_panel=(29,18,40,20),
        upper_glass=(18,12,48,15), lower_glass=(18,32,48,35))

    def compare(candidate):
        low = candidate[0]
        geometry = alpha_geometry(original, low)
        assert geometry['original_bounds'] == geometry['reconstructed_bounds']
        assert geometry['shape_overlap'] >= .955 and geometry['alpha_rms_difference'] <= 21
        assert .975 <= geometry['reconstructed_coverage']/geometry['original_coverage'] <= 1.025
        assert max(abs(a-b) for a,b in zip(geometry['original_center'],geometry['reconstructed_center'])) <= .15
        for label, box in exact.items():
            assert low.crop(box).tobytes() == original.crop(box).tobytes(), label
        errors = {}
        for label, (x0,y0,x1,y1) in materials.items():
            error = regional_error(original, low, [(x,y) for y in range(y0,y1) for x in range(x0,x1)])
            assert error['mean'] <= 6 and error['rms'] <= 8 and error['channel_mean_difference'] <= 2, (label,error)
            errors[label] = error
        assert low.getchannel('A').getextrema()[1] == 240, 'Original translucent housing changed'
        for image, reference in zip(candidate, housing):
            # Only the glass and its miniature login panel differ from Display.
            for y in range(image.height):
                for x in range(image.width):
                    if x+1 <= 16*image.width/66 or x >= 50*image.width/66 or y+1 <= 11*image.height/57 or y >= 36*image.height/57:
                        assert image.getpixel((x,y)) == reference.getpixel((x,y)), 'Shared monitor housing changed'
        assert_not_enlarged(candidate, 'Login preference monitor')
        return dict(geometry=geometry, materials=errors)

    metrics = compare(frames)
    shifted = Image.new('RGBA', (66,57)); shifted.paste(frames[0], (1,0))
    candidates = [('shift', [shifted,*frames[1:]]), ('mirror', [ImageOps.mirror(frames[0]),*frames[1:]]),
        ('missing-login-panel', housing)]
    for method in (Image.Resampling.NEAREST,Image.Resampling.LANCZOS):
        candidates.append((method.name, [frames[0],*(frames[0].resize(size,method) for size in sizes[1:])]))
    for label, match, change in (
            ('missing-fields', lambda n:n.get('d','').startswith('M29 21'), ('fill','#888')),
            ('missing-bevel', lambda n:n.get('d','').startswith('M21 16H43'), ('fill','#888')),
            ('opaque-housing', lambda n:n.get('opacity')=='.94117647' and not n.get('id'), ('opacity','1')),
            ('wrong-glass', lambda n:n.get('stop-color')=='#494567', ('stop-color','#ff0000')),
            ('wrong-panel', lambda n:n.get('stop-color')=='#929496', ('stop-color','#ff0000'))):
        altered = copy.deepcopy(artwork); altered.cache.clear()
        next(node for node in altered.root.iter() if match(node)).set(*change)
        candidates.append((label,[altered.render('LoginPreferences',size) for size in sizes]))
    for label, candidate in candidates:
        try: compare(candidate)
        except AssertionError: pass
        else: raise AssertionError('Accepted Login preference source mutation: '+label)
    return dict(passed=True, original_fields_and_bevels_rgba_exact=True,
        shared_monitor_housing_unchanged=True, original_rgba_exact=False,
        negative_controls=len(candidates), **metrics)
