import test from 'node:test';
import assert from 'node:assert/strict';
import {readProfileGuide,saveProfileGuide,profileGuideSteps} from '../src/helpers/profileGuide.ts';

test('profile introduction remembers each account even when browser storage is unavailable',()=>{
  assert.equal(readProfileGuide(91001),null);
  saveProfileGuide(91001,'completed');
  assert.equal(readProfileGuide(91001),'completed');
  assert.equal(readProfileGuide(91002),null);
  saveProfileGuide(91002,'skipped');
  assert.equal(readProfileGuide(91002),'skipped');
  assert.equal(readProfileGuide(91001),'completed');
});

test('profile tour covers all personal functions including trophies and sharing',()=>{
  assert.equal(profileGuideSteps.length,9);
  assert(profileGuideSteps.some(step=>step.target==='#profile-trophies'));
  assert(profileGuideSteps.some(step=>step.target==='.profile-sharing'));
  assert(profileGuideSteps.some(step=>step.target==='.profile-favorites'));
  assert(profileGuideSteps.every(step=>step.text.length>40));
});
