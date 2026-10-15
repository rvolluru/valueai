import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { PNG } = require('pngjs');
const root = new URL('../../', import.meta.url);
const config = JSON.parse(readFileSync(new URL('app.json', root))).expo;
const read = filename => PNG.sync.read(readFileSync(new URL(filename, root)));

test('iOS and legacy Android use the same opaque 1024px logo icon', () => {
  const png = read(config.icon);
  assert.equal(png.width, 1024);
  assert.equal(png.height, 1024);
  for (let i = 3; i < png.data.length; i += 4) assert.equal(png.data[i], 255);
  assert.deepEqual(readFileSync(new URL(config.icon, root)), readFileSync(new URL('ios/ValueAIMobile/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png', root)));
});

test('adaptive and themed Android icons contain transparent safe-zone foregrounds', () => {
  assert.equal(config.android.adaptiveIcon.backgroundColor, '#4a161b');
  for (const file of [config.android.adaptiveIcon.foregroundImage, config.android.adaptiveIcon.monochromeImage]) {
    const png = read(file);
    assert.equal(png.width, 1024);
    assert.equal(png.height, 1024);
    assert.equal(png.data[3], 0);
    let visible = 0;
    for (let y = 0; y < 1024; y++) for (let x = 0; x < 1024; x++) {
      if (png.data[(y * 1024 + x) * 4 + 3]) {
        visible++;
        assert.ok(Math.hypot(x - 512, y - 512) < 312, 'J must fit the adaptive safe zone');
      }
    }
    assert.ok(visible > 10000);
  }
});
