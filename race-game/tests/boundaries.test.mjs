import assert from 'node:assert/strict';
import test from 'node:test';
import {loadTs} from './support/modules.mjs';
const {simulationSteps} = await loadTs(new URL('../src/raceClock.ts',import.meta.url));
const {finishCrossing} = await loadTs(new URL('../src/finishLine.ts',import.meta.url));

for (const [name,frame,total] of [
  ['negative',-1,0],['zero',0,0],['nan',NaN,0],['infinity',Infinity,0],
  ['tiny-frame',0.001,0.001],['one-step',1000/120,1000/120],['above-one-step',1000/120+0.001,1000/120+0.001],
  ['before-catchup-cap',249.999,249.999],['at-catchup-cap',250,250],
  ['above-catchup-cap',250.001,250],['suspended',10000,250],
]) test(`physics elapsed boundary: ${name}`,()=>{
  const steps=simulationSteps(frame);
  assert.ok(Math.abs(steps.reduce((sum,value)=>sum+value,0)-total)<1e-8);
  assert.ok(steps.every(value=>value>0 && value<=1000/120));
  if (!total) assert.deepEqual(steps,[]);
});

for (const [name,y,expected] of [
  ['below-road',629.999,null],['lower-edge',630,0.5],['inside',660,0.5],
  ['upper-edge',700,0.5],['above-road',700.001,null],
]) test(`finish gate road boundary: ${name}`,()=>{
  assert.equal(finishCrossing({x:874,y},{x:876,y}),expected);
});

for (const [name,previous,current,expected] of [
  ['no-crossing',874,874.999,null],['reach-line',874,875,1],
  ['forward',874,876,0.5],['backwards',876,874,null],['start-on-line',875,876,null],
]) test(`finish gate direction: ${name}`,()=>{
  assert.equal(finishCrossing({x:previous,y:660},{x:current,y:660}),expected);
});
