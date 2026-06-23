# 抓取过程、依赖、踩坑与经验

记录本仓库数据是如何从中远海运官网抓取的，方便日后维护与复现。

## 目标

把 COSCO 航线查询工具（`https://world.lines.coscoshipping.com/home/Services/route/16`）里
所有航线的明细抓成结构化文件。该工具是三级级联下拉：**大类标签 → 航线组 → 具体航线**，
人工需要逐个点开每个下拉的每个选项才能看到一条航线，无法手工完成全部 193 条。

## 依赖与版本

| 工具 / 库 | 版本 | 用途 |
|---|---|---|
| Node.js | v22.15.0 | 运行抓取脚本 |
| Playwright | 1.61.0 | 驱动浏览器、在页面内发起请求 |
| Google Chrome（系统安装，`channel:'chrome'`） | 149.0.7827.115 | 绕过反爬的关键（见下） |
| Python | 3.10.12 | 生成 Excel、运行路线查询 |
| openpyxl | 3.1.5 | 写 .xlsx |

> `route_finder.py` 仅依赖 Python 标准库，无需安装任何包。

## 抓取过程

1. **找接口，而不是点下拉。** 用 Playwright 监听页面网络请求，发现下拉背后是一套
   JSON 接口（`/homeapiak/routeService/...`）。于是整个抓取改为直接调用接口，跳过所有点击。

2. **接口调用链：**

   ```
   ServiceLoopGroup/{tradeUuid}   → 航线组列表（下拉1）         8 个大类 = tradeUuid 11–18
   routeService/{groupUuid}       → 航线列表（下拉2），含 serLpCode
   callPort/{serLpCode}           → 航线路线表（港口/码头/ETA/ETD/累计天数）
   advantage/{serLpCode}          → 航线优势
   loopExport/ loopImport/{code}  → 运输时间表（POL→POD 运输天数矩阵）
   ```

3. **两轮抓取：**第一轮抓 `callPort` + `advantage`（→ `cosco_routes_raw.json`）；
   后来补抓 `loopExport`/`loopImport`（→ `cosco_transit_raw.json`）。

4. **生成交付物：**`build_xlsx.py` 把两个 JSON 合成 4 表 Excel；
   `route_finder.py` 把 `cosco_routes_raw.json` 构建成港口图做最短路径查询。

## 踩坑与经验

1. **裸 HTTP 请求会被 403。** 直接用 `curl` / Python `urllib` 调接口被 WAF 拦截（403 Forbidden）。
   **解法：**把 `fetch` 放到 Playwright 的浏览器页面上下文里执行（`page.evaluate`），
   携带正确的 Cookie / 头部，即可拿到 200。

2. **无头 Chromium 会被反爬封禁，真实 Chrome 不会。** 抓得多了之后，无头的
   “Chrome for Testing” 开始整页返回 *“Your current behavior is detected as abnormal”*。
   实测发现封禁是**基于浏览器指纹，而非 IP**——同一个 IP 下：
   - 无头 Chrome for Testing → 被封；
   - 系统安装的真实 Chrome（`channel:'chrome'`）+ `--disable-blink-features=AutomationControlled`
     → **直接通过**（`navigator.webdriver=false`），无头/有头均可。

   **经验：**一开始就该用真实 Chrome，根本不会触发 WAF。`gh`/`curl` 等工具换 CLI 没用，
   关键是浏览器与指纹，不是工具本身。

3. **“419”不是航线数。** 官网首页统计卡片显示“146 国家 / 663 港口 / 419 航线 / 596 船舶”，
   其中 419 是公司**全球覆盖的宣传数字**（由 CMS 维护、带数字滚动动画，未硬编码在 JS 里），
   与查询工具暴露的可浏览航线数无关。查询工具实际只有 **193 条唯一航线**（每条含进/出口两个方向 = 385 条方向序列）。
   核对方法：每个下拉的选项数都列在了 `航线清单_routes_list.txt`，可逐项与网站对照。

4. **`schedule/findServiceCode` 是死胡同。** 起初以为“运输时间表”来自这个接口，
   但它只返回 `{trade: "..."}`（大类名），没有时间数据。真正的运输时间表是
   `loopExport` / `loopImport`，返回 **起运港(POL)→目的港(POD) 的运输天数矩阵**。

5. **港口名碎片化，必须归一。** 港口字段里同一个港口存在多种写法：
   `ROTTERDAM` / `Rotterdam` / `Rotterdam (RWG)` / `Rotterdam (DDE)` …
   不归一会把同一港口拆成多个图节点，**直接破坏连通性**。
   `route_finder.py` 里做了归一（去掉 `(码头)` 括号后缀 + 统一大小写 + 别名表），
   节点数从 400 降到 301，路线搜索才正常。

6. **抓取要稳：限速 + 增量存盘 + 断点续抓 + 浏览器重启。**
   - 请求间隔 ~0.8–1.5s，礼貌限速；
   - `crawl_transit.mjs` 每 15 条写盘一次，崩溃不丢进度，重跑自动跳过已抓的；
   - 有头窗口曾中途被关闭导致丢了 50 条（且旧脚本只在结尾写盘 → 全丢），
     因此改为**无头真实 Chrome** + 捕获“浏览器已关闭”异常自动重启。

7. **小代码坑：`heapq` 比较报错。** 优先队列元组在代价相等时会继续比较后面的
   `dict`/`list` 元素而报 `TypeError`。加一个自增计数器作为 tie-breaker 即可。

## 复现步骤

```bash
node crawl.mjs           # 航线 + 路线表 + 优势 → cosco_routes_raw.json
node crawl_transit.mjs   # 运输时间表          → cosco_transit_raw.json
python3 build_xlsx.py    # 合成 Excel
```

> 反爬随时间变化；若 `crawl*.mjs` 失效，先确认仍在用系统真实 Chrome（`channel:'chrome'`）
> 且带 `--disable-blink-features=AutomationControlled`。
