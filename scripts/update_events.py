#!/usr/bin/env python3
"""
Cool.fi – eventi COOL a Firenze: nightlife, club, rooftop, aperitivi, live.
Fonti: Dice.fm (club/live) · Eventbrite (serate/musica) · firenzespettacolo · theflorentine
Curazione: punteggio "coolness" — premia nightlife/social, taglia il turistico.
Social: mappa venue → Instagram handle, link diretto a ogni evento.
"""
import requests, json, os, re, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urljoin

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_FILE = os.path.join(ROOT, "cooleventsfi.html")
JSON_FILE = os.path.join(ROOT, "events.json")
LOG_FILE  = os.path.expanduser("~/Library/Logs/coolfi/update.log")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

# ── Stock fallback ──────────────────────────────────────────────────────────
IMAGES = {
    "CONCERTO": ["1501386761578-eac5c94b800a","1470225620780-dba8ba36b745","1465847899084-d164df4dedc6","1493225457124-a3eb161ffa5f"],
    "SERATA":   ["1533174072545-7a4b6ad7a6c3","1492684223066-81342ee5ff30","1516450360452-9312f5e86fc7","1574015974293-f6b9e3e2bb5e"],
    "MOSTRA":   ["1577083552431-6e5fd01988ec","1554907984-15263bfd63bd","1518998053901-5348d3961a04","1605350353407-d7a98fe16b21"],
    "MERCATO":  ["1452860606245-08befc0ff44b","1488459716781-31db52582fe9","1472851294608-062f824d29cc"],
    "SPORT":    ["1543429776-2782fc8e1acd","1571019613454-1cb2f99b2d8b","1461896836934-ffe607ba8211"],
    "FOOD":     ["1565299585323-38d6b0865b47","1498837167922-ddd27525d352","1414235077428-338989a2e8c0"],
    "CULTURA":  ["1489599849927-2ee91cede3ba","1571696769037-c6a7c44c1db6","1524995997946-a1c2e315a42f","1481627834876-b7833e8f5570"],
}
def random_img(cat): return random.choice(IMAGES.get(cat, IMAGES["CULTURA"]))

# ── Mappa venue → Instagram handle ─────────────────────────────────────────
VENUE_IG = {
    "the lodge":              "thelodgeflorence",
    "murate":                 "muratecaffelettario",
    "society music":          "societymusicclub",
    "dopolavoro ferroviario": "dlffirenze",
    "dlf":                    "dlffirenze",
    "ostello bello":          "ostellobellofirenze",
    "manifattura tabacchi":   "manifatturatabacchi",
    "flò":                    "flo.firenze",
    "flo firenze":            "flo.firenze",
    "yellowsquare":           "yellowsquareflorence",
    "yellow square":          "yellowsquareflorence",
    "w florence":             "wflorence",
    "w hotel":                "wflorence",
    "ruby bea":               "rubyflorence",
    "the social hub":         "thesocialhub",
    "palazzo strozzi":        "palazzostrozzi",
    "galleria accademia":     "galleriaaccademiafirenze",
    "palazzo medici":         "palazzomedici",
    "villa bardini":          "villabardini",
    "zeffirelli":             "zeffirelli_foundation",
    "teatro del maggio":      "teatrodelmaggio",
    "hard rock":              "hardrockcafeflorence",
    "geko":                   "gekoartstudio",
    "nana bianca":            "nanabianca",
}

def venue_social(luogo: str) -> dict | None:
    """Restituisce oggetto social per un venue noto, None se sconosciuto."""
    key = luogo.lower()
    for kw, handle in VENUE_IG.items():
        if kw in key:
            return {
                "platform": "Instagram",
                "label": f"@{handle}",
                "url": f"https://www.instagram.com/{handle}/",
            }
    return None

# ══ COOLNESS — sistema di curazione ═══════════════════════════════════════════
# Profilo Cool.fi: nightlife / club / rooftop + aperitivi & social. No turistico.

# Venue cool noti → grosso bonus
COOL_VENUES = [
    "atollo","ultravox","casa del popolo","tenax","otel","viper","flò","flo firenze",
    "the social hub","social hub","manifattura tabacchi","combo","sabotage","nof",
    "jazz club","volume","rooftop","ruby bea","w florence","w hotel","the lodge",
    "society music","le murate","ostello bello","yellowsquare","yellow square",
    "chalet fontana","fonderia","glue","ex wide","spazio alfieri","limonaia",
]

# Keyword cool → bonus
COOL_KW = [
    "rooftop","dj set","dj ","club","clubbing","party","disco","techno","house music",
    "live","concerto","band","aperitivo","apericena","secret","underground","rave",
    "vinyl","funk","soul","afrobeat","reggae","drum","bass","electronic","indie",
    "warehouse","after","night","serata","open air","sunset",
]

# Keyword turistico/robaccia → reject diretto
JUNK_KW = [
    "cooking class","cozymeal","food tour","walking tour","free walking","pasta making",
    "pizza making","make ravioli","make tagliatelle","make fabulous","craft authentic",
    "craft traditional","cooking in","hands-on pizza","dinner with new friends",
    "100 cities","foodies + new friends","new friends:","spa experience","matinée experience",
    "location provided after booking","quiz night","trivia","game night","summer camp",
    "art workshop for children","cup pong","legal & dpo",
]

# Concerti classici/barocchi turistici → reject (utente: "taglia troppo turistici")
TOURIST_CLASSICAL = [
    "baroque concert","opera arias","four seasons","quattro stagioni","vivaldi",
    "orchestra da camera","walt disney","matinée","chamber music","viole da gamba",
    "live baroque","armonie veneziane","concert in florence","opera in santa",
    # vocabolario musica da camera / classica
    "archi","ottetto","quintetto","quartetto","violino","violoncello","pianoforte",
    "flauto"," arpa","vibrafono","soprano","lirica","liriche","sinfon","coro della",
    "ensemble","duo ","mozart","hummel","fellini","rota","risonanze","cameristic",
    "flussi incrociati","l'acqua come","mare aperto","sulle rive del tempo","gocce e",
]

# Pagine aggregatore (non sono eventi) → reject
AGGREGATOR = [
    "oggi a firenze","weekend a firenze","la settimana dello spettacolo","wine news",
    "cartellone","city trend","hot news","pitti pool","agenda settimanale",
]

# Altre città (non Firenze) → reject
OTHER_CITIES = [
    "lucca","arezzo","pisa","siena","san gimignano","greve","carmignano","prato",
    "pistoia","livorno","grosseto","massa","maremma","chianti","bobi","etruschi",
]

def cool_score(ev: dict) -> int:
    """Punteggio coolness. < 1 = scartato. Più alto = più cool."""
    text = f"{ev.get('titolo','')} {ev.get('descrizione','')} {ev.get('luogo','')}".lower()
    luogo = ev.get("luogo","").lower()

    # Reject hard
    if any(j in text for j in JUNK_KW):         return -100
    if any(t in text for t in TOURIST_CLASSICAL): return -100
    if any(a in text for a in AGGREGATOR):       return -100
    if any(c in text for c in OTHER_CITIES):     return -100

    score = 0
    # Bonus venue cool
    if any(v in luogo for v in COOL_VENUES):     score += 5
    # Bonus keyword cool (max conta la varietà)
    score += sum(1 for k in COOL_KW if k in text)
    # Bonus categoria coerente col profilo (nightlife/social)
    cat = ev.get("categoria","")
    if cat == "SERATA":      score += 3
    elif cat == "CONCERTO":  score += 1
    elif cat == "MERCATO":   score -= 1   # raramente cool
    # Bonus se ha social IG di un venue noto
    if ev.get("social"):     score += 2
    # Bonus se ha video
    if ev.get("video"):      score += 2
    return score

# ── Date utils ──────────────────────────────────────────────────────────────
WEEKDAYS_IT = ["lun","mar","mer","gio","ven","sab","dom"]
MONTHS_IT = {
    "gen":1,"feb":2,"mar":3,"apr":4,"mag":5,"giu":6,
    "lug":7,"ago":8,"set":9,"ott":10,"nov":11,"dic":12,
    "gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,
    "luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12,
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
}

def fmt_date(dt: date) -> str:
    return f"{WEEKDAYS_IT[dt.weekday()]} {dt.day}/{dt.month:02d}"

def parse_iso(s: str) -> date | None:
    try: return datetime.fromisoformat(s.replace("Z","")).date()
    except: return None

def parse_date(text: str, today: date) -> date | None:
    t = text.lower()
    # "15/06/2026" o "15/06" o "15.06"
    m = re.search(r'\b(\d{1,2})[/\.](\d{1,2})(?:[/\.](\d{2,4}))?\b', t)
    if m:
        try:
            d, mo = int(m.group(1)), int(m.group(2))
            yr = int(m.group(3)) if m.group(3) else today.year
            if yr < 100: yr += 2000
            if 1 <= d <= 31 and 1 <= mo <= 12:
                dt = date(yr, mo, d)
                if dt < today: dt = date(yr+1, mo, d)
                if (dt - today).days <= 30: return dt
        except: pass
    # "15 giugno" / "15 june"
    m = re.search(r'\b(\d{1,2})\s+(' + '|'.join(MONTHS_IT) + r')\b', t)
    if m:
        try:
            d, mo = int(m.group(1)), MONTHS_IT.get(m.group(2), 0)
            if mo:
                dt = date(today.year, mo, d)
                if dt < today: dt = date(today.year+1, mo, d)
                if (dt - today).days <= 30: return dt
        except: pass
    return None

def parse_time(text: str) -> str:
    m = re.search(r'\b(\d{1,2})[:\.](\d{2})\b', text)
    if m: return f"{m.group(1)}:{m.group(2)}"
    m = re.search(r'(?:ore|h)\s*(\d{1,2})\b', text, re.I)
    if m: return f"{m.group(1)}:00"
    return ""

# ── Categoria ───────────────────────────────────────────────────────────────
def classify(title: str, desc: str = "") -> str:
    t = (title + " " + desc).lower()
    # SERATA prima di CONCERTO: party/club/dj/rooftop = nightlife, non concerto seduto
    if any(w in t for w in ["serata","club ","clubbing","discoteca","disco ","party",
                            "cocktail","nightlife","rooftop","dj set","dj ","soundsystem",
                            "sound system","rave","after party","open air","techno","house music"]):
        return "SERATA"
    if any(w in t for w in ["concerto","live","musica","band","jazz","classica","orchestra","rock","pop","indie","cantautore","gig"]):
        return "CONCERTO"
    if any(w in t for w in ["mostra","esposizione","galleria","arte","dipinti","scultura","fotografia","museo","exhibition"]):
        return "MOSTRA"
    if any(w in t for w in ["mercato","fiera","bancarelle","artigianato","antiquariato"]):
        return "MERCATO"
    if any(w in t for w in ["sport","calcio","basket","tennis","corsa","maratona","yoga","atletica"]):
        return "SPORT"
    if any(w in t for w in ["food","sagra","degustazione","vino","birra","cucina","gastronomia","dinner","cena","aperitivo","apericena"]):
        return "FOOD"
    return "CULTURA"

# ── og:image / og:video cache ───────────────────────────────────────────────
_media_cache: dict[str, tuple[str, str]] = {}

def _norm(u: str) -> str:
    u = (u or "").strip()
    return "https:" + u if u.startswith("//") else u

def fetch_og_media(url: str, timeout: int = 8) -> tuple[str, str]:
    """Restituisce (og:image, og:video) da una pagina. Video solo se è un file riproducibile."""
    if not url or url in _media_cache:
        return _media_cache.get(url, ("", ""))
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        soup = BeautifulSoup(r.text, "html.parser")
        img_tag = (soup.find("meta", property="og:image")
                   or soup.find("meta", attrs={"name": "og:image"}))
        img = _norm(img_tag.get("content","")) if img_tag else ""
        # og:video:secure_url > og:video:url > og:video — solo mp4/webm diretti
        vid = ""
        for prop in ("og:video:secure_url", "og:video:url", "og:video"):
            vt = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            cand = _norm(vt.get("content","")) if vt else ""
            if cand and re.search(r"\.(mp4|webm|m4v)(\?|$)", cand, re.I):
                vid = cand
                break
        _media_cache[url] = (img, vid)
        return img, vid
    except Exception:
        _media_cache[url] = ("", "")
        return "", ""

def fetch_og_image(url: str, timeout: int = 8) -> str:
    return fetch_og_media(url, timeout)[0]

def _ev(titolo, data, orario, luogo, quartiere, cat, desc, img, social, event_url, video="") -> dict:
    return {
        "titolo":      titolo[:80],
        "data":        data,
        "orario":      orario,
        "luogo":       luogo,
        "quartiere":   quartiere,
        "categoria":   cat,
        "descrizione": desc[:130],
        "vibe":        [],
        "img":         img,
        "video":       video,
        "social":      social or venue_social(luogo),
        "event_url":   event_url,
    }

# ── Scraper 1: firenzespettacolo.it ─────────────────────────────────────────
def scrape_firenzespettacolo(today: date) -> list:
    """Legge le card dalla homepage, segue il link di ogni articolo per la data."""
    events = []
    try:
        r = requests.get("https://www.firenzespettacolo.it/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        # raccoglie massimo 20 link unici agli articoli
        seen_links: set[str] = set()
        links = []
        for a in soup.select("article a[href], .post-list__body a[href], .featured-posts-grid a[href]"):
            href = a.get("href","")
            if href and href.startswith("https://www.firenzespettacolo.it/") and href not in seen_links:
                seen_links.add(href)
                links.append(href)
            if len(links) >= 20:
                break

        def fetch_article(url: str):
            try:
                r2 = requests.get(url, headers=HEADERS, timeout=12)
                s2 = BeautifulSoup(r2.text, "html.parser")
                # Titolo
                h = s2.find(["h1","h2"])
                if not h: return None
                name = h.get_text(strip=True)
                if len(name) < 5: return None
                # Testo principale
                body = s2.find("article") or s2.find("main") or s2
                text = body.get_text(" ", strip=True)
                # Data: "data 15/06/2026" o nel testo
                dt = parse_date(text, today)
                if not dt: return None
                # Immagine
                img_tag = s2.find("meta", property="og:image")
                img = (img_tag.get("content","") if img_tag else "") or ""
                if not img:
                    img_el = s2.find("img", src=re.compile(r"\.jpe?g|\.png|\.webp", re.I))
                    img = (img_el.get("src","") if img_el else "") or ""
                if img and not img.startswith("http"):
                    img = urljoin("https://www.firenzespettacolo.it", img)
                # Luogo
                loc_m = re.search(r'(?:presso|al |alla |a |in )([\w\s\'àèéìòù]+?)(?:\.|,|\n)', text, re.I)
                luogo = loc_m.group(1).strip()[:50] if loc_m else "Firenze"
                cat = classify(name, text)
                return _ev(name, fmt_date(dt), parse_time(text), luogo, "", cat,
                           text[:130], img or random_img(cat), None, url)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=6) as pool:
            for result in pool.map(fetch_article, links):
                if result:
                    events.append(result)
    except Exception as e:
        log(f"  [warn] firenzespettacolo: {e}")
    return events

# ── Scraper 2: theflorentine.net ────────────────────────────────────────────
def scrape_theflorentine(today: date) -> list:
    """Legge le .standard-card e ricava la data dalla URL (anno/mese/giorno)."""
    events = []
    try:
        r = requests.get("https://www.theflorentine.net/events/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select(".standard-card"):
            a = card.find("a", href=True)
            if not a: continue
            url = a["href"]
            # data dalla URL path /2026/06/17/...
            m = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
            if not m: continue
            try:
                dt = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            if dt < today or (dt - today).days > 30: continue
            h = card.find(["h2","h3","h4"])
            if not h: continue
            name = h.get_text(strip=True)
            if len(name) < 5: continue
            img_tag = card.find("img")
            img = ""
            if img_tag:
                img = img_tag.get("src","") or img_tag.get("data-src","")
            text = card.get_text(" ", strip=True)
            cat = classify(name, text)
            social = {"platform": "Instagram", "label": "@theflorentine",
                      "url": "https://www.instagram.com/theflorentine/"}
            events.append(_ev(name, fmt_date(dt), parse_time(text),
                              "Firenze", "", cat, text[:130],
                              img or random_img(cat), social, url))
    except Exception as e:
        log(f"  [warn] theflorentine: {e}")
    return events

# ── Scraper 3: Dice.fm – club, live, nightlife (la fonte più cool) ──────────
def scrape_dice(today: date) -> list:
    """API pubblica Dice.fm: eventi club/live geolocalizzati su Firenze."""
    events = []
    try:
        payload = {"lat": 43.7696, "lng": 11.2558, "radius": 30, "count": 50, "type": "event"}
        r = requests.post("https://api.dice.fm/unified_search",
                          json=payload,
                          headers={**HEADERS, "Content-Type": "application/json"},
                          timeout=15)
        items = []
        for sec in r.json().get("sections", []):
            items += sec.get("items", [])
        for it in items:
            ev = it.get("event") or {}
            name = (ev.get("name") or "").strip()
            if not name:
                continue
            start = ev.get("dates", {}).get("event_start_date", "")
            dt = parse_iso(start[:19]) if start else None
            if not dt:
                ts = ev.get("date_unix")
                dt = datetime.fromtimestamp(ts).date() if ts else None
            if not dt or dt < today or (dt - today).days > 21:
                continue
            venues = ev.get("venues") or [{}]
            luogo = (venues[0].get("name") or "Firenze").strip()
            addr  = (venues[0].get("address") or "")
            # Solo Firenze e dintorni stretti
            if "firenze" not in addr.lower() and "florence" not in addr.lower():
                continue
            time_str = start[11:16] if len(start) > 15 and "T" in start else ""
            imgs = ev.get("images") or {}
            img = imgs.get("landscape") or imgs.get("square") or imgs.get("portrait") or ""
            about = (ev.get("about") or {}).get("description", "") or ""
            desc = re.sub(r"[*#_]", "", about).strip()[:130] or name
            perm = ev.get("perm_name", "")
            event_url = f"https://dice.fm/event/{perm}" if perm else \
                        (ev.get("social_links", {}) or {}).get("event_share", "")
            cat = classify(name, desc)
            if cat == "CULTURA":   # Dice è club/nightlife → default serata
                cat = "SERATA"
            events.append(_ev(name, fmt_date(dt), time_str, luogo, "", cat,
                              desc, img or random_img(cat), None, event_url))
    except Exception as e:
        log(f"  [warn] Dice.fm: {e}")
    return events

# ── Scraper 4: Eventbrite – musica, arte, serate, food ──────────────────────
EB_CATEGORIES = [
    "https://www.eventbrite.it/d/italy--florence/music/",
    "https://www.eventbrite.it/d/italy--florence/arts/",
    "https://www.eventbrite.it/d/italy--florence/nightlife/",
    "https://www.eventbrite.it/d/italy--florence/food-and-drink/",
]

def scrape_eventbrite(today: date) -> list:
    events = []
    for url in EB_CATEGORIES:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(tag.string or "")
                    if isinstance(data, dict) and data.get("@type") == "ItemList":
                        items = [e.get("item", e) for e in data.get("itemListElement", [])]
                    elif isinstance(data, list):
                        items = data
                    else:
                        items = [data]
                    for item in items:
                        if (item.get("@type") or "").lower() != "event": continue
                        ev = _parse_eb(item, today)
                        if ev: events.append(ev)
                except Exception:
                    pass
        except Exception as e:
            log(f"  [warn] Eventbrite {url}: {e}")
    return events

def _parse_eb(item: dict, today: date) -> dict | None:
    name = (item.get("name") or "").strip()
    if not name: return None
    if "online" in (item.get("eventAttendanceMode") or "").lower(): return None
    start_raw = item.get("startDate","")
    dt = parse_iso(start_raw)
    if not dt or dt < today or (dt - today).days > 14: return None
    desc = BeautifulSoup(item.get("description",""), "html.parser").get_text()[:130].strip()
    loc = item.get("location", {})
    luogo = (loc.get("name","") if isinstance(loc, dict) else "").strip()
    addr  = loc.get("address",{}) if isinstance(loc, dict) else {}
    qrt   = (addr.get("addressLocality","") if isinstance(addr, dict) else "").strip()
    if qrt.lower() in ("florence","firenze","fi"): qrt = ""
    if not luogo or luogo.lower() in ("firenze","florence","fi"): return None
    time_str = start_raw[11:16] if len(start_raw) > 15 and "T" in start_raw else ""
    img_raw = item.get("image","")
    if isinstance(img_raw, list): img_raw = img_raw[0] if img_raw else ""
    if isinstance(img_raw, dict): img_raw = img_raw.get("url","")
    img = (img_raw or "").strip()
    event_url = (item.get("url") or "").strip()
    cat = classify(name, desc)
    return _ev(name, fmt_date(dt), time_str, luogo, qrt, cat, desc or name[:130],
               img if img.startswith("http") else random_img(cat),
               None, event_url)

# ── Deduplication ───────────────────────────────────────────────────────────
def deduplicate(events: list) -> list:
    seen, out = set(), []
    for ev in events:
        key = re.sub(r"[^a-z0-9]", "", ev["titolo"].lower())[:30]
        if key not in seen:
            seen.add(key)
            out.append(ev)
    return out

# ── Arricchimento media (og:image + og:video) in parallelo ───────────────────
def enrich_images(events: list) -> list:
    # Visita la pagina evento per: immagine mancante OPPURE video non ancora trovato
    need = [e for e in events
            if e.get("event_url") and
               (not str(e.get("img","")).startswith("http") or not e.get("video"))]
    if need:
        log(f"  Fetch media (img+video) per {len(need)} eventi…")
        def fetch_one(ev):
            img, vid = fetch_og_media(ev["event_url"])
            if img and not str(ev.get("img","")).startswith("http"):
                ev["img"] = img
            if vid and not ev.get("video"):
                ev["video"] = vid
            return ev
        with ThreadPoolExecutor(max_workers=8) as pool:
            for _ in pool.map(fetch_one, need):
                pass

    # Fallback stock per chi resta senza immagine
    video_count = 0
    for ev in events:
        if not str(ev.get("img","")).startswith("http"):
            ev["img"] = random_img(ev.get("categoria","CULTURA"))
        if ev.get("video"):
            video_count += 1
    if video_count:
        log(f"  → {video_count} eventi con video reale")
    return events

# ── Vibe automatici ─────────────────────────────────────────────────────────
VIBE_MAP = {
    "CONCERTO": [["live","musica"],["free","gratis"],["outdoor","all'aperto"],["intimo","piccolo"]],
    "SERATA":   [["aperitivo"],["disco","clubbing"],["rooftop"],["jazz","live"]],
    "MOSTRA":   [["da-non-perdere"],["gratis","free"],["arte-contemporanea"],["storica"]],
    "MERCATO":  [["outdoor"],["vintage"],["artigianato"],["free","gratis"]],
    "SPORT":    [["outdoor"],["free"],["agonistico"],["amatoriale"]],
    "FOOD":     [["street-food"],["vino"],["gourmet"],["family"]],
    "CULTURA":  [["teatro"],["cinema"],["letteratura"],["free"]],
}
def add_vibes(ev: dict) -> dict:
    if not ev.get("vibe"):
        pool = VIBE_MAP.get(ev.get("categoria","CULTURA"), VIBE_MAP["CULTURA"])
        ev["vibe"] = [random.choice(v) for v in random.sample(pool, min(2, len(pool)))]
    return ev

# ── Inject HTML ─────────────────────────────────────────────────────────────
INJECT_START = "// COOLFI_EVENTS_START\n"
INJECT_END   = "// COOLFI_EVENTS_END\n"

def inject_into_html(events: list):
    try:
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        log(f"  [warn] HTML non trovato: {HTML_FILE}")
        return
    blob = INJECT_START + f"let allEvents = {json.dumps(events, ensure_ascii=False, indent=2)};\n" + INJECT_END
    if INJECT_START in html and INJECT_END in html:
        i, j = html.index(INJECT_START), html.index(INJECT_END) + len(INJECT_END)
        html = html[:i] + blob + html[j:]
    else:
        html = html.replace("let allEvents = [];", INJECT_START + "let allEvents = [];\n" + INJECT_END, 1)
        if INJECT_START in html:
            i, j = html.index(INJECT_START), html.index(INJECT_END) + len(INJECT_END)
            html = html[:i] + blob + html[j:]
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  ✓ HTML aggiornato ({len(events)} eventi iniettati)")

# ── Log ─────────────────────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    today = date.today()
    log(f"▶ Cool.fi aggiornamento — {today.isoformat()}")
    all_events: list[dict] = []

    log("  Scraping Dice.fm (club/live/nightlife)…")
    dc = scrape_dice(today)
    log(f"  → {len(dc)} eventi")
    all_events.extend(dc)

    log("  Scraping Eventbrite (musica/arte/serate/food)…")
    eb = scrape_eventbrite(today)
    log(f"  → {len(eb)} eventi")
    all_events.extend(eb)

    log("  Scraping firenzespettacolo.it…")
    fs = scrape_firenzespettacolo(today)
    log(f"  → {len(fs)} eventi")
    all_events.extend(fs)

    log("  Scraping theflorentine.net…")
    tf = scrape_theflorentine(today)
    log(f"  → {len(tf)} eventi")
    all_events.extend(tf)

    all_events = deduplicate(all_events)
    all_events = enrich_images(all_events)

    # ── Curazione coolness ──────────────────────────────────────────────────
    scored = [(cool_score(e), e) for e in all_events]
    kept   = [e for s, e in scored if s >= 1]
    cut    = [e for s, e in scored if s < 1]
    log(f"  🎚  Coolness: {len(kept)} tenuti, {len(cut)} scartati")
    # Ordina per coolness decrescente (i più cool in cima)
    kept.sort(key=lambda e: cool_score(e), reverse=True)
    all_events = [add_vibes(e) for e in kept]

    if not all_events:
        log("  ⚠ Nessun evento cool trovato — mantengo dati esistenti")
        return

    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "city": "Firenze",
        "events": all_events,
    }
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f"  ✓ events.json aggiornato ({len(all_events)} eventi)")
    inject_into_html(all_events)
    log(f"✅ Completato — {len(all_events)} eventi totali")
    _git_push(ROOT)


def _git_push(repo_path: str):
    import subprocess
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "-C", repo_path, "add", "events.json", "cooleventsfi.html"], check=True)
        result = subprocess.run(["git", "-C", repo_path, "diff", "--staged", "--quiet"], capture_output=True)
        if result.returncode == 0:
            log("  git: nessuna modifica")
            return
        subprocess.run(["git", "-C", repo_path, "commit", "-m", f"chore: aggiorna eventi {ts}"], check=True)
        subprocess.run(["git", "-C", repo_path, "push"], check=True)
        log("  ✓ Push su GitHub completato")
    except Exception as e:
        log(f"  [warn] git push fallito: {e}")

if __name__ == "__main__":
    main()
