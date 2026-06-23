import { chromium } from '/Users/eddyliang/.pixi/envs/playwright/lib/node_modules/playwright/index.mjs';
import { writeFileSync } from 'fs';
const EXEC = '/Users/eddyliang/Library/Caches/ms-playwright/chromium-1217/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const browser = await chromium.launch({ headless: true, executablePath: EXEC });
const page = await browser.newPage();
await page.goto('https://world.lines.coscoshipping.com/home/Services/route/16', { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(1500);

// grab the 8 tab names + their route ids from the DOM
const tabs = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll('a[href*="/Services/route/"]').forEach(a => {
    const m = a.getAttribute('href').match(/route\/(\d+)/);
    const t = a.textContent.trim();
    if (m && t) out.push({ id: m[1], name: t });
  });
  return out;
});
console.error('tabs found:', JSON.stringify(tabs));

// everything else runs as in-page fetch (carries WAF cookies) with throttle
const result = await page.evaluate(async () => {
  const B = 'https://world.lines.coscoshipping.com/homeapiak';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function get(p, tries=5) {
    for (let i=0;i<tries;i++){
      try {
        const r = await fetch(B+p, {headers:{'Accept':'application/json'}});
        if (r.status===200) return await r.json();
        await sleep(400*(i+1));
      } catch(e){ await sleep(500*(i+1)); }
    }
    return null;
  }
  const trades = [11,12,13,14,15,16,17,18];
  const data = [];
  for (const t of trades) {
    const g = await get(`/routeService/ServiceLoopGroup/${t}`);
    const groups = g?.data?.content || [];
    for (const grp of groups) {
      const lr = await get(`/routeService/routeService/${grp.serLpGroupUuid}`);
      const loops = lr?.data?.content || [];
      for (const lp of loops) {
        const code = lp.serLpCode;
        const [cp, adv] = await Promise.all([
          get(`/routeService/callPort/${code}`),
          get(`/routeService/advantage/${code}`),
        ]);
        data.push({
          tradeUuid: t,
          groupUuid: grp.serLpGroupUuid,
          groupCn: grp.serLpGroupNameCn,
          groupEn: grp.serLpGroupNameEn,
          serLpUuid: lp.serLpUuid,
          serLpCode: code,
          nameCn: lp.serLpNameCn,
          nameEn: lp.serLpNameEn,
          callPort: cp?.data || null,
          advantage: adv?.data?.content || null,
        });
        await sleep(120);
      }
    }
  }
  return data;
});
console.error('total routes collected:', result.length);
writeFileSync('cosco_routes.json', JSON.stringify({tabs, routes: result}, null, 1));
await browser.close();
