"""Render output/dashboard.html: an interactive single-page dashboard.

The page renders entirely from predictions data: a snapshot is embedded at
build time, then the page re-fetches predictions.json when served, and the
Refresh button POSTs /refresh (handled by serve.py) to run the fast update.
All kickoff times display in AEST.

Run: python3 dashboard.py
"""

import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0A0A0A; color: #A1A1AA; font-size: 15px; line-height: 1.6;
  font-family: Inter, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 48px 28px 80px; }
.label { display: flex; align-items: center; gap: 10px; text-transform: uppercase;
  letter-spacing: 0.18em; font-size: 12px; font-weight: 500; color: #2DD4BF; }
.label .rule { width: 26px; height: 2px; background: #2DD4BF; }
h1 { color: #F2F2F2; font-size: 34px; font-weight: 500; line-height: 1.2;
  margin: 14px 0 4px; }
h1 span { color: #2DD4BF; display: block; }
h2 { color: #F2F2F2; font-size: 19px; font-weight: 500; margin: 0 0 14px; }
.meta { font-size: 13px; color: #52525B; margin-top: 10px; }
.meta b { color: #A1A1AA; font-weight: 500; }
.controls { display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
  margin: 30px 0 8px; position: sticky; top: 0; background: #0A0A0A;
  padding: 12px 0; z-index: 5; border-bottom: 1px solid #27272A; }
select { background: #171717; color: #F2F2F2; border: 1px solid #27272A;
  font: inherit; font-size: 14px; padding: 8px 12px; min-width: 220px; }
select:focus { outline: none; border-color: #2DD4BF; }
.btn { background: #2DD4BF; color: #0A0A0A; border: none; font: inherit;
  font-size: 14px; font-weight: 500; padding: 9px 20px; cursor: pointer; }
.btn:disabled { background: #27272A; color: #52525B; cursor: wait; }
#status { font-size: 13px; color: #52525B; }
#status.err { color: #2DD4BF; }
.sec { margin-top: 36px; }
.card { background: #171717; border-top: 2px solid #2DD4BF; padding: 18px 20px; }
.cards2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.bar-row { display: grid; grid-template-columns: 140px 1fr 60px; gap: 12px;
  align-items: center; padding: 6px 0; border-bottom: 1px solid #1d1d20; }
.bar-row:last-child { border-bottom: none; }
.bar-row .t { color: #F2F2F2; font-size: 13.5px; }
.bar-track { display: block; background: #27272A; height: 8px; }
.bar-fill { display: block; background: #2DD4BF; height: 8px; }
.bar-row .p { text-align: right; color: #F2F2F2; font-size: 13px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 10px; margin: 14px 0; }
.tile { background: #0A0A0A; border: 1px solid #27272A; padding: 10px 12px; }
.tile .v { color: #2DD4BF; font-size: 21px; font-weight: 500; }
.tile .k { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.12em;
  color: #52525B; }
.mrow { display: grid; grid-template-columns: 170px 1fr; gap: 14px;
  padding: 11px 0; border-bottom: 1px solid #1d1d20; align-items: baseline; }
.mrow:last-child { border-bottom: none; }
.when { color: #52525B; font-size: 12.5px; }
.fixture { color: #F2F2F2; font-size: 14.5px; }
.fixture .score { color: #2DD4BF; font-weight: 500; }
.call { font-size: 13px; margin-top: 2px; }
.call b { color: #F2F2F2; font-weight: 500; }
.odds { font-size: 12px; color: #52525B; margin-top: 3px; }
.odds b { color: #A1A1AA; font-weight: 500; }
.xcheck { font-size: 12.5px; color: #A1A1AA; margin: 6px 0 14px;
  padding: 9px 13px; background: #0A0A0A; border: 1px solid #27272A; }
.xcheck b { color: #2DD4BF; }
.xcheck .muted { color: #52525B; font-size: 11.5px; display: block;
  margin-top: 3px; }
.venue { color: #52525B; font-size: 12px; }
.chip { display: inline-block; font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.12em; padding: 1px 7px; border: 1px solid #27272A;
  color: #A1A1AA; margin-left: 6px; white-space: nowrap; }
.chip.hit { border-color: #2DD4BF; color: #2DD4BF; }
.chip.miss { border-color: #52525B; color: #52525B; }
.grow { display: grid; grid-template-columns: 1fr 50px 56px 64px; gap: 8px;
  padding: 5px 0; border-bottom: 1px solid #1d1d20; font-size: 13px; }
.grow.hdr { color: #52525B; font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.1em; }
.grow .t { color: #F2F2F2; }
.grow .v { text-align: right; }
.note { font-size: 12.5px; color: #52525B; margin-top: 10px; }
.foot { margin-top: 60px; padding-top: 18px; border-top: 1px solid #27272A;
  font-size: 12px; color: #52525B; max-width: 80ch; }
@media (max-width: 760px) { .cards2 { grid-template-columns: 1fr; }
  .mrow { grid-template-columns: 1fr; gap: 2px; } h1 { font-size: 26px; } }
"""

JS_MAIN = """
let DATA = EMBEDDED;
let TEAM = '';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
  'Sep', 'Oct', 'Nov', 'Dec'];

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
function pct(x, dp) { return (x * 100).toFixed(dp || 0) + '%'; }
function fairOdds(p) { return p > 0 ? (1 / p).toFixed(2) : 'n/a'; }

function aest(iso, dateOnly) {
  if (!iso) return dateOnly ? esc(dateOnly) + ' (time tbc)' : 'time tbc';
  const d = new Date(Date.parse(iso) + 36000000);
  let h = d.getUTCHours(), m = d.getUTCMinutes();
  const am = h < 12 ? 'am' : 'pm';
  h = h % 12; if (h === 0) h = 12;
  return DAYS[d.getUTCDay()] + ' ' + d.getUTCDate() + ' ' +
    MONTHS[d.getUTCMonth()] + ', ' + h + ':' +
    String(m).padStart(2, '0') + am + ' AEST';
}

function callLine(m) {
  const p = m.prediction;
  if (!p) return 'awaiting teams';
  let lead;
  if (p.p_win >= Math.max(p.p_draw, p.p_loss)) {
    lead = '<b>' + esc(m.team1) + ' win ' + pct(p.p_win) + '</b>';
  } else if (p.p_loss >= Math.max(p.p_win, p.p_draw)) {
    lead = '<b>' + esc(m.team2) + ' win ' + pct(p.p_loss) + '</b>';
  } else {
    lead = '<b>Draw ' + pct(p.p_draw) + '</b>';
  }
  let s = lead + ' (' + pct(p.p_win) + ' / ' + pct(p.p_draw) + ' / ' +
    pct(p.p_loss) + ' for ' + esc(m.team1) + '), likely ' +
    esc(p.modal_score) + ' (' + pct(p.modal_p) + ')';
  if (p.p_advance !== undefined && m.status !== 'played') {
    const fav = p.p_advance >= 0.5 ? m.team1 : m.team2;
    const fp = p.p_advance >= 0.5 ? p.p_advance : 1 - p.p_advance;
    s += '; <b>' + esc(fav) + ' advance ' + pct(fp) + '</b>';
  }
  return s;
}

function pickOutcome(p) {
  if (p.p_win >= Math.max(p.p_draw, p.p_loss)) return 'team1';
  if (p.p_loss >= Math.max(p.p_win, p.p_draw)) return 'team2';
  return 'draw';
}

function stageName(s) {
  return {group: 'Group', r32: 'Last 32', r16: 'Last 16', qf: 'QF',
          sf: 'SF', third: '3rd place', final: 'Final'}[s] || s;
}

function involves(m, t) { return m.team1 === t || m.team2 === t; }

function renderMeta() {
  const played = DATA.matches.filter(m => m.status === 'played').length;
  const gen = DATA.generated_aest || DATA.generated;
  document.getElementById('meta').innerHTML =
    'Updated <b>' + esc(gen) + '</b> | results through <b>' +
    esc(DATA.data_through) + '</b> | <b>' + played +
    '</b> of 104 matches played | <b>' +
    DATA.sim_runs.toLocaleString() + '</b> simulations';
}

function renderOdds() {
  const top = Object.entries(DATA.teams)
    .sort((a, b) => b[1].p_champion - a[1].p_champion).slice(0, 8);
  const max = top[0][1].p_champion || 0.01;
  let h = '<h2>Title odds</h2>';
  top.forEach(([name, i]) => {
    h += '<div class="bar-row"><span class="t">' + esc(name) +
      '</span><span class="bar-track"><span class="bar-fill" style="width:' +
      Math.max(2, i.p_champion / max * 100).toFixed(1) +
      '%"></span></span><span class="p">' + pct(i.p_champion, 1) +
      '</span></div>';
  });
  document.getElementById('odds').innerHTML = h;
}

function renderTeamPanel() {
  const el = document.getElementById('teampanel');
  if (!TEAM) { el.innerHTML = ''; el.style.display = 'none'; return; }
  el.style.display = 'block';
  const i = DATA.teams[TEAM];
  let h = '<h2>' + esc(TEAM) + ' <span style="color:#52525B;font-size:14px">' +
    'Group ' + esc(i.group) + ' | rating ' + Math.round(i.rating) +
    (i.adjust ? ' (includes squad adjustment ' + i.adjust + ')' : '') +
    '</span></h2>';
  h += '<div class="xcheck">Model rank <b>#' + (i.model_rank || '?') +
    '</b> of 48 (rating ' + Math.round(i.rating) + ')' +
    (i.fifa_rank ? ' &nbsp; FIFA rank <b>#' + i.fifa_rank + '</b>' +
      (i.fifa_points ? ' (' + i.fifa_points + ' pts)' : '') : '') +
    '<span class="muted">FIFA ranking shown for reference only; it is not ' +
    'used by the model.</span></div>';
  h += '<div class="tiles">';
  [['Last 32', i.p_r32], ['Last 16', i.p_r16], ['Quarterfinal', i.p_qf],
   ['Semifinal', i.p_sf], ['Final', i.p_final], ['Champion', i.p_champion]]
    .forEach(([k, v]) => {
      h += '<div class="tile"><div class="v">' + pct(v, v < 0.1 ? 1 : 0) +
        '</div><div class="k">' + k + '</div></div>';
    });
  h += '</div>';
  if (i.adjust_note) {
    h += '<div class="note">Squad news: ' + esc(i.adjust_note) + '</div>';
  }
  const group = DATA.groups[i.group];
  const pts = {};
  group.forEach(t => { pts[t] = 0; });
  DATA.matches.forEach(m => {
    if (m.stage === 'group' && m.status === 'played' &&
        group.indexOf(m.team1) >= 0) {
      const a = m.actual;
      if (a.score1 > a.score2) pts[m.team1] += 3;
      else if (a.score2 > a.score1) pts[m.team2] += 3;
      else { pts[m.team1] += 1; pts[m.team2] += 1; }
    }
  });
  h += '<div style="max-width:430px;margin-top:14px">' +
    '<div class="grow hdr"><span>Group ' + esc(i.group) +
    '</span><span class="v">Pts</span><span class="v">xPts</span>' +
    '<span class="v">Last 32</span></div>';
  group.slice().sort((a, b) => DATA.teams[b].p_r32 - DATA.teams[a].p_r32)
    .forEach(t => {
      h += '<div class="grow"><span class="t">' + esc(t) + '</span>' +
        '<span class="v">' + pts[t] + '</span><span class="v">' +
        DATA.teams[t].exp_points.toFixed(1) + '</span><span class="v" ' +
        'style="color:#2DD4BF">' + pct(DATA.teams[t].p_r32) + '</span></div>';
    });
  h += '</div>';
  const proj = DATA.matches.filter(m => m.projected && involves(m, TEAM));
  if (proj.length) {
    h += '<div class="note" style="margin-top:14px">Most likely knockout ' +
      'path (projected pairings from simulation):</div>';
    proj.forEach(m => {
      h += '<div class="mrow"><span class="when">' + stageName(m.stage) +
        ', ' + aest(m.kickoff_utc, m.date) + '</span><span><span class="fixture">' +
        esc(m.team1) + ' v ' + esc(m.team2) + '</span> <span class="venue">(' +
        pct(m.p_pairing || 0) + ' of simulations)</span><div class="call">' +
        callLine(m) + '</div></span></div>';
    });
  }
  el.innerHTML = h;
}

function matchRow(m) {
  let fixture, tags = '';
  if (m.status === 'played') {
    const a = m.actual;
    fixture = esc(m.team1) + ' <span class="score">' + a.score1 + '-' +
      a.score2 + '</span> ' + esc(m.team2) +
      (a.aet ? ' <span class="venue">aet</span>' : '') +
      (a.pens ? ' <span class="venue">(' + a.pens[0] + '-' + a.pens[1] +
        ' pens)</span>' : '');
    if (m.prediction) {
      const pick = pickOutcome(m.prediction);
      const hit = pick === a.outcome;
      tags += '<span class="chip ' + (hit ? 'hit' : 'miss') + '">result ' +
        (hit ? 'hit' : 'miss') + '</span>';
      const shit = m.prediction.modal_score === a.score1 + '-' + a.score2;
      tags += '<span class="chip ' + (shit ? 'hit' : 'miss') + '">score ' +
        (shit ? 'hit' : 'miss') + '</span>';
    }
  } else {
    fixture = esc(m.team1) + ' v ' + esc(m.team2);
    if (m.low_stakes) tags += '<span class="chip">low stakes</span>';
    if (m.projected) tags += '<span class="chip">projected</span>';
  }
  let oddsLine = '';
  if (m.status !== 'played' && m.prediction) {
    const p = m.prediction;
    let parts = esc(m.team1) + ' <b>' + fairOdds(p.p_win) + '</b> / draw <b>' +
      fairOdds(p.p_draw) + '</b> / ' + esc(m.team2) + ' <b>' +
      fairOdds(p.p_loss) + '</b>';
    if (p.p_advance !== undefined) {
      const fav = p.p_advance >= 0.5 ? m.team1 : m.team2;
      const fp = p.p_advance >= 0.5 ? p.p_advance : 1 - p.p_advance;
      parts += '; ' + esc(fav) + ' to advance <b>' + fairOdds(fp) + '</b>';
    }
    oddsLine = '<div class="odds">Fair odds, back only above: ' + parts +
      '</div>';
  }
  return '<div class="mrow"><span class="when">' +
    aest(m.kickoff_utc, m.date) + '<br><span class="venue">' +
    stageName(m.stage) + (m.group ? ' ' + esc(m.group) : '') + ' | ' +
    esc(m.city) + '</span></span><span><span class="fixture">' + fixture +
    '</span>' + tags + '<div class="call">' +
    (m.prediction ? callLine(m) : 'awaiting teams') + '</div>' + oddsLine +
    '</span></div>';
}

function renderUpcoming() {
  let ms = DATA.matches.filter(m => m.status === 'scheduled' && m.team1 &&
    m.team2 && m.prediction && !m.projected);
  if (TEAM) ms = ms.filter(m => involves(m, TEAM));
  ms.sort((a, b) => (a.kickoff_utc || a.date) < (b.kickoff_utc || b.date)
    ? -1 : 1);
  const total = ms.length;
  let note = '';
  if (!TEAM && ms.length > 16) {
    ms = ms.slice(0, 16);
    note = '<div class="note">Next 16 of ' + total + ' fixtures with teams ' +
      'set. Pick a team above to see its full schedule, or open ' +
      'PREDICTIONS.md for every match including knockout projections.</div>';
  }
  document.getElementById('upcoming').innerHTML =
    ms.map(matchRow).join('') +
    (ms.length ? '' : '<div class="note">No upcoming fixtures' +
      (TEAM ? ' for ' + esc(TEAM) : '') + '.</div>') + note;
}

function renderResults() {
  let ms = DATA.matches.filter(m => m.status === 'played');
  if (TEAM) ms = ms.filter(m => involves(m, TEAM));
  ms.sort((a, b) => (a.kickoff_utc || a.date) > (b.kickoff_utc || b.date)
    ? -1 : 1);
  let rec = '';
  if (ms.length) {
    let hits = 0, shits = 0;
    ms.forEach(m => {
      if (!m.prediction) return;
      if (pickOutcome(m.prediction) === m.actual.outcome) hits += 1;
      if (m.prediction.modal_score ===
          m.actual.score1 + '-' + m.actual.score2) shits += 1;
    });
    rec = '<div class="note" style="margin-bottom:8px">Model record: ' +
      hits + '/' + ms.length + ' results, ' + shits + '/' + ms.length +
      ' exact scores. Pre-match predictions are frozen once played.</div>';
  }
  document.getElementById('results').innerHTML = rec +
    (ms.map(matchRow).join('') ||
     '<div class="note">No completed matches yet' +
     (TEAM ? ' for ' + esc(TEAM) : '') + '.</div>');
}

function renderAll() {
  renderMeta(); renderOdds(); renderTeamPanel();
  renderUpcoming(); renderResults();
}

function fillSelect() {
  const sel = document.getElementById('teamsel');
  const names = Object.keys(DATA.teams).sort();
  sel.innerHTML = '<option value="">All teams</option>' +
    names.map(n => '<option value="' + esc(n) + '">' + esc(n) +
      '</option>').join('');
  sel.onchange = () => { TEAM = sel.value; renderAll(); };
}

async function doRefresh() {
  const btn = document.getElementById('refreshbtn');
  const st = document.getElementById('status');
  const local = ['localhost', '127.0.0.1'].includes(location.hostname);
  btn.disabled = true;
  st.className = '';
  if (local) {
    // Local use: trigger a real model run via serve.py.
    st.textContent = 'Refreshing: fetching new results and re-simulating ' +
      '(about 10 to 20 seconds)...';
    try {
      const r = await fetch('/refresh', {method: 'POST'});
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || 'update failed');
      const p = await fetch('predictions.json', {cache: 'no-store'});
      DATA = await p.json();
      renderAll();
      st.textContent = 'Updated. ' + (j.summary || '');
    } catch (e) {
      st.className = 'err';
      st.textContent = 'Local refresh needs the server running: run ' +
        'python3 serve.py in the project folder.';
    }
  } else {
    // Public site: reload the latest published predictions. The model
    // re-runs automatically in the background as results come in.
    st.textContent = 'Loading the latest published predictions...';
    try {
      const p = await fetch('predictions.json?t=' + Date.now(), {cache: 'no-store'});
      DATA = await p.json();
      renderAll();
      st.textContent = 'Showing the latest published predictions. This site ' +
        'updates automatically as results come in.';
    } catch (e) {
      st.className = 'err';
      st.textContent = 'Could not load the latest data. Please reload the page.';
    }
  }
  btn.disabled = false;
}

fillSelect();
renderAll();
if (window.location.protocol !== 'file:') {
  fetch('predictions.json', {cache: 'no-store'})
    .then(r => r.json())
    .then(j => { DATA = j; renderAll(); })
    .catch(() => {});
}
"""


def main():
    with open(os.path.join(OUT, "predictions.json"), encoding="utf-8") as f:
        data = json.load(f)
    embedded = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>World Cup 2026 Predictor</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="label"><span class="rule"></span>
      <span>World Cup 2026 | live predictor</span></div>
    <h1>Every match, modelled.<span>All times AEST.</span></h1>
    <div class="meta" id="meta"></div>
  </header>
  <div class="controls">
    <select id="teamsel"></select>
    <button class="btn" id="refreshbtn" onclick="doRefresh()">Refresh predictions</button>
    <span id="status"></span>
  </div>
  <div class="sec card" id="odds"></div>
  <div class="sec card" id="teampanel" style="display:none"></div>
  <div class="sec">
    <h2>Upcoming, with predictions</h2>
    <div id="upcoming"></div>
  </div>
  <div class="sec">
    <h2>Results</h2>
    <div id="results"></div>
  </div>
  <footer class="foot">
    This site updates automatically as new results come in. Probabilities
    are model estimates from public match data, not guarantees; exact
    scorelines rarely exceed 15 to 20% even for heavy favourites. Fair odds
    are 1 divided by the model probability and exclude any bookmaker margin,
    so a wager only carries positive expected value at a price above the one
    shown; this is information, not betting advice. FIFA rankings are a
    read-only reference and play no part in the model, which is built from
    match results only.
  </footer>
</div>
<script>
const EMBEDDED = {embedded};
{JS_MAIN}
</script>
</body>
</html>"""
    out_path = os.path.join(OUT, "dashboard.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out_path} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
