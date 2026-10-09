import React, {useEffect,useState} from 'react';
import {ActivityIndicator,FlatList,Pressable,ScrollView,StyleSheet,Text,TextInput,View,useColorScheme} from 'react-native';
import {api} from './api';
import {finiteNumber,quantityLabel,safeLabel} from './presentation';

function useData(route:string){
  const [version,setVersion]=useState(0);
  const [state,setState]=useState<{data:any;busy:boolean;error:string}>({data:null,busy:true,error:''});
  useEffect(()=>{
    let active=true;
    setState({data:null,busy:true,error:''});
    api<any>(route).then(data=>{if(active)setState({data,busy:false,error:''})})
      .catch(e=>{if(active)setState({data:null,busy:false,error:e instanceof Error?e.message:'The account service did not respond.'})});
    return()=>{active=false};
  },[route,version]);
  return {...state,retry:()=>setVersion(n=>n+1)};
}
function ErrorState({busy,error,retry}:{busy:boolean;error:string;retry:()=>void}){
  const styles=useStyles();
  return <View style={styles.card}>
    {busy?<ActivityIndicator color={useColorScheme()==='light'?'#08754e':'#4ce0a4'}/>:<Text accessibilityRole="alert" style={styles.body}>{error||'No confirmed records returned.'}</Text>}
    {!busy&&<Pressable accessibilityRole="button" style={styles.secondary} onPress={retry}><Text style={styles.body}>Retry account data</Text></Pressable>}
  </View>;
}
const alertKinds=[
  {key:'signal_generated',label:'Qualified signal'},
  {key:'price_above',label:'Price above'},
  {key:'price_below',label:'Price below'},
  {key:'entry_triggered',label:'Entry observed'},
  {key:'outcome',label:'Outcome event'},
  {key:'provider_status',label:'Provider status'},
] as const;
type AlertKind=typeof alertKinds[number]['key'];
function priceKind(kind:AlertKind){return kind==='price_above'||kind==='price_below';}

export function NativeAlertRules(){
  const styles=useStyles();
  const state=useData('/alerts');
  const [kind,setKind]=useState<AlertKind>('signal_generated');
  const [asset,setAsset]=useState('');
  const [threshold,setThreshold]=useState('');
  const [notice,setNotice]=useState('');
  const [pending,setPending]=useState(false);
  const [confirmId,setConfirmId]=useState('');
  if(!state.data)return <ErrorState busy={state.busy} error={state.error} retry={state.retry}/>;
  const items=Array.isArray(state.data.alerts)?state.data.alerts:[];
  async function create(){
    if(pending)return;
    const symbol=asset.trim().toUpperCase();
    const price=finiteNumber(threshold);
    if(!/^[A-Z0-9._/-]{2,32}$/.test(symbol)||(priceKind(kind)&&(price===null||price<=0))){
      setNotice('Enter an eligible instrument and a positive threshold if required.');return;
    }
    setPending(true);setNotice('');
    try{
      const response=await api<any>('/alerts',{
        method:'POST',body:JSON.stringify({
          asset:symbol,alert_type:kind,condition:priceKind(kind)?{value:price}:{},channels:['web'],
        }),
      });
      if(response.alert_id){setNotice('Web alert rule confirmed.');setAsset('');setThreshold('');setKind('signal_generated');state.retry();}
      else setNotice('Alert creation was not confirmed.');
    }catch(e){setNotice(e instanceof Error?e.message:'Alert rule could not be saved.');}
    finally{setPending(false);}
  }
  async function disable(id:string){
    if(pending||confirmId!==id)return;
    setPending(true);setNotice('');
    try{
      const response=await api<any>('/alerts/'+encodeURIComponent(id),{method:'DELETE'});
      if(response.disabled===true){setConfirmId('');setNotice('Alert disablement confirmed by the account service.');state.retry();}
      else setNotice('Alert disablement was not confirmed.');
    }catch(e){setNotice(e instanceof Error?e.message:'Alert disablement could not be verified.');}
    finally{setPending(false);}
  }
  return <ScrollView keyboardShouldPersistTaps="handled">
    <View style={styles.disclosure}><Text style={styles.muted}>Custom alert rules monitor events; they are not orders or guaranteed delivery receipts. Account plan and provider coverage apply.</Text></View>
    {items.map((item:any,i:number)=>{
      const id=safeLabel(item.alert_id,'');
      const isPrice=item.alert_type==='price_above'||item.alert_type==='price_below';
      return <View style={styles.card} key={id||String(i)}>
        <Text style={styles.overline}>{item.active===true?'ACTIVE RULE':'DISABLED RULE'}</Text>
        <Text style={styles.title}>{safeLabel(item.asset,'Instrument')} · {safeLabel(item.alert_type)}</Text>
        <Text style={styles.muted}>Threshold: {isPrice?quantityLabel(item.condition?.value,6):'Event based'}</Text>
        <Text style={styles.muted}>Channels: {Array.isArray(item.channels)?item.channels.join(', '):'Unreported'}</Text>
        {item.active===true&&id&&(confirmId===id?<View style={styles.row}>
          <Text style={styles.body}>Disable this alert?</Text>
          <Pressable accessibilityRole="button" disabled={pending} style={styles.secondary} onPress={()=>setConfirmId('')}><Text style={styles.body}>Keep</Text></Pressable>
          <Pressable accessibilityRole="button" disabled={pending} style={styles.secondary} onPress={()=>disable(id)}><Text style={styles.body}>Confirm disable</Text></Pressable>
        </View>:<Pressable accessibilityRole="button" style={styles.secondary} onPress={()=>setConfirmId(id)}><Text style={styles.body}>Disable rule</Text></Pressable>)}
      </View>;
    })}
    {!items.length&&<Text style={styles.muted}>No custom alert rules returned. Your plan may restrict this feature.</Text>}
    <View style={styles.card}>
      <Text style={styles.overline}>ACCOUNT-OWNED MONITORING</Text><Text style={styles.title}>Create web alert</Text>
      <TextInput accessibilityLabel="Instrument symbol" value={asset} onChangeText={setAsset} autoCapitalize="characters" maxLength={32} style={styles.input} placeholder="Instrument symbol" placeholderTextColor="#869f91"/>
      <Text style={styles.muted}>Event type</Text>
      <View style={styles.row}>{alertKinds.map(item=><Pressable key={item.key} accessibilityRole="button"
        accessibilityState={{selected:kind===item.key}} onPress={()=>setKind(item.key)} style={[styles.chip,kind===item.key&&styles.selected]}><Text style={styles.chipText}>{item.label}</Text></Pressable>)}</View>
      {priceKind(kind)&&<TextInput accessibilityLabel="Positive price threshold" value={threshold} onChangeText={setThreshold} keyboardType="decimal-pad" style={styles.input} placeholder="Price threshold" placeholderTextColor="#869f91"/>}
      <Text style={styles.muted}>Delivery channel: Web only for this native form. Configure additional channels in the web workspace.</Text>
      <Pressable accessibilityRole="button" style={styles.primary} disabled={pending} onPress={create}><Text style={styles.primaryText}>{pending?'Saving…':'Create alert'}</Text></Pressable>
    </View>
    {notice?<Text accessibilityRole="alert" style={styles.body}>{notice}</Text>:null}
  </ScrollView>;
}

export function NativeResearch(){
  const styles=useStyles();
  const state=useData('/strategy-leaderboard?days=30');
  if(!state.data)return <ErrorState busy={state.busy} error={state.error} retry={state.retry}/>;
  const items=Array.isArray(state.data.strategies)?state.data.strategies:[];
  return <FlatList data={items} keyExtractor={(item,i)=>safeLabel(item.strategy_name,String(i))}
    ListHeaderComponent={<View style={styles.disclosure}>
      <Text style={styles.muted}>Strategy frequency in a 30-day research window. Counts are not profitability, execution proof or a recommendation. This diagnostic is subject to account authority.</Text>
    </View>}
    ListEmptyComponent={<Text style={styles.muted}>No authorized research breakdown returned.</Text>}
    renderItem={({item})=><View style={styles.card}>
      <Text style={styles.overline}>STRATEGY / OBSERVATIONAL COUNT</Text>
      <Text style={styles.title}>{safeLabel(item.strategy_name,'Unspecified strategy')}</Text>
      <Text style={styles.body}>Recorded signals: {quantityLabel(item.signals,0)}</Text>
    </View>}/>;
}

const darkStyles=StyleSheet.create({
 card:{backgroundColor:'#101e19',borderColor:'#294036',borderWidth:1,borderRadius:12,padding:16,marginBottom:12,gap:11},
 disclosure:{backgroundColor:'#14251d',borderLeftColor:'#4ce0a4',borderLeftWidth:3,padding:14,borderRadius:9,marginBottom:12},
 overline:{color:'#bcf4d7',fontSize:10,fontWeight:'800',letterSpacing:1},
 title:{color:'#e6eeea',fontSize:17,fontWeight:'800'},
 body:{color:'#e6eeea',fontSize:13,lineHeight:20},
 muted:{color:'#a5b8ad',fontSize:12,lineHeight:19},
 row:{flexDirection:'row',flexWrap:'wrap',gap:7,alignItems:'center'},
 chip:{backgroundColor:'#14251d',borderColor:'#294036',borderWidth:1,borderRadius:8,paddingVertical:10,paddingHorizontal:11,minHeight:44,justifyContent:'center'},
 selected:{borderColor:'#4ce0a4'},
 chipText:{fontSize:11,color:'#e6eeea'},
 input:{color:'#e6eeea',backgroundColor:'#08120f',borderColor:'#294036',borderWidth:1,borderRadius:9,padding:12,minHeight:45},
 primary:{backgroundColor:'#4ce0a4',padding:13,minHeight:44,borderRadius:9,alignItems:'center',justifyContent:'center'},
 primaryText:{color:'#071c12',fontWeight:'800',fontSize:13},
 secondary:{borderColor:'#294036',borderWidth:1,backgroundColor:'#14251d',padding:11,minHeight:44,borderRadius:9,alignItems:'center',justifyContent:'center'},
});
const lightPalette:Record<string,string>={
 '#08120f':'#f1f5f3','#101e19':'#ffffff','#14251d':'#eaf1ed','#e6eeea':'#152a21',
 '#a5b8ad':'#52685c','#294036':'#d1dfd6','#4ce0a4':'#08754e','#bcf4d7':'#085c3f','#071c12':'#ffffff',
};
const lightStyles=Object.fromEntries(Object.entries(darkStyles).map(([key,style])=>[
 key,Object.fromEntries(Object.entries(style).map(([prop,value])=>[
 prop,typeof value==='string'?(lightPalette[value]||value):value
 ])),
])) as typeof darkStyles;
function useStyles(){return useColorScheme()==='light'?lightStyles:darkStyles;}
