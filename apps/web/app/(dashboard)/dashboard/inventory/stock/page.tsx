"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import type { Me } from "@/lib/me";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { Spinner } from "@/components/ui";
import { useIsMobile } from "@/hooks/useIsMobile";
type Warehouse={id:number;name:string;is_active:boolean;warehouse_type?:string};
type StockRow={product_id:number;sku:string|null;name:string;category:string|null;barcode:string|null;on_hand:string;avg_cost?:string|null};
function toNum(v:string|number|null|undefined):number{if(v==null)return NaN;const n=Number(v);return Number.isFinite(n)?n:NaN;}
function fQty(v:string):string{const n=Number(v);if(!Number.isFinite(n))return v;return n.toLocaleString("es-CL",{maximumFractionDigits:3});}
function sanitizePos(v:string):string{const c=v.replace(/[^0-9.]/g,"");const p=c.split(".");return p.length<=2?c:`${p[0]}.${p.slice(1).join("")}`;}
function sanitizeDelta(v:string):string{let c=v.replace(/[^0-9.\-]/g,"");c=c.replace(/(?!^)-/g,"");const p=c.split(".");return p.length<=2?c:`${p[0]}.${p.slice(1).join("")}`;}

type BtnV="primary"|"secondary"|"ghost"|"danger"|"success"|"teal"|"sky"|"violet";
function Btn({children,onClick,variant="secondary",disabled,size="md",full}:{children:React.ReactNode;onClick?:()=>void;variant?:BtnV;disabled?:boolean;size?:"sm"|"md"|"lg";full?:boolean;}){
  const vs:Record<BtnV,React.CSSProperties>={
    primary:{background:C.accent,color:"#fff",border:`1px solid ${C.accent}`},
    secondary:{background:C.surface,color:C.text,border:`1px solid ${C.borderMd}`},
    ghost:{background:"transparent",color:C.mid,border:"1px solid transparent"},
    danger:{background:C.redBg,color:C.red,border:`1px solid ${C.redBd}`},
    success:{background:C.greenBg,color:C.green,border:`1px solid ${C.greenBd}`},
    teal:{background:C.tealBg,color:C.teal,border:`1px solid ${C.tealBd}`},
    sky:{background:C.skyBg||"#F0F9FF",color:C.sky||"#0EA5E9",border:`1px solid ${C.skyBd||"#BAE6FD"}`},
    violet:{background:"#F5F3FF",color:"#7C3AED",border:"1px solid #DDD6FE"},
  };
  const h=size==="lg"?46:size==="sm"?30:38;
  const px=size==="lg"?"0 20px":size==="sm"?"0 10px":"0 14px";
  const fs=size==="lg"?14:size==="sm"?11:13;
  return(<button type="button" onClick={onClick} disabled={disabled} className="xb" style={{...vs[variant],display:"inline-flex",alignItems:"center",justifyContent:"center",gap:6,height:h,padding:px,borderRadius:C.r,fontSize:fs,fontWeight:600,letterSpacing:"0.01em",whiteSpace:"nowrap",width:full?"100%":undefined}}>{children}</button>);
}

function StockBadge({val}:{val:string}){
  const n=toNum(val);
  const low=!isNaN(n)&&n<=5;
  const zero=!isNaN(n)&&n<=0;
  const color=zero?C.red:low?C.amber:C.green;
  const bg=zero?C.redBg:low?C.amberBg:C.greenBg;
  const bd=zero?C.redBd:low?C.amberBd:C.greenBd;
  return(
    <span style={{display:"inline-flex",alignItems:"center",gap:4,padding:"2px 8px",borderRadius:99,fontSize:12,fontWeight:700,border:`1px solid ${bd}`,background:bg,color,fontVariantNumeric:"tabular-nums",fontFamily:C.mono}}>
      {fQty(val)}
    </span>
  );
}

// ─── Modal wrapper ────────────────────────────────────────────────────────────
function Modal({title,subtitle,onClose,disabled,accentColor,children}:{title:string;subtitle?:string;onClose:()=>void;disabled?:boolean;accentColor?:string;children:React.ReactNode;}){
  return(
    <div className="bd-in" onMouseDown={e=>{if(e.target===e.currentTarget&&!disabled)onClose();}}
      style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.4)",display:"grid",placeItems:"center",padding:20,zIndex:60}}>
      <div className="m-in" style={{width:"min(520px,100%)",background:C.surface,borderRadius:C.rLg,border:`1px solid ${C.border}`,boxShadow:C.shLg,overflow:"hidden"}}>
        <div style={{height:3,background:accentColor??C.accent}}/>
        <div style={{padding:"18px 22px"}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:14}}>
            <div>
              <div style={{fontSize:15,fontWeight:700,color:C.text}}>{title}</div>
              {subtitle&&<div style={{fontSize:12,color:C.mute,marginTop:3}}>{subtitle}</div>}
            </div>
            <button onClick={onClose} disabled={disabled} className="xb" style={{width:28,height:28,borderRadius:C.r,border:`1px solid ${C.border}`,background:C.bg,color:C.mute,fontSize:15,display:"flex",alignItems:"center",justifyContent:"center"}}>✕</button>
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}

function ProductCard({row}:{row:StockRow}){
  return(
    <div style={{padding:"10px 12px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.bg,marginBottom:14}}>
      <div style={{fontWeight:700,fontSize:14}}>{row.name}</div>
      <div style={{display:"flex",gap:16,marginTop:4,fontSize:12,color:C.mute}}>
        {row.sku&&<span>SKU: <span style={{fontFamily:C.mono,color:C.mid}}>{row.sku}</span></span>}
        {row.barcode&&<span>Barcode: <span style={{fontFamily:C.mono,color:C.mid}}>{row.barcode}</span></span>}
        <span>Stock: <span style={{fontWeight:700,color:C.text,fontFamily:C.mono}}>{fQty(row.on_hand)}</span></span>
      </div>
    </div>
  );
}

function FieldGroup({label,children,hint,err}:{label:string;children:React.ReactNode;hint?:string;err?:string|null;}){
  return(
    <div style={{display:"flex",flexDirection:"column",gap:5}}>
      <label style={{fontSize:11,fontWeight:700,color:C.mid,textTransform:"uppercase",letterSpacing:"0.06em"}}>{label}</label>
      {children}
      {hint&&!err&&<div style={{fontSize:11,color:C.mute}}>{hint}</div>}
      {err&&<div style={{fontSize:11,color:C.red,fontWeight:600}}>{err}</div>}
    </div>
  );
}

function iS(extra?:React.CSSProperties):React.CSSProperties{
  return{width:"100%",height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.surface,...extra};
}

function ErrBanner({msg,onClose}:{msg:string;onClose:()=>void}){
  return(
    <div style={{padding:"10px 12px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13,display:"flex",gap:8,alignItems:"center",marginTop:12}}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{flexShrink:0}}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/></svg>
      <span style={{flex:1}}>{msg}</span>
      <button onClick={onClose} className="xb" style={{background:"none",border:"none",color:C.red,fontSize:15,cursor:"pointer",padding:0,lineHeight:1}}>✕</button>
    </div>
  );
}

function OkBanner({msg}:{msg:string}){
  return(
    <div style={{padding:"10px 12px",borderRadius:C.r,border:`1px solid ${C.greenBd}`,background:C.greenBg,color:C.green,fontSize:13,display:"flex",gap:8,alignItems:"center",marginTop:12}}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{flexShrink:0}}><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      {msg}
    </div>
  );
}

// ─── Preview row ──────────────────────────────────────────────────────────────
function PreviewRow({label,value,highlight}:{label:string;value:string;highlight?:boolean}){
  return(
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
      <span style={{fontSize:12,color:C.mute}}>{label}</span>
      <span style={{fontSize:14,fontWeight:700,fontVariantNumeric:"tabular-nums",fontFamily:C.mono,color:highlight?C.accent:C.text}}>{value}</span>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function StockPage(){
  useGlobalStyles();
  const mob = useIsMobile();
  const router=useRouter();

  const [meErr,setMeErr]   = useState<string|null>(null);
  const [warehouses,setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId,setWarehouseId] = useState<number|null>(null);
  const [q,setQ]           = useState("");
  const [page,setPage]     = useState(1);
  const [totalCount,setTotalCount] = useState(0);
  const [items,setItems]   = useState<StockRow[]>([]);
  const [loading,setLoading] = useState(true);
  const [err,setErr]       = useState<string|null>(null);
  const [okMsg,setOkMsg]   = useState<string|null>(null);

  const activeWh = useMemo(()=>warehouses.filter(w=>w.is_active),[warehouses]);
  const whName   = useMemo(()=>activeWh.find(w=>w.id===warehouseId)?.name??`#${warehouseId}`,[activeWh,warehouseId]);

  // ── selected row for modals ───────────────────────────────────────────────
  const [sel,setSel] = useState<StockRow|null>(null);

  // ── ADJUST ───────────────────────────────────────────────────────────────
  const [adjOpen,setAdjOpen]   = useState(false);
  const [adjQty,setAdjQty]     = useState("");
  const [adjCost,setAdjCost]   = useState("");
  const [adjNote,setAdjNote]   = useState("Ajuste manual");
  const [adjBusy,setAdjBusy]   = useState(false);
  const [adjErr,setAdjErr]     = useState<string|null>(null);

  // ── RECEIVE ───────────────────────────────────────────────────────────────
  const [recOpen,setRecOpen]   = useState(false);
  const [recQty,setRecQty]     = useState("");
  const [recCost,setRecCost]   = useState("");
  const [recNote,setRecNote]   = useState("Recepción");
  const [recBusy,setRecBusy]   = useState(false);
  const [recErr,setRecErr]     = useState<string|null>(null);

  // ── ISSUE ─────────────────────────────────────────────────────────────────
  const [issOpen,setIssOpen]   = useState(false);
  const [issQty,setIssQty]     = useState("");
  const [issReason,setIssReason] = useState<"MERMA"|"VENCIDO"|"USO_INTERNO"|"OTRO">("MERMA");
  const [issNote,setIssNote]   = useState("Salida");
  const [issBusy,setIssBusy]   = useState(false);
  const [issErr,setIssErr]     = useState<string|null>(null);

  // ── TRANSFER ──────────────────────────────────────────────────────────────
  const [trOpen,setTrOpen]     = useState(false);
  const [trProdId,setTrProdId] = useState<number|null>(null);
  const [trTarget,setTrTarget] = useState<number|null>(null);
  const [trQty,setTrQty]       = useState("");
  const [trNote,setTrNote]     = useState("Transferencia");
  const [trBusy,setTrBusy]     = useState(false);
  const [trErr,setTrErr]       = useState<string|null>(null);

  const anyBusy = adjBusy||recBusy||issBusy||trBusy;

  // ESC to close
  useEffect(()=>{
    function onKey(e:KeyboardEvent){if(e.key!=="Escape"||anyBusy)return;setAdjOpen(false);setRecOpen(false);setIssOpen(false);setTrOpen(false);}
    window.addEventListener("keydown",onKey);return()=>window.removeEventListener("keydown",onKey);
  },[anyBusy]);

  // reset on warehouse change
  useEffect(()=>{setAdjOpen(false);setRecOpen(false);setIssOpen(false);setTrOpen(false);setSel(null);},[warehouseId]);

  // boot
  useEffect(()=>{
    (async()=>{
      setLoading(true);
      try{
        const me=(await apiFetch("/core/me/")) as Me;
        if(!me?.tenant_id){setMeErr("Tu usuario no tiene tenant asignado.");return;}
        const whs=(await apiFetch("/core/warehouses/")) as Warehouse[];
        const list=Array.isArray(whs)?whs:[];
        setWarehouses(list);
        const active=list.filter(w=>w.is_active);
        if(!active.length){setMeErr("No tienes bodegas activas.");return;}
        const preferred=me.default_warehouse_id&&active.some(w=>w.id===me.default_warehouse_id)?me.default_warehouse_id:active[0].id;
        setMeErr(null);setWarehouseId(preferred);
      }catch(e:any){setMeErr(e?.message??"No se pudo cargar configuración.");}
      finally{setLoading(false);}
    })();
  },[]);

  const endpoint=useMemo(()=>{
    if(!warehouseId)return null;
    const qq=q.trim();
    const params=new URLSearchParams();
    params.set("warehouse_id",String(warehouseId));
    params.set("page",String(page));
    if(qq)params.set("q",qq);
    return `/inventory/stock/?${params.toString()}`;
  },[warehouseId,q,page]);

  // Reset page on search or warehouse change
  useEffect(()=>{setPage(1);},[q,warehouseId]);

  async function load(){
    if(!endpoint)return;
    setLoading(true);setErr(null);
    try{
      const data=await apiFetch(endpoint);
      setItems(data?.results??[]);
      setTotalCount(data?.count??data?.results?.length??0);
    }
    catch(e:any){setErr(e?.message??"Error cargando stock");setItems([]);setTotalCount(0);}
    finally{setLoading(false);}
  }

  useEffect(()=>{if(!endpoint)return;const t=setTimeout(()=>load(),250);return()=>clearTimeout(t);},[endpoint]); // eslint-disable-line

  function showOk(msg:string){setOkMsg(msg);setTimeout(()=>setOkMsg(null),3500);}

  function openAdj(r:StockRow){setSel(r);setAdjQty("");setAdjCost("");setAdjNote("Ajuste manual");setAdjErr(null);setAdjOpen(true);}
  function openRec(r:StockRow){setSel(r);setRecQty("");setRecCost("");setRecNote("Recepción");setRecErr(null);setRecOpen(true);}
  function openIss(r:StockRow){setSel(r);setIssQty("");setIssReason("MERMA");setIssNote("Salida");setIssErr(null);setIssOpen(true);}
  function openTr(){
    setSel(null);setTrProdId(null);setTrQty("");setTrNote("Transferencia");setTrErr(null);
    const other=activeWh.find(w=>w.id!==warehouseId)??null;
    setTrTarget(other?.id??null);setTrOpen(true);
  }

  // ── previews ─────────────────────────────────────────────────────────────
  const onHand=toNum(sel?.on_hand??"");
  const adjDelta=toNum(adjQty);
  const adjEst=!isNaN(onHand)&&!isNaN(adjDelta)?onHand+adjDelta:NaN;
  const adjNeg=!isNaN(adjEst)&&adjEst<0;
  // allow qty=0 when only changing cost; require at least one of delta!=0 or cost filled
  const adjOk=!isNaN(adjDelta)&&!adjNeg&&(adjDelta!==0||adjCost.trim()!=="");

  const recQtyN=toNum(recQty);
  const recCostN=recCost.trim()?toNum(recCost):0;
  const recOk=!isNaN(recQtyN)&&recQtyN>0&&(!recCost.trim()||(!isNaN(recCostN)&&recCostN>=0));

  const issQtyN=toNum(issQty);
  const issEst=!isNaN(onHand)&&!isNaN(issQtyN)?onHand-issQtyN:NaN;
  const issNeg=!isNaN(issEst)&&issEst<0;
  const issOk=!isNaN(issQtyN)&&issQtyN>0&&!issNeg;

  const trQtyN=toNum(trQty);
  const trOk=!isNaN(trQtyN)&&trQtyN>0&&!!trTarget&&trTarget!==warehouseId&&!!trProdId;

  // ── submit handlers ───────────────────────────────────────────────────────
  async function submitAdj(){
    if(!adjOk||!sel||!warehouseId)return;
    setAdjBusy(true);setAdjErr(null);
    try{
      const adjCostN=adjCost.trim()?toNum(adjCost):null;
      const body:Record<string,unknown>={warehouse_id:warehouseId,product_id:sel.product_id,qty:adjDelta,note:adjNote};
      if(adjCostN!==null&&!isNaN(adjCostN)&&adjCostN>=0)body.new_avg_cost=adjCostN;
      await apiFetch("/inventory/adjust/",{method:"POST",body:JSON.stringify(body)});
      await load();setAdjOpen(false);showOk(`Ajuste aplicado en ${sel.name}`);
    }catch(e:any){setAdjErr(e?.message??"No se pudo ajustar.");}
    finally{setAdjBusy(false);}
  }

  async function submitRec(){
    if(!recOk||!sel||!warehouseId)return;
    setRecBusy(true);setRecErr(null);
    try{
      await apiFetch("/inventory/receive/",{method:"POST",body:JSON.stringify({warehouse_id:warehouseId,product_id:sel.product_id,qty:String(recQtyN),unit_cost:recCost.trim()?String(recCostN):null,note:recNote})});
      await load();setRecOpen(false);showOk(`Recepción de ${recQtyN} × ${sel.name}`);
    }catch(e:any){setRecErr(e?.message??"No se pudo recibir.");}
    finally{setRecBusy(false);}
  }

  async function submitIss(){
    if(!issOk||!sel||!warehouseId)return;
    setIssBusy(true);setIssErr(null);
    try{
      await apiFetch("/inventory/issue/",{method:"POST",body:JSON.stringify({warehouse_id:warehouseId,product_id:sel.product_id,qty:String(issQtyN),reason:issReason,note:issNote})});
      await load();setIssOpen(false);showOk(`Salida de ${issQtyN} × ${sel.name}`);
    }catch(e:any){setIssErr(e?.message??"No se pudo egresar.");}
    finally{setIssBusy(false);}
  }

  async function submitTr(){
    if(!trOk||!warehouseId||!trTarget||!trProdId)return;
    setTrBusy(true);setTrErr(null);
    try{
      const resp=await apiFetch("/inventory/transfer/",{method:"POST",body:JSON.stringify({from_warehouse_id:warehouseId,to_warehouse_id:trTarget,lines:[{product_id:trProdId,qty:String(trQtyN),note:trNote}]})}) as any;
      setTrOpen(false);
      const tid=resp?.transfer_id??resp?.id??null;
      if(tid){router.push(`/dashboard/inventory/transfers/${tid}`);return;}
      await load();
    }catch(e:any){setTrErr(e?.message??"No se pudo transferir.");}
    finally{setTrBusy(false);}
  }

  // ─── metrics ────────────────────────────────────────────────────────────
  const metrics=useMemo(()=>{
    const total=items.length;
    const low=items.filter(r=>{const n=toNum(r.on_hand);return !isNaN(n)&&n>0&&n<=5;}).length;
    const zero=items.filter(r=>toNum(r.on_hand)<=0).length;
    const totalUnits=items.reduce((a,r)=>{const n=toNum(r.on_hand);return a+(isNaN(n)?0:n);},0);
    return{total,low,zero,totalUnits};
  },[items]);

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
            <div style={{width:4,height:26,background:C.accent,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:22,fontWeight:800,letterSpacing:"-0.04em"}}>Stock actual</h1>
            <span style={{fontSize:12,color:C.mute,fontWeight:500,padding:"2px 8px",borderRadius:99,border:`1px solid ${C.border}`,background:C.surface}}>{whName}</span>
          </div>
          <p style={{margin:0,fontSize:13,color:C.mute,paddingLeft:14}}>Stock teórico (on_hand) por bodega</p>
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          <Btn variant="danger" size="sm" onClick={()=>router.push("/dashboard/inventory/salidas")} disabled={!!meErr||!warehouseId}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12l7 7 7-7"/></svg>
            Salida masiva
          </Btn>
          {activeWh.length>=2&&(
            <Btn variant="sky" size="sm" onClick={openTr} disabled={!!meErr||!warehouseId||loading}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
              Transferir
            </Btn>
          )}
          <Btn variant="secondary" size="sm" onClick={load} disabled={loading||!!meErr||!warehouseId}>
            {loading?<Spinner/>:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>}
            Recargar
          </Btn>
        </div>
      </div>

      {/* OK banner */}
      {okMsg&&<OkBanner msg={okMsg}/>}

      {/* meErr */}
      {meErr&&<div style={{padding:"11px 14px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13,fontWeight:600}}>{meErr}</div>}

      {/* STAT CARDS */}
      {!meErr&&(
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(140px,1fr))",gap:10}}>
          {[
            {label:"Productos",value:String(metrics.total),color:C.accent,sub:"en bodega"},
            {label:"Unidades tot.",value:metrics.totalUnits.toLocaleString("es-CL",{maximumFractionDigits:0}),color:C.accent,sub:"on_hand total"},
            {label:"Stock bajo",value:String(metrics.low),color:C.amber,sub:"≤ 5 unidades"},
            {label:"Sin stock",value:String(metrics.zero),color:C.red,sub:"on_hand = 0"},
          ].map(s=>(
            <div key={s.label} style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,padding:"12px 16px",boxShadow:C.sh}}>
              <div style={{fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em",marginBottom:6}}>{s.label}</div>
              <div style={{fontSize:20,fontWeight:800,color:s.color,letterSpacing:"-0.03em",fontVariantNumeric:"tabular-nums"}}>{s.value}</div>
              <div style={{fontSize:11,color:C.mute,marginTop:3}}>{s.sub}</div>
            </div>
          ))}
        </div>
      )}

      {/* FILTERS */}
      <div style={{display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
        {activeWh.length>1&&(
          <select value={warehouseId??""} onChange={e=>setWarehouseId(Number(e.target.value))} disabled={!!meErr||loading}
            style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.surface,minWidth:160}}>
            {activeWh.map(w=><option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
          </select>
        )}
        <div style={{position:"relative",flex:1,minWidth:220,maxWidth:440}}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
            style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",pointerEvents:"none"}}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Buscar por nombre o SKU…"
            style={{width:"100%",height:36,padding:"0 10px 0 34px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.surface}}
            disabled={!!meErr||!warehouseId}/>
        </div>
      </div>

      {/* TABLE */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
       <div style={{overflowX:"auto"}}>
        <div style={{display:"grid",gridTemplateColumns:"1fr 100px 110px 130px 100px 110px 200px",columnGap:12,padding:"10px 18px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.08em",minWidth:mob?800:undefined}}>
          <div>Producto</div><div>SKU</div><div>Categoría</div><div>Barcode</div>
          <div style={{textAlign:"right"}}>Stock</div>
          <div style={{textAlign:"right"}}>Costo prom.</div>
          <div style={{textAlign:"right"}}>Acciones</div>
        </div>

        {loading&&<div style={{padding:"48px 0",display:"flex",alignItems:"center",justifyContent:"center",gap:10,color:C.mute}}><Spinner size={16}/><span style={{fontSize:13}}>Cargando stock…</span></div>}
        {err&&<div style={{padding:"18px"}}><div style={{padding:"10px 12px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13}}>{err}</div></div>}
        {!loading&&!err&&items.length===0&&!meErr&&(
          <div style={{padding:"52px 24px",textAlign:"center"}}>
            <div style={{fontSize:36,marginBottom:10}}>📦</div>
            <div style={{fontSize:15,fontWeight:700,marginBottom:4}}>Sin stock registrado</div>
            <div style={{fontSize:13,color:C.mute}}>Usa "Recibir" en cualquier producto para cargar inventario inicial</div>
          </div>
        )}

        {!loading&&!err&&items.map((r,i)=>{
          const n=toNum(r.on_hand);
          const isLow=!isNaN(n)&&n>0&&n<=5;
          const isZero=!isNaN(n)&&n<=0;
          return(
            <div key={r.product_id} className="prow" style={{display:"grid",gridTemplateColumns:"1fr 100px 110px 130px 100px 110px 200px",columnGap:12,padding:"11px 18px",borderBottom:i<items.length-1?`1px solid ${C.border}`:"none",alignItems:"center",borderLeft:isZero?`3px solid ${C.red}`:isLow?`3px solid ${C.amber}`:"3px solid transparent",minWidth:mob?800:undefined}}>
              <div>
                <div style={{fontWeight:600,fontSize:13}}>{r.name}</div>
                {(isZero||isLow)&&<div style={{fontSize:10,color:isZero?C.red:C.amber,fontWeight:700,marginTop:2}}>{isZero?"Sin stock":"Stock bajo"}</div>}
              </div>
              <div style={{fontSize:12,color:C.mid,fontFamily:C.mono}}>{r.sku??"-"}</div>
              <div style={{fontSize:12,color:C.mid}}>{r.category??"-"}</div>
              <div style={{fontSize:11,color:C.mute,fontFamily:C.mono}}>{r.barcode??"-"}</div>
              <div style={{textAlign:"right"}}><StockBadge val={r.on_hand}/></div>
              <div style={{textAlign:"right",fontSize:12,color:C.mid,fontFamily:"monospace"}}>
                {r.avg_cost&&toNum(r.avg_cost)>0?`$${Math.round(toNum(r.avg_cost)).toLocaleString("es-CL")}`:"-"}
              </div>
              <div style={{display:"flex",justifyContent:"flex-end",gap:5}}>
                <Btn variant="success" size="sm" onClick={()=>openRec(r)} disabled={!!meErr||!warehouseId}>Recibir</Btn>
                <Btn variant="danger" size="sm" onClick={()=>openIss(r)} disabled={!!meErr||!warehouseId}>Egresar</Btn>
                <Btn variant="secondary" size="sm" onClick={()=>openAdj(r)} disabled={!!meErr||!warehouseId}>Ajustar</Btn>
              </div>
            </div>
          );
        })}
       </div>
      </div>

      {!loading&&items.length>0&&(()=>{
        const PAGE_SIZE=50;
        const totalPages=Math.max(1,Math.ceil(totalCount/PAGE_SIZE));
        return <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"8px 4px",flexWrap:"wrap",gap:8}}>
          <div style={{fontSize:12,color:C.mute}}>{totalCount} producto{totalCount!==1?"s":""} · Bodega: {whName}</div>
          {totalPages>1&&<div style={{display:"flex",alignItems:"center",gap:8}}>
            <Btn variant="secondary" size="sm" disabled={page<=1} onClick={()=>setPage(p=>Math.max(1,p-1))}>← Anterior</Btn>
            <span style={{fontSize:12,color:C.mid}}>Pág <b style={{color:C.text}}>{page}</b> de <b style={{color:C.text}}>{totalPages}</b></span>
            <Btn variant="secondary" size="sm" disabled={page>=totalPages} onClick={()=>setPage(p=>Math.min(totalPages,p+1))}>Siguiente →</Btn>
          </div>}
        </div>;
      })()}

      {/* ── MODAL RECEIVE ─────────────────────────────────────────────────── */}
      {recOpen&&sel&&(
        <Modal title="Recibir stock" subtitle={`Bodega: ${whName}`} onClose={()=>setRecOpen(false)} disabled={recBusy} accentColor={C.green}>
          <ProductCard row={sel}/>
          <div style={{display:"flex",flexDirection:"column",gap:12}}>
            <FieldGroup label="Cantidad *" err={!isNaN(recQtyN)&&recQtyN<=0&&recQty.trim()?"Debe ser > 0":null}>
              <input value={recQty} onChange={e=>setRecQty(sanitizePos(e.target.value))} autoFocus inputMode="decimal"
                placeholder="Ej: 10" style={iS({fontFamily:C.mono})} disabled={recBusy}
                onKeyDown={e=>{if(e.key==="Enter")submitRec();}}/>
            </FieldGroup>
            <FieldGroup label="Costo unitario (opcional)" hint="Usado para costeo promedio ponderado">
              <div style={{position:"relative"}}>
                <span style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",color:C.mute,fontFamily:C.mono,fontSize:13,pointerEvents:"none"}}>$</span>
                <input value={recCost} onChange={e=>setRecCost(sanitizePos(e.target.value))} inputMode="decimal"
                  placeholder="0" style={iS({paddingLeft:22,fontFamily:C.mono})} disabled={recBusy}/>
              </div>
            </FieldGroup>
            <FieldGroup label="Nota">
              <input value={recNote} onChange={e=>setRecNote(e.target.value)} style={iS()} disabled={recBusy}/>
            </FieldGroup>
          </div>
          {recErr&&<ErrBanner msg={recErr} onClose={()=>setRecErr(null)}/>}
          <div style={{display:"flex",justifyContent:"flex-end",gap:8,marginTop:16}}>
            <Btn variant="ghost" onClick={()=>setRecOpen(false)} disabled={recBusy}>Cancelar</Btn>
            <Btn variant="success" onClick={submitRec} disabled={recBusy||!recOk}>
              {recBusy?<><Spinner size={13}/>Guardando…</>:"Confirmar recepción"}
            </Btn>
          </div>
        </Modal>
      )}

      {/* ── MODAL ISSUE ───────────────────────────────────────────────────── */}
      {issOpen&&sel&&(
        <Modal title="Egresar stock" subtitle={`Bodega: ${whName}`} onClose={()=>setIssOpen(false)} disabled={issBusy} accentColor={C.red}>
          <ProductCard row={sel}/>
          <div style={{display:"flex",flexDirection:"column",gap:12}}>
            <FieldGroup label="Cantidad *" err={issNeg?"Stock insuficiente":(!isNaN(issQtyN)&&issQtyN<=0&&issQty.trim()?"Debe ser > 0":null)}>
              <input value={issQty} onChange={e=>setIssQty(sanitizePos(e.target.value))} autoFocus inputMode="decimal"
                placeholder="Ej: 2" style={iS({fontFamily:C.mono})} disabled={issBusy}
                onKeyDown={e=>{if(e.key==="Enter")submitIss();}}/>
            </FieldGroup>
            {!isNaN(issQtyN)&&issQtyN>0&&(
              <div style={{padding:"8px 12px",borderRadius:C.r,background:C.bg,border:`1px solid ${C.border}`,display:"flex",flexDirection:"column",gap:4}}>
                <PreviewRow label="Stock actual" value={fQty(sel.on_hand)}/>
                <PreviewRow label="Salida" value={`- ${fQty(String(issQtyN))}`}/>
                <div style={{height:1,background:C.border}}/>
                <PreviewRow label="Stock resultante" value={isNaN(issEst)?"—":fQty(String(issEst))} highlight={!issNeg}/>
                {issNeg&&<div style={{fontSize:11,color:C.red,fontWeight:700}}>⚠️ Stock insuficiente</div>}
              </div>
            )}
            <FieldGroup label="Motivo">
              <select value={issReason} onChange={e=>setIssReason(e.target.value as any)} style={iS({height:36})} disabled={issBusy}>
                <option value="MERMA">MERMA</option>
                <option value="VENCIDO">VENCIDO</option>
                <option value="USO_INTERNO">USO INTERNO</option>
                <option value="OTRO">OTRO</option>
              </select>
            </FieldGroup>
            <FieldGroup label="Nota">
              <input value={issNote} onChange={e=>setIssNote(e.target.value)} style={iS()} disabled={issBusy}/>
            </FieldGroup>
          </div>
          {issErr&&<ErrBanner msg={issErr} onClose={()=>setIssErr(null)}/>}
          <div style={{display:"flex",justifyContent:"flex-end",gap:8,marginTop:16}}>
            <Btn variant="ghost" onClick={()=>setIssOpen(false)} disabled={issBusy}>Cancelar</Btn>
            <Btn variant="danger" onClick={submitIss} disabled={issBusy||!issOk}>
              {issBusy?<><Spinner size={13}/>Guardando…</>:"Confirmar salida"}
            </Btn>
          </div>
        </Modal>
      )}

      {/* ── MODAL ADJUST ──────────────────────────────────────────────────── */}
      {adjOpen&&sel&&(
        <Modal title="Ajustar stock" subtitle={`Bodega: ${whName}`} onClose={()=>setAdjOpen(false)} disabled={adjBusy} accentColor={C.accent}>
          <ProductCard row={sel}/>
          <div style={{display:"flex",flexDirection:"column",gap:12}}>
            <FieldGroup label="Delta de cantidad (opcional)" hint="Ej: 5 para agregar, -3 para descontar. Deja vacío si solo quieres cambiar el costo."
              err={adjNeg?"Dejaría el stock negativo":(!isNaN(adjDelta)&&adjDelta===0&&adjQty.trim()?"Debe ser distinto de 0":null)}>
              <input value={adjQty} onChange={e=>setAdjQty(sanitizeDelta(e.target.value))} autoFocus inputMode="decimal"
                placeholder="Ej: 10 o -3" style={iS({fontFamily:C.mono})} disabled={adjBusy}
                onKeyDown={e=>{if(e.key==="Enter")submitAdj();}}/>
            </FieldGroup>
            {!isNaN(adjDelta)&&adjDelta!==0&&(
              <div style={{padding:"8px 12px",borderRadius:C.r,background:C.bg,border:`1px solid ${C.border}`,display:"flex",flexDirection:"column",gap:4}}>
                <PreviewRow label="Stock actual" value={fQty(sel.on_hand)}/>
                <PreviewRow label="Delta" value={(adjDelta>0?"+":"")+fQty(String(adjDelta))}/>
                <div style={{height:1,background:C.border}}/>
                <PreviewRow label="Stock resultante" value={isNaN(adjEst)?"—":fQty(String(adjEst))} highlight={!adjNeg}/>
                {adjNeg&&<div style={{fontSize:11,color:C.red,fontWeight:700}}>⚠️ Quedaría negativo</div>}
              </div>
            )}
            <FieldGroup label="Nuevo costo promedio (opcional)" hint={`Costo actual: ${sel.avg_cost&&toNum(sel.avg_cost)>0?"$"+Math.round(toNum(sel.avg_cost)).toLocaleString("es-CL"):"no registrado"} — deja vacío para no modificarlo`}>
              <div style={{position:"relative"}}>
                <span style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",color:C.mute,fontFamily:C.mono,fontSize:13,pointerEvents:"none"}}>$</span>
                <input value={adjCost} onChange={e=>setAdjCost(sanitizePos(e.target.value))} inputMode="decimal"
                  placeholder={sel.avg_cost&&toNum(sel.avg_cost)>0?String(Math.round(toNum(sel.avg_cost))):"0"}
                  style={iS({paddingLeft:22,fontFamily:C.mono})} disabled={adjBusy}/>
              </div>
            </FieldGroup>
            <FieldGroup label="Nota">
              <input value={adjNote} onChange={e=>setAdjNote(e.target.value)} style={iS()} disabled={adjBusy}/>
            </FieldGroup>
          </div>
          {adjErr&&<ErrBanner msg={adjErr} onClose={()=>setAdjErr(null)}/>}
          <div style={{display:"flex",justifyContent:"flex-end",gap:8,marginTop:16}}>
            <Btn variant="ghost" onClick={()=>setAdjOpen(false)} disabled={adjBusy}>Cancelar</Btn>
            <Btn variant="violet" onClick={submitAdj} disabled={adjBusy||!adjOk}>
              {adjBusy?<><Spinner size={13}/>Guardando…</>:"Guardar ajuste"}
            </Btn>
          </div>
        </Modal>
      )}

      {/* ── MODAL TRANSFER ────────────────────────────────────────────────── */}
      {trOpen&&(
        <Modal title="Transferir stock" subtitle={`Desde: ${whName}`} onClose={()=>setTrOpen(false)} disabled={trBusy} accentColor={C.sky}>
          <div style={{display:"flex",flexDirection:"column",gap:12}}>
            <FieldGroup label="Bodega destino *">
              <select value={trTarget??""} onChange={e=>setTrTarget(Number(e.target.value))} style={iS({height:36})} disabled={trBusy}>
                <option value="" disabled>Selecciona…</option>
                {activeWh.filter(w=>w.id!==warehouseId).map(w=><option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
              </select>
            </FieldGroup>
            <FieldGroup label="Producto *">
              <select value={trProdId??""} onChange={e=>setTrProdId(Number(e.target.value))} style={iS({height:36})} disabled={trBusy}>
                <option value="" disabled>Selecciona un producto…</option>
                {items.map(r=><option key={r.product_id} value={r.product_id}>{r.name}{r.sku?` (${r.sku})`:""} — Stock: {fQty(r.on_hand)}</option>)}
              </select>
            </FieldGroup>
            <FieldGroup label="Cantidad *">
              <input value={trQty} onChange={e=>setTrQty(sanitizePos(e.target.value))} autoFocus inputMode="decimal"
                placeholder="Ej: 5" style={iS({fontFamily:C.mono})} disabled={trBusy}
                onKeyDown={e=>{if(e.key==="Enter")submitTr();}}/>
            </FieldGroup>
            <FieldGroup label="Nota">
              <input value={trNote} onChange={e=>setTrNote(e.target.value)} style={iS()} disabled={trBusy}/>
            </FieldGroup>
          </div>
          {trErr&&<ErrBanner msg={trErr} onClose={()=>setTrErr(null)}/>}
          <div style={{display:"flex",justifyContent:"flex-end",gap:8,marginTop:16}}>
            <Btn variant="ghost" onClick={()=>setTrOpen(false)} disabled={trBusy}>Cancelar</Btn>
            <Btn variant="sky" onClick={submitTr} disabled={trBusy||!trOk}>
              {trBusy?<><Spinner size={13}/>Procesando…</>:"Confirmar transferencia"}
            </Btn>
          </div>
        </Modal>
      )}
    </div>
  );
}