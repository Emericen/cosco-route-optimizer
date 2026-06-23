# COSCO 全航线数据与路线查询

本仓库包含从中远海运（COSCO）官网航线查询工具抓取的**全部 193 条航线**数据（抓取于 2026-06-23），覆盖 8 大航线类别、35 个航线组。每条航线含三类信息：**航线路线表**（经停港口、码头、ETA/ETD、累计天数）、**运输时间表**（起运港→目的港的运输天数）、**航线优势**。数据以 Excel（`COSCO_全航线汇总_2026-06-23.xlsx`，4 个工作表）和原始 JSON 两种形式提供，并附带一个可直接运行的 **A→B 最优路线查询工具** `route_finder.py`。

## 数据规模

| 项目 | 数量 |
|---|---|
| 航线大类 / 航线组 / 唯一航线 | 8 / 35 / 193 |
| 港口挂靠记录（航线路线表） | 1,865 |
| 港口对运输时间（POL→POD） | 4,984 |
| 港口节点（归一化后） | 301 |

> 注：官网首页“419 航线”是公司全球覆盖的宣传统计数字，并非航线查询工具暴露的可浏览航线数。查询工具实际只暴露 193 条唯一航线（每条含进/出口两个方向，合计 385 条方向序列）。本仓库已覆盖查询工具暴露的全部航线。

## 文件结构

```
COSCO_全航线汇总_2026-06-23.xlsx   主交付文件（4 个工作表，见下）
航线清单_routes_list.txt           193 条航线可视化清单（按大类/组分组，便于人工核对）
route_finder.py                    ★ A→B 最优路线查询 CLI
cosco_routes_raw.json              航线路线表 + 航线优势 原始数据
cosco_transit_raw.json             运输时间表（POL→POD）原始数据
crawl.mjs                          抓取航线/路线表脚本（Node + Playwright）
crawl_transit.mjs                  抓取运输时间表脚本（支持断点续抓）
build_xlsx.py                      由 JSON 生成 Excel 的脚本（Python + openpyxl）
CRAWLING_NOTES.md                  抓取过程、依赖版本、踩坑与经验（详见此文件）
```

Excel 的 4 个工作表：
- **港口挂靠明细 Port Calls** —【航线路线表】每行 = 一个挂靠港口
- **运输时间表 Transit Times** —【运输时间表】每行 = 起运港→目的港 + 运输天数
- **航线索引 Route Index** — 每行 = 一条航线（起止港、全程天数、航线优势）
- **说明 README** — 总览与字段说明

## 使用方法

### 查询 A→B 最优路线（无需任何依赖，纯 Python 标准库）

```bash
# 直达 + 中转，按运输天数排序
python3 route_finder.py --from Shanghai --to "Long Beach"

# 允许最多 2 次中转，返回前 5 条
python3 route_finder.py --from Ningbo --to Rotterdam --max-transship 2 -k 5

# 查港口名（名称会自动归一，去除“(码头)”后缀、统一大小写）
python3 route_finder.py --list-ports rotter
```

示例输出（`Ningbo → Rotterdam`）：

```
1. 总运输 ~31 天  (1 次中转)
     AEU3   AEU3   Ningbo → Singapore    (5天, 方向W)
     AEU5   AEU5   Singapore → Rotterdam (26天, 方向W)
2. 总运输 ~34 天  (直达)
     AEU5   AEU5   Ningbo → Rotterdam    (34天, 方向W)
```

工作原理：以港口为节点、同一航线的“港→港”为带权边（权重 = 运输天数）构建图，用最短路径搜索返回最快的直达/中转路线。`--penalty` 设每次中转的等待惩罚天数（默认 2，仅影响排序）。

> **“最优”的范围**：本站只提供运输时间与经停信息，因此可按**最快 / 最少中转**优化，**无法按运价或船期优化**（官网航线页不含运价、船期、舱位数据）。

### 重新生成数据 / Excel

```bash
node crawl.mjs           # → cosco_routes_raw.json（航线 + 路线表 + 优势）
node crawl_transit.mjs   # → cosco_transit_raw.json（运输时间表）
python3 build_xlsx.py    # → COSCO_全航线汇总_*.xlsx
```

## 抓取说明

数据如何抓取、用了哪些库与版本、过程中踩了哪些坑、有哪些经验——详见 **[CRAWLING_NOTES.md](CRAWLING_NOTES.md)**。
