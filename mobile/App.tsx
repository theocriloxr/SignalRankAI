import React, {useEffect, useState} from 'react';
import {ActivityIndicator, Alert, FlatList, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View} from 'react-native';
import * as Linking from 'expo-linking';
import {StatusBar} from 'expo-status-bar';
import {
  activateTelegram, api, beginMfaSetup, cancelAutoRenew, clearSession, completeMagicLogin,
  completeMfa, completePasswordReset, createBillingCheckout, createJournalEntry, createTelegramLink,
  disableMfa, enableMfa, getBilling, getBillingProducts, legalUrl, login, mfaStatus, register, registerPushDevice,
  requestMagicLink, requestPasswordReset, requestRefundReview, updateProfile,
} from './src/api';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

type Screen = 'overview'|'signals'|'markets'|'paper'|'portfolio'|'performance'|'journal'|'support'|'account';
type AuthMode = 'login'|'register'|'activate'|'mfa'|'reset';

export default function App() {
  const [loading,setLoading]=useState(true); const [user,setUser]=useState<any>(null);
  const [screen,setScreen]=useState<Screen>('overview'); const [authMode,setAuthMode]=useState<AuthMode>('login');
  const [form,setForm]=useState({displayName:'',email:'',password:'',code:'',mfaToken:'',resetToken:'',termsAccepted:false,privacyAcknowledged:false,marketingConsent:false}); const [error,setError]=useState('');
  const loadMe=async()=>{try{const result=await api<any>('/me');setUser(result.user)}catch{setUser(null)}finally{setLoading(false)}};
  useEffect(()=>{loadMe()},[]);
  useEffect(()=>{const handle=async({url}:{url:string})=>{const parsed=Linking.parse(url);const q:any=parsed.queryParams||{};try{if(q.magic_login){setLoading(true);const result=await completeMagicLogin(String(q.magic_login));if(result.mfa_required){setForm(v=>({...v,mfaToken:String(result.mfa_token||'')}));setAuthMode('mfa')}else setUser(result.user)}else if(q.password_reset){setForm(v=>({...v,resetToken:String(q.password_reset)}));setAuthMode('reset')}else if(q.token){setForm(v=>({...v,code:String(q.token)}));setAuthMode('activate')}}catch(e){setError(e instanceof Error?e.message:'Link failed')}finally{setLoading(false)}};Linking.getInitialURL().then(url=>{if(url)handle({url})});const sub=Linking.addEventListener('url',handle);return()=>sub.remove()},[]);
  useEffect(()=>{if(!user||!Device.isDevice||!['android','ios'].includes(Platform.OS))return;void(async()=>{try{const current=await Notifications.getPermissionsAsync();const permission=current.status==='granted'?current:await Notifications.requestPermissionsAsync();if(permission.status!=='granted')return;if(Platform.OS==='android')await Notifications.setNotificationChannelAsync('signals',{name:'Signal updates',importance:Notifications.AndroidImportance.HIGH});const projectId=process.env.EXPO_PUBLIC_EAS_PROJECT_ID||Constants.expoConfig?.extra?.eas?.projectId;if(!projectId)return;const token=await Notifications.getExpoPushTokenAsync({projectId});await registerPushDevice({pushToken:token.data,platform:Platform.OS as 'android'|'ios',deviceId:`${Device.osName||Platform.OS}:${Device.modelName||'device'}`,appVersion:Constants.expoConfig?.version})}catch{}})()},[user]);
  const authenticate=async()=>{
    setError('');
    if((authMode==='register'||authMode==='activate')&&(!form.termsAccepted||!form.privacyAcknowledged)){
      setError('Accept the Terms of Use and acknowledge the Privacy Notice to continue.');
      return;
    }
    setLoading(true);
    try{
      if(authMode==='reset'){
        await completePasswordReset(form.resetToken,form.password);
        setAuthMode('login');
        setError('Password reset. Sign in again.');
        return;
      }
      const result=authMode==='login'
        ?await login(form.email,form.password)
        :authMode==='register'
          ?await register(form.displayName,form.email,form.password,form.termsAccepted,form.privacyAcknowledged,form.marketingConsent)
          :authMode==='activate'
            ?await activateTelegram(form.code,form.email,form.password,form.termsAccepted,form.privacyAcknowledged,form.marketingConsent)
            :await completeMfa(form.mfaToken,form.code);
      if(result.mfa_required){
        setForm(v=>({...v,mfaToken:String(result.mfa_token||''),code:''}));
        setAuthMode('mfa');
      }else{
        setUser(result.user);
        setScreen('overview');
      }
    }catch(e){
      setError(e instanceof Error?e.message:'Authentication failed');
    }finally{
      setLoading(false);
    }
  };
  if(loading)return <SafeAreaView style={styles.center}><ActivityIndicator color="#64f0b4"/><StatusBar style="light"/></SafeAreaView>;
  if(!user)return <Auth mode={authMode} setMode={setAuthMode} form={form} setForm={setForm} error={error} submit={authenticate}/>;
  const screens:Screen[]=['overview','signals','markets','paper','portfolio','performance','journal','support','account'];
  return <SafeAreaView style={styles.root}><StatusBar style="light"/><View style={styles.header}><View><Text style={styles.eyebrow}>SIGNALRANKAI</Text><Text style={styles.title}>Welcome{user.display_name?`, ${String(user.display_name).split(' ')[0]}`:''}</Text></View><Text style={styles.badge}>{String(user.tier||'free').toUpperCase()}</Text></View><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.nav}>{screens.map(item=><Pressable key={item} onPress={()=>setScreen(item)} style={[styles.navItem,screen===item&&styles.navActive]}><Text style={styles.navText}>{item}</Text></Pressable>)}</ScrollView><View style={styles.content}>{screen==='overview'?<Overview/>:screen==='signals'?<Signals/>:screen==='markets'?<Markets/>:screen==='paper'?<Paper/>:screen==='portfolio'?<Portfolio/>:screen==='performance'?<Performance/>:screen==='journal'?<Journal/>:screen==='support'?<Support/>:<Account user={user} setUser={setUser} onRefresh={loadMe} onLogout={async()=>{await clearSession();setUser(null)}}/>}</View></SafeAreaView>;
}

function ToggleRow({checked,onPress,label}:any){
  return <Pressable onPress={onPress} style={styles.checkboxRow} accessibilityRole="checkbox" accessibilityState={{checked}}>
    <View style={[styles.checkboxBox,checked&&styles.checkboxOn]}><Text style={styles.checkboxMark}>{checked?'✓':''}</Text></View>
    <Text style={styles.checkboxLabel}>{label}</Text>
  </Pressable>;
}

function Auth({mode,setMode,form,setForm,error,submit}:any){
  const magic=async()=>{if(!form.email)return setForm({...form});try{await requestMagicLink(form.email);Alert.alert('Check your email','If the account exists, a sign-in link was queued.')}catch(e){Alert.alert('Error',e instanceof Error?e.message:'Could not request link')}};
  const reset=async()=>{if(!form.email)return;try{await requestPasswordReset(form.email);Alert.alert('Check your email','If the account exists, reset instructions were queued.')}catch(e){Alert.alert('Error',e instanceof Error?e.message:'Could not request reset')}};
  const legalBlocked=(mode==='register'||mode==='activate')&&(!form.termsAccepted||!form.privacyAcknowledged);
  return <SafeAreaView style={styles.root}><ScrollView contentContainerStyle={styles.auth}>
    <Text style={styles.eyebrow}>ONE ACCOUNT. EVERY CHANNEL.</Text>
    <Text style={styles.hero}>SignalRankAI follows you.</Text>
    <Text style={styles.muted}>Keep Telegram signals, subscriptions, paper positions and preferences when you move into the app.</Text>
    {!['mfa','reset'].includes(mode)&&<View style={styles.tabs}>{(['login','register','activate'] as AuthMode[]).map(x=><Pressable key={x} onPress={()=>setMode(x)} style={[styles.tab,mode===x&&styles.tabActive]}><Text style={styles.navText}>{x}</Text></Pressable>)}</View>}
    {mode==='register'&&<TextInput style={styles.input} placeholder="Display name" placeholderTextColor="#75869a" value={form.displayName} onChangeText={(v)=>setForm({...form,displayName:v})}/>}
    {mode==='activate'&&<TextInput style={styles.input} placeholder="Telegram one-time code" placeholderTextColor="#75869a" value={form.code} onChangeText={(v)=>setForm({...form,code:v})}/>}
    {mode==='mfa'&&<><Text style={styles.rowTitle}>Two-factor authentication</Text><TextInput style={styles.input} placeholder="Authenticator or recovery code" placeholderTextColor="#75869a" value={form.code} onChangeText={(v)=>setForm({...form,code:v})}/></>}
    {mode==='reset'&&<Text style={styles.rowTitle}>Choose a new password</Text>}
    {!['mfa'].includes(mode)&&<TextInput style={styles.input} placeholder="Email" placeholderTextColor="#75869a" autoCapitalize="none" keyboardType="email-address" value={form.email} onChangeText={(v)=>setForm({...form,email:v})}/>}
    {!['mfa'].includes(mode)&&<TextInput style={styles.input} placeholder={mode==='reset'?'New password':'Password'} placeholderTextColor="#75869a" secureTextEntry value={form.password} onChangeText={(v)=>setForm({...form,password:v})}/>}
    {(mode==='register'||mode==='activate')?<View style={styles.legalBox}>
      <ToggleRow checked={form.termsAccepted} onPress={()=>setForm({...form,termsAccepted:!form.termsAccepted})} label="I agree to the Terms of Use and acknowledge the trading risk disclosure. This does not enable broker execution."/>
      <ToggleRow checked={form.privacyAcknowledged} onPress={()=>setForm({...form,privacyAcknowledged:!form.privacyAcknowledged})} label="I have read the Privacy Notice."/>
      <ToggleRow checked={form.marketingConsent} onPress={()=>setForm({...form,marketingConsent:!form.marketingConsent})} label="Optional: send me product news and marketing updates."/>
      <View style={styles.inline}><Pressable onPress={()=>Linking.openURL(legalUrl('/terms'))}><Text style={styles.link}>Terms</Text></Pressable><Pressable onPress={()=>Linking.openURL(legalUrl('/privacy'))}><Text style={styles.link}>Privacy</Text></Pressable><Pressable onPress={()=>Linking.openURL(legalUrl('/risk-disclosure'))}><Text style={styles.link}>Risk</Text></Pressable></View>
    </View>:null}
    {error?<Text style={styles.error}>{error}</Text>:null}
    <Pressable style={[styles.primary,registerBlocked&&styles.disabled]} disabled={legalBlocked} onPress={submit}><Text style={styles.primaryText}>{mode==='login'?'Log in':mode==='register'?'Create account':mode==='activate'?'Activate Telegram account':mode==='mfa'?'Verify code':'Reset password'}</Text></Pressable>
    {mode==='login'&&<View style={styles.inline}><Pressable onPress={magic}><Text style={styles.link}>Email sign-in link</Text></Pressable><Pressable onPress={reset}><Text style={styles.link}>Reset password</Text></Pressable></View>}
  </ScrollView><StatusBar style="light"/></SafeAreaView>;
}
function Overview(){const [data,setData]=useState<any>(null);useEffect(()=>{api('/dashboard').then(setData).catch(()=>{})},[]);if(!data)return <ActivityIndicator color="#64f0b4"/>;const s=data.summary||{};return <ScrollView><View style={styles.grid}>{[['Delivered',s.delivered_signals],['Open paper',s.open_positions],['Paper cash',`$${Number(s.paper_cash||0).toFixed(2)}`],['Unrealized',`$${Number(s.unrealized_pnl||0).toFixed(2)}`]].map(([k,v])=><View style={styles.card} key={String(k)}><Text style={styles.muted}>{k}</Text><Text style={styles.metric}>{v}</Text></View>)}</View></ScrollView>}
function Signals(){const [rows,setRows]=useState<any[]>([]);useEffect(()=>{api<any>('/signals?limit=50').then(x=>setRows(x.signals||[])).catch(()=>{})},[]);return <FlatList data={rows} keyExtractor={x=>x.signal_id} ListEmptyComponent={<Text style={styles.muted}>No delivery-proven signals yet.</Text>} renderItem={({item})=><View style={styles.row}><View><Text style={styles.rowTitle}>{item.asset} {String(item.direction).toUpperCase()}</Text><Text style={styles.muted}>{item.timeframe} · {item.strategy_name}</Text></View><Text style={styles.badge}>{item.outcome_status||'PENDING'}</Text></View>}/>} 
function Markets(){const [q,setQ]=useState('');const [rows,setRows]=useState<any[]>([]);const search=()=>api<any>(`/instruments/search?q=${encodeURIComponent(q)}&limit=50`).then(x=>setRows(x.instruments||[])).catch(()=>{});useEffect(()=>{search()},[]);return <View style={{flex:1}}><View style={styles.searchRow}><TextInput style={[styles.input,{flex:1,marginBottom:0}]} placeholder="Search markets" placeholderTextColor="#75869a" value={q} onChangeText={setQ}/><Pressable style={styles.primary} onPress={search}><Text style={styles.primaryText}>Search</Text></Pressable></View><FlatList data={rows} keyExtractor={x=>x.instrument_id} renderItem={({item})=><View style={styles.row}><View><Text style={styles.rowTitle}>{item.display_symbol||item.canonical_symbol}</Text><Text style={styles.muted}>{item.asset_class} · {item.instrument_type}</Text></View><Text style={styles.muted}>{(item.providers||[]).join(', ')}</Text></View>}/></View>}
function Paper(){const [data,setData]=useState<any>(null);useEffect(()=>{api('/paper').then(setData).catch(()=>{})},[]);if(!data)return <ActivityIndicator color="#64f0b4"/>;return <FlatList data={data.positions||[]} keyExtractor={x=>x.position_id} ListHeaderComponent={<View style={styles.card}><Text style={styles.muted}>Paper cash</Text><Text style={styles.metric}>${Number(data.account?.cash_balance||0).toFixed(2)}</Text></View>} ListEmptyComponent={<Text style={styles.muted}>No paper positions.</Text>} renderItem={({item})=><View style={styles.row}><View><Text style={styles.rowTitle}>{item.asset} {String(item.direction).toUpperCase()}</Text><Text style={styles.muted}>{item.status} · entry {item.fill_entry}</Text></View><Text style={Number(item.unrealized_pnl)>=0?styles.gain:styles.loss}>${Number(item.unrealized_pnl||0).toFixed(2)}</Text></View>}/>} 
function Portfolio(){const [data,setData]=useState<any>(null);useEffect(()=>{api('/portfolio').then(setData).catch(()=>{})},[]);if(!data)return <ActivityIndicator color="#64f0b4"/>;return <FlatList data={data.exposures||[]} keyExtractor={(x,i)=>`${x.asset}:${x.direction}:${i}`} ListHeaderComponent={<View style={styles.grid}><View style={styles.card}><Text style={styles.muted}>Equity</Text><Text style={styles.metric}>${Number(data.equity||0).toFixed(2)}</Text></View><View style={styles.card}><Text style={styles.muted}>Cash</Text><Text style={styles.metric}>${Number(data.account?.cash_balance||0).toFixed(2)}</Text></View></View>} ListEmptyComponent={<Text style={styles.muted}>No open exposure.</Text>} renderItem={({item})=><View style={styles.row}><View><Text style={styles.rowTitle}>{item.asset} {String(item.direction).toUpperCase()}</Text><Text style={styles.muted}>{item.asset_class} · {item.positions} position(s)</Text></View><Text style={Number(item.unrealized_pnl)>=0?styles.gain:styles.loss}>${Number(item.unrealized_pnl||0).toFixed(2)}</Text></View>}/>} 
function Performance(){const [data,setData]=useState<any>(null);useEffect(()=>{api('/performance').then(setData).catch(()=>{})},[]);if(!data)return <ActivityIndicator color="#64f0b4"/>;const s=data.summary||{};return <ScrollView><View style={styles.grid}>{[['Signals',s.signals||0],['Wins',s.wins||0],['Losses',s.losses||0],['Win rate',s.win_rate==null?'N/A':`${(Number(s.win_rate)*100).toFixed(1)}%`],['Average R',Number(s.average_r||0).toFixed(2)],['Total R',Number(s.total_r||0).toFixed(2)]].map(([k,v])=><View style={styles.card} key={String(k)}><Text style={styles.muted}>{k}</Text><Text style={styles.metric}>{v}</Text></View>)}</View><Text style={styles.muted}>Proof-backed history is not a guarantee of future results.</Text></ScrollView>}
function Journal(){const [entries,setEntries]=useState<any[]>([]);const [title,setTitle]=useState('');const [notes,setNotes]=useState('');const [error,setError]=useState('');const load=()=>api<any>('/journal?limit=100').then(data=>setEntries(data.entries||[])).catch(e=>setError(e instanceof Error?e.message:'Could not load journal'));useEffect(()=>{load()},[]);const save=async()=>{if(!notes.trim())return;setError('');try{await createJournalEntry({title:title||undefined,notes});setTitle('');setNotes('');load()}catch(e){setError(e instanceof Error?e.message:'Could not save journal')}};return <ScrollView><View style={styles.card}><Text style={styles.rowTitle}>Trading journal</Text><TextInput style={styles.input} placeholder="Title" placeholderTextColor="#75869a" value={title} onChangeText={setTitle}/><TextInput style={[styles.input,{minHeight:120}]} multiline placeholder="Plan, execution, emotion and lessons" placeholderTextColor="#75869a" value={notes} onChangeText={setNotes}/>{error?<Text style={styles.error}>{error}</Text>:null}<Pressable style={styles.primary} onPress={save}><Text style={styles.primaryText}>Save entry</Text></Pressable></View>{entries.map(entry=><View key={entry.journal_entry_id} style={styles.card}><Text style={styles.rowTitle}>{entry.title||'Journal entry'}</Text><Text style={styles.muted}>{new Date(entry.occurred_at).toLocaleString()}</Text><Text style={styles.body}>{entry.notes}</Text></View>)}</ScrollView>}
function Support(){const [rows,setRows]=useState<any[]>([]);const [subject,setSubject]=useState('');const [message,setMessage]=useState('');const load=()=>api<any>('/support/tickets').then(x=>setRows(x.tickets||[])).catch(()=>{});useEffect(()=>{load()},[]);const create=async()=>{if(!subject.trim()||!message.trim())return;await api('/support/tickets',{method:'POST',body:JSON.stringify({subject,category:'general',message})});setSubject('');setMessage('');load()};return <ScrollView><View style={styles.card}><Text style={styles.rowTitle}>Contact support</Text><TextInput style={styles.input} placeholder="Subject" placeholderTextColor="#75869a" value={subject} onChangeText={setSubject}/><TextInput style={[styles.input,{minHeight:100}]} multiline placeholder="How can we help?" placeholderTextColor="#75869a" value={message} onChangeText={setMessage}/><Pressable style={styles.primary} onPress={create}><Text style={styles.primaryText}>Create ticket</Text></Pressable></View>{rows.map(t=><View key={t.ticket_id} style={styles.row}><View><Text style={styles.rowTitle}>{t.subject}</Text><Text style={styles.muted}>{t.category} · {t.priority}</Text></View><Text style={styles.badge}>{t.status}</Text></View>)}</ScrollView>}
function Account({user,setUser,onRefresh,onLogout}:any){
  const [link,setLink]=useState<any>(null);
  const [name,setName]=useState(user.display_name||'');
  const [timezone,setTimezone]=useState(user.timezone||'');
  const [marketingConsent,setMarketingConsent]=useState(Boolean(user.marketing_consent));
  const [mfa,setMfa]=useState<any>(null);
  const [mfaSecret,setMfaSecret]=useState('');
  const [mfaCode,setMfaCode]=useState('');
  const [products,setProducts]=useState<any[]>([]);
  const [receipts,setReceipts]=useState<any[]>([]);
  const [billing,setBilling]=useState<any>({subscriptions:[],receipts:[],auto_renew:false});
  const [refundReference,setRefundReference]=useState('');
  const [refundReason,setRefundReason]=useState('');
  const refreshMfa=()=>mfaStatus().then(setMfa).catch(()=>{});
  const refreshBilling=()=>Promise.all([getBillingProducts(),getBilling()]).then(([p,b])=>{setProducts(p.products||[]);setReceipts(b.receipts||[]);setBilling(b)}).catch(()=>{});
  useEffect(()=>{refreshMfa();refreshBilling()},[]);
  const connect=async()=>setLink(await createTelegramLink());
  const save=async()=>{const result=await updateProfile({display_name:name,timezone,marketing_consent:marketingConsent});setUser(result.user);Alert.alert('Saved','Profile and marketing preference updated.')};
  const setup=async()=>{const result=await beginMfaSetup();setMfaSecret(result.secret)};
  const confirm=async()=>{const result=await enableMfa(mfaCode);Alert.alert('Recovery codes',result.recovery_codes.join('\n'));setMfaSecret('');setMfaCode('');refreshMfa()};
  const disable=async()=>{await disableMfa(mfaCode);setMfaCode('');refreshMfa()};
  const checkout=async(product:any)=>{
    const open=async()=>{
      try{
        const result=await createBillingCheckout(product.product_id,Boolean(product.recurring));
        await Linking.openURL(result.authorization_url);
      }catch(e){
        Alert.alert('Checkout unavailable',e instanceof Error?e.message:'Could not start checkout');
      }
    };
    if(product.recurring){
      Alert.alert(
        'Recurring subscription',
        'This plan renews automatically until you cancel auto-renew from Account. Cancelling renewal does not remove the already-paid period or automatically issue a refund.',
        [{text:'Cancel',style:'cancel'},{text:'Continue to Paystack',onPress:open}],
      );
      return;
    }
    await open();
  };
  const activeSub=(billing.subscriptions||[]).find((s:any)=>['active','grace_period'].includes(String(s.status||'').toLowerCase()));
  const cancelRenewal=()=>Alert.alert('Cancel auto-renew?','Your current paid access remains until its expiry. This does not automatically issue a refund.',[
    {text:'Keep renewal',style:'cancel'},
    {text:'Cancel auto-renew',style:'destructive',onPress:async()=>{try{const result=await cancelAutoRenew();await refreshBilling();Alert.alert('Auto-renew cancelled',result.policy||'Future renewal has been disabled.')}catch(e){Alert.alert('Cancellation issue',e instanceof Error?e.message:'Could not cancel auto-renew')}}},
  ]);
  const requestRefund=async()=>{if(!refundReference.trim()||refundReason.trim().length<3)return Alert.alert('More information needed','Enter the payment reference and reason for review.');try{const result=await requestRefundReview(refundReference.trim(),refundReason.trim());setRefundReference('');setRefundReason('');Alert.alert('Refund review submitted',result.message||'A billing support review was created.')}catch(e){Alert.alert('Refund review issue',e instanceof Error?e.message:'Could not submit refund review')}};
  const telegramStatus=String(user.telegram_link_status||'not_linked').toLowerCase();
  const telegramConnected=Boolean(user.telegram_user_id)||telegramStatus==='merge_review';
  const telegramLabel=user.telegram_user_id?'Linked':telegramStatus==='merge_review'?'Verified · reconciliation pending':telegramStatus==='link_pending'?'Link pending':'Not linked';
  return <ScrollView>
    <View style={styles.card}><Text style={styles.rowTitle}>{user.display_name||user.username||'SignalRank user'}</Text><Text style={styles.muted}>{user.primary_email||'Telegram account'}</Text><Text style={styles.muted}>Email verified: {user.email_verified_at?'Yes':'No'}</Text><Text style={styles.muted}>Telegram: {telegramLabel}</Text><TextInput style={styles.input} placeholder="Display name" placeholderTextColor="#75869a" value={name} onChangeText={setName}/><TextInput style={styles.input} placeholder="Timezone" placeholderTextColor="#75869a" value={timezone} onChangeText={setTimezone}/><ToggleRow checked={marketingConsent} onPress={()=>setMarketingConsent(v=>!v)} label="Optional marketing emails. Service, security and billing messages are separate."/><Pressable style={styles.primary} onPress={save}><Text style={styles.primaryText}>Save profile</Text></Pressable></View>
    {!telegramConnected?<View style={styles.card}><Text style={styles.rowTitle}>Connect Telegram</Text><Text style={styles.muted}>{telegramStatus==='link_pending'?'A link code is already pending. Complete it in Telegram or create a replacement code.':'Link Telegram once to share identity and preferences across channels.'}</Text><Pressable style={styles.primary} onPress={connect}><Text style={styles.primaryText}>{telegramStatus==='link_pending'?'Create replacement code':'Create one-time code'}</Text></Pressable>{link?<><Text style={styles.metric}>{link.code}</Text><Text style={styles.muted}>Send /link {link.code} to the bot.</Text>{link.telegram_deep_link?<Pressable style={styles.primary} onPress={()=>Linking.openURL(link.telegram_deep_link)}><Text style={styles.primaryText}>Open Telegram</Text></Pressable>:null}</>:null}<Pressable style={styles.danger} onPress={onRefresh}><Text style={styles.muted}>Refresh Telegram status</Text></Pressable></View>:telegramStatus==='merge_review'?<View style={styles.card}><Text style={styles.rowTitle}>Telegram verified</Text><Text style={styles.muted}>Your Telegram identity is recognized. Older Telegram-side account history is being reconciled; do not reconnect or create another account.</Text><Pressable style={styles.primary} onPress={onRefresh}><Text style={styles.primaryText}>Refresh status</Text></Pressable></View>:null}
    <View style={styles.card}><Text style={styles.rowTitle}>Plans & renewal</Text><Text style={styles.muted}>Server-priced Paystack checkout. Paid plans change access and limits; they do not guarantee trading results.</Text>{products.map(product=><View key={product.product_id} style={styles.row}><View style={{flex:1}}><Text style={styles.rowTitle}>{product.display_name}</Text><Text style={styles.muted}>{product.currency} {Number(product.price_ngn||0).toLocaleString()} · {product.duration_days} days</Text><Text style={product.recurring?styles.warning:styles.muted}>{product.recurring?'Renews automatically until cancelled':'One-off paid period · no automatic renewal'}</Text></View><Pressable style={styles.primary} onPress={()=>checkout(product)}><Text style={styles.primaryText}>Choose</Text></Pressable></View>)}{activeSub?<Text style={styles.muted}>Current paid access: {String(activeSub.tier||'').toUpperCase()} until {activeSub.expires_at?new Date(activeSub.expires_at).toLocaleString():'expiry shown by provider'} · Auto-renew {billing.auto_renew?'ON':'OFF'}.</Text>:<Text style={styles.muted}>No active paid subscription.</Text>}{activeSub&&billing.auto_renew?<Pressable style={styles.danger} onPress={cancelRenewal}><Text style={styles.loss}>Cancel auto-renew</Text></Pressable>:null}<Pressable onPress={()=>Linking.openURL(legalUrl('/billing-policy'))}><Text style={styles.link}>Read billing, cancellation & refund policy</Text></Pressable></View>
    <View style={styles.card}><Text style={styles.rowTitle}>Receipts & refund review</Text>{receipts.length?receipts.slice(0,10).map(receipt=><View key={receipt.receipt_number} style={styles.row}><View><Text style={styles.rowTitle}>{receipt.plan}</Text><Text style={styles.muted}>{receipt.receipt_number}</Text></View><Text style={styles.body}>{receipt.currency} {Number(receipt.amount||0).toLocaleString()}</Text></View>):<Text style={styles.muted}>No receipts yet.</Text>}<TextInput style={styles.input} placeholder="Payment reference" placeholderTextColor="#75869a" value={refundReference} onChangeText={setRefundReference}/><TextInput style={[styles.input,{minHeight:90}]} multiline placeholder="Reason for refund review" placeholderTextColor="#75869a" value={refundReason} onChangeText={setRefundReason}/><Text style={styles.muted}>A request opens a manual billing review; it does not automatically issue a refund.</Text><Pressable style={styles.danger} onPress={requestRefund}><Text style={styles.loss}>Request refund review</Text></Pressable></View>
    <View style={styles.card}><Text style={styles.rowTitle}>Legal & risk</Text><Text style={styles.muted}>General account terms and execution-risk acceptance are separate. Broker execution still requires its own explicit consent and safety gates.</Text><View style={styles.inline}><Pressable onPress={()=>Linking.openURL(legalUrl('/terms'))}><Text style={styles.link}>Terms</Text></Pressable><Pressable onPress={()=>Linking.openURL(legalUrl('/privacy'))}><Text style={styles.link}>Privacy</Text></Pressable><Pressable onPress={()=>Linking.openURL(legalUrl('/risk-disclosure'))}><Text style={styles.link}>Risk</Text></Pressable></View><View style={styles.inline}><Pressable onPress={()=>Linking.openURL(legalUrl('/cookies'))}><Text style={styles.link}>Cookies</Text></Pressable><Pressable onPress={()=>Linking.openURL(legalUrl('/accessibility'))}><Text style={styles.link}>Accessibility</Text></Pressable></View></View>
    <View style={styles.card}><Text style={styles.rowTitle}>Authenticator security</Text><Text style={styles.muted}>{mfa?.enabled?'Enabled':'Disabled'}</Text>{mfaSecret?<><Text selectable style={styles.body}>{mfaSecret}</Text><TextInput style={styles.input} placeholder="6-digit code" placeholderTextColor="#75869a" value={mfaCode} onChangeText={setMfaCode}/><Pressable style={styles.primary} onPress={confirm}><Text style={styles.primaryText}>Enable MFA</Text></Pressable></>:mfa?.enabled?<><TextInput style={styles.input} placeholder="Authenticator or recovery code" placeholderTextColor="#75869a" value={mfaCode} onChangeText={setMfaCode}/><Pressable style={styles.danger} onPress={disable}><Text style={styles.loss}>Disable MFA</Text></Pressable></>:<Pressable style={styles.primary} onPress={setup}><Text style={styles.primaryText}>Set up MFA</Text></Pressable>}</View>
    <Pressable style={styles.danger} onPress={onLogout}><Text style={styles.loss}>Log out</Text></Pressable>
  </ScrollView>
}
const styles=StyleSheet.create({root:{flex:1,backgroundColor:'#080b10',padding:16},center:{flex:1,backgroundColor:'#080b10',alignItems:'center',justifyContent:'center'},header:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',paddingVertical:12},eyebrow:{color:'#64f0b4',fontSize:11,fontWeight:'800',letterSpacing:2},title:{color:'#edf3fb',fontSize:28,fontWeight:'800'},hero:{color:'#edf3fb',fontSize:44,lineHeight:48,fontWeight:'900',marginVertical:16},muted:{color:'#8fa0b5',lineHeight:20},body:{color:'#edf3fb',lineHeight:22,marginTop:10},badge:{color:'#64f0b4',borderColor:'#2c7b60',borderWidth:1,paddingHorizontal:10,paddingVertical:5,borderRadius:20,fontSize:11,fontWeight:'800'},nav:{flexDirection:'row',gap:5,marginVertical:12},navItem:{paddingHorizontal:10,paddingVertical:8,borderRadius:9},navActive:{backgroundColor:'#151d28'},navText:{color:'#c7d4e3',textTransform:'capitalize'},content:{flex:1,paddingTop:10},auth:{padding:24,justifyContent:'center',minHeight:'100%'},tabs:{flexDirection:'row',backgroundColor:'#10161f',padding:4,borderRadius:12,marginVertical:24},tab:{flex:1,padding:10,alignItems:'center'},tabActive:{backgroundColor:'#263242',borderRadius:9},input:{backgroundColor:'#10161f',borderColor:'#263242',borderWidth:1,borderRadius:12,color:'#edf3fb',padding:14,marginBottom:12},primary:{backgroundColor:'#64f0b4',paddingHorizontal:18,paddingVertical:14,borderRadius:12,alignItems:'center',marginTop:8},primaryText:{color:'#04120d',fontWeight:'900'},link:{color:'#64f0b4',padding:12},inline:{flexDirection:'row',justifyContent:'space-between',marginTop:10},error:{color:'#ff6b75',marginBottom:12},grid:{flexDirection:'row',flexWrap:'wrap',gap:10},card:{backgroundColor:'#10161f',borderColor:'#263242',borderWidth:1,borderRadius:16,padding:18,marginBottom:12,minWidth:'47%'},metric:{color:'#edf3fb',fontSize:24,fontWeight:'800',marginTop:8},row:{backgroundColor:'#10161f',borderColor:'#263242',borderWidth:1,borderRadius:14,padding:15,marginBottom:9,flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:10},rowTitle:{color:'#edf3fb',fontWeight:'800',fontSize:16},gain:{color:'#64f0b4'},loss:{color:'#ff6b75'},danger:{borderColor:'#ff6b75',borderWidth:1,borderRadius:12,padding:15,alignItems:'center',marginTop:12},searchRow:{flexDirection:'row',gap:8,marginBottom:14},checkboxRow:{flexDirection:'row',gap:10,alignItems:'flex-start',paddingVertical:8},checkboxBox:{width:22,height:22,borderRadius:6,borderWidth:1,borderColor:'#536477',alignItems:'center',justifyContent:'center',marginTop:1},checkboxOn:{backgroundColor:'#64f0b4',borderColor:'#64f0b4'},checkboxMark:{color:'#04120d',fontWeight:'900'},checkboxLabel:{color:'#b8c5d4',lineHeight:20,flex:1},legalBox:{backgroundColor:'#0d141c',borderColor:'#263242',borderWidth:1,borderRadius:14,padding:12,marginBottom:12},disabled:{opacity:.45},warning:{color:'#ffcf70',lineHeight:20}});
