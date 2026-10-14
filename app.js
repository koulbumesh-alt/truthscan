/* ===================================================================
   TRUTHSCAN AI — APP LOGIC
   Live headlines, fact-check reviews, and evidence reports come from the
   FastAPI backend. Any offline fallback article remains visibly labeled.
   =================================================================== */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const app = $('#app');

const state = {
  page: 'home',
  search: { q: '', cat: 'All', sort: 'Trending' },
  verificationHistory: [],
  user: null,
  auth: { mode: 'signup', loading: false, error: '', message: '', actionUrl: '', resetToken: '', providers: {google:false,meta:false,email:false,development:false} },
  live: { loading: true, connected: false, warning: '', refreshedAt: null },
  rumours: { loading: true, refreshing: false, items: [], error: '', warnings: [], refreshedAt: null, recencyDays: 14 },
  searchRemote: { query: '', loading: false, ids: [], bestCount: 0, relatedCount: 0, error: '', requestKey: '' },
  searchAssessment: { query: '', loading: false, result: null, error: '', requestKey: '' },
  verification: { loading: false, result: null, error: '', inputLabel: '' },
};

const getArticle = id => ARTICLES.find(a => a.id === id);

function pickDiverse(items,limit){
  const chosen=[],seen=new Set();
  for(const item of items){
    const key=(item.source||'').toLowerCase();
    if(!seen.has(key)){chosen.push(item);seen.add(key);if(chosen.length===limit)return chosen;}
  }
  for(const item of items){if(!chosen.includes(item)){chosen.push(item);if(chosen.length===limit)break;}}
  return chosen;
}

function timeAgo(value){
  if(!value) return 'Recently published';
  const seconds=Math.max(0,(Date.now()-new Date(value).getTime())/1000);
  if(seconds<3600) return `${Math.max(1,Math.floor(seconds/60))} min ago`;
  if(seconds<86400) return `${Math.floor(seconds/3600)} hours ago`;
  const days=Math.floor(seconds/86400);
  return days===1?'Yesterday':`${days} days ago`;
}

function liveToArticle(item, index=0){
  const allowed=['India','Fact Check','Technology','World','Science','Business','Sports','Entertainment'];
  const category=allowed.includes(item.category)?item.category:'World';
  const date=item.published_at?new Date(item.published_at):null;
  return {
    id:`live_${item.id}`,
    backendId:item.id,
    isLive:true,
    category,
    headline:item.headline,
    description:item.description || `Latest reporting from ${item.source}. Open the original publisher to read the full article.`,
    source:item.source,
    provider:item.provider,
    author:item.author || 'Publisher newsroom',
    time:timeAgo(item.published_at),
    date:date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'}) : 'Latest',
    publishedAt:item.published_at,
    trending:Boolean(item.is_trending),
    topics:[`#${category}`],
    keywords:(item.headline+' '+(item.description||'')+' '+category).toLowerCase().split(/\W+/).filter(Boolean),
    body:[item.description || 'A summary was not supplied by this feed.', 'TRUTHSCAN displays this feed summary with source attribution. Use the link below to read the complete report on the publisher’s website.'],
    image:item.image_url || makeImage(category, index+20),
    fallbackImage:makeImage(category, index+20),
    url:item.url,
    relevanceScore:item.relevance_score ?? null,
    matchType:item.match_type || null,
    feedVerdict:item.feed_verdict || 'MORE VERIFICATION NEEDED',
    feedVerdictReason:item.feed_verdict_reason || 'Run an in-app evidence check for this item.',
    analysis:null,
  };
}

function mergeLiveArticles(items){
  const mapped=items.map(liveToArticle);
  const incoming=new Set(mapped.map(a=>a.id));
  for(let i=ARTICLES.length-1;i>=0;i--){
    if(ARTICLES[i].isLive && incoming.has(ARTICLES[i].id)) ARTICLES.splice(i,1);
  }
  ARTICLES.unshift(...mapped);
  return mapped;
}

async function loadLiveNews({q='',category='All',limit=80}={}){
  const cleanQuery=q.trim().replace(/^#/,'');
  const requestKey=`${cleanQuery.toLowerCase()}|${category}|${Date.now()}`;
  state.live.loading=true;
  if(cleanQuery){
    state.searchRemote={query:cleanQuery,loading:true,ids:[],bestCount:0,relatedCount:0,error:'',requestKey};
    if(state.page==='search') render();
  }
  try{
    const params=new URLSearchParams({limit:String(limit),sort:cleanQuery?'relevant':'trending'});
    if(cleanQuery) params.set('q',cleanQuery);
    if(category && category!=='All') params.set('category',category);
    const response=await fetch(`/api/v1/news?${params}`);
    if(!response.ok) throw new Error(`API ${response.status}`);
    const payload=await response.json();
    const mapped=mergeLiveArticles(payload.articles||[]);
    if(cleanQuery && state.searchRemote.requestKey===requestKey){
      state.searchRemote={
        query:cleanQuery,
        loading:false,
        ids:mapped.map(a=>a.id),
        bestCount:payload.meta?.best_count||mapped.filter(a=>a.matchType==='best').length,
        relatedCount:payload.meta?.related_count||mapped.filter(a=>a.matchType==='related').length,
        error:'',
        requestKey,
      };
    }
    state.live={loading:false,connected:true,warning:(payload.meta?.warnings||[])[0]||'',refreshedAt:payload.meta?.refreshed_at||null};
  }catch(error){
    console.warn('Live news unavailable; using demo articles.',error);
    if(cleanQuery && state.searchRemote.requestKey===requestKey){
      state.searchRemote={query:cleanQuery,loading:false,ids:[],bestCount:0,relatedCount:0,error:'Live search is temporarily unavailable.',requestKey};
    }
    state.live={loading:false,connected:false,warning:'Live feeds are temporarily unavailable. Demo articles remain available.',refreshedAt:null};
  }
  if(['home','trending','search','analyze'].includes(state.page)) render();
}
window.loadLiveNews=loadLiveNews;

async function loadSearchAssessment(query){
  const cleanQuery=String(query||'').trim().replace(/^#/,'');
  if(!cleanQuery){
    state.searchAssessment={query:'',loading:false,result:null,error:'',requestKey:''};
    if(state.page==='search')render();
    return;
  }
  const requestKey=`${cleanQuery.toLowerCase()}|${Date.now()}`;
  state.searchAssessment={query:cleanQuery,loading:true,result:null,error:'',requestKey};
  if(state.page==='search')render();
  try{
    const response=await fetch('/api/v1/verify/text',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:cleanQuery})
    });
    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(authError(payload,'Fact-check search is temporarily unavailable.'));
    if(state.searchAssessment.requestKey===requestKey){
      state.searchAssessment={query:cleanQuery,loading:false,result:payload,error:'',requestKey};
    }
  }catch(error){
    if(state.searchAssessment.requestKey===requestKey){
      state.searchAssessment={query:cleanQuery,loading:false,result:null,error:error.message||'Fact-check search is temporarily unavailable.',requestKey};
    }
  }
  if(state.page==='search')render();
}
window.loadSearchAssessment=loadSearchAssessment;

function rumourFinding(item){
  const text=`${item.headline||''} ${item.description||''}`.toLowerCase();
  if(/\b(deepfake|fake|false|falsely|fabricated|morphed|ai-generated|ai generated|did not happen|no evidence)\b/.test(text)) return {label:'DEBUNKED / FALSE CLAIM',cls:'rumour-false'};
  if(/\b(misleading|out of context|old video|old photo|unrelated|altered|satire)\b/.test(text)) return {label:'MISLEADING / CONTEXT',cls:'rumour-context'};
  if(/\b(claim is true|found to be true|authentic|genuine)\b/.test(text)) return {label:'SUPPORTED / GENUINE',cls:'rumour-supported'};
  return {label:'FACT-CHECK REVIEW',cls:'rumour-review'};
}

function feedVerdictMeta(item){
  const verdict=item.feedVerdict||item.feed_verdict||'MORE VERIFICATION NEEDED';
  const reason=item.feedVerdictReason||item.feed_verdict_reason||'Run an in-app evidence check for this item.';
  if(verdict==='DEBUNKED BY FACT-CHECKERS')return {verdict,label:'DEBUNKED BY FACT-CHECKERS',short:'DEBUNKED',icon:'✕',cls:'feed-debunked',reason};
  if(verdict==='SUPPORTED BY VERIFIED NEWS SOURCE')return {verdict,label:'SUPPORTED BY VERIFIED NEWS SOURCE',short:'SUPPORTED',icon:'✓',cls:'feed-supported',reason};
  return {verdict:'MORE VERIFICATION NEEDED',label:'MORE VERIFICATION NEEDED',short:'VERIFY MORE',icon:'?',cls:'feed-more',reason};
}

function feedVerdictBadge(item){
  const status=feedVerdictMeta(item);
  return `<div class="feed-verdict ${status.cls}" title="${esc(status.reason)}"><span>${status.icon}</span><b>${status.label}</b></div>`;
}

function rumourCard(item){
  const finding=rumourFinding(item);
  const status=feedVerdictMeta(item);
  const published=item.published_at?timeAgo(item.published_at):'Recently reviewed';
  const url=/^https?:\/\//i.test(item.url||'')?item.url:'#';
  const encodedHeadline=encodeURIComponent(item.headline||'').replace(/'/g,'%27');
  return `<article class="glass rumour-card ${finding.cls} ${status.cls}">
    <div class="rumour-card-top"><span class="rumour-status">${status.icon} ${status.label}</span><span>${esc(item.source)}</span></div>
    <h3>${esc(item.headline)}</h3>
    <p>${esc(item.description||'Open the publisher’s review for the examined claim, evidence, and conclusion.')}</p>
    <div class="feed-verdict-reason">${esc(status.reason)}</div>
    <div class="rumour-meta"><span>${esc(published)}</span><span>Latest 14-day review window</span></div>
    <div class="rumour-actions"><a class="btn btn-sm" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Read Fact Check ↗</a><button class="btn btn-sm btn-primary" onclick="verifySubmittedText(decodeURIComponent('${encodedHeadline}'))">${status.verdict==='MORE VERIFICATION NEEDED'?'VERIFY MORE IN TRUTHSCAN':'VIEW IN-APP EVIDENCE'}</button></div>
  </article>`;
}

async function loadRumours({force=false}={}){
  state.rumours.loading=true;
  state.rumours.refreshing=force;
  if(state.page==='rumours')render();
  try{
    let refreshStats=null;
    if(force){
      const refreshed=await fetch('/api/v1/rumours/refresh',{method:'POST'});
      if(!refreshed.ok)throw new Error(`Refresh service returned ${refreshed.status}`);
      refreshStats=await refreshed.json();
    }
    const response=await fetch('/api/v1/rumours?limit=60');
    if(!response.ok)throw new Error(`Rumour feed returned ${response.status}`);
    const payload=await response.json();
    state.rumours={
      loading:false,refreshing:false,items:payload.articles||[],error:'',
      warnings:payload.meta?.warnings||[],refreshedAt:payload.meta?.refreshed_at||new Date().toISOString(),
      recencyDays:payload.meta?.recency_days||14,lastRefresh:refreshStats,
    };
    if(force){
      const fresh=refreshStats?.new_items||0;
      toast(fresh?`${fresh} new fact-check review${fresh!==1?'s':''} added`:`No new publisher reviews yet · ${refreshStats?.updated_items||0} existing items refreshed`);
    }
  }catch(error){
    state.rumours={...state.rumours,loading:false,refreshing:false,error:error.message||'Fact-check feeds are temporarily unavailable.'};
    if(force)toast('Some fact-check feeds could not be refreshed');
  }
  if(['home','rumours'].includes(state.page))render();
}
window.loadRumours=loadRumours;
window.refreshRumours=()=>loadRumours({force:true});

async function refreshEverything(){
  state.live.loading=true;
  state.rumours.refreshing=true;
  render();
  toast('Refreshing live news and fact-check feeds…');
  try{
    const response=await fetch('/api/v1/news/refresh',{method:'POST'});
    if(!response.ok)throw new Error(`Refresh service returned ${response.status}`);
    const stats=await response.json();
    await Promise.all([loadLiveNews(),loadRumours({force:true})]);
    const fresh=stats.new_items||0;
    toast(fresh?`${fresh} new news item${fresh!==1?'s':''} added · existing reports refreshed`:`No newly published news yet · ${stats.updated_items||0} existing reports refreshed`);
  }catch(error){
    state.live.loading=false;
    state.rumours.refreshing=false;
    toast('Refresh completed with source warnings');
    await Promise.all([loadLiveNews(),loadRumours()]);
  }
}
window.refreshEverything=refreshEverything;

/* ---------- helpers ---------- */
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

function toast(msg){
  let t=$('#toast'); t.innerHTML='✨ '+msg; t.classList.add('show');
  clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove('show'),2600);
}

function updateNavUser(){
  const avatar=$('#userAvatar');
  const button=$('#accountButton');
  const navLabel=$('#accountNavLabel');
  if(!avatar||!button)return;
  avatar.textContent=state.user?String(state.user.name||'U').trim().charAt(0).toUpperCase():'G';
  button.title=state.user?`Account · ${state.user.name}`:'Create account or sign in';
  if(navLabel)navLabel.textContent=state.user?'Account':'Sign Up';
}

async function loadSession(){
  try{
    const response=await fetch('/api/v1/auth/me');
    state.user=response.ok?await response.json():null;
  }catch(_){state.user=null;}
  updateNavUser();
  if(state.page==='signup')render();
}

async function loadAuthProviders(){
  try{
    const response=await fetch('/api/v1/auth/providers');
    if(!response.ok)return;
    const payload=await response.json();
    state.auth.providers={
      google:Boolean(payload.google?.enabled),
      meta:Boolean(payload.meta?.enabled),
      email:Boolean(payload.email_delivery?.enabled),
      development:Boolean(payload.development_links),
    };
    if(state.page==='signup')render();
  }catch(_){}
}

async function handleAuthReturn(){
  const params=new URLSearchParams(location.search);
  const verifyToken=params.get('verify_email');
  const resetToken=params.get('reset_password');
  const oauthSuccess=params.get('auth')==='success';
  const oauthError=params.get('auth_error');
  if(!(verifyToken||resetToken||oauthSuccess||oauthError))return;
  history.replaceState({},'',location.pathname+location.hash);
  state.page='signup';
  if(resetToken){
    state.auth={...state.auth,mode:'reset',resetToken,error:'',message:'Choose a new password for your account.',actionUrl:''};
    render();
    return;
  }
  if(verifyToken){
    state.auth={...state.auth,loading:true,error:'',message:'Verifying your email…',actionUrl:''};render();
    try{
      const response=await fetch('/api/v1/auth/verify-email',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:verifyToken})});
      const payload=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(authError(payload,'The verification link is invalid or expired.'));
      state.user=payload.user;
      state.auth={...state.auth,loading:false,error:'',message:payload.message||'Email verified successfully.'};
      updateNavUser();
    }catch(error){state.auth={...state.auth,loading:false,error:error.message,message:''};}
    render();
    return;
  }
  if(oauthSuccess){
    await loadSession();
    state.auth={...state.auth,loading:false,error:'',message:'Social sign-in completed successfully.'};
  }else{
    const messages={oauth_state:'The social sign-in state check failed. Please try again.',oauth_expired:'The social sign-in request expired. Please try again.',oauth_failed:'The provider could not complete sign-in.'};
    state.auth={...state.auth,loading:false,error:messages[oauthError]||'Social sign-in could not be completed.',message:''};
  }
  render();
}

/* ---------- navigation ---------- */
function navigate(page, opts={}){
  state.page = page;
  if(opts.search) state.search = {...state.search, ...opts.search};
  window.scrollTo({top:0,behavior:'smooth'});
  $('#navlinks').classList.remove('open');
  render(opts);
  // Keep Analyze highlighted throughout the verification workflow.
  const activePage=page.startsWith('verify-')?'analyze':page;
  $$('.nav-links button').forEach(b=>b.classList.toggle('active', b.dataset.nav===activePage));
}
window.navigate = navigate;

/* ---------- news card ---------- */
function imageUploadButton(context, label='UPLOAD NEWS SCREENSHOT'){
  return `<button class="btn" onclick="document.getElementById('imageUpload-${context}').click()">▣ ${label}</button>
    <input class="hidden" id="imageUpload-${context}" type="file" accept="image/png,image/jpeg,image/webp,image/tiff,image/bmp" onchange="verifyImageInput(this)">`;
}

function cardHTML(a){
  const badge=a.isLive?'LIVE FEED':'DEMO DATA';
  const status=feedVerdictMeta(a);
  const analyze=`<button class="btn btn-sm btn-primary" onclick="verifyArticle('${a.id}')">🔎 ${status.verdict==='MORE VERIFICATION NEEDED'?'VERIFY MORE IN TRUTHSCAN':'VIEW IN-APP EVIDENCE'}</button>`;
  return `<article class="glass card ${status.cls}" onclick="openArticle('${a.id}')">
    <div class="thumb">
      <span class="cat">${esc(a.category)}</span>
      ${a.trending?'<span class="fire">🔥 TRENDING</span>':''}
      <span class="demo-tag">${badge}</span>
      <img src="${esc(a.image)}" onerror="this.onerror=null;this.src='${a.fallbackImage||a.image}'" alt="">
    </div>
    <div class="body">
      <h3>${esc(a.headline)}</h3>
      ${feedVerdictBadge(a)}
      <p class="desc">${esc(a.description)}</p>
      <div class="meta">
        <span>${esc(a.source)}</span><span class="dot"></span><span>${esc(a.time)}</span>
      </div>
      <div class="actions" onclick="event.stopPropagation()">
        <button class="btn btn-sm" onclick="openArticle('${a.id}')">📖 Read</button>
        ${analyze}
      </div>
    </div>
  </article>`;
}

/* =====================================================================
   PAGES
   ===================================================================== */
function renderHome(){
  const trending = ARTICLES.filter(a=>a.trending).slice(0,6);
  const six = trending.length>=6?trending:[...trending,...ARTICLES.filter(a=>!a.trending)].slice(0,6);
  const indiaLive=pickDiverse(ARTICLES.filter(a=>a.isLive&&a.category==='India'),6);
  const recentRumours=state.rumours.items.slice(0,4);
  return `<div class="page">
    <section class="hero wrap">
      <div class="center">
        <div class="eyebrow"><span class="demo-pill"><span class="pulse"></span>${state.live.connected?'LIVE NEWS CONNECTED':'CONNECTING LIVE NEWS'} · EVIDENCE CHECKS</span></div>
        <h1>What's Trending.<br><span class="grad">What's True?</span></h1>
        <p class="lead">Search live reporting or upload a news screenshot to compare its claim against independent coverage.</p>
        <div class="searchbar">
          <span class="mag">🔍</span>
          <input id="homeSearch" placeholder="Search AI, technology, sports, politics, science..." />
          <button class="btn btn-primary" onclick="doHomeSearch()">SEARCH</button>
        </div>
        <div class="hero-actions">
          ${imageUploadButton('home','VERIFY SCREENSHOT')}
          <button class="btn" onclick="navigate('trending')">🔥 Explore Trending</button>
          <button class="btn" onclick="refreshEverything()">↻ Refresh Everything</button>
          <button class="btn btn-primary" onclick="navigate('analyze')">🔎 Verify News</button>
        </div>
        <div class="stats">
          <div class="stat reveal"><b>${ARTICLES.filter(a=>a.isLive).length}</b><span>Live headlines loaded</span></div>
          <div class="stat reveal" style="animation-delay:.08s"><b>${state.live.connected?'Online':'Fallback'}</b><span>Feed service status</span></div>
          <div class="stat reveal" style="animation-delay:.16s"><b>Hybrid</b><span>Google + publisher RSS</span></div>
          <div class="stat reveal" style="animation-delay:.24s"><b>Evidence</b><span>Cross-source verification</span></div>
        </div>
      </div>
    </section>

    <div class="spacer"></div>

    <section class="wrap">
      <div class="section-head">
        <h2>🔥 Top Trending News</h2>
        <span class="sub">${state.live.loading?'Updating feeds…':state.live.connected?'Live aggregated headlines':'Demo fallback'}</span>
      </div>
      ${state.live.warning?`<p style="color:var(--muted);font-size:12px;margin:-8px 0 14px">Feed note: ${esc(state.live.warning)}</p>`:''}
      <div class="cards">${six.map(cardHTML).join('')}</div>
    </section>

    ${indiaLive.length?`<div class="spacer"></div><section class="wrap"><div class="section-head"><h2>🇮🇳 India Live</h2><span class="sub">Multi-publisher coverage</span></div><div class="source-strip"><b>CONNECTED:</b><span>Aaj Tak</span><span>Zee News</span><span>NDTV</span><span>India Today</span><span>ABP</span><span>News18</span><span>TOI</span><span>The Hindu</span><span>Times Now</span><span>TV9</span><span>+ regional sources</span></div><div class="cards">${indiaLive.map(cardHTML).join('')}</div><div style="text-align:right;margin-top:14px"><button class="btn btn-sm" onclick="navigate('search',{search:{q:'',cat:'India',sort:'Newest'}})">View all India coverage →</button></div></section>`:''}

    <div class="spacer"></div>

    <section class="wrap rumour-home-section">
      <div class="section-head"><div><h2>⚠ Latest Rumours & Fact Checks</h2><p class="section-deck">Reviews published in the latest ${state.rumours.recencyDays||14} days only.</p></div><div class="section-actions"><button class="btn btn-sm" onclick="refreshRumours()" ${state.rumours.refreshing?'disabled':''}>${state.rumours.refreshing?'Refreshing…':'↻ Refresh'}</button><button class="btn btn-sm btn-primary" onclick="navigate('rumours')">View all reviews →</button></div></div>
      ${state.rumours.error?`<div class="feed-alert">${esc(state.rumours.error)}</div>`:''}
      ${recentRumours.length?`<div class="rumour-grid compact">${recentRumours.map(rumourCard).join('')}</div>`:`<div class="glass search-pending"><div class="search-spinner"></div><div><h3>Loading recent fact checks…</h3><p>Connecting to India-focused misinformation review feeds.</p></div></div>`}
    </section>

    <div class="spacer"></div>

    <section class="wrap">
      <div class="section-head"><h2># Trending Topics</h2><span class="sub">Tap to search</span></div>
      <div class="topics">
        ${TRENDING_TOPICS.map(t=>`<button class="chip" onclick="topicSearch('${t}')">${esc(t)}</button>`).join('')}
      </div>
    </section>

    <div class="spacer"></div>

    <section class="wrap">
      <div class="section-head"><h2>⚙️ How It Works</h2><span class="sub">Explainable by design</span></div>
      <div class="how">
        ${[
          ['1','Search','Find a news article.'],
          ['2','Read','Open the article.'],
          ['3','Analyze','AI examines the content.'],
          ['4','Check Claims','Important claims are identified.'],
          ['5','Understand','Get an explainable report.'],
        ].map(([n,t,d],i)=>`<div class="step">
          <div class="num">${n}</div><h4>${t}</h4><p>${d}</p>
          ${i<4?'<div class="arrow">→</div>':''}
        </div>`).join('')}
      </div>
    </section>
    ${footer()}
  </div>`;
}

function renderTrending(){
  return `<div class="page wrap">
    <div class="section-head" style="margin-top:34px">
      <h2>🔥 Trending News</h2><div class="section-actions"><span class="sub">${state.live.loading?'Refreshing…':state.live.connected?'Live feeds + labeled demos':'Demo fallback'}</span><button class="btn btn-sm" onclick="refreshEverything()">↻ Refresh Everything</button></div>
    </div>
    <p style="color:var(--muted);margin:-8px 0 22px;max-width:700px">Current headlines are aggregated from Google News discovery and direct publisher feeds. Open a live item to continue to the original publisher.</p>
    <div class="cards">${[...ARTICLES].sort((a,b)=>(Number(Boolean(b.isLive))-Number(Boolean(a.isLive)))||(Number(Boolean(b.trending))-Number(Boolean(a.trending)))).map(cardHTML).join('')}</div>
    ${footer()}
  </div>`;
}

function renderRumours(){
  const items=state.rumours.items;
  const counts=items.reduce((acc,item)=>{const key=feedVerdictMeta(item).verdict;acc[key]=(acc[key]||0)+1;return acc;},{});
  const refreshed=state.rumours.refreshedAt?new Date(state.rumours.refreshedAt).toLocaleString('en-IN'):'Waiting for first refresh';
  return `<div class="page wrap rumours-page">
    <div class="rumours-masthead">
      <div><div class="result-kicker">LATEST · ROLLING ${state.rumours.recencyDays||14}-DAY WINDOW</div><h1>Latest Rumours & Misinformation</h1><p>Only reviews published during the latest ${state.rumours.recencyDays||14} days are shown, from sources including Alt News, BOOM, FACTLY, Newschecker, Vishvas News, and Fact Crescendo. Older items and reviews without a reliable publication date are excluded.</p></div>
      <button class="btn btn-primary refresh-rumours" onclick="refreshRumours()" ${state.rumours.refreshing?'disabled':''}>${state.rumours.refreshing?'Refreshing live feeds…':'↻ REFRESH NOW'}</button>
    </div>
    <div class="rumour-summary">
      <div><b>${items.length}</b><span>reviews from latest ${state.rumours.recencyDays||14} days</span></div>
      <div><b>${counts['DEBUNKED BY FACT-CHECKERS']||0}</b><span>debunked by attributed fact-checkers</span></div>
      <div><b>${counts['SUPPORTED BY VERIFIED NEWS SOURCE']||0}</b><span>supported by a reviewed source</span></div>
      <div><b>${counts['MORE VERIFICATION NEEDED']||0}</b><span>can be checked further inside TRUTHSCAN</span></div>
    </div>
    <div class="rumour-disclosure"><b>Current-only status policy:</b> TRUTHSCAN uses a rolling ${state.rumours.recencyDays||14}-day cutoff and shows one of three feed statuses: Debunked, Supported, or More Verification Needed. Select the in-app evidence button for the complete report; original links remain available for transparent attribution.</div>
    <div class="rumour-toolbar"><span>Last refreshed: ${esc(refreshed)}${state.rumours.lastRefresh?` · ${state.rumours.lastRefresh.new_items||0} new · ${state.rumours.lastRefresh.updated_items||0} refreshed`:''}</span><span>Latest ${state.rumours.recencyDays||14} days · newest first · auto-updates every 5 minutes</span></div>
    ${state.rumours.error?`<div class="feed-alert">${esc(state.rumours.error)}</div>`:''}
    ${state.rumours.loading&&!items.length?`<div class="glass search-pending"><div class="search-spinner"></div><div><h3>Refreshing fact-check feeds…</h3><p>Retrieving the newest published reviews.</p></div></div>`:items.length?`<div class="rumour-grid">${items.map(rumourCard).join('')}</div>`:`<div class="glass empty"><div class="big">⌕</div><h3>No current reviews were retrieved</h3><p>Try Refresh Now. A temporary empty feed does not mean there are no circulating rumours.</p></div>`}
    ${state.rumours.warnings.length?`<details class="glass feed-warnings"><summary>Source warnings (${state.rumours.warnings.length})</summary><ul>${state.rumours.warnings.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}
    ${footer()}
  </div>`;
}

function renderAnalyze(){
  const live=ARTICLES.filter(a=>a.isLive).slice(0,9);
  return `<div class="page wrap">
    <div class="section-head" style="margin-top:34px"><h2>🔎 Verify News</h2><span class="sub">Live evidence analysis</span></div>
    <p class="search-intro">Submit the news you actually want checked. TRUTHSCAN extracts its central claim and compares it with current reporting from independent publishers.</p>
    <div class="verify-input-grid">
      <div class="glass panel verify-input-card">
        <div class="verify-icon">Aa</div>
        <h3>Headline, claim, or news URL</h3>
        <p class="phint">Paste a headline, claim, news URL, YouTube/Shorts, TikTok, X, Reddit, or an approved-access Meta post link.</p>
        <textarea id="pasteInput" class="verify-textarea" placeholder="Paste a social-media link, news URL, headline, or claim…"></textarea>
        <button class="btn btn-primary btn-block" onclick="verifySubmittedText()">SEARCH & VERIFY EVIDENCE</button>
      </div>
      <div class="glass panel verify-input-card">
        <div class="verify-icon">▣</div>
        <h3>News screenshot</h3>
        <p class="phint">Upload a screenshot from a website, message, YouTube, Facebook, or Instagram. The image is processed temporarily and not retained.</p>
        <input id="imageClaim" class="manual-claim" placeholder="Optional: type the headline if the screenshot is unclear">
        <div class="upload-zone" ondragover="event.preventDefault();this.classList.add('drag')" ondragleave="this.classList.remove('drag')" ondrop="handleImageDrop(event)">
          <div class="upload-mark">⇧</div>
          <b>Drop screenshot here</b>
          <span>PNG, JPEG, WebP, TIFF or BMP · max 10 MB</span>
          ${imageUploadButton('analyze','CHOOSE SCREENSHOT')}
        </div>
      </div>
    </div>
    <div class="verify-method-note"><b>Live link support:</b> YouTube/Shorts, TikTok, X, Reddit, and public news pages. Configured X API access is used before the public fallback. Approved Meta Graph API access can read permitted Facebook Page content and media from an authorized Instagram professional account; other Meta links require a screenshot or pasted caption. Every report states which access path actually ran.</div>
    <div class="section-head" style="margin-top:34px"><h2 style="font-size:21px">Current News You Can Verify</h2><span class="sub">${state.live.loading?'Updating feeds…':`${live.length} live articles`}</span></div>
    ${live.length?`<div class="cards">${live.map(cardHTML).join('')}</div>`:`<div class="glass search-pending"><div class="search-spinner"></div><div><h3>Loading live articles…</h3><p>Current reports will appear here as soon as the feeds respond.</p></div></div>`}
    ${footer()}
  </div>`;
}

function filterResults(){
  const {q,cat,sort} = state.search;
  let res = state.live.connected ? ARTICLES.filter(a=>a.isLive) : ARTICLES.slice();
  const ql = q.trim().toLowerCase().replace(/^#/,'');
  if(ql){
    res = res.filter(a=>{
      const hay = (a.headline+' '+a.description+' '+a.category+' '+a.keywords.join(' ')+' '+a.topics.join(' ')).toLowerCase();
      return ql.split(/\s+/).some(word => hay.includes(word));
    });
  }
  if(cat!=='All'){
    res = res.filter(a=>a.category===cat || (cat==='World'&&a.category==='World'));
  }
  if(sort==='Newest') res.sort((a,b)=>ARTICLES.indexOf(a)-ARTICLES.indexOf(b));
  else if(sort==='Trending') res.sort((a,b)=>b.trending-a.trending);
  else if(sort==='Most Relevant' && ql){
    res.sort((a,b)=>score(b)-score(a));
    function score(a){const h=a.headline.toLowerCase();return (h.includes(ql)?3:0)+(a.category.toLowerCase().includes(ql)?2:0);}
  }
  return res;
}

function searchFactCheckReviewHTML(review,index){
  const negative=/false|fake|misleading|incorrect|fabricated|altered|morphed|manipulated|unrelated|out of context|no evidence|फर्जी|झूठ|भ्रामक|गलत|फेक/i.test(review.rating||'');
  const positive=/\btrue\b|correct|accurate|supported|सही|सच|सत्य/i.test(review.rating||'');
  const ratingClass=negative?'negative':positive?'positive':'review';
  const rawDate=review.review_date?new Date(review.review_date):null;
  const date=rawDate&&!Number.isNaN(rawDate.getTime())?rawDate.toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'}):'Review date unavailable';
  const url=/^https?:\/\//i.test(review.url||'')?review.url:'#';
  return `<a class="glass search-factcheck-card" href="${esc(url)}" target="_blank" rel="noopener noreferrer">
    <div class="search-factcheck-rank">CLOSEST REVIEW ${index+1}</div>
    <div class="factcheck-top"><span class="factchecker-name">${esc(review.publisher||'Fact checker')}</span><span class="fact-rating ${ratingClass==='negative'?'rating-false':''}">${esc(review.rating||'Review available')}</span></div>
    <h3>${esc(review.title||review.claim_text||'Fact-check review')}</h3>
    ${review.claim_text?`<p><b>Claim reviewed:</b> ${esc(review.claim_text)}</p>`:''}
    <div class="rmeta">${esc(date)}${review.structured?' · Structured publisher rating':' · Attributed fact-check article'}</div>
    <span class="review-link">Read the correcting evidence ↗</span>
  </a>`;
}

function searchAssessmentHTML(cleanQuery){
  const current=state.searchAssessment;
  if(!cleanQuery||current.query.toLowerCase()!==cleanQuery.toLowerCase())return '';
  if(current.loading){
    return `<section class="search-assessment-section"><div class="glass search-pending"><div class="search-spinner"></div><div><h3>Checking the closest fact-check reviews…</h3><p>Comparing “${esc(cleanQuery)}” with attributed reviews from the latest 14 days and live publisher coverage.</p></div></div></section>`;
  }
  if(current.error){
    return `<div class="feed-alert">Fact-check scan note: ${esc(current.error)} Live news matches are still shown below.</div>`;
  }
  const result=current.result;
  if(!result)return '';
  const reviews=result.fact_checks||[];
  const verdict=result.verdict||'NO VERDICT — INSUFFICIENT EVIDENCE';
  const verdictClass=verificationVerdictClass(verdict);
  const isDebunked=verdict==='DEBUNKED BY FACT-CHECKERS';
  const isDisputed=verdict==='DISPUTED OR MIXED';
  const heading=isDebunked?'Closest reviews flag a matching false or misleading claim':isDisputed?'Fact-checkers returned mixed findings for the closest claim':reviews.length?'Fact-check reviews matching this search':'No attributed debunk matched this search';
  return `<section class="search-assessment-section">
    <div class="glass search-verdict ${verdictClass}-panel">
      <div class="provenance-icon ${verdictClass}">${verificationVerdictIcon(verdict)}</div>
      <div><div class="result-kicker">RUMOUR & FACT-CHECK SCAN</div><h2>${heading}</h2><span class="verdict-badge ${verdictClass}">${esc(verdict)}</span><p>${esc(result.summary||'')}</p><small>TRUTHSCAN only shows a debunked outcome when an attributed fact-check review closely matches. Missing coverage is not treated as proof that a claim is fake.</small></div>
      <button class="btn btn-sm btn-primary" onclick="openSearchAssessment()">Open full evidence report</button>
    </div>
    ${reviews.length?`<div class="section-head search-review-head"><div><h2>Closest Current Fact-Check Reviews</h2><p class="section-deck">Published within the latest 14 days, with publisher, rating, correction, and original link.</p></div><span class="sub">${reviews.length} attributed review${reviews.length!==1?'s':''}</span></div><div class="factcheck-list search-factcheck-list">${reviews.map(searchFactCheckReviewHTML).join('')}</div>`:''}
  </section>`;
}

function renderSearch(){
  const {q,cat,sort}=state.search;
  const cleanQuery=q.trim().replace(/^#/,'');
  const remoteMatches=Boolean(cleanQuery)&&state.searchRemote.query.toLowerCase()===cleanQuery.toLowerCase();
  let results=remoteMatches?state.searchRemote.ids.map(getArticle).filter(Boolean):filterResults();
  const sorter={
    'Newest':(a,b)=>new Date(b.publishedAt||0)-new Date(a.publishedAt||0),
    'Trending':(a,b)=>Number(Boolean(b.trending))-Number(Boolean(a.trending))||(b.relevanceScore||0)-(a.relevanceScore||0),
    'Most Relevant':(a,b)=>(b.relevanceScore||0)-(a.relevanceScore||0),
  }[sort];
  if(remoteMatches&&sorter)results=[...results].sort(sorter);
  const assessment=state.searchAssessment.query.toLowerCase()===cleanQuery.toLowerCase()?state.searchAssessment.result:null;
  const reviewUrls=new Set((assessment?.fact_checks||[]).map(review=>String(review.url||'').split('#')[0].replace(/\/$/,'')));
  const indexedReviews=results.filter(item=>item.category==='Fact Check'&&!reviewUrls.has(String(item.url||'').split('#')[0].replace(/\/$/,'')));
  const newsResults=results.filter(item=>item.category!=='Fact Check');
  const best=remoteMatches?newsResults.filter(item=>item.matchType==='best'):[];
  const related=remoteMatches?newsResults.filter(item=>item.matchType!=='best'):[];
  const cats=CATEGORIES;
  const sorts=['Most Relevant','Newest','Trending'];
  let resultsHTML=cleanQuery?searchAssessmentHTML(cleanQuery):'';
  if(cleanQuery&&remoteMatches&&state.searchRemote.loading){
    resultsHTML+=`<div class="glass search-pending"><div class="search-spinner"></div><div><h3>Searching live news sources…</h3><p>Finding the closest headline matches and similar reporting for “${esc(cleanQuery)}”.</p></div></div>`;
  }else if(results.length&&cleanQuery&&remoteMatches){
    if(indexedReviews.length){
      resultsHTML+=`<section class="search-group indexed-review-group"><div class="section-head"><div><h2>Additional Current Fact Checks</h2><p class="section-deck">Closest related reviews published within the rolling 14-day window.</p></div><span class="sub">${indexedReviews.length} review${indexedReviews.length!==1?'s':''}</span></div><div class="grid">${indexedReviews.map(resultHTML).join('')}</div></section>`;
    }
    if(best.length){
      resultsHTML+=`<section class="search-group"><div class="section-head"><h2>Closest News Matches</h2><span class="sub">${best.length} closest result${best.length!==1?'s':''}</span></div><div class="grid">${best.map(resultHTML).join('')}</div></section>`;
    }
    if(related.length){
      resultsHTML+=`<section class="search-group"><div class="section-head"><h2>Similar & Related Coverage</h2><span class="sub">${related.length} report${related.length!==1?'s':''}</span></div><p class="search-note">Other reports sharing the main people, places, organizations, or events in your search. Similarity alone is not a truth verdict.</p><div class="grid">${related.map(resultHTML).join('')}</div></section>`;
    }
  }else if(results.length){
    resultsHTML+=`<div class="section-head"><h2>${cleanQuery?'Results':'Latest Coverage'}</h2><span class="sub">${results.length} article${results.length!==1?'s':''}</span></div><div class="grid">${results.map(resultHTML).join('')}</div>`;
  }else if(!state.searchRemote.loading){
    resultsHTML+=`<div class="glass empty"><div class="big">🔎</div><h3>No indexed coverage found for “${esc(cleanQuery||q)}”</h3><p>${state.searchRemote.error?esc(state.searchRemote.error):'No matching report or attributed fact-check review was found. Try the complete claim, a person or organization name, a place, or fewer words. This absence is not proof that the claim is fake.'}</p>${cleanQuery?`<button class="btn btn-primary" onclick="verifySubmittedText(decodeURIComponent('${encodeURIComponent(cleanQuery).replace(/'/g,'%27')}'))">Run full evidence check</button>`:''}</div>`;
  }
  const assessmentCount=assessment?.fact_checks?.length||0;
  const countLabel=state.searchRemote.loading?'searching news and fact checks':`${results.length} indexed result${results.length!==1?'s':''}${assessmentCount?` · ${assessmentCount} closest fact-check review${assessmentCount!==1?'s':''}`:''}`;
  return `<div class="page wrap">
    <div class="section-head" style="margin-top:34px"><h2>🔎 Search News & Rumours</h2><span class="sub">${countLabel}</span></div>
    <p class="search-intro">Search a headline, event, person, organization, or viral claim. TRUTHSCAN checks live news and fact-check reviews published within the latest 14 days, then displays the closest current matches first.</p>
    <div class="glass panel" style="margin-bottom:26px">
      <div class="searchbar" style="margin-bottom:14px">
        <span class="mag">🔍</span>
        <input id="searchInput" value="${esc(q)}" placeholder="Enter a headline, viral rumour, event, person, place, or claim..." />
        <button class="btn btn-primary" onclick="applySearch()">SEARCH & CHECK</button>
      </div>
      <div class="search-image-row"><span>Have a screenshot instead?</span>${imageUploadButton('search','UPLOAD & VERIFY IMAGE')}</div>
      <div class="filters" style="margin-bottom:12px"><span class="label">CATEGORY</span>${cats.map(c=>`<button class="chip ${c===cat?'active':''}" onclick="setFilter('cat','${c}')">${c}</button>`).join('')}</div>
      <div class="filters"><span class="label">SORT</span>${sorts.map(s=>`<button class="chip ${s===sort?'active':''}" onclick="setFilter('sort','${s}')">${s}</button>`).join('')}</div>
    </div>
    ${resultsHTML}
    ${footer()}
  </div>`;
}
function resultHTML(a){
  const factCheck=a.category==='Fact Check';
  const finding=factCheck?rumourFinding(a):null;
  const status=feedVerdictMeta(a);
  const action=`<button class="btn btn-sm btn-primary" onclick="verifyArticle('${a.id}')">🔎 ${status.verdict==='MORE VERIFICATION NEEDED'?'VERIFY MORE IN TRUTHSCAN':'VIEW IN-APP EVIDENCE'}</button>`;
  return `<article class="glass result ${factCheck?'search-review-result':''} ${status.cls}" onclick="openArticle('${a.id}')">
    <div class="rthumb"><span class="demo-tag" style="position:absolute;top:8px;left:8px;z-index:2">${factCheck?'ATTRIBUTED REVIEW':a.isLive?'LIVE':'DEMO'}</span><img src="${esc(a.image)}" onerror="this.onerror=null;this.src='${a.fallbackImage||a.image}'" alt=""></div>
    <div class="rbody">
      <span class="rcat">${factCheck?esc(finding.label):esc(a.category).toUpperCase()}</span>
      <h3>${esc(a.headline)}</h3>
      ${feedVerdictBadge(a)}
      <div class="rmeta">${esc(a.source)} · ${esc(a.author)} · ${esc(a.date)}</div>
      <p class="rdesc">${esc(a.description)}</p>
      <div class="ractions" onclick="event.stopPropagation()">
        <button class="btn btn-sm" onclick="openArticle('${a.id}')">${factCheck?'⚖ Read Fact Check':'📖 Read Article'}</button>
        ${action}
      </div>
    </div>
  </article>`;
}

function renderArticle(id){
  const a=getArticle(id); if(!a) return renderHome();
  const status=feedVerdictMeta(a);
  const liveActions=a.isLive
    ? `<div class="disclaimer" style="margin-bottom:14px">ℹ️ <span>The core evidence report stays inside TRUTHSCAN. Original publisher links remain available for attribution, transparency, and full context.</span></div>
       <button class="btn btn-primary btn-lg btn-block" onclick="verifyArticle('${a.id}')">🔎 ${status.verdict==='MORE VERIFICATION NEEDED'?'VERIFY MORE INSIDE TRUTHSCAN':'OPEN COMPLETE IN-APP EVIDENCE'}</button>
       <a class="btn btn-lg btn-block" style="margin-top:10px" href="${esc(/^https?:\/\//i.test(a.url||'')?a.url:'#')}" target="_blank" rel="noopener noreferrer">↗ OPTIONAL: READ ORIGINAL AT ${esc(a.source.toUpperCase())}</a>`
    : `<button class="btn btn-primary btn-lg btn-block" onclick="verifyArticle('${a.id}')">🔎 VERIFY MORE INSIDE TRUTHSCAN</button>`;
  return `<div class="page wrap"><div class="article">
    <div class="backbar">
      <button class="btn btn-sm btn-ghost" onclick="history.back(); navigate('search')">← Back</button>
      <span class="demo-pill"><span class="pulse"></span>${a.isLive?'LIVE FEED ARTICLE':'DEMO ARTICLE'}</span>
    </div>
    <img class="hero-img" src="${esc(a.image)}" onerror="this.onerror=null;this.src='${a.fallbackImage||a.image}'" alt="">
    <h1>${esc(a.headline)}</h1>
    <div class="amETA">
      <span class="cat-tag">${esc(a.category).toUpperCase()}</span>
      <span>🏢 ${esc(a.source)}</span><span>·</span><span>✍️ ${esc(a.author)}</span><span>·</span><span>🕒 ${esc(a.date)} (${esc(a.time)})</span>
    </div>
    <div class="article-feed-verdict ${status.cls}">${feedVerdictBadge(a)}<p>${esc(status.reason)}</p><small>Feed-level status · a complete in-app evidence check can supersede it.</small></div>
    <div class="content" style="margin-top:20px">
      ${a.body.map(p=>`<p>${esc(p)}</p>`).join('')}
    </div>
    <div class="section-head" style="margin-top:26px"><h2 style="font-size:16px">Related Topics</h2></div>
    <div class="rel-topics">${a.topics.map(t=>`<button class="chip" onclick="topicSearch('${esc(t)}')">${esc(t)}</button>`).join('')}</div>
    <div style="margin:34px 0 10px">${liveActions}</div>
  </div>${footer()}</div>`;
}

function verificationVerdictClass(verdict){
  if(verdict==='SUPPORTED BY MULTIPLE SOURCES'||verdict==='SUPPORTED BY A VERIFIED NEWS SOURCE') return 'v-credible';
  if(verdict==='DEBUNKED BY FACT-CHECKERS') return 'v-mislead';
  return 'v-verify';
}
function verificationVerdictIcon(verdict){
  if(verdict==='SUPPORTED BY MULTIPLE SOURCES'||verdict==='SUPPORTED BY A VERIFIED NEWS SOURCE') return '✓';
  if(verdict==='DEBUNKED BY FACT-CHECKERS') return '✕';
  if(verdict==='DISPUTED OR MIXED') return '⇄';
  if(verdict.startsWith('REPORTED BY')) return 'i';
  return '?';
}

function renderVerificationLoading(){
  return `<div class="page wrap"><div class="glass analyze-load verify-load">
    <div class="scanner"><div class="ring"></div><div class="ring r2"></div><div class="spin"></div><div class="spin s2"></div><div class="core">🔎</div></div>
    <h2>Running live checks…</h2>
    <p class="lead">${esc(state.verification.inputLabel||'Evidence search')}</p>
    <div class="live-request-status"><div class="search-spinner"></div><div><b>${esc(state.verification.stage||'Backend verification request is in progress')}</b><span>Long YouTube videos may switch to Gemini background processing before publisher and fact-check searches run.</span></div></div>
    <p style="color:var(--muted-2);font-size:12px;margin-top:22px">No simulated step completion is shown. This page reports the backend job’s current state and lists only checks that actually completed.</p>
  </div></div>`;
}

function renderSocialContext(sc){
  const claims=sc.extracted_claims||[];
  const visible=sc.visible_text||[];
  const analyzed=Boolean(sc.audiovisual_content_analyzed);
  const status=analyzed?'ACTUAL VIDEO CONTENT ANALYZED':'METADATA / CAPTION ONLY';
  return `<div class="glass social-context-card">
    <div class="social-platform">${esc(sc.platform)}</div>
    <div><div class="result-kicker">LIVE PUBLIC POST RETRIEVED</div><h3>${esc(sc.title)}</h3><p>${sc.author?'Published by '+esc(sc.author)+' · ':''}${esc(sc.resolver)}</p><small>Retrieved ${new Date(sc.retrieved_at).toLocaleString('en-IN')}</small></div>
    <a class="btn btn-sm" href="${esc(sc.source_url)}" target="_blank" rel="noopener noreferrer">Open post ↗</a>
    ${sc.official_api_note?`<div class="social-api-status ${sc.official_api_access_used?'api-used':'api-fallback'}"><b>${sc.official_api_access_used?'✓ OFFICIAL API ACCESS USED':'API FALLBACK DISCLOSED'}</b><span>${esc(sc.official_api_note)}</span></div>`:''}
    <div class="social-analysis ${analyzed?'analyzed':'metadata-only'}">
      <div class="social-analysis-head"><span>${analyzed?'✓':'i'}</span><b>${status}</b>${sc.content_analysis_provider?`<small>${esc(sc.content_analysis_provider)}</small>`:''}</div>
      ${sc.content_summary?`<p>${esc(sc.content_summary)}</p>`:''}
      ${claims.length?`<div class="social-extract"><b>Claims extracted from the audio/frames (the first is searched in this report)</b><ol>${claims.map(x=>`<li>${esc(x)}</li>`).join('')}</ol></div>`:''}
      ${visible.length?`<details><summary>Visible on-screen text detected</summary><ul>${visible.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}
      ${sc.content_analysis_notes?`<small class="social-caveat">Analysis note: ${esc(sc.content_analysis_notes)}</small>`:''}
      ${sc.content_analysis_error?`<small class="social-caveat">${esc(sc.content_analysis_error)}</small>`:''}
    </div>
  </div>`;
}

function renderVerificationResult(){
  const r=state.verification.result;
  if(!r){
    return `<div class="page wrap"><div class="glass empty" style="margin-top:42px"><div class="big">⚠️</div><h3>Verification could not be completed</h3><p>${esc(state.verification.error||'An unexpected error occurred.')}</p><button class="btn btn-primary" onclick="navigate('analyze')">Try Another Item</button></div>${footer()}</div>`;
  }
  const reported=(r.reported_by||[]);
  const recognizedReported=reported.filter(item=>item.recognized_publisher);
  const factChecks=(r.fact_checks||[]);
  return `<div class="page wrap">
    <div class="backbar" style="margin-top:26px"><button class="btn btn-sm btn-ghost" onclick="navigate('analyze')">← Verify another item</button><span class="demo-pill"><span class="pulse"></span>PROVENANCE REPORT</span></div>
    <div class="glass provenance-head ${verificationVerdictClass(r.verdict)}-panel" style="margin-bottom:20px">
      <div class="provenance-icon ${verificationVerdictClass(r.verdict)}">${verificationVerdictIcon(r.verdict)}</div>
      <div><div class="result-kicker">EVIDENCE-BASED OUTCOME · NO CONFIDENCE SCORE</div><span class="verdict-badge ${verificationVerdictClass(r.verdict)}">${esc(r.verdict)}</span><p class="verify-summary">${esc(r.summary)}</p><div class="provenance-counts"><span><b>${reported.length}</b> matching publishers shown</span><span><b>${factChecks.length}</b> fact-check reviews found</span><span><b>${esc(r.input_type.toUpperCase())}</b> input</span></div></div>
    </div>
    <div class="glass panel claim-focus"><div class="result-kicker">CLAIM SEARCHED</div><h2>“${esc(r.query)}”</h2>${r.extracted_text?`<details><summary>View ${r.input_type==='image'?'text extracted from screenshot':r.input_type==='social'&&r.social_context?.audiovisual_content_analyzed?'claims extracted from the video':r.input_type==='social'?'live social caption/title':'submitted text'}</summary><pre>${esc(r.extracted_text)}</pre><small>${esc(r.extraction_method||'Text extraction')}</small></details>`:''}</div>
    ${r.social_context?renderSocialContext(r.social_context):''}
    ${r.real_context?`<div class="glass real-context"><div class="real-context-label">WHAT THE EVIDENCE ESTABLISHES</div><p>${esc(r.real_context)}</p></div>`:''}

    <section class="evidence-section factcheck-section"><div class="section-head"><h2>Who Fact-Checked or Debunked It?</h2><span class="sub">${factChecks.length} attributed review${factChecks.length!==1?'s':''}</span></div>
      ${factChecks.length?`<div class="factcheck-list">${factChecks.map(f=>`<a class="glass factcheck-item" href="${esc(/^https?:\/\//i.test(f.url||'')?f.url:'#')}" target="_blank" rel="noopener noreferrer"><div class="factcheck-top"><span class="factchecker-name">${esc(f.publisher)}</span><span class="fact-rating ${/false|fake|misleading|incorrect|फर्जी|गलत|भ्रामक/i.test(f.rating)?'rating-false':''}">${esc(f.rating)}</span></div><h3>${esc(f.title)}</h3>${f.claim_text?`<p><b>Claim reviewed:</b> ${esc(f.claim_text)}</p>`:''}<div class="rmeta">${f.review_date?new Date(f.review_date).toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'}):'Review date unavailable'}${f.site?' · '+esc(f.site):''}${f.structured?' · Structured ClaimReview rating':' · Fact-check article discovery'}</div><span class="review-link">Read the full fact check ↗</span></a>`).join('')}</div>`:`<div class="glass empty compact-empty"><div class="big">⌕</div><h3>No attributed fact-check review found</h3><p>This means no connected fact-check source matched the claim; it does not mean the claim is true.</p></div>`}
    </section>

    <section class="evidence-section"><div class="section-head"><h2>Who Reported This News?</h2><span class="sub">${reported.length} publisher${reported.length!==1?'s':''}</span></div>
      ${reported.length?`<p class="search-note">${recognizedReported.length?`${recognizedReported.length} result${recognizedReported.length!==1?'s':''} came from TRUTHSCAN’s reviewed source registry. One strongly matching verified source is enough for provisional support unless an attributed correction or debunk is found.`:'Named coverage was found, but no result matched TRUTHSCAN’s reviewed source registry strongly enough for the one-source supported policy.'}</p><div class="evidence-list">${reported.map(e=>`<a class="glass evidence-item" href="${esc(/^https?:\/\//i.test(e.url||'')?e.url:'#')}" target="_blank" rel="noopener noreferrer"><div><div class="evidence-badges"><span class="publisher-badge">${esc(e.source)}</span>${e.recognized_publisher?'<span class="recognized-badge">✓ VERIFIED NEWS SOURCE</span>':''}</div><h3>${esc(e.headline)}</h3><p>${esc(e.description||'Open the publisher report for full context.')}</p><div class="rmeta">${e.published_at?timeAgo(e.published_at):'Recent'} · ${esc(e.category||'News')}</div></div><span class="open-source">↗</span></a>`).join('')}</div>`:`<div class="glass empty compact-empty"><div class="big">?</div><h3>No independent matching publisher found</h3><p>The claim may be local, breaking, private, incorrectly worded, or not yet indexed. No fake/real label has been inferred.</p></div>`}
    </section>

    <div class="analysis-grid" style="margin-top:24px"><div class="glass panel"><h3>🧭 Evidence Summary</h3><div class="signal-list">${(r.signals||[]).map(s=>`<div class="verify-signal sig-${s.status}"><span>${s.status==='support'?'✓':s.status==='warning'?'⚠':'i'}</span><div><b>${esc(s.title)}</b><p>${esc(s.detail)}</p></div></div>`).join('')}</div></div><div class="glass panel"><h3>✓ Checks Performed</h3><ul class="check-list">${(r.checks_performed||[]).map(c=>`<li>✓ ${esc(c)}</li>`).join('')}</ul></div></div>
    <div class="glass panel limitations"><h3>Important Limitations</h3><ul>${(r.limitations||[]).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>
    <div class="verify-again"><button class="btn btn-primary" onclick="navigate('analyze')">Verify Another News Item</button>${imageUploadButton('result','UPLOAD ANOTHER SCREENSHOT')}</div>
    ${footer()}
  </div>`;
}

function renderSignup(){
  const mode=state.auth.mode||'signup';
  if(state.user&&mode!=='reset'){
    const joined=state.user.created_at?new Date(state.user.created_at).toLocaleDateString('en-IN',{day:'numeric',month:'long',year:'numeric'}):'Recently';
    const verified=Boolean(state.user.email_verified);
    return `<div class="page wrap account-page"><div class="account-shell signed-in-shell">
      <div class="account-editorial"><div class="result-kicker">TRUTHSCAN ACCOUNT</div><h1>Your verification workspace</h1><p>Your account uses a secure server-side session. Passwords are stored only as salted PBKDF2 hashes, never as readable text.</p><ul><li>One-time email verification</li><li>Secure password recovery</li><li>Revocable HttpOnly session</li></ul></div>
      <div class="glass account-card"><div class="account-avatar-large">${esc(String(state.user.name||'U').charAt(0).toUpperCase())}</div><h2>${esc(state.user.name)}</h2><p>${esc(state.user.email)}</p>
        <span class="verification-badge ${verified?'verified':'unverified'}">${verified?'✓ EMAIL VERIFIED':'! EMAIL NOT VERIFIED'}</span>
        ${state.auth.error?`<div class="auth-message error">${esc(state.auth.error)}</div>`:''}${state.auth.message?`<div class="auth-message success">${esc(state.auth.message)}</div>`:''}
        ${state.auth.actionUrl?`<a class="development-link" href="${esc(state.auth.actionUrl)}">Open one-time development link</a>`:''}
        <div class="account-facts"><span><b>Member since</b>${esc(joined)}</span><span><b>Session</b>Secure HttpOnly cookie</span></div>
        ${!verified?`<button class="btn btn-block" onclick="resendVerification()" ${state.auth.loading?'disabled':''}>${state.auth.loading?'Preparing link…':'Resend verification email'}</button>`:''}
        <button class="btn btn-block" onclick="logoutAccount()">Sign out</button><button class="btn btn-primary btn-block" onclick="navigate('home')">Continue to TRUTHSCAN</button></div>
    </div>${footer()}</div>`;
  }
  const signup=mode==='signup',login=mode==='login',forgot=mode==='forgot',reset=mode==='reset';
  const title=signup?'Sign up':login?'Sign in to TRUTHSCAN':forgot?'Recover your account':'Set a new password';
  const kicker=signup?'NEW ACCOUNT':login?'WELCOME BACK':forgot?'PASSWORD RECOVERY':'SECURE RESET';
  const socialEnabled=state.auth.providers.google||state.auth.providers.meta;
  return `<div class="page wrap account-page"><div class="account-shell">
    <div class="account-editorial"><div class="result-kicker">JOIN TRUTHSCAN</div><h1>Save your place in the evidence desk.</h1><p>Create a securely verified identity for future saved reports, alerts, and personalization. News search and verification remain available without an account.</p><ul><li>Verified email ownership</li><li>One-time password-reset links</li><li>Rate-limited authentication</li><li>Google and Meta OAuth when configured</li></ul></div>
    <div class="glass auth-card">
      ${!forgot&&!reset?`<div class="auth-tabs"><button class="${signup?'active':''}" onclick="setAuthMode('signup')">Create account</button><button class="${login?'active':''}" onclick="setAuthMode('login')">Sign in</button></div>`:`<button class="auth-back" onclick="setAuthMode('login')">← Back to sign in</button>`}
      <div><div class="result-kicker">${kicker}</div><h2>${title}</h2></div>
      ${state.auth.error?`<div class="auth-message error">${esc(state.auth.error)}</div>`:''}${state.auth.message?`<div class="auth-message success">${esc(state.auth.message)}</div>`:''}
      ${state.auth.actionUrl?`<a class="development-link" href="${esc(state.auth.actionUrl)}">Open one-time development link</a>`:''}
      ${forgot?`<form class="auth-form" onsubmit="submitForgotPassword(event)"><p class="password-note">Enter your account email. We will prepare a one-time link that expires after 30 minutes.</p><label>Email address<input id="authEmail" type="email" autocomplete="email" maxlength="254" required placeholder="you@example.com"></label><button class="btn btn-primary btn-block" type="submit" ${state.auth.loading?'disabled':''}>${state.auth.loading?'PREPARING…':'SEND RESET LINK'}</button></form>`:
      reset?`<form class="auth-form" onsubmit="submitPasswordReset(event)"><label>New password<input id="authPassword" type="password" autocomplete="new-password" minlength="8" maxlength="128" required placeholder="At least 8 characters"></label><label>Confirm new password<input id="authConfirm" type="password" autocomplete="new-password" minlength="8" maxlength="128" required placeholder="Repeat your password"></label><button class="btn btn-primary btn-block" type="submit" ${state.auth.loading?'disabled':''}>${state.auth.loading?'RESETTING…':'RESET PASSWORD'}</button></form>`:
      `<form class="auth-form" onsubmit="${signup?'submitSignup(event)':'submitLogin(event)'}">
        ${signup?`<label>Full name<input id="authName" autocomplete="name" minlength="2" maxlength="80" required placeholder="Your name"></label>`:''}
        <label>Email address<input id="authEmail" type="email" autocomplete="email" maxlength="254" required placeholder="you@example.com"></label>
        <label>Password<input id="authPassword" type="password" autocomplete="${signup?'new-password':'current-password'}" minlength="8" maxlength="128" required placeholder="At least 8 characters"></label>
        ${signup?`<label>Confirm password<input id="authConfirm" type="password" autocomplete="new-password" minlength="8" maxlength="128" required placeholder="Repeat your password"></label><p class="password-note">Use a unique password of at least 8 characters.</p>`:`<button type="button" class="forgot-link" onclick="setAuthMode('forgot')">Forgot your password?</button>`}
        <button class="btn btn-primary btn-block" type="submit" ${state.auth.loading?'disabled':''}>${state.auth.loading?'Please wait…':signup?'CREATE SECURE ACCOUNT':'SIGN IN'}</button>
      </form>
      <div class="auth-divider"><span>OR CONTINUE WITH</span></div>
      <div class="social-auth"><button class="social-auth-btn" onclick="startSocialLogin('google')" ${state.auth.providers.google?'':'disabled'}><b>G</b><span>Google${state.auth.providers.google?'':' · setup required'}</span></button><button class="social-auth-btn" onclick="startSocialLogin('meta')" ${state.auth.providers.meta?'':'disabled'}><b>f</b><span>Meta${state.auth.providers.meta?'':' · setup required'}</span></button></div>
      ${!socialEnabled?'<p class="provider-note">Social login stays disabled until real provider credentials are installed on the backend.</p>':''}`}
      <p class="auth-privacy">Verification and reset tokens are one-time, expire automatically, and are never stored in browser storage. Provider and SMTP secrets stay on the server.</p>
    </div>
  </div>${footer()}</div>`;
}
function renderHistory(){
  const items=state.verificationHistory;
  return `<div class="page wrap"><div class="section-head" style="margin-top:34px"><h2>🗂️ Verification History</h2><span class="sub">${items.length} evidence report${items.length!==1?'s':''}</span></div><p style="color:var(--muted);margin:-8px 0 22px">Reports created in this browser session. No confidence percentages are used.</p>${items.length?`<div class="grid">${items.map((r,i)=>`<button class="glass provenance-history" onclick="openVerificationHistory(${i})"><span class="provenance-icon ${verificationVerdictClass(r.verdict)}">${verificationVerdictIcon(r.verdict)}</span><span><b>${esc(r.query)}</b><small>${esc(r.verdict)} · ${(r.reported_by||[]).length} publishers · ${(r.fact_checks||[]).length} fact checks</small></span><span class="open-source">→</span></button>`).join('')}</div>`:`<div class="glass empty"><div class="big">🗂️</div><h3>No verification reports yet</h3><p>Verify a headline, live article, URL, or screenshot to build your evidence history.</p><button class="btn btn-primary" onclick="navigate('analyze')">Verify News</button></div>`}${footer()}</div>`;
}

function openVerificationHistory(index){
  const result=state.verificationHistory[index];
  if(!result)return;
  state.verification={loading:false,result,error:'',inputLabel:'History'};
  navigate('verify-result');
}
window.openVerificationHistory=openVerificationHistory;

/* Legacy simulated score screens removed: live reports use attributed provenance. */

/* ---------- footer ---------- */
function footer(){
  return `<footer class="footer wrap">
    <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;justify-content:space-between">
      <div><span class="fbrand">TRUTHSCAN AI</span> — Discover What's Trending. Verify What You Read.</div>
      <span class="demo-pill"><span class="pulse"></span>LIVE HEADLINES · EVIDENCE CHECKS · NOT DEFINITIVE</span>
    </div>
    <p style="margin:14px 0 0;max-width:780px">Live headlines and summaries remain the property of their publishers. Verification reports measure cross-source evidence and disclose their limitations; they are not absolute declarations of truth. Open original and primary sources before making consequential decisions.</p>
  </footer>`;
}

/* =====================================================================
   RENDER dispatcher
   ===================================================================== */
function render(opts={}){
  let html='';
  switch(state.page){
    case 'home': html=renderHome(); break;
    case 'trending': html=renderTrending(); break;
    case 'rumours': html=renderRumours(); break;
    case 'search': html=renderSearch(); break;
    case 'analyze': html=renderAnalyze(); break;
    case 'verify-loading': html=renderVerificationLoading(); break;
    case 'verify-result': html=renderVerificationResult(); break;
    case 'signup': html=renderSignup(); break;
    case 'history': html=renderHistory(); break;
    case 'article': html=renderArticle(opts.id||state._articleId); break;
    default: html=renderHome();
  }
  app.innerHTML=html;

  // hydrate special pages
  if(state.page==='home'){
    const inp=$('#homeSearch'); if(inp) inp.addEventListener('keydown',e=>{if(e.key==='Enter')doHomeSearch();});
  }
  if(state.page==='search'){
    const inp=$('#searchInput'); if(inp){inp.addEventListener('keydown',e=>{if(e.key==='Enter')applySearch();}); inp.focus(); inp.setSelectionRange(inp.value.length,inp.value.length);}
  }
  if(state.page==='analyze'){
    const inp=$('#pasteInput'); if(inp) inp.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();verifySubmittedText();}});
  }
}

/* =====================================================================
   ACTIONS
   ===================================================================== */
function setAuthMode(mode){
  const allowed=['signup','login','forgot','reset'];
  state.auth={...state.auth,mode:allowed.includes(mode)?mode:'signup',loading:false,error:'',message:'',actionUrl:''};
  render();
}
window.setAuthMode=setAuthMode;

function authError(payload,fallback){
  if(typeof payload?.detail==='string')return payload.detail;
  if(Array.isArray(payload?.detail)&&payload.detail[0]?.msg)return payload.detail[0].msg;
  return fallback;
}

async function submitSignup(event){
  event.preventDefault();
  const name=$('#authName').value.trim(),email=$('#authEmail').value.trim();
  const password=$('#authPassword').value,confirm=$('#authConfirm').value;
  if(password!==confirm){state.auth={...state.auth,error:'Passwords do not match.',message:''};render();return;}
  state.auth={...state.auth,loading:true,error:'',message:''};render();
  try{
    const response=await fetch('/api/v1/auth/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,email,password})});
    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(authError(payload,'Could not create account.'));
    state.user=payload.user;
    state.auth={...state.auth,mode:'signup',loading:false,error:'',message:payload.message||'Account created.',actionUrl:payload.action_url||''};
    updateNavUser();toast('Account created securely');render();
  }catch(error){state.auth={...state.auth,mode:'signup',loading:false,error:error.message||'Could not create account.',message:'',actionUrl:''};render();}
}
window.submitSignup=submitSignup;

async function submitLogin(event){
  event.preventDefault();
  const email=$('#authEmail').value.trim(),password=$('#authPassword').value;
  state.auth={...state.auth,loading:true,error:'',message:''};render();
  try{
    const response=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password})});
    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(authError(payload,'Could not sign in.'));
    state.user=payload.user;
    state.auth={...state.auth,mode:'login',loading:false,error:'',message:payload.message||'Signed in.',actionUrl:''};
    updateNavUser();toast('Signed in successfully');render();
  }catch(error){state.auth={...state.auth,mode:'login',loading:false,error:error.message||'Could not sign in.',message:'',actionUrl:''};render();}
}
window.submitLogin=submitLogin;

async function logoutAccount(){
  try{await fetch('/api/v1/auth/logout',{method:'POST'});}catch(_){}
  state.user=null;state.auth={...state.auth,mode:'login',loading:false,error:'',message:'You have been signed out.',actionUrl:'',resetToken:''};
  updateNavUser();render();toast('Signed out');
}
window.logoutAccount=logoutAccount;

async function resendVerification(){
  if(!state.user?.email)return;
  state.auth={...state.auth,loading:true,error:'',message:'',actionUrl:''};render();
  try{
    const response=await fetch('/api/v1/auth/resend-verification',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:state.user.email})});
    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(authError(payload,'Could not prepare a verification link.'));
    state.auth={...state.auth,loading:false,error:'',message:payload.message,actionUrl:payload.action_url||''};
  }catch(error){state.auth={...state.auth,loading:false,error:error.message||'Could not prepare a verification link.',message:'',actionUrl:''};}
  render();
}
window.resendVerification=resendVerification;

async function submitForgotPassword(event){
  event.preventDefault();
  const email=$('#authEmail').value.trim();
  state.auth={...state.auth,loading:true,error:'',message:'',actionUrl:''};render();
  try{
    const response=await fetch('/api/v1/auth/forgot-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});
    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(authError(payload,'Could not prepare a password-reset link.'));
    state.auth={...state.auth,loading:false,error:'',message:payload.message,actionUrl:payload.action_url||''};
  }catch(error){state.auth={...state.auth,loading:false,error:error.message||'Could not prepare a password-reset link.',message:'',actionUrl:''};}
  render();
}
window.submitForgotPassword=submitForgotPassword;

async function submitPasswordReset(event){
  event.preventDefault();
  const password=$('#authPassword').value,confirm=$('#authConfirm').value;
  if(password!==confirm){state.auth={...state.auth,error:'Passwords do not match.',message:''};render();return;}
  state.auth={...state.auth,loading:true,error:'',message:'',actionUrl:''};render();
  try{
    const response=await fetch('/api/v1/auth/reset-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:state.auth.resetToken,password})});
    const payload=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(authError(payload,'Could not reset the password.'));
    state.user=null;
    state.auth={...state.auth,mode:'login',loading:false,error:'',message:payload.message||'Password reset successfully.',actionUrl:'',resetToken:''};
    updateNavUser();toast('Password reset successfully');
  }catch(error){state.auth={...state.auth,loading:false,error:error.message||'Could not reset the password.',message:''};}
  render();
}
window.submitPasswordReset=submitPasswordReset;

function startSocialLogin(provider){
  if(!['google','meta'].includes(provider)||!state.auth.providers[provider])return;
  location.href=`/api/v1/auth/oauth/${provider}/start`;
}
window.startSocialLogin=startSocialLogin;

function doHomeSearch(){
  const q=$('#homeSearch').value.trim();
  navigate('search',{search:{q, cat:'All', sort:'Most Relevant'}});
  loadLiveNews({q,category:'All'});
  loadSearchAssessment(q);
}
window.doHomeSearch=doHomeSearch;

function topicSearch(t){
  const q=t.replace(/^#/,'');
  navigate('search',{search:{q:t, cat:'All', sort:'Most Relevant'}});
  loadLiveNews({q,category:'All'});
  loadSearchAssessment(q);
  toast('Searching live news and fact checks for '+t);
}
window.topicSearch=topicSearch;

function applySearch(){
  const q=$('#searchInput').value.trim();
  state.search.q=q;
  state.search.sort='Most Relevant';
  if(!q){
    state.searchRemote={query:'',loading:false,ids:[],bestCount:0,relatedCount:0,error:'',requestKey:''};
    state.searchAssessment={query:'',loading:false,result:null,error:'',requestKey:''};
    render();
    return;
  }
  render();
  loadLiveNews({q,category:state.search.cat});
  loadSearchAssessment(q);
}
window.applySearch=applySearch;

function setFilter(key,val){
  state.search[key]=val;
  render();
  if(key==='cat') loadLiveNews({q:state.search.q.replace(/^#/,''),category:val});
}
window.setFilter=setFilter;

function openSearchAssessment(){
  const result=state.searchAssessment.result;
  if(!result){toast('The fact-check scan is still running.');return;}
  state.verificationHistory.unshift(result);
  state.verificationHistory=state.verificationHistory.slice(0,20);
  state.verification={loading:false,result,error:'',inputLabel:`Search · ${state.searchAssessment.query}`};
  navigate('verify-result');
}
window.openSearchAssessment=openSearchAssessment;

function openArticle(id){
  state._articleId=id;
  navigate('article',{id});
}
window.openArticle=openArticle;

async function runVerification(url, options, inputLabel){
  state.verification={loading:true,result:null,error:'',inputLabel};
  navigate('verify-loading');
  try{
    const response=await fetch(url,options);
    let payload={};
    try{payload=await response.json();}catch(_){payload={};}
    if(!response.ok) throw new Error(payload.detail||`Verification service returned ${response.status}`);
    state.verificationHistory.unshift(payload);
    state.verificationHistory=state.verificationHistory.slice(0,20);
    state.verification={loading:false,result:payload,error:'',inputLabel};
  }catch(error){
    state.verification={loading:false,result:null,error:error.message||'Verification failed.',inputLabel};
  }
  navigate('verify-result');
}

async function runVerificationJob(text,inputLabel){
  state.verification={loading:true,result:null,error:'',inputLabel,stage:'Submitting verification job'};
  navigate('verify-loading');
  try{
    const createdResponse=await fetch('/api/v1/verify/jobs',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})
    });
    const created=await createdResponse.json().catch(()=>({}));
    if(!createdResponse.ok||!created.id)throw new Error(created.detail||'Could not start verification job.');
    let job=null;
    for(let attempt=0;attempt<240;attempt++){
      await new Promise(resolve=>setTimeout(resolve,3000));
      const response=await fetch(`/api/v1/verify/jobs/${encodeURIComponent(created.id)}`);
      job=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(job.detail||'Could not read verification progress.');
      state.verification.stage=job.stage||'Verification is running';
      if(state.page==='verify-loading')render();
      if(job.status==='completed')break;
      if(job.status==='failed')throw new Error(job.error||'Verification failed.');
    }
    if(!job||job.status!=='completed'||!job.result){
      throw new Error('Verification is still taking too long. Retry with a shorter public video or paste its transcript.');
    }
    state.verificationHistory.unshift(job.result);
    state.verificationHistory=state.verificationHistory.slice(0,20);
    state.verification={loading:false,result:job.result,error:'',inputLabel,stage:'Completed'};
  }catch(error){
    state.verification={loading:false,result:null,error:error.message||'Verification failed.',inputLabel,stage:'Failed'};
  }
  navigate('verify-result');
}

function verifySubmittedText(value=''){
  const text=value || (($('#pasteInput')&&$('#pasteInput').value.trim())||'');
  if(text.length<3){toast('Paste a headline, claim, article text, or public URL first.');return;}
  const isLink=/^https?:\/\/\S+$/i.test(text);
  runVerificationJob(text,isLink?'Retrieving live link content and checking evidence':'Submitted headline or claim');
}
window.verifySubmittedText=verifySubmittedText;
window.analyzePasted=verifySubmittedText;

function verifyArticle(id){
  const article=getArticle(id);
  if(!article){toast('Article is no longer available.');return;}
  if(article.backendId){
    runVerification(`/api/v1/verify/article/${encodeURIComponent(article.backendId)}`,{method:'POST'},`Live article · ${article.source}`);
  }else{
    verifySubmittedText(`${article.headline}\n${article.description}`);
  }
}
window.verifyArticle=verifyArticle;

function verifyImageFile(file,claim=''){
  if(!file)return;
  if(!file.type.startsWith('image/')){toast('Please choose an image file.');return;}
  if(file.size>10*1024*1024){toast('Image must be 10 MB or smaller.');return;}
  const form=new FormData();
  form.append('image',file,file.name);
  if(claim.trim())form.append('claim',claim.trim());
  runVerification('/api/v1/verify/image',{method:'POST',body:form},`Image verification · ${file.name}`);
}

function verifyImageInput(input){
  const file=input.files&&input.files[0];
  const claim=($('#imageClaim')&&$('#imageClaim').value)||'';
  verifyImageFile(file,claim);
  input.value='';
}
window.verifyImageInput=verifyImageInput;

function handleImageDrop(event){
  event.preventDefault();
  event.currentTarget.classList.remove('drag');
  const file=event.dataTransfer?.files?.[0];
  const claim=($('#imageClaim')&&$('#imageClaim').value)||'';
  verifyImageFile(file,claim);
}
window.handleImageDrop=handleImageDrop;

function toggleMenu(){ $('#navlinks').classList.toggle('open'); }
window.toggleMenu=toggleMenu;

/* ---------- boot ---------- */
render();
updateNavUser();
loadAuthProviders();
handleAuthReturn().then(()=>loadSession());
loadLiveNews();
loadRumours();
setInterval(()=>{
  if(document.visibilityState==='visible'){
    loadLiveNews();
    loadRumours();
  }
},5*60*1000);
