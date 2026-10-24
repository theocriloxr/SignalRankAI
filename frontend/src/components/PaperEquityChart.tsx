"use client";

import { useState } from "react";
import { finite, moneyLabel, timeLabel, type Row } from "../lib/presentation";
import { Badge, Card, Empty, Stat, TableWrap } from "./ui/primitives";

type Point = {value:number;time:string;amount:number|null;entry:string;sourceIndex:number};
const plotWidth=760;
const plotHeight=200;
const padding={top:16,bottom:16,left:8,right:8};

/** Paper-ledger chart. No interpolation, future predictions, derived broker
 * balances, currency conversion or invented zero-value points. */
export function PaperEquityChart({ledger,currency}:{ledger:Row[];currency:unknown}) {
  const [showTable,setShowTable]=useState(false);
  const series:Point[]=ledger.flatMap((row,index)=>{
    const value=finite(row.balance_after);
    const date=typeof row.created_at==="string" && Number.isFinite(Date.parse(row.created_at)) ? row.created_at : null;
    if(value===null||date===null)return [];
    return [{value,time:date,amount:finite(row.amount),entry:typeof row.entry_type==="string"?row.entry_type:"Unclassified",sourceIndex:index}];
  });
  const samples=series.slice(-250);
  const label=(value:number)=>moneyLabel(value,currency)==="Unavailable" ? value.toLocaleString() : moneyLabel(value,currency);
  if(samples.length<2)return <Card title="Paper equity history" eyebrow="Simulated ledger">
    <Empty title="Not enough ledger records to draw a chart." icon="performance">The chart needs at least two timestamped paper ledger balances. No example or placeholder values are shown.</Empty>
  </Card>;

  const lower=Math.min(...samples.map(p=>p.value));
  const upper=Math.max(...samples.map(p=>p.value));
  const range=upper-lower || 1;
  const span=plotWidth-padding.left-padding.right;
  const height=plotHeight-padding.top-padding.bottom;
  const points=samples.map((p,i)=>{
    const x=padding.left+i/(samples.length-1)*span;
    const y=padding.top+height-(p.value-lower)/range*height;
    return [x,y] as const;
  });
  const coordinates=points.map(([x,y])=>`${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area=`M${points[0][0].toFixed(2)},${plotHeight} L${coordinates.replaceAll(" "," L")} L${points[points.length-1][0].toFixed(2)},${plotHeight} Z`;
  const last=samples[samples.length-1];
  const first=samples[0];

  return <Card id="ws-paper-ledger" title="Paper equity ledger" eyebrow="Simulated capital · historical records only"
    actions={<Badge plain>{samples.length} recorded balances</Badge>}>
    <div className="ui-stat-grid">
      <Stat label="Earliest displayed balance" value={label(first.value)} detail={timeLabel(first.time)}/>
      <Stat label="Latest displayed balance" value={label(last.value)} detail={timeLabel(last.time)}/>
      <Stat label="Recorded range" value={`${lower.toLocaleString()}–${upper.toLocaleString()}`} detail="Paper account units · not market prices"/>
    </div>
    <div className="ws-chart">
      <svg viewBox={`0 0 ${plotWidth} ${plotHeight}`} role="img" aria-labelledby="ws-ledger-svg-title ws-ledger-svg-description" preserveAspectRatio="none">
        <title id="ws-ledger-svg-title">Historical paper ledger balance</title>
        <desc id="ws-ledger-svg-description">{samples.length} observed virtual balance records from {timeLabel(first.time)} to {timeLabel(last.time)}. Minimum observed {lower.toLocaleString()}, maximum observed {upper.toLocaleString()}. Straight segments connect successive recorded balances; they are not broker fills or live account prices.</desc>
        <path d={area} className="ws-chart-area"/>
        <polyline points={coordinates} className="ws-chart-line" fill="none" strokeLinejoin="round" strokeLinecap="round" strokeWidth="2" vectorEffect="non-scaling-stroke"/>
      </svg>
    </div>
    <div className="ui-pagination">
      <p className="ui-muted">Source: canonical paper ledger. Lines connect recorded snapshots only; nothing between observations is inferred.</p>
      <button type="button" className="ui-btn ui-btn--sm" aria-expanded={showTable} aria-controls="ws-equity-data-table" onClick={()=>setShowTable(v=>!v)}>{showTable?"Hide ledger rows":"Inspect ledger rows"}</button>
    </div>
    {showTable&&<div className="ws-stack"><TableWrap id="ws-equity-data-table" label="Scrollable simulated equity ledger table">
      <thead><tr><th>Recorded at</th><th>Paper balance</th><th>Entry type</th><th>Ledger delta</th></tr></thead>
      <tbody>{samples.slice(-25).reverse().map(p=><tr key={p.sourceIndex}><td>{timeLabel(p.time)}</td><td>{label(p.value)}</td><td>{p.entry}</td><td>{p.amount===null?"Unavailable":p.amount.toLocaleString()}</td></tr>)}</tbody>
    </TableWrap>
    <p className="ui-muted">Showing the latest {Math.min(25,samples.length)} of {samples.length} eligible ledger rows. All amounts are simulated.</p></div>}
  </Card>;
}
