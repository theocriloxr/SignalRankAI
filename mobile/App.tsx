import React, {useEffect, useState} from 'react';
import {ActivityIndicator, FlatList, Linking, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View} from 'react-native';
import {StatusBar} from 'expo-status-bar';
import {activateTelegram, api, clearSession, createJournalEntry, createTelegramLink, login, register, registerPushDevice} from './src/api';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

type Screen = 'overview' | 'signals' | 'markets' | 'paper' | 'journal' | 'account';
type AuthMode = 'login' | 'register' | 'activate';

export default function App() {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<any>(null);
  const [screen, setScreen] = useState<Screen>('overview');
  const [authMode, setAuthMode] = useState<AuthMode>('login');
  const [form, setForm] = useState({displayName:'', email:'', password:'', code:''});
  const [error, setError] = useState('');

  const loadMe = async () => {
    try { const result = await api<any>('/me'); setUser(result.user); }
    catch { setUser(null); }
    finally { setLoading(false); }
  };
  useEffect(() => { loadMe(); }, []);
  useEffect(() => {
    if (!user || !Device.isDevice || !['android', 'ios'].includes(Platform.OS)) return;
    const registerForPush = async () => {
      try {
        const existing = await Notifications.getPermissionsAsync();
        const permission = existing.status === 'granted' ? existing : await Notifications.requestPermissionsAsync();
        if (permission.status !== 'granted') return;
        if (Platform.OS === 'android') {
          await Notifications.setNotificationChannelAsync('signals', {
            name: 'Signal updates',
            importance: Notifications.AndroidImportance.HIGH,
          });
        }
        const projectId = process.env.EXPO_PUBLIC_EAS_PROJECT_ID || Constants.expoConfig?.extra?.eas?.projectId;
        if (!projectId) return;
        const token = await Notifications.getExpoPushTokenAsync({projectId});
        await registerPushDevice({
          pushToken: token.data,
          platform: Platform.OS as 'android' | 'ios',
          deviceId: `${Device.osName || Platform.OS}:${Device.modelName || 'device'}`,
          appVersion: Constants.expoConfig?.version,
        });
      } catch {
        // Push is optional; authentication and signal access must remain usable.
      }
    };
    registerForPush();
  }, [user]);

  const authenticate = async () => {
    setError(''); setLoading(true);
    try {
      const result = authMode === 'login'
        ? await login(form.email, form.password)
        : authMode === 'register'
          ? await register(form.displayName, form.email, form.password)
          : await activateTelegram(form.code, form.email, form.password);
      setUser(result.user); setScreen('overview');
    } catch (e) { setError(e instanceof Error ? e.message : 'Authentication failed'); }
    finally { setLoading(false); }
  };

  if (loading) return <SafeAreaView style={styles.center}><ActivityIndicator color="#64f0b4"/><StatusBar style="light"/></SafeAreaView>;
  if (!user) return <Auth mode={authMode} setMode={setAuthMode} form={form} setForm={setForm} error={error} submit={authenticate}/>;

  return <SafeAreaView style={styles.root}>
    <StatusBar style="light"/>
    <View style={styles.header}><View><Text style={styles.eyebrow}>SIGNALRANKAI</Text><Text style={styles.title}>Welcome{user.display_name ? `, ${String(user.display_name).split(' ')[0]}` : ''}</Text></View><Text style={styles.badge}>{String(user.tier || 'free').toUpperCase()}</Text></View>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.nav}>{(['overview','signals','markets','paper','journal','account'] as Screen[]).map(item=><Pressable key={item} onPress={()=>setScreen(item)} style={[styles.navItem, screen===item && styles.navActive]}><Text style={styles.navText}>{item}</Text></Pressable>)}</ScrollView>
    <View style={styles.content}>{screen === 'overview' ? <Overview/> : screen === 'signals' ? <Signals/> : screen === 'markets' ? <Markets/> : screen === 'paper' ? <Paper/> : screen === 'journal' ? <Journal/> : <Account user={user} onLogout={async()=>{await clearSession();setUser(null)}}/>}</View>
  </SafeAreaView>;
}

function Auth({mode,setMode,form,setForm,error,submit}:any){return <SafeAreaView style={styles.root}><ScrollView contentContainerStyle={styles.auth}><Text style={styles.eyebrow}>ONE ACCOUNT. EVERY CHANNEL.</Text><Text style={styles.hero}>SignalRankAI follows you.</Text><Text style={styles.muted}>Keep your Telegram signals, subscription, paper portfolio and preferences when you move into the app.</Text><View style={styles.tabs}>{(['login','register','activate'] as AuthMode[]).map(x=><Pressable key={x} onPress={()=>setMode(x)} style={[styles.tab,mode===x&&styles.tabActive]}><Text style={styles.navText}>{x}</Text></Pressable>)}</View>{mode==='register'&&<TextInput style={styles.input} placeholder="Display name" placeholderTextColor="#75869a" value={form.displayName} onChangeText={(v)=>setForm({...form,displayName:v})}/>} {mode==='activate'&&<TextInput style={styles.input} placeholder="Telegram one-time code" placeholderTextColor="#75869a" value={form.code} onChangeText={(v)=>setForm({...form,code:v})}/>}<TextInput style={styles.input} placeholder="Email" placeholderTextColor="#75869a" autoCapitalize="none" keyboardType="email-address" value={form.email} onChangeText={(v)=>setForm({...form,email:v})}/><TextInput style={styles.input} placeholder="Password" placeholderTextColor="#75869a" secureTextEntry value={form.password} onChangeText={(v)=>setForm({...form,password:v})}/>{error?<Text style={styles.error}>{error}</Text>:null}<Pressable style={styles.primary} onPress={submit}><Text style={styles.primaryText}>{mode==='login'?'Log in':mode==='register'?'Create account':'Activate Telegram account'}</Text></Pressable></ScrollView><StatusBar style="light"/></SafeAreaView>}

function Overview(){const [data,setData]=useState<any>(null);useEffect(()=>{api('/dashboard').then(setData).catch(()=>{})},[]);if(!data)return <ActivityIndicator color="#64f0b4"/>;const s=data.summary||{};return <ScrollView><View style={styles.grid}>{[['Delivered',s.delivered_signals],['Open paper',s.open_positions],['Paper cash',`$${Number(s.paper_cash||0).toFixed(2)}`],['Unrealized',`$${Number(s.unrealized_pnl||0).toFixed(2)}`]].map(([k,v])=><View style={styles.card} key={String(k)}><Text style={styles.muted}>{k}</Text><Text style={styles.metric}>{v}</Text></View>)}</View></ScrollView>}
function Signals(){const [rows,setRows]=useState<any[]>([]);useEffect(()=>{api<any>('/signals?limit=50').then(x=>setRows(x.signals||[])).catch(()=>{})},[]);return <FlatList data={rows} keyExtractor={x=>x.signal_id} ListEmptyComponent={<Text style={styles.muted}>No delivery-proven signals yet.</Text>} renderItem={({item})=><View style={styles.row}><View><Text style={styles.rowTitle}>{item.asset} {String(item.direction).toUpperCase()}</Text><Text style={styles.muted}>{item.timeframe} · {item.strategy_name}</Text></View><Text style={styles.badge}>{item.outcome_status||'PENDING'}</Text></View>}/>}
function Markets(){const [q,setQ]=useState('');const [rows,setRows]=useState<any[]>([]);const search=()=>api<any>(`/instruments/search?q=${encodeURIComponent(q)}&limit=50`).then(x=>setRows(x.instruments||[])).catch(()=>{});useEffect(search,[]);return <View style={{flex:1}}><View style={styles.searchRow}><TextInput style={[styles.input,{flex:1,marginBottom:0}]} placeholder="Search markets" placeholderTextColor="#75869a" value={q} onChangeText={setQ}/><Pressable style={styles.primary} onPress={search}><Text style={styles.primaryText}>Search</Text></Pressable></View><FlatList data={rows} keyExtractor={x=>x.instrument_id} renderItem={({item})=><View style={styles.row}><View><Text style={styles.rowTitle}>{item.display_symbol||item.canonical_symbol}</Text><Text style={styles.muted}>{item.asset_class} · {item.instrument_type}</Text></View><Text style={styles.muted}>{(item.providers||[]).join(', ')}</Text></View>}/></View>}
function Paper(){const [data,setData]=useState<any>(null);useEffect(()=>{api('/paper').then(setData).catch(()=>{})},[]);if(!data)return <ActivityIndicator color="#64f0b4"/>;return <FlatList data={data.positions||[]} keyExtractor={x=>x.position_id} ListHeaderComponent={<View style={styles.card}><Text style={styles.muted}>Paper cash</Text><Text style={styles.metric}>${Number(data.account?.cash_balance||0).toFixed(2)}</Text></View>} ListEmptyComponent={<Text style={styles.muted}>No paper positions.</Text>} renderItem={({item})=><View style={styles.row}><View><Text style={styles.rowTitle}>{item.asset} {String(item.direction).toUpperCase()}</Text><Text style={styles.muted}>{item.status} · entry {item.fill_entry}</Text></View><Text style={Number(item.unrealized_pnl)>=0?styles.gain:styles.loss}>${Number(item.unrealized_pnl||0).toFixed(2)}</Text></View>}/>}
function Journal(){const [entries,setEntries]=useState<any[]>([]);const [title,setTitle]=useState('');const [notes,setNotes]=useState('');const [error,setError]=useState('');const load=()=>api<any>('/journal?limit=100').then(data=>setEntries(data.entries||[])).catch(e=>setError(e instanceof Error?e.message:'Could not load journal'));useEffect(load,[]);const save=async()=>{if(!notes.trim())return;setError('');try{await createJournalEntry({title:title||undefined,notes});setTitle('');setNotes('');load()}catch(e){setError(e instanceof Error?e.message:'Could not save journal')}};return <ScrollView><View style={styles.card}><Text style={styles.rowTitle}>Trading journal</Text><TextInput style={styles.input} placeholder="Title" placeholderTextColor="#75869a" value={title} onChangeText={setTitle}/><TextInput style={[styles.input,{minHeight:120}]} multiline placeholder="Plan, execution, emotion and lessons" placeholderTextColor="#75869a" value={notes} onChangeText={setNotes}/>{error?<Text style={styles.error}>{error}</Text>:null}<Pressable style={styles.primary} onPress={save}><Text style={styles.primaryText}>Save entry</Text></Pressable></View>{entries.map(entry=><View key={entry.journal_entry_id} style={styles.card}><Text style={styles.rowTitle}>{entry.title||'Journal entry'}</Text><Text style={styles.muted}>{new Date(entry.occurred_at).toLocaleString()}</Text><Text style={styles.body}>{entry.notes}</Text></View>)}</ScrollView>}

function Account({user,onLogout}:any){const [link,setLink]=useState<any>(null);const [linkError,setLinkError]=useState('');const connect=async()=>{setLinkError('');try{setLink(await createTelegramLink())}catch(e){setLinkError(e instanceof Error?e.message:'Could not create Telegram link')}};return <ScrollView><View style={styles.card}><Text style={styles.rowTitle}>{user.display_name||user.username||'SignalRank user'}</Text><Text style={styles.muted}>{user.primary_email||'Telegram account'}</Text><Text style={styles.muted}>Public ID: {user.public_user_id}</Text><Text style={styles.muted}>Telegram: {user.telegram_user_id?'Linked':'Not linked'}</Text></View>{!user.telegram_user_id?<View style={styles.card}><Text style={styles.rowTitle}>Connect Telegram</Text><Text style={styles.muted}>Keep bot signals, app history, subscriptions and paper data on one canonical account.</Text><Pressable style={styles.primary} onPress={connect}><Text style={styles.primaryText}>Create one-time code</Text></Pressable>{link?<><Text style={styles.metric}>{link.code}</Text><Text style={styles.muted}>Send /link {link.code} to the SignalRankAI bot before {new Date(link.expires_at).toLocaleTimeString()}.</Text>{link.telegram_deep_link?<Pressable style={styles.primary} onPress={()=>Linking.openURL(link.telegram_deep_link)}><Text style={styles.primaryText}>Open Telegram</Text></Pressable>:null}</>:null}{linkError?<Text style={styles.error}>{linkError}</Text>:null}</View>:null}<Pressable style={styles.danger} onPress={onLogout}><Text style={styles.loss}>Log out</Text></Pressable></ScrollView>}

const styles=StyleSheet.create({root:{flex:1,backgroundColor:'#080b10',padding:16},center:{flex:1,backgroundColor:'#080b10',alignItems:'center',justifyContent:'center'},header:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',paddingVertical:12},eyebrow:{color:'#64f0b4',fontSize:11,fontWeight:'800',letterSpacing:2},title:{color:'#edf3fb',fontSize:28,fontWeight:'800'},hero:{color:'#edf3fb',fontSize:48,lineHeight:52,fontWeight:'900',marginVertical:16},muted:{color:'#8fa0b5',lineHeight:20},badge:{color:'#64f0b4',borderColor:'#2c7b60',borderWidth:1,paddingHorizontal:10,paddingVertical:5,borderRadius:20,fontSize:11,fontWeight:'800'},nav:{flexDirection:'row',gap:5,marginVertical:12},navItem:{paddingHorizontal:10,paddingVertical:8,borderRadius:9},navActive:{backgroundColor:'#151d28'},navText:{color:'#c7d4e3',textTransform:'capitalize'},content:{flex:1,paddingTop:10},auth:{padding:24,justifyContent:'center',minHeight:'100%'},tabs:{flexDirection:'row',backgroundColor:'#10161f',padding:4,borderRadius:12,marginVertical:24},tab:{flex:1,padding:10,alignItems:'center'},tabActive:{backgroundColor:'#263242',borderRadius:9},input:{backgroundColor:'#10161f',borderColor:'#263242',borderWidth:1,borderRadius:12,color:'#edf3fb',padding:14,marginBottom:12},primary:{backgroundColor:'#64f0b4',paddingHorizontal:18,paddingVertical:14,borderRadius:12,alignItems:'center'},primaryText:{color:'#04120d',fontWeight:'900'},error:{color:'#ff6b75',marginBottom:12},grid:{flexDirection:'row',flexWrap:'wrap',gap:10},card:{backgroundColor:'#10161f',borderColor:'#263242',borderWidth:1,borderRadius:16,padding:18,marginBottom:12,minWidth:'47%'},metric:{color:'#edf3fb',fontSize:24,fontWeight:'800',marginTop:8},row:{backgroundColor:'#10161f',borderColor:'#263242',borderWidth:1,borderRadius:14,padding:15,marginBottom:9,flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:10},rowTitle:{color:'#edf3fb',fontWeight:'800',fontSize:16},gain:{color:'#64f0b4'},loss:{color:'#ff6b75'},danger:{borderColor:'#ff6b75',borderWidth:1,borderRadius:12,padding:15,alignItems:'center',marginTop:12},searchRow:{flexDirection:'row',gap:8,marginBottom:14}});
