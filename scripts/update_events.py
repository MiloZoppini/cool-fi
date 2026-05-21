#!/usr/bin/env python3
"""
Cool.fi – aggiornamento automatico eventi Firenze.
Scrapa Eventbrite, firenzespettacolo.it e altre fonti pubbliche.
Aggiorna events.json e inietta i dati nell'HTML per uso locale.
"""
import requests
import json
import os
import re
import sys
import random
from datetime import datetime, date, timedelta
from bs4 import BeautifulSoup

# ── Percorsi ──────────────────────────────────────────────────────────────────
ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_FILE = os.path.join(ROOT, "cooleventsfi.html")
JSON_FILE = os.path.join(ROOT, "events.json")
LOG_FILE  = os.path.expanduser("~/Library/Logs/coolfi/update.log")

# ── Immagini Unsplash per categoria (IDs curati) ──────────────────────────────
IMAGES = {
    "CONCERTO": ["1501386761578-eac5c94b800a","1470225620780-dba8ba36b745","1465847899084-d164df4dedc6","1493225457124-a3eb161ffa5f"],
    "SERATA":   ["1533174072545-7a4b6ad7a6c3","1492684223066-81342ee5ff30","1516450360452-9312f5e86fc7","1574015974293-f6b9e3e2bb5e"],
    "MOSTRA":   ["1577083552431-6e5fd01988ec","1554907984-15263bfd63bd","1518998053901-5348d3961a04","1605350353407-d7a98fe16b21"],
    "MERCATO":  ["1452860606245-08befc0ff44b","1488459716781-31db52582fe9","1472851294608-062f824d29cc","1490750967868-88aa4486c946"],
    "SPORT":    ["1543429776-2782fc8e1acd","1571019613454-1cb2f99b2d8b","1461896836934-ffe607ba8211","1540539234-c14428952f72"],
    "FOOD":     ["1565299585323-38d6b0865b47","1498837167922-ddd27525d352","1414235077428-338989a2e8c0","1504674900247-0877df9cc836"],
    "CULTURA":  ["1489599849927-2ee91cede3ba","1571696769037-c6a7c44c1db6","1524995997946-a1c2e315a42f","1481627834876-b7833e8f5570"],
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

# ── Classificazione categoria da testo ────────────────────────────────────────
def classify(title: str, desc: str = "") -> str:
    t = (title + " " + desc).lower()
    if any(w in t for w in ["concerto","live","musica","band","jazz","classica","orchestra","rock","pop","indie","cantautore","rapper","dj set"]):
        return "CONCERTO"
    if any(w in t for w in ["mostra","esposizione","galleria","arte","dipinti","scultura","photography","fotografia","retrospettiva","museo"]):
        return "MOSTRA"
    if any(w in t for w in ["mercato","fiera","bancarelle","artigianato","hobbistica","antiquariato","collezionismo","brocante"]):
        return "MERCATO"
    if any(w in t for w in ["sport","calcio","basket","tennis","corsa","maratona","atletica","ciclismo","nuoto","pallavolo"]):
        return "SPORT"
    if any(w in t for w in ["food","ristorante","sagra","degustazione","vino","birra","street food","cucina","gastronomia","gelato"]):
        return "FOOD"
    if any(w in t for w in ["serata","club","discoteca","disco","party","aperitivo","cocktail","nightlife","bar"]):
        return "SERATA"
    return "CULTURA"

def random_img(cat: str) -> str:
    return random.choice(IMAGES.get(cat, IMAGES["CULTURA"]))

# ── Formattazione data ─────────────────────────────────────────────────────────
WEEKDAYS_IT = ["lun","mar","mer","gio","ven","sab","dom"]
MONTHS_IT   = ["gen","feb","mar","apr","mag","giu","lug","ago","set","ott","nov","dic"]

def fmt_date(dt: date) -> str:
    return f"{WEEKDAYS_IT[dt.weekday()]} {dt.day}/{dt.month:02d}"

def parse_iso(s: str) -> date | None:
    try:
        return datetime.fromisoformat(s.replace("Z","")).date()
    except Exception:
        return None

# ── Scraper Eventbrite ─────────────────────────────────────────────────────────
def scrape_eventbrite(today: date) -> list:
    events = []
    urls = [
        "https://www.eventbrite.it/d/italy--florence/events/",
        "https://www.eventbrite.it/d/italy--florence/music/",
        "https://www.eventbrite.it/d/italy--florence/arts/",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(tag.string or "")
                    # Gestisci ItemList (struttura Eventbrite)
                    if isinstance(data, dict) and data.get("@type") == "ItemList":
                        raw_items = [e.get("item", e) for e in data.get("itemListElement", [])]
                    elif isinstance(data, list):
                        raw_items = data
                    else:
                        raw_items = [data]

                    for item in raw_items:
                        if (item.get("@type") or "").lower() != "event":
                            continue
                        ev = _parse_jsonld_event(item, today)
                        if ev:
                            events.append(ev)
                except Exception:
                    pass
        except Exception as e:
            log(f"  [warn] Eventbrite {url}: {e}")
    return events

def _parse_jsonld_event(item: dict, today: date) -> dict | None:
    name = (item.get("name") or "").strip()
    if not name:
        return None

    # Salta eventi online
    mode = (item.get("eventAttendanceMode") or "").lower()
    if "online" in mode:
        return None

    start_raw = item.get("startDate","")
    start_dt  = parse_iso(start_raw)
    if not start_dt or start_dt < today:
        return None
    if (start_dt - today).days > 14:
        return None

    desc    = BeautifulSoup(item.get("description",""), "html.parser").get_text()[:130].strip()
    loc_obj = item.get("location", {})
    luogo   = (loc_obj.get("name","") if isinstance(loc_obj, dict) else "").strip()
    addr    = loc_obj.get("address",{}) if isinstance(loc_obj, dict) else {}
    quartiere = (addr.get("addressLocality","") if isinstance(addr, dict) else "").strip()
    if quartiere.lower() in ("florence","firenze","fi"):
        quartiere = ""

    # Salta eventi senza venue specifico (es. webinar)
    if not luogo or luogo.lower() in ("firenze","florence","fi"):
        return None

    # Estrai orario se disponibile (formato ISO: 2026-05-22T21:00:00)
    time_str = start_raw[11:16] if len(start_raw) > 15 and "T" in start_raw else ""

    cat = classify(name, desc)

    return {
        "titolo":    name[:80],
        "data":      fmt_date(start_dt),
        "orario":    time_str,
        "luogo":     luogo,
        "quartiere": quartiere,
        "categoria": cat,
        "descrizione": desc or name[:130],
        "vibe":      [],
        "img":       random_img(cat),
    }

# ── Scraper firenzespettacolo.it ───────────────────────────────────────────────
def scrape_firenzespettacolo(today: date) -> list:
    events = []
    try:
        r = requests.get("https://www.firenzespettacolo.it/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        # Cerca articoli/card evento
        for card in soup.select("article, .event-item, .evento, [class*='event']")[:30]:
            title_tag = card.find(["h2","h3","h4","a"])
            if not title_tag:
                continue
            name = title_tag.get_text(strip=True)
            if len(name) < 5:
                continue
            cat = classify(name)
            # Cerca data nel testo
            text = card.get_text(" ", strip=True)
            dt_match = re.search(r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?", text)
            if dt_match:
                day = int(dt_match.group(1))
                month = int(dt_match.group(2))
                year = today.year
                try:
                    ev_date = date(year, month, day)
                    if ev_date < today:
                        ev_date = date(year+1, month, day)
                    if (ev_date - today).days > 14:
                        continue
                    data_str = fmt_date(ev_date)
                except ValueError:
                    data_str = "in corso"
            else:
                data_str = "in corso"

            loc = ""
            for w in ["teatro","piazza","palazzo","villa","giardino","museo","chiesa","arena","auditorium","sala"]:
                m = re.search(rf"\b{w}\s+[\w\s']+", text, re.I)
                if m:
                    loc = m.group(0).strip()[:50]
                    break

            events.append({
                "titolo":    name[:80],
                "data":      data_str,
                "orario":    "",
                "luogo":     loc or "Firenze",
                "quartiere": "",
                "categoria": cat,
                "descrizione": text[:130].strip(),
                "vibe":      [],
                "img":       random_img(cat),
            })
    except Exception as e:
        log(f"  [warn] firenzespettacolo: {e}")
    return events

# ── Scraper visitflorence.com ──────────────────────────────────────────────────
def scrape_visitflorence(today: date) -> list:
    events = []
    try:
        r = requests.get("https://www.visitflorence.com/events/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select(".event, article, [class*='event']")[:20]:
            title_tag = card.find(["h2","h3","h4","a"])
            if not title_tag:
                continue
            name = title_tag.get_text(strip=True)
            if len(name) < 5 or name.lower() in ("events","eventi"):
                continue
            cat = classify(name)
            text = card.get_text(" ", strip=True)
            events.append({
                "titolo":    name[:80],
                "data":      "in corso",
                "orario":    "",
                "luogo":     "Firenze",
                "quartiere": "",
                "categoria": cat,
                "descrizione": text[:130].strip(),
                "vibe":      [],
                "img":       random_img(cat),
            })
    except Exception as e:
        log(f"  [warn] visitflorence: {e}")
    return events

# ── Deduplicazione ─────────────────────────────────────────────────────────────
def deduplicate(events: list) -> list:
    seen = set()
    out  = []
    for ev in events:
        key = re.sub(r"[^a-z0-9]", "", ev["titolo"].lower())[:30]
        if key not in seen:
            seen.add(key)
            out.append(ev)
    return out

# ── Aggiungi vibe automatici ───────────────────────────────────────────────────
VIBE_MAP = {
    "CONCERTO": [["live","musica"],["free","gratis"],["outdoor","all'aperto"],["intimo","piccolo"]],
    "SERATA":   [["aperitivo"],["disco","clubbing"],["rooftop"],["jazz","live"]],
    "MOSTRA":   [["must-see","da-non-perdere"],["gratis","free"],["arte-contemporanea"],["storica"]],
    "MERCATO":  [["outdoor"],["vintage"],["artigianato"],["free","gratis"]],
    "SPORT":    [["outdoor"],["free"],["agonistico"],["amatoriale"]],
    "FOOD":     [["street-food"],["vino"],["gourmet"],["family"]],
    "CULTURA":  [["teatro"],["cinema"],["letteratura"],["free"]],
}

def add_vibes(ev: dict) -> dict:
    if not ev.get("vibe"):
        cat = ev.get("categoria","CULTURA")
        pool = VIBE_MAP.get(cat, VIBE_MAP["CULTURA"])
        ev["vibe"] = [random.choice(v) for v in random.sample(pool, min(2, len(pool)))]
    return ev

# ── Aggiorna HTML (inietta dati per uso locale) ───────────────────────────────
INJECT_START = "// COOLFI_EVENTS_START\n"
INJECT_END   = "// COOLFI_EVENTS_END\n"

def inject_into_html(events: list):
    try:
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        log(f"  [warn] HTML non trovato: {HTML_FILE}")
        return

    json_str = json.dumps(events, ensure_ascii=False, indent=2)
    new_block = (
        INJECT_START +
        f"let allEvents = {json_str};\n" +
        INJECT_END
    )

    if INJECT_START in html and INJECT_END in html:
        i = html.index(INJECT_START)
        j = html.index(INJECT_END) + len(INJECT_END)
        html = html[:i] + new_block + html[j:]
    else:
        # Prima run: inserisci il marker nel posto giusto
        html = html.replace("let allEvents = [];", INJECT_START + "let allEvents = [];\n" + INJECT_END, 1)
        if INJECT_START in html:
            i = html.index(INJECT_START)
            j = html.index(INJECT_END) + len(INJECT_END)
            html = html[:i] + new_block + html[j:]

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  ✓ HTML aggiornato ({len(events)} eventi iniettati)")

# ── Log ────────────────────────────────────────────────────────────────────────
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

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    today = date.today()
    log(f"▶ Cool.fi aggiornamento — {today.isoformat()}")

    all_events = []

    log("  Scraping Eventbrite…")
    eb = scrape_eventbrite(today)
    log(f"  → {len(eb)} eventi da Eventbrite")
    all_events.extend(eb)

    log("  Scraping firenzespettacolo.it…")
    fs = scrape_firenzespettacolo(today)
    log(f"  → {len(fs)} eventi da firenzespettacolo")
    all_events.extend(fs)

    log("  Scraping visitflorence.com…")
    vf = scrape_visitflorence(today)
    log(f"  → {len(vf)} eventi da visitflorence")
    all_events.extend(vf)

    all_events = deduplicate(all_events)
    all_events = [add_vibes(e) for e in all_events]

    if not all_events:
        log("  ⚠ Nessun evento trovato — mantengo dati esistenti")
        return

    # Salva events.json
    output = {
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "city": "Firenze",
        "events": all_events,
    }
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    log(f"  ✓ events.json aggiornato ({len(all_events)} eventi)")

    # Inietta nel HTML per uso locale
    inject_into_html(all_events)

    log(f"✅ Completato — {len(all_events)} eventi totali")

    # Push su GitHub Pages
    _git_push(ROOT)


def _git_push(repo_path: str):
    import subprocess
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "-C", repo_path, "add", "events.json", "cooleventsfi.html"], check=True)
        result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--staged", "--quiet"],
            capture_output=True
        )
        if result.returncode == 0:
            log("  git: nessuna modifica da committare")
            return
        subprocess.run(["git", "-C", repo_path, "commit", "-m", f"chore: aggiorna eventi {ts}"], check=True)
        subprocess.run(["git", "-C", repo_path, "push"], check=True)
        log("  ✓ Push su GitHub completato")
    except Exception as e:
        log(f"  [warn] git push fallito: {e}")

if __name__ == "__main__":
    main()
