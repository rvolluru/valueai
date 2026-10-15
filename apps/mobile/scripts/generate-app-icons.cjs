// Reuse the exact logo crop displayed by LogoJ; do not substitute a font.
const fs = require('node:fs');
const path = require('node:path');
const Jimp = require(require.resolve('jimp-compact', { paths: [path.dirname(require.resolve('@expo/image-utils'))] }));
const root = path.resolve(__dirname, '..');
const size = 1024;
const burgundy = 0x4a161bff;

async function main() {
  const logo = await Jimp.read(path.join(root, 'assets/jouft-logo.png'));
  // Same proportions as App.js: 14.03 x 28 viewport, image 130.11 x 30.66.
  const scale = logo.bitmap.width / 130.11;
  const j = logo.clone().crop(Math.round(.56 * scale), Math.round(1.79 * scale), Math.round(14.03 * scale), Math.round(28 * scale));
  j.scan(0, 0, j.bitmap.width, j.bitmap.height, function (x, y, idx) {
    this.bitmap.data[idx] = this.bitmap.data[idx + 1] = this.bitmap.data[idx + 2] = 255;
  });
  async function render(height, background, filename) {
    const image = new Jimp(size, size, background);
    const mark = j.clone().resize(Jimp.AUTO, height, Jimp.RESIZE_BICUBIC);
    image.composite(mark, Math.round((size - mark.bitmap.width) / 2), Math.round((size - height) / 2));
    if (background === burgundy) {
      for (let i = 3; i < image.bitmap.data.length; i += 4) image.bitmap.data[i] = 255;
    }
    await image.writeAsync(path.join(root, filename));
  }
  await render(512, burgundy, 'assets/app-icon.png');
  // Adaptive foreground remains within Android's central safe zone.
  await render(460, 0x00000000, 'assets/app-icon-adaptive.png');
  await render(460, 0x00000000, 'assets/app-icon-monochrome.png');
  fs.copyFileSync(path.join(root, 'assets/app-icon.png'), path.join(root, 'ios/ValueAIMobile/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png'));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
