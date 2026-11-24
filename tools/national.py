"""National Account Tracker: match account-level depletions to chain location lists.

  python3 tools/national.py locations.csv vip_ytd.txt vip_ly.txt work/national.csv work/meta.json

locations.csv: chain,location,address,city,state,note  (one row per known location)
vip_*.txt: VIP "Accounts by Flavor_Import" rows (dist|account|address|city|state|vipid|12 brand columns),
  YTD (1/1–through date this year) and the same dates last year.
Matching: an account belongs to a chain if its name matches the chain pattern, or its street address
(number + first street word) and state match a listed location. Listed locations with no sales are kept
so "stores buying" can be shown against the full list.
"""
import csv, json, re, sys
from collections import defaultdict

BRANDS = ["Mango", "Citrus", "Espresso", "Lychee", "Key Lime Pie", "Orange", "Twin P Whiskey", "TD Vodka",
          "Blishens", "Strawberry Blood Orange RTD", "Tropical Rum", "KG Vodka"]
CHAINS = {  # name patterns on distributor account names
    "Hard Rock": r"HARD ROCK(?! STADIUM)|SEMINOLE (HARD ROCK|INDIAN CASINO|CASINO|BRIGHTON|CLASSIC|COCONUT)|\bHRC\b",
    "Mastro's": r"MASTRO'?S",
    "Beef O'Brady's": r"BEEF ?'?O'? ?BRADY|BEEFS? O BRAD",
    "Fat Tuesday": r"FAT TUESDAY",
    "Primanti Bros": r"PRIMANTI",
    "Alamo Drafthouse": r"ALAMO DRAFT",
    "Buffalo Wild Wings": r"BUFFALO WILD WING|\bBWW\b",
    "Motek": r"\bMOTEK\b",
    "Crescent Hotels": r"$^",  # hotels go by address only
    "Duffy's Sports Grill": r"DUFFY",
    "Azteca D'Oro": r"AZTECA D ?'?OR",
    "Riviera Dining Group": r"^MILA\b|CASA NEOS|CLAUDIE|^AVA (MEDITERR|COCONUT|WINTER)|^HONO\b",
    "Knallhart Group": r"AJ'?S PIZZA JOINT|HARLOW GROVE|FLORIDA HOUSE|THE FEDERAL|WAR MEMORIAL|HARRELL'?S|MARINA VILLAGE|SHORELY|PALM ROOM|RHYTHM ?(\+|&|AND)? ?VINE|ROXANNE'?S|THE WILDER|WHOLE ENCHILADA|WINTER GARDEN HOTEL",
    "The Restaurant People": r"^YOLO\b|^BOATYARD\b|^NAIA\b|SUN SURF SAND|CASABLANCA CAFE|GISELLE|JAVA ?(&|AND)? ?JAM|1 ?WLO|ROSA SKY|TARPON RIVER BREW|TRP TASTE|NUBE ROOF|JAGGER SUITE",
    "Taco Mac": r"TACO MAC",
    "V&E Hospitality Group": r"HAVANA 1957|OH!? MEXICO|MERCATO DELLA PESCHERIA|PAPER ?FISH|CORTADITO|NEWS CAFE|CAFE AMERICANO|BARSECCO|MARABU|DONATELLA|CERVECERIA DE BARRIO|SALTY FLAME",
}
ALIAS = {  # (state, VIP city, VIP account prefix) -> listed location name, for names the matcher can't tie
    ("FL", "HOLLYWOOD", "SEMINOLE INDIAN CASINO"): "Casino: Seminole Casino - Hollywood (Classic)",
    ("FL", "FORT LAUDERDALE", "SEMINOLE HARD ROCK HOTEL"): "Casino Hotel: Seminole Hard Rock Hollywood",
    ("FL", "FORT LAUDERDALE", "HARD ROCK CAFE"): "Café: Hollywood FL",
    ("FL", "POMPANO BEACH", "SEMINOLE INDIAN CASINO COCONUT"): "Casino: Seminole Casino - Coconut Creek (Coco)",
    ("FL", "OKEECHOBEE", "SEMINOLE BRIGHTON"): "Casino: Seminole Casino - Brighton",
    ("NY", "NEW YORK", "HARD ROCK CAFE"): "Café: New York",
    ("NY", "BRONX", "HARD ROCK CAFE"): "Café: Yankee Stadium",
    ("DC", "WASHINGTON", "HARD ROCK CAFE"): "Café: Washington DC",
    ("IN", "GARY", "HARD ROCK CASINO"): "Casino: Northwest, Indiana",
    ("OH", "CINCINNATI", "HARD ROCK CASINO"): "Casino: Hard Rock Cincinnati",
    ("CA", "WHEATLAND", "HARD ROCK HOTEL"): "Casino Hotel: Hard Rock Sacramento",
}
CONTROL = {"PA", "VA", "IA", "MS"}
ABBR = {"STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "ROAD": "RD", "DRIVE": "DR", "HIGHWAY": "HWY",
        "PARKWAY": "PKWY", "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "NORTHEAST": "NE",
        "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW", "LANE": "LN", "CIRCLE": "CIR", "COURT": "CT"}


def akey(addr, st):
    a = re.sub(r"[^A-Z0-9 ]", " ", str(addr).upper())
    w = [ABBR.get(x, x) for x in a.split()]
    if not w or not w[0][0].isdigit():
        return None
    num = re.sub(r"\D.*", "", w[0])
    rest = [x for x in w[1:] if x not in ("N", "S", "E", "W", "NE", "NW", "SE", "SW")]
    return f"{st}|{num}|{rest[0] if rest else ''}"


def load_vip(path):
    out = {}
    dist = ""
    for line in open(path, encoding="utf-8"):
        c = line.rstrip("\n").split("|")
        if len(c) < 18 or c[0] == "Total":
            continue
        dist = c[0] or dist
        acct, addr, city, st, vid = c[1:6]
        vals = [float(x.replace(",", "") or 0) for x in c[6:18]]
        out[vid] = dict(dist=dist, account=acct, address=addr, city=city, state=st, cases=dict(zip(BRANDS, vals)))
    return out


def main(loc_path, ytd_path, ly_path, out_path, meta_path):
    locs = list(csv.DictReader(open(loc_path, encoding="utf-8")))
    ytd, ly = load_vip(ytd_path), load_vip(ly_path)
    accts = {**ly, **ytd}
    bykey = {}
    for i, l in enumerate(locs):
        k = akey(l["address"], l["state"].strip())
        if k:
            bykey.setdefault(k, i)
    rows, hit = [], set()
    for vid, a in accts.items():
        chain, li = None, None
        k = akey(a["address"], a["state"])
        if k in bykey:
            li = bykey[k]
            chain = locs[li]["chain"]
        else:
            for ch, pat in CHAINS.items():
                if re.search(pat, a["account"]):
                    chain = ch
                    break
        if not chain:
            continue
        if li is None:
            for (ast, acity, apre), lname in ALIAS.items():
                if a["state"] == ast and a["city"].upper() == acity and a["account"].startswith(apre):
                    li = next((i for i, l in enumerate(locs) if l["location"] == lname), None)
        if li is None:  # name match: attach to a listed location in the same city if there is one
            cands = [i for i, l in enumerate(locs) if l["chain"] == chain and l["state"].strip() == a["state"]
                     and str(l["city"]).strip().upper() == a["city"].strip().upper() and i not in hit]
            if len(cands) > 1:  # pick by type words (cafe / casino / hotel / airport)
                words = set(re.findall(r"CAFE|CASINO|HOTEL|AIRPORT|STADIUM", a["account"]))
                score = lambda i: len(words & set(re.findall(r"CAFE|CASINO|HOTEL|AIRPORT|STADIUM", locs[i]["location"].upper().replace("É", "E"))))
                best = max(cands, key=score)
                cands = [best] if score(best) and sum(score(i) == score(best) for i in cands) == 1 else []
            li = cands[0] if len(cands) == 1 else None
        if li is not None:
            hit.add(li)
        L = locs[li] if li is not None else None
        for b in BRANDS:
            y, p = ytd.get(vid, {}).get("cases", {}).get(b, 0), ly.get(vid, {}).get("cases", {}).get(b, 0)
            if y or p:
                rows.append(dict(chain=chain, state=a["state"], location=(L["location"] if L else f'{a["account"].title()} ({a["city"].title()})'),
                                 city=a["city"].title(), account=a["account"], on_list="Yes" if L else "Name match",
                                 sku=b, ytd=round(y, 1), ly=round(p, 1), note=(L or {}).get("note", "")))
    for i, l in enumerate(locs):
        if i in hit:
            continue
        st = l["state"].strip()
        rows.append(dict(chain=l["chain"], state=st, location=l["location"], city=str(l["city"]).strip().title(),
                         account="", on_list="Yes", sku="", ytd=0, ly=0,
                         note=l.get("note", "") or ("Control state: no store-level depletions" if st in CONTROL else "")))
    rows.sort(key=lambda r: (r["chain"], r["state"], r["location"], r["sku"]))
    for n, r in enumerate(rows, 1):
        r["id"] = n
    cols = ["id", "chain", "state", "location", "city", "account", "on_list", "sku", "ytd", "ly", "note"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    meta = json.load(open(meta_path, encoding="utf-8"))
    meta.setdefault("_types", {})["national"] = {c: ("float" if c in ("ytd", "ly") else "int" if c == "id" else "str") for c in cols}
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    s = defaultdict(lambda: [0, 0, set(), 0])
    for r in rows:
        g = s[r["chain"]]
        g[0] += r["ytd"]; g[1] += r["ly"]
        if r["ytd"] > 0:
            g[2].add((r["state"], r["location"]))
    for ch, g in sorted(s.items()):
        n_loc = sum(1 for l in locs if l["chain"] == ch)
        print(f"{ch:20s} YTD {g[0]:7.0f}  LY {g[1]:7.0f}  buying {len(g[2])}  listed {n_loc}")


if __name__ == "__main__":
    main(*sys.argv[1:6])
