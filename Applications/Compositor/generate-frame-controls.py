#!/usr/bin/env python3
"""Compile the shared polygon title glyphs to native Cairo paths."""
from pathlib import Path
import math
import re
import sys
import xml.etree.ElementTree as ET

TOKEN = r'[MLHVZ]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'


def path_commands(data, offset_x=0, offset_y=0):
    if re.sub(TOKEN, '', data).replace(',', '').strip():
        raise ValueError('Title controls support absolute M/L/H/V/Z paths only')
    tokens = re.findall(TOKEN, data)
    command, x, y, start = None, 0, 0, None
    index = 0
    while index < len(tokens):
        if tokens[index] in ('M', 'L', 'H', 'V', 'Z'):
            command = tokens[index]
            index += 1
        if command == 'Z':
            assert start is not None, 'Path must start with M'
            yield ('CLOSE_PATH',)
            x, y = start
            command = None
            continue
        assert command is not None and (start is not None or command == 'M'), 'Path must start with M'
        count = 2 if command in ('M', 'L') else 1
        values = tuple(map(float, tokens[index:index+count]))
        assert len(values) == count and all(math.isfinite(v) for v in values), 'Invalid path coordinate'
        index += count
        if command in ('M', 'L'):
            x, y = values
        elif command == 'H':
            x = values[0]
        else:
            y = values[0]
        if command == 'M':
            start = (x, y)
        yield ('MOVE_TO' if command == 'M' else 'LINE_TO', x + offset_x, y + offset_y)
        if command == 'M':
            command = 'L'


def primitives(root, symbol):
    ids = {node.get('id'): node for node in root.iter() if node.get('id')}

    def walk(node, style, x=0, y=0, stack=()):
        style = dict(style, **node.attrib)
        tag = node.tag.rsplit('}', 1)[-1]
        assert 'transform' not in node.attrib, 'Use explicit coordinates in title controls'
        assert not any(key in node.attrib for key in ('style', 'clip-path', 'mask', 'opacity', 'fill-opacity'))
        if tag == 'use':
            reference = node.get('href', '')
            assert reference.startswith('#') and reference not in stack
            yield from walk(ids[reference[1:]], style,
                x + float(node.get('x', 0)), y + float(node.get('y', 0)), stack + (reference,))
        elif tag in ('svg', 'g'):
            for child in node:
                yield from walk(child, style, x, y, stack)
        elif tag == 'path':
            assert style.get('shape-rendering') == 'crispEdges'
            assert style.get('fill-rule', 'nonzero') == 'nonzero'
            assert style.get('stroke', 'none') == 'none'
            color = style.get('fill', 'none')
            if color == 'currentColor':
                color = style.get('color', '#000')
            assert color.startswith('#') and len(color) in (4, 7), color
            digits = color[1:]
            if len(digits) == 3:
                digits = ''.join(digit * 2 for digit in digits)
            yield int(digits, 16), list(path_commands(node.get('d', ''), x, y))
        else:
            raise ValueError(f'Unsupported title-control geometry: {tag}')

    return list(walk(ids[symbol], root.attrib))


def main(destination, source):
    root = ET.parse(source).getroot()
    assert root.get('viewBox') == '0 0 12 12'
    lines = ['/* Generated from WindowControls.svg; do not edit. */',
        'struct decoration_primitive { const cairo_path_t *path; uint32_t rgb; };',
        'struct decoration_glyph { unsigned count; const struct decoration_primitive *primitives; };']
    for symbol in ('common_Close', 'common_CloseH', 'common_CloseBroken', 'common_CloseBrokenH', 'common_Miniaturize', 'common_MiniaturizeH'):
        name = symbol.lower()
        shapes = primitives(root, symbol)
        for index, (color, commands) in enumerate(shapes):
            prefix = f'{name}_{index}'
            lines.append(f'static cairo_path_data_t {prefix}_data[] = {{')
            for operation, *point in commands:
                lines.append(f'  {{.header = {{CAIRO_PATH_{operation}, {2 if point else 1}}}}},')
                if point:
                    lines.append('  {.point = {' + ', '.join(f'{v:g}' for v in point) + '}},')
            lines += ['};', f'static const cairo_path_t {prefix}_path = {{CAIRO_STATUS_SUCCESS, '
                + f'{prefix}_data, sizeof({prefix}_data) / sizeof({prefix}_data[0])' + '};']
        lines.append(f'static const struct decoration_primitive {name}_primitives[] = {{')
        for index, (color, commands) in enumerate(shapes):
            lines.append(f'  {{&{name}_{index}_path, 0x{color:06x}}},')
        lines += ['};', f'static const struct decoration_glyph {name} = '
            + '{' + f'{len(shapes)}, {name}_primitives' + '};']
    Path(destination).write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main(*sys.argv[1:])
