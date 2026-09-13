import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import assert from 'node:assert/strict';
import test from 'node:test';

const result = await build({
  entryPoints:[fileURLToPath(new URL('../src/components/DetailedTrackMap.tsx',import.meta.url))],
  bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic',external:['react','react-dom'],
  plugins:[{name:'ignore-css',setup(builder){builder.onLoad({filter:/\.css$/},()=>({contents:'',loader:'js'}));}}],
});
const mod={exports:{}};
new Function('require','module','exports',result.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports);
const {DetailedTrackMap}=mod.exports;
const render=(eventName,season,preview=true)=>renderToStaticMarkup(React.createElement(DetailedTrackMap,{
  eventName,season,...(preview?{preview:React.createElement('span',null,'Контур трассы')}:{}),
}));

test('reviewed map launches a closed dialog with controls and source',()=>{
  const html=render('Austrian Grand Prix',2026);
  assert.match(html,/Открыть карту: Austrian Grand Prix/);
  assert.match(html,/<dialog/);
  assert.doesNotMatch(html,/<dialog[^>]*\sopen(?:\s|=|>)/);
  assert.match(html,/circuit-layer-controls/);
  assert.match(html,/50 м до T10/);
  assert.match(html,/circuit-legend/);
});
test('unreviewed season and circuit show an honest contour fallback',()=>{
  for(const [event,season] of [['Austrian Grand Prix',2025],['Spanish Grand Prix',2026]]){
    const html=render(event,season);
    assert.match(html,/<dialog/);
    assert.match(html,/пока не проверена/);
    assert.doesNotMatch(html,/circuit-layer-controls|Детекция Overtake/);
  }
});
test('regular panel remains available for embedding',()=>{
  assert.match(render('Italian Grand Prix',2026,false),/Подробная карта трассы/);
});
test('both routes pass their actual season and a clickable preview',async()=>{
  const next=await readFile(new URL('../src/pages/next-race/NextRacePage.tsx',import.meta.url),'utf8');
  const details=await readFile(new URL('../src/pages/race-details/RaceDetailsPage.tsx',import.meta.url),'utf8');
  assert.equal((next.match(/<DetailedTrackMap /g)||[]).length,2);
  assert.match(next,/setRaceSeason\(raceData\.season/);
  assert.match(details,/season=\{Number\(season\)\} preview=/);
});
