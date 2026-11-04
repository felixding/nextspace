"""Compare cursor-independent samples with separately captured display pixels."""
from PIL import Image

# Convert scanout-buffer coordinates to the displayed orientation. This uses
# Pillow's image transforms, independently of the compositor's scene traversal.
TRANSFORMS=(None,Image.Transpose.ROTATE_270,Image.Transpose.ROTATE_180,
            Image.Transpose.ROTATE_90,Image.Transpose.FLIP_LEFT_RIGHT,
            Image.Transpose.TRANSPOSE,Image.Transpose.FLIP_TOP_BOTTOM,Image.Transpose.TRANSVERSE)


def check_frame(frame,raw,output,transform,command):
    image=Image.frombytes('RGB',(frame['width'],frame['height']),raw,'raw','BGRX',frame['stride'])
    if frame['flags'] & 1:image=image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if TRANSFORMS[transform] is not None:image=image.transpose(TRANSFORMS[transform])
    scale=output['scale']/120;records=[]
    for fx,fy in [(1,1),(3,1),(1,3),(3,3),(2,2)]:
        px,py=image.width*fx//4,image.height*fy//4
        x,y=output['x']+(px+.5)/scale,output['y']+(py+.5)/scale
        # The reference was captured before this move. The sample must exclude
        # the cursor even when it now covers the selected display pixel.
        assert command(f'pointer {int(x)} {int(y)}')['ok']
        actual=command(f'sample-color {x:.9f} {y:.9f}');assert actual['ok'],(output,transform,actual)
        assert actual['argb']>>24==255,('Display sample lost its opaque background',actual)
        color=tuple((actual['argb']>>shift)&255 for shift in (16,8,0));expected=image.getpixel((px,py))
        maximum=max(abs(a-b) for a,b in zip(color,expected))
        assert maximum<=1,('Scene sample differs from the display',output,transform,(x,y),(px,py),color,expected)
        records.append(dict(argb=actual['argb'],point=[x,y],display_pixel=[px,py],rgb=list(color),expected=list(expected),maximum_channel_difference=maximum))
    return records
