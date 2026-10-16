"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import client from "../lib/client";
import { record } from "../lib/presentation";

/** Presentation only; the backend enforces owner/admin authorization on every request. */
export function OperationsNavLink({ active }: { active: boolean }) {
  const [permitted,setPermitted]=useState(false);
  useEffect(()=>{
    let cancelled=false;
    void client.GET("/api/v1/platform/me").then(({data,response})=>{
      if(cancelled || !response.ok)return;
      const user=record(record(data).user);
      const authority=String(user.authority||"").toUpperCase();
      setPermitted(authority==="OWNER"||authority==="ADMIN");
    }).catch(()=>{ if(!cancelled)setPermitted(false); });
    return ()=>{cancelled=true};
  },[]);
  if(!permitted)return null;
  return <Link href="/app/operations" aria-current={active?"page":undefined}
    className={active?"active":undefined}>Operations</Link>;
}
