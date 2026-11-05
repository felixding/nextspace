"""Render authored SVG artwork directly at the requested backing resolution."""
from io import BytesIO
import base64
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
from PIL import Image
from PIL.TiffImagePlugin import AppendingTiffWriter


SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)
DENSITIES = (120, 150, 180, 210, 240, 360, 480, 600, 720, 840, 960)


def backing_size(logical, density):
    return int((logical * density + 60) // 120)


def backing_sizes(logical):
    return tuple(backing_size(logical, density) for density in DENSITIES)


def write_tiff(artwork, symbol, target, logical, densities=DENSITIES):
    """Render each TIFF representation from its master, preserving logical size."""
    declared = artwork.symbols[symbol].get('data-logical-size')
    if declared:
        logical = tuple(map(float, declared.split()))
    width, height = (logical, logical) if isinstance(logical, int) else logical
    with target.open('w+b') as output:
        writer = AppendingTiffWriter(output)
        for density in densities:
            size = tuple(backing_size(value, density) for value in (width, height))
            image = artwork.render(symbol, size)
            image.save(writer, format='TIFF', dpi=(72*size[0]/width, 72*size[1]/height), compression='raw')
            writer.newFrame()
        writer.close()
        del writer


def write_resource_images(artwork, symbol, output, filenames, logical, densities=DENSITIES[:5]):
    """Write one image master to equivalent resources, preserving canonical aliases."""
    names = [Path(name) for name in filenames]
    if not names or len(set(names)) != len(names) or any(
            name.is_absolute() or '..' in name.parts or name.suffix != '.tiff' for name in names):
        raise ValueError('Image targets must be unique relative TIFF paths')
    targets = [output/name for name in names]
    canonical = targets[0]
    if canonical.is_symlink():
        raise ValueError('The canonical image resource must be a regular file')
    for target in targets[1:]:
        if target.is_symlink() and target.resolve() != canonical.resolve():
            raise ValueError('Image aliases must point to the canonical resource: ' + str(target))
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
    write_tiff(artwork, symbol, canonical, logical, densities)
    for target in targets[1:]:
        if not target.is_symlink():
            shutil.copyfile(canonical, target)


class Artwork:
    def __init__(self, path):
        path = Path(path)
        self.root = ET.parse(path).getroot()
        # Inline local SVG definitions so shared artwork also works over stdin.
        loaded = set()
        for node in list(self.root.iter()):
            reference = node.get('href', '')
            if not reference or reference.startswith('#'):
                continue
            filename, separator, fragment = reference.partition('#')
            relative = Path(filename)
            if node.tag == f'{{{SVG}}}image' and not separator and \
                    not relative.is_absolute() and ':' not in filename and relative.suffix == '.png':
                source = path.parent / relative
                with Image.open(source) as image:
                    if image.format != 'PNG':
                        raise ValueError('Artwork image references must contain PNG pixels')
                    image.verify()
                node.set('href', 'data:image/png;base64,' + base64.b64encode(source.read_bytes()).decode('ascii'))
                continue
            if node.tag != f'{{{SVG}}}use' or not separator or not fragment or \
                    relative.is_absolute() or ':' in filename or relative.suffix != '.svg':
                raise ValueError('Artwork references must name local SVG definitions: ' + reference)
            source = (path.parent / relative).resolve()
            if source not in loaded:
                shared = ET.parse(source).getroot().find(f'{{{SVG}}}defs')
                assert shared is not None, source
                self.root.find(f'{{{SVG}}}defs').extend(list(shared))
                loaded.add(source)
            node.set('href', '#' + fragment)
        self.symbols = {node.get('id'): node for node in self.root.iter() if node.get('id')}
        identifiers = [node.get('id') for node in self.root.iter() if node.get('id')]
        assert len(identifiers) == len(self.symbols), 'Duplicate artwork definition'
        self.viewbox = self.root.get('viewBox')
        self.preview = self.root.find(f'{{{SVG}}}use[@id="preview"]')
        assert self.preview is not None, path
        for node in self.root.iter():
            kind = node.tag.rsplit('}', 1)[-1].lower()
            assert kind not in ('feimage', 'foreignobject', 'text'), path
            if kind == 'image':
                assert node.get('href', '').startswith('data:image/png;base64,'), path
            reference = node.get('href')
            embedded_image = node.tag == f'{{{SVG}}}image' and reference and reference.startswith('data:image/png;base64,')
            assert reference is None or reference.startswith('#') or embedded_image, path
            assert reference is None or embedded_image or reference[1:] in self.symbols, reference
        self.converter = shutil.which('rsvg-convert')
        if not self.converter:
            raise RuntimeError('rsvg-convert is required to render the SVG artwork')
        self.cache = {}

    def render(self, symbol, size):
        width, height = (size, size) if isinstance(size, int) else size
        assert symbol in self.symbols and width > 0 and height > 0, (symbol, size)
        key = (symbol, width, height)
        if key not in self.cache:
            self.preview.set('href', '#' + symbol)
            viewbox = self.symbols[symbol].get('viewBox', self.viewbox)
            self.root.set('viewBox', viewbox)
            _, _, logical_width, logical_height = viewbox.split()
            self.preview.set('width', logical_width)
            self.preview.set('height', logical_height)
            self.cache[key] = subprocess.check_output([self.converter, '--format=png',
                '--width', str(width), '--height', str(height)], input=ET.tostring(self.root))
        with Image.open(BytesIO(self.cache[key])) as image:
            assert image.size == (width, height)
            return image.convert('RGBA')


def premultiplied_bgra(image):
    rgba = image.convert('RGBa').tobytes()
    pixels = bytearray(len(rgba))
    pixels[0::4], pixels[1::4], pixels[2::4], pixels[3::4] = rgba[2::4], rgba[1::4], rgba[0::4], rgba[3::4]
    return pixels
