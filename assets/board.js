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
  const pk=(lb,val,cf)=>`<div class="pk"><div class="lb">${lb}</div><div class="vl">${val||'—'}</div><div class="cf">${cf!=null?num(cf,0)+'%':''}</div><div class="bar"><i style="width:${Math.max(0,Math.min(100,cf||0))}%"></i></div></div>`;
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
      ${pk('SPREAD', k.ats_pick_abbr?`${k.ats_pick_abbr} ${k.ats_spread>0?'+':''}${k.ats_spread??''}`:(k.ats_suppressed?'no pick':'—'), k.ats_confidence)}
      ${pk('TOTAL', k.ou_pick?`${k.ou_pick} ${k.ou_line??''}`:'—', k.ou_confidence)}
    </div>
  </div>`;
}
function render(){
  const sp=SPORTS.find(s=>s.k===active);
  let rows=(DATA.predictions||[]).filter(p=>sp.match(p.sport));
  if(document.getElementById('hiOnly').checked) rows=rows.filter(isHi);
  const sort=document.getElementById('sort').value;
  rows.sort((a,b)=> sort==='date'?String(a.date_local).localeCompare(String(b.date_local)) : sort==='edge'?edge(b)-edge(a) : ((b.prediction&&b.prediction.confidence||0)-(a.prediction&&a.prediction.confidence||0)));
  document.getElementById('cnt').textContent = rows.length+' game'+(rows.length===1?'':'s');
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
function setMsg(html){ document.getElementById('board').innerHTML = '<div class="empty">'+html+'</div>'; }

// Data is served from the same origin as this page; there is no embedded copy.
function load(){
  setMsg('Loading the latest run\u2026');
  return fetch('predictions.json?t='+Date.now(),{cache:'no-store'})
    .then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(j=>{
      if(!j||!Array.isArray(j.predictions)) throw new Error('predictions.json has no predictions array');
      DATA=j; boot();
    })
    .catch(e=>{ setMsg('Could not load the latest run.<br><small>'+String(e.message||e)+'</small>'); });
}
load();
