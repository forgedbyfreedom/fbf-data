/* ForgedByFreedom live picks UI
   - Loads predictions.json
   - Groups by sport
   - 3 cards across
   - Red glow border for high confidence
*/

const PREDICTIONS_URL = "./predictions.json";   // same folder on gh-pages

const SPORT_ORDER = ["nfl","ncaaf","nba","ncaab","nhl","mlb","arts"];
const SPORT_LABELS = {
  all:"ALL",
  nfl:"NFL",
  ncaaf:"NCAAF",
  nba:"NBA",
  ncaab:"NCAAB",
  nhl:"NHL",
  mlb:"MLB",
  arts:"ARTS"
};

let allGames = [];
let activeSport = "all";
let searchTerm = "";
let sortMode = "time";

const elFilters = document.getElementById("sportFilters");
const elSections = document.getElementById("sportSections");
const elSearch = document.getElementById("searchBox");
const elSort = document.getElementById("sortSelect");

// stats elements
const statTotalGames = document.getElementById("statTotalGames");
const statFavorites = document.getElementById("statFavorites");
const statPicksAvail = document.getElementById("statPicksAvail");
const statHighConf = document.getElementById("statHighConf");
const statTimestamp = document.getElementById("statTimestamp");

function safe(obj, fallback){
  return (obj && typeof obj === "object") ? obj : fallback;
}

function parseTimestamp(ts){
  if(!ts) return "—";
  if(typeof ts === "string" && ts.length >= 8){
    // e.g. 20251124_2339
    const y = ts.slice(0,4);
    const m = ts.slice(4,6);
    const d = ts.slice(6,8);
    const rest = ts.split("_")[1] || "";
    const hh = rest.slice(0,2) || "00";
    const mm = rest.slice(2,4) || "00";
    return `${y}-${m}-${d} ${hh}:${mm} UTC`;
  }
  return String(ts);
}

function buildFilters(sportsPresent){
  elFilters.innerHTML = "";

  const btn = (key,label) => {
    const b = document.createElement("button");
    b.className = "filter-btn" + (activeSport===key ? " active":"");
    b.textContent = label;
    b.onclick = () => { activeSport = key; render(); };
    return b;
  };

  elFilters.appendChild(btn("all", SPORT_LABELS.all));

  sportsPresent.forEach(s => {
    elFilters.appendChild(btn(s, SPORT_LABELS[s] || s.toUpperCase()));
  });
}

function groupBySport(games){
  const map = {};
  games.forEach(g => {
    const sport = (g.sport || "unknown").toLowerCase();
    if(!map[sport]) map[sport] = [];
    map[sport].push(g);
  });
  return map;
}

function gameSearchText(g){
  const odds = safe(g.odds, {});
  const weather = safe(g.weather, {});
  const venue = safe(g.venue, {});
  return [
    g.matchup, g.name, g.shortName,
    g.home, g.away,
    odds.details, odds.provider,
    venue.name, venue.city, venue.state,
    weather.shortForecast
  ].filter(Boolean).join(" ").toLowerCase();
}

function sortGames(games){
  const toNum = v => (v==null || isNaN(v)) ? 0 : Number(v);

  if(sortMode==="confidence"){
    return games.slice().sort((a,b)=>{
      const ca = toNum(safe(a.prediction,{}).confidence);
      const cb = toNum(safe(b.prediction,{}).confidence);
      return cb - ca;
    });
  }

  if(sortMode==="edge"){
    return games.slice().sort((a,b)=>{
      const pa = safe(a.prediction,{});
      const pb = safe(b.prediction,{});
      const oa = safe(a.odds,{});
      const ob = safe(b.odds,{});
      const edgeA = Math.abs(toNum(pa.projected_spread) - toNum(oa.spread));
      const edgeB = Math.abs(toNum(pb.projected_spread) - toNum(ob.spread));
      return edgeB - edgeA;
    });
  }

  // default time:
  return games.slice().sort((a,b)=>{
    const ta = Date.parse(a.date_utc || a.dateUtc || "") || 0;
    const tb = Date.parse(b.date_utc || b.dateUtc || "") || 0;
    return ta - tb;
  });
}

function renderCard(g){
  const odds = safe(g.odds, {});
  const venue = safe(g.venue, {});
  const weather = safe(g.weather, {});
  const risk = safe(g.risk || g.weatherRisk, {});
  const pred = safe(g.prediction, null);

  const confidence = pred ? (pred.confidence ?? 0) : 0;
  const high = confidence >= 70 || g.highlight === true;

  const card = document.createElement("div");
  card.className = "card" + (high ? " high":"");

  const sport = (g.sport || "—").toUpperCase();
  const localTime = g.date_local || g.dateLocal || "—";

  const oddsDetails = odds.details || "N/A (ESPN)";
  const spread = (odds.spread==null ? "N/A" : odds.spread);
  const total = (odds.total==null ? "N/A" : odds.total);

  let weatherLine = "Indoor / N/A";
  if(venue.indoor) {
    weatherLine = "Indoor / N/A";
  } else if(weather && weather.temperatureF != null) {
    const t = weather.temperatureF;
    const w = weather.windSpeedMph ?? 0;
    const r = weather.rainChancePct ?? 0;
    const s = weather.shortForecast || "";
    weatherLine = `${t}°F • Wind ${w}mph • Rain ${r}% ${s ? "• "+s : ""}`.trim();
  }

  let riskLine = "Indoor / N/A";
  if(!venue.indoor){
    riskLine = (risk.risk==null) ? "0" : String(risk.risk);
  }

  let pickHtml = `<div class="meta">Picks: <b>No prediction yet</b></div>`;
  if(pred){
    const ph = pred.projected_home_score;
    const pa = pred.projected_away_score;
    const pt = pred.projected_total;
    const ps = pred.projected_spread;
    const wp = pred.win_probability_home;

    const home = g.home || safe(g.home_team,{}).abbr || "HOME";
    const away = g.away || safe(g.away_team,{}).abbr || "AWAY";

    pickHtml = `
      <div class="pick">
        <div class="line"><b>Projected Scores</b><span>${away} ${pa} • ${home} ${ph}</span></div>
        <div class="line"><b>Projected Total</b><span>${pt}</span></div>
        <div class="line"><b>Projected Spread</b><span>${ps}</span></div>
        <div class="line"><b>Win Prob (Home)</b><span>${(wp*100).toFixed(1)}%</span></div>
        <div class="line"><b>Confidence</b><span>${confidence}%</span></div>
      </div>
    `;
  }

  card.innerHTML = `
    ${high ? `<div class="badge">HIGH CONF</div>` : ``}
    <div class="row-top">
      <div class="sport-pill">${sport}</div>
      <div class="time">${localTime}</div>
    </div>

    <div class="matchup">${g.matchup || g.name || "—"}</div>

    <div class="teams">
      <span>${g.away || safe(g.away_team,{}).name || "Away"}</span>
      <span>${g.home || safe(g.home_team,{}).name || "Home"}</span>
    </div>

    <div class="meta">
      Odds: <b>${oddsDetails}</b><br/>
      Spread: <b>${spread}</b> | Total: <b>${total}</b><br/>
      Venue: ${venue.name || "—"}${venue.city ? " • "+venue.city:""}${venue.state ? ", "+venue.state:""}
    </div>

    <div class="meta">
      Weather: <b>${weatherLine}</b><br/>
      Weather Risk: <b>${riskLine}</b>
    </div>

    ${pickHtml}
  `;

  return card;
}

function render(){
  const filtered = allGames.filter(g=>{
    if(activeSport!=="all" && (g.sport||"").toLowerCase()!==activeSport) return false;
    if(searchTerm){
      return gameSearchText(g).includes(searchTerm);
    }
    return true;
  });

  const sorted = sortGames(filtered);

  const grouped = groupBySport(sorted);
  elSections.innerHTML = "";

  const sportsToRender = (activeSport==="all")
    ? Object.keys(grouped).sort((a,b)=>{
        const ia = SPORT_ORDER.indexOf(a);
        const ib = SPORT_ORDER.indexOf(b);
        return (ia===-1?999:ia) - (ib===-1?999:ib);
      })
    : [activeSport];

  sportsToRender.forEach(sport=>{
    const games = grouped[sport] || [];
    if(!games.length) return;

    const sec = document.createElement("section");
    sec.className = "section";

    const label = SPORT_LABELS[sport] || sport.toUpperCase();

    sec.innerHTML = `
      <h2>${label} <span class="count">— ${games.length} games</span></h2>
      <div class="grid"></div>
    `;

    const grid = sec.querySelector(".grid");
    games.forEach(g=>{
      grid.appendChild(renderCard(g));
    });

    elSections.appendChild(sec);
  });
}

async function loadPredictions(){
  const res = await fetch(PREDICTIONS_URL, {cache:"no-store"});
  const data = await res.json();

  // support either predictions.json or old combined-style
  const games = data.predictions || data.data || [];
  allGames = Array.isArray(games) ? games : [];

  // stats
  const total = allGames.length;
  const highConf = allGames.filter(g=>{
    const c = safe(g.prediction,{}).confidence || 0;
    return c >= 70 || g.highlight === true;
  }).length;

  const favorites = allGames.filter(g=>g.favorite === true).length;

  statTotalGames.textContent = total;
  statHighConf.textContent = highConf;
  statFavorites.textContent = favorites;
  statPicksAvail.textContent = total; // picks = games predicted
  statTimestamp.textContent = parseTimestamp(data.timestamp);

  // filters
  const sportsPresent = [...new Set(allGames.map(g=>(g.sport||"").toLowerCase()))]
    .filter(Boolean)
    .sort((a,b)=>{
      const ia = SPORT_ORDER.indexOf(a);
      const ib = SPORT_ORDER.indexOf(b);
      return (ia===-1?999:ia) - (ib===-1?999:ib);
    });

  buildFilters(sportsPresent);
  render();
}

elSearch.addEventListener("input", e=>{
  searchTerm = e.target.value.trim().toLowerCase();
  render();
});

elSort.addEventListener("change", e=>{
  sortMode = e.target.value;
  render();
});

// boot
loadPredictions().catch(err=>{
  console.error(err);
  elSections.innerHTML = `
    <div style="padding:20px;color:#fff">
      ❌ Failed to load predictions.json
    </div>
  `;
});
