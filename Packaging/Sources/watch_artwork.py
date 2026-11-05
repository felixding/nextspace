"""Regenerate continuous busy-cursor gradients from their SVG authoring model."""
import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

SVG = 'http://www.w3.org/2000/svg'
PREFIX = 'original-watch-'


def definitions(model):
    assert model['version'] == 1 and len(model['frames']) == 3
    result = ET.Element(f'{{{SVG}}}defs')
    def node(parent, tag, **attributes):
        return ET.SubElement(parent, f'{{{SVG}}}{tag}', attributes)
    clip = node(result, 'clipPath', id=PREFIX+'disc')
    node(clip, 'circle', cx='12', cy='12', r=str(model['radius']), **{'shape-rendering':'geometricPrecision'})
    for frame, coefficients in enumerate(model['frames']):
        lower, upper = model['bounds'][frame]
        group = node(result, 'g', id=f'watch-{frame+1}', filter='url(#original-shadow)', **{'data-reconstructed':'true'})
        paint = node(group, 'g', **{'clip-path':f'url(#{PREFIX}disc)', 'shape-rendering':'crispEdges'})
        for sector in range(model['sectors']):
            angle = (sector+.5)*2*math.pi/model['sectors']
            identifier = f'{PREFIX}{frame}-{sector}'
            gradient = node(result, 'radialGradient', id=identifier, cx='12', cy='12', r='9',
                **{'gradientUnits':'userSpaceOnUse', 'color-interpolation':'sRGB'})
            for stop in range(model['stops']):
                radius = 9*stop/(model['stops']-1); r = radius/8
                terms = [r**p for p in range(model['degree']+1)]
                for k in range(1,model['harmonics']+1):
                    for p in range(1,model['degree']+2):
                        terms.extend((r**p*math.cos(k*angle),r**p*math.sin(k*angle)))
                dx,dy = r*math.cos(angle),r*math.sin(angle)
                for width in model['hub_widths']:
                    value = math.exp(-r*r/(2*width*width))
                    terms.extend((value,value*dx,value*dy,value*dx*dy,value*(dx*dx-dy*dy)))
                assert len(terms) == len(coefficients)
                color = [min(upper[channel],max(lower[channel],sum(value*row[channel]
                    for value,row in zip(terms,coefficients)))) for channel in range(3)]
                node(gradient, 'stop', offset=str(stop/(model['stops']-1)),
                    **{'stop-color':'#'+''.join(f'{round(value*255):02x}' for value in color)})
            a = sector*2*math.pi/model['sectors']-.0001
            b = (sector+1)*2*math.pi/model['sectors']+.0001
            points = (12+9*math.cos(a),12+9*math.sin(a),12+9*math.cos(b),12+9*math.sin(b))
            node(paint, 'path', d='M12 12L%.6f %.6fA9 9 0 0 1 %.6f %.6fZ'%points,
                fill=f'url(#{identifier})')
    hub = node(result, 'linearGradient', id=PREFIX+'hub', x1='11', y1='11', x2='13', y2='13',
        gradientUnits='userSpaceOnUse')
    node(hub, 'stop', offset='0', **{'stop-color':'#555'})
    node(hub, 'stop', offset='1', **{'stop-color':'#a8a8a8'})
    fade = node(result, 'radialGradient', id=PREFIX+'hub-fade')
    node(fade, 'stop', offset='0', **{'stop-color':'#fff'})
    node(fade, 'stop', offset='.5', **{'stop-color':'#fff'})
    node(fade, 'stop', offset='1', **{'stop-color':'#fff','stop-opacity':'0'})
    mask = node(result, 'mask', id=PREFIX+'hub-mask', maskUnits='userSpaceOnUse',
        x='10', y='10', width='4', height='4')
    node(mask, 'circle', cx='12', cy='12', r='1.6', fill=f'url(#{PREFIX}hub-fade)')
    for frame in range(3):
        node(result.find(f".//*[@id='watch-{frame+1}']"), 'circle', cx='12', cy='12', r='1.6',
            fill=f'url(#{PREFIX}hub)', mask=f'url(#{PREFIX}hub-mask)')
    return list(result)


def signature(node):
    return (node.tag,sorted(node.attrib.items()),(node.text or '').strip(),
        [signature(child) for child in node])


def selected(node):
    name = node.get('id','')
    return name.startswith(PREFIX) or name in ('watch-1','watch-2','watch-3')


def validate(root):
    metadata = root.find(f"{{{SVG}}}metadata[@id='watch-model']")
    if metadata is None:
        return
    generated = definitions(json.loads(metadata.text))
    actual = [node for node in root.find(f'{{{SVG}}}defs') if selected(node)]
    assert {node.get('id'):signature(node) for node in actual} == {
        node.get('id'):signature(node) for node in generated}, 'Busy-cursor SVG differs from its authoring model'


def regenerate(path):
    tree = ET.parse(path); root = tree.getroot(); defs = root.find(f'{{{SVG}}}defs')
    model = json.loads(root.find(f"{{{SVG}}}metadata[@id='watch-model']").text)
    for node in list(defs):
        if selected(node): defs.remove(node)
    defs.extend(definitions(model))
    ET.register_namespace('', SVG); ET.indent(tree, space='  ')
    tree.write(path, encoding='unicode'); path.write_text(path.read_text()+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    if args.check: validate(ET.parse(args.source).getroot())
    else: regenerate(args.source)
