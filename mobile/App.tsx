import React, {useEffect, useState} from 'react';
import {ActivityIndicator, Alert, AppState, FlatList, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme} from 'react-native';
import * as Linking from 'expo-linking';
import {StatusBar} from 'expo-status-bar';
import {
  activateTelegram, api, beginMfaSetup, logout, completeMagicLogin,
  completeMfa, completePasswordReset, createBillingCheckout, createJournalEntry, createTelegramLink,
  disableMfa, enableMfa, getBilling, getBillingProducts, login, mfaStatus, register, registerPushDevice,
  PlatformAPIError, requestMagicLink, requestPasswordReset, updateProfile,
  getSessionGeneration,
} from './src/api';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import {amountTone, currencyLabel, percentLabel, quantityLabel, safeLabel} from './src/presentation';
import {MobileNavigation} from './src/MobileNavigation';
import {NativeBrokers,NativeNotifications,NativeWatchlists} from './src/AccountScreens';

type Screen = 'overview'|'signals'|'markets'|'paper'|'portfolio'|'performance'|'journal'|'support'|'account'|'brokers'|'notifications'|'watchlists';
type AuthMode = 'login'|'register'|'activate'|'mfa'|'reset';

export default function App() {
  const styles=useNativeStyles();
  const scheme=useColorScheme();
  const [loading,setLoading]=useState(true); const [user,setUser]=useState<any>(null);
  const [screen,setScreen]=useState<Screen>('overview'); const [authMode,setAuthMode]=useState<AuthMode>('login');
  const [form,setForm]=useState({displayName:'',email:'',password:'',code:'',mfaToken:'',resetToken:''}); const [error,setError]=useState('');
  const loadMe=async()=>{
    const generation=getSessionGeneration();
    try{
      const result=await api<any>('/me');
      if(generation===getSessionGeneration())setUser(result.user);
    }catch(e){
      const current=generation===getSessionGeneration()||(e instanceof PlatformAPIError&&e.generation===getSessionGeneration());
      if(current){
        if(e instanceof PlatformAPIError&&(e.status===401||e.status===403||e.code==='session_storage_failed'))setUser(null);
        setError(e instanceof Error?e.message:'Could not refresh account status');
        setLoading(false);
      }
    }finally{if(generation===getSessionGeneration())setLoading(false)}
  };
  useEffect(()=>{loadMe()},[]);
  useEffect(()=>{if(!user)return;const sub=AppState.addEventListener('change',next=>{if(next==='active')void loadMe()});return()=>sub.remove()},[user?.id]);
  useEffect(()=>{const handle=async({url}:{url:string})=>{const parsed=Linking.parse(url);const q:any=parsed.queryParams||{};try{if(q.magic_login){setLoading(true);const result=await completeMagicLogin(String(q.magic_login));if(result.mfa_required){setForm(v=>({...v,mfaToken:String(result.mfa_token||'')}));setAuthMode('mfa')}else setUser(result.user)}else if(q.password_reset){setForm(v=>({...v,resetToken:String(q.password_reset)}));setAuthMode('reset')}else if(q.token){setForm(v=>({...v,code:String(q.token)}));setAuthMode('activate')}}catch(e){setError(e instanceof Error?e.message:'Link failed')}finally{setLoading(false)}};Linking.getInitialURL().then(url=>{if(url)handle({url})});const sub=Linking.addEventListener('url',handle);return()=>sub.remove()},[]);
  useEffect(()=>{if(!user||!Device.isDevice||!['android','ios'].includes(Platform.OS))return;void(async()=>{try{const current=await Notifications.getPermissionsAsync();const permission=current.status==='granted'?current:await Notifications.requestPermissionsAsync();if(permission.status!=='granted')return;if(Platform.OS==='android')await Notifications.setNotificationChannelAsync('signals',{name:'Signal updates',importance:Notifications.AndroidImportance.HIGH});const projectId=process.env.EXPO_PUBLIC_EAS_PROJECT_ID||Constants.expoConfig?.extra?.eas?.projectId;if(!projectId)return;const token=await Notifications.getExpoPushTokenAsync({projectId});await registerPushDevice({pushToken:token.data,platform:Platform.OS as 'android'|'ios',deviceId:`${Device.osName||Platform.OS}:${Device.modelName||'device'}`,appVersion:Constants.expoConfig?.version})}catch{}})()},[user]);
  const authenticate=async()=>{setError('');setLoading(true);try{if(authMode==='reset'){await completePasswordReset(form.resetToken,form.password);setAuthMode('login');setError('Password reset. Sign in again.');return}const result=authMode==='login'?await login(form.email,form.password):authMode==='register'?await register(form.displayName,form.email,form.password):authMode==='activate'?await activateTelegram(form.code,form.email,form.password):await completeMfa(form.mfaToken,form.code);if(result.mfa_required){setForm(v=>({...v,mfaToken:String(result.mfa_token||''),code:''}));setAuthMode('mfa')}else{setUser(result.user);setScreen('overview')}}catch(e){setError(e instanceof Error?e.message:'Authentication failed')}finally{setLoading(false)}};
  if(loading)return <SafeAreaView style={styles.center}><ActivityIndicator color="#4ce0a4"/><StatusBar style={scheme==='light'?'dark':'light'}/></SafeAreaView>;
  if(!user)return <Auth mode={authMode} setMode={setAuthMode} form={form} setForm={setForm} error={error} submit={authenticate}/>;
  return <SafeAreaView style={styles.root}><StatusBar style={scheme==='light'?'dark':'light'}/><View style={styles.header}><View><Text style={styles.eyebrow}>SIGNALRANKAI</Text><Text style={styles.title}>Welcome{user.display_name?`, ${String(user.display_name).split(' ')[0]}`:''}</Text></View><Text style={styles.badge}>{String(user.tier||'free').toUpperCase()}</Text></View>{error?<View accessibilityRole="alert"><Text style={styles.error}>{error}</Text><Pressable accessibilityRole="button" onPress={()=>{setError('');void loadMe()}}><Text style={styles.link}>Retry account refresh</Text></Pressable></View>:null}<View style={styles.content}>{screen==='overview'?<Overview/>:screen==='signals'?<Signals/>:screen==='markets'?<Markets/>:screen==='paper'?<Paper/>:screen==='portfolio'?<Portfolio/>:screen==='performance'?<Performance/>:screen==='journal'?<Journal/>:screen==='support'?<Support/>:screen==='brokers'?<NativeBrokers/>:screen==='notifications'?<NativeNotifications/>:screen==='watchlists'?<NativeWatchlists/>:<Account user={user} setUser={setUser} onRefresh={loadMe} onLogout={async()=>{const generation=getSessionGeneration()+1;setUser(null);setError('');setAuthMode('login');setForm({displayName:'',email:'',password:'',code:'',mfaToken:'',resetToken:''});const result=await logout();if(generation===getSessionGeneration()){if(!result.device_credentials_removed)setError('Device credentials could not be removed. Revoke this device session from Security.');else if(!result.server_session_revoked)setError('Signed out on this device. Server sign-out could not be confirmed. Revoke this device session from Security when you reconnect.')}}}/>}</View><MobileNavigation active={screen} onSelect={setScreen}/></SafeAreaView>;
}

function Auth({mode,setMode,form,setForm,error,submit}:any){const styles=useNativeStyles();const scheme=useColorScheme();const magic=async()=>{if(!form.email)return setForm({...form});try{await requestMagicLink(form.email);Alert.alert('Check your email','If the account exists, a sign-in link was queued.')}catch(e){Alert.alert('Error',e instanceof Error?e.message:'Could not request link')}};const reset=async()=>{if(!form.email)return;try{await requestPasswordReset(form.email);Alert.alert('Check your email','If the account exists, reset instructions were queued.')}catch(e){Alert.alert('Error',e instanceof Error?e.message:'Could not request reset')}};return <SafeAreaView style={styles.root}><ScrollView contentContainerStyle={styles.auth}><Text style={styles.eyebrow}>ONE ACCOUNT. EVERY CHANNEL.</Text><Text style={styles.hero}>SignalRankAI follows you.</Text><Text style={styles.muted}>Keep Telegram signals, subscriptions, paper positions and preferences when you move into the app.</Text>{!['mfa','reset'].includes(mode)&&<View style={styles.tabs}>{(['login','register','activate'] as AuthMode[]).map(x=><Pressable key={x} onPress={()=>setMode(x)} style={[styles.tab,mode===x&&styles.tabActive]}><Text style={styles.navText}>{x}</Text></Pressable>)}</View>}{mode==='register'&&<TextInput style={styles.input} placeholder="Display name" placeholderTextColor="#869f91" value={form.displayName} onChangeText={(v)=>setForm({...form,displayName:v})}/>} {mode==='activate'&&<TextInput style={styles.input} placeholder="Telegram one-time code" placeholderTextColor="#869f91" value={form.code} onChangeText={(v)=>setForm({...form,code:v})}/>} {mode==='mfa'&&<><Text style={styles.rowTitle}>Two-factor authentication</Text><TextInput style={styles.input} placeholder="Authenticator or recovery code" placeholderTextColor="#869f91" value={form.code} onChangeText={(v)=>setForm({...form,code:v})}/></>} {mode==='reset'&&<Text style={styles.rowTitle}>Choose a new password</Text>} {!['mfa'].includes(mode)&&<TextInput style={styles.input} placeholder="Email" placeholderTextColor="#869f91" autoCapitalize="none" keyboardType="email-address" value={form.email} onChangeText={(v)=>setForm({...form,email:v})}/>} {!['mfa'].includes(mode)&&<TextInput style={styles.input} placeholder={mode==='reset'?'New password':'Password'} placeholderTextColor="#869f91" secureTextEntry value={form.password} onChangeText={(v)=>setForm({...form,password:v})}/>} {error?<Text style={styles.error}>{error}</Text>:null}<Pressable style={styles.primary} onPress={submit}><Text style={styles.primaryText}>{mode==='login'?'Log in':mode==='register'?'Create account':mode==='activate'?'Activate Telegram account':mode==='mfa'?'Verify code':'Reset password'}</Text></Pressable>{mode==='login'&&<View style={styles.inline}><Pressable onPress={magic}><Text style={styles.link}>Email sign-in link</Text></Pressable><Pressable onPress={reset}><Text style={styles.link}>Reset password</Text></Pressable></View>}</ScrollView><StatusBar style={scheme==='light'?'dark':'light'}/></SafeAreaView>}


type AccountData<T> = {data:T|null;loading:boolean;error:string;retry:()=>void};
function useAccountData<T=any>(route:string):AccountData<T>{
  const [version,setVersion]=useState(0);
  const [state,setState]=useState<{data:T|null;loading:boolean;error:string}>({data:null,loading:true,error:''});
  useEffect(()=>{
    let active=true;
    setState({data:null,loading:Boolean(route),error:''});
    if(!route)return ()=>{active=false};
    api<T>(route)
      .then(value=>{if(active)setState({data:value,loading:false,error:''})})
      .catch(e=>{if(active)setState({data:null,loading:false,error:e instanceof Error?e.message:'The service could not be verified.'})});
    return()=>{active=false};
  },[route,version]);
  return {...state,retry:()=>setVersion(value=>value+1)};
}
function AccountDataState({loading,error,retry}:{loading:boolean;error:string;retry:()=>void}){
  const styles=useNativeStyles();
  if(loading)return <View style={styles.feedbackPanel}><ActivityIndicator color="#4ce0a4"/><Text style={styles.muted}>Retrieving verified account data…</Text></View>;
  if(error)return <View style={styles.feedbackPanel} accessibilityRole="alert">
    <Text style={styles.rowTitle}>Account information unavailable</Text><Text style={styles.muted}>{error}</Text>
    <Pressable accessibilityRole="button" style={styles.primary} onPress={retry}><Text style={styles.primaryText}>Retry securely</Text></Pressable>
  </View>;
  return null;
}
function MetricTile({title,value,detail}:{title:string;value:string;detail?:string}){
  const styles=useNativeStyles();
  return <View style={styles.card}><Text style={styles.muted}>{title}</Text><Text style={styles.metric}>{value}</Text>
    {detail?<Text style={styles.muted}>{detail}</Text>:null}</View>;
}

function Overview(){
  const styles=useNativeStyles();
  const {data,loading,error,retry}=useAccountData<any>('/dashboard');
  if(!data)return <AccountDataState loading={loading} error={error} retry={retry}/>;
  const summary=data.summary||{};
  return <ScrollView showsVerticalScrollIndicator={false}>
    <Text style={styles.sectionLabel}>ACCOUNT / DECISION OVERVIEW</Text>
    <Text style={styles.body}>Canonical receipts and simulated balances. This screen never authorizes broker execution.</Text>
    <View style={styles.grid}>
      <MetricTile title="Delivered signals" value={quantityLabel(summary.delivered_signals,0)} detail="Receipt-backed history"/>
      <MetricTile title="Open paper positions" value={quantityLabel(summary.open_positions,0)} detail="Simulated"/>
      <MetricTile title="Paper cash (currency not reported)" value={quantityLabel(summary.paper_cash)} detail="Not live broker funds"/>
      <MetricTile title="Unrealized paper P&L (currency not reported)" value={quantityLabel(summary.unrealized_pnl)} detail="Unverified currency"/>
    </View>
    <View style={styles.disclosure}><Text style={styles.muted}>Missing market or account data is unavailable—not zero. Brokerage eligibility must be verified independently.</Text></View>
  </ScrollView>;
}

function Signals(){
  const styles=useNativeStyles();
  const {data,loading,error,retry}=useAccountData<any>('/signals?limit=50');
  const [selected,setSelected]=useState('');
  if(selected)return <NativeSignalEvidence id={selected} back={()=>setSelected('')}/>;
  if(!data)return <AccountDataState loading={loading} error={error} retry={retry}/>;
  const list=Array.isArray(data.signals)?data.signals:[];
  return <FlatList
    data={list}
    keyExtractor={(row,i)=>String(row.signal_id||i)}
    ListHeaderComponent={<View style={styles.disclosure}><Text style={styles.muted}>Delivered account signals only. A signal receipt is not proof of an order, fill or future return.</Text></View>}
    ListEmptyComponent={<Text style={styles.muted}>No delivered signals were returned. No trade can be a valid outcome.</Text>}
    renderItem={({item})=><Pressable accessibilityRole="button" onPress={()=>{if(item.signal_id)setSelected(String(item.signal_id))}} style={styles.row}>
      <View style={{flex:1,minWidth:0}}><Text style={styles.rowTitle}>{safeLabel(item.asset,'Instrument')} · {safeLabel(item.direction,'Direction').toUpperCase()}</Text>
        <Text style={styles.muted}>{safeLabel(item.timeframe)} / {safeLabel(item.strategy_name)}</Text>
        <Text style={styles.muted}>Calibrated probability: {percentLabel(item.ml_probability_calibrated)}</Text>
      </View><Text style={styles.badge}>{safeLabel(item.outcome_status,'Unreported')}</Text>
    </Pressable>}/>;
}
function NativeSignalEvidence({id,back}:{id:string;back:()=>void}){
  const styles=useNativeStyles();
  const {data,loading,error,retry}=useAccountData<any>('/signals/'+encodeURIComponent(id));
  if(!data)return <View style={{flex:1}}><Pressable accessibilityRole="button" onPress={back}><Text style={styles.link}>← Back to signals</Text></Pressable><AccountDataState loading={loading} error={error} retry={retry}/></View>;
  const signal=data.signal||{}, proof=data.proof||{}, events=Array.isArray(data.events)?data.events:[];
  const confirmed=proof.access_proven===true?'Receipt confirmed':proof.access_proven===false?'Not confirmed':'Unavailable';
  return <ScrollView showsVerticalScrollIndicator={false}>
    <Pressable accessibilityRole="button" onPress={back}><Text style={styles.link}>← Delivered signals</Text></Pressable>
    <Text style={styles.eyebrow}>SIGNAL / ENTITLED EVIDENCE</Text>
    <Text style={styles.heroTitle}>{safeLabel(signal.asset,'Instrument')} · {safeLabel(signal.direction)}</Text>
    <View style={styles.disclosure}><Text style={styles.muted}>Delivery proof does not certify broker execution or real-money results.</Text></View>
    <MetricTile title="Account delivery proof" value={confirmed} detail={safeLabel(proof.delivery_channel,'Channel unknown')}/>
    <View style={styles.grid}>
      <MetricTile title="Entry" value={quantityLabel(signal.entry,6)}/>
      <MetricTile title="Stop" value={quantityLabel(signal.stop_loss,6)}/>
      <MetricTile title="First target" value={quantityLabel(signal.take_profit,6)}/>
      <MetricTile title="Calibrated probability" value={percentLabel(signal.ml_probability_calibrated)}/>
      <MetricTile title="Lifecycle state" value={safeLabel(signal.lifecycle_state)}/>
      <MetricTile title="Recorded outcome" value={safeLabel(signal.canonical_outcome)}/>
    </View>
    <Text style={styles.sectionLabel}>LIFECYCLE EVENTS / {events.length}</Text>
    {events.length?events.map((event:any,i:number)=><View key={i} style={styles.row}>
      <Text style={styles.rowTitle}>{safeLabel(event.event_type,'Observation')}</Text>
      <Text style={styles.muted}>{quantityLabel(event.price,6)}</Text>
    </View>):<Text style={styles.muted}>No events returned. Do not infer a fill or closure.</Text>}
  </ScrollView>;
}

function Markets(){
  const styles=useNativeStyles();const [q,setQ]=useState('');const [rows,setRows]=useState<any[]>([]);const search=()=>api<any>(`/instruments/search?q=${encodeURIComponent(q)}&limit=50`).then(x=>setRows(x.instruments||[])).catch(()=>{});useEffect(()=>{search()},[]);return <View style={{flex:1}}><View style={styles.searchRow}><TextInput style={[styles.input,{flex:1,marginBottom:0}]} placeholder="Search markets" placeholderTextColor="#869f91" value={q} onChangeText={setQ}/><Pressable style={styles.primary} onPress={search}><Text style={styles.primaryText}>Search</Text></Pressable></View><FlatList data={rows} keyExtractor={x=>x.instrument_id} renderItem={({item})=><View style={styles.row}><View><Text style={styles.rowTitle}>{item.display_symbol||item.canonical_symbol}</Text><Text style={styles.muted}>{item.asset_class} · {item.instrument_type}</Text></View><Text style={styles.muted}>{(item.providers||[]).join(', ')}</Text></View>}/></View>}
function Paper(){
  const styles=useNativeStyles();
  const {data,loading,error,retry}=useAccountData<any>('/paper');
  if(!data)return <AccountDataState loading={loading} error={error} retry={retry}/>;
  const account=data.account||{}, snapshot=data.snapshot||{};
  const currency=account.currency;
  const positions=Array.isArray(data.positions)?data.positions:[];
  return <FlatList
    data={positions}
    keyExtractor={(row,i)=>String(row.position_id||i)}
    ListHeaderComponent={<View>
      <View style={styles.disclosure}><Text style={styles.muted}>SIMULATED FUNDS ONLY — paper positions do not establish live broker fills.</Text></View>
      <View style={styles.grid}>
        <MetricTile title="Paper cash" value={currencyLabel(account.cash_balance??snapshot.cash_balance,currency)}/>
        <MetricTile title="Paper equity" value={currencyLabel(snapshot.equity,currency)}/>
        <MetricTile title="Open paper positions" value={quantityLabel(snapshot.open_positions,0)}/>
      </View>
    </View>}
    ListEmptyComponent={<Text style={styles.muted}>No paper positions were returned.</Text>}
    renderItem={({item})=><View style={styles.row}>
      <View style={{flex:1,minWidth:0}}><Text style={styles.rowTitle}>{safeLabel(item.asset,'Instrument')} · {safeLabel(item.direction)}</Text>
        <Text style={styles.muted}>{safeLabel(item.status)} · entry {quantityLabel(item.fill_entry,6)}</Text>
      </View>
      <Text style={amountTone(item.unrealized_pnl)==='positive'?styles.gain:amountTone(item.unrealized_pnl)==='negative'?styles.loss:styles.muted}>{currencyLabel(item.unrealized_pnl,currency)}</Text>
    </View>}/>;
}

function Portfolio(){
  const styles=useNativeStyles();
  const {data,loading,error,retry}=useAccountData<any>('/portfolio');
  if(!data)return <AccountDataState loading={loading} error={error} retry={retry}/>;
  const account=data.account||{},currency=account.currency;
  const exposures=Array.isArray(data.exposures)?data.exposures:[];
  return <FlatList
    data={exposures}
    keyExtractor={(item,i)=>String(item.asset)+':'+String(item.direction)+':'+i}
    ListHeaderComponent={<View>
      <View style={styles.disclosure}><Text style={styles.muted}>This is paper-account exposure. It is not consolidated real broker equity.</Text></View>
      <View style={styles.grid}><MetricTile title="Paper equity" value={currencyLabel(data.equity,currency)}/>
      <MetricTile title="Paper cash" value={currencyLabel(account.cash_balance,currency)}/></View>
    </View>}
    ListEmptyComponent={<Text style={styles.muted}>No paper exposure was returned.</Text>}
    renderItem={({item})=><View style={styles.row}>
      <View style={{flex:1,minWidth:0}}><Text style={styles.rowTitle}>{safeLabel(item.asset,'Instrument')} · {safeLabel(item.direction)}</Text>
        <Text style={styles.muted}>{safeLabel(item.asset_class)} · {quantityLabel(item.positions,0)} positions</Text>
      </View>
      <Text style={amountTone(item.unrealized_pnl)==='positive'?styles.gain:amountTone(item.unrealized_pnl)==='negative'?styles.loss:styles.muted}>{currencyLabel(item.unrealized_pnl,currency)}</Text>
    </View>}/>;
}

function Performance(){
  const styles=useNativeStyles();
  const {data,loading,error,retry}=useAccountData<any>('/performance');
  if(!data)return <AccountDataState loading={loading} error={error} retry={retry}/>;
  const stats=data.summary||{};
  return <ScrollView showsVerticalScrollIndicator={false}>
    <View style={styles.disclosure}><Text style={styles.muted}>{safeLabel(stats.disclaimer,'Historical performance cannot guarantee a future outcome.')} Claim certified: {stats.claim_certified===true?'Yes':'No'}.</Text></View>
    <View style={styles.grid}>
      <MetricTile title="Evaluated signals" value={quantityLabel(stats.signals,0)}/>
      <MetricTile title="Wins" value={quantityLabel(stats.wins,0)}/>
      <MetricTile title="Losses" value={quantityLabel(stats.losses,0)}/>
      <MetricTile title="Historical win ratio" value={percentLabel(stats.win_rate)}/>
      <MetricTile title="Average R" value={quantityLabel(stats.average_r,3)}/>
      <MetricTile title="Total R" value={quantityLabel(stats.total_r,3)}/>
    </View>
    <Text style={styles.body}>Backtests, simulations and historical ledgers must not be presented as guaranteed or forward performance.</Text>
  </ScrollView>;
}

function Journal(){
  const styles=useNativeStyles();const [entries,setEntries]=useState<any[]>([]);const [title,setTitle]=useState('');const [notes,setNotes]=useState('');const [error,setError]=useState('');const load=()=>api<any>('/journal?limit=100').then(data=>setEntries(data.entries||[])).catch(e=>setError(e instanceof Error?e.message:'Could not load journal'));useEffect(()=>{load()},[]);const save=async()=>{if(!notes.trim())return;setError('');try{await createJournalEntry({title:title||undefined,notes});setTitle('');setNotes('');load()}catch(e){setError(e instanceof Error?e.message:'Could not save journal')}};return <ScrollView><View style={styles.card}><Text style={styles.rowTitle}>Trading journal</Text><TextInput style={styles.input} placeholder="Title" placeholderTextColor="#869f91" value={title} onChangeText={setTitle}/><TextInput style={[styles.input,{minHeight:120}]} multiline placeholder="Plan, execution, emotion and lessons" placeholderTextColor="#869f91" value={notes} onChangeText={setNotes}/>{error?<Text style={styles.error}>{error}</Text>:null}<Pressable style={styles.primary} onPress={save}><Text style={styles.primaryText}>Save entry</Text></Pressable></View>{entries.map(entry=><View key={entry.journal_entry_id} style={styles.card}><Text style={styles.rowTitle}>{entry.title||'Journal entry'}</Text><Text style={styles.muted}>{new Date(entry.occurred_at).toLocaleString()}</Text><Text style={styles.body}>{entry.notes}</Text></View>)}</ScrollView>}
function Support(){
  const styles=useNativeStyles();const [rows,setRows]=useState<any[]>([]);const [subject,setSubject]=useState('');const [message,setMessage]=useState('');const load=()=>api<any>('/support/tickets').then(x=>setRows(x.tickets||[])).catch(()=>{});useEffect(()=>{load()},[]);const create=async()=>{if(!subject.trim()||!message.trim())return;await api('/support/tickets',{method:'POST',body:JSON.stringify({subject,category:'general',message})});setSubject('');setMessage('');load()};return <ScrollView><View style={styles.card}><Text style={styles.rowTitle}>Contact support</Text><TextInput style={styles.input} placeholder="Subject" placeholderTextColor="#869f91" value={subject} onChangeText={setSubject}/><TextInput style={[styles.input,{minHeight:100}]} multiline placeholder="How can we help?" placeholderTextColor="#869f91" value={message} onChangeText={setMessage}/><Pressable style={styles.primary} onPress={create}><Text style={styles.primaryText}>Create ticket</Text></Pressable></View>{rows.map(t=><View key={t.ticket_id} style={styles.row}><View><Text style={styles.rowTitle}>{t.subject}</Text><Text style={styles.muted}>{t.category} · {t.priority}</Text></View><Text style={styles.badge}>{t.status}</Text></View>)}</ScrollView>}
function Account({user,setUser,onRefresh,onLogout}:any){
  const styles=useNativeStyles();
  const [link,setLink]=useState<any>(null);
  const [name,setName]=useState(user.display_name||'');
  const [timezone,setTimezone]=useState(user.timezone||'');
  const [mfa,setMfa]=useState<any>(null);
  const [mfaSecret,setMfaSecret]=useState('');
  const [mfaCode,setMfaCode]=useState('');
  const [products,setProducts]=useState<any[]>([]);
  const [receipts,setReceipts]=useState<any[]>([]);
  const refreshMfa=()=>mfaStatus().then(setMfa).catch(()=>{});
  const refreshBilling=()=>Promise.all([getBillingProducts(),getBilling()]).then(([p,b])=>{setProducts(p.products||[]);setReceipts(b.receipts||[])}).catch(()=>{});
  useEffect(()=>{refreshMfa();refreshBilling()},[]);
  const [linkError,setLinkError]=useState('');
  const [linkLoading,setLinkLoading]=useState(false);
  const connect=async()=>{
    if(linkLoading)return;
    setLinkLoading(true);setLinkError('');
    try{setLink(await createTelegramLink());await onRefresh()}
    catch(e){
      if(e instanceof PlatformAPIError&&['telegram_already_linked','telegram_verified_merge_pending'].includes(e.code||'')){setLink(null);await onRefresh()}
      else setLinkError(e instanceof Error?e.message:'Could not create Telegram link');
    }finally{setLinkLoading(false)}
  };
  const save=async()=>{const result=await updateProfile({display_name:name,timezone});setUser(result.user)};
  const setup=async()=>{const result=await beginMfaSetup();setMfaSecret(result.secret)};
  const confirm=async()=>{const result=await enableMfa(mfaCode);Alert.alert('Recovery codes',result.recovery_codes.join('\n'));setMfaSecret('');setMfaCode('');refreshMfa()};
  const disable=async()=>{await disableMfa(mfaCode);setMfaCode('');refreshMfa()};
  const checkout=async(productId:string)=>{try{const result=await createBillingCheckout(productId);await Linking.openURL(result.authorization_url)}catch(e){Alert.alert('Checkout unavailable',e instanceof Error?e.message:'Could not start checkout')}};
  const telegramStatus=String(user.telegram_link_status||'not_linked').toLowerCase();
  const telegramConnected=Boolean(user.telegram_user_id)||telegramStatus==='linked'||telegramStatus==='merge_review';
  const telegramLabel=telegramStatus==='merge_review'?'Verified · reconciliation pending':telegramConnected?'Linked':telegramStatus==='link_pending'?'Link pending':'Not linked';
  return <ScrollView>
    <View style={styles.card}><Text style={styles.rowTitle}>{user.display_name||user.username||'SignalRank user'}</Text><Text style={styles.muted}>{user.primary_email||'Telegram account'}</Text><Text style={styles.muted}>Email verified: {user.email_verified_at?'Yes':'No'}</Text><Text style={styles.muted}>Telegram: {telegramLabel}</Text><TextInput style={styles.input} placeholder="Display name" placeholderTextColor="#869f91" value={name} onChangeText={setName}/><TextInput style={styles.input} placeholder="Timezone" placeholderTextColor="#869f91" value={timezone} onChangeText={setTimezone}/><Pressable style={styles.primary} onPress={save}><Text style={styles.primaryText}>Save profile</Text></Pressable></View>
    {!telegramConnected?<View style={styles.card}>
      <Text style={styles.rowTitle}>Connect Telegram</Text>
      <Text style={styles.muted}>{telegramStatus==='link_pending'?'A link code is already pending. Complete it in Telegram or create a replacement code.':'Link Telegram once to share identity and preferences across channels.'}</Text>
      {linkError?<Text accessibilityRole="alert" style={styles.error}>{linkError}</Text>:null}
      <Pressable accessibilityRole="button" accessibilityState={{disabled:linkLoading,busy:linkLoading}} disabled={linkLoading} style={styles.primary} onPress={connect}><Text style={styles.primaryText}>{linkLoading?'Creating link…':telegramStatus==='link_pending'?'Create replacement code':'Create one-time code'}</Text></Pressable>
      {link?<><Text selectable style={styles.metric}>{link.code}</Text><Text style={styles.muted}>Send /link {link.code} to the bot, then return here. Your connection status refreshes automatically.</Text>{link.telegram_deep_link?<Pressable style={styles.primary} onPress={()=>Linking.openURL(link.telegram_deep_link)}><Text style={styles.primaryText}>Open Telegram</Text></Pressable>:null}</>:null}
      <Pressable style={styles.danger} onPress={onRefresh}><Text style={styles.muted}>Refresh Telegram status</Text></Pressable>
    </View>:telegramStatus==='merge_review'?<View style={styles.card}><Text style={styles.rowTitle}>Telegram verified</Text><Text style={styles.muted}>Your Telegram identity is recognized. Older Telegram-side account history is being reconciled; do not reconnect or create another account.</Text><Pressable style={styles.primary} onPress={onRefresh}><Text style={styles.primaryText}>Refresh status</Text></Pressable></View>:null}
    <View style={styles.card}><Text style={styles.rowTitle}>Plans</Text><Text style={styles.muted}>Server-priced Paystack checkout. Verify your email first.</Text>{products.map(product=><View key={product.product_id} style={styles.row}><View><Text style={styles.rowTitle}>{product.display_name}</Text><Text style={styles.muted}>{currencyLabel(product.price_ngn,product.currency||"NGN")} · {product.duration_days} days</Text></View><Pressable style={styles.primary} onPress={()=>checkout(product.product_id)}><Text style={styles.primaryText}>Choose</Text></Pressable></View>)}</View>
    <View style={styles.card}><Text style={styles.rowTitle}>Receipts</Text>{receipts.length?receipts.slice(0,10).map(receipt=><View key={receipt.receipt_number} style={styles.row}><View><Text style={styles.rowTitle}>{receipt.plan}</Text><Text style={styles.muted}>{receipt.receipt_number}</Text></View><Text style={styles.body}>{currencyLabel(receipt.amount,receipt.currency)}</Text></View>):<Text style={styles.muted}>No receipts yet.</Text>}</View>
    <View style={styles.card}><Text style={styles.rowTitle}>Authenticator security</Text><Text style={styles.muted}>{mfa?.enabled?'Enabled':'Disabled'}</Text>{mfaSecret?<><Text selectable style={styles.body}>{mfaSecret}</Text><TextInput style={styles.input} placeholder="6-digit code" placeholderTextColor="#869f91" value={mfaCode} onChangeText={setMfaCode}/><Pressable style={styles.primary} onPress={confirm}><Text style={styles.primaryText}>Enable MFA</Text></Pressable></>:mfa?.enabled?<><TextInput style={styles.input} placeholder="Authenticator or recovery code" placeholderTextColor="#869f91" value={mfaCode} onChangeText={setMfaCode}/><Pressable style={styles.danger} onPress={disable}><Text style={styles.loss}>Disable MFA</Text></Pressable></>:<Pressable style={styles.primary} onPress={setup}><Text style={styles.primaryText}>Set up MFA</Text></Pressable>}</View>
    <Pressable style={styles.danger} onPress={onLogout}><Text style={styles.loss}>Log out</Text></Pressable>
  </ScrollView>
}

const darkStyles=StyleSheet.create({feedbackPanel:{backgroundColor:'#101e19',borderColor:'#294036',borderWidth:1,borderRadius:14,padding:20,alignItems:'flex-start',gap:12,marginBottom:14},disclosure:{padding:14,borderColor:'#294036',borderWidth:1,borderLeftColor:'#4ce0a4',borderLeftWidth:3,backgroundColor:'#14251d',borderRadius:10,marginBottom:15},sectionLabel:{color:'#bcf4d7',fontSize:11,fontWeight:'800',letterSpacing:1.3,marginBottom:10},heroTitle:{color:'#e6eeea',fontSize:26,fontWeight:'800',lineHeight:31,marginVertical:13},root:{flex:1,backgroundColor:'#08120f',paddingHorizontal:16,paddingTop:8,paddingBottom:10},center:{flex:1,backgroundColor:'#08120f',alignItems:'center',justifyContent:'center'},header:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',gap:10,paddingVertical:16,borderBottomWidth:1,borderBottomColor:'#294036'},eyebrow:{color:'#4ce0a4',fontSize:11,fontWeight:'800',letterSpacing:2},title:{color:'#e6eeea',fontSize:26,fontWeight:'800',flexShrink:1},hero:{color:'#e6eeea',fontSize:44,lineHeight:48,fontWeight:'900',marginVertical:16},muted:{color:'#a5b8ad',lineHeight:20},body:{color:'#e6eeea',lineHeight:22,marginTop:10},badge:{color:'#4ce0a4',borderColor:'#294036',borderWidth:1,paddingHorizontal:10,paddingVertical:5,borderRadius:20,fontSize:11,fontWeight:'800'},nav:{flexDirection:'row',gap:6,paddingVertical:14},navItem:{paddingHorizontal:14,paddingVertical:13,borderRadius:10,minHeight:44,justifyContent:'center'},navActive:{backgroundColor:'#14251d'},navText:{color:'#d9e5de',textTransform:'capitalize'},content:{flex:1,paddingTop:10},auth:{padding:24,justifyContent:'center',minHeight:'100%'},tabs:{flexDirection:'row',backgroundColor:'#101e19',padding:4,borderRadius:12,marginVertical:24},tab:{flex:1,padding:10,alignItems:'center'},tabActive:{backgroundColor:'#294036',borderRadius:9},input:{backgroundColor:'#101e19',borderColor:'#294036',borderWidth:1,borderRadius:12,color:'#e6eeea',padding:14,marginBottom:12},primary:{backgroundColor:'#4ce0a4',paddingHorizontal:18,paddingVertical:14,borderRadius:12,alignItems:'center',marginTop:8},primaryText:{color:'#071c12',fontWeight:'900'},link:{color:'#4ce0a4',padding:12},inline:{flexDirection:'row',justifyContent:'space-between',marginTop:10},error:{color:'#ff6b75',marginBottom:12},grid:{flexDirection:'row',flexWrap:'wrap',gap:10},card:{backgroundColor:'#101e19',borderColor:'#294036',borderWidth:1,borderRadius:14,padding:18,marginBottom:12,minWidth:'47%',flexGrow:1},metric:{color:'#e6eeea',fontSize:24,fontWeight:'800',marginTop:8},row:{backgroundColor:'#101e19',borderColor:'#294036',borderWidth:1,borderRadius:12,padding:16,marginBottom:10,flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:10,minWidth:0},rowTitle:{color:'#e6eeea',fontWeight:'800',fontSize:16},gain:{color:'#4ce0a4'},loss:{color:'#ff6b75'},danger:{borderColor:'#ff6b75',borderWidth:1,borderRadius:12,padding:15,alignItems:'center',marginTop:12},searchRow:{flexDirection:'row',gap:8,marginBottom:14}});

/** App-wide platform appearance: Expo userInterfaceStyle=automatic. A visual
 * preference must never modify session, market or execution authorities. */
const lightNativePalette: Record<string,string> = {
  '#08120f':'#f1f5f3', '#101e19':'#ffffff', '#14251d':'#eaf1ed',
  '#e6eeea':'#152a21', '#a5b8ad':'#52685c', '#294036':'#d1dfd6',
  '#4ce0a4':'#08754e', '#bcf4d7':'#085c3f', '#d9e5de':'#152a21',
  '#071c12':'#ffffff', '#ff6b75':'#be123c',
};
const lightStyles = Object.fromEntries(
  Object.entries(darkStyles).map(([key,style])=>[
    key,Object.fromEntries(Object.entries(style).map(([prop,value])=>[
      prop,typeof value==='string'?(lightNativePalette[value]||value):value
    ])),
  ])
) as typeof darkStyles;

function useNativeStyles(){return useColorScheme()==='light'?lightStyles:darkStyles;}
