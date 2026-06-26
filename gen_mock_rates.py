#!/usr/bin/env python3
"""
gen_mock_rates.py — 生成【模拟运价】primitives，供 quote_optimizer.py 使用。

⚠️ 全部为模拟数据(MOCK),仅用于搭建结构与逻辑。拿到真实运价后,直接替换
   ocean_edges_MOCK.csv 与 door_charges_MOCK.csv 的数值即可,优化器无需改动。

锚点(让数字可信):真实产品 上海→Chicago,25天,20GP = USD 4,375
   => 20GP 海运费 ≈ USD 175 / 运输天  (25 × 175 = 4,375 ✓)
   40GP/40HQ 倍率 = 4750/4375 ≈ 1.086 (同样取自该真实产品)
"""
import json, csv, re, os
HERE=os.path.dirname(os.path.abspath(__file__))

# ---- 模拟定价模型(可调) ----
RATE_PER_DAY_20GP = 175          # 锚定 上海→Chicago 真实产品
BOX_MULT = {'20GP':1.00, '40GP':1.086, '40HQ':1.086,   # 干货箱
            '40RF':2.00,                                # 冷藏箱(溢价~2x)
            '40OT':1.35, '40FR':1.45}                   # 开顶/框架(超规溢价)
SEA_SURCHARGE_USD  = 50   # 海运附加费(AQS/CAS/CBX),按【每个航段】计;中转有2段→各算一遍
BOOKING_ORIGIN_USD = 200  # 订舱费+起运地附加费(THC/港务/码头安保),按【每次订舱】计
                          #   关键: 中转 = 2 次订舱 → 这部分要算【两遍】(优化器里每段都加一次)
DOOR_ORIGIN_USD = {'20':300, '40':380}   # 起运地拖车(门到... )
DOOR_DEST_USD   = {'20':400, '40':500}   # 目的地拖车(...到门)
VALIDITY = "MOCK (replace with real 运价有效期)"

def canon(p):
    s=re.sub(r"\(.*?\)","",p or ""); return re.sub(r"\s+"," ",s).strip().title()

def main():
    routes=json.load(open(os.path.join(HERE,'cosco_routes_raw.json')))['routes']
    def num(v):
        try: return int(v)
        except: return None
    # 连通边:同一航线同方向内 i<j 的可售 O-D,days = eta_j - etd_i,取最小天数
    edge_days={}
    for x in routes:
        c=x['callPort'].get('content') if x['callPort'] else None
        if not c: continue
        if isinstance(c,dict): c=[c]
        for blk in c:
            ps=blk.get('ports',[])
            for i in range(len(ps)):
                etd=num(ps[i].get('callPortEtdTime')); A=canon(ps[i]['callPort'])
                if etd is None: continue
                for j in range(i+1,len(ps)):
                    eta=num(ps[j].get('callPortEtaTime')); B=canon(ps[j]['callPort'])
                    if eta is None or B==A: continue
                    d=eta-etd
                    if d<0: continue
                    k=(A,B)
                    if k not in edge_days or d<edge_days[k]: edge_days[k]=d

    # 1) 海运边运价(每条 O-D 边 × 箱型)
    with open(os.path.join(HERE,'ocean_edges_MOCK.csv'),'w',newline='') as f:
        w=csv.writer(f); w.writerow(['起运港','目的港','箱型','海运费USD','海运附加费USD','订舱起运地费USD','运输天数','运价有效期','数据来源'])
        for (A,B),d in sorted(edge_days.items()):
            for box,m in BOX_MULT.items():
                ocean=round(RATE_PER_DAY_20GP*d*m, -1)   # round to 10
                w.writerow([A,B,box,int(ocean),SEA_SURCHARGE_USD,BOOKING_ORIGIN_USD,d,VALIDITY,'MOCK'])

    # 2) 港口拖车费(门到门/门到港/港到门 用)
    ports=sorted({p for e in edge_days for p in e})
    with open(os.path.join(HERE,'door_charges_MOCK.csv'),'w',newline='') as f:
        w=csv.writer(f); w.writerow(['港口','起运拖车20USD','起运拖车40USD','目的拖车20USD','目的拖车40USD','数据来源'])
        for p in ports:
            w.writerow([p,DOOR_ORIGIN_USD['20'],DOOR_ORIGIN_USD['40'],DOOR_DEST_USD['20'],DOOR_DEST_USD['40'],'MOCK'])

    print(f"connected O-D edges: {len(edge_days):,}")
    print(f"  -> ocean_edges_MOCK.csv : {len(edge_days)*len(BOX_MULT):,} rows (edge × box)")
    print(f"  -> door_charges_MOCK.csv: {len(ports):,} ports")

if __name__=='__main__':
    main()
