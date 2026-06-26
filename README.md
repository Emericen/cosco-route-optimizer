# COSCO 航线 + 订舱运价 优化器

本仓库做两件事:

1. **完整抓取中远海运(COSCO)的全部航线数据** —— 193 条航线、经停港口/码头、ETA/ETD、运输天数、航线优势(全部为官网真实数据)。
2. **一个 A→B 路线优化器** —— 输入客户的起运港 + 目的港,按 **价格 / 天数** 排序输出可选方案(支持中转、箱型、门到门),把"航线效率(天数)"和"订舱成本(运价)"结合起来给出最优。

> ⚠️ **运价目前为模拟数据(MOCK)**。COSCO 的真实运价被账号权限锁住(需企业认证账号),无法自动抓取。运价层已按"可随时替换"的方式搭好:拿到真实运价后,替换两个 CSV 的数值即可,**结构与逻辑完全不用动**。详见下方[运价说明](#运价为什么是模拟的)。

---

## 📊 数据规模

| 项目 | 数量 |
|---|---|
| 航线大类 / 航线组 / 唯一航线 | 8 / 35 / **193** |
| 港口挂靠记录(航线路线表) | 1,865 |
| 港口对运输时间(POL→POD) | 4,984 |
| 港口节点 | 302 |
| 可售直达 O-D 边(优化器图的边) | 2,734 |

> 关于官网首页"419 航线":那是**公司全球覆盖的宣传数字**,不是航线查询工具里的可浏览航线数。查询工具实际只有 **193 条唯一航线**(每条含进/出口两个方向 = 385 条方向序列)。本仓库已覆盖查询工具暴露的全部航线。

---

## 📗 主交付:单一工作簿

**`COSCO_航线与运价_汇总_2026-06-23.xlsx`** —— 5 个工作表:

| 工作表 | 内容 | 真实/模拟 |
|---|---|---|
| 说明 README | 总览 + 替换运价的方法 | — |
| ① 港口挂靠明细 Port Calls | 航线路线表(港口/码头/ETA/ETD/累计天数) 1,865 行 | **真实** |
| ② 运输时间表 Transit Times | 起运港→目的港 运输天数 4,984 行 | **真实** |
| ③ 航线索引 Route Index | 193 条航线 + 起止港 + 航线优势 | **真实** |
| ④ 运价表 Rates | 箱型 × O-D,含**四种服务类型总价**(港到港PP/门到港DP/港到门PD/门到门DD)+ 海运费/附加费/拖车费 16,404 行 | **模拟 MOCK** |

---

## 🚀 怎么用 / How to use

### 1. 查询客户 A→B 最优方案(核心功能)

纯 Python 标准库,无需安装任何包:

```bash
# 价格优先,40GP,门到门
python3 quote_optimizer.py --from Ningbo --to Rotterdam --box 40GP --service DD --priority price

# 天数优先(注意排序会变 —— 直达更快但更贵)
python3 quote_optimizer.py --from Ningbo --to Rotterdam --box 40GP --service DD --priority days

# 港到港,价格优先,返回前 5 条
python3 quote_optimizer.py --from Nansha --to Hochiminh --box 20GP --service PP --priority price -k 5
```

参数:
- `--box` 箱型:`20GP` `40GP` `40HQ`(干货箱)· `40RF`(冷藏)· `40OT`(开顶)· `40FR`(框架)
- `--service` 服务类型:`PP` 港到港 · `DD` 门到门 · `DP` 门到港 · `PD` 港到门
- `--priority` 排序:`price` 价格优先 · `days` 天数优先 · `balanced` 综合
- `--max-transship` 最大中转次数(默认 1)· `-k` 返回方案数(默认 5)

示例输出(Ningbo→Rotterdam,价格优先):
```
1. 总价 ~USD 7,270  |  ~38天  (1次中转)
     AEU1   Ningbo→Singapore   $1,100 / 8天
     AEU5   Singapore→Rotterdam $5,090 / 26天
     + 拖车(门点) $880
2. 总价 ~USD 7,490  |  ~34天  (直达)   ← 天数优先时此条会排第一
     AEU5   Ningbo→Rotterdam   $6,610 / 34天
```

> **工作原理**:港口=图的节点,航段=带权边。**天数权重是真实数据**;**运价权重是模拟数据**。优化器枚举 A→B 的所有可选路径(直达 + 中转),每条算出(总价, 天数),按你选的目标排序。同一 A→B 通常有多条路径、不同的价格/天数取舍 —— 这正是优化的意义。

### 2. 替换为真实运价(拿到认证账号/货代报价后)

只改数字,不动逻辑:

1. 把真实运价填进 **`ocean_edges_MOCK.csv`**(海运费/附加费)和 **`door_charges_MOCK.csv`**(拖车费)。
2. 重新生成工作簿:
   ```bash
   python3 build_master.py
   ```
3. `quote_optimizer.py` 会自动读到新运价 —— 完成。

### 3. 从头刷新航线数据(航线有增减时)

```bash
node crawl.mjs           # 航线 + 路线表 + 优势  → cosco_routes_raw.json
node crawl_transit.mjs   # 运输时间表           → cosco_transit_raw.json
python3 gen_mock_rates.py # 重新生成模拟运价骨架
python3 build_master.py  # 重新生成工作簿
```
> 反爬提示:站点有 WAF。脚本使用**系统真实 Chrome**(`channel:'chrome'` + `--disable-blink-features=AutomationControlled`)绕过;`crawl_transit.mjs` 每 15 条存盘、可断点续抓。详见 [CRAWLING_NOTES.md](CRAWLING_NOTES.md)。

---

## 📁 文件结构

```
COSCO_航线与运价_汇总_2026-06-23.xlsx   ★ 主交付(5 工作表)
quote_optimizer.py                     ★ A→B 优化器(核心逻辑)
ocean_edges_MOCK.csv                   运价层-海运(替换为真实即可)
door_charges_MOCK.csv                  运价层-拖车(替换为真实即可)
gen_mock_rates.py                      生成模拟运价(锚定 上海→Chicago $175/运输天)
build_master.py                        由 JSON+CSV 生成工作簿
crawl.mjs / crawl_transit.mjs          抓取脚本(Node + Playwright + 真实Chrome)
cosco_routes_raw.json                  航线路线表 + 优势 原始数据
cosco_transit_raw.json                 运输时间表 原始数据
航线清单_routes_list.txt               193 条航线可视化清单(便于人工核对)
port_reference.csv                     港口名 → UN/LOCODE 参照(96% 已校验)
CRAWLING_NOTES.md                      抓取过程、依赖版本、踩坑与经验
```

> 本地另有 `how-tos/`(COSCO 官方操作 PDF,共 17 份)与 `unlocode_reference.csv`(UN/LOCODE 公共数据集),因版权/体积**未纳入公开仓库**。UN/LOCODE 数据集可自行下载:
> ```bash
> curl -L -o unlocode_reference.csv https://raw.githubusercontent.com/datasets/un-locode/main/data/code-list.csv
> ```

---

## 运价为什么是模拟的

我们彻底验证过:COSCO 的真实运价**无法自动抓取**。

- 即期运价(SPOT)对**未认证账号**返回 0 条产品(测过 上海→洛杉矶 等多条主干线,均为空)—— 是**账号级**封锁,不是某条线没有。
- 看/买运价需要 **企业认证账号**(需上传**营业执照 + 统一社会信用代码**、企业银行账号,且人工审批),或 **7 天试用**,或**关联一个已认证企业**。
- 公开可得的只有:① RFQ 询价表单(人工回复,无即时数据)② 已公布的 Tariff 备案运价(非实际成交价)。

所以真实运价的现实来源是:**货代报价**(货代本身已认证、可自由报价)、**COSCO 销售/中小客户专线**、或将来拿到认证账号后用 `My Orders → 导出Excel`。

模拟运价的标定:真实产品 **上海→Chicago,25 天,20GP = USD 4,375** ⇒ **USD 175 / 运输天**;40GP/40HQ 倍率取自同一产品(4750/4375≈1.086)。它是一个**可信的形状,不是预测** —— 真实运价并非随天数线性变化。用于把结构和逻辑跑通,真实数据到位后直接替换。

---

## 依赖

- Node v22.15.0 · Playwright 1.61.0 · 系统 Google Chrome(`channel:'chrome'`)—— 抓取用
- Python 3.10+ · openpyxl —— 生成工作簿用
- `quote_optimizer.py` 仅依赖 Python 标准库
