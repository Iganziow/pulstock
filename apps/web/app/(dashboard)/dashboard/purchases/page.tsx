"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";

type Warehouse = {id:number; name:string; is_active:boolean; warehouse_type?:string};
type PurchaseRow = {
  id:number; created_at:string; warehouse_id:number;
  supplier_name:string; invoice_number:string; invoice_date:string|null;
  subtotal_cost:string; tax_amount:string; total_cost:string;
  status:"DRAFT"|"POSTED"|"VOID"|string;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function toNum(v:string|number|null|undefined):number{if(v==null)return 0;const n=typeof v==="string"?Number(v):v;return Number.isFinite(n)?n:0;}
function fCLP(v:string|number|null|undefined):string{return Math.round(toNum(v)).toLocaleString("es-CL");}
function isoDate(d:Date):string{return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;}
function fDate(iso:string):string{const d=new Date(iso);if(isNaN(d.getTime()))return iso;return d.toLocaleDateString("es-CL",{day:"2-digit",month:"2-digit",year:"numeric"});}
function fDateTime(iso:string):string{const d=new Date(iso);if(isNaN(d.getTime()))return iso;return d.toLocaleString("es-CL",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"});}

// ─── Mini-components ──────────────────────────────────────────────────────────

type BtnV="primary"|"secondary"|"ghost"|"danger"|"success"|"teal";
function Btn({children,onClick,variant="secondary",disabled,size="md",full}:{children:React.ReactNode;onClick?:()=>void;variant?:BtnV;disabled?:boolean;size?:"sm"|"md"|"lg";full?:boolean;}){
  const vs:Record<BtnV,React.CSSProperties>={
    primary:{background:C.accent,color:"#fff",border:`1px solid ${C.accent}`},
    secondary:{background:C.surface,color:C.text,border:`1px solid ${C.borderMd}`},
    ghost:{background:"transparent",color:C.mid,border:"1px solid transparent"},
    danger:{background:C.redBg,color:C.red,border:`1px solid ${C.redBd}`},
    success:{background:C.greenBg,color:C.green,border:`1px solid ${C.greenBd}`},
    teal:{background:C.tealBg,color:C.teal,border:`1px solid ${C.tealBd}`},
  };
  const h=size==="lg"?46:size==="sm"?30:38;
  const px=size==="lg"?"0 20px":size==="sm"?"0 10px":"0 14px";
  const fs=size==="lg"?14:size==="sm"?11:13;
  return(<button type="button" onClick={onClick} disabled={disabled} className="xb" style={{...vs[variant],display:"inline-flex",alignItems:"center",justifyContent:"center",gap:6,height:h,padding:px,borderRadius:C.r,fontSize:fs,fontWeight:600,letterSpacing:"0.01em",whiteSpace:"nowrap",width:full?"100%":undefined}}>{children}</button>);
}

function StatusBadge({status}:{status:string}){
  const s=(status||"").toUpperCase();
  const cfg:Record<string,{bg:string;bd:string;color:string;label:string}> = {
    DRAFT:  {bg:C.amberBg, bd:C.amberBd, color:C.amber,  label:"Borrador"},
    POSTED: {bg:C.greenBg, bd:C.greenBd, color:C.green,  label:"Posteada"},
    VOID:   {bg:C.redBg,   bd:C.redBd,   color:C.red,    label:"Anulada"},
  };
  const c=cfg[s]??{bg:C.bg,bd:C.border,color:C.mid,label:s};
  return(
    <span style={{display:"inline-flex",alignItems:"center",gap:5,padding:"3px 9px",borderRadius:99,fontSize:11,fontWeight:700,border:`1px solid ${c.bd}`,background:c.bg,color:c.color,letterSpacing:"0.03em"}}>
      <span style={{width:6,height:6,borderRadius:"50%",background:"currentColor",display:"inline-block"}}/>
      {c.label}
    </span>
  );
}

function StatCard({label,value,sub,color,icon}:{label:string;value:string;sub?:string;color:string;icon:React.ReactNode;}){
  return(
    <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,padding:"14px 18px",boxShadow:C.sh,display:"flex",flexDirection:"column",gap:8}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
        <div style={{fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>{label}</div>
        <div style={{color,opacity:0.7}}>{icon}</div>
      </div>
      <div style={{fontSize:22,fontWeight:800,color,letterSpacing:"-0.03em",fontVariantNumeric:"tabular-nums"}}>{value}</div>
      {sub&&<div style={{fontSize:11,color:C.mute}}>{sub}</div>}
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function PurchasesListPage(){
  useGlobalStyles();
  const mob = useIsMobile();
  const [items,setItems]       = useState<PurchaseRow[]>([]);
  const [loading,setLoading]   = useState(true);
  const [err,setErr]           = useState<string|null>(null);
  const [warehouses,setWarehouses] = useState<Warehouse[]>([]);

  // Filters
  const [q,setQ]               = useState("");
  const [status,setStatus]     = useState<"ALL"|"DRAFT"|"POSTED"|"VOID">("ALL");
  const [range,setRange]       = useState<"TODAY"|"7D"|"30D"|"ALL">("30D");
  const [warehouseId,setWarehouseId] = useState<number|"ALL">("ALL");

  const endpoint = useMemo(()=>{
    const base="/purchases/";
    const p=new URLSearchParams();
    const qq=q.trim();
    if(qq) p.set("q",qq);
    if(status!=="ALL") p.set("status",status);
    if(warehouseId!=="ALL") p.set("warehouse_id",String(warehouseId));
    if(range!=="ALL"){
      const now=new Date(); let start=new Date(now);
      if(range==="TODAY") start=new Date(now.getFullYear(),now.getMonth(),now.getDate());
      else if(range==="7D") start.setDate(now.getDate()-7);
      else if(range==="30D") start.setDate(now.getDate()-30);
      p.set("date_from",isoDate(start)); p.set("date_to",isoDate(now));
    }
    const qs=p.toString();
    return qs?`${base}?${qs}`:base;
  },[q,status,range,warehouseId]);

  const load = useCallback(async()=>{
    setLoading(true); setErr(null);
    try{
      const data=await apiFetch(endpoint);
      setItems(data?.results??data??[]);
    }catch(e:any){setErr(e?.message??"Error cargando compras");setItems([]);}
    finally{setLoading(false);}
  },[endpoint]);

  useEffect(()=>{
    (async()=>{try{const ws=(await apiFetch("/core/warehouses/")) as Warehouse[];setWarehouses(Array.isArray(ws)?ws:[]);}catch{setWarehouses([]);}})();
  },[]);

  useEffect(()=>{const t=setTimeout(()=>load(),250);return()=>clearTimeout(t);},[load]);

  const metrics = useMemo(()=>{
    const posted=items.filter(p=>p.status.toUpperCase()==="POSTED");
    const drafts=items.filter(p=>p.status.toUpperCase()==="DRAFT");
    const voids=items.filter(p=>p.status.toUpperCase()==="VOID");
    const totalCost=posted.reduce((a,p)=>a+toNum(p.total_cost),0);
    return {total:items.length,posted:posted.length,drafts:drafts.length,voids:voids.length,totalCost};
  },[items]);

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
            <div style={{width:4,height:26,background:C.teal,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:22,fontWeight:800,color:C.text,letterSpacing:"-0.04em"}}>Compras</h1>
          </div>
          <p style={{margin:0,fontSize:13,color:C.mute,paddingLeft:14}}>Órdenes de compra y entradas de stock</p>
        </div>
        <div style={{display:"flex",gap:8}}>
          <Btn variant="secondary" size="sm" onClick={load} disabled={loading}>
            {loading?<Spinner/>:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>}
            {loading?"Cargando…":"Recargar"}
          </Btn>
          <Link href="/dashboard/purchases/new" style={{display:"inline-flex",alignItems:"center",gap:6,height:38,padding:"0 16px",borderRadius:C.r,fontSize:13,fontWeight:600,background:C.teal,color:"#fff",border:`1px solid ${C.teal}`,textDecoration:"none",whiteSpace:"nowrap"}}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Nueva compra
          </Link>
        </div>
      </div>

      {/* STAT CARDS */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))",gap:10}}>
        <StatCard label="Total compras" value={String(metrics.total)}
          sub={`${metrics.posted} posteadas · ${metrics.drafts} borradores`} color={C.teal}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 01-8 0"/></svg>}
        />
        <StatCard label="Inversión total" value={`$${fCLP(metrics.totalCost)}`}
          sub="Solo compras posteadas" color={C.accent}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>}
        />
        <StatCard label="Borradores" value={String(metrics.drafts)}
          sub="Pendientes de postear" color={C.amber}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>}
        />
        <StatCard label="Anuladas" value={String(metrics.voids)} color={C.red}
          icon={<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>}
        />
      </div>

      {/* FILTERS */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,padding:"12px 16px",boxShadow:C.sh,display:"flex",gap:10,alignItems:"center",flexWrap:"wrap"}}>
        <div style={{position:"relative",flex:1,minWidth:200}}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round" style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",pointerEvents:"none"}}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Buscar por folio (ID), proveedor…"
            style={{width:"100%",height:36,padding:"0 10px 0 34px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg}}/>
        </div>
        <div style={{width:1,height:24,background:C.border}}/>
        {([{v:"TODAY",l:"Hoy"},{v:"7D",l:"7 días"},{v:"30D",l:"30 días"},{v:"ALL",l:"Todo"}] as const).map(b=>(
          <button key={b.v} type="button" onClick={()=>setRange(b.v)} className="xb" style={{height:32,padding:"0 12px",borderRadius:C.r,fontSize:12,fontWeight:600,border:`1px solid ${range===b.v?C.teal:C.border}`,background:range===b.v?C.tealBg:C.surface,color:range===b.v?C.teal:C.mid}}>{b.l}</button>
        ))}
        <div style={{width:1,height:24,background:C.border}}/>
        <select value={status} onChange={e=>setStatus(e.target.value as any)} style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg}}>
          <option value="ALL">Todos los estados</option>
          <option value="DRAFT">Borrador</option>
          <option value="POSTED">Posteadas</option>
          <option value="VOID">Anuladas</option>
        </select>
        {warehouses.length>0&&(
          <select value={warehouseId} onChange={e=>setWarehouseId(e.target.value==="ALL"?"ALL":Number(e.target.value))} style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg}}>
            <option value="ALL">Todas las bodegas</option>
            {warehouses.map(w=><option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
          </select>
        )}
      </div>

      {/* TABLE */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
       <div style={{overflowX:"auto"}}>
        {/* Header */}
        <div style={{display:"grid",gridTemplateColumns:"80px 110px 1fr 150px 130px 120px 110px",columnGap:12,padding:"10px 18px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.08em",minWidth:mob?780:undefined}}>
          <div>Folio</div><div>Fecha</div><div>Proveedor</div><div>Factura</div>
          <div style={{textAlign:"right"}}>Total costo</div>
          <div style={{textAlign:"center"}}>Estado</div>
          <div style={{textAlign:"right"}}>Acciones</div>
        </div>

        {loading&&<div style={{padding:"52px 0",display:"flex",alignItems:"center",justifyContent:"center",gap:10,color:C.mute}}><Spinner size={16}/><span style={{fontSize:13}}>Cargando compras…</span></div>}
        {err&&<div style={{padding:"20px 18px"}}><div style={{padding:"11px 14px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13}}>{err}</div></div>}
        {!loading&&!err&&items.length===0&&(
          <div style={{padding:"56px 24px",textAlign:"center"}}>
            <div style={{fontSize:36,marginBottom:10}}>📦</div>
            <div style={{fontSize:15,fontWeight:700,color:C.text,marginBottom:4}}>No hay compras</div>
            <div style={{fontSize:13,color:C.mute,marginBottom:16}}>Cambia los filtros o crea una nueva compra</div>
            <Link href="/dashboard/purchases/new" style={{display:"inline-flex",alignItems:"center",gap:6,height:36,padding:"0 16px",borderRadius:C.r,fontSize:13,fontWeight:600,background:C.teal,color:"#fff",textDecoration:"none"}}>
              + Nueva compra
            </Link>
          </div>
        )}

        {!loading&&!err&&items.map((p,i)=>{
          const isVoid=p.status.toUpperCase()==="VOID";
          const isDraft=p.status.toUpperCase()==="DRAFT";
          const whName=warehouses.find(w=>w.id===p.warehouse_id)?.name??`#${p.warehouse_id}`;
          return(
            <div key={p.id} className="prow" style={{display:"grid",gridTemplateColumns:"80px 110px 1fr 150px 130px 120px 110px",columnGap:12,padding:"13px 18px",borderBottom:i<items.length-1?`1px solid ${C.border}`:"none",alignItems:"center",opacity:isVoid?0.6:1,minWidth:mob?780:undefined}}>
              <div style={{fontFamily:C.mono,fontWeight:700,fontSize:13,color:C.accent}}>#{p.id}</div>
              <div>
                <div style={{fontSize:12,fontWeight:500}}>{fDate(p.created_at)}</div>
                <div style={{fontSize:10,color:C.mute,marginTop:1}}>{new Date(p.created_at).toLocaleTimeString("es-CL",{hour:"2-digit",minute:"2-digit"})}</div>
              </div>
              <div>
                <div style={{fontSize:13,fontWeight:600,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{p.supplier_name||<span style={{color:C.mute}}>Sin proveedor</span>}</div>
                <div style={{fontSize:11,color:C.mute,marginTop:1}}>{whName}</div>
              </div>
              <div style={{fontSize:12,color:C.mid,fontFamily:C.mono}}>{p.invoice_number||<span style={{color:C.mute}}>—</span>}</div>
              <div style={{textAlign:"right"}}>
                {isVoid?<span style={{textDecoration:"line-through",color:C.mute,fontSize:13}}>${fCLP(p.total_cost)}</span>:
                  <span style={{fontWeight:800,fontSize:14,fontVariantNumeric:"tabular-nums"}}>${fCLP(p.total_cost)}</span>}
              </div>
              <div style={{display:"flex",justifyContent:"center"}}><StatusBadge status={p.status}/></div>
              <div style={{display:"flex",justifyContent:"flex-end",gap:6}}>
                <Link href={`/dashboard/purchases/${p.id}`} style={{display:"inline-flex",alignItems:"center",gap:4,height:28,padding:"0 10px",borderRadius:C.r,fontSize:11,fontWeight:600,border:`1px solid ${C.borderMd}`,background:C.surface,color:C.mid,textDecoration:"none"}}>
                  Ver
                </Link>
                {isDraft&&(
                  <Link href={`/dashboard/purchases/${p.id}`} style={{display:"inline-flex",alignItems:"center",gap:4,height:28,padding:"0 10px",borderRadius:C.r,fontSize:11,fontWeight:600,border:`1px solid ${C.amberBd}`,background:C.amberBg,color:C.amber,textDecoration:"none"}}>
                    Postear →
                  </Link>
                )}
              </div>
            </div>
          );
        })}
       </div>
      </div>

      {!loading&&items.length>0&&(
        <div style={{padding:"6px 4px",fontSize:12,color:C.mute}}>
          {items.length} compra{items.length!==1?"s":""}
        </div>
      )}
    </div>
  );
}