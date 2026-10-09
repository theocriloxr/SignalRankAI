import React, {useEffect,useState} from 'react';
import {ActivityIndicator,FlatList,Pressable,ScrollView,StyleSheet,Text,TextInput,View} from 'react-native';
import {api} from './api';
import {safeLabel,quantityLabel} from './presentation';

function useResource(path:string) {
  const [revision,setRevision]=useState(0);
  const [state,setState]=useState<{loading:boolean;error:string;data:any}>({loading:true,error:'',data:null});
  useEffect(()=>{
    let active=true;
    setState({loading:true,error:'',data:null});
    api<any>(path).then(data=>{if(active)setState({loading:false,error:'',data})})
      .catch(error=>{if(active)setState({loading:false,error:error instanceof Error?error.message:'The account service is unavailable.',data:null})});
    return()=>{active=false};
  },[path,revision]);
  return {...state,retry:()=>setRevision(x=>x+1)};
}

function ResponseState({loading,error,retry}:{loading:boolean;error:string;retry:()=>void}){
  if(loading)return <View style={styles.panel}><ActivityIndicator color="#4ce0a4"/><Text style={styles.muted}>Retrieving account records…</Text></View>;
  return <View style={styles.panel} accessibilityRole="alert">
    <Text style={styles.title}>Records unavailable</Text><Text style={styles.muted}>{error||'No confirmed response was returned.'}</Text>
    <Pressable accessibilityRole="button" style={styles.action} onPress={retry}><Text style={styles.actionText}>Retry</Text></Pressable>
  </View>;
}
function Disclosure({text}:{text:string}){return <View style={styles.disclosure}><Text style={styles.muted}>{text}</Text></View>;}

export function NativeBrokers(){
  const state=useResource('/broker/connections');
  if(!state.data)return <ResponseState {...state}/>;
  const connections=Array.isArray(state.data.connections)?state.data.connections:[];
  return <FlatList data={connections} keyExtractor={(x,i)=>String(x.id||i)}
    ListHeaderComponent={<Disclosure text="Connection status is not permission to place live or demo orders. Every account and venue must pass separate execution certification."/>}
    ListEmptyComponent={<Text style={styles.muted}>No verified broker connection records were returned.</Text>}
    renderItem={({item})=><View style={styles.panel}>
      <Text style={styles.overline}>BROKER / ACCOUNT-SCOPED</Text>
      <Text style={styles.title}>{safeLabel(item.account_label,'Broker connection')}</Text>
      <Text style={styles.muted}>Provider: {safeLabel(item.platform,safeLabel(item.provider))}</Text>
      <Text style={styles.line}>Environment: {item.environment==='demo'?'Demo':item.environment==='live'?'Live account (not a certification)':'Unverified'}</Text>
      <Text style={styles.line}>Connection: {safeLabel(item.status)}</Text>
      <Text style={styles.line}>Execution permission: {item.execution_enabled===true?'Backend reports enabled; certification still required':item.execution_enabled===false?'Disabled':'Unreported'}</Text>
      <Text style={styles.muted}>No trading action is available on this read-only screen.</Text>
    </View>}/>;
}

export function NativeNotifications(){
  const state=useResource('/notifications?limit=50');
  const [pending,setPending]=useState('');
  const [message,setMessage]=useState('');
  const [unread,setUnread]=useState(false);
  if(!state.data)return <ResponseState {...state}/>;
  const notifications=Array.isArray(state.data.notifications)?state.data.notifications:[];
  const visible=unread?notifications.filter((x:any)=>x.read_at==null):notifications;
  async function markRead(id:string) {
    if(!id||pending)return;
    setPending(id);setMessage('');
    try{
      const result=await api<any>('/notifications/'+encodeURIComponent(id)+'/read',{method:'POST'});
      if(result.read===true){state.retry();}
      else setMessage('The service did not confirm the read receipt.');
    }catch(e){setMessage(e instanceof Error?e.message:'Could not confirm this update.');}
    finally{setPending('');}
  }
  return <View style={{flex:1}}>
    <Disclosure text="Notifications are account-scoped messages. Message receipt does not certify a broker fill or signal outcome."/>
    <Pressable accessibilityRole="button" onPress={()=>setUnread(v=>!v)} style={styles.secondary}>
      <Text style={styles.actionText}>{unread?'Show all recent messages':'Show unread in this view'}</Text>
    </Pressable>
    {message?<Text accessibilityRole="alert" style={styles.warning}>{message}</Text>:null}
    <FlatList data={visible} keyExtractor={(item,i)=>String(item.notification_id||i)}
      ListEmptyComponent={<Text style={styles.muted}>No {unread?'unread':'recent'} notifications were returned.</Text>}
      renderItem={({item})=><View style={styles.panel}>
        <Text style={styles.overline}>{safeLabel(item.event_type,'NOTIFICATION')} / {item.read_at?'READ':'UNREAD'}</Text>
        <Text style={styles.title}>{safeLabel(item.title,'Account notification')}</Text>
        <Text style={styles.line}>{safeLabel(item.body,'No message provided.')}</Text>
        {!item.read_at&&<Pressable accessibilityRole="button" disabled={Boolean(pending)} style={styles.secondary}
          onPress={()=>markRead(safeLabel(item.notification_id,''))}><Text style={styles.actionText}>{pending===item.notification_id?'Updating…':'Mark as read'}</Text></Pressable>}
      </View>}/></View>;
}

export function NativeWatchlists(){
  const state=useResource('/watchlists');
  const [name,setName]=useState('');
  const [query,setQuery]=useState('');
  const [selected,setSelected]=useState('');
  const [results,setResults]=useState<any[]|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  if(!state.data)return <ResponseState {...state}/>;
  const lists=Array.isArray(state.data.watchlists)?state.data.watchlists:[];
  async function create(){
    if(!name.trim()||busy)return;
    setBusy(true);setMessage('');
    try{
      const result=await api<any>('/watchlists',{method:'POST',body:JSON.stringify({name:name.trim()})});
      if(result.watchlist_id){setName('');state.retry();setMessage('Watchlist created.');}
      else setMessage('Watchlist creation was not confirmed.');
    }catch(e){setMessage(e instanceof Error?e.message:'Watchlist not saved.');}
    finally{setBusy(false);}
  }
  async function search(){
    if(query.trim().length<2)return;
    setBusy(true);setMessage('');setResults(null);
    try{
      const result=await api<any>('/instruments/search?q='+encodeURIComponent(query.trim())+'&limit=12');
      setResults(Array.isArray(result.instruments)?result.instruments:[]);
    }catch(e){setMessage(e instanceof Error?e.message:'Instrument search unavailable.');}
    finally{setBusy(false);}
  }
  async function add(instrumentId:string){
    if(!selected||!instrumentId||busy)return;
    setBusy(true);setMessage('');
    try{
      const result=await api<any>('/watchlists/'+encodeURIComponent(selected)+'/items',{
        method:'POST',body:JSON.stringify({instrument_id:instrumentId}),
      });
      if(result.added===true){setMessage('Instrument added to your account watchlist.');state.retry();}
      else setMessage('No watchlist change was confirmed.');
    }catch(e){setMessage(e instanceof Error?e.message:'Could not add instrument.');}
    finally{setBusy(false);}
  }
  return <ScrollView keyboardShouldPersistTaps="handled">
    <Disclosure text="Watchlists are informational. Only canonical active instrument identities can be added; this does not enable broker execution."/>
    <View style={styles.panel}>
      <Text style={styles.title}>Your watchlists</Text>
      {lists.length?lists.map((item:any,i:number)=><Pressable accessibilityRole="button" key={String(item.watchlist_id||i)}
        onPress={()=>{setSelected(String(item.watchlist_id));setResults(null)}} style={[styles.listItem,selected===item.watchlist_id&&styles.selected]}>
        <Text style={styles.line}>{safeLabel(item.name,'Unnamed list')} {item.is_default===true?'· Default':''}</Text>
        <Text style={styles.muted}>{quantityLabel(Array.isArray(item.items)?item.items.length:undefined,0)} watched instruments</Text>
      </Pressable>):<Text style={styles.muted}>No watchlists returned. Create one below.</Text>}
      <TextInput accessibilityLabel="New watchlist name" value={name} onChangeText={setName}
        style={styles.input} placeholder="New watchlist name" placeholderTextColor="#a5b8ad" maxLength={90}/>
      <Pressable accessibilityRole="button" disabled={busy||name.trim().length<2} onPress={create} style={styles.action}><Text style={styles.actionText}>Create watchlist</Text></Pressable>
    </View>
    {selected?<View style={styles.panel}>
      <Text style={styles.title}>Add a canonical instrument</Text>
      <TextInput accessibilityLabel="Search instruments" value={query} onChangeText={setQuery}
        style={styles.input} placeholder="BTCUSD, XAUUSD, EURUSD…" placeholderTextColor="#a5b8ad" maxLength={80}/>
      <Pressable accessibilityRole="button" disabled={busy||query.trim().length<2} style={styles.secondary} onPress={search}><Text style={styles.actionText}>Search instruments</Text></Pressable>
      {results!==null&&(results.length?results.map((item:any,i:number)=><View style={styles.listItem} key={String(item.instrument_id||i)}>
        <Text style={styles.line}>{safeLabel(item.display_symbol,safeLabel(item.canonical_symbol))} · {safeLabel(item.asset_class)}</Text>
        <Pressable accessibilityRole="button" disabled={busy||!item.instrument_id} style={styles.secondary} onPress={()=>add(String(item.instrument_id))}><Text style={styles.actionText}>Add</Text></Pressable>
      </View>):<Text style={styles.muted}>No matching instruments were returned.</Text>)}
    </View>:null}
    {message?<Text accessibilityRole="alert" style={styles.warning}>{message}</Text>:null}
  </ScrollView>;
}

const styles=StyleSheet.create({
  panel:{backgroundColor:'#101e19',borderColor:'#294036',borderWidth:1,borderRadius:14,padding:17,gap:11,marginBottom:13},
  disclosure:{padding:14,borderLeftWidth:3,borderLeftColor:'#4ce0a4',backgroundColor:'#14251d',borderRadius:9,marginBottom:13},
  overline:{color:'#bcf4d7',fontSize:10,letterSpacing:1,fontWeight:'800'},
  title:{color:'#e6eeea',fontSize:18,fontWeight:'800',lineHeight:24},
  muted:{color:'#a5b8ad',fontSize:12,lineHeight:19},
  line:{color:'#e6eeea',fontSize:13,lineHeight:20,flexShrink:1},
  action:{backgroundColor:'#4ce0a4',borderRadius:9,paddingVertical:13,paddingHorizontal:16,minHeight:44,justifyContent:'center',alignItems:'center'},
  secondary:{backgroundColor:'#14251d',borderColor:'#294036',borderWidth:1,borderRadius:9,paddingVertical:11,paddingHorizontal:12,minHeight:44,justifyContent:'center',alignItems:'center'},
  actionText:{color:'#e6eeea',fontSize:12,fontWeight:'800'},
  input:{borderColor:'#294036',borderWidth:1,backgroundColor:'#08120f',color:'#e6eeea',padding:12,minHeight:45,borderRadius:9},
  listItem:{backgroundColor:'#14251d',borderWidth:1,borderColor:'#294036',borderRadius:8,padding:11,gap:7,marginBottom:7},
  selected:{borderColor:'#4ce0a4'},
  warning:{color:'#e6eeea',backgroundColor:'#14251d',padding:12,borderRadius:9,marginBottom:12},
});
