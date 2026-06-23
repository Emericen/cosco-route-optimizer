import { chromium } from '/Users/eddyliang/.pixi/envs/playwright/lib/node_modules/playwright/index.mjs';
import { readFileSync, writeFileSync, existsSync } from 'fs';
const DIR='/Users/eddyliang/Desktop/COSCO_航线数据_2026-06-23';
const OUT=DIR+'/cosco_transit_raw.json';
const routes=JSON.parse(readFileSync(DIR+'/cosco_routes_raw.json')).routes;
const codes=routes.map(r=>r.serLpCode);
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const log=(...a)=>console.log(new Date().toISOString().slice(11,19),...a);

// resume: load any prior partial results
let result = existsSync(OUT) ? JSON.parse(readFileSync(OUT)) : {};
const todo = codes.filter(c => !(result[c] && result[c].loopExport!==null));
log(`${codes.length} routes total, ${codes.length-todo.length} already done, ${todo.length} to fetch`);

async function freshBrowser(){
  const browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-blink-features=AutomationControlled']});
  const ctx=await browser.newContext();
  const page=await ctx.newPage();
  await page.goto('https://world.lines.coscoshipping.com/home/Services/route/11',{waitUntil:'domcontentloaded',timeout:40000});
  await sleep(2500);
  return {browser,page};
}
let {browser,page}=await freshBrowser();
if((await page.evaluate(()=>document.body.innerText)).includes('abnormal')){log('BLOCKED at start');await browser.close();process.exit(1);}
log('unblocked, crawling transit matrix');

async function g(code,kind){
  return page.evaluate(async([c,k])=>{
    try{const r=await fetch('https://world.lines.coscoshipping.com/homeapiak/routeService/'+k+'/'+encodeURIComponent(c),{headers:{Accept:'application/json'}});
      if(r.status!==200)return null;const j=await r.json();return j?.data?.content??null;}catch(e){return null;}
  },[code,kind]);
}
let done=codes.length-todo.length;
for(const code of todo){
  let exp=null,imp=null;
  for(let t=0;t<4 && exp===null;t++){
    try{ exp=await g(code,'loopExport'); }
    catch(e){ log('  browser died, relaunching'); try{await browser.close();}catch(_){}; ({browser,page}=await freshBrowser()); }
    if(exp===null)await sleep(1500);
  }
  await sleep(350);
  for(let t=0;t<4 && imp===null;t++){
    try{ imp=await g(code,'loopImport'); }
    catch(e){ log('  browser died, relaunching'); try{await browser.close();}catch(_){}; ({browser,page}=await freshBrowser()); }
    if(imp===null)await sleep(1500);
  }
  result[code]={loopExport:exp,loopImport:imp};
  done++;
  if(done%15===0){ writeFileSync(OUT,JSON.stringify(result,null,1)); log(`progress ${done}/${codes.length} (saved)`); }
  await sleep(800);
}
writeFileSync(OUT,JSON.stringify(result,null,1));
const withExp=Object.values(result).filter(v=>v.loopExport&&v.loopExport.length).length;
log(`DONE. export-matrix for ${withExp}/${codes.length} -> cosco_transit_raw.json`);
await browser.close();
