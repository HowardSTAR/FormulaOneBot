import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeTrophyQueue, trophyImage, type TrophyAward } from '../src/helpers/trophies.ts';

test('confirmed receipts are deduplicated and acknowledged trophies never re-enter the queue', () => {
  const bronze: TrophyAward={id:'oracle:0:0',family:'oracle',season:0,level:0,name:'Оракул',tier:'Бронза',earned_at:'2026-10-11'};
  const silver={...bronze,id:'oracle:0:1',level:1,tier:'Серебро'};
  assert.deepEqual(mergeTrophyQueue([bronze,bronze,silver],new Set([bronze.id])),[silver]);
  assert.equal(trophyImage('rhythm',2),'/images/trophies/rhythm-gold.webp');
});
