"""Original-frame checks for the busy cursor's continuous color field."""
import colorsys


def compare(original, actual, references):
    assert original.size == actual.size == (24,24)
    old,new = list(original.getdata()),list(actual.getdata())
    reference_pixels = [list(image.getdata()) for image in references]
    foreground = {i for i in range(576) if sum(pixels[i][3]>=128 for pixels in reference_pixels)>=2}
    assert {i for i,pixel in enumerate(new) if pixel[3]>=128} == foreground, 'Busy-cursor outline changed'
    core = [i for i in foreground if 0<i%24<23 and 0<i//24<23 and
        all(i+offset in foreground for offset in (-25,-24,-23,-1,1,23,24,25))]
    assert len(foreground)==210 and len(core)==150
    assert all(old[i][3]==new[i][3]==255 for i in core)
    differences = [abs(a-b) for i in core for a,b in zip(old[i][:3],new[i][:3])]
    maximum,mean = max(differences),sum(differences)/len(differences)
    assert maximum<=12 and mean<=4, ('Busy-cursor color/shading changed',maximum,mean)
    hue = []
    for i in core:
        if max(old[i][:3])-min(old[i][:3])>=64:
            before = colorsys.rgb_to_hsv(*(value/255 for value in old[i][:3]))[0]
            after = colorsys.rgb_to_hsv(*(value/255 for value in new[i][:3]))[0]
            difference = abs(before-after)
            hue.append(min(difference,1-difference)*360)
    assert max(hue)<=4, ('Busy-cursor hue changed',max(hue))
    hub = [y*24+x for y in (11,12) for x in (11,12)]
    hub_delta = max(abs(a-b) for i in hub for a,b in zip(old[i],new[i]))
    assert hub_delta<=8, ('Busy-cursor gray hub changed',hub_delta)
    shadow = 0
    for i,(before,after) in enumerate(zip(old,new)):
        x,y = i%24,i//24
        if all(yy*24+xx not in foreground for yy in range(max(0,y-2),min(24,y+3))
                for xx in range(max(0,x-2),min(24,x+3))):
            shadow = max(shadow,*(abs(a-b) for a,b in zip(before[:3],after[:3])),
                *(abs(a-before[3]-b+after[3]) for a,b in zip(before[:3],after[:3])))
    assert shadow<=8, ('Busy-cursor shadow changed',shadow)
    variation = len(foreground ^ {i for i,pixel in enumerate(old) if pixel[3]>=128})
    assert variation<=2
    return dict(reference_check='animated-color-field',foreground_pixels=len(foreground),
        original_edge_variation=variation,interior_pixels=len(core),maximum_color_difference=maximum,
        mean_color_difference=mean,maximum_hue_difference_degrees=max(hue),
        hub_anchors=len(hub),maximum_hub_difference=hub_delta,
        maximum_far_shadow_composite_difference=shadow)


def negative_controls(original, actual, references, other_phase):
    from PIL import Image
    shifted = Image.new('RGBA',actual.size);shifted.paste(actual,(1,0))
    rotated = actual.copy();rotated.putdata([(p[1],p[2],p[0],p[3]) for p in actual.getdata()])
    gray = actual.copy();gray.putdata([((p[0]+p[1]+p[2])//3,)*3+(p[3],) for p in actual.getdata()])
    shaded = actual.copy();shaded.putdata([(*(round(value*.8) for value in p[:3]),p[3]) for p in actual.getdata()])
    hub = actual.copy();hub.putpixel((12,12),(200,200,200,255))
    shadow = actual.copy();shadow.putpixel((0,0),(9,9,9,9))
    controls = [('translated',shifted),('palette-rotated',rotated),('desaturated',gray),
        ('shade-changed',shaded),('phase-swapped',other_phase),('hub-changed',hub),('shadow-tinted',shadow)]
    for label,image in controls:
        try:compare(original,image,references)
        except AssertionError:pass
        else:raise AssertionError(('Unfaithful busy cursor accepted',label))
    return [label for label,_ in controls]
