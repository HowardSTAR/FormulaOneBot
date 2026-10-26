import test from 'node:test';
import assert from 'node:assert/strict';
import { chartSeriesColor, DRIVER_COLOR_PALETTE } from '../src/pages/compare/compareModel.ts';

function luminance(hex: string) {
  return hex.slice(1).match(/../g)!.map(channel => parseInt(channel, 16) / 255)
    .map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4)
    .reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0);
}

test('every comparison series stays legible on both chart backgrounds', () => {
  for (const dark of [false, true]) {
    const background = luminance(dark ? '#141518' : '#f5f5f7');
    for (const color of [...DRIVER_COLOR_PALETTE, '#229971', '#3671C6', '#B6BABD', '#C4A97D']) {
      const result = luminance(chartSeriesColor(color, dark));
      const contrast = (Math.max(result, background) + .05) / (Math.min(result, background) + .05);
      assert.ok(contrast >= 3.1, `${color} in ${dark ? 'dark' : 'light'} theme: ${contrast}`);
    }
  }
});
