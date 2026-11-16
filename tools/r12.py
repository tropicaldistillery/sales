"""Rolling 12-month shipments by state x SKU (DISTILL x 5 Product Outbound, physical cases).

  python3 tools/r12.py dx5_agg.txt jensen.csv work/r12.csv work/meta.json [YYYYMM_last_complete]

dx5_agg.txt: lines "YYYYMM|customer|product|size|cases|bottles|price" (Product Outbound,
  aggregated by month/customer/product/size; pull at least 24 months back).
jensen.csv: pass "-". (Jensen's Vodka IS in DISTILL x 5: Mazeltov Beverages orders of TD Vodka 1.75L.)
Window = last 12 COMPLETE months; "prior" = the 12 months before that.
Excludes TD Retail (samples) and Casa Loco (commission brand). Writes r12_months into meta.json.
"""
import csv, json, sys
from collections import defaultdict

STATE = [  # (substring in customer name, state label as used in the states table, code)
    ("TD Retail", None, None),
    ("Monarq", "Caribbean / Latin America / cruise duty free (Monarq)", "Intl (Monarq)"),
    ("Trade Links", "Caribbean / Latin America / cruise duty free (Monarq)", "Intl (Monarq)"),
    ("Cruise Duty Free", "Caribbean / Latin America / cruise duty free (Monarq)", "Intl (Monarq)"),
    ("RBG Tampa", "Florida", "FL"), ("RBG Deerfield", "Florida", "FL"), ("RBG Pensacola", "Florida", "FL"),
    ("RNDC Jacksonville", "Florida", "FL"), ("Mazeltov", "Florida", "FL"),
    ("National Dist", "Georgia", "GA"),
    ("New York Wine", "New York", "NY"), ("RNDC New York", "New York", "NY"),
    ("Fedway", "New Jersey", "NJ"), ("Athens", "Tennessee", "TN"),
    ("California", "California", "CA"),
    ("Nevada", "Nevada", "NV"), ("Summit", "Nevada", "NV"),
    ("Heidelberg", "Ohio", "OH"),
    ("of Maryland", "Maryland", "MD"), ("Alcohol Beverage Services", "Maryland", "MD"),
    ("of DC", "Washington DC", "DC"), ("Washington DC", "Washington DC", "DC"),
    ("of Texas", "Texas", "TX"), ("RNDC Texas", "Texas", "TX"),
    ("Louisiana", "Louisiana", "LA"), ("LAFAYETTE", "Louisiana", "LA"),
    ("Columbia", "South Carolina", "SC"), ("Oklahoma", "Oklahoma", "OK"), ("RNDC Illinois", "Illinois", "IL"),
    ("LibDib", "LibDib (CT/IL)", "CT/IL (LibDib)"), ("Island Dist", "Hawaii", "HI"),
    ("Pennsylvania", "Pennsylvania (bailment)", "PA"), ("Virginia", "Virginia (bailment)", "VA"),
    ("Iowa", "Iowa (bailment)", "IA"), ("MISSISSIPPI", "Mississippi", "MS"),
    ("Burke", "Massachusetts", "MA"), ("Standard Beverage", "Kansas", "KS"),
    ("Denver", "Colorado", "CO"), ("Sioux Falls", "South Dakota", "SD"), ("Arizona", "Arizona", "AZ"),
    ("Indiana", "Indiana", "IN"),
]
SKU = {  # DISTILL product -> (sku, line)
    "Lychee Liqueur": ("Lychee", "J.F. Haden's"), "Mango Liqueur": ("Mango", "J.F. Haden's"),
    "Espresso Liqueur": ("Espresso", "J.F. Haden's"), "Key Lime Pie Liqueur": ("Key Lime Pie", "J.F. Haden's"),
    "Citrus Liqueur": ("Citrus", "J.F. Haden's"), "Orange Liqueur": ("Orange", "J.F. Haden's"),
    "TD Vodka": ("TD Vodka", "House brands"), "Twin P Bourbon": ("Twin P Whiskey", "House brands"),
    "KG Vodka": ("KG Vodka", "House brands"), "Blishen's Fire Whisky": ("Blishens", "House brands"),
    "TD White Rum": ("Tropical Rum", "House brands"), "TD Gin": ("TD Gin", "House brands"),
    "Allapattah Agave": ("Allapattah Agave", "House brands"),
    "Strawberry Blood Orange Vodka RTD": ("Strawberry Blood Orange RTD", "RTD"),
    "Cranberry Spritz RTD": ("Cranberry Spritz RTD", "RTD"),
}
PACK = {"750mL": 6, "1750mL": 6, "1L": 12, "355mL": 24, "12oz": 24}
MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def state_of(cust):
    for k, lab, code in STATE:
        if k.lower() in cust.lower():
            return lab, code
    return "Other: " + cust, "?"


def ym_add(ym, n):
    y, m = divmod(int(ym[:4]) * 12 + int(ym[4:]) - 1 + n, 12)
    return f"{y}{m + 1:02d}"


def main(src, jensen, out, meta_path, last=None):
    rows = [l.rstrip("\n").split("|") for l in open(src, encoding="utf-8") if l.count("|") >= 6]
    if not last:
        last = ym_add(max(r[0] for r in rows), -1)  # last complete month
    months = [ym_add(last, -i) for i in range(11, -1, -1)]
    prior = {ym_add(m, -12) for m in months}
    agg = defaultdict(lambda: defaultdict(float))
    lines = {}
    unknown = set()
    for ym, cust, prod, size, cases, bottles, _ in rows:
        if "casa loco" in prod.lower():
            continue
        st, code = state_of(cust)
        if st is None:
            continue
        if code == "?":
            unknown.add(cust)
        base = SKU.get(prod, (prod, "Other"))
        if "mazeltov" in cust.lower():  # Jensen's Vodka private label ships as TD Vodka 1.75L
            base, prod = ("Jensen's Vodka", "House brands"), "Jensen's Vodka"
        sku = base[0] + (f" {size.replace('1750mL', '1.75L')}" if prod in ("TD Vodka", "TD White Rum") else "")
        c = float(cases or 0)
        if c == 0 and float(bottles or 0):
            c = float(bottles) / PACK.get(size, 6)
        key = (st, code, sku)
        lines[key] = base[1]
        agg[key][ym] += c
    if jensen and jensen != "-":
        for r in csv.DictReader(open(jensen)):
            key = ("Florida", "FL", "Jensen's Vodka")
            lines[key] = "House brands"
            agg[key][r["month"]] += float(r["cases"])
    out_rows = []
    for (st, code, sku), byM in agg.items():
        vals = [round(byM.get(m, 0)) for m in months]
        pr = round(sum(v for m, v in byM.items() if m in prior))
        if sum(vals) == 0 and pr == 0:
            continue
        r = {"state": st, "code": code, "sku": sku, "line": lines[(st, code, sku)]}
        r.update({f"m{i + 1:02d}": v for i, v in enumerate(vals)})
        r.update({"r12": sum(vals), "prior": pr})
        out_rows.append(r)
    out_rows.sort(key=lambda r: (r["state"], -r["r12"]))
    for i, r in enumerate(out_rows, 1):
        r["id"] = i
    cols = ["id", "state", "code", "sku", "line"] + [f"m{i:02d}" for i in range(1, 13)] + ["r12", "prior"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)
    meta = json.load(open(meta_path, encoding="utf-8"))
    meta["r12_months"] = [f"{MON[int(m[4:]) - 1]} {m[2:4]}" for m in months]
    meta.setdefault("_types", {})["r12"] = {c: ("str" if c in ("state", "code", "sku", "line") else "int") for c in cols}
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(len(out_rows), "rows", meta["r12_months"][0], "-", meta["r12_months"][-1],
          "R12", sum(r["r12"] for r in out_rows), "prior", sum(r["prior"] for r in out_rows))
    if unknown:
        print("UNMAPPED CUSTOMERS:", sorted(unknown))


if __name__ == "__main__":
    main(*sys.argv[1:6])
