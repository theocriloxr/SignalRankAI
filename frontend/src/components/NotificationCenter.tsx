"use client";

import { useState } from "react";
import client from "../lib/client";
import { display, rows, timeLabel, type Row } from "../lib/presentation";

function NotificationRecord({item,refresh}:{item:Row;refresh:()=>void}) {
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const id=display(item.notification_id,"");
  const unread=item.read_at===null||item.read_at===undefined;
  async function markRead(){
    if(!id||busy||!unread)return;
    setBusy(true);setMessage("");
    try{
      const result=await client.POST("/api/v1/platform/notifications/{notification_id}/read",{
        params:{path:{notification_id:id}},
      });
      if(result.response.ok && result.data && result.data.read===true){
        refresh();
      }else setMessage(result.response.status===401?"Sign in again to update this notification.":"Read status was not confirmed. Try again.");
    }catch{setMessage("Unable to confirm the update. Try again.");}
    finally{setBusy(false);}
  }
  return <article className="ws-note">
    <div className="ws-note-head">
      <div>
        <p className="ui-eyebrow">{display(item.event_type,"Notification")} / {display(item.severity,"Unclassified")}</p>
        <h3>{display(item.title,"Account notification")}</h3>
      </div>
      <span className="ui-badge">{unread?"UNREAD":"READ"}</span>
    </div>
    <p>{display(item.body,"No additional message was provided.")}</p>
    <footer><span>{timeLabel(item.created_at)}</span>
      {unread&&<button type="button" className="ui-btn" disabled={busy||!id} onClick={markRead}>{busy?"Updating…":"Mark as read"}</button>}
    </footer>
    {message&&<p role="alert" className="ui-feedback ui-feedback--error">{message}</p>}
  </article>;
}

export function NotificationCenter({data,onChanged}:{data:Row;onChanged:()=>void}){
  const [unreadOnly,setUnreadOnly]=useState(false);
  const notifications=rows(data.notifications);
  const visible=unreadOnly?notifications.filter(n=>n.read_at==null):notifications;
  return <section className="ws-stack" aria-label="Account notifications">
    <p className="ui-notice ui-notice--neutral">This lists the most recent account notifications from the canonical service. Notification receipt does not certify trade execution, P&amp;L or delivery to another channel.</p>
    <div className="ui-pagination">
      <span>{notifications.length} recent records · {notifications.filter(n=>n.read_at==null).length} unread in this view</span>
      <button className="ui-btn" type="button" onClick={()=>setUnreadOnly(v=>!v)} aria-pressed={unreadOnly}>{unreadOnly?"Show recent notifications":"Show unread in this view"}</button>
    </div>
    {visible.length?<div className="ws-cards">{visible.map((item,i)=><NotificationRecord key={display(item.notification_id,String(i))} item={item} refresh={onChanged}/>)}</div>
     : <div className="ui-empty"><strong>No {unreadOnly?"unread":"recent"} notifications returned.</strong><p>This display is based on the backend&apos;s latest returned records, not a global audit of notification delivery.</p></div>}
  </section>;
}
