"use client";

import { useEffect, useRef, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { usePathname } from "next/navigation";

/** Native semantic disclosure with reliable touch, routing and keyboard closure.
 * Navigation remains server-renderable and works without hover/canvas. */
export function ResponsiveDisclosure({
  children, className, id, label,
}:{
  children:ReactNode; className:string; id?:string; label:string;
}){
  const pathname=usePathname();
  const menu=useRef<HTMLDetailsElement>(null);
  const summary=useRef<HTMLElement>(null);

  useEffect(()=>{
    const element=menu.current;
    if(element)element.open=false;
  },[pathname]);

  useEffect(()=>{
    function outside(event:PointerEvent){
      const el=menu.current;
      if(el?.open && event.target instanceof Node && !el.contains(event.target))el.open=false;
    }
    function viewport(){
      // Both desktop navigation versions have dedicated alternatives.
      // Never preserve an invisible open disclosure after breakpoint changes.
      if(window.innerWidth>1120 && menu.current)menu.current.open=false;
    }
    document.addEventListener("pointerdown",outside,true);
    window.addEventListener("resize",viewport);
    return ()=>{
      document.removeEventListener("pointerdown",outside,true);
      window.removeEventListener("resize",viewport);
    };
  },[]);

  function onKeyDown(event:KeyboardEvent<HTMLDetailsElement>){
    if(event.key!=="Escape"||!menu.current?.open)return;
    event.stopPropagation();
    menu.current.open=false;
    summary.current?.focus();
  }
  function onClick(event:MouseEvent<HTMLDetailsElement>){
    const el=event.target;
    if(el instanceof Element && el.closest("a[href]") && menu.current) menu.current.open=false;
  }
  return <details className={className} id={id} ref={menu} onKeyDown={onKeyDown} onClickCapture={onClick}>
    <summary ref={summary}>{label}</summary>
    <div className="sr-responsive-disclosure-content">{children}</div>
  </details>;
}
