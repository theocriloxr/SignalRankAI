"use client";

import { useEffect, useState, type FormEvent } from "react";
import client from "../lib/client";
import { display, record, rows, statusText, timeLabel, type Row } from "../lib/presentation";

type Detail = { ticket: Row; messages: Row[] };
export function SupportCenter({data,onChanged}:{data:Row;onChanged:()=>void}){
  const tickets=rows(data.tickets);
  const [selected,setSelected]=useState("");
  const [version,setVersion]=useState(0);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [detail,setDetail]=useState<Detail|null>(null);
  const [text,setText]=useState("");
  const [saving,setSaving]=useState(false);
  const [feedback,setFeedback]=useState("");

  useEffect(()=>{
    if(!selected)return;
    let cancelled=false;
    async function load(){
      setLoading(true);setError("");setDetail(null);
      try{
        const response=await client.GET("/api/v1/platform/support/tickets/{ticket_id}",{
          params:{path:{ticket_id:selected}},
        });
        if(cancelled)return;
        if(response.response.ok && response.data) {
          const result=record(response.data);
          setDetail({ticket:record(result.ticket),messages:rows(result.messages)});
        }else setError(statusText(response.response.status));
      }catch{if(!cancelled)setError("We couldn't load this conversation. Try again shortly.");}
      finally{if(!cancelled)setLoading(false);}
    }
    void load();
    return ()=>{cancelled=true};
  },[selected,version]);

  function choose(id:string) {
    if(!id)return;
    if(id===selected){setVersion(x=>x+1);return;}
    setSelected(id);setText("");setFeedback("");setError("");
  }
  async function reply(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    const message=text.trim();
    if(!selected||!detail||saving||message.length===0||message.length>20000)return;
    if(detail.ticket.status==="closed"){setFeedback("This ticket is closed.");return;}
    setSaving(true);setFeedback("");
    try{
      const response=await client.POST("/api/v1/platform/support/tickets/{ticket_id}/messages",{
        params:{path:{ticket_id:selected}},
        body:{message},
      });
      if(response.response.ok && response.data){
        setText("");
        setFeedback("Reply sent.");
        setVersion(x=>x+1);
        onChanged();
      }else setFeedback(response.response.status===409?"This ticket has been closed. Refresh to confirm.":response.response.status===401?"Sign in again to reply.":"Your reply didn't send. Try again.");
    }catch{setFeedback("We couldn't confirm your reply. Refresh to check.");}
    finally{setSaving(false);}
  }
  return <section className="ws-stack">
    <p className="ws-aside">A person on our team reads every ticket. We reply as soon as we can.</p>
    {tickets.length===0&&<div className="ui-empty"><strong>No tickets yet.</strong><p>Use the form below to ask us something.</p></div>}
    <div className="ws-split">
      {tickets.length>0&&<nav className="ws-select-list" aria-label="Your support tickets">
        {tickets.map((ticket,i)=>{
          const id=display(ticket.ticket_id,"");
          return <button className="ws-select-item" aria-pressed={id===selected}
            disabled={!id} key={id||i} type="button" onClick={()=>choose(id)}>
            <strong>{display(ticket.subject,"Support ticket")}</strong>
            <span>{display(ticket.category)} · {display(ticket.status)}</span>
            <small>Updated {timeLabel(ticket.updated_at)}</small>
          </button>;
        })}
      </nav>}
      <div className="ws-stack">
        {!selected&&tickets.length>0&&<div className="ui-empty">Pick a ticket to read and reply.</div>}
        {loading&&<div className="ui-loading" role="status">Loading…</div>}
        {error&&<div className="ui-state" role="alert"><p>{error}</p><button className="ui-btn" type="button" onClick={()=>setVersion(x=>x+1)}>Retry</button></div>}
        {detail&&!loading&&<section className="ui-card">
          <p className="ui-eyebrow">{display(detail.ticket.priority,"Standard")} priority</p>
          <h2>{display(detail.ticket.subject)}</h2>
          <p>State: <strong>{display(detail.ticket.status)}</strong> · Created {timeLabel(detail.ticket.created_at)}</p>
          <div className="ws-thread">
            {detail.messages.length===0&&<p>No messages yet.</p>}
            {detail.messages.map((message,i)=><article className="ws-message" key={display(message.message_id,String(i))}>
              <div className="ui-pagination"><strong>{message.author_role==="user"?"Your message":"Support team"}</strong><small>{timeLabel(message.created_at)}</small></div>
              <p>{display(message.message,"Message unavailable")}</p>
            </article>)}
          </div>
          {detail.ticket.status!=="closed"&&<form className="ui-form" onSubmit={reply}>
            <label className="ui-field">Reply to this ticket<textarea className="ui-textarea" value={text} onChange={e=>setText(e.target.value)} maxLength={20000} rows={5} required placeholder="What happened, and what did you expect?"/></label>
            <button type="submit" className="ui-btn ui-btn--primary" disabled={saving||!text.trim()}>{saving?"Sending…":"Send reply"}</button>
            <p>Please don&rsquo;t send passwords, API keys, one-time codes or card details here.</p>
          </form>}
          {detail.ticket.status==="closed"&&<p className="ui-notice ui-notice--neutral">This ticket is closed. Open a new one if you need more help.</p>}
          {feedback&&<p role="status" className="ui-feedback">{feedback}</p>}
        </section>}
      </div>
    </div>
  </section>;
}
