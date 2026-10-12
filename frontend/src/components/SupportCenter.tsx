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
      }catch{if(!cancelled)setError("Ticket messages could not be verified. Retry shortly.");}
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
    if(detail.ticket.status==="closed"){setFeedback("The ticket is closed. Replies are unavailable.");return;}
    setSaving(true);setFeedback("");
    try{
      const response=await client.POST("/api/v1/platform/support/tickets/{ticket_id}/messages",{
        params:{path:{ticket_id:selected}},
        body:{message},
      });
      if(response.response.ok && response.data){
        setText("");
        setFeedback("Your reply was accepted by the support service.");
        setVersion(x=>x+1);
        onChanged();
      }else setFeedback(response.response.status===409?"This ticket has been closed. Refresh to confirm.":response.response.status===401?"Sign in again to reply.":"The message was not confirmed sent. Retry.");
    }catch{setFeedback("The service could not confirm the reply. Please retry.");}
    finally{setSaving(false);}
  }
  return <section className="sr-view-stack">
    <p className="sr-risk-note">Tickets and messages are retrieved for the signed-in account only. Ticket status comes from the support service; no response time is promised.</p>
    {tickets.length===0&&<div className="sr-empty"><strong>No account support tickets returned.</strong><p>Use the form below to open a new request.</p></div>}
    <div className="sr-support-layout">
      {tickets.length>0&&<nav className="sr-support-list" aria-label="Your support tickets">
        {tickets.map((ticket,i)=>{
          const id=display(ticket.ticket_id,"");
          return <button className={id===selected?"sr-support-ticket active":"sr-support-ticket"} aria-pressed={id===selected}
            disabled={!id} key={id||i} type="button" onClick={()=>choose(id)}>
            <strong>{display(ticket.subject,"Support ticket")}</strong>
            <span>{display(ticket.category)} · {display(ticket.status)}</span>
            <small>Updated {timeLabel(ticket.updated_at)}</small>
          </button>;
        })}
      </nav>}
      <div className="sr-support-detail">
        {!selected&&tickets.length>0&&<div className="sr-empty">Select a ticket to review its message history and reply.</div>}
        {loading&&<div className="sr-loading" role="status">Retrieving the selected account ticket…</div>}
        {error&&<div className="sr-access-state" role="alert"><p>{error}</p><button className="sr-secondary-action" type="button" onClick={()=>setVersion(x=>x+1)}>Retry</button></div>}
        {detail&&!loading&&<section className="sr-data-panel">
          <p className="sr-overline">Account ticket / {display(detail.ticket.priority,"Standard")}</p>
          <h2>{display(detail.ticket.subject)}</h2>
          <p>State: <strong>{display(detail.ticket.status)}</strong> · Created {timeLabel(detail.ticket.created_at)}</p>
          <div className="sr-support-messages">
            {detail.messages.length===0&&<p>No messages returned for this ticket.</p>}
            {detail.messages.map((message,i)=><article className="sr-support-message" key={display(message.message_id,String(i))}>
              <div className="sr-list-actions"><strong>{message.author_role==="user"?"Your message":"Support team"}</strong><small>{timeLabel(message.created_at)}</small></div>
              <p>{display(message.message,"Message unavailable")}</p>
            </article>)}
          </div>
          {detail.ticket.status!=="closed"&&<form className="sr-create-form" onSubmit={reply}>
            <label>Reply to this ticket<textarea value={text} onChange={e=>setText(e.target.value)} maxLength={20000} rows={5} required placeholder="Describe what happened and any relevant non-sensitive details."/></label>
            <button type="submit" className="button" disabled={saving||!text.trim()}>{saving?"Sending…":"Send reply"}</button>
            <p>Avoid sending passwords, broker API keys, one-time codes or card data in a support message.</p>
          </form>}
          {detail.ticket.status==="closed"&&<p className="sr-risk-note">This ticket is closed and cannot receive new replies.</p>}
          {feedback&&<p role="status" className="sr-submit-feedback">{feedback}</p>}
        </section>}
      </div>
    </div>
  </section>;
}
