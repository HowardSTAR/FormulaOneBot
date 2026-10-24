import test from 'node:test';
import assert from 'node:assert/strict';
import { spotlightTeamMedia } from '../src/pages/index/spotlight-team-media.ts';

test('team aliases resolve to the correct current-season logo and car', () => {
  for (const [id, name, slug] of [['mclaren', 'McLaren', 'mclaren'], ['red_bull', 'Red Bull Racing', 'redbullracing'], ['haas', 'Haas F1 Team', 'haasf1team'], ['', 'Mercedes', 'mercedes'], ['rb', 'Racing Bulls', 'racingbulls']]) {
    const media = spotlightTeamMedia(id, name, 2026);
    assert.match(media.logo[0], new RegExp(`/2026/${slug}/2026${slug}logowhite.webp$`));
    assert.match(media.car[0], new RegExp(`/2026/${slug}/2026${slug}carright.webp$`));
  }
});
test('other seasons and unknown teams do not acquire current-year or unrelated imagery', () => {
  assert.deepEqual(spotlightTeamMedia('mclaren', 'McLaren', 2025), { logo: [], car: [] });
  assert.deepEqual(spotlightTeamMedia('unknown', 'New Team', 2026), { logo: [], car: [] });
});
