"use client";

import { useState, type FormEvent } from "react";
import client from "../lib/client";

/** Account-owned CRUD using only the canonical cookie+CSRF transport.
 * No broker orders, payments, trading-profile or safety controls. */
export function AccountCreation({ kind, onCreated }: {
  kind: "watchlists" | "support" | "journal";
  onCreated: () => void;
}) {
  const [saving,setSaving]=useState(false);
  const [feedback,setFeedback]=useState<{success:boolean;message:string}|null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if(saving)return;
    const form=event.currentTarget;
    const values=new FormData(form);
    setSaving(true);setFeedback(null);
    try {
      const response=kind==="watchlists"
        ? await client.POST("/api/v1/platform/watchlists",{
          body:{name:String(values.get("name")||"").trim()},
        })
        :kind==="support"
        ? await client.POST("/api/v1/platform/support/tickets",{
          body:{
            subject:String(values.get("subject")||"").trim(),
            message:String(values.get("message")||"").trim(),
            category:String(values.get("category")||"general"),
          },
        })
        : await client.POST("/api/v1/platform/journal",{
          body:{
            title:String(values.get("title")||"").trim()||null,
            notes:String(values.get("notes")||"").trim(),
          },
        });
      if (response.response.ok && response.data) {
        setFeedback({success:true,message:kind==="watchlists"?"Watchlist created in your account.":kind==="support"?"Support ticket submitted.":"Journal entry saved."});
        form.reset();
        onCreated();
      } else {
        setFeedback({success:false,message:response.response.status===401
          ?"Your session expired. Sign in to save changes."
          :response.response.status===403?"Your plan does not permit this action."
          :response.response.status===409?"A record with this name already exists."
          :response.response.status===429?"The service is rate limiting new requests. Retry later."
          :"No record was confirmed saved. Check the details and retry."});
      }
    } catch {
      setFeedback({success:false,message:"The service could not be reached. Nothing has been confirmed saved."});
    } finally {setSaving(false);}
  }
  const title=kind==="watchlists"?"New watchlist":kind==="support"?"Create a support ticket":"Add journal entry";
  return <section className="ui-card">
    <h2>{title}</h2>
    <p>Saved records are linked to the signed-in account. This form never authorizes broker execution.</p>
    <form onSubmit={submit} className="ui-form">
      {kind==="watchlists" ? <label className="ui-field">Watchlist name
        <input className="ui-input" name="name" required minLength={2} maxLength={90} placeholder="e.g. FX session watch" />
      </label> :kind==="support"?<>
        <label className="ui-field">Subject<input className="ui-input" name="subject" required minLength={5} maxLength={160}/></label>
        <label className="ui-field">Category<select className="ui-select" name="category" defaultValue="general">
          <option value="general">General</option><option value="technical">Technical issue</option><option value="billing">Billing</option><option value="account">Account access</option>
        </select></label>
        <label className="ui-field">Details<textarea className="ui-textarea" name="message" required minLength={10} maxLength={5000} rows={5}/></label>
      </>:<>
        <label className="ui-field">Title (optional)<input className="ui-input" name="title" maxLength={180}/></label>
        <label className="ui-field">Notes<textarea className="ui-textarea" name="notes" required minLength={2} maxLength={5000} rows={6}/></label>
      </>}
      <button type="submit" className="ui-btn ui-btn--primary" disabled={saving}>{saving?"Saving…":kind==="watchlists"?"Create watchlist":kind==="support"?"Send ticket":"Save journal entry"}</button>
    </form>
    {feedback&&<p className={feedback.success?"ui-feedback":"ui-feedback ui-feedback--error"} role={feedback.success?"status":"alert"}>{feedback.message}</p>}
  </section>;
}
