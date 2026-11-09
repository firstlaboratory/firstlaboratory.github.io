"""Daily price update for Daam. Standard library only.

Writes daam/prices.json with:
  - gold / silver spot price (USD per gram) from gold-api.com (free, no key)
  - exchange rates (units per USD) from open.er-api.com (free, no key)
  - India mandi (wholesale market) prices by state from data.gov.in,
    converted to an estimated shop price per kg. Needs a free API key in the
    repository secret DATA_GOV_IN_KEY; skipped if the key is missing.
Any source that fails keeps its previous value, so the app never goes blank.
"""
import json, os, statistics, urllib.parse, urllib.request
from datetime import datetime, timezone

OUT = os.path.join(os.path.dirname(__file__), "..", "prices.json")
UA = {"User-Agent": "daam-price-updater/1.0 (github.com/firstlaboratory)"}

def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

try:
    with open(OUT, encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    data = {}
log = []
now = datetime.now(timezone.utc).isoformat(timespec="minutes")

# --- Exchange rates ---
try:
    j = get("https://open.er-api.com/v6/latest/USD")
    if j.get("result") == "success":
        data["rates"] = j["rates"]; data["rates_updated"] = now; log.append("rates ok")
except Exception as e:
    log.append(f"rates failed: {e}")

# --- Gold & silver (USD per troy ounce -> per gram) ---
OZ = 31.1034768
for sym, key in (("XAU", "gold"), ("XAG", "silver")):
    try:
        j = get(f"https://api.gold-api.com/price/{sym}")
        price = float(j["price"])
        if price > 0:
            data[key] = {"usd_per_g": round(price / OZ, 4), "updated": now}; log.append(f"{key} ok")
    except Exception as e:
        log.append(f"{key} failed: {e}")

# --- India mandi prices (data.gov.in) ---
# Daam item id -> commodity name used by Agmarknet, and shop markup over wholesale.
MANDI = {
    "onion": ("Onion", 1.5), "tomato": ("Tomato", 1.6), "potato": ("Potato", 1.5),
    "garlic": ("Garlic", 1.4), "bananas": ("Banana", 1.6), "apples": ("Apple", 1.5),
    "rice": ("Rice", 1.25), "dal": ("Arhar Dal(Tur Dal)", 1.2), "atta": ("Wheat Atta", 1.2),
    "mango": ("Mango", 1.6), "oranges": ("Orange", 1.6),
}
# Agmarknet state name -> Daam state label
STATES = {
    "Tamil Nadu": "Tamil Nadu (Chennai)", "Maharashtra": "Maharashtra (Mumbai)", "Karnataka": "Karnataka (Bengaluru)",
    "NCT of Delhi": "Delhi", "Delhi": "Delhi", "Telangana": "Telangana (Hyderabad)", "Kerala": "Kerala (Kochi)",
    "West Bengal": "West Bengal (Kolkata)", "Gujarat": "Gujarat (Ahmedabad)", "Rajasthan": "Rajasthan (Jaipur)",
    "Uttar Pradesh": "Uttar Pradesh (Lucknow)", "Uttrakhand": "Uttarakhand (Dehradun)", "Uttarakhand": "Uttarakhand (Dehradun)",
    "Punjab": "Punjab (Chandigarh)", "Chandigarh": "Punjab (Chandigarh)",
}
KEY = os.environ.get("DATA_GOV_IN_KEY", "").strip()
RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"  # Current daily price of various commodities from various markets
if KEY:
    mandi = data.get("mandi", {})
    for item, (commodity, markup) in MANDI.items():
        try:
            q = urllib.parse.urlencode({"api-key": KEY, "format": "json", "limit": 1000, "filters[commodity]": commodity})
            j = get(f"https://api.data.gov.in/resource/{RESOURCE}?{q}", timeout=60)
            by_state = {}
            for rec in j.get("records", []):
                st = STATES.get(rec.get("state", "").strip())
                try:
                    modal = float(rec.get("modal_price") or 0)  # rupees per quintal (100 kg)
                except ValueError:
                    continue
                if st and modal > 0:
                    by_state.setdefault(st, []).append(modal)
            if by_state:
                allv = [v for vs in by_state.values() for v in vs]
                mandi[item] = {
                    "IN": round(statistics.median(allv) / 100 * markup, 1),
                    **{st: round(statistics.median(vs) / 100 * markup, 1) for st, vs in by_state.items()},
                    "updated": now,
                }
                log.append(f"mandi {item}: {len(by_state)} states")
            else:
                log.append(f"mandi {item}: no records today")
        except Exception as e:
            log.append(f"mandi {item} failed: {e}")
    data["mandi"] = mandi
else:
    log.append("mandi skipped: add the DATA_GOV_IN_KEY secret to enable")

data["updated"] = now
data["log"] = log
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print("\n".join(log))
