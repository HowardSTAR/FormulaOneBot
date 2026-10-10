import test from 'node:test';
import assert from 'node:assert/strict';
import {navigationFor, navigationActive} from '../front/src/helpers/navigation.ts';

const links = auth => { const nav = navigationFor(auth); return [...nav.primary, ...nav.general, ...nav.personal, ...nav.groups.flatMap(group => group.items)]; };
const paths = auth => links(auth).map(link => link.to);
test('Guest has all public sections but no protected links', () => {
  const values = paths({signedIn:false, personalized:false, role:null});
  for (const path of ['/history','/drivers','/constructors','/practice-results','/compare','/predictions','/wiki','/reaction-game','/reflex-grid-game','/race-game','/contact-admin']) assert.ok(values.includes(path), path);
  for (const path of ['/notifications','/favorites','/voting','/settings','/admin','/prediction-analytics']) assert.ok(!values.includes(path), path);
});
test('Email account opens personal features through My profile', () => {
  const values = paths({signedIn:true, personalized:false, role:'user'});
  assert.ok(values.includes('/profile'));
  assert.ok(!values.includes('/settings'));
  assert.ok(!values.includes('/notifications'));
  assert.ok(!values.includes('/favorites'));
});
test('Telegram member gets personal sections, not administration', () => {
  const values = paths({signedIn:true, personalized:true, role:'user'});
  for (const path of ['/profile','/notifications','/voting']) assert.ok(values.includes(path));
  for (const path of ['/settings','/favorites']) assert.ok(!values.includes(path));
  assert.ok(!values.includes('/admin'));
  assert.ok(!values.includes('/prediction-analytics'));
});
for (const role of ['admin','superadmin']) test(`${role} sees administrative links`, () => {
  const values = paths({signedIn:true, personalized:true, role});
  assert.ok(values.includes('/admin'));
  assert.ok(values.includes('/prediction-analytics'));
  assert.equal(new Set(values).size, values.length);
});
test('Nested detail pages select the matching section, not Home', () => {
  const values = links({signedIn:false, personalized:false, role:null});
  assert.equal(navigationActive(values.find(link => link.to === '/drivers'), '/driver-details'), true);
  assert.equal(navigationActive(values.find(link => link.to === '/'), '/driver-details'), false);
  assert.equal(navigationActive(values.find(link => link.to === '/season'), '/next-race'), true);
  for (const path of ['/settings','/favorites','/account','/profile/123']) assert.equal(navigationActive(values.find(link => link.to === '/profile'), path), true);
});
