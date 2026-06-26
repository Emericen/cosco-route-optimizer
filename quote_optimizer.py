#!/usr/bin/env python3
"""
quote_optimizer.py — 客户 A→B 方案优化器(成本 + 天数 多目标)

结构与逻辑已完整;运价目前是【模拟数据】。拿到真实运价后,只需替换
ocean_edges_MOCK.csv / door_charges_MOCK.csv 的数值,本程序无需改动。

数据来源:
  cosco_routes_raw.json   航线图(港口=节点,航段=边),边的【天数】权重=真实抓取
  ocean_edges_MOCK.csv    边的【运价】权重(模拟,可替换为真实)
  door_charges_MOCK.csv   门到门/门到港/港到门 的拖车费(模拟)

用法:
  python3 quote_optimizer.py --from Ningbo --to Rotterdam --box 40GP --service DD --priority price
  python3 quote_optimizer.py --from Nansha --to Hochiminh --priority days -k 5
  service: PP 港到港 | DD 门到门 | DP 门到港 | PD 港到门
  priority: price 价格优先 | days 天数优先 | balanced 综合
"""
import json, csv, heapq, argparse, os, re
HERE=os.path.dirname(os.path.abspath(__file__))
ALIASES={"ho chi minh":"Hochiminh","saigon":"Hochiminh","hk":"Hong Kong"}

def canon(p):
    s=re.sub(r"\(.*?\)","",p or ""); s=re.sub(r"\s+"," ",s).strip()
    if not s: return p
    return ALIASES.get(s.lower(), s.title())

def load_graph():
    routes=json.load(open(os.path.join(HERE,'cosco_routes_raw.json')))['routes']
    name={x['serLpCode']:x['nameCn'] or x['serLpCode'] for x in routes}
    def num(v):
        try: return int(v)
        except: return None
    adj={}; ports=set()
    for x in routes:
        c=x['callPort'].get('content') if x['callPort'] else None
        if not c: continue
        if isinstance(c,dict): c=[c]
        for blk in c:
            ps=blk.get('ports',[]); d=blk.get('direction')
            for i in range(len(ps)):
                etd=num(ps[i].get('callPortEtdTime')); A=canon(ps[i]['callPort']); ports.add(A)
                if etd is None: continue
                for j in range(i+1,len(ps)):
                    eta=num(ps[j].get('callPortEtaTime')); B=canon(ps[j]['callPort']); ports.add(B)
                    if eta is None or B==A or eta-etd<0: continue
                    adj.setdefault(A,[]).append({'to':B,'days':eta-etd,'svc':x['serLpCode'],'svc_name':name[x['serLpCode']]})
    # keep fastest edge per (A,B,svc)
    for p,es in adj.items():
        best={}
        for e in es:
            k=(e['to'],e['svc'])
            if k not in best or e['days']<best[k]['days']: best[k]=e
        adj[p]=list(best.values())
    return adj, sorted(ports)

def load_rates():
    ocean={}  # (A,B,box) -> (海运费, 海运附加费, 订舱起运地费)  —— 每段(=每次订舱)都收一遍
    for r in csv.DictReader(open(os.path.join(HERE,'ocean_edges_MOCK.csv'))):
        ocean[(r['起运港'],r['目的港'],r['箱型'])]=(int(r['海运费USD']),int(r['海运附加费USD']),int(r['订舱起运地费USD']))
    door={}   # port -> dict
    for r in csv.DictReader(open(os.path.join(HERE,'door_charges_MOCK.csv'))):
        door[r['港口']]={'o20':int(r['起运拖车20USD']),'o40':int(r['起运拖车40USD']),
                         'd20':int(r['目的拖车20USD']),'d40':int(r['目的拖车40USD'])}
    return ocean, door

# 中转操作费(在中转港掏箱/换船的物理操作),按【每次中转】计;订舱/起运地费的"翻倍"已在每段单独计入
TRANSSHIP_HANDLING=100; TRANSSHIP_DWELL=2   # 中转等待天数(等下一班船),按每次中转计

def resolve(q, ports):
    c=canon(q)
    if c in ports: return c, []
    ms=sorted({p for p in ports if q.lower() in p.lower()})
    return (ms[0],[]) if len(ms)==1 else (None,ms)

def find(adj, ocean, door, A, B, box, service, priority, max_transship, k):
    sz='20' if box.startswith('20') else '40'
    def door_cost(port, side):  # side 'o' origin / 'd' dest
        d=door.get(port);
        return d[side+sz] if d else 0
    def legcost(frm,to):   # 每一段=一次订舱: 海运费 + 海运附加费 + 订舱起运地费(中转有2段→订舱起运地费自然算两遍)
        v=ocean.get((frm,to,box))
        return (v[0]+v[1]+v[2]) if v else None
    max_legs=max_transship+1
    # state: (key, ctr, days, cost, transship, port, last_svc, path)
    ctr=0
    pq=[(0.0, ctr, 0, 0, 0, A, None, [])]
    out=[]; seen=set()
    W_PRICE={'price':1.0,'days':0.0,'balanced':0.5}[priority]
    W_DAYS ={'price':0.0,'days':1.0,'balanced':0.5}[priority]
    while pq and len(out)<k:
        key,_,days,cost,tx,port,last,path=heapq.heappop(pq)
        if port==B and path:
            sig=tuple((l['svc'],l['from'],l['to']) for l in path)
            if sig in seen: continue
            seen.add(sig)
            # add door charges at true endpoints by service type
            extra=0
            if service in ('DD','DP'): extra+=door_cost(A,'o')
            if service in ('DD','PD'): extra+=door_cost(B,'d')
            out.append({'days':days,'cost':cost+extra,'transship':tx,   # days 已含中转等待,勿重复加
                        'legs':path,'door':extra})
            continue
        if len(path)>=max_legs: continue
        visited={A}|{l['to'] for l in path}
        for e in adj.get(port,[]):
            if e['to'] in visited: continue
            if last and e['svc']==last: continue
            lc=legcost(port,e['to'])
            if lc is None: continue
            nd=days+e['days']+(TRANSSHIP_DWELL if path else 0)
            nc=cost+lc+(TRANSSHIP_HANDLING if path else 0)
            # normalize for ranking key (days~/40, cost~/4000 to similar scale)
            nkey=W_PRICE*(nc/4000.0)+W_DAYS*(nd/40.0)
            ctr+=1
            leg={'from':port,'to':e['to'],'svc':e['svc'],'svc_name':e['svc_name'],'days':e['days'],'cost':lc}
            heapq.heappush(pq,(nkey,ctr,nd,nc,tx+(1 if path else 0),e['to'],e['svc'],path+[leg]))
    # final sort by chosen objective
    out.sort(key=lambda r:(r['cost'] if priority=='price' else r['days'] if priority=='days' else r['cost']/4000+r['days']/40))
    return out

SVC_CN={'PP':'港到港','DD':'门到门','DP':'门到港','PD':'港到门'}
def fmt(res,A,B,box,service,priority):
    if not res: return f"  ✗ 未找到 {A}→{B} 的方案"
    pri={'price':'价格优先','days':'天数优先','balanced':'综合'}[priority]
    o=[f"  {A} → {B}  | 箱型 {box} | 服务 {SVC_CN.get(service,service)} | 排序: {pri}",
       f"  (运价=模拟数据MOCK,锚定 上海→Chicago 真实产品 $175/天)\n"]
    for n,r in enumerate(res,1):
        tag='直达' if r['transship']==0 else f"{r['transship']}次中转"
        o.append(f"  {n}. 总价 ~USD {r['cost']:,}  |  ~{r['days']}天  ({tag})")
        for l in r['legs']:
            o.append(f"       {l['svc']:8} {l['from']}→{l['to']}  ${l['cost']:,} / {l['days']}天")
        if r['door']: o.append(f"       + 拖车(门点) ${r['door']:,}")
        o.append("")
    return "\n".join(o)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--from',dest='src',required=True); ap.add_argument('--to',dest='dst',required=True)
    ap.add_argument('--box',default='20GP'); ap.add_argument('--service',default='PP',choices=['PP','DD','DP','PD'])
    ap.add_argument('--priority',default='price',choices=['price','days','balanced'])
    ap.add_argument('--max-transship',type=int,default=1); ap.add_argument('-k',type=int,default=5)
    a=ap.parse_args()
    adj,ports=load_graph(); ocean,door=load_rates()
    A,am=resolve(a.src,ports); B,bm=resolve(a.dst,ports)
    if A is None: print(f"起运港 '{a.src}' 不唯一/未找到: {am[:12]}"); return
    if B is None: print(f"目的港 '{a.dst}' 不唯一/未找到: {bm[:12]}"); return
    print(fmt(find(adj,ocean,door,A,B,a.box,a.service,a.priority,a.max_transship,a.k),A,B,a.box,a.service,a.priority))

if __name__=='__main__':
    main()
