"use client";

import { useState } from "react";
import { finite, moneyLabel, timeLabel, type Row } from "../lib/presentation";

type Point = {value:number;time:string;amount:number|null;entry:string;sourceIndex:number};
const plotWidth=760;
const plotHeight=200;
const padding={top:16,bottom:22,left:12,right:12};

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
  if(samples.length<2)return <section className="sr-data-panel">
    <p className="sr-overline">Account-owned simulated ledger</p>
    <h2>Paper equity history</h2>
    <div className="sr-empty"><strong>Insufficient verified ledger records to draw a chart.</strong>
      <p>The graph needs at least two timestamped paper ledger balances. No example or placeholder prices are shown.</p></div>
  </section>;

  const lower=Math.min(...samples.map(p=>p.value));
  const upper=Math.max(...samples.map(p=>p.value));
  const range=upper-lower || 1;
  const span=plotWidth-padding.left-padding.right;
  const height=plotHeight-padding.top-padding.bottom;
  const coordinates=samples.map((p,i)=>{
    const x=padding.left+i/(samples.length-1)*span;
    const y=padding.top+height-(p.value-lower)/range*height;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  const last=samples[samples.length-1];
  const first=samples[0];

  return <section className="sr-data-panel sr-ledger-chart" aria-labelledby="sr-paper-ledger-title">
    <div className="sr-section-head">
      <div><p className="sr-overline">Simulated capital / historical evidence only</p>
        <h2 id="sr-paper-ledger-title">Paper equity ledger</h2>
      </div><strong className="sr-state">{samples.length} recorded balances</strong>
    </div>
    <div className="sr-ledger-chart-metrics">
      <div><span>Earliest displayed balance</span><strong>{moneyLabel(first.value,currency)==="Unavailable" ? first.value.toLocaleString() : moneyLabel(first.value,currency)}</strong><small>{timeLabel(first.time)}</small></div>
      <div><span>Latest displayed balance</span><strong>{moneyLabel(last.value,currency)==="Unavailable" ? last.value.toLocaleString() : moneyLabel(last.value,currency)}</strong><small>{timeLabel(last.time)}</small></div>
      <div><span>Recorded range</span><strong>{lower.toLocaleString()}–{upper.toLocaleString()}</strong><small>Paper account units · not market-price data</small></div>
    </div>
    <div className="sr-ledger-plot">
      <svg viewBox="0 0 760 200" role="img" aria-labelledby="sr-ledger-svg-title sr-ledger-svg-description" preserveAspectRatio="none">
        <title id="sr-ledger-svg-title">Historical paper ledger balance</title>
        <desc id="sr-ledger-svg-description">{samples.length} observed virtual balance records from {timeLabel(first.time)} to {timeLabel(last.time)}. Minimum observed {lower.toLocaleString()}, maximum observed {upper.toLocaleString()}. Straight segments connect successive recorded balances; they are not broker fills or live account prices.</desc>
        {[0,.25,.5,.75,1].map(f=><line key={f} x1={padding.left} x2={plotWidth-padding.right} y1={padding.top+f*height} y2={padding.top+f*height} className="sr-ledger-gridline"/>)}
        <polyline points={coordinates} className="sr-ledger-line" fill="none" strokeLinejoin="round" strokeLinecap="round" strokeWidth="2.4" vectorEffect="non-scaling-stroke"/>
      </svg>
    </div>
    <div className="sr-list-actions">
      <p className="sr-muted">Source: canonical paper ledger. The chart connects recorded snapshots only; no price path or outcome is inferred between observations.</p>
      <button type="button" className="sr-secondary-action" aria-expanded={showTable} aria-controls="sr-equity-data-table" onClick={()=>setShowTable(v=>!v)}>{showTable?"Hide ledger rows":"Inspect ledger rows"}</button>
    </div>
    {showTable&&<div id="sr-equity-data-table" className="sr-table-scroll" tabIndex={0} aria-label="Scrollable simulated equity ledger table">
      <table><thead><tr><th>Recorded at</th><th>Paper balance</th><th>Entry type</th><th>Ledger delta</th></tr></thead>
        <tbody>{samples.slice(-25).reverse().map(p=><tr key={p.sourceIndex}><td>{timeLabel(p.time)}</td><td>{moneyLabel(p.value,currency)==="Unavailable"?p.value.toLocaleString():moneyLabel(p.value,currency)}</td><td>{p.entry}</td><td>{p.amount===null?"Unavailable":p.amount.toLocaleString()}</td></tr>)}</tbody>
      </table>
      <p className="sr-muted">Showing the latest {Math.min(25,samples.length)} of {samples.length} eligible ledger rows. All amounts are simulated.</p>
    </div>}
  </section>;
}
