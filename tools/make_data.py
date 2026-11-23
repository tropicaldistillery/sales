"""Daily Sales Snapshot data tool for sales.tropicaldistillery.com.

  python3 tools/make_data.py split data.js work/   -> one CSV per table + meta.json
  python3 tools/make_data.py build work/ data.js   -> data.js from those files

Tables: portfolio, states, brands, monthly, inventory, pending, new_accounts, lost.
meta.json holds: updated, day, notes, risks (list of HTML strings).
Column order and names must stay the same; index.html reads them by name.
"""
import csv, json, os, sys

TABLES = ["portfolio", "states", "brands", "monthly", "inventory", "pending", "new_accounts", "lost", "r12", "national", "cities"]
META = ["updated", "day", "notes", "risks", "r12_months"]


def load_js(path):
    s = open(path, encoding="utf-8").read()
    return json.loads(s[s.index("{"): s.rindex("}") + 1])


def num(v):
    if v is None or v == "":
        return v
    try:
        f = float(v)
        return int(f) if f.is_integer() and "." not in str(v) else f
    except ValueError:
        return v


def split(js, out):
    os.makedirs(out, exist_ok=True)
    d = load_js(js)
    for t in TABLES:
        rows = d.get(t, [])
        cols = list(rows[0].keys()) if rows else []
        with open(os.path.join(out, t + ".csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    types = {t: {c: next((type(r[c]).__name__ for r in d.get(t, []) if r.get(c) is not None), "str") for c in (d[t][0].keys() if d.get(t) else [])} for t in TABLES}
    json.dump({**{k: d.get(k) for k in META}, "_types": types}, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("split", {t: len(d.get(t, [])) for t in TABLES})


def build(src, js):
    meta = json.load(open(os.path.join(src, "meta.json"), encoding="utf-8"))
    types = meta.pop("_types", {})

    def cast(t, k, v):
        ty = types.get(t, {}).get(k)
        if v == "":
            return None if ty in ("int", "float", "NoneType") else v
        if ty == "int":
            return int(float(v))
        if ty == "float":
            return float(v)
        if ty == "bool":
            return v == "True"
        if ty == "str":
            return v
        return num(v)

    d = {}
    for t in TABLES:
        p_ = os.path.join(src, t + ".csv")
        if not os.path.exists(p_):
            d[t] = []
            continue
        with open(p_, encoding="utf-8") as f:
            d[t] = [{k: cast(t, k, v) for k, v in r.items()} for r in csv.DictReader(f)]
    d.update(meta)
    # sanity checks
    p = {r["measure"]: r for r in d["portfolio"]}
    st_ship = sum(float(r["ship_ytd"] or 0) for r in d["states"])
    if "Shipments" in p and abs(st_ship - float(p["Shipments"]["ytd"])) > 2:
        print(f"WARNING: state shipments {st_ship:.0f} != portfolio {p['Shipments']['ytd']}")
    st_dep = sum(float(r["depl_ytd"] or 0) for r in d["states"])
    if "Depletions" in p and abs(st_dep - float(p["Depletions"]["ytd"])) > 2:
        print(f"WARNING: state depletions {st_dep:.0f} != portfolio {p['Depletions']['ytd']}")
    open(js, "w", encoding="utf-8").write("window.D=" + json.dumps(d, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("built", js, {t: len(d[t]) for t in TABLES}, d["day"])


if __name__ == "__main__":
    cmd, a, b = sys.argv[1:4]
    split(a, b) if cmd == "split" else build(a, b)
