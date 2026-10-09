import React, {useState} from 'react';
import {Pressable, ScrollView, StyleSheet, Text, View, useColorScheme} from 'react-native';

export type MobileScreen = 'overview'|'signals'|'markets'|'paper'|'portfolio'|'performance'|'journal'|'support'|'account'|'brokers'|'notifications'|'watchlists'|'alerts'|'research';
const primary: {label:string;screen:MobileScreen;index:string}[] = [
  {label:'Overview',screen:'overview',index:'01'},
  {label:'Signals',screen:'signals',index:'02'},
  {label:'Markets',screen:'markets',index:'03'},
  {label:'Paper',screen:'paper',index:'04'},
];
const secondary: {label:string;screen:MobileScreen;description:string}[] = [
  {label:'Portfolio',screen:'portfolio',description:'Paper exposure'},
  {label:'Performance',screen:'performance',description:'Proof-backed history'},
  {label:'Journal',screen:'journal',description:'Personal reflections'},
  {label:'Support',screen:'support',description:'Account assistance'},
  {label:'Account',screen:'account',description:'Identity, security and billing'},
  {label:'Brokers',screen:'brokers',description:'Connection inventory'},
  {label:'Watchlists',screen:'watchlists',description:'Canonical instruments'},
  {label:'Notifications',screen:'notifications',description:'Account message receipts'},
  {label:'Alerts',screen:'alerts',description:'Monitoring rules'},
  {label:'Research',screen:'research',description:'Entitlement-gated strategy counts'},

];

export function MobileNavigation({active,onSelect}:{active:MobileScreen;onSelect:(screen:MobileScreen)=>void}) {
  const styles=useAppStyles();
  const [more,setMore]=useState(false);
  const selectedSecondary=secondary.some(s=>s.screen===active);
  function navigate(screen:MobileScreen){onSelect(screen);setMore(false);}
  return <View style={styles.container}>
    {more&&<View style={styles.menu}>
      <Text style={styles.menuTitle}>MORE WORKSPACE SECTIONS</Text>
      <ScrollView nestedScrollEnabled contentContainerStyle={styles.menuGrid} showsVerticalScrollIndicator>{secondary.map(item=><Pressable
        key={item.screen}
        accessibilityRole="button"
        accessibilityState={{selected:active===item.screen}}
        style={[styles.menuItem,active===item.screen&&styles.selected]}
        onPress={()=>navigate(item.screen)}>
        <Text style={styles.menuName}>{item.label}</Text>
        <Text style={styles.menuDetail}>{item.description}</Text>
      </Pressable>)}</ScrollView>
    </View>}
    <View style={styles.tabs} accessibilityRole="tablist">
      {primary.map(item=><Pressable
        key={item.screen}
        accessibilityRole="tab"
        accessibilityLabel={item.label}
        accessibilityState={{selected:active===item.screen}}
        style={[styles.tab,active===item.screen&&styles.selected]}
        onPress={()=>navigate(item.screen)}>
        <Text style={[styles.tabNumber,active===item.screen&&styles.activeLabel]}>{item.index}</Text>
        <Text numberOfLines={1} style={[styles.tabLabel,active===item.screen&&styles.activeLabel]}>{item.label}</Text>
      </Pressable>)}
      <Pressable accessibilityRole="button" accessibilityLabel={more?'Close more sections':'Browse more sections'}
        accessibilityState={{expanded:more}} style={[styles.tab,(selectedSecondary||more)&&styles.selected]}
        onPress={()=>setMore(value=>!value)}>
        <Text style={[styles.tabNumber,(selectedSecondary||more)&&styles.activeLabel]}>···</Text>
        <Text style={[styles.tabLabel,(selectedSecondary||more)&&styles.activeLabel]}>More</Text>
      </Pressable>
    </View>
  </View>;
}
const darkStyles=StyleSheet.create({
  container:{backgroundColor:'#101e19',borderTopColor:'#294036',borderTopWidth:1,paddingTop:6},
  tabs:{flexDirection:'row',alignItems:'stretch',justifyContent:'space-between',gap:3,paddingBottom:3},
  tab:{flex:1,minWidth:0,alignItems:'center',justifyContent:'center',paddingVertical:7,borderRadius:9,minHeight:51,gap:2},
  selected:{backgroundColor:'#14251d'},
  tabNumber:{color:'#a5b8ad',fontSize:11,fontWeight:'800'},
  tabLabel:{color:'#a5b8ad',fontSize:10,fontWeight:'600'},
  activeLabel:{color:'#4ce0a4'},
  menu:{borderBottomColor:'#294036',borderBottomWidth:1,paddingBottom:14,paddingTop:9,maxHeight:340},
  menuTitle:{color:'#bcf4d7',fontSize:10,fontWeight:'800',letterSpacing:1,marginBottom:9},
  menuGrid:{flexDirection:'row',flexWrap:'wrap',gap:7},
  menuItem:{backgroundColor:'#14251d',borderColor:'#294036',borderWidth:1,borderRadius:9,minWidth:'47%',flexGrow:1,padding:11,minHeight:60,justifyContent:'center'},
  menuName:{color:'#e6eeea',fontSize:13,fontWeight:'700'},
  menuDetail:{color:'#a5b8ad',fontSize:10,marginTop:5},
});

const lightPalette:Record<string,string> = {
 '#101e19':'#ffffff','#14251d':'#eaf1ed','#294036':'#d1dfd6',
 '#a5b8ad':'#52685c','#4ce0a4':'#08754e','#bcf4d7':'#085c3f',
 '#e6eeea':'#152a21',
};
const lightStyles=Object.fromEntries(Object.entries(darkStyles).map(([key,style])=>[
 key,Object.fromEntries(Object.entries(style).map(([prop,value])=>[
 prop,typeof value==='string'?(lightPalette[value]||value):value
 ])),
])) as typeof darkStyles;
function useAppStyles(){return useColorScheme()==='light'?lightStyles:darkStyles;}
