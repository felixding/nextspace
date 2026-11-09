"""Native progress frames, engine model transitions and owned frame lifetimes."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time
from PIL import Image
from native_date_fields import FirefoxDates


def run(test, references):
    native = set()
    for path in references.glob('animation-*.argb'):
        image = Image.frombytes('RGBA', (128, 24), path.read_bytes(), 'raw', 'BGRA')
        canvas = Image.new('RGBA', image.size, 'white');canvas.alpha_composite(image)
        native.add(canvas.convert('RGB').tobytes())
    assert len(native) > 1, 'Independent original native animation references'
    test.js('document.querySelectorAll("progress").forEach(e=>e.style.boxSizing="border-box")')
    test.until(lambda: test.js('animated.getBoundingClientRect().width') == 128, 'fixed native viewport')

    def capture(identifier):
        rect = test.js('document.getElementById('+json.dumps(identifier)+').getBoundingClientRect().toJSON()')
        response = test.command('capture '+test.command('outputs')[0]['name'])
        event = response['event']
        image = Image.frombytes('RGB', (event['width'], event['height']), Path(response['path']).read_bytes(),
                                'raw', 'BGRX', event['stride'])
        left, top = (math.floor(test.origin[0]+rect['x']+.5),
                     math.floor(test.origin[1]+rect['y']+.5))
        cropped = image.crop((left, top, left+128, top+24))
        cropped.save(test.root/(identifier+'-progress-actual.png'))
        return cropped.tobytes()

    def animated(identifier, label):
        hashes = set()
        for index in range(8):
            pixels = capture(identifier)
            test.check(label+'-whole-native-frame-'+str(index), pixels in native)
            hashes.add(hashlib.sha256(pixels).hexdigest())
            time.sleep(.035)
        test.check(label+'-native-timer-advances', len(hashes) > 1)

    # A synchronous layout query does not commit the corresponding browser
    # surface. Wait for the first native frame after the border-box change.
    test.until(lambda: capture('animated') in native, 'first committed native progress frame')
    animated('animated', 'initial')
    animated('second', 'second')
    before = capture('static');time.sleep(.2)
    test.check('determinate-progress-remains-stable', capture('static') == before)
    test.js('window.events=[];animated.value=.5')
    time.sleep(.15);before = capture('animated');time.sleep(.2)
    test.check('engine-value-stops-native-animation', capture('animated') == before)
    test.js('animated.removeAttribute("value")')
    time.sleep(.15);animated('animated', 'restarted')
    test.js('window.detachedProgress=animated;animated.remove()')
    time.sleep(.15)
    rows = [json.loads(line) for line in (test.root/'helper.jsonl').read_text().splitlines()]
    test.check('removed-progress-retires-original-native-control',
               any(r.get('event') == 'native-progress-destroy' for r in rows))
    test.js('document.body.append(detachedProgress);window.detachedProgress=null')
    time.sleep(.15);animated('animated', 'reinserted')
    test.check('native-animation-never-synthesizes-dom-edits', test.js('events.length') == 0)
    before = len((test.root/'helper.jsonl').read_text().splitlines())
    test.js('animated.style.appearance="none";animated.style.background="magenta"')
    time.sleep(.2)
    rows = [json.loads(line) for line in (test.root/'helper.jsonl').read_text().splitlines()[before:]]
    test.check('author-styling-retires-native-animation',
               any(r.get('event') == 'native-progress-destroy' for r in rows))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--references', required=True, type=Path)
    args = parser.parse_args()
    trial = FirefoxDates(args.root, args.port, '../../Experiments/ChromiumScrollers/test-animation.html',
                         'Native animation invalidation transport')
    try:
        run(trial, args.references)
    finally:
        (trial.root/'progress-animation-checks.json').write_text(json.dumps(trial.results, indent=2)+'\n')
        trial.close()
