"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";

type Warehouse={id:number;name:string;is_active:boolean;warehouse_type?:string};
type ProductMini={id:number;name:string;sku?:string|null};
type MoveRow={id:number;created_at:string;warehouse_id:number;product:ProductMini;move_type:string;qty:string;ref_type:string|null;ref_id:number|null;note:string|null};

function fDt(iso:string):string{const d=new Date(iso);return isNaN(d.getTime())?iso:d.toLocaleString("es-CL");}
function isoDate(d:Date):string{return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;}

const PAGE_CSS = `.mrow{transition:background 0.1s ease}.mrow:hover{background:#F4F4F5}`;

function TypeBadge({type}:{type:string}){
  const t=(type||"").toUpperCase();
  const cfg:Record<string,{bg:string;bd:string;color:string;label:string}>={
    IN:{bg:C.greenBg,bd:C.greenBd,color:C.green,label:"Entrada"},
    OUT:{bg:C.redBg,bd:C.redBd,color:C.red,label:"Salida"},
    ADJ:{bg:C.amberBg,bd:C.amberBd,color:C.amber,label:"Ajuste"},
  };
  const c=cfg[t]||{bg:"#F4F4F5",bd:"#E4E4E7",color:C.mid,label:t};
  return(<span style={{display:"inline-flex",padding:"2px 8px",borderRadius:99,fontSize:11,fontWeight:700,border:`1px solid ${c.bd}`,background:c.bg,color:c.color}}>{c.label}</span>);
}

function refHref(refType:string|null,refId:number|null):string|null{
  if(!refType||refId==null)return null;
  if(refType==="SALE")return `/dashboard/sales/${refId}`;
  if(refType==="TRANSFER")return `/dashboard/inventory/transfers/${refId}`;
  if(refType==="PURCHASE")return `/dashboard/purchases/${refId}`;
  return null;
}

export default function MovesPage(){
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();
  const [warehouses,setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId,setWarehouseId] = useState<number|"ALL">("ALL");
  const [moveType,setMoveType] = useState<"ALL"|"IN"|"OUT"|"ADJ">("ALL");
  const [q,setQ] = useState("");
  const [range,setRange] = useState<"TODAY"|"7D"|"30D">("7D");
  const [items,setItems] = useState<MoveRow[]>([]);
  const [loading,setLoading] = useState(true);
  const [err,setErr] = useState<string|null>(null);

  const whMap=useMemo(()=>new Map(warehouses.map(w=>[w.id,w.name])),[warehouses]);
  const whTypeMap=useMemo(()=>new Map(warehouses.map(w=>[w.id,w.warehouse_type])),[warehouses]);

  const endpoint=useMemo(()=>{
    const p=new URLSearchParams();
    if(warehouseId!=="ALL")p.set("warehouse_id",String(warehouseId));
    if(moveType!=="ALL")p.set("move_type",moveType);
    const qq=q.trim();if(qq)p.set("q",qq);
    const now=new Date();let start=new Date(now);
    if(range==="TODAY")start=new Date(now.getFullYear(),now.getMonth(),now.getDate());
    else if(range==="7D")start.setDate(now.getDate()-7);
    else start.setDate(now.getDate()-30);
    p.set("from",isoDate(start));p.set("to",isoDate(now));
    return `/inventory/moves/?${p.toString()}`;
  },[warehouseId,moveType,q,range]);

  async function load(){
    setLoading(true);setErr(null);
    try{const data=await apiFetch(endpoint);setItems(data?.results??data??[]);}
    catch(e:any){setErr(e?.message??"Error cargando movimientos");setItems([]);}
    finally{setLoading(false);}
  }

  useEffect(()=>{
    (async()=>{try{const ws=(await apiFetch("/core/warehouses/")) as Warehouse[];setWarehouses(Array.isArray(ws)?ws:[]);}catch{setWarehouses([]);}})();
  },[]);

  useEffect(()=>{const t=setTimeout(()=>load(),250);return()=>clearTimeout(t);},[endpoint]); // eslint-disable-line

  // counts by type for quick summary
  const summary=useMemo(()=>{
    const in_=items.filter(m=>m.move_type==="IN").length;
    const out=items.filter(m=>m.move_type==="OUT").length;
    const adj=items.filter(m=>m.move_type==="ADJ").length;
    return{in_,out,adj,total:items.length};
  },[items]);

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
            <div style={{width:4,height:26,background:C.accent,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:22,fontWeight:800,letterSpacing:"-0.04em"}}>Movimientos</h1>
          </div>
          <p style={{margin:0,fontSize:13,color:C.mute,paddingLeft:14}}>Historial de movimientos de stock (IN / OUT / ADJ)</p>
        </div>
        <div style={{display:"flex",gap:8}}>
          <Link href="/dashboard/inventory/stock" className="xb" style={{height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.borderMd}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6,textDecoration:"none"}}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
            Stock
          </Link>
          <button type="button" onClick={load} disabled={loading} className="xb"
            style={{height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6}}>
            {loading?<Spinner/>:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>}
            Recargar
          </button>
        </div>
      </div>

      {/* SUMMARY STRIP */}
      {!loading&&items.length>0&&(
        <div style={{display:"flex",gap:16,flexWrap:"wrap",padding:"10px 16px",background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,boxShadow:C.sh,alignItems:"center"}}>
          <span style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Resumen</span>
          {[
            {label:"Total",val:summary.total,color:C.text},
            {label:"IN",val:summary.in_,color:C.green},
            {label:"OUT",val:summary.out,color:C.red},
            {label:"ADJ",val:summary.adj,color:C.accent},
          ].map(s=>(
            <div key={s.label} style={{display:"flex",alignItems:"baseline",gap:5}}>
              <span style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.06em"}}>{s.label}</span>
              <span style={{fontSize:16,fontWeight:800,color:s.color,fontVariantNumeric:"tabular-nums"}}>{s.val}</span>
            </div>
          ))}
        </div>
      )}

      {/* FILTERS */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,padding:"12px 16px",boxShadow:C.sh,display:"flex",gap:10,flexWrap:"wrap",alignItems:"center"}}>
        {/* Range buttons */}
        <div style={{display:"flex",gap:6}}>
          {([{v:"TODAY",l:"Hoy"},{v:"7D",l:"7 días"},{v:"30D",l:"30 días"}] as const).map(b=>(
            <button key={b.v} type="button" onClick={()=>setRange(b.v)} className="xb"
              style={{height:32,padding:"0 12px",borderRadius:C.r,fontSize:12,fontWeight:600,
                border:`1px solid ${range===b.v?C.accentBd:C.border}`,
                background:range===b.v?C.accentBg:C.surface,
                color:range===b.v?C.accent:C.mid}}>
              {b.l}
            </button>
          ))}
        </div>
        <div style={{width:1,height:24,background:C.border}}/>
        {warehouses.length>0&&(
          <select value={warehouseId} onChange={e=>setWarehouseId(e.target.value==="ALL"?"ALL":Number(e.target.value))}
            style={{height:34,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg,minWidth:160}}>
            <option value="ALL">Todas las bodegas</option>
            {warehouses.map(w=><option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
          </select>
        )}
        <select value={moveType} onChange={e=>setMoveType(e.target.value as any)}
          style={{height:34,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg,minWidth:130}}>
          <option value="ALL">Todos los tipos</option>
          <option value="IN">IN</option>
          <option value="OUT">OUT</option>
          <option value="ADJ">ADJ</option>
        </select>
        <div style={{position:"relative",flex:1,minWidth:180}}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
            style={{position:"absolute",left:9,top:"50%",transform:"translateY(-50%)",pointerEvents:"none"}}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Buscar por SKU o nombre…"
            style={{width:"100%",height:34,padding:"0 10px 0 30px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg}}/>
        </div>
      </div>

      {err&&<div style={{padding:"10px 12px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13}}>{err}</div>}

      {/* TABLE */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
       <div style={{overflowX:"auto"}}>
        <div style={{display:"grid",gridTemplateColumns:"150px 1fr 90px 130px 70px 80px 180px 1fr",columnGap:10,padding:"10px 18px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.08em",minWidth:mob?900:undefined}}>
          <div>Fecha</div><div>Producto</div><div>SKU</div><div>Bodega</div>
          <div style={{textAlign:"center"}}>Tipo</div>
          <div style={{textAlign:"right"}}>Qty</div>
          <div>Ref</div><div>Nota</div>
        </div>

        {loading&&<div style={{padding:"48px 0",display:"flex",alignItems:"center",justifyContent:"center",gap:10,color:C.mute}}><Spinner size={16}/><span style={{fontSize:13}}>Cargando…</span></div>}

        {!loading&&items.length===0&&(
          <div style={{padding:"48px 24px",textAlign:"center"}}>
            <div style={{fontSize:32,marginBottom:8}}>🔄</div>
            <div style={{fontSize:14,fontWeight:700,marginBottom:4}}>Sin movimientos</div>
            <div style={{fontSize:13,color:C.mute}}>Cambia el rango de fechas o los filtros</div>
          </div>
        )}

        {!loading&&items.map((m,i)=>{
          const href=refHref(m.ref_type,m.ref_id);
          return(
            <div key={m.id} className="mrow" style={{display:"grid",gridTemplateColumns:"150px 1fr 90px 130px 70px 80px 180px 1fr",columnGap:10,padding:"11px 18px",borderBottom:i<items.length-1?`1px solid ${C.border}`:"none",alignItems:"center",minWidth:mob?900:undefined}}>
              <div style={{fontSize:11,color:C.mute}}>{fDt(m.created_at)}</div>
              <div>
                <div style={{fontWeight:600,fontSize:13,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{m.product?.name??"—"}</div>
              </div>
              <div style={{fontSize:12,color:C.mid,fontFamily:C.mono}}>{m.product?.sku??"-"}</div>
              <div style={{fontSize:12,color:C.mid,display:"flex",alignItems:"center",gap:4}}>
                {whMap.get(m.warehouse_id)??`#${m.warehouse_id}`}
                {whTypeMap.get(m.warehouse_id)==="sales_floor"
                  ?<span style={{fontSize:9,fontWeight:700,padding:"1px 5px",borderRadius:4,background:C.greenBg,color:C.green,border:`1px solid ${C.greenBd}`}}>Sala</span>
                  :<span style={{fontSize:9,fontWeight:700,padding:"1px 5px",borderRadius:4,background:C.bg,color:C.mute,border:`1px solid ${C.border}`}}>Bodega</span>}
              </div>
              <div style={{display:"flex",justifyContent:"center"}}><TypeBadge type={m.move_type}/></div>
              <div style={{textAlign:"right",fontWeight:700,fontSize:13,fontVariantNumeric:"tabular-nums",fontFamily:C.mono,
                color:m.move_type==="OUT"?C.red:m.move_type==="IN"?C.green:C.accent}}>
                {m.qty}
              </div>
              <div style={{fontSize:12}}>
                {m.ref_type&&<span style={{fontWeight:600,color:C.mid}}>{m.ref_type}{m.ref_id!=null?` #${m.ref_id}`:""}</span>}
                {href&&<Link href={href} style={{display:"block",fontSize:11,color:C.accent,textDecoration:"none",fontWeight:600,marginTop:2}}>Ver →</Link>}
                {!m.ref_type&&<span style={{color:C.mute}}>—</span>}
              </div>
              <div style={{fontSize:12,color:C.mute,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{m.note||"-"}</div>
            </div>
          );
        })}
       </div>
      </div>

      {!loading&&items.length>0&&<div style={{fontSize:12,color:C.mute,padding:"4px"}}>{items.length} movimiento{items.length!==1?"s":""}</div>}
    </div>
  );
}