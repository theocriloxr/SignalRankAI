"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

const stages = [
  { index:"01",slug:"sources",eyebrow:"INGEST / VERIFY",title:"Start with trustworthy inputs.",description:"A quote is only useful with its market, source, timestamp and session. Unsupported or stale data must fail the qualification process.",nodes:["Provider capability","Market session","Quote freshness"],tag:"DATA QUALITY" },
  { index:"02",slug:"strategy",eyebrow:"RESEARCH / EVALUATE",title:"Find the setup. Challenge the evidence.",description:"Strategies, market structure and model context are evaluated together. A promising setup is not automatically an eligible signal.",nodes:["Strategy candidate","Model calibration","Threshold evidence"],tag:"CANDIDATE REVIEW" },
  { index:"03",slug:"risk",eyebrow:"RISK / REJECT",title:"Protection before participation.",description:"Account, market and execution policies can stop the workflow. High scores never override missing authorization or risk information.",nodes:["Risk constraints","Account boundaries","Fail-closed decision"],tag:"ADMISSION POLICY" },
  { index:"04",slug:"delivery",eyebrow:"DELIVER / TRACE",title:"Every signal has a history.",description:"Delivery receipts, paper observations and broker-confirmed executions are different events. The account workspace keeps them distinguishable.",nodes:["Entitled receipt","Lifecycle evidence","Outcome tracking"],tag:"RECORDED LIFECYCLE" },
] as const;

export function SignalLifecycleExperience() {
  const [active,setActive] = useState(0);
  const targets = useRef<(HTMLElement|null)[]>([]);
  useEffect(()=>{
    if(typeof IntersectionObserver==="undefined")return;
    const obs=new IntersectionObserver(entries=>{
      const visible=entries.filter(entry=>entry.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];
      if(visible)setActive(Number((visible.target as HTMLElement).dataset.stage||0));
    },{rootMargin:"-24% 0px -32% 0px",threshold:[0,.25,.5,.75]});
    targets.current.forEach(node=>{if(node)obs.observe(node)});
    return ()=>obs.disconnect();
  },[]);
  const current=stages[active];
  function jump(index:number){
    setActive(index);
    const reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    targets.current[index]?.scrollIntoView({behavior:reduced?"instant":"smooth",block:"center"});
  }
  return <section className="sr-cinema-lifecycle" id="lifecycle" aria-labelledby="sr-lifecycle-title">
    <div className="sr-cinema-section-heading">
      <p className="sr-cinema-kicker">02 / THE DECISION ENGINE</p>
      <div><h2 id="sr-lifecycle-title">From market noise to <em>accountable decisions.</em></h2>
        <p>Scroll through the four gates. Each phase changes the schematic workstation, showing how the product earns—or refuses—a signal. This is a system illustration, not live market data.</p>
      </div>
    </div>
    <div className="sr-cinema-lifecycle-grid">
      <div className="sr-cinema-sticky">
        <div className="sr-cinema-workstation" data-stage={current.slug} aria-label={"Illustrative signal workflow: "+current.tag}>
          <div className="sr-cinema-workstation-top"><span>SR / DECISION PIPELINE</span><span>SCHEMATIC · NOT LIVE</span></div>
          <div className="sr-cinema-workstation-screen">
            <div className="sr-cinema-mini-rail" aria-hidden="true"><i/><i/><i/><i/></div>
            <div className="sr-cinema-mini-main">
              <div className="sr-cinema-mini-head"><span>{current.eyebrow}</span><span>{current.index} / 04</span></div>
              <div className="sr-cinema-mini-graph" aria-hidden="true">
                <div className="sr-cinema-rings"><i/><i/><i/></div>
                <div className="sr-cinema-mini-beam"/>
                <div className="sr-cinema-mini-nodes">{current.nodes.map((node,i)=><div key={node}><span>0{i+1}</span><strong>{node}</strong></div>)}</div>
              </div>
              <div className="sr-cinema-mini-output"><span>REVIEW STATE</span><strong>{current.tag}</strong></div>
            </div>
          </div>
          <div className="sr-cinema-workstation-bottom"><span>NO LIVE PRICE / NO ORDER CLAIM</span><span>GATE {current.index}</span></div>
        </div>
        <nav className="sr-cinema-gates" aria-label="Explore decision stages">{stages.map((stage,index)=>
          <button key={stage.index} type="button" onClick={()=>jump(index)} aria-current={active===index?"step":undefined}
            className={active===index?"is-active":""}>
            <span>{stage.index}</span>{" "}<strong>{stage.tag}</strong></button>)}</nav>
      </div>
      <div className="sr-cinema-chapters">
        {stages.map((stage,index)=><article id={"gate-"+stage.slug} data-stage={index} key={stage.index}
          className={"sr-cinema-chapter"+(active===index?" is-active":"")}
          ref={node=>{targets.current[index]=node}}>
          <p className="sr-cinema-kicker">{stage.index} / {stage.eyebrow}</p>
          <h3>{stage.title}</h3><p>{stage.description}</p>
          <div className="sr-cinema-chapter-steps">{stage.nodes.map((node,i)=><span key={node}><b>0{i+1}</b>{node}</span>)}</div>
          <button type="button" onClick={()=>jump(index)} className="sr-cinema-inspect">Inspect this phase <span aria-hidden="true">↗</span></button>
        </article>)}
      </div>
    </div>
    <div className="sr-cinema-lifecycle-end"><p>See the actual evidence your account is permitted to access.</p><Link href="/app/signals">Inspect delivered signals <span aria-hidden="true">↗</span></Link></div>
  </section>;
}
