"use client";

import { useEffect, useRef, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { Icon } from "./ui/Icon";

/** Native semantic disclosure used for the mobile menus.
 * Closes on route change, outside touch, link activation, Escape and desktop resize. */
export function ResponsiveDisclosure({
  children, className, id, label, desktopFrom = 1024,
}:{
  children:ReactNode; className:string; id?:string; label:string; desktopFrom?:number;
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
      // The desktop layout has its own navigation; never keep an invisible open drawer.
      if(window.innerWidth>=desktopFrom && menu.current)menu.current.open=false;
    }
    document.addEventListener("pointerdown",outside,true);
    window.addEventListener("resize",viewport);
    return ()=>{
      document.removeEventListener("pointerdown",outside,true);
      window.removeEventListener("resize",viewport);
    };
  },[desktopFrom]);

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
    <summary ref={summary} aria-label={label}><Icon name="menu"/><span>Menu</span></summary>
    <div className="disclosure-panel">{children}</div>
  </details>;
}
