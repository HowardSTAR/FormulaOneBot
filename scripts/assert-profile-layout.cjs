const assert = require('node:assert/strict');

// Measure rendered geometry: API content, loaded fonts and responsive rules all apply.
module.exports = async function assertProfileLayout(page) {
  await page.evaluate(() => document.fonts.ready);
  const layout = await page.locator('.profile-content').evaluate(content => {
    const rect = el => {
      const r = el.getBoundingClientRect();
      return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};
    };
    const blocks = [...content.children].map(el=>({name:el.className,...rect(el)}));
    const columns = [...content.querySelector('.profile-columns').children].map(rect);
    const surfaces = [...content.querySelectorAll('.profile-hero,.profile-panel')].map(el=>({name:el.className,padding:parseFloat(getComputedStyle(el).paddingLeft)}));
    const controls = [...document.querySelectorAll('.profile-sharing button,.profile-avatar-edit,.profile-season select,.profile-panel-action,.profile-favorites-heading a,.supporter-league>.profile-primary')].map(el=>({label:el.textContent,...rect(el)}));
    const statsFit = [...content.querySelectorAll('.profile-stats>div')].every(el=>el.scrollWidth<=el.clientWidth);
    return {blocks,columns,surfaces,controls,statsFit,overflow:document.documentElement.scrollWidth>innerWidth};
  });
  const gaps=layout.blocks.slice(1).map((block,i)=>block.top-layout.blocks[i].bottom);
  assert(gaps.every(gap=>gap>=16 && gap<=32),`Cards need breathing room: ${JSON.stringify(gaps)}`);
  assert(Math.max(...gaps)-Math.min(...gaps)<1,'All main sections use the same spacing');
  assert(layout.blocks.every(block=>Math.abs(block.left-layout.blocks[0].left)<1&&Math.abs(block.right-layout.blocks[0].right)<1),'Section edges align');
  assert(layout.blocks[1].name==='profile-season-block','Season results precede the large trophy collection');
  const padding=layout.surfaces.map(surface=>surface.padding);
  assert(Math.min(...padding)>=16&&Math.max(...padding)-Math.min(...padding)<1,'Card contents use consistent, readable insets');
  const [predictions,records]=layout.columns;
  const columnGap=Math.abs(predictions.top-records.top)<1?records.left-predictions.right:records.top-predictions.bottom;
  assert(columnGap>=12&&columnGap<=24,'Prediction and record cards have a clear gap in both layouts');
  assert(layout.controls.every(control=>control.height>=44),`Comfortable actions: ${JSON.stringify(layout.controls.filter(control=>control.height<44))}`);
  assert(layout.statsFit,'Metric labels stay inside their cards');
  assert(!layout.overflow,'Profile stays within the viewport');
  return {gaps: gaps.map(gap=>Math.round(gap)),padding:padding[0]};
};
