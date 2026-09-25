const API='/api/v1/platform';
const $=(s)=>document.querySelector(s);const $$=(s)=>[...document.querySelectorAll(s)];
const state={user:null,entitlements:null,dashboard:null,signals:[],paper:null,portfolio:null,performance:null,quality:null,shadow:null,broker:null,tradingProfile:null,watchlists:[],alerts:[],notifications:[]};
const THEME_KEY='signalrank.theme';
const themeMedia=window.matchMedia?.('(prefers-color-scheme: light)');
function resolvedTheme(){const explicit=document.documentElement.dataset.theme;if(explicit==='light'||explicit==='dark')return explicit;return themeMedia?.matches?'light':'dark'}
function syncThemeUi(){const theme=resolvedTheme();const icon=$('#themeIcon');const label=$('#themeLabel');const toggle=$('#themeToggle');if(icon)icon.textContent=theme==='dark'?'☀':'☾';if(label)label.textContent=theme==='dark'?'Light':'Dark';if(toggle){toggle.setAttribute('aria-label',`Switch to ${theme==='dark'?'light':'dark'} mode`);toggle.title=`Switch to ${theme==='dark'?'light':'dark'} mode`}const meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.content=theme==='dark'?'#07131d':'#f4f8f7'}
function setTheme(theme,{persist=true}={}){if(theme==='light'||theme==='dark'){document.documentElement.dataset.theme=theme;if(persist){try{localStorage.setItem(THEME_KEY,theme)}catch{}}}else{delete document.documentElement.dataset.theme;if(persist){try{localStorage.removeItem(THEME_KEY)}catch{}}}syncThemeUi()}
function initTheme(){let saved='';try{saved=localStorage.getItem(THEME_KEY)||''}catch{}if(saved==='light'||saved==='dark')document.documentElement.dataset.theme=saved;syncThemeUi();themeMedia?.addEventListener?.('change',()=>{let explicit='';try{explicit=localStorage.getItem(THEME_KEY)||''}catch{}if(!explicit)syncThemeUi()});$('#themeToggle')?.addEventListener('click',()=>setTheme(resolvedTheme()==='dark'?'light':'dark'))}
const esc=(v)=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
function toast(message,error=false){const el=$('#toast');el.textContent=typeof message==='string'?message:JSON.stringify(message);el.style.borderColor=error?'rgba(255,107,117,.7)':'rgba(100,240,180,.5)';el.classList.add('show');setTimeout(()=>el.classList.remove('show'),4000)}
function cookie(name){return document.cookie.split(';').map(x=>x.trim()).find(x=>x.startsWith(name+'='))?.split('=').slice(1).join('=')||''}
async function request(path,options={}){const method=String(options.method||'GET').toUpperCase();const headers={'Content-Type':'application/json',...(options.headers||{})};if(!['GET','HEAD','OPTIONS'].includes(method)){const csrf=decodeURIComponent(cookie('sr_csrf'));if(csrf)headers['X-CSRF-Token']=csrf}const response=await fetch(API+path,{credentials:'include',headers,...options});let data={};try{data=await response.json()}catch{}if(!response.ok){const detail=data.detail;const serverMessage=typeof detail==='string'?detail:(detail?.message||detail?.code||'');const fallback=response.status>=500?'SignalRank sign-in services are temporarily unavailable. Please retry in a moment.':`Request failed (${response.status})`;throw new Error(serverMessage||fallback)}return data}
function formData(form){return Object.fromEntries(new FormData(form).entries())}
function fmt(value,digits=2){const number=Number(value||0);return Number.isFinite(number)?number.toLocaleString(undefined,{maximumFractionDigits:digits}):'—'}
function time(value){if(!value)return'—';return new Date(value).toLocaleString()}
function statusClass(value){const v=String(value||'').toLowerCase();return ['tp1','tp2','tp3','win','open','active'].some(x=>v.includes(x))?'positive':['sl','loss','closed_sl'].some(x=>v.includes(x))?'negative':''}
function setLoggedIn(value){$('#authShell').hidden=value;$('#appShell').hidden=!value;$('#sessionNav').hidden=!value;document.body.classList.toggle('session-active',value)}
function hasFeature(feature){const features=state.entitlements?.features||[];return features.includes('*')||features.includes(feature)}
function applyEntitlements(){$$('[data-feature]').forEach(el=>{const allowed=hasFeature(el.dataset.feature);el.classList.toggle('locked-nav',!allowed);el.setAttribute('aria-disabled',allowed?'false':'true');if(!allowed)el.title='Available on a higher SignalRankAI plan'})}
function setAuthTab(name){const forms={login:$('#loginForm'),register:$('#registerForm'),activate:$('#activateForm')};Object.entries(forms).forEach(([key,el])=>el.hidden=key!==name);$('#mfaForm').hidden=true;$('#passwordResetForm').hidden=true;$('#loginTab').classList.toggle('active',name==='login');$('#registerTab').classList.toggle('active',name==='register');$('#activateTab').classList.toggle('active',name==='activate')}
$('#loginTab').onclick=()=>setAuthTab('login');$('#registerTab').onclick=()=>setAuthTab('register');$('#activateTab').onclick=()=>setAuthTab('activate');
async function completeAuth(data){if(data.mfa_required){$('#loginForm').hidden=true;$('#registerForm').hidden=true;$('#activateForm').hidden=true;$('#mfaForm').hidden=false;$('#mfaForm [name="token"]').value=data.mfa_token;toast('Enter your authenticator or recovery code');return}await boot();toast('Signed in successfully')}
$('#loginForm').onsubmit=async e=>{e.preventDefault();try{await completeAuth(await request('/auth/login',{method:'POST',body:JSON.stringify({...formData(e.target),client_type:'web'})}))}catch(err){toast(err.message,true)}};
function signupContext(){const qs=new URLSearchParams(location.search);return{referral_code:qs.get('ref')||qs.get('referral')||qs.get('referral_code')||null,signup_source:'web',landing_path:location.pathname+location.search,http_referrer:document.referrer||null,utm_source:qs.get('utm_source'),utm_medium:qs.get('utm_medium'),utm_campaign:qs.get('utm_campaign'),utm_content:qs.get('utm_content'),utm_term:qs.get('utm_term')}}
$('#registerForm').onsubmit=async e=>{e.preventDefault();try{const data=await request('/auth/register',{method:'POST',body:JSON.stringify({...formData(e.target),...signupContext(),client_type:'web'})});await completeAuth(data);toast('Account created. Check your email to verify it. You can connect Telegram later from Account.')}catch(err){toast(err.message,true)}};
$('#activateForm').onsubmit=async e=>{e.preventDefault();try{await completeAuth(await request('/auth/telegram/complete',{method:'POST',body:JSON.stringify({...formData(e.target),client_type:'web'})}));history.replaceState({},'',location.pathname);toast('Telegram account activated')}catch(err){toast(err.message,true)}};
$('#mfaForm').onsubmit=async e=>{e.preventDefault();try{await completeAuth(await request('/auth/mfa/complete',{method:'POST',body:JSON.stringify({...formData(e.target),client_type:'web'})}))}catch(err){toast(err.message,true)}};
$('#passwordResetForm').onsubmit=async e=>{e.preventDefault();try{await request('/auth/password-reset/complete',{method:'POST',body:JSON.stringify(formData(e.target))});history.replaceState({},'',location.pathname);setAuthTab('login');toast('Password reset. Sign in again.')}catch(err){toast(err.message,true)}};
$('#magicLinkButton').onclick=async()=>{const email=prompt('Enter your account email');if(!email)return;try{await request('/auth/magic-link/request',{method:'POST',body:JSON.stringify({email})});toast('If the account exists, a sign-in link was queued.')}catch(err){toast(err.message,true)}};
$('#forgotPasswordButton').onclick=async()=>{const email=prompt('Enter your account email');if(!email)return;try{await request('/auth/password-reset/request',{method:'POST',body:JSON.stringify({email})});toast('If the account exists, reset instructions were queued.')}catch(err){toast(err.message,true)}};
function showView(name){const trigger=$(`[data-view="${name}"]`);if(trigger?.dataset.feature&&!hasFeature(trigger.dataset.feature)){toast('This workspace is available on a higher SignalRankAI plan.',true);return}$$('.view').forEach(el=>el.hidden=true);const target=$(`#${name}View`);if(target)target.hidden=false;$$('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));const loaders={overview:loadOverview,signals:loadSignals,evidence:loadEvidence,markets:searchMarkets,tools:loadTools,paper:loadPaper,portfolio:loadPortfolio,performance:loadPerformance,journal:loadJournal,support:loadSupport,account:loadAccount};loaders[name]?.().catch(err=>toast(err.message,true))}
$$('[data-view]').forEach(b=>b.onclick=()=>showView(b.dataset.view));
async function boot(){try{const me=await request('/me');state.user=me.user;try{state.entitlements=await request('/entitlements')}catch{state.entitlements={features:[]}}setLoggedIn(true);applyEntitlements();renderProfile();const initial=[loadOverview(),loadSignals()];if(hasFeature('paper_trading'))initial.push(loadPaper());await Promise.allSettled(initial);const invite=new URLSearchParams(location.search).get('organization_invite');if(invite){await request('/organizations/invitations/accept',{method:'POST',body:JSON.stringify({token:invite})});history.replaceState({},'',location.pathname);toast('Workspace invitation accepted')}}catch{state.user=null;state.entitlements=null;setLoggedIn(false)}}
async function loadOverview(){state.dashboard=await request('/dashboard');const s=state.dashboard.summary||{};$('#welcomeTitle').textContent=`Welcome${state.user?.display_name?`, ${state.user.display_name.split(' ')[0]}`:''}`;$('#accountSubtitle').textContent='Your signals, paper portfolio and market intelligence in one place.';$('#tierBadge').textContent=String(state.user?.tier||'free').toUpperCase();const cards=[['Delivered signals',s.delivered_signals],['Open positions',s.open_positions],['Paper cash',`$${fmt(s.paper_cash)}`],['Unrealized P/L',`$${fmt(s.unrealized_pnl)}`]];$('#summaryCards').innerHTML=cards.map(([k,v])=>`<div class="metric-card"><small>${esc(k)}</small><strong>${esc(v??0)}</strong></div>`).join('');renderOverviewLists()}
async function loadSignals(){const asset=$('#signalAssetFilter')?.value?.trim()||'';const assetClass=$('#signalClassFilter')?.value||'';const timeframe=$('#signalTimeframeFilter')?.value||'';const strategy=$('#signalStrategyFilter')?.value?.trim()||'';const status=$('#signalStatusFilter')?.value||'';const qs=new URLSearchParams({limit:'50'});if(asset)qs.set('asset',asset);if(assetClass)qs.set('asset_class',assetClass);if(timeframe)qs.set('timeframe',timeframe);if(strategy)qs.set('strategy',strategy);if(status)qs.set('status',status);state.signals=(await request('/signals?'+qs)).signals||[];renderSignals();renderOverviewLists()}
function loadEvidence(){const signal=state.signals[0];$('#evidenceAsset').textContent=signal?String(signal.asset||'LATEST SIGNAL').replace(/([A-Z]{3,4})(USD|USDT)$/,'$1 / $2'):'LATEST SIGNAL';$('#evidenceTimeframe').textContent=signal?.timeframe||'—';$('#evidenceFreshness').textContent=signal?.delivered_at?`Delivered ${time(signal.delivered_at)}`:'No delivery-proven signal selected';const rows=[['01','Rejection','Wick geometry is measured as evidence, never a reversal guarantee.','OBSERVED'],['02','Close location','The close shows who controlled the end of the completed period.','OBSERVED'],['03','Key-level context','Support and resistance use only candles known at assessment time.','CONTEXT'],['04','Relative volume','Participation is compared with a prior-period median.','CONTEXT'],['05','Next candle','No conclusion is recorded until the following candle is final.','PENDING']];$('#evidenceLedger').innerHTML=rows.map(([n,event,detail,status])=>`<div class="ledger-row"><b>${n}</b><strong>${esc(event)}</strong><p>${esc(detail)}</p><span class="${status==='PENDING'?'pending-text':'cyan'}">${status}</span></div>`).join('')}
function renderOverviewLists(){const recent=state.signals.slice(0,5);$('#latestSignals').innerHTML=recent.length?recent.map(s=>`<div class="list-row"><div><strong>${esc(s.asset)} ${esc(String(s.direction).toUpperCase())}</strong><small>${esc(s.timeframe)} · ${esc(s.strategy_name||'Strategy')}</small></div><div class="${statusClass(s.outcome_status)}">${esc(s.outcome_status||'Pending')}</div></div>`).join(''):'<p>No confirmed signals yet.</p>';const positions=(state.paper?.positions||[]).filter(p=>p.status==='open').slice(0,5);$('#overviewPositions').innerHTML=positions.length?positions.map(p=>`<div class="list-row"><div><strong>${esc(p.asset)} ${esc(String(p.direction).toUpperCase())}</strong><small>Entry ${fmt(p.fill_entry,6)}</small></div><div class="${Number(p.unrealized_pnl)>=0?'positive':'negative'}">$${fmt(p.unrealized_pnl)}</div></div>`).join(''):'<p>No open paper positions.</p>'}
function renderSignals(){const rows=state.signals;$('#signalsTable').innerHTML=rows.length?`<table><thead><tr><th>Asset</th><th>Market</th><th>Direction</th><th>Timeframe</th><th>Entry</th><th>Stop</th><th>Score</th><th>ML</th><th>Strategy</th><th>Outcome</th><th>Delivered</th><th></th></tr></thead><tbody>${rows.map(s=>`<tr><td><strong>${esc(s.asset)}</strong><br><small>${esc(s.display_id||String(s.signal_id).slice(0,8))}</small></td><td><span class="market-badge">${esc(String(s.asset_class||'unknown').toUpperCase())}</span></td><td>${esc(String(s.direction).toUpperCase())}</td><td>${esc(s.timeframe)}</td><td>${s.exact_levels_locked?'<span class="muted">Premium only</span>':fmt(s.entry,6)}</td><td>${s.exact_levels_locked?'<span class="muted">Premium only</span>':fmt(s.stop_loss,6)}</td><td>${s.exact_levels_locked?'<span class="muted">Premium only</span>':fmt(s.score,1)}</td><td>${s.exact_levels_locked?'<span class="muted">Premium only</span>':(s.ml_probability_calibrated==null?'—':fmt(Number(s.ml_probability_calibrated)*100,1)+'%')}</td><td>${esc(s.strategy_name||'—')}</td><td class="${statusClass(s.outcome_status)}">${esc(s.outcome_status||s.status||'Pending')}</td><td>${time(s.delivered_at)}</td><td><button class="ghost signal-detail" data-id="${esc(s.signal_id)}" type="button">View</button></td></tr>`).join('')}</tbody></table>`:'<div class="panel">No delivery-proven signals match this view.</div>';$$('.signal-detail').forEach(button=>button.onclick=()=>loadSignalDetail(button.dataset.id).catch(e=>toast(e.message,true)))}
$('#refreshSignals').onclick=loadSignals;['#signalAssetFilter','#signalClassFilter','#signalTimeframeFilter','#signalStrategyFilter','#signalStatusFilter'].forEach(selector=>{const el=$(selector);if(!el)return;el.onchange=loadSignals;if(el.tagName==='INPUT')el.onkeydown=e=>{if(e.key==='Enter')loadSignals()}});
async function loadSignalDetail(signalId){const data=await request('/signals/'+encodeURIComponent(signalId));const x=data.signal||{};const events=data.events||[];const panel=$('#signalDetailPanel');$('#signalDetailTitle').textContent=`${x.asset||'Signal'} · ${String(x.direction||'').toUpperCase()} · ${x.timeframe||''}`;const targets=Array.isArray(x.take_profit)?x.take_profit:[];const targetsText=targets.map(t=>typeof t==='object'?(t.price??t.tp??t.target??''):t).filter(v=>v!==''&&v!=null).map(v=>fmt(v,6)).join(' · ')||'—';const proof=data.proof||{};const locked=Boolean(x.exact_levels_locked);const gated=(value,digits=6)=>locked?'Premium only':fmt(value,digits);$('#signalDetailBody').innerHTML=`<div class="mini-metrics signal-proof-grid"><div><small>Entry</small><strong>${esc(gated(x.entry,6))}</strong></div><div><small>Stop</small><strong>${esc(gated(x.stop_loss,6))}</strong></div><div><small>Targets</small><strong>${esc(targetsText)}</strong></div><div><small>R/R</small><strong>${esc(gated(x.rr_estimate,2))}</strong></div><div><small>Score</small><strong>${esc(gated(x.score,1))}</strong></div><div><small>ML confidence</small><strong>${locked?'Premium only':(x.ml_probability_calibrated==null?'—':fmt(Number(x.ml_probability_calibrated)*100,1)+'%')}</strong></div><div><small>Lifecycle</small><strong>${esc(x.lifecycle_state||x.outcome_status||x.status||'Pending')}</strong></div><div><small>Outcome</small><strong class="${statusClass(x.outcome_status)}">${esc(x.outcome_status||'Pending')}</strong></div></div><div class="proof-strip ${proof.access_proven?'positive':'negative'}"><b>${proof.access_proven?'Signal receipt confirmed':'Signal receipt incomplete'}</b><span>${esc(proof.delivery_channel||'unknown')} · ${esc(proof.delivery_state||'unknown')} · ${time(proof.delivery_confirmed_at||x.delivered_at)} · age ${esc(proof.signal_age_at_delivery_seconds??'—')}s</span><small>Telegram proof: ${proof.delivery_proven?'yes':'no'} · Web receipt: ${proof.web_delivery_proven?'yes':'no'}</small></div>${x.ml_recovery_mode?'<div class="proof-strip warning"><b>Model-health recovery signal</b><span>Strict deterministic quality gates passed while the serving model is starved. Live broker execution is disabled; use paper trading for validation.</span></div>':''}<div class="two-column"><div><h3>Trade state</h3><div class="detail-list">${[['Strategy',x.strategy_name],['Regime',x.regime],['Last price',x.last_price==null?'—':fmt(x.last_price,6)],['MFE',x.mfe_r==null?'—':fmt(x.mfe_r,2)+'R'],['MAE',x.mae_r==null?'—':fmt(x.mae_r,2)+'R'],['Highest TP',x.highest_tp_hit??0],['Terminal event',x.terminal_event_type||'—'],['Terminal price',x.terminal_price==null?'—':fmt(x.terminal_price,6)]].map(([k,v])=>`<div class="detail-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')}</div></div><div><h3>Lifecycle timeline</h3><div class="timeline">${events.length?events.map(e=>`<div class="timeline-event"><span></span><div><strong>${esc(String(e.event_type||'event').replaceAll('_',' '))}</strong><small>${time(e.event_time)}${e.price==null?'':` · ${fmt(e.price,6)}`}${e.r_multiple==null?'':` · ${fmt(e.r_multiple,2)}R`}</small></div></div>`).join(''):'<p class="muted">No lifecycle events recorded yet.</p>'}</div></div></div>`;if(hasFeature('broker_connection')&&!x.ml_recovery_mode){$('#signalDetailBody').insertAdjacentHTML('beforeend',`<article class="panel signal-execution-panel"><div class="panel-heading"><div><p class="eyebrow">MANUAL BROKER EXECUTION</p><h3>Execute this signal</h3><p>This submits one order through your connected MT5 account only after the server re-checks broker readiness, terms, live quote freshness, market status, risk, quota, reconciliation and kill switches.</p></div></div><div class="detail-list"><div class="detail-row"><span>Asset</span><strong>${esc(x.asset||'—')}</strong></div><div class="detail-row"><span>Direction</span><strong>${esc(String(x.direction||'').toUpperCase())}</strong></div><div class="detail-row"><span>Entry / Stop</span><strong>${fmt(x.entry,6)} / ${fmt(x.stop_loss,6)}</strong></div></div><button id="executeSignalButton" class="danger" type="button">Confirm and submit to MT5</button><p class="muted">A broker order can lose money. This action is not an auto-trade toggle and does not guarantee execution or profit.</p></article>`);const executeButton=$('#executeSignalButton');if(executeButton)executeButton.onclick=async()=>{const label=`${x.asset||'this signal'} ${String(x.direction||'').toUpperCase()} at ${fmt(x.entry,6)} with stop ${fmt(x.stop_loss,6)}`;if(!confirm(`Submit ${label} to your connected MT5 account?\n\nThe server will block the trade if any safety, risk, quote, market, consent, quota or reconciliation gate fails.`))return;executeButton.disabled=true;try{const result=await request('/signals/'+encodeURIComponent(signalId)+'/execute',{method:'POST',body:JSON.stringify({confirm:true,provider:((state.broker?.connections||[]).find(x=>x.is_default&&['mt4','mt5'].includes(x.platform))?.platform||(['mt4','mt5'].includes(state.broker?.execution?.execution_provider)?state.broker.execution.execution_provider:'mt5'))})});toast(result.order_id?`Order submitted: ${result.order_id}`:'Broker submission accepted');await loadSignalDetail(signalId)}catch(err){toast(err.message,true)}finally{executeButton.disabled=false}}};$('#signalDetailBody').insertAdjacentHTML('beforeend',`<article class="panel signal-feedback-panel"><div class="panel-heading"><div><h3>Signal feedback</h3><p>Rate this delivered signal or report a specific problem. Feedback is attached to this signal and your canonical account.</p></div></div><form id="signalFeedbackForm" class="stack-form"><label>Rating<select name="rating"><option value="">No rating</option><option value="5">5 — excellent</option><option value="4">4 — good</option><option value="3">3 — mixed</option><option value="2">2 — poor</option><option value="1">1 — bad</option></select></label><label>Issue<select name="issue"><option value="">No issue</option><option value="stale">Stale</option><option value="bad_setup">Bad setup</option><option value="wrong_levels">Wrong levels</option><option value="wrong_outcome">Wrong outcome</option><option value="late_delivery">Late delivery</option><option value="duplicate">Duplicate</option><option value="unclear">Unclear</option><option value="other">Other</option></select></label><label>Comment<textarea name="comment" rows="3" maxlength="4000" placeholder="What should SignalRankAI learn from this?"></textarea></label><button class="primary" type="submit">Send feedback</button></form></article>`);const feedbackForm=$('#signalFeedbackForm');if(feedbackForm)feedbackForm.onsubmit=async e=>{e.preventDefault();const raw=formData(e.target);const payload={rating:raw.rating?Number(raw.rating):null,issue:raw.issue||null,comment:String(raw.comment||'').trim()||null};if(payload.rating==null&&!payload.issue){toast('Choose a rating or issue',true);return}try{await request('/signals/'+encodeURIComponent(signalId)+'/feedback',{method:'POST',body:JSON.stringify(payload)});e.target.reset();toast('Feedback recorded for this signal')}catch(err){toast(err.message,true)}};panel.hidden=false;panel.scrollIntoView({behavior:'smooth',block:'start'})}
$('#closeSignalDetail')?.addEventListener('click',()=>{$('#signalDetailPanel').hidden=true});

async function searchMarkets(){const qs=new URLSearchParams({q:$('#marketSearch')?.value||'',limit:'60'});const assetClass=$('#assetClassFilter')?.value;if(assetClass)qs.set('asset_class',assetClass);const rows=(await request('/instruments/search?'+qs)).instruments||[];$('#marketResults').innerHTML=rows.length?rows.map(i=>`<article class="market-card"><div class="market-card-top"><h3>${esc(i.display_symbol||i.canonical_symbol)}</h3><button class="ghost market-watch" data-instrument="${esc(i.instrument_id)}" data-symbol="${esc(i.display_symbol||i.canonical_symbol)}" type="button">Watch</button></div><p>${esc(i.asset_class)} · ${esc(i.instrument_type)}</p><p>${i.tradable?'Tradable':'Analysis only'} · ${esc(i.discovery_status)}</p><div class="provider-pills">${(i.providers||[]).map(p=>`<span>${esc(p)}</span>`).join('')}</div></article>`).join(''):'<p>No registry instruments found. Run provider discovery after migration.</p>';$$('.market-watch').forEach(button=>button.onclick=()=>addInstrumentToWatchlist(button.dataset.instrument,button.dataset.symbol))}
$('#searchMarkets').onclick=()=>searchMarkets().catch(e=>toast(e.message,true));$('#marketSearch').onkeydown=e=>{if(e.key==='Enter')searchMarkets().catch(x=>toast(x.message,true))};
async function loadRecap(){const r=await request('/recap');const topAssets=(r.top_assets||[]).map(x=>`${esc(x.asset)} <b>${esc(x.n)}</b>`).join(' · ')||'No delivered signals';const topStrategies=(r.top_strategies||[]).map(x=>`${esc(x.strategy)} <b>${esc(x.n)}</b>`).join(' · ')||'No strategy data';const wr=r.resolved_win_rate==null?'Not enough resolved outcomes':`${fmt(Number(r.resolved_win_rate)*100,1)}%`;$('#weeklyRecap').innerHTML=`<div class="mini-metrics"><div><small>Delivered</small><strong>${esc(r.total_delivered)}</strong></div><div><small>Resolved win rate</small><strong>${esc(wr)}</strong></div><div><small>Average R</small><strong>${fmt(r.average_r,2)}R</strong></div></div><p><b>Most active:</b> ${topAssets}</p><p><b>Strategies:</b> ${topStrategies}</p><small>${esc(r.disclaimer)}</small>`}
async function loadWatchlists(){const data=await request('/watchlists');state.watchlists=data.watchlists||[];$('#watchlistList').innerHTML=state.watchlists.length?state.watchlists.map(w=>`<div class="watchlist-block"><div class="list-row"><div><strong>${esc(w.name)}</strong><small>${(w.items||[]).length} instruments${w.is_default?' · Default':''}</small></div><button class="danger watchlist-delete" data-id="${esc(w.watchlist_id)}" type="button">Delete</button></div><div class="watch-items">${(w.items||[]).map(item=>`<span>${esc(item.instrument_id)}</span>`).join('')||'<small>No markets added yet. Use Watch from Market explorer.</small>'}</div></div>`).join(''):'<p>Create a watchlist, then add markets from Market explorer.</p>';$$('.watchlist-delete').forEach(b=>b.onclick=async()=>{if(!confirm('Delete this watchlist?'))return;await request('/watchlists/'+encodeURIComponent(b.dataset.id),{method:'DELETE'});await loadWatchlists()})}
async function addInstrumentToWatchlist(instrumentId,symbol){if(!state.watchlists.length)await loadWatchlists();if(!state.watchlists.length){toast('Create a watchlist in Tools first.',true);showView('tools');return}let selected=state.watchlists[0];if(state.watchlists.length>1){const menu=state.watchlists.map((w,i)=>`${i+1}. ${w.name}`).join('\n');const pick=prompt(`Add ${symbol} to which watchlist?\n${menu}`,'1');const index=Math.max(0,Math.min(state.watchlists.length-1,Number(pick||1)-1));selected=state.watchlists[index]}try{await request('/watchlists/'+encodeURIComponent(selected.watchlist_id)+'/items',{method:'POST',body:JSON.stringify({instrument_id:instrumentId})});toast(`${symbol} added to ${selected.name}`);await loadWatchlists()}catch(err){toast(err.message,true)}}
async function loadAlerts(){try{const data=await request('/alerts');state.alerts=data.alerts||[];$('#alertList').innerHTML=state.alerts.length?state.alerts.map(a=>`<div class="list-row"><div><strong>${esc(a.asset||a.instrument_id||'Market')} · ${esc(String(a.alert_type||'').replaceAll('_',' '))}</strong><small>${a.active?'Active':'Disabled'} · ${(a.channels||[]).map(esc).join(', ')}</small></div>${a.active?`<button class="danger alert-delete" data-id="${esc(a.alert_id)}" type="button">Disable</button>`:''}</div>`).join(''):'<p>No alerts configured.</p>';$$('.alert-delete').forEach(b=>b.onclick=async()=>{await request('/alerts/'+encodeURIComponent(b.dataset.id),{method:'DELETE'});await loadAlerts()})}catch(err){$('#alertList').innerHTML=`<p class="muted">${esc(err.message)}</p>`}}
async function loadNotifications(){const data=await request('/notifications?limit=50');state.notifications=data.notifications||[];$('#notificationCenter').innerHTML=state.notifications.length?state.notifications.map(n=>`<div class="notification-row ${n.read_at?'':'unread'}"><div><small>${esc(String(n.event_type||'update').replaceAll('_',' '))} · ${time(n.created_at)}</small><strong>${esc(n.title||'SignalRankAI update')}</strong><p>${esc(n.body||'')}</p></div>${n.read_at?'':`<button class="ghost notification-read" data-id="${esc(n.notification_id)}" type="button">Mark read</button>`}</div>`).join(''):'<p class="muted">No notifications yet.</p>';$$('.notification-read').forEach(b=>b.onclick=async()=>{await request('/notifications/'+encodeURIComponent(b.dataset.id)+'/read',{method:'POST',body:'{}'});await loadNotifications()})}
async function loadTools(){await Promise.allSettled([loadRecap(),loadWatchlists(),loadAlerts(),loadNotifications()])}
$('#refreshRecap')?.addEventListener('click',()=>loadRecap().catch(e=>toast(e.message,true)));$('#refreshNotifications')?.addEventListener('click',()=>loadNotifications().catch(e=>toast(e.message,true)));
$('#liveQuoteForm')?.addEventListener('submit',async e=>{e.preventDefault();const asset=String(formData(e.target).asset||'').trim().toUpperCase();const target=$('#liveQuoteResult');target.innerHTML='<span class="loading-dot">Fetching provider quote…</span>';try{const q=await request('/live-price?asset='+encodeURIComponent(asset));const spread=q.bid!=null&&q.ask!=null?Math.abs(Number(q.ask)-Number(q.bid)):null;target.innerHTML=`<div class="quote-hero"><div><small>${esc(String(q.asset_class||'market').toUpperCase())}</small><strong>${esc(q.asset)} · ${fmt(q.price,6)}</strong></div><span class="${q.is_stale?'negative':'positive'}">${q.is_stale?'STALE':'LIVE'}</span></div><div class="mini-metrics"><div><small>Provider</small><strong>${esc(q.provider)}</strong></div><div><small>Latency</small><strong>${esc(q.latency_ms)} ms</strong></div><div><small>Confidence</small><strong>${fmt(Number(q.confidence||0)*100,0)}%</strong></div><div><small>Spread</small><strong>${spread==null?'—':fmt(spread,6)}</strong></div></div><small>${esc(q.quote_kind)} · ${esc(q.provider_health)} · ${esc(q.market_status||'unknown')} · request ${esc(String(q.request_id||'').slice(0,10))}</small>`}catch(err){target.textContent=err.message;target.classList.add('negative')}});
$('#aiAnalyzeForm')?.addEventListener('submit',async e=>{e.preventDefault();const raw=formData(e.target);const target=$('#aiAnalysisResult');target.innerHTML='<span class="loading-dot">Running market analysis…</span>';try{const result=await request('/ai/analyze',{method:'POST',body:JSON.stringify({asset:String(raw.asset||'').toUpperCase(),timeframe:raw.timeframe||'1h'})});if(!result.setup){target.innerHTML=`<p><strong>No qualified setup right now.</strong></p><p>${esc(String(result.reason||'No setup').replaceAll('_',' '))} · ${esc(result.candles||0)} candles checked.</p>`;return}const x=result.setup;const ai=result.openai||{};target.innerHTML=`<div class="analysis-hero"><div><small>${esc(String(result.asset_class||'').toUpperCase())} · ${esc(result.timeframe)}</small><strong>${esc(result.asset)} ${esc(String(x.direction||'').toUpperCase())}</strong></div><span class="score-ring">${fmt(x.score,0)}</span></div><div class="mini-metrics"><div><small>Entry</small><strong>${fmt(x.entry,6)}</strong></div><div><small>Stop</small><strong>${fmt(x.stop_loss,6)}</strong></div><div><small>Confidence</small><strong>${fmt(Number(x.confidence||0)*100,1)}%</strong></div><div><small>Strategy</small><strong>${esc(x.strategy_name||'—')}</strong></div></div>${ai.explanation?`<div class="ai-explanation"><b>OpenAI explanation</b><p>${esc(ai.explanation)}</p>${(ai.strengths||[]).length?`<p><b>Strengths:</b> ${(ai.strengths||[]).map(esc).join(' · ')}</p>`:''}${(ai.risks||[]).length?`<p><b>Risks:</b> ${(ai.risks||[]).map(esc).join(' · ')}</p>`:''}</div>`:''}<small>${esc(result.disclaimer)}</small>`}catch(err){target.innerHTML=`<p class="negative">${esc(err.message)}</p>`}});
$('#watchlistForm')?.addEventListener('submit',async e=>{e.preventDefault();try{await request('/watchlists',{method:'POST',body:JSON.stringify(formData(e.target))});e.target.reset();await loadWatchlists();toast('Watchlist created')}catch(err){toast(err.message,true)}});
function syncAlertThreshold(){const type=$('#alertForm [name="alert_type"]')?.value||'';const needsPrice=['price_above','price_below'].includes(type);$('#alertValueLabel').hidden=!needsPrice;const input=$('#alertForm [name="value"]');if(input)input.required=needsPrice}
$('#alertForm [name="alert_type"]')?.addEventListener('change',syncAlertThreshold);syncAlertThreshold();
$('#alertForm')?.addEventListener('submit',async e=>{e.preventDefault();const raw=formData(e.target);const needsPrice=['price_above','price_below'].includes(raw.alert_type);const channels=['web'];if(state.user?.telegram_user_id)channels.push('telegram');const payload={asset:String(raw.asset||'').toUpperCase(),alert_type:raw.alert_type,condition:needsPrice?{value:Number(raw.value)}:{},channels};try{await request('/alerts',{method:'POST',body:JSON.stringify(payload)});e.target.reset();syncAlertThreshold();await loadAlerts();toast('Alert created')}catch(err){toast(err.message,true)}});
function renderPaperDetail(detail){const snap=detail?.snapshot||{};const form=$('#paperSettingsForm');if(form){for(const name of ['risk_pct','max_open_positions','min_signal_score','spread_bps','slippage_bps','fee_bps','target_mode','allowed_directions']){if(form.elements[name])form.elements[name].value=snap[name]??''}form.elements.auto_trade_enabled.checked=Boolean(snap.auto_trade_enabled);const classes=new Set(snap.allowed_asset_classes||[]);$$('#paperSettingsForm input[name="paper_asset_class"]').forEach(input=>input.checked=classes.has(input.value))}const perf=detail?.performance||{};$('#paperPerformance').innerHTML=[['Closed trades',perf.sample_size||0],['Win rate',perf.win_rate_pct==null?'—':fmt(perf.win_rate_pct,1)+'%'],['Net P/L',`${fmt(perf.net_pnl)}`],['Return',perf.return_pct==null?'—':fmt(perf.return_pct,2)+'%'],['Average R',perf.avg_r==null?'—':fmt(perf.avg_r,2)+'R'],['Equity',`${fmt(snap.equity)}`]].map(([k,v])=>`<div class="metric-card"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('');const closed=detail?.closed_positions||[];const skipped=detail?.skipped_positions||[];const history=[...closed.map(x=>({...x,_kind:'closed'})),...skipped.map(x=>({...x,_kind:'skipped'}))].sort((a,b)=>new Date(b.closed_at||b.opened_at||0)-new Date(a.closed_at||a.opened_at||0));$('#paperHistory').innerHTML=history.length?`<table><thead><tr><th>Type</th><th>Asset</th><th>Direction</th><th>Result</th><th>R</th><th>Reason</th><th>Closed</th></tr></thead><tbody>${history.map(x=>`<tr><td>${esc(x._kind)}</td><td>${esc(x.asset)}</td><td>${esc(String(x.direction||'').toUpperCase())}</td><td class="${Number(x.realized_pnl||0)>=0?'positive':'negative'}">${fmt(x.realized_pnl)}</td><td>${fmt(x.r_multiple,2)}</td><td>${esc(x.exit_reason||'—')}</td><td>${time(x.closed_at||x.opened_at)}</td></tr>`).join('')}</tbody></table>`:'<p class="muted">No paper history yet.</p>';const activity=detail?.activity||[];$('#paperActivity').innerHTML=activity.length?activity.map(a=>`<div class="list-row"><div><strong>${esc(a.display_id||String(a.signal_id||'').slice(0,12))} · ${esc(a.asset||'')}</strong><small>${esc(a.decision||'')} · ${esc(a.reason||'')} · ${esc(String(a.receipt_channel||'account').toUpperCase())} receipt · ${time(a.created_at)}</small></div><span class="${String(a.decision||'').toLowerCase()==='opened'?'positive':''}">${a.retryable?'Retryable':'Final'}</span></div>`).join(''):'<p class="muted">No paper decisions recorded yet.</p>'}
async function loadPaper(){state.paper=await request('/paper');const a=state.paper.account||{};$('#paperAccount').innerHTML=[['Cash balance',`${fmt(a.cash_balance)}`],['Realized P/L',`${fmt(a.realized_pnl)}`],['Risk per trade',`${fmt(a.risk_pct)}%`],['Auto paper',a.auto_trade_enabled?'Enabled':'Disabled']].map(([k,v])=>`<div class="metric-card"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('');const rows=state.paper.positions||[];$('#paperPositions').innerHTML=rows.length?`<table><thead><tr><th>Asset</th><th>Market</th><th>Status</th><th>Direction</th><th>Entry</th><th>Current</th><th>Quantity</th><th>Unrealized</th><th>Opened</th></tr></thead><tbody>${rows.map(p=>`<tr><td>${esc(p.asset)}</td><td><span class="market-badge">${esc(String(p.asset_class||'').toUpperCase())}</span></td><td>${esc(p.status)}</td><td>${esc(String(p.direction).toUpperCase())}</td><td>${fmt(p.fill_entry,6)}</td><td>${fmt(p.current_price,6)}</td><td>${fmt(p.quantity,6)}</td><td class="${Number(p.unrealized_pnl)>=0?'positive':'negative'}">${fmt(p.unrealized_pnl)}</td><td>${time(p.opened_at)}</td></tr>`).join('')}</tbody></table>`:'<div class="panel">No paper positions yet.</div>';const notice=$('#paperLinkNotice');try{const detail=await request('/paper/detail');notice.hidden=true;renderPaperDetail(detail)}catch(err){notice.hidden=false;notice.innerHTML=`<strong>Paper controls are temporarily unavailable.</strong><p>${esc(err.message)}</p><button class="ghost" type="button" id="retryPaperDetail">Retry</button>`;notice.querySelector('#retryPaperDetail')?.addEventListener('click',()=>loadPaper());$('#paperPerformance').innerHTML='';$('#paperHistory').innerHTML='<p class="muted">Paper history could not be loaded. Your account does not need Telegram to use web paper trading.</p>';$('#paperActivity').innerHTML=''}renderOverviewLists()}
async function loadPortfolio(){state.portfolio=await request('/portfolio');const a=state.portfolio.account||{};$('#portfolioSummary').innerHTML=[['Equity',`$${fmt(state.portfolio.equity)}`],['Cash',`$${fmt(a.cash_balance)}`],['Realized',`$${fmt(a.realized_pnl)}`],['Open exposures',(state.portfolio.exposures||[]).length]].map(([k,v])=>`<div class="metric-card"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('');const rows=state.portfolio.exposures||[];$('#portfolioExposures').innerHTML=rows.length?`<table><thead><tr><th>Asset</th><th>Class</th><th>Direction</th><th>Positions</th><th>Notional</th><th>Unrealized</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.asset)}</td><td>${esc(r.asset_class)}</td><td>${esc(r.direction)}</td><td>${esc(r.positions)}</td><td>$${fmt(r.notional)}</td><td class="${Number(r.unrealized_pnl)>=0?'positive':'negative'}">$${fmt(r.unrealized_pnl)}</td></tr>`).join('')}</tbody></table>`:'<div class="panel">No open exposure.</div>'}
async function loadPerformance(){const [performance,quality,shadow]=await Promise.all([request('/performance'),request('/quality'),request('/shadow-report')]);state.performance=performance;state.quality=quality;state.shadow=shadow;const s=performance.summary||{};$('#performanceSummary').innerHTML=[['Signals',s.signals||0],['Wins',s.wins||0],['Losses',s.losses||0],['Win rate',s.win_rate==null?'Not enough data':`${fmt(Number(s.win_rate)*100,1)}%`],['Average R',fmt(s.average_r,2)],['Total R',fmt(s.total_r,2)]].map(([k,v])=>`<div class="metric-card"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('');const rows=performance.breakdown||[];$('#performanceBreakdown').innerHTML=rows.length?`<table><thead><tr><th>Asset</th><th>Timeframe</th><th>Signals</th><th>Average R</th><th>Total R</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.asset)}</td><td>${esc(r.timeframe)}</td><td>${esc(r.signals)}</td><td>${fmt(r.average_r)}</td><td>${fmt(r.total_r)}</td></tr>`).join('')}</tbody></table>`:'<div class="panel">No proof-backed performance rows yet.</div>';const accept=quality.acceptance_rate==null?'—':`${fmt(Number(quality.acceptance_rate)*100,1)}%`;$('#qualitySummary').innerHTML=[['Issued',quality.issued||0],['Rejected / skipped',quality.rejected_or_skipped||0],['Acceptance',accept]].map(([k,v])=>`<div class="metric-card"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('');$('#qualityReasons').innerHTML=(quality.top_reasons||[]).slice(0,8).map(r=>`<div class="list-row"><div><strong>${esc(String(r.reason||'Other').replaceAll('_',' '))}</strong></div><span>${esc(r.rows||0)}</span></div>`).join('')||'<p>No rejection data in this window.</p>';const sh=shadow.summary||{};const shadowRate=sh.counterfactual_win_rate==null?'—':`${fmt(Number(sh.counterfactual_win_rate)*100,1)}%`;$('#shadowSummary').innerHTML=[['Candidates',sh.samples||0],['Tracked',sh.tracked||0],['Resolved',sh.resolved||0],['Counterfactual win rate',shadowRate]].map(([k,v])=>`<div class="metric-card"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('');$('#shadowMethodology').textContent=sh.methodology||'';$('#shadowReasons').innerHTML=(shadow.by_reason||[]).slice(0,8).map(r=>`<div class="list-row"><div><strong>${esc(String(r.rejection_reason||'Other').replaceAll('_',' '))}</strong><small>${esc(r.tracked||0)} tracked</small></div><span>${esc(r.rows||0)}</span></div>`).join('')||'<p>No shadow candidates in this window.</p>';try{const leaderboard=await request('/strategy-leaderboard');const panel=$('#strategyLeaderboardPanel');if(panel){panel.hidden=false;const strategies=leaderboard.strategies||[];$('#strategyLeaderboard').innerHTML=strategies.length?`<table><thead><tr><th>Strategy</th><th>Signals</th></tr></thead><tbody>${strategies.map(r=>`<tr><td>${esc(r.strategy_name)}</td><td>${esc(r.signals)}</td></tr>`).join('')}</tbody></table>`:'<p>No strategy activity.</p>'}}catch{$('#strategyLeaderboardPanel')?.setAttribute('hidden','')}await loadVipResearch()}
async function loadVipResearch(){const panel=$('#vipResearchPanel');if(!panel)return;try{const elite=await request('/elite-signals');panel.hidden=false;$('#priorityDeliveryBadge').textContent=elite.priority_delivery_active?'PRIORITY ACTIVE':'VIP';const rows=elite.signals||[];$('#eliteSignalList').innerHTML=rows.length?rows.map(s=>`<div class="list-row"><div><strong>${esc(s.display_id||String(s.signal_id||'').slice(0,12))} · ${esc(s.asset||'')}</strong><small>${esc(String(s.direction||'').toUpperCase())} · ${esc(s.timeframe||'')} · score ${fmt(s.score,1)} · delivered ${time(s.delivered_at)}</small></div><span>${esc(s.outcome_status||'Active')}</span></div>`).join(''):'<p class="muted">No elite delivered signals in the last 7 days.</p>'}catch{panel.hidden=true;$('#eliteSignalList').innerHTML='';$('#simulationResult').innerHTML=''}}
$('#simulationForm')?.addEventListener('submit',async e=>{e.preventDefault();const raw=formData(e.target);const payload={starting_capital:raw.starting_capital?Number(raw.starting_capital):null,risk_pct:raw.risk_pct?Number(raw.risk_pct):null};try{const data=await request('/simulation',{method:'POST',body:JSON.stringify(payload)});if(!data.ready){$('#simulationResult').innerHTML=[['Completed outcomes',data.completed_outcomes],['Minimum required',data.minimum_required],['Delivered signals',data.delivered_total],['Awaiting terminal outcome',data.pending_delivered],['Paper equity',`${fmt(data.paper_equity)}`]].map(([k,v])=>`<div class="detail-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')+`<p class="muted">${esc(data.methodology||'')}</p>`;return}const ev=data.evidence||{},p=data.projection||{};$('#simulationResult').innerHTML=[['Evidence',`${ev.completed_outcomes||0} outcomes`],['Observed win rate',`${fmt(Number(ev.observed_win_rate||0)*100,1)}%`],['Avg win / loss',`${fmt(ev.observed_avg_win_r,2)}R / ${fmt(ev.observed_avg_loss_r,2)}R`],['Observed pace',`${ev.observed_trades_per_month||0}/month`],['5th percentile',`${fmt(p.p05)}`],['Median',`${fmt(p.p50)}`],['95th percentile',`${fmt(p.p95)}`],['Ruin probability',`${fmt(p.ruin_probability_pct,2)}%`]].map(([k,v])=>`<div class="detail-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')+`<p class="muted">${esc(data.disclaimer||'')}</p>`}catch(err){toast(err.message,true)}});

async function loadJournal(){const rows=(await request('/journal?limit=100')).entries||[];$('#journalEntries').innerHTML=rows.length?rows.map(entry=>`<div class="list-row"><div><strong>${esc(entry.title||'Journal entry')}</strong><small>${time(entry.occurred_at)} · ${esc(entry.emotion||'No emotion tag')}${entry.result_r==null?'':` · ${fmt(entry.result_r)}R`}</small><p>${esc(entry.notes||'')}</p></div><button class="danger journal-delete" data-id="${esc(entry.journal_entry_id)}">Delete</button></div>`).join(''):'<p>No journal entries yet.</p>';$$('.journal-delete').forEach(button=>button.onclick=async()=>{if(!confirm('Delete this journal entry?'))return;await request('/journal/'+encodeURIComponent(button.dataset.id),{method:'DELETE'});loadJournal()})}
$('#journalForm').onsubmit=async e=>{e.preventDefault();const raw=formData(e.target);const payload={title:raw.title||null,notes:raw.notes||'',emotion:raw.emotion||null,mistake_category:raw.mistake_category||null,plan_adherence:raw.plan_adherence?Number(raw.plan_adherence):null,result_r:raw.result_r?Number(raw.result_r):null,tags:String(raw.tags||'').split(',').map(x=>x.trim()).filter(Boolean)};try{await request('/journal',{method:'POST',body:JSON.stringify(payload)});e.target.reset();await loadJournal();toast('Journal entry saved')}catch(err){toast(err.message,true)}};
async function loadSupport(){const rows=(await request('/support/tickets')).tickets||[];$('#supportTickets').innerHTML=rows.length?rows.map(t=>`<div class="list-row"><div><strong>${esc(t.subject)}</strong><small>${esc(t.category)} · ${esc(t.priority)} · ${time(t.updated_at)}</small></div><span>${esc(t.status)}</span></div>`).join(''):'<p>No support tickets.</p>'}
$('#supportForm').onsubmit=async e=>{e.preventDefault();try{await request('/support/tickets',{method:'POST',body:JSON.stringify(formData(e.target))});e.target.reset();await loadSupport();toast('Support ticket created')}catch(err){toast(err.message,true)}};
function renderProfile(){const u=state.user||{};const entries=[['Public ID',u.public_user_id],['Email',u.primary_email||'Not set'],['Email verified',u.email_verified_at?'Yes':'No'],['Telegram',u.telegram_user_id?'Linked':'Not linked'],['Tier',String(u.tier||'free').toUpperCase()],['Timezone',u.timezone||'UTC'],['Travel mode',u.timezone_auto_update?'On':'Off'],['Account status',u.account_status]];$('#profileDetails').innerHTML=entries.map(([k,v])=>`<div class="detail-row"><span>${esc(k)}</span><strong>${esc(v||'—')}</strong></div>`).join('');const form=$('#profileForm');if(form){['display_name','country','timezone','locale','preferred_currency','max_risk_percentage','max_daily_drawdown_pct'].forEach(name=>{if(form.elements[name])form.elements[name].value=u[name]??''});if(form.elements.timezone_auto_update)form.elements.timezone_auto_update.checked=Boolean(u.timezone_auto_update)}}
$('#profileForm').onsubmit=async e=>{e.preventDefault();const raw=formData(e.target);const payload={timezone_auto_update:Boolean(e.target.elements.timezone_auto_update?.checked)};for(const [k,v] of Object.entries(raw)){if(k==='timezone_auto_update')continue;if(v!=='')payload[k]=['max_risk_percentage','max_daily_drawdown_pct'].includes(k)?Number(v):v}try{state.user=(await request('/profile',{method:'PATCH',body:JSON.stringify(payload)})).user;renderProfile();toast('Profile updated')}catch(err){toast(err.message,true)}};
function csvValues(value,{upper=false}={}){return String(value||'').split(',').map(x=>x.trim()).filter(Boolean).map(x=>upper?x.toUpperCase():x.toLowerCase())}
function renderTradingProfile(data){state.tradingProfile=data;const p=data?.preferences||{};const form=$('#tradingProfileForm');if(!form)return;for(const name of ['trade_profile','risk_profile','min_signal_score','risk_per_trade_pct','max_daily_loss_pct','max_signals_per_day','max_concurrent_positions']){if(form.elements[name])form.elements[name].value=p[name]??''}for(const name of ['preferred_assets','blocked_assets','preferred_timeframes','preferred_strategies','sessions']){if(form.elements[name])form.elements[name].value=(p[name]||[]).join(', ')}const classes=new Set(p.asset_classes||[]);$$('#tradingProfileForm input[name="asset_class"]').forEach(input=>input.checked=classes.has(input.value));for(const name of ['notify_on_entry','notify_on_exit','notify_on_tp','notify_on_sl']){if(form.elements[name])form.elements[name].checked=p[name]!==false}const sync=$('#tradingProfileSync');if(sync)sync.textContent=state.user?.telegram_user_id?'Synced with your linked Telegram account':'Saved for web now; it will sync when Telegram is linked'}
$('#tradingProfileForm').onsubmit=async e=>{e.preventDefault();const form=e.target;const classes=[...document.querySelectorAll('#tradingProfileForm input[name="asset_class"]:checked')].map(x=>x.value);if(!classes.length){toast('Choose at least one market',true);return}const n=name=>form.elements[name]?.value;const num=name=>{const value=n(name);return value===''?null:Number(value)};const payload={trade_profile:n('trade_profile'),risk_profile:n('risk_profile'),asset_classes:classes,preferred_assets:csvValues(n('preferred_assets'),{upper:true}),blocked_assets:csvValues(n('blocked_assets'),{upper:true}),preferred_timeframes:csvValues(n('preferred_timeframes')),preferred_strategies:csvValues(n('preferred_strategies')),sessions:csvValues(n('sessions')),min_signal_score:num('min_signal_score'),risk_per_trade_pct:num('risk_per_trade_pct'),max_daily_loss_pct:num('max_daily_loss_pct'),max_signals_per_day:num('max_signals_per_day'),max_concurrent_positions:num('max_concurrent_positions'),notify_on_entry:form.elements.notify_on_entry.checked,notify_on_exit:form.elements.notify_on_exit.checked,notify_on_tp:form.elements.notify_on_tp.checked,notify_on_sl:form.elements.notify_on_sl.checked};for(const key of Object.keys(payload)){if(payload[key]===null)delete payload[key]}try{const result=await request('/trading-profile',{method:'PUT',body:JSON.stringify(payload)});renderTradingProfile(result);toast('Trading profile synced across SignalRankAI')}catch(err){toast(err.message,true)}};
async function loadReferralLeaderboard(){const el=$('#referralLeaderboard');if(!el)return;try{const data=await request('/referrals/leaderboard');const rows=data.leaders||[];el.innerHTML=rows.length?rows.map(row=>`<div class="list-row"><div><strong>#${esc(row.rank)} · ${esc(row.label)}</strong><small>${row.is_current_user?'Your account · ':''}${esc(row.valid_referrals)} successful referrals</small></div></div>`).join(''):`<p class="muted">No successful referrals yet. You have ${esc(data.your_valid_referrals||0)}.</p>`}catch{el.innerHTML='<p class="muted">Referral leaderboard is temporarily unavailable.</p>'}}
async function loadExecutionWebhook(){const panel=$('#executionWebhookPanel');if(!panel)return;try{const data=await request('/execution-webhook');panel.hidden=false;const row=data.webhook||{};const form=$('#executionWebhookForm');if(form?.elements.url)form.elements.url.value=row.webhook_url||'';$('#executionWebhookStatus').innerHTML=row.webhook_url?`<div class="detail-row"><span>Status</span><strong>${row.is_active?'Active':'Disabled'}</strong></div><div class="detail-row"><span>Endpoint</span><strong>${esc(row.webhook_url)}</strong></div>`:'<p class="muted">No VIP execution webhook configured.</p>'}catch{panel.hidden=true}}
$('#executionWebhookForm')?.addEventListener('submit',async e=>{e.preventDefault();try{const raw=formData(e.target);await request('/execution-webhook',{method:'PUT',body:JSON.stringify({url:raw.url})});await loadExecutionWebhook();toast('Execution webhook saved')}catch(err){toast(err.message,true)}});
$('#disableExecutionWebhook')?.addEventListener('click',async()=>{if(!confirm('Disable the VIP execution webhook?'))return;try{await request('/execution-webhook',{method:'DELETE'});await loadExecutionWebhook();toast('Execution webhook disabled')}catch(err){toast(err.message,true)}});

async function loadDeveloperAccess(){try{const entitlements=await request('/entitlements');const allowed=(entitlements.features||[]).includes('rest_api');$('#developerPanel').hidden=!allowed;if(!allowed)return;const keys=await request('/api-keys');$('#apiKeyList').innerHTML=(keys.api_keys||[]).map(key=>`<div class="list-row"><div><strong>${esc(key.name)}</strong><small>${esc(key.key_prefix)} · ${key.active?'Active':'Revoked'} · last used ${time(key.last_used_at)}</small></div></div>`).join('')||'<p>No API keys.</p>'}catch{$('#developerPanel').hidden=true}}
$('#createApiKeyButton').onclick=async()=>{const name=prompt('Name this API key','Signals client');if(!name)return;try{const data=await request('/api-keys',{method:'POST',body:JSON.stringify({name,scopes:['signals:read'],expires_in_days:90})});$('#apiKeyResult').innerHTML=`<div class="detail-row"><span>Copy now</span><strong><code>${esc(data.api_key)}</code></strong></div><p>${esc(data.warning)}</p>`;await loadDeveloperAccess()}catch(err){toast(err.message,true)}};
$('#cancelAutoRenewButton')?.addEventListener('click',async()=>{if(!confirm('Turn off subscription auto-renew? Your current paid access remains active until its expiry, and this does not issue a refund.'))return;try{const result=await request('/billing/cancel-auto-renew',{method:'POST',body:JSON.stringify({confirm:true})});toast(result.provider_follow_up_required?'Auto-renew is off in SignalRankAI, but Paystack needs manual follow-up. A billing review is recommended.':'Auto-renew cancelled. Current access remains until expiry.');await loadAccount()}catch(err){toast(err.message,true)}});
$('#refundReviewForm')?.addEventListener('submit',async e=>{e.preventDefault();const raw=formData(e.target);try{const result=await request('/billing/refund-request',{method:'POST',body:JSON.stringify(raw)});e.target.reset();toast(`Refund review ticket created: ${result.ticket_id}`);await loadSupport()}catch(err){toast(err.message,true)}});

async function loadBillingProducts(){const data=await request('/billing/products');const products=data.products||[];$('#billingProducts').innerHTML=products.length?products.map(p=>`<article class="metric-card"><small>${esc(String(p.tier).toUpperCase())}</small><strong>${esc(p.display_name)}</strong><p>${esc(p.currency)} ${fmt(p.price_ngn,0)} · ${esc(p.duration_days)} days</p><button class="primary billing-checkout" data-product="${esc(p.product_id)}">Choose plan</button></article>`).join(''):'<p>No public checkout products are available.</p>';$$('.billing-checkout').forEach(button=>button.onclick=async()=>{button.disabled=true;try{const checkout=await request('/billing/checkout',{method:'POST',body:JSON.stringify({product_id:button.dataset.product,currency:'NGN'})});if(!checkout.authorization_url)throw new Error('Checkout URL unavailable');location.assign(checkout.authorization_url)}catch(err){button.disabled=false;toast(err.message,true)}})}
async function loadAccount(){const [devices,prefs,mfa,billing,referrals,tradingProfile]=await Promise.all([request('/devices'),request('/notifications/preferences'),request('/security/mfa'),request('/billing'),request('/referrals'),request('/trading-profile')]);renderTradingProfile(tradingProfile);await Promise.all([loadDeveloperAccess(),loadBillingProducts(),loadBroker()]);$('#sessionList').innerHTML=(devices.sessions||[]).map(s=>`<div class="list-row"><div><strong>${s.session_id===devices.current_session_id?'Current session':'Signed-in session'}</strong><small>${time(s.last_used_at)} · expires ${time(s.expires_at)}</small></div>${s.session_id===devices.current_session_id?'<span>Current</span>':`<button class="danger revoke-session" data-id="${esc(s.session_id)}">Revoke</button>`}</div>`).join('')||'<p>No sessions.</p>';$$('.revoke-session').forEach(b=>b.onclick=async()=>{await request('/devices/'+encodeURIComponent(b.dataset.id),{method:'DELETE'});loadAccount()});const p=prefs.preferences||{};['telegram_enabled','web_enabled','email_enabled','push_enabled'].forEach(name=>{const input=$(`#notificationForm [name="${name}"]`);if(input)input.checked=Boolean(p[name])});['quiet_hours_start','quiet_hours_end','timezone'].forEach(name=>{const input=$(`#notificationForm [name="${name}"]`);if(input)input.value=p[name]??''});$('#emailVerificationPanel').innerHTML=state.user.email_verified_at?'<p class="positive">Email verified</p>':'<button id="verifyEmailButton" class="ghost">Send verification email</button>';$('#verifyEmailButton')?.addEventListener('click',async()=>{await request('/auth/email-verification/request',{method:'POST',body:'{}'});toast('Verification email queued')});$('#mfaPanel').innerHTML=mfa.enabled?`<div class="detail-row"><span>Authenticator MFA</span><strong>Enabled</strong></div><button id="disableMfaButton" class="danger">Disable MFA</button>`:`<div class="detail-row"><span>Authenticator MFA</span><strong>Disabled</strong></div><button id="setupMfaButton" class="primary">Set up MFA</button>`;$('#setupMfaButton')?.addEventListener('click',setupMfa);$('#disableMfaButton')?.addEventListener('click',disableMfa);$('#billingHistory').innerHTML=(billing.receipts||[]).map(r=>`<div class="list-row"><div><strong>${esc(r.plan)}</strong><small>${esc(r.receipt_number)} · ${time(r.payment_date)}</small></div><span>${esc(r.currency)} ${fmt(r.amount)}</span></div>`).join('')||'<p>No payment receipts.</p>';const activeSub=(billing.subscriptions||[]).find(s=>['active','grace_period'].includes(String(s.status||'').toLowerCase()));$('#renewalPanel').innerHTML=activeSub?`<div class="detail-row"><span>Auto-renew</span><strong>${billing.auto_renew?'On':'Off'}</strong></div><div class="detail-row"><span>Current paid period</span><strong>${esc(String(activeSub.tier||'').toUpperCase())} · until ${time(activeSub.expires_at)}</strong></div>`:'<p class="muted">No active paid subscription.</p>';const cancelButton=$('#cancelAutoRenewButton');if(cancelButton)cancelButton.hidden=!(activeSub&&billing.auto_renew);const referral=$('#referralPanel');if(referral){referral.innerHTML=`<div class="detail-row"><span>Your code</span><strong><code>${esc(referrals.code)}</code></strong></div><div class="detail-row"><span>Valid referrals</span><strong>${esc(referrals.total_referrals)}</strong></div><div class="detail-row"><span>Premium days earned</span><strong>${esc(referrals.premium_days_earned)}</strong></div><div class="detail-row"><span>Next reward</span><strong>${esc(referrals.needed_for_next)} more → +${esc(referrals.reward_days)} days</strong></div><p><a class="primary link-button" href="${esc(referrals.web_url)}" target="_blank" rel="noopener">Open web referral link</a></p>${referrals.telegram_url?`<p><a class="ghost link-button" href="${esc(referrals.telegram_url)}" target="_blank" rel="noopener">Open Telegram referral link</a></p>`:''}<button id="copyReferralButton" class="ghost" type="button">Copy web referral link</button>`;$('#copyReferralButton')?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(referrals.web_url);toast('Referral link copied')}catch{toast(referrals.web_url)}})}await Promise.all([loadReferralLeaderboard(),loadExecutionWebhook()]);renderProfile()}
function brokerPolicyPct(value){const n=Number(value);return Number.isFinite(n)?n*100:''}
function brokerPolicyFraction(value){const n=Number(value);return Number.isFinite(n)?n/100:0}
function brokerPolicyCsv(value){return String(value||'').split(',').map(x=>x.trim()).filter(Boolean)}
function brokerPolicyNullablePct(value){if(value===undefined||value===null||String(value).trim()==='')return null;return brokerPolicyFraction(value)}
function brokerPolicyDays(value){return String(value||'').split(',').map(x=>Number(x.trim())).filter(x=>Number.isInteger(x)&&x>=0&&x<=6)}

async function openBrokerPolicy(connection){
  const editor=$('#brokerPolicyEditor');
  const form=$('#brokerPolicyForm');
  if(!editor||!form||!connection)return;
  let data,ledgerData;
  try{
    [data,ledgerData]=await Promise.all([
      request('/broker/connections/'+encodeURIComponent(connection.connection_id)+'/policy'),
      request('/broker/connections/'+encodeURIComponent(connection.connection_id)+'/ledger?limit=50')
    ])
  }
  catch(err){toast('Account policy could not be loaded: '+err.message,true);return}
  const p=data.policy||{};
  const reconciliation=data.reconciliation||{};
  const ledgerEntries=ledgerData.entries||[];
  form.elements.connection_id.value=connection.connection_id;
  form.elements.account_mode.value=p.account_mode||'DEMO';
  form.elements.execution_permission.value=p.execution_permission||'SIGNALS_ONLY';
  form.elements.reset_timezone.value=p.reset_timezone||'UTC';
  form.elements.currency.value=p.currency||'USD';
  for(const name of ['max_risk_per_trade_pct','max_daily_loss_pct','max_weekly_loss_pct','max_total_drawdown_pct','safety_buffer_pct']){
    if(form.elements[name])form.elements[name].value=brokerPolicyPct(p[name]);
  }
  for(const name of ['max_open_positions','max_leverage','max_spread_bps','max_slippage_bps','min_expected_rr']){
    if(form.elements[name])form.elements[name].value=p[name]??'';
  }
  form.elements.min_confidence.value=brokerPolicyPct(p.min_confidence);
  for(const name of ['external_max_daily_loss_pct','external_max_weekly_loss_pct','external_max_total_drawdown_pct']){
    form.elements[name].value=p[name]===null||p[name]===undefined?'':brokerPolicyPct(p[name]);
  }
  form.elements.allowed_instruments.value=(p.allowed_instruments||[]).join(', ');
  form.elements.allowed_asset_classes.value=(p.allowed_asset_classes||[]).join(', ');
  form.elements.allowed_strategies.value=(p.allowed_strategies||[]).join(', ');
  form.elements.news_trading_allowed.checked=p.news_trading_allowed!==false;
  form.elements.weekend_holding_allowed.checked=p.weekend_holding_allowed!==false;
  form.elements.prop_firm.value=p.prop_firm||'';
  form.elements.prop_phase.value=p.prop_phase||'';
  form.elements.prop_rules_version.value=p.prop_rules_version||'';
  form.elements.external_rules_json.value=JSON.stringify(p.external_rules||{},null,2);
  const firstWindow=(p.trading_windows||[])[0]||{};
  form.elements.trading_days.value=Array.isArray(firstWindow.days)?firstWindow.days.join(','):'';
  form.elements.trading_window_start.value=firstWindow.start||'';
  form.elements.trading_window_end.value=firstWindow.end||'';
  $('#brokerPolicyTitle').textContent=(connection.account_label||String(connection.platform||'').toUpperCase()||'Trading account')+' policy';
  $('#brokerPolicyState').innerHTML=[
    ['Policy version',p.policy_version||1],
    ['Policy status',String(p.status||'configured').toUpperCase()],
    ['PROP certification',p.account_mode==='PROP'?(p.certified?'Certified':'Required'):'Not applicable'],
    ['Safety freeze',p.frozen?(p.frozen_reason||'Active'):'Clear'],
    ['Broker reconciliation',String(reconciliation.status||'UNKNOWN').toUpperCase()]
  ].map(([k,v])=>`<div class="detail-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');
  const ledger=$('#brokerAccountLedger');
  if(ledger){
    ledger.innerHTML=ledgerEntries.length?ledgerEntries.map(entry=>{
      const financial=[
        entry.amount!==null&&entry.amount!==undefined?`amount ${entry.currency||''} ${entry.amount}`:'',
        entry.equity!==null&&entry.equity!==undefined?`equity ${entry.equity}`:'',
        entry.balance!==null&&entry.balance!==undefined?`balance ${entry.balance}`:'',
        entry.realized_pnl!==null&&entry.realized_pnl!==undefined?`realized P/L ${entry.realized_pnl}`:'',
        entry.unrealized_pnl!==null&&entry.unrealized_pnl!==undefined?`unrealized P/L ${entry.unrealized_pnl}`:'',
        entry.fees!==null&&entry.fees!==undefined?`fees ${entry.fees}`:''
      ].filter(Boolean).join(' · ');
      const refs=[entry.order_ref?`order ${entry.order_ref}`:'',entry.position_ref?`position ${entry.position_ref}`:''].filter(Boolean).join(' · ');
      return `<div class="list-row"><div><strong>${esc(String(entry.entry_type||'ledger').replaceAll('_',' ').toUpperCase())}</strong><small>${esc(String(entry.provider||'broker').toUpperCase())} · ${esc(time(entry.provider_timestamp||entry.created_at))}</small><small>${esc(financial||refs||'Provider evidence recorded')}</small></div><span>${esc(entry.currency||'')}</span></div>`;
    }).join(''):'<p class="muted">No broker-authoritative ledger events have been recorded for this account yet.</p>';
  }
  $('#freezeBrokerAccount').disabled=Boolean(p.frozen);
  $('#unfreezeBrokerAccount').disabled=!p.frozen;
  editor.hidden=false;
  editor.scrollIntoView({behavior:'smooth',block:'nearest'});
}

function brokerPolicyPayload(form){
  const raw=formData(form);
  let externalRules={};
  const externalRaw=String(raw.external_rules_json||'').trim();
  if(externalRaw){
    try{externalRules=JSON.parse(externalRaw)}
    catch{throw new Error('Advanced firm hard rules must be valid JSON.')}
    if(!externalRules||Array.isArray(externalRules)||typeof externalRules!=='object'){
      throw new Error('Advanced firm hard rules must be a JSON object.');
    }
  }
  const days=brokerPolicyDays(raw.trading_days);
  const start=String(raw.trading_window_start||'').trim();
  const end=String(raw.trading_window_end||'').trim();
  if((days.length||start||end)&&!(days.length&&start&&end)){
    throw new Error('Trading window requires days, start time and end time together.');
  }
  return {
    confirm:true,
    account_mode:raw.account_mode,
    execution_permission:raw.execution_permission,
    reset_timezone:String(raw.reset_timezone||'UTC').trim()||'UTC',
    currency:String(raw.currency||'USD').trim().toUpperCase()||'USD',
    max_risk_per_trade_pct:brokerPolicyFraction(raw.max_risk_per_trade_pct),
    max_daily_loss_pct:brokerPolicyFraction(raw.max_daily_loss_pct),
    max_weekly_loss_pct:brokerPolicyFraction(raw.max_weekly_loss_pct),
    max_total_drawdown_pct:brokerPolicyFraction(raw.max_total_drawdown_pct),
    max_open_positions:Number(raw.max_open_positions||0),
    max_leverage:Number(raw.max_leverage||0),
    max_spread_bps:Number(raw.max_spread_bps||0),
    max_slippage_bps:Number(raw.max_slippage_bps||0),
    min_confidence:brokerPolicyFraction(raw.min_confidence),
    min_expected_rr:Number(raw.min_expected_rr||0),
    safety_buffer_pct:brokerPolicyFraction(raw.safety_buffer_pct),
    external_max_daily_loss_pct:brokerPolicyNullablePct(raw.external_max_daily_loss_pct),
    external_max_weekly_loss_pct:brokerPolicyNullablePct(raw.external_max_weekly_loss_pct),
    external_max_total_drawdown_pct:brokerPolicyNullablePct(raw.external_max_total_drawdown_pct),
    allowed_instruments:brokerPolicyCsv(raw.allowed_instruments),
    allowed_asset_classes:brokerPolicyCsv(raw.allowed_asset_classes),
    allowed_strategies:brokerPolicyCsv(raw.allowed_strategies),
    trading_windows:days.length?[{days,start,end}]:[],
    news_trading_allowed:Boolean(form.elements.news_trading_allowed.checked),
    weekend_holding_allowed:Boolean(form.elements.weekend_holding_allowed.checked),
    prop_firm:String(raw.prop_firm||'').trim()||null,
    prop_phase:String(raw.prop_phase||'').trim()||null,
    prop_rules_version:String(raw.prop_rules_version||'').trim()||null,
    external_rules:externalRules
  };
}

async function saveBrokerPolicy(event){
  event.preventDefault();
  const form=event.target;
  const connectionId=form.elements.connection_id.value;
  if(!connectionId)return;
  try{
    const payload=brokerPolicyPayload(form);
    if(!confirm('Save this account policy? Execution will be disabled until you explicitly re-enable this account.'))return;
    await request('/broker/connections/'+encodeURIComponent(connectionId)+'/policy',{method:'PUT',body:JSON.stringify(payload)});
    toast('Account policy saved. Execution remains disabled until explicitly re-enabled.');
    await loadBroker();
    const connection=(state.broker?.connections||[]).find(x=>x.connection_id===connectionId);
    if(connection)await openBrokerPolicy(connection);
  }catch(err){toast(err.message,true)}
}

async function setBrokerSafetyFreeze(frozen){
  const form=$('#brokerPolicyForm');
  const connectionId=form?.elements.connection_id?.value;
  if(!connectionId)return;
  let reason='user_unfreeze';
  if(frozen){
    reason=prompt('Reason for immediately freezing new execution on this account:','manual safety freeze')||'';
    if(!reason.trim())return;
  }else if(!confirm('Clear your manual safety freeze? System/reconciliation freezes cannot be cleared here. Execution will still remain disabled until separately re-enabled.'))return;
  try{
    await request('/broker/connections/'+encodeURIComponent(connectionId)+'/safety-freeze',{method:'POST',body:JSON.stringify({frozen,confirm:true,reason})});
    toast(frozen?'Account safety freeze enabled':'Manual safety freeze cleared');
    await loadBroker();
    const connection=(state.broker?.connections||[]).find(x=>x.connection_id===connectionId);
    if(connection)await openBrokerPolicy(connection);
  }catch(err){toast(err.message,true)}
}

$('#brokerPolicyForm')?.addEventListener('submit',saveBrokerPolicy);
$('#closeBrokerPolicy')?.addEventListener('click',()=>{$('#brokerPolicyEditor').hidden=true});
$('#freezeBrokerAccount')?.addEventListener('click',()=>setBrokerSafetyFreeze(true));
$('#unfreezeBrokerAccount')?.addEventListener('click',()=>setBrokerSafetyFreeze(false));

async function loadBroker(){
  const panel=$('#brokerPanel');
  if(!panel)return;
  if(!hasFeature('broker_connection')){panel.hidden=true;return}
  panel.hidden=false;
  try{
    const data=await request('/broker');
    state.broker=data;
    const ex=data.execution||{};
    const connections=data.connections||[];
    const platforms=data.platforms||[];
    const accountStats=data.stats?.accounts||[];
    const accountStatsById=new Map(accountStats.map(row=>[String(row.connection_id||''),row]));
    const readyConnections=connections.filter(x=>['verified','ready','linked'].includes(String(x.status||'').toLowerCase()));
    const executableConnections=connections.filter(x=>x.execution_enabled===true);
    $('#brokerReadinessBadge').textContent=executableConnections.length?'EXECUTION READY':readyConnections.length?'CONNECTED':'NOT CONNECTED';

    const catalog=$('#brokerPlatformCatalog');
    if(catalog){
      catalog.innerHTML=platforms.map(p=>{
        const stateLabel=p.execution_adapter==='ready'?'Execution ready':p.execution_adapter==='integration'?'Connector integration':'Custom integration';
        return `<div class="metric-card"><small>${esc(p.name)}</small><strong>${esc(stateLabel)}</strong><span class="${p.configured?'positive':'muted'}">${p.configured?'Configured':'Setup required'}</span><small>${esc((p.asset_classes||[]).join(' · '))}</small></div>`;
      }).join('');
    }

    const connectionList=$('#brokerConnections');
    if(connectionList){
      connectionList.innerHTML=connections.length?connections.map(x=>{
        const status=String(x.status||'pending').toUpperCase();
        const env=String(x.environment||'unknown').toUpperCase();
        const exec=x.execution_enabled?'Execution allowed':'Execution off';
        const defaultTag=x.is_default?'Default · ':'';
        const account=x.account_ref_masked||'Account hidden';
        const verifyButton=x.connector==='metaapi'?'<button class="ghost broker-action" data-action="verify">Verify</button>':'';
        const accountPerf=accountStatsById.get(String(x.connection_id||''))||{};
        const perfParts=[
          accountPerf.executions!==undefined?`${accountPerf.executions} executions`:'',
          accountPerf.wins!==undefined?`${accountPerf.wins} wins`:'',
          accountPerf.losses!==undefined?`${accountPerf.losses} losses`:'',
          accountPerf.realized_pnl!==null&&accountPerf.realized_pnl!==undefined?`realized P/L ${fmt(accountPerf.realized_pnl||0)}`:''
        ].filter(Boolean).join(' · ');
        const mode=String(accountPerf.account_mode||x.account_classification||'UNKNOWN').toUpperCase();
        return `<div class="list-row" data-connection-id="${esc(x.connection_id)}"><div><strong>${esc(x.account_label||x.platform?.toUpperCase()||'Trading account')}</strong><small>${esc(defaultTag+String(x.platform||'').toUpperCase())} · ${esc(x.broker_name||x.connector||'Broker')} · ${esc(env)} · ${esc(mode)} · ${esc(account)}</small><small>${esc(status)} · ${esc(exec)}${x.last_error_message?' · '+esc(x.last_error_message):''}</small><small>${esc(perfParts||'No account-specific closed performance yet')}</small></div><div class="row-actions">${verifyButton}<button class="ghost broker-action" data-action="default">Default</button><button class="ghost broker-action" data-action="policy">Risk policy</button><button class="${x.execution_enabled?'danger':'primary'} broker-action" data-action="execution">${x.execution_enabled?'Disable execution':'Enable execution'}</button><button class="danger broker-action" data-action="remove">Remove</button></div></div>`;
      }).join(''):'<p class="muted">No trading accounts connected yet.</p>';
    }

    $('#brokerStats').innerHTML=[
      ['Connected accounts',connections.length],
      ['Execution-enabled',executableConnections.length],
      ['Accounts with execution evidence',accountStats.filter(x=>Number(x.executions||0)>0).length],
      ['Performance scope','Per account only']
    ].map(([k,v])=>`<div class="detail-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('')+
      '<p class="muted">Demo, personal-live and PROP performance are not combined into one headline. Open each account policy/ledger for its own evidence.</p>';

    $('#brokerStatus').innerHTML=[
      ['Connection does not grant trading','Yes'],
      ['Demo-first support','Yes'],
      ['Live requires separate activation','Yes'],
      ['Global real-money activation',data.safety?.global_activation_still_required?'Still required':'Unknown']
    ].map(([k,v])=>`<div class="detail-row"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');

    const form=$('#executionSettingsForm');
    if(form){
      for(const name of ['trading_mode','execution_mode','execution_provider','fixed_lot_size','auto_signals_daily_limit']){
        if(form.elements[name])form.elements[name].value=ex[name]??''
      }
    }
    $('#executionTermsPanel').innerHTML=ex.accepted_terms
      ?'<p class="positive">Execution-risk terms accepted. Account-level execution permission is still separate.</p>'
      :'<p class="muted">Broker execution remains blocked until you explicitly accept the execution-risk terms.</p><button id="acceptExecutionTerms" class="ghost" type="button">Accept execution-risk terms</button>';
    $('#acceptExecutionTerms')?.addEventListener('click',acceptExecutionTerms);

    $$('.broker-action').forEach(button=>button.onclick=async()=>{
      const row=button.closest('[data-connection-id]');
      const connectionId=row?.dataset.connectionId;
      const connection=connections.find(x=>x.connection_id===connectionId);
      if(!connectionId||!connection)return;
      const action=button.dataset.action;
      try{
        if(action==='verify'){
          await request('/broker/connections/'+encodeURIComponent(connectionId)+'/verify',{method:'POST',body:'{}'});
          toast('Broker connection verified');
        }else if(action==='default'){
          await request('/broker/connections/'+encodeURIComponent(connectionId)+'/default',{method:'POST',body:JSON.stringify({confirm:true})});
          toast('Default broker route updated');
        }else if(action==='policy'){
          await openBrokerPolicy(connection);
          return;
        }else if(action==='execution'){
          const enable=!connection.execution_enabled;
          const warning=enable
            ?'Enable broker execution for this account? This only grants account-level permission. Every trade still requires SignalRankAI risk, quote, market, evidence, quota, reconciliation and kill-switch checks.'
            :'Disable broker execution for this account immediately?';
          if(!confirm(warning))return;
          await request('/broker/connections/'+encodeURIComponent(connectionId)+'/execution',{method:'POST',body:JSON.stringify({enabled:enable,confirm:true})});
          toast(enable?'Account execution permission enabled':'Account execution permission disabled');
        }else if(action==='remove'){
          if(!confirm('Remove this broker connection? Execution must be disabled first.'))return;
          await request('/broker/connections/'+encodeURIComponent(connectionId),{method:'DELETE'});
          toast('Broker connection removed');
        }
        await loadBroker();
      }catch(err){toast(err.message,true)}
    });
  }catch(err){
    panel.hidden=false;
    $('#brokerStatus').innerHTML=`<p class="negative">${esc(err.message)}</p>`;
  }

  if($('#brokerLinkForm'))$('#brokerLinkForm').onsubmit=async e=>{
    e.preventDefault();
    const raw=formData(e.target);
    try{
      await request('/broker/metatrader',{method:'POST',body:JSON.stringify(raw)});
      e.target.elements.password.value='';
      await loadBroker();
      toast(raw.environment==='demo'?raw.platform.toUpperCase()+' demo connection saved':raw.platform.toUpperCase()+' connection saved');
    }catch(err){toast(err.message,true)}
  };

  if($('#brokerSecureLinkButton'))$('#brokerSecureLinkButton').onclick=async()=>{
    const form=$('#brokerLinkForm');
    if(!form)return;
    const raw=formData(form);
    if(!raw.server){toast('Enter the exact broker server first',true);return}
    const payload={
      platform:raw.platform,
      server:raw.server,
      broker_name:raw.broker_name||null,
      account_label:raw.account_label||null,
      environment:raw.environment||'unknown',
      ttl_days:3
    };
    try{
      const result=await request('/broker/metatrader/secure-link',{method:'POST',body:JSON.stringify(payload)});
      const target=$('#brokerSecureLinkResult');
      target.innerHTML=`<p class="positive">Secure credential link created.</p><p><a class="primary link-button" href="${esc(result.configuration_link)}" target="_blank" rel="noopener noreferrer">Open MetaApi secure connection</a></p><p class="muted">After entering the account credentials there, return here and press Verify on the connection.</p>`;
      window.open(result.configuration_link,'_blank','noopener,noreferrer');
      await loadBroker();
    }catch(err){toast(err.message,true)}
  };

  if($('#executionSettingsForm'))$('#executionSettingsForm').onsubmit=async e=>{
    e.preventDefault();
    const raw=formData(e.target);
    const payload={
      execution_mode:raw.execution_mode,
      trading_mode:raw.trading_mode,
      execution_provider:raw.execution_provider,
      fixed_lot_size:raw.fixed_lot_size===''?undefined:Number(raw.fixed_lot_size),
      auto_signals_daily_limit:raw.auto_signals_daily_limit===''?undefined:Number(raw.auto_signals_daily_limit)
    };
    Object.keys(payload).forEach(k=>payload[k]===undefined&&delete payload[k]);
    try{
      await request('/execution-settings',{method:'PUT',body:JSON.stringify(payload)});
      await loadBroker();
      toast('Execution settings updated');
    }catch(err){toast(err.message,true)}
  };
}
async function acceptExecutionTerms(){if(!confirm('I understand that live broker execution can lose money and that SignalRankAI safety checks do not guarantee outcomes. Accept execution-risk terms?'))return;try{await request('/execution-terms/accept',{method:'POST',body:JSON.stringify({confirm:true})});await loadBroker();toast('Execution-risk terms accepted')}catch(err){toast(err.message,true)}}
async function setupMfa(){try{const setup=await request('/security/mfa/setup',{method:'POST',body:'{}'});const code=prompt(`Add this secret to your authenticator:\n${setup.secret}\n\nThen enter the 6-digit code.`);if(!code)return;const result=await request('/security/mfa/enable',{method:'POST',body:JSON.stringify({code})});alert('Store these recovery codes offline:\n\n'+result.recovery_codes.join('\n'));await loadAccount();toast('MFA enabled')}catch(err){toast(err.message,true)}}
async function disableMfa(){const code=prompt('Enter an authenticator or recovery code to disable MFA');if(!code)return;try{await request('/security/mfa/disable',{method:'POST',body:JSON.stringify({code})});await loadAccount();toast('MFA disabled')}catch(err){toast(err.message,true)}}
$('#connectTelegramButton').onclick=async()=>{try{const data=await request('/account/telegram-link',{method:'POST',body:'{}'});const result=$('#telegramLinkResult');result.hidden=false;result.innerHTML=`<div class="detail-row"><span>One-time code</span><strong>${esc(data.code)}</strong></div><p>Send <code>/link ${esc(data.code)}</code> to the bot before ${time(data.expires_at)}.</p>${data.telegram_deep_link?`<p><a class="primary link-button" href="${esc(data.telegram_deep_link)}" target="_blank" rel="noopener">Open Telegram</a></p>`:''}`;toast('Telegram link code created')}catch(err){toast(err.message,true)}};
$('#notificationForm').onsubmit=async e=>{e.preventDefault();const payload={};['telegram_enabled','web_enabled','email_enabled','push_enabled'].forEach(name=>payload[name]=e.target.elements[name].checked);for(const name of ['quiet_hours_start','quiet_hours_end','timezone']){const value=e.target.elements[name]?.value?.trim();payload[name]=value||null}try{await request('/notifications/preferences',{method:'PUT',body:JSON.stringify(payload)});toast('Notification preferences saved across your account')}catch(err){toast(err.message,true)}};
async function logout(){try{await request('/auth/logout',{method:'POST',body:'{}'})}finally{state.user=null;setLoggedIn(false);location.reload()}}
$('#logoutButton').onclick=logout;$('#logoutAllButton').onclick=async()=>{if(!confirm('Sign out every device?'))return;try{await request('/auth/logout-all',{method:'POST',body:'{}'});location.reload()}catch(err){toast(err.message,true)}};
async function processUrlActions(){const qs=new URLSearchParams(location.search);const token=qs.get('token');if(token){setAuthTab('activate');$('#activationCredential').value=token}const reset=qs.get('password_reset');if(reset){setAuthTab('login');$('#loginForm').hidden=true;$('#passwordResetForm').hidden=false;$('#passwordResetForm [name="token"]').value=reset}const verify=qs.get('verify_email');if(verify){try{await request('/auth/email-verification/complete',{method:'POST',body:JSON.stringify({token:verify,client_type:'web'})});history.replaceState({},'',location.pathname);toast('Email verified')}catch(err){toast(err.message,true)}}const magic=qs.get('magic_login');if(magic){try{await completeAuth(await request('/auth/magic-link/complete',{method:'POST',body:JSON.stringify({token:magic,client_type:'web'})}));history.replaceState({},'',location.pathname)}catch(err){toast(err.message,true)}}}
if('serviceWorker'in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('/app/service-worker.js').catch(()=>{}))}
initTheme();
processUrlActions().then(boot);

$('#refreshPaper')?.addEventListener('click',()=>loadPaper().catch(e=>toast(e.message,true)));
$('#paperSettingsForm')?.addEventListener('submit',async e=>{e.preventDefault();const f=e.target;const classes=$$('#paperSettingsForm input[name="paper_asset_class"]:checked').map(x=>x.value);const payload={auto_trade_enabled:f.elements.auto_trade_enabled.checked,risk_pct:Number(f.elements.risk_pct.value||1),max_open_positions:Number(f.elements.max_open_positions.value||5),min_signal_score:Number(f.elements.min_signal_score.value||0),spread_bps:Number(f.elements.spread_bps.value||0),slippage_bps:Number(f.elements.slippage_bps.value||0),fee_bps:Number(f.elements.fee_bps.value||0),target_mode:f.elements.target_mode.value,allowed_directions:f.elements.allowed_directions.value,allowed_asset_classes:classes};try{await request('/paper/settings',{method:'PUT',body:JSON.stringify(payload)});await loadPaper();toast('Paper settings saved')}catch(err){toast(err.message,true)}});
$('#paperCloseAll')?.addEventListener('click',async()=>{if(!confirm('Close every open virtual position using the latest trusted quotes? No live broker orders are affected.'))return;try{const r=await request('/paper/close-all',{method:'POST',body:JSON.stringify({confirm:true,allow_last_mark_fallback:false})});toast(`Closed ${r.result?.closed||0} paper position(s); ${r.result?.failed||0} remain open.`);await loadPaper()}catch(err){toast(err.message,true)}});
$('#paperReset')?.addEventListener('click',async()=>{const balance=Number($('#paperResetBalance')?.value||10000);if(!confirm(`Reset the virtual paper account to $${fmt(balance)}? This deletes paper history and is blocked while positions are open.`))return;try{await request('/paper/reset',{method:'POST',body:JSON.stringify({starting_balance:balance,confirm:true})});toast('Paper account reset');await loadPaper()}catch(err){toast(err.message,true)}});
