"""Check actual popup windows against their native control's measured geometry."""
import argparse
import json
import math
from native_density_controls import DensityFixture
from native_popup_fixture import PopupFixture


def run(test):
    native = PopupFixture(test.root, test.command, None, test.check, test.pid, None, None)
    geometry = []
    for index, (x, y) in enumerate(((140, 80), (250, 130))):
        assert test.command(f'move {test.window["id"]} {x} {y}')["ok"]
        test.until(lambda: test.js('[screenX,screenY]') == [x+test.window['frame_left'], y+test.window['frame_top']],
                   'original browser screen origin')
        test.update_origin()
        test.js('document.getElementById("select").focus()')
        for down in (1, 0):
            assert test.command(f'key 57 {down}')["ok"]
        menu = test.until(native.native_menu, 'original native popup window')
        offset = native.native_state(3).parts[6]
        rect = test.js('document.getElementById("select").getBoundingClientRect().toJSON()')
        expected = [math.floor((test.origin_pixels[axis] + rect[name]*test.scale + value)/test.output_scale+.5)
                    for axis, name, value in ((0, 'x', offset.x), (1, 'y', offset.y))]
        geometry.append(dict(window=[x, y], expected=expected, actual=[menu['x'], menu['y']],
                             native_offset=[offset.x, offset.y], field=rect))
        (test.root/'popup-origin-geometry.json').write_text(json.dumps(geometry, indent=2)+'\n')
        test.check(f'moved-window-{index}-popup-uses-original-native-anchor', [menu['x'], menu['y']] == expected)
        for down in (1, 0):
            assert test.command(f'key 1 {down}')["ok"]
        test.until(lambda: not native.native_menu(), 'original native menu completion')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--family', choices=['chromium', 'firefox'], required=True)
    parser.add_argument('--port', type=int, default=2870)
    parser.add_argument('--scale', type=float, default=1)
    args = parser.parse_args()
    test = DensityFixture(args.root, args.family, args.port, args.scale,
                          '../../Experiments/ChromiumScrollers/test-popups.html', 'Native select model transport',
                          report='popup-origin-checks.json')
    try:
        run(test)
    finally:
        (test.root/'popup-origin-checks.json').write_text(json.dumps(test.results, indent=2)+'\n')
        if args.family == 'firefox':
            test.driver.close()
