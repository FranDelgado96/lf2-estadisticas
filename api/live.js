// Marcadores en directo de la FEB para la web (LF2 y LF Challenge).
// Lee el mismo servicio público que usa la página de partido de feb.es y devuelve solo lo necesario.
let TOKEN = null, TOKEN_AT = 0;
const UA = { "user-agent": "Mozilla/5.0 (lf2-estadisticas)" };

async function getToken(force) {
  if (!force && TOKEN && Date.now() - TOKEN_AT < 30 * 60e3) return TOKEN;
  const html = await (await fetch("https://www.feb.es/competiciones/partido/2524718", { headers: UA })).text();
  const m = html.match(/id="_ctl0_token"\s+value="([^"]+)"/) || html.match(/name="_ctl0:token"[^>]*value="([^"]+)"/);
  if (!m) throw new Error("token no encontrado");
  TOKEN = m[1]; TOKEN_AT = Date.now();
  return TOKEN;
}

const N = x => Number(x) || 0;
function rows(team) {
  return (team && team.PLAYER || []).map(p => ({
    id: String(p.id || ""), st: p.inn === "1" || p.sta === "1", d: N(p.no), name: p.name, min: Math.round(N(p.min) / 60 * 100) / 100, pts: N(p.pts),
    t2: [N(p.p2m), N(p.p2a)], t3: [N(p.p3m), N(p.p3a)], tl: [N(p.p1m), N(p.p1a)], ro: N(p.ro), rd: N(p.rd), ast: N(p.assist),
    rob: N(p.st), per: N(p.to), tap: N(p.bs), fc: N(p.pf), fr: N(p.rf), va: N(p.val)
  }));
}

async function one(id, tok) {
  const r = await fetch("https://intrafeb.feb.es/LiveStats.API/api/v1/BoxScore/" + id, { headers: { ...UA, Authorization: "Bearer " + tok } });
  if (r.status === 404) return null;
  if (r.status === 401) throw Object.assign(new Error("401"), { auth: true });
  if (!r.ok) return null;
  const j = await r.json(); const H = j && j.HEADER;
  if (!H || !H.TEAM) return null;
  const fin = /FINISH|FINAL|END/i.test(H.statusText || "") || H.time === "FINAL";
  const live = /PROGRESS|LIVE|HALF|BREAK/i.test(H.statusText || "");
  if (!fin && !live) return null;
  const q = N(H.quarter);
  const status = fin ? "FINAL" : ((q <= 4 ? q + "º cuarto" : "Prórroga") + (H.time ? " · " + H.time : ""));
  return {
    status, hs: N(H.TEAM[0].pts), as: N(H.TEAM[1].pts),
    quarters: ((H.QUARTERS && H.QUARTERS.QUARTER) || []).map(x => ({ q: N(x.n), h: N(x.scoreA), a: N(x.scoreB) })),
    teams: [{ rows: rows(j.BOXSCORE && j.BOXSCORE.TEAM && j.BOXSCORE.TEAM[0]) }, { rows: rows(j.BOXSCORE && j.BOXSCORE.TEAM && j.BOXSCORE.TEAM[1]) }],
    at: Date.now(), source: "api"
  };
}

module.exports = async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Cache-Control", "public, s-maxage=20, stale-while-revalidate=20");
  const ids = String((req.query && req.query.ids) || "").split(",").map(s => s.trim()).filter(s => /^\d{5,9}$/.test(s)).slice(0, 20);
  const games = {};
  if (ids.length) {
    try {
      let tok = await getToken(false);
      const run = () => Promise.all(ids.map(async id => { const g = await one(id, tok); if (g) games[id] = g; }));
      try { await run(); } catch (e) { if (!e.auth) throw e; tok = await getToken(true); await run(); }
    } catch (e) {
      res.status(502).json({ error: String(e.message || e), games });
      return;
    }
  }
  res.status(200).json({ at: Date.now(), games });
};
