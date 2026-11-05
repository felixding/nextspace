"""Use the artist's full-resolution artwork from verified complete sets."""
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageChops, ImageOps
from vector_art import Artwork, SVG


def fit_source(master, bounds, logical):
    """Pad the untouched source pixels to the original consumer's footprint."""
    if len(bounds) != 4 or len(logical) != 2 or not all(math.isfinite(n) for n in (*bounds,*logical)):
        raise ValueError('Icon content bounds and logical size must be finite coordinates')
    left,top,right,bottom = bounds;width,height = logical
    if width <= 0 or height <= 0 or not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError('Icon content bounds must fit its logical canvas')
    box = master.getchannel('A').getbbox()
    if box is None: raise ValueError('An icon needs visible source artwork')
    cropped = master.crop(box)
    factor = max(cropped.width/(right-left),cropped.height/(bottom-top))
    canvas = Image.new('RGBA',(math.ceil(width*factor),math.ceil(height*factor)))
    x = round((left+right)/2*canvas.width/width-cropped.width/2)
    y = round((top+bottom)/2*canvas.height/height-cropped.height/2)
    canvas.paste(cropped,(x,y))
    return canvas


def fitted_frame(master, bounds, logical, size):
    image = master.resize(size,Image.Resampling.LANCZOS)
    # Keep resampling lobes inside the original occupied rectangle.
    left,top,right,bottom = (bounds[0]*size[0]/logical[0],bounds[1]*size[1]/logical[1],
        bounds[2]*size[0]/logical[0],bounds[3]*size[1]/logical[1])
    left,top,right,bottom = math.floor(left),math.floor(top),math.ceil(right),math.ceil(bottom)
    for box in ((0,0,size[0],top),(0,bottom,size[0],size[1]),(0,top,left,bottom),(right,top,size[0],bottom)):
        image.paste((0,0,0,0),box)
    return image


def neighborhood_master(master, artwork_directory, state):
    """Keep the original two-house layout using one full-resolution artist house."""
    if state not in ('closed', 'open') or master.size != (1024, 1024):
        raise ValueError('Neighborhood artwork requires a 1024-pixel house and a known state')
    masks = Artwork(artwork_directory / 'Neighborhood.svg')
    lights = Artwork(artwork_directory / 'HomeStates.svg')
    repair = masks.render('RepairLeft', master.size).getchannel('A')
    rear = Image.composite(ImageOps.mirror(master), master, repair)
    rear.putalpha(ImageChops.multiply(rear.getchannel('A'), masks.render('BareHouse', master.size).getchannel('A')))
    # Both 32-point houses retain all 1024 source pixels in this 48-point canvas.
    size = 1536
    canvas = masks.render('Ground', (size, size))
    for x, y, source in ((0, 0, rear), (16, 10, master)):
        image = source
        if state == 'open':
            image = Image.alpha_composite(image, lights.render('HomeLights', image.size))
        left, top = x*32, y*32
        height = min(1024, size-top-1024)
        if height > 0:
            # The original open state leaves its reflections unlit.
            reflected = ImageOps.flip(source).crop((0, 0, 1024, height))
            reflected.putalpha(ImageChops.multiply(reflected.getchannel('A'),
                masks.render('Reflection', reflected.size).getchannel('A')))
            canvas.alpha_composite(reflected, (left, top+1024))
        canvas.alpha_composite(image, (left, top))
    if state == 'open':
        canvas = Image.alpha_composite(canvas, masks.render('NeighborSmoke', canvas.size))
    return canvas


class NextSpiritArtwork:
    def __init__(self, pack, group='application_icons'):
        self.pack = pack
        self.source = Path(__file__).resolve().parents[2] / 'Applications/Artwork/NextSpirit.json'
        self.manifest = json.loads(self.source.read_text())
        for name, expected in self.manifest['files'].items():
            path = pack / name
            with path.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError('NeXTSpirit source differs: ' + str(path))
        self.symbols, self.images = {}, {}
        self.source_layers, self.overlay_layers, self.layout_layers = {}, {}, {}
        self.master_sizes = {}
        masters, overlays = {}, {}
        self.entries = self.manifest[group]
        for name, case in self.entries.items():
            logical = case.get('logical', (48, 48))
            self.symbols[name] = {'data-logical-size': ' '.join(map(str, logical))}
            key = case['source'], case['pixels']
            if key not in masters:
                with Image.open(pack / case['source']) as image:
                    image.size = (case['pixels'], case['pixels'])
                    image.load()
                    masters[key] = image.convert('RGBA')
            base = masters[key]
            if 'composition' in case:
                if case['composition'] != 'neighborhood' or tuple(logical) != (48, 48):
                    raise ValueError('Unknown artist artwork composition')
                base = neighborhood_master(base, self.source.parent, case['state'])
            bounds = case.get('base_bounds', case.get('content_bounds'))
            if bounds:
                base = fit_source(base, bounds, logical)
                self.layout_layers[name] = base
            self.source_layers[name] = base
            self.master_sizes[name] = tuple(round(case['pixels']*v/max(logical)) for v in logical)
            if 'composition' in case:
                self.master_sizes[name] = base.size
            if 'overlay_artwork' in case:
                path = self.source.parent / case['overlay_artwork']
                if path not in overlays:
                    overlays[path] = Artwork(path)
                self.overlay_layers[name] = masters[key], overlays[path], case['overlay_symbol']
            opacity = case.get('opacity', 1)
            if not math.isfinite(opacity) or not 0 <= opacity <= 1:
                raise ValueError('Artwork opacity must be between zero and one')
            self.images[name] = self.render(name, self.master_sizes[name])

    def render(self, name, size):
        size = (size, size) if isinstance(size, int) else size
        maximum = self.master_sizes[name] if name in self.master_sizes else self.images[name].size
        if any(target > source for target, source in zip(size, maximum)):
            raise ValueError('NeXTSpirit artwork must never be enlarged')
        source = self.source_layers[name] if name in self.source_layers else self.images[name]
        case = self.entries.get(name, {})
        if name in self.layout_layers:
            result = fitted_frame(source, case.get('base_bounds') or case['content_bounds'], case['logical'], size)
        else:
            result = source.resize(size, Image.Resampling.LANCZOS)
        if name in self.overlay_layers:
            _, art, symbol = self.overlay_layers[name]
            result = Image.alpha_composite(result, art.render(symbol, size))
        if 'base_bounds' in case and 'content_bounds' in case:
            result = fitted_frame(result, case['content_bounds'], case['logical'], size)
        if case.get('opacity', 1) != 1:
            result.putalpha(result.getchannel('A').point(lambda value: round(value*case['opacity'])))
        return result


class NextSpiritFolders(NextSpiritArtwork):
    def __init__(self, source, pack):
        super().__init__(pack, 'folder_states')
        self.symbols = Artwork(source).symbols
        self.symbols['open'] = ET.Element(f'{{{SVG}}}symbol', {
            'viewBox': '0 0 48 48', 'data-reconstructed': 'true',
            'data-workspace-files': 'openFolder.tiff'})
        # Match Workspace's unavailable treatment without changing the artwork.
        red, green, blue, alpha = self.images['closed'].split()
        self.images['bad'] = Image.merge('RGBA', (
            *(channel.point(lambda value: (value + 170) // 2)
              for channel in (red, green, blue)), alpha))

