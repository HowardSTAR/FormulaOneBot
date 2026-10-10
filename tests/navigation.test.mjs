import test from 'node:test';
import assert from 'node:assert/strict';
import {navigationFor, navigationActive, isSectionRoot} from '../front/src/helpers/navigation.ts';

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
  assert.equal(navigationActive(values.find(link => link.to === '/season'), '/next-race'), false);
  assert.equal(navigationActive(values.find(link => link.to === '/next-race'), '/next-race'), true);
  assert.equal(navigationActive(values.find(link => link.to === '/season'), '/race-details'), true);
  for (const path of ['/settings','/favorites','/account','/profile/123']) assert.equal(navigationActive(values.find(link => link.to === '/profile'), path), true);
});

const desktopLinks = nav => [...nav.sections.flatMap(section => section.items.flatMap(entry => 'to' in entry ? [entry] : entry.items)), ...(nav.management?.items ?? [])];

test('Desktop groups season history with comparison and keeps help actions together', () => {
  const nav = navigationFor({signedIn:true, personalized:true, role:'user'});
  assert.deepEqual(nav.sections.map(section => section.label), ['Гонки', 'Прогнозы и статистика', 'Сообщество', 'Личное и справка']);
  const groups = nav.sections.flatMap(section => section.items).filter(entry => 'items' in entry);
  assert.deepEqual(groups.find(group => group.id === 'comparison').items.map(link => link.to), ['/compare', '/history']);
  assert.ok(!groups.find(group => group.id === 'peloton').items.some(link => link.to === '/history'));
  assert.ok(groups.find(group => group.id === 'social').items.some(link => link.to === '/voting'));
  const help = groups.find(group => group.id === 'help');
  assert.deepEqual(help.actions.map(action => action.id), ['onboarding']);
  assert.deepEqual(help.items.map(link => link.to), ['/contact-admin']);
  assert.equal(groups.reduce((count, group) => count + (group.actions?.length ?? 0), 0), 1);
});

for (const auth of [
  {signedIn:false, personalized:false, role:null},
  {signedIn:true, personalized:false, role:'user'},
  {signedIn:true, personalized:true, role:'user'},
  {signedIn:true, personalized:true, role:'admin'},
  {signedIn:true, personalized:true, role:'superadmin'},
]) test(`Desktop permissions and unique destinations: ${JSON.stringify(auth)}`, () => {
  const nav = navigationFor(auth);
  const values = desktopLinks(nav).map(link => link.to);
  assert.equal(new Set(values).size, values.length);
  for (const path of ['/','/next-race','/season','/predictions','/compare','/history','/community','/wiki','/contact-admin','/account']) assert.ok(values.includes(path), path);
  for (const path of ['/settings','/profile']) assert.equal(values.includes(path), auth.signedIn, path);
  for (const path of ['/notifications','/favorites','/voting']) assert.equal(values.includes(path), auth.personalized, path);
  const isAdmin = ['admin','superadmin'].includes(auth.role);
  assert.equal(Boolean(nav.management), isAdmin);
  for (const path of ['/admin','/prediction-analytics']) assert.equal(values.includes(path), isAdmin, path);
});

test('Desktop selects exactly one destination on profile, weekend and detail pages', () => {
  const nav = navigationFor({signedIn:true, personalized:true, role:'admin'});
  for (const [route, expected] of [['/account','/account'], ['/settings','/settings'], ['/favorites','/favorites'], ['/notifications','/notifications'], ['/next-race','/next-race'], ['/driver-details','/drivers'], ['/constructor-details','/constructors'], ['/profile/123','/profile']]) {
    assert.deepEqual(desktopLinks(nav).filter(link => navigationActive(link,route)).map(link => link.to), [expected], route);
  }
});

test('Every bottom tab and menu section is a root, including protected sections', () => {
  const sections = paths({signedIn:true, personalized:true, role:'superadmin'});
  for (const path of [...sections, '/next-race', '/account', '/settings', '/favorites']) {
    assert.equal(isSectionRoot(path), true, path);
    assert.equal(isSectionRoot(`${path}/`), true, `${path}/`);
  }
  for (const path of ['/driver-details', '/constructor-details', '/team-principal', '/profile/123', '/share/token', '/reset-password', '/account/delete']) {
    assert.equal(isSectionRoot(path), false, path);
  }
});
