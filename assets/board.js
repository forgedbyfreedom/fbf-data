const SPORTS = [
  {k:'FB', label:'Football', match:x=>x==='ncaaf'||x==='nfl'},
  {k:'nfl', label:'NFL', match:x=>x==='nfl'},
  {k:'ncaaf', label:'CFB', match:x=>x==='ncaaf'},
];
let DATA={predictions:[]}, active='FB';
function stampFmt(ts){ if(!ts) return ''; const m=String(ts).match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/); if(!m) return ts; return `updated ${m[2]}/${m[3]} ${m[4]}:${m[5]} · latest run`; }
function num(v,d=1){ return (v==null||isNaN(v))?'—':Number(v).toFixed(d); }
function logo(t){ return t&&t.logo?`<img src="${t.logo}" onerror="this.style.visibility='hidden'">`:'<span style="width:26px"></span>'; }
function isHi(p){ const k=p.picks||{}; return !!(k.ats_high_conf||k.ou_high_conf|| (p.prediction&&p.prediction.confidence>=80)); }
function edge(p){ const pr=p.prediction||{},od=p.odds||{}; if(pr.projected_spread==null||od.spread==null) return 0; return Math.abs(Math.abs(pr.projected_spread)-Math.abs(od.spread)); }
function card(p){
  const h=p.home_team||{},a=p.away_team||{},pr=p.prediction||{},k=p.picks||{},s=p.simulation||{},od=p.odds||{};
  const hi=isHi(p);
  const conf = pr.confidence!=null?pr.confidence:(k.su_confidence||0);
  const line = od.details?`<span class="pill">${od.details}${od.total?` · O/U ${od.total}`:''}</span>`+(od.provider?`<span class="pill">${od.provider}</span>`:''):'<span class="pill">no line yet</span>';
  const pk=(lb,val,cf,why)=>`<div class="pk"${why?` title="${String(why).replace(/"/g,'&quot;')}"`:''}><div class="lb">${lb}</div><div class="vl">${val||'—'}</div><div class="cf">${cf!=null?num(cf,0)+'%':''}</div><div class="bar"><i style="width:${Math.max(0,Math.min(100,cf||0))}%"></i></div></div>`;
  return `<div class="card ${hi?'hi':''}">
    ${hi?'<div class="hiflag">★ HIGH CONF</div>':''}
    <div class="when">${p.date_local||''}</div>
    <div class="teams">
      <div class="team">${logo(a)}<span class="nm">${a.name||p.away||''}</span><span class="ab">${a.abbr||''}</span></div>
      <div class="team">${logo(h)}<span class="nm">${h.name||p.home||''}</span><span class="ab">${h.abbr||''}</span></div>
    </div>
    <div class="line">${line}</div>
    <div class="line">Model: <b>${h.abbr||'H'} ${num(pr.projected_home_score,0)}</b> – <b>${num(pr.projected_away_score,0)} ${a.abbr||'A'}</b> · proj spread <b>${num(pr.projected_spread)}</b> · win ${num((pr.win_probability_home||0)*100,0)}%${s.simulations?` · ${(s.simulations/1000)}k sims`:''}</div>
    <div class="picks">
      ${pk('STRAIGHT UP', k.su_pick_abbr||k.su_pick, k.su_confidence)}
      ${pk('SPREAD', k.ats_pick_abbr?`${k.ats_pick_abbr} ${k.ats_spread>0?'+':''}${k.ats_spread??''}`:(k.ats_suppressed?'no pick':'—'), k.ats_confidence, k.ats_suppressed_reason)}
      ${pk('TOTAL', k.ou_pick?`${k.ou_pick} ${k.ou_line??''}`:(k.ou_suppressed?'no pick':'—'), k.ou_confidence, k.ou_suppressed_reason)}
    </div>
  </div>`;
}

// A board where most markets read "no pick" needs to say why, or it reads as
// broken. Both gates are magnitude tests: the model only speaks when it
// disagrees with the number by enough for the disagreement to mean something.
function renderCoverage(rows){
  const el=document.getElementById('coverage');
  if(!el) return;
  if(!rows.length){ el.hidden=true; return; }
  const ats=rows.filter(p=>(p.picks||{}).ats_pick).length;
  const ou =rows.filter(p=>(p.picks||{}).ou_pick).length;
  el.hidden=false;
  el.innerHTML =
    `Publishing <b>${ats}</b> spread pick${ats===1?'':'s'} and <b>${ou}</b> total pick${ou===1?'':'s'} `+
    `across ${rows.length} game${rows.length===1?'':'s'}. Everything else reads "no pick" on purpose — `+
    `the model has to disagree with the market number by a set margin before it says anything, `+
    `and against a closing line it usually doesn't. `+
    `Measured over 3,570 football games (2021&ndash;2025), totals closed at <b>50.0% Over</b> `+
    `and no factor in this pipeline beat that, so the bar on totals is the higher of the two.`;
}

function render(){
  const sp=SPORTS.find(s=>s.k===active);
  let rows=(DATA.predictions||[]).filter(p=>sp.match(p.sport));
  if(document.getElementById('hiOnly').checked) rows=rows.filter(isHi);
  const sort=document.getElementById('sort').value;
  rows.sort((a,b)=> sort==='date'?String(a.date_local).localeCompare(String(b.date_local)) : sort==='edge'?edge(b)-edge(a) : ((b.prediction&&b.prediction.confidence||0)-(a.prediction&&a.prediction.confidence||0)));
  document.getElementById('cnt').textContent = rows.length+' game'+(rows.length===1?'':'s');
  renderCoverage(rows);
  document.getElementById('board').innerHTML = rows.length?rows.map(card).join(''):`<div class="empty">No ${sp.label} games in the latest run.${active==='nfl'?' NFL is between slates right now — check back in-season.':''}</div>`;
}
function buildTabs(){
  const counts={}; (DATA.predictions||[]).forEach(p=>{counts[p.sport]=(counts[p.sport]||0)+1;});
  const t=document.getElementById('tabs'); t.innerHTML='';
  SPORTS.forEach(s=>{
    const n=(DATA.predictions||[]).filter(p=>s.match(p.sport)).length;
    if(s.k!=='FB'&&s.k!=='nfl'&&s.k!=='ncaaf'&&n===0) return;
    const el=document.createElement('div'); el.className='tab'+(s.k===active?' active':'');
    el.innerHTML=`${s.label} <span class="n">${n}</span>`;
    el.onclick=()=>{active=s.k;buildTabs();render();};
    t.appendChild(el);
  });
}
function boot(){
  document.getElementById('stamp').textContent=stampFmt(DATA.timestamp);
  buildTabs(); render();
  document.getElementById('hiOnly').onchange=render;
  document.getElementById('sort').onchange=render;
}
// ── ACCURACY PANEL ────────────────────────────────────────────────
// Sample size is shown as loudly as the percentage, on purpose. On
// 2026-09-04 the tracker held a 3-1 ATS record, which renders as 75% and
// means nothing whatsoever. A hit rate is only readable once there are
// enough graded picks for the confidence interval to be narrower than the
// thing being measured, so below MIN_READABLE the number is greyed and
// labelled rather than presented as a result.
const MIN_READABLE = 30;      // graded picks before a percentage is trusted
const BREAKEVEN = 52.4;       // -110 vig

function accCell(label, pct, record, n, isAts){
  const readable = n >= MIN_READABLE;
  const val = (pct==null||!n) ? String.fromCharCode(8212) : num(pct,1)+"%";
  let cls = "acc-val" + (readable ? "" : " thin");
  if(readable && isAts) cls += pct >= BREAKEVEN ? " acc-good" : " acc-bad";
  let bar = "";
  if(isAts && n){
    const w = Math.max(0, Math.min(100, pct));
    // Muted while the sample is unreadable: a full orange bar at 75% reads as
    // a strong result even when the number beside it is deliberately greyed.
    const fill = readable ? "var(--o)" : "#4a4a4a";
    bar = `<div class="acc-bar"><i style="width:${w}%;background:${fill}"></i>` +
          `<u style="left:${BREAKEVEN}%" title="breakeven ${BREAKEVEN}%"></u></div>`;
  }
  const flag = readable ? "" : `<div class="acc-flag">${n} of ${MIN_READABLE} graded &middot; not yet readable</div>`;
  return `<div class="acc-cell">
    <div class="acc-lb">${label}</div>
    <div class="${cls}">${val}</div>
    <div class="acc-rec">${record||"0-0"}</div>
    <div class="acc-n">from <b>${n}</b> graded pick${n===1?"":"s"}</div>
    ${bar}${flag}
  </div>`;
}

function renderAccuracy(a){
  const el = document.getElementById("acc");
  if(!a || !a.sports || !a.sports.ALL){ el.hidden = true; return; }
  const s = a.sports.ALL;
  const parse = r => { const p=String(r||"0-0").split("-"); return (parseInt(p[0])||0)+(parseInt(p[1])||0); };
  const nSU = parse(s.SU_record), nATS = parse(s.ATS_record), nOU = parse(s.OU_record);
  document.getElementById("accGrid").innerHTML =
      accCell("Against the spread", s.ATS_pct, s.ATS_record, nATS, true)
    + accCell("Over / under",       s.OU_pct,  s.OU_record,  nOU,  true)
    + accCell("Straight up",        s.SU_pct,  s.SU_record,  nSU,  false);
  document.getElementById("accSince").textContent =
    a.model_start ? ("tracking since " + a.model_start) : "";

  const worst = Math.min(nATS, nOU);
  let note = "";
  if(worst < MIN_READABLE){
    note = "Breakeven against the spread is <b>52.4%</b> at standard -110 pricing. "
         + "These records are far too small to read as a result - a 3-1 start is 75% "
         + "and tells you nothing. The numbers become meaningful somewhere north of "
         + MIN_READABLE + " graded picks per market.";
  } else {
    note = "Breakeven against the spread is <b>52.4%</b> at standard -110 pricing. "
         + "The marker on each bar sits at breakeven.";
  }
  const cal = a.calibration && a.calibration.ATS;
  if(cal){
    const used = cal.filter(b => b.picks > 0);
    if(used.length){
      note += "<br><br><b>Calibration</b> (does a stated confidence mean what it says): "
            + used.map(b => `${b.bucket} said &rarr; ${b.actual_pct==null?"&mdash;":num(b.actual_pct,0)+"%"} actual (${b.picks})`).join(" &middot; ");
    }
  }
  document.getElementById("accNote").innerHTML = note;
  el.hidden = false;
}

function setMsg(html){ document.getElementById('board').innerHTML = '<div class="empty">'+html+'</div>'; }

// Data is served from the same origin as this page; there is no embedded copy.
function load(){
  setMsg('Loading the latest run\u2026');
  return fetch('predictions.json?t='+Date.now(),{cache:'no-store'})
    .then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(j=>{
      if(!j||!Array.isArray(j.predictions)) throw new Error('predictions.json has no predictions array');
      DATA=j; boot();
      fetch("accuracy.json?t="+Date.now(),{cache:"no-store"})
        .then(r=>r.ok?r.json():null)
        .then(a=>{ try{ renderAccuracy(a); }catch(e){} })
        .catch(()=>{});
    })
    .catch(e=>{ setMsg('Could not load the latest run.<br><small>'+String(e.message||e)+'</small>'); });
}
load();
