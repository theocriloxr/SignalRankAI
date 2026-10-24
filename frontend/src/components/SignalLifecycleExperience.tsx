"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "./ui/Icon";
import { WorkspaceLink } from "./WorkspaceLink";

const stages = [
  { index:"01",slug:"sources",eyebrow:"INGEST / VERIFY",title:"Start with trustworthy inputs.",description:"A quote is only useful with its market, source, timestamp and session. Unsupported or stale data fails qualification instead of being filled in.",nodes:["Provider capability","Market session","Quote freshness"] },
  { index:"02",slug:"strategy",eyebrow:"RESEARCH / EVALUATE",title:"Find the setup. Challenge the evidence.",description:"Strategies, market structure and calibrated model context are evaluated together. A promising setup is not automatically an eligible signal.",nodes:["Strategy candidate","Model calibration","Threshold evidence"] },
  { index:"03",slug:"risk",eyebrow:"RISK / REJECT",title:"Protection before participation.",description:"Account, market and execution policies can stop the workflow. A high score never overrides missing authorization or risk information.",nodes:["Risk constraints","Account boundaries","Fail-closed decision"] },
  { index:"04",slug:"delivery",eyebrow:"DELIVER / TRACE",title:"Every signal has a history.",description:"Delivery receipts, paper observations and broker-confirmed executions are different events, and the workspace keeps them distinguishable.",nodes:["Entitled receipt","Lifecycle evidence","Outcome tracking"] },
] as const;

/** Four-gate explainer. Purely illustrative: NOT LIVE market data, no prices and no order claims. */
export function SignalLifecycleExperience() {
  const [active,setActive] = useState(0);
  const targets = useRef<(HTMLElement|null)[]>([]);
  useEffect(()=>{
    if(typeof IntersectionObserver==="undefined")return;
    const obs=new IntersectionObserver(entries=>{
      const visible=entries.filter(entry=>entry.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio)[0];
      if(visible)setActive(Number((visible.target as HTMLElement).dataset.stage||0));
    },{rootMargin:"-30% 0px -40% 0px",threshold:[0,.25,.5,.75]});
    targets.current.forEach(node=>{if(node)obs.observe(node)});
    return ()=>obs.disconnect();
  },[]);
  function jump(index:number){
    setActive(index);
    const reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    targets.current[index]?.scrollIntoView({behavior:reduced?"instant":"smooth",block:"center"});
  }
  return <section className="mk-section" id="lifecycle" aria-labelledby="mk-lifecycle-title">
    <div className="mk-container">
      <div className="mk-section-head">
        <p className="ui-eyebrow ui-eyebrow--brand">The decision engine</p>
        <h2 id="mk-lifecycle-title">From market noise to <em>accountable decisions.</em></h2>
        <p>Four gates decide whether an opportunity becomes a signal. This is a system illustration — NOT LIVE market data, and no price or order is shown.</p>
      </div>
      <div className="mk-lifecycle">
        <nav className="mk-lifecycle-nav" aria-label="Explore decision stages">{stages.map((stage,index)=>
          <button key={stage.index} type="button" onClick={()=>jump(index)} aria-current={active===index?"step":undefined}
            className={active===index?"is-active":""}>
            <span>{stage.index}</span><strong>{stage.eyebrow}</strong></button>)}</nav>
        <div className="mk-lifecycle-stages">
          {stages.map((stage,index)=><article id={"gate-"+stage.slug} data-stage={index} key={stage.index}
            data-active={active===index?"true":"false"} className="mk-stage"
            ref={node=>{targets.current[index]=node}}>
            <p className="ui-eyebrow">{stage.index} / {stage.eyebrow}</p>
            <h3>{stage.title}</h3><p>{stage.description}</p>
            <ul>{stage.nodes.map(node=><li key={node}><Icon name="check"/>{node}</li>)}</ul>
          </article>)}
          <WorkspaceLink className="ui-link" href="/app/signals">Inspect the signals delivered to your account <Icon name="arrowRight"/></WorkspaceLink>
        </div>
      </div>
    </div>
  </section>;
}
