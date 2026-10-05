import {test} from 'node:test';
import assert from 'node:assert/strict';
import {loadTs} from './support/modules.mjs';
const {mobilePlatform,shouldShowInstallHint} = await loadTs(new URL('../src/helpers/installHint.ts',import.meta.url));
for (const [agent,touch,expected,name] of [
  ['iPhone',5,'ios','iPhone'],['iPad',0,'ios','iPad'],['iPod',1,'ios','iPod'],
  ['Macintosh',0,null,'desktop-Mac'],['Macintosh',1,null,'single-pointer-Mac'],
  ['Macintosh',2,'ios','desktop-mode-iPad-boundary'],['Android',5,'android','Android'],
  ['',0,null,'unknown'],['Windows',0,null,'Windows'],
]) test(`mobile platform: ${name}`,()=>assert.equal(mobilePlatform(agent,touch),expected));
const now=100*86400000;
for (const [name,state,expected] of [
  ['first-visit',{},true],['count-two',{count:2},true],['count-three',{count:3},false],
  ['before-cooldown',{lastShown:now-30*86400000+1},false],
  ['exact-cooldown',{lastShown:now-30*86400000},true],
  ['after-cooldown',{lastShown:now-30*86400000-1},true],
  ['clock-moved-backwards',{lastShown:now+1},false],
  ['permanent-dismissal',{dismissed:true,count:0},false],
]) test(`install hint decision: ${name}`,()=>{
  const before=structuredClone(state);
  assert.equal(shouldShowInstallHint(state,now),expected);
  assert.deepEqual(state,before);
});
