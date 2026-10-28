// Requires the frontend Vite server. Reuses the real game's renderer, not a mock.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const tracks=require('../app/race_tracks.json');
(async()=>{
  const browser=await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL||'chrome',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1536,height:1024}});
    page.on('pageerror',error=>console.error(error.message));
    const out=path.join(__dirname,'../front/src/assets/community');await fs.mkdir(out,{recursive:true});
    for(const track of tracks){
      await page.goto(`${process.env.COMMUNITY_UI_URL||'http://127.0.0.1:5177'}/tests/community-track-render.html?track=${track.id}`);
      await page.waitForSelector('html[data-ready="true"]');
      const data=await page.locator('canvas').evaluate(canvas=>{
        const thumbnail=document.createElement('canvas');thumbnail.width=1152;thumbnail.height=768;
        thumbnail.getContext('2d').drawImage(canvas,0,0,1152,768);
        return thumbnail.toDataURL('image/webp',.86).split(',')[1];
      });
      await fs.writeFile(path.join(out,`${track.id}.webp`),Buffer.from(data,'base64'));
      console.log(`Rendered ${track.id}`);
    }
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
