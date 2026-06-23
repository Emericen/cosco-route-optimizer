#!/usr/bin/env python3
"""
route_finder.py — COSCO 航线 A→B 最优路线查询
Builds a port graph from the scraped data and finds the fastest itinerary
(direct or with transshipment) between two ports, ranked by transit days.

Data in:  cosco_routes_raw.json  (port-call sequences w/ cumulative ETA/ETD days)
Optimizes for: transit time + a configurable per-transshipment penalty.
(NOTE: cost / sailing-frequency are NOT on the source site, so "optimal" here
means fastest / fewest-transshipment, not cheapest.)

Examples:
  python3 route_finder.py --from Shanghai --to "Long Beach"
  python3 route_finder.py --from Ningbo --to Rotterdam --max-transship 2 -k 5
  python3 route_finder.py --list-ports Shang
"""
import json, heapq, argparse, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ----- optional alias map for messy port names (extend as needed) -----
ALIASES = {
    "ho chi minh": "Hochiminh", "saigon": "Hochiminh",
    "hk": "Hong Kong", "la": "Los Angeles", "lb": "Long Beach",
}

def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def canon(p):
    """Canonical port node: drop '(terminal)' suffixes, normalize case/space, alias."""
    s = re.sub(r"\(.*?\)", "", p or "")          # "Rotterdam (RWG)" -> "Rotterdam"
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return p
    a = ALIASES.get(norm(s))
    return a if a else s.title()                  # "ROTTERDAM"/"rotterdam" -> "Rotterdam"

def load_graph(routes_path):
    routes = json.load(open(routes_path))["routes"]
    name = {x["serLpCode"]: x["nameCn"] or x["serLpCode"] for x in routes}

    def legs(x):
        cp = x["callPort"]; c = cp.get("content") if cp else None
        if not c: return []
        if isinstance(c, dict): c = [c]
        out = []
        for b in c:
            for p in b.get("ports", []):
                out.append({**p, "_dir": b.get("direction")})
        return out

    def num(v):
        try: return int(v)
        except (TypeError, ValueError): return None

    # adjacency: from_port -> list of edge dicts
    adj = {}
    ports = set()
    for x in routes:
        seq = legs(x)
        for d in {p["_dir"] for p in seq}:
            sub = [p for p in seq if p["_dir"] == d]
            for i in range(len(sub)):
                etd_i = num(sub[i].get("callPortEtdTime"))
                A = canon(sub[i]["callPort"]); ports.add(A)
                if etd_i is None:
                    continue
                for j in range(i + 1, len(sub)):
                    eta_j = num(sub[j].get("callPortEtaTime"))
                    B = canon(sub[j]["callPort"]); ports.add(B)
                    if eta_j is None or B == A:
                        continue
                    t = eta_j - etd_i
                    if t < 0:
                        continue
                    adj.setdefault(A, []).append(
                        {"to": B, "days": t, "svc": x["serLpCode"],
                         "svc_name": name[x["serLpCode"]], "dir": d})
    # dedup: keep fastest edge per (from,to,svc,dir)
    for p, edges in adj.items():
        best = {}
        for e in edges:
            k = (e["to"], e["svc"], e["dir"])
            if k not in best or e["days"] < best[k]["days"]:
                best[k] = e
        adj[p] = list(best.values())
    return adj, sorted(ports)

def resolve(query, ports):
    """Resolve a user port query to a canonical port name in the graph."""
    c = canon(query)
    if c in ports:
        return c, []
    q = norm(query)
    matches = sorted({p for p in ports if q in norm(p)})
    if len(matches) == 1:
        return matches[0], []
    return None, matches

def find_routes(adj, A, B, max_transship=1, k=5, penalty=2.0):
    """Best-first (uniform-cost) search over itineraries. Returns up to k."""
    max_legs = max_transship + 1
    # state in pq: (cost, tiebreak, days, transship, port, last_svc, path)
    ctr = 0
    pq = [(0.0, ctr, 0, 0, A, None, [])]
    results, seen_sig = [], set()
    while pq and len(results) < k:
        cost, _, days, tx, port, last_svc, path = heapq.heappop(pq)
        if port == B and path:
            sig = tuple((l["svc"], l["from"], l["to"]) for l in path)
            if sig not in seen_sig:
                seen_sig.add(sig)
                results.append({"days": days, "transship": tx, "legs": path})
            continue
        if len(path) >= max_legs:
            continue
        visited = {A} | {l["to"] for l in path}
        for e in adj.get(port, []):
            if e["to"] in visited:        # no cycles
                continue
            if last_svc and e["svc"] == last_svc:  # same service = not a transfer
                continue
            new_tx = tx + (1 if path else 0)
            add = e["days"] + (penalty if path else 0)
            leg = {"from": port, "to": e["to"], "svc": e["svc"],
                   "svc_name": e["svc_name"], "dir": e["dir"], "days": e["days"]}
            ctr += 1
            heapq.heappush(pq, (cost + add, ctr, days + e["days"], new_tx,
                                e["to"], e["svc"], path + [leg]))
    return results

def fmt(results, A, B):
    if not results:
        return f"  ✗ 未找到 {A} → {B} 的路线（在允许的中转次数内）。"
    out = [f"  {A} → {B}：找到 {len(results)} 条路线（按运输天数排序）\n"]
    for n, r in enumerate(results, 1):
        tag = "直达" if r["transship"] == 0 else f"{r['transship']} 次中转"
        out.append(f"  {n}. 总运输 ~{r['days']} 天  ({tag})")
        for l in r["legs"]:
            out.append(f"       {l['svc']:8} {l['svc_name']:<12} "
                       f"{l['from']} → {l['to']}  ({l['days']}天, 方向{l['dir']})")
        out.append("")
    return "\n".join(out)

def main():
    ap = argparse.ArgumentParser(description="COSCO A→B 最优航线查询")
    ap.add_argument("--from", dest="src", help="起运港 origin port")
    ap.add_argument("--to", dest="dst", help="目的港 destination port")
    ap.add_argument("--max-transship", type=int, default=1, help="最大中转次数 (默认1)")
    ap.add_argument("-k", type=int, default=5, help="返回路线条数 (默认5)")
    ap.add_argument("--penalty", type=float, default=2.0,
                    help="每次中转的等待惩罚天数 (默认2)")
    ap.add_argument("--list-ports", metavar="Q", help="列出包含 Q 的港口名")
    ap.add_argument("--data", default=os.path.join(HERE, "cosco_routes_raw.json"))
    args = ap.parse_args()

    adj, ports = load_graph(args.data)

    if args.list_ports is not None:
        q = norm(args.list_ports)
        hits = [p for p in ports if q in norm(p)]
        print(f"匹配 '{args.list_ports}' 的港口 ({len(hits)}):")
        for p in hits: print("  ", p)
        print(f"\n图中共 {len(ports)} 个港口节点。")
        return

    if not args.src or not args.dst:
        ap.error("需要 --from 和 --to （或用 --list-ports 查港口名）")

    A, am = resolve(args.src, ports)
    B, bm = resolve(args.dst, ports)
    for label, val, ms in [("起运港", args.src, am), ("目的港", args.dst, bm)]:
        if val == args.src and A is None or val == args.dst and B is None:
            print(f"{label} '{val}' 不唯一/未找到。候选: {ms[:15] or '无 (试试 --list-ports)'}")
    if A is None or B is None:
        return
    print(fmt(find_routes(adj, A, B, args.max_transship, args.k, args.penalty), A, B))

if __name__ == "__main__":
    main()
