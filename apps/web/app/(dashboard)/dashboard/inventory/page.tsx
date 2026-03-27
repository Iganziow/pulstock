"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { Me } from "@/lib/me";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}
function Spinner({size=14}:{size?:number}){return(<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{animation:"spin 0.7s linear infinite",display:"block",flexShrink:0}}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>);}
type Warehouse={id:number;name:string;is_active:boolean;warehouse_type?:string};
type StockRow={product_id:number;sku:string|null;name:string;category:string|null;barcode:string|null;on_hand:string};
function toNum(v:string|number|null|undefined):number{if(v==null)return NaN;const n=Number(v);return Number.isFinite(n)?n:NaN;}
function fQty(v:string):string{const n=Number(v);if(!Number.isFinite(n))return v;return n.toLocaleString("es-CL",{maximumFractionDigits:3});}
function StockChip({val}:{val:string}){
  const n=toNum(val);
  const zero=!isNaN(n)&&n<=0;
  const low=!isNaN(n)&&n>0&&n<=5;
  const color=zero?C.red:low?C.amber:C.green;
  const bg=zero?C.redBg:low?C.amberBg:C.greenBg;
  const bd=zero?C.redBd:low?C.amberBd:C.greenBd;
  return(<span style={{display:"inline-flex",padding:"2px 8px",borderRadius:99,fontSize:12,fontWeight:700,border:`1px solid ${bd}`,background:bg,color,fontVariantNumeric:"tabular-nums",fontFamily:C.mono}}>{fQty(val)}</span>);
}

const NAV_ITEMS = [
  {href:"/dashboard/inventory/kardex",label:"Kardex",icon:<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>,color:C.accent},
  {href:"/dashboard/inventory/kardex/report",label:"Reporte",icon:<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>,color:C.teal},
  {href:"/dashboard/inventory/moves",label:"Movimientos",icon:<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 014-4h14M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 01-4 4H3"/></svg>,color:C.sky},
  {href:"/dashboard/stock",label:"Stock + Ops",icon:<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>,color:C.amber},
];

export default function InventoryPage(){
  useGlobalStyles();
  const mob = useIsMobile();
  const [meErr,setMeErr]     = useState<string|null>(null);
  const [warehouses,setWhs]  = useState<Warehouse[]>([]);
  const [warehouseId,setWid] = useState<number|null>(null);
  const [q,setQ]             = useState("");
  const [items,setItems]     = useState<StockRow[]>([]);
  const [loading,setLoading] = useState(true);
  const [err,setErr]         = useState<string|null>(null);

  const activeWh=useMemo(()=>warehouses.filter(w=>w.is_active),[warehouses]);
  const whName=useMemo(()=>activeWh.find(w=>w.id===warehouseId)?.name??`#${warehouseId}`,[activeWh,warehouseId]);

  useEffect(()=>{
    (async()=>{
      setLoading(true);
      try{
        const me=(await apiFetch("/core/me/")) as Me;
        if(!me?.tenant_id){setMeErr("Sin tenant asignado.");return;}
        const whs=(await apiFetch("/core/warehouses/")) as Warehouse[];
        const list=Array.isArray(whs)?whs:[];
        setWhs(list);
        const active=list.filter(w=>w.is_active);
        if(!active.length){setMeErr("Sin bodegas activas.");return;}
        const pref=me.default_warehouse_id&&active.some(w=>w.id===me.default_warehouse_id)?me.default_warehouse_id:active[0].id;
        setMeErr(null);setWid(pref);
      }catch(e:any){setMeErr(e?.message??"Error de configuración");}
      finally{setLoading(false);}
    })();
  },[]);

  const endpoint=useMemo(()=>{
    if(!warehouseId)return null;
    const qq=q.trim();
    return qq?`/inventory/stock/?warehouse_id=${warehouseId}&q=${encodeURIComponent(qq)}`:`/inventory/stock/?warehouse_id=${warehouseId}`;
  },[warehouseId,q]);

  async function load(){
    if(!endpoint)return;
    setLoading(true);setErr(null);
    try{const data=await apiFetch(endpoint);setItems(data?.results??[]);}
    catch(e:any){setErr(e?.message??"Error cargando stock");setItems([]);}
    finally{setLoading(false);}
  }

  useEffect(()=>{if(!endpoint)return;const t=setTimeout(()=>load(),250);return()=>clearTimeout(t);},[endpoint]); // eslint-disable-line

  const metrics=useMemo(()=>{
    const zero=items.filter(r=>toNum(r.on_hand)<=0).length;
    const low=items.filter(r=>{const n=toNum(r.on_hand);return !isNaN(n)&&n>0&&n<=5;}).length;
    const units=items.reduce((a,r)=>{const n=toNum(r.on_hand);return a+(isNaN(n)||n<0?0:n);},0);
    return{total:items.length,zero,low,units};
  },[items]);

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
            <div style={{width:4,height:26,background:C.accent,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:mob?20:22,fontWeight:800,letterSpacing:"-0.04em"}}>Inventario</h1>
          </div>
          <p style={{margin:0,fontSize:13,color:C.mute,paddingLeft:14}}>Vista de stock y accesos rápidos al módulo</p>
        </div>
        <button type="button" onClick={load} disabled={loading||!!meErr||!warehouseId} className="xb"
          style={{height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.borderMd}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6}}>
          {loading?<Spinner/>:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>}
          Recargar
        </button>
      </div>

      {/* NAV SHORTCUTS */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",gap:10}}>
        {NAV_ITEMS.map(n=>(
          <Link key={n.href} href={n.href} style={{display:"flex",alignItems:"center",gap:10,padding:"12px 14px",background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,textDecoration:"none",color:C.text,boxShadow:C.sh,transition:"all 0.15s ease"}}>
            <span style={{color:n.color,flexShrink:0}}>{n.icon}</span>
            <span style={{fontSize:13,fontWeight:600}}>{n.label}</span>
          </Link>
        ))}
      </div>

      {/* STAT CARDS */}
      {!meErr&&(
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(130px,1fr))",gap:10}}>
          {[
            {label:"Productos",value:String(metrics.total),color:C.accent},
            {label:"Unidades",value:metrics.units.toLocaleString("es-CL",{maximumFractionDigits:0}),color:C.accent},
            {label:"Stock bajo",value:String(metrics.low),color:C.amber},
            {label:"Sin stock",value:String(metrics.zero),color:C.red},
          ].map(s=>(
            <div key={s.label} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,padding:"12px 16px",boxShadow:C.sh}}>
              <div style={{fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em",marginBottom:5}}>{s.label}</div>
              <div style={{fontSize:20,fontWeight:800,color:s.color,letterSpacing:"-0.03em",fontVariantNumeric:"tabular-nums"}}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {meErr&&<div style={{padding:"11px 14px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13,fontWeight:600}}>{meErr}</div>}

      {/* FILTERS */}
      <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
        {activeWh.length>1&&(
          <select value={warehouseId??""} onChange={e=>setWid(Number(e.target.value))} disabled={!!meErr}
            style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.surface,minWidth:160}}>
            {activeWh.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
        )}
        <div style={{position:"relative",flex:1,minWidth:mob?0:200,maxWidth:400}}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
            style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",pointerEvents:"none"}}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Buscar por nombre o SKU…"
            disabled={!!meErr||!warehouseId}
            style={{width:"100%",height:36,padding:"0 10px 0 32px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.surface}}/>
        </div>
        {!loading&&items.length>0&&<span style={{fontSize:12,color:C.mute}}>{items.length} productos · {whName}</span>}
      </div>

      {/* TABLE */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh,overflowX:"auto" as const}}>
        <div style={{display:"grid",gridTemplateColumns:"1fr 110px 120px 140px 110px",columnGap:12,padding:mob?"10px 12px":"10px 18px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.08em",minWidth:mob?600:undefined}}>
          <div>Producto</div><div>SKU</div><div>Categoría</div><div>Barcode</div>
          <div style={{textAlign:"right"}}>Stock</div>
        </div>

        {loading&&<div style={{padding:"48px 0",display:"flex",alignItems:"center",justifyContent:"center",gap:10,color:C.mute}}><Spinner size={16}/><span style={{fontSize:13}}>Cargando…</span></div>}
        {err&&<div style={{padding:"18px"}}><div style={{padding:"10px 12px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13}}>{err}</div></div>}
        {!loading&&!err&&items.length===0&&!meErr&&(
          <div style={{padding:"48px 24px",textAlign:"center"}}>
            <div style={{fontSize:32,marginBottom:8}}>📦</div>
            <div style={{fontSize:14,fontWeight:700,marginBottom:4}}>Sin stock para mostrar</div>
            <div style={{fontSize:13,color:C.mute,marginBottom:14}}>Ve al módulo Stock para cargar inventario inicial</div>
            <Link href="/dashboard/stock" style={{display:"inline-flex",alignItems:"center",gap:6,height:36,padding:"0 14px",borderRadius:C.r,fontSize:13,fontWeight:600,background:C.accent,color:"#fff",textDecoration:"none"}}>
              Ir a Stock →
            </Link>
          </div>
        )}

        {!loading&&!err&&items.map((r,i)=>{
          const n=toNum(r.on_hand);
          const isZero=!isNaN(n)&&n<=0;
          const isLow=!isNaN(n)&&n>0&&n<=5;
          return(
            <div key={r.product_id} className="prow" style={{display:"grid",gridTemplateColumns:"1fr 110px 120px 140px 110px",columnGap:12,padding:mob?"11px 12px":"11px 18px",borderBottom:i<items.length-1?`1px solid ${C.border}`:"none",alignItems:"center",borderLeft:isZero?`3px solid ${C.red}`:isLow?`3px solid ${C.amber}`:"3px solid transparent",minWidth:mob?600:undefined}}>
              <div>
                <div style={{fontWeight:600,fontSize:13}}>{r.name}</div>
                {(isZero||isLow)&&<div style={{fontSize:10,color:isZero?C.red:C.amber,fontWeight:700,marginTop:1}}>{isZero?"Sin stock":"Stock bajo"}</div>}
              </div>
              <div style={{fontSize:12,color:C.mid,fontFamily:C.mono}}>{r.sku??"-"}</div>
              <div style={{fontSize:12,color:C.mid}}>{r.category??"-"}</div>
              <div style={{fontSize:11,color:C.mute,fontFamily:C.mono}}>{r.barcode??"-"}</div>
              <div style={{textAlign:"right"}}><StockChip val={r.on_hand}/></div>
            </div>
          );
        })}
      </div>
    </div>
  );
}