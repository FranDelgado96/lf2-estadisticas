#!/usr/bin/env python3
"""Actualizador automático de la web de estadísticas de Liga Femenina Challenge 26/27.

Uso (desde una sesión programada):
  python3 lf2_tool.py targets --data DIR
      Lista los febId de partidos que ya han empezado y aún no tienen estadísticas guardadas.
  python3 lf2_tool.py build --data DIR --id FEBID --box FILE [--out OUT]
      Valida el acta copiada de la FEB (formato G#.../L|.../V|...) y genera:
        OUT/FEBID/writes.json  -> escrituras para ArtifactData batch (jugadoras nuevas, partido o directo)
        OUT/FEBID/acta.pdf     -> PDF de la estadística (solo si el partido ha terminado)
        OUT/FEBID/result.json  -> resumen (estado final/directo, marcador, verificación)
  python3 lf2_tool.py acta --id FEBID --asset ASSETID --size BYTES --name NAME [--out OUT]
      Genera OUT/FEBID/acta_write.json con el documento actas/FEBID.

DIR es la carpeta donde ArtifactData guardó las colecciones (schedule/, games/, players/).
"""
import argparse, glob, json, os, re, sys, time, unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
TEAMS = {"A": ["Club Joventut Badalona", "Al-Qázeres Extremadura", "Fustecma NBF Castelló", "Domusa Teknik ISB", "Mipelletymas BF León", "SPAR Gran Canaria", "La Laguna Toyota Adareva", "Melilla Ciudad del Deporte La Salle", "MCR Lima-Horta Barcelona", "Sparking Truth Maristas", "Bosonit Unibasket", "Unicaja Mijas", "Oses Construcción", "Sevilla Cajasol Gardenstore", "Valencia Basket", "Recoletas Zamora"]}


def norm(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z]", "", s.upper())


def toks(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return sorted(t for t in re.split(r"[^A-Z]+", s.upper()) if t)


OVER = {"CLUBJOVENTUTBADALONA": "Club Joventut Badalona", "CBALQAZERESEXTREMADURA": "Al-Qázeres Extremadura", "FUSTECMANBFCASTELLO": "Fustecma NBF Castelló", "DOMUSATEKNIKISB": "Domusa Teknik ISB", "MIPELLETYMASBFLEON": "Mipelletymas BF León", "SPARGRANCANARIA": "SPAR Gran Canaria", "LALAGUNATOYOTAADAREVA": "La Laguna Toyota Adareva", "MELILLACIUDADDELDEPORTELASALLE": "Melilla Ciudad del Deporte La Salle", "MCRLIMAHORTABARCELONA": "MCR Lima-Horta Barcelona", "SPARKINGTRUTHMARISTAS": "Sparking Truth Maristas", "BOSONITUNIBASKET": "Bosonit Unibasket", "UNICAJAMIJAS": "Unicaja Mijas", "OSESCONSTRUCCION": "Oses Construcción", "SEVILLACAJASOLGARDENSTOREBALONCESTO": "Sevilla Cajasol Gardenstore", "VALENCIABASKET": "Valencia Basket", "RECOLETASZAMORA": "Recoletas Zamora"}
BYNORM = {norm(t): t for g in TEAMS for t in TEAMS[g]}


def team(name):
    k = norm(name)
    return OVER.get(k) or BYNORM.get(k)


def load_dir(d, coll):
    out = []
    for p in glob.glob(os.path.join(d, coll, "*.json")):
        x = json.load(open(p, encoding="utf8"))
        doc_id = os.path.basename(p)[:-5]
        if isinstance(x, dict) and "data" in x and isinstance(x["data"], dict):
            data = dict(x["data"]); doc_id = x.get("id", doc_id)
        else:
            data = dict(x)
        data["_id"] = doc_id
        out.append(data)
    return out


def schedule(d):
    games = []
    for s in load_dir(d, "schedule"):
        for e in s.get("games", []):
            games.append(dict(e, group=s.get("group") or s["_id"]))
    return games


def start_of(e):
    if not e.get("date"):
        return None
    return datetime.fromisoformat(f"{e['date']}T{e.get('time') or '12:00'}:00").replace(tzinfo=TZ)


def cmd_targets(a):
    now = datetime.now(TZ)
    done = {g.get("febId") for g in load_dir(a.data, "games")}
    out = []
    for e in schedule(a.data):
        st = start_of(e)
        if e["id"] in done or e.get("status") == "final" or not st or not e.get("time"):
            continue
        if st - timedelta(minutes=5) <= now <= st + timedelta(days=4):
            out.append(e["id"])
    print(json.dumps(out))


def mins(s):
    m, x = s.split(":")
    return round(int(m) + int(x) / 60, 2)


def parse_box(path):
    head = None; rows = {"L": [], "V": []}
    for line in open(path, encoding="utf8").read().strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("G#"):
            f = line.split("#"); head = {"home": f[1], "hs": int(f[2]), "away": f[3], "as": int(f[4])}
            continue
        f = line.split("|")
        if f[0] not in rows or len(f) < 17:
            continue
        t2, t3, tl = (x.split("/") for x in f[5:8])
        b = {"d": int(f[1]), "name": re.sub(r"\s+", " ", f[2]).strip(), "min": mins(f[3]), "pts": int(f[4]),
             "t2m": int(t2[0]), "t2a": int(t2[1]), "t3m": int(t3[0]), "t3a": int(t3[1]), "tlm": int(tl[0]), "tla": int(tl[1]),
             "ro": int(f[8]), "rd": int(f[9]), "ast": int(f[10]), "rob": int(f[11]), "per": int(f[12]), "tap": int(f[13]),
             "fc": int(f[14]), "fr": int(f[15]), "va": int(f[16])}
        rows[f[0]].append(b)
    if not head:
        raise SystemExit("ERROR: falta la línea G# con el marcador")
    return head, rows


def title(full):
    t = re.sub(r"\s+", " ", full).title()
    return re.sub(r"\b(De|Del|La|Las|Los|Y|Dos)\b", lambda m: m.group(0).lower(), t)


def cmd_build(a):
    now = datetime.now(TZ)
    sched = {e["id"]: e for e in schedule(a.data)}
    e = sched.get(a.id)
    if not e:
        raise SystemExit(f"ERROR: el partido {a.id} no está en el calendario")
    head, rows = parse_box(a.box)
    problems = []
    if team(head["home"]) != e["home"] or team(head["away"]) != e["away"]:
        problems.append(f"equipos no coinciden: {head['home']} / {head['away']} frente a {e['home']} / {e['away']}")
    for side, k in (("L", "hs"), ("V", "as")):
        for b in rows[side]:
            if b["pts"] != 2 * b["t2m"] + 3 * b["t3m"] + b["tlm"]:
                problems.append(f"puntos incoherentes en {b['name']}")
    sums = {s: sum(b["pts"] for b in rows[s]) for s in rows}
    minutes = {s: sum(b["min"] for b in rows[s]) for s in rows}
    st = start_of(e)
    complete = rows["L"] and rows["V"] and sums["L"] == head["hs"] and sums["V"] == head["as"] and head["hs"] + head["as"] > 0 and min(minutes.values()) >= 199.5
    is_final = bool(complete and st and now >= st + timedelta(minutes=95) and head["hs"] != head["as"])
    players = load_dir(a.data, "players")
    by_team = {}
    for p in players:
        by_team.setdefault(p.get("team"), []).append(p)
    writes, new_players = [], []
    box = {"home": {}, "away": {}}
    for side, key in (("L", "home"), ("V", "away")):
        tm = e[key]
        for b in rows[side]:
            sur, _, name = b["name"].partition(",")
            full = (name.strip() + " " + sur.strip()).strip()
            pid = None
            for r in by_team.get(tm, []):
                if norm(r.get("name", "")) == norm(full) or toks(r.get("name", "")) == toks(full):
                    pid = r["_id"]; break
            if not pid:
                pid = f"auto-{a.id}-{key[0]}{b['d']}"
                doc = {"name": title(full), "dorsal": b["d"], "pos": "", "team": tm, "source": "acta", "created": int(time.time() * 1000)}
                new_players.append(doc["name"])
                by_team.setdefault(tm, []).append(dict(doc, _id=pid))
                writes.append({"op": "set", "collection": "players", "doc_id": pid, "data": doc})
            if pid in box[key]:
                problems.append(f"jugadora repetida {b['name']}")
            box[key][pid] = {k: v for k, v in b.items() if k != "name"}
    out = os.path.join(a.out, a.id); os.makedirs(out, exist_ok=True)
    live_rows = lambda side: [{"st": False, "d": b["d"], "name": b["name"], "min": b["min"], "pts": b["pts"], "t2": [b["t2m"], b["t2a"]], "t3": [b["t3m"], b["t3a"]], "tl": [b["tlm"], b["tla"]], "ro": b["ro"], "rd": b["rd"], "ast": b["ast"], "rob": b["rob"], "per": b["per"], "tap": b["tap"], "fc": b["fc"], "fr": b["fr"], "va": b["va"]} for b in rows[side]]
    live = {"status": "FINAL" if is_final else "En juego", "hs": head["hs"], "as": head["as"], "quarters": [], "teams": [{"rows": live_rows("L")}, {"rows": live_rows("V")}], "at": int(time.time() * 1000), "source": "programado"}
    if problems and is_final:
        is_final = False
    if is_final:
        game = {"group": e["group"], "jornada": e["j"], "date": e["date"], "home": e["home"], "away": e["away"], "hs": head["hs"], "as": head["as"], "box": box, "source": "feb", "febId": a.id, "updated": int(time.time() * 1000)}
        writes.append({"op": "set", "collection": "games", "doc_id": "feb-g-" + a.id, "data": game})
        make_pdf(game, e, {pid: n for pid, n in ((p["_id"], p.get("name")) for v in by_team.values() for p in v)}, os.path.join(out, "acta.pdf"))
    elif not problems and head["hs"] + head["as"] > 0:
        writes = [w for w in writes if w["collection"] != "players"]
    writes.append({"op": "set", "collection": "live", "doc_id": a.id, "data": live})
    json.dump(writes, open(os.path.join(out, "writes.json"), "w", encoding="utf8"), ensure_ascii=False)
    res = {"id": a.id, "final": is_final, "hs": head["hs"], "as": head["as"], "home": e["home"], "away": e["away"], "problems": problems, "new_players": new_players if is_final else [], "pdf": os.path.join(out, "acta.pdf") if is_final else None, "writes": os.path.join(out, "writes.json"), "pdf_name": f"LFC_J{e['j']:02d}_{a.id} (estadística FEB).pdf"}
    json.dump(res, open(os.path.join(out, "result.json"), "w", encoding="utf8"), ensure_ascii=False)
    print(json.dumps(res, ensure_ascii=False))


def make_pdf(g, e, names, fn):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    reg = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf"; bold = "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"
    F, FB = ("DV", "DVB") if os.path.exists(reg) else ("Helvetica", "Helvetica-Bold")
    if F == "DV":
        pdfmetrics.registerFont(TTFont("DV", reg)); pdfmetrics.registerFont(TTFont("DVB", bold))
    INK = colors.HexColor("#14213a"); ACC = colors.HexColor("#d9541e"); LINE = colors.HexColor("#d9dde5")
    H = ParagraphStyle("h", fontName=FB, fontSize=16, textColor=INK, leading=19)
    S = ParagraphStyle("s", fontName=F, fontSize=9, textColor=colors.HexColor("#5d6779"), leading=12)
    T = ParagraphStyle("t", fontName=FB, fontSize=11, textColor=INK, leading=14, spaceBefore=8)
    doc = SimpleDocTemplate(fn, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=26, bottomMargin=26, title=f"Estadística J{g['jornada']} {g['home']} - {g['away']}")
    mmss = lambda m: f"{round(m * 60) // 60}:{round(m * 60) % 60:02d}"
    el = [Paragraph(f"{g['home']} <font color='#d9541e'>{g['hs']} – {g['as']}</font> {g['away']}", H),
          Paragraph(f"Liga Femenina Challenge · Temporada 2026/27 · Jornada {g['jornada']} · {g['date'][8:10]}/{g['date'][5:7]}/{g['date'][:4]} · {e.get('venue', '')}", S),
          Paragraph(f"Estadística oficial del partido según la FEB (partido {g['febId']}). Documento generado a partir de los datos publicados en feb.es; no sustituye al acta firmada.", S)]
    for side, tname in (("home", g["home"]), ("away", g["away"])):
        bx = g["box"][side]; ids = sorted(bx, key=lambda i: bx[i]["d"])
        rows = [["D", "Jugadora", "MIN", "PTS", "T2", "T3", "TL", "RO", "RD", "REB", "AST", "ROB", "PER", "TAP", "FC", "FR", "VAL"]]
        tot = {k: 0 for k in ["min", "pts", "t2m", "t2a", "t3m", "t3a", "tlm", "tla", "ro", "rd", "ast", "rob", "per", "tap", "fc", "fr", "va"]}
        for i in ids:
            b = bx[i]
            for k in tot: tot[k] += b[k]
            rows.append([b["d"], names.get(i, i), mmss(b["min"]), b["pts"], f"{b['t2m']}/{b['t2a']}", f"{b['t3m']}/{b['t3a']}", f"{b['tlm']}/{b['tla']}", b["ro"], b["rd"], b["ro"] + b["rd"], b["ast"], b["rob"], b["per"], b["tap"], b["fc"], b["fr"], b["va"]])
        rows.append(["", "Total", round(tot["min"]), tot["pts"], f"{tot['t2m']}/{tot['t2a']}", f"{tot['t3m']}/{tot['t3a']}", f"{tot['tlm']}/{tot['tla']}", tot["ro"], tot["rd"], tot["ro"] + tot["rd"], tot["ast"], tot["rob"], tot["per"], tot["tap"], tot["fc"], tot["fr"], tot["va"]])
        t = Table(rows, colWidths=[24, 190] + [40] * 15, repeatRows=1)
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), F, 8.5), ("FONT", (0, 0), (-1, 0), FB, 8), ("FONT", (0, -1), (-1, -1), FB, 8.5),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#5d6779")), ("LINEBELOW", (0, 0), (-1, 0), 1, INK), ("LINEBELOW", (0, 1), (-1, -2), 0.3, LINE), ("LINEABOVE", (0, -1), (-1, -1), 1, INK),
                               ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("ALIGN", (0, 0), (0, -1), "RIGHT"), ("TEXTCOLOR", (3, 1), (3, -1), ACC), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("TOPPADDING", (0, 0), (-1, -1), 2.5)]))
        el += [Paragraph(tname, T), t]
    el += [Spacer(1, 8), Paragraph("D: dorsal · T2/T3/TL: anotados/intentados · RO/RD: rebotes ofensivos/defensivos · ROB: robos · PER: pérdidas · TAP: tapones · FC/FR: faltas cometidas/recibidas · VAL: valoración. Fuente: www.feb.es", S)]
    doc.build(el)


def cmd_acta(a):
    out = os.path.join(a.out, a.id); os.makedirs(out, exist_ok=True)
    w = [{"op": "set", "collection": "actas", "doc_id": a.id, "data": {"files": [{"id": a.asset, "name": a.name, "type": "application/pdf", "size": int(a.size), "at": int(time.time() * 1000), "source": "feb"}]}}]
    json.dump(w, open(os.path.join(out, "acta_write.json"), "w", encoding="utf8"), ensure_ascii=False)
    print(os.path.join(out, "acta_write.json"))


def cmd_sched_targets(a):
    today = datetime.now(TZ).date()
    done = {g.get("febId") for g in load_dir(a.data, "games")}
    out = []
    for e in schedule(a.data):
        if e["id"] in done or e.get("status") == "final":
            continue
        if e.get("status") == "tbd" or not e.get("date"):
            out.append(e["id"]); continue
        d = datetime.fromisoformat(e["date"]).date()
        if today - timedelta(days=3) <= d <= today + timedelta(days=21):
            out.append(e["id"])
    print(json.dumps(out))


def cmd_sched_update(a):
    """FILE: una línea por partido 'FEBID|F#<fecha>#<pista>#...' tal como la devuelve WebFetch."""
    info = {}
    for line in open(a.fechas, encoding="utf8"):
        line = line.strip()
        if "|" not in line or "F#" not in line:
            continue
        fid, rest = line.split("|", 1)
        f = rest[rest.index("F#") + 2:].split("#")
        info[fid.strip()] = f[0].strip()
    docs = {s["_id"]: s for s in load_dir(a.data, "schedule")}
    changed = []
    for gid, doc in docs.items():
        dirty = False
        for e in doc.get("games", []):
            raw = info.get(e["id"])
            if raw is None:
                continue
            m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s*-\s*(\d{1,2}:\d{2})", raw)
            if m:
                date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"; tm = m.group(4).zfill(5)
                if (e.get("date"), e.get("time"), e.get("status")) != (date, tm, "scheduled"):
                    changed.append({"id": e["id"], "antes": f"{e.get('date')} {e.get('time')}", "ahora": f"{date} {tm}", "partido": f"{e['home']} - {e['away']}"})
                    e.update(date=date, time=tm, status="scheduled"); dirty = True
            elif re.search(r"determinar", raw, re.I):
                if e.get("status") != "tbd":
                    changed.append({"id": e["id"], "antes": f"{e.get('date')} {e.get('time')}", "ahora": "por determinar", "partido": f"{e['home']} - {e['away']}"})
                    e.update(date="", time="", status="tbd"); dirty = True
        if dirty:
            doc = {k: v for k, v in doc.items() if k != "_id"}
            doc["updated"] = datetime.now(TZ).strftime("%Y-%m-%d")
            os.makedirs(a.out, exist_ok=True)
            json.dump(doc, open(os.path.join(a.out, f"schedule-{gid}.json"), "w", encoding="utf8"), ensure_ascii=False)
    print(json.dumps({"changed": changed, "files": sorted(glob.glob(os.path.join(a.out, "schedule-*.json")))}, ensure_ascii=False))


def cmd_bundle(a):
    """Genera SITE/data/bundle.json para la versión pública (Vercel) a partir de las colecciones guardadas en DIR.
    Los PDF deben estar (o copiarse con --pdf FEBID=RUTA) en SITE/actas/FEBID.pdf."""
    import shutil
    os.makedirs(os.path.join(a.site, "data"), exist_ok=True); os.makedirs(os.path.join(a.site, "actas"), exist_ok=True)
    for spec in a.pdf or []:
        fid, path = spec.split("=", 1); shutil.copyfile(path, os.path.join(a.site, "actas", fid + ".pdf"))
    strip = lambda d: {k: v for k, v in d.items() if k != "_id"}
    players = [dict(strip(p), id=p["_id"]) for p in load_dir(a.data, "players")]
    games = [dict(strip(g), id=g["_id"]) for g in load_dir(a.data, "games")]
    sched = {s["_id"]: strip(s) for s in load_dir(a.data, "schedule")}
    # actas que falten en la web pública: se generan a partir de la estadística guardada
    sched_by_id = {e["id"]: e for e in schedule(a.data)}
    names = {p["_id"]: p.get("name") for p in load_dir(a.data, "players")}
    for g in load_dir(a.data, "games"):
        fid = g.get("febId")
        if not fid or not g.get("box"):
            continue
        pdf = os.path.join(a.site, "actas", fid + ".pdf")
        if not os.path.exists(pdf):
            try:
                make_pdf(g, sched_by_id.get(fid, {}), names, pdf)
            except Exception as ex:
                print("aviso: no se pudo generar el acta", fid, ex, file=sys.stderr)
    actas = {}
    for d in load_dir(a.data, "actas"):
        fid = d["_id"]; pdf = os.path.join(a.site, "actas", fid + ".pdf")
        files = []
        for f in d.get("files", []):
            f = dict(f)
            if f.get("type") == "application/pdf" and os.path.exists(pdf):
                f["url"] = "actas/" + fid + ".pdf"
            elif not f.get("url"):
                continue
            files.append(f)
        if files:
            actas[fid] = {"files": files}
    for g in load_dir(a.data, "games"):
        fid = g.get("febId"); pdf = os.path.join(a.site, "actas", (fid or "x") + ".pdf")
        if fid and fid not in actas and os.path.exists(pdf):
            actas[fid] = {"files": [{"id": "pub-" + fid, "name": f"Acta {fid} (estadística FEB).pdf", "type": "application/pdf", "size": os.path.getsize(pdf), "url": "actas/" + fid + ".pdf", "source": "feb"}]}
    live = {d["_id"]: strip(d) for d in load_dir(a.data, "live")}
    b = {"generated": int(time.time() * 1000), "players": players, "games": games, "schedule": sched, "actas": actas, "live": live}
    json.dump(b, open(os.path.join(a.site, "data", "bundle.json"), "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({"players": len(players), "games": len(games), "actas": len(actas), "live": len(live)}))


def cmd_site(a):
    """Envuelve la página del artifact (sin <head>) en un documento HTML completo para Vercel."""
    body = open(a.html, encoding="utf8").read()
    head = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="description" content="Clasificación, calendario, resultados, actas y estadísticas de Liga Femenina Challenge de baloncesto 2026/27.">'
            '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
            '</head><body>')
    os.makedirs(a.out, exist_ok=True)
    open(os.path.join(a.out, "index.html"), "w", encoding="utf8").write(head + body + "</body></html>")
    open(os.path.join(a.out, "vercel.json"), "w").write(json.dumps({"headers": [{"source": "/data/(.*)", "headers": [{"key": "Cache-Control", "value": "no-store"}]}]}, indent=2))
    print(os.path.join(a.out, "index.html"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("targets"); p.add_argument("--data", required=True)
    p = sp.add_parser("build"); p.add_argument("--data", required=True); p.add_argument("--id", required=True); p.add_argument("--box", required=True); p.add_argument("--out", default="lfcout")
    p = sp.add_parser("acta"); p.add_argument("--id", required=True); p.add_argument("--asset", required=True); p.add_argument("--size", required=True); p.add_argument("--name", required=True); p.add_argument("--out", default="lfcout")
    p = sp.add_parser("sched-targets"); p.add_argument("--data", required=True)
    p = sp.add_parser("sched-update"); p.add_argument("--data", required=True); p.add_argument("--fechas", required=True); p.add_argument("--out", default="lfcsched")
    p = sp.add_parser("bundle"); p.add_argument("--data", required=True); p.add_argument("--site", required=True); p.add_argument("--pdf", action="append")
    p = sp.add_parser("site"); p.add_argument("--html", required=True); p.add_argument("--out", required=True)
    a = ap.parse_args()
    {"targets": cmd_targets, "build": cmd_build, "acta": cmd_acta, "sched-targets": cmd_sched_targets, "sched-update": cmd_sched_update, "bundle": cmd_bundle, "site": cmd_site}[a.cmd](a)
