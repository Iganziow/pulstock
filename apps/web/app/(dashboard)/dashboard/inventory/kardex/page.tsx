"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { Spinner } from "@/components/ui";
import { useIsMobile } from "@/hooks/useIsMobile";
type Warehouse={id:number;name:string;is_active:boolean;warehouse_type?:string};
type KardexProduct={id:number;name:string;sku:string;barcode:string|null};
type KardexRow={
  id:number; created_at:string; warehouse_id:number;
  move_type:"IN"|"OUT"|"ADJ"|string;
  product:KardexProduct; qty:string; balance:string;
  ref_type:string|null; ref_id:number|null;
  note:string; created_by:{id:number;username:string|null}|null;
};
type KardexResponse={count:number;next:string|null;previous:string|null;results:{warehouse_id:number;results:KardexRow[]}};

function fQty(v:string):string{const n=Number(v);if(!Number.isFinite(n))return v;return n.toLocaleString("es-CL",{maximumFractionDigits:3});}
function fDt(iso:string):{date:string;time:string}{
  const d=new Date(iso);
  if(isNaN(d.getTime()))return{date:iso,time:""};
  return{
    date:d.toLocaleDateString("es-CL",{day:"2-digit",month:"2-digit",year:"numeric"}),
    time:d.toLocaleTimeString("es-CL",{hour:"2-digit",minute:"2-digit"}),
  };
}
function isoDate(d:Date):string{return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;}

// ── Etiquetas legibles para humanos ────────────────────────────────────────────
const MOVE_LABEL: Record<string,{label:string;icon:string;bg:string;bd:string;color:string}> = {
  IN:       {label:"Entrada",         icon:"↑", bg:C.greenBg,  bd:C.greenBd,  color:C.green},
  OUT:      {label:"Salida",          icon:"↓", bg:C.redBg,    bd:C.redBd,    color:C.red},
  ADJ:      {label:"Ajuste",          icon:"≈", bg:C.accentBg, bd:C.accentBd, color:C.accent},
  TRANSFER: {label:"Traslado",        icon:"⇄", bg:C.tealBg,   bd:C.tealBd,   color:C.teal},
  PURCHASE: {label:"Compra",          icon:"↑", bg:C.skyBg,    bd:C.skyBd,    color:C.sky},
  SALE_VOID:{label:"Anulación venta", icon:"↩", bg:C.amberBg,  bd:C.amberBd,  color:C.amber},
};
function getMoveStyle(type:string){return MOVE_LABEL[(type||"").toUpperCase()]??{label:type||"—",icon:"·",bg:C.bg,bd:C.border,color:C.mid};}

const REF_LABEL: Record<string,string> = {
  SALE:"Venta", TRANSFER:"Traslado", PURCHASE:"Compra", SALE_VOID:"Anulación de venta", ADJ:"Ajuste manual",
};
function refHref(rt:string|null,ri:number|null):string|null{
  if(!rt||ri==null)return null;
  if(rt==="SALE")return `/dashboard/sales/${ri}`;
  if(rt==="TRANSFER"||rt==="SALE_VOID")return `/dashboard/inventory/transfers/${ri}`;
  return null;
}
function refText(rt:string|null,ri:number|null):string{
  if(!rt)return "—";
  const label=REF_LABEL[rt]??rt;
  return ri!=null?`${label} #${ri}`:label;
}

// ── CSV export ─────────────────────────────────────────────────────────────────
function toCsv(rows:KardexRow[]):string{
  const hdr=["Fecha","Movimiento","Producto","SKU","Cantidad","Stock final","Origen","Usuario","Nota"];
  const esc=(s:any)=>{const v=s==null?"":String(s);const n=/[",\n]/.test(v);return n?`"${v.replace(/"/g,'""')}"`:`${v}`;};
  const {date,time}=fDt("");
  void date;void time;
  const lines=rows.map(r=>{
    const dt=fDt(r.created_at);
    return[
      `${dt.date} ${dt.time}`,
      getMoveStyle(r.move_type).label,
      r.product?.name??"",
      r.product?.sku??"",
      r.qty,
      r.balance,
      refText(r.ref_type,r.ref_id),
      r.created_by?.username??"",
      r.note??"",
    ];
  });
  return[hdr,...lines].map(l=>l.map(esc).join(",")).join("\n");
}
function dlCsv(name:string,csv:string){const b=new Blob([csv],{type:"text/csv;charset=utf-8;"});const u=URL.createObjectURL(b);const a=document.createElement("a");a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(u);}


function MoveBadge({type}:{type:string}){
  const s=getMoveStyle(type);
  return(
    <span style={{display:"inline-flex",alignItems:"center",gap:4,padding:"3px 8px",borderRadius:99,fontSize:11,fontWeight:700,border:`1px solid ${s.bd}`,background:s.bg,color:s.color,letterSpacing:"0.02em",whiteSpace:"nowrap"}}>
      <span style={{fontSize:12,lineHeight:1}}>{s.icon}</span>
      {s.label}
    </span>
  );
}

const PAGE_CSS = `
.krow{transition:background 0.1s ease}.krow:hover{background:#F4F4F5}
@media print{.no-print{display:none!important}.print-only{display:block!important}}
`;

export default function KardexPage(){
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();
  const [warehouses,setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId,setWarehouseId] = useState<number|null>(null);
  const [productId,setProductId] = useState("");
  const [q,setQ] = useState("");
  const [from,setFrom] = useState("");
  const [to,setTo] = useState("");
  const [moveType,setMoveType] = useState("");
  const [rows,setRows] = useState<KardexRow[]>([]);
  const [count,setCount] = useState(0);
  const [limit,setLimit] = useState(200);
  const [offset,setOffset] = useState(0);
  const [loading,setLoading] = useState(false);
  const [err,setErr] = useState<string|null>(null);

  useEffect(()=>{
    (async()=>{try{const ws=(await apiFetch("/core/warehouses/")) as Warehouse[];const list=Array.isArray(ws)?ws:[];setWarehouses(list);if(list.length&&!warehouseId)setWarehouseId(list[0].id);}catch(e:any){setErr(e?.message??"Error cargando bodegas");}})();
  },[]); // eslint-disable-line

  useEffect(()=>setOffset(0),[warehouseId,productId,q,from,to,moveType,limit]);

  const endpoint=useMemo(()=>{
    if(!warehouseId)return null;
    const p=new URLSearchParams();
    p.set("warehouse_id",String(warehouseId));p.set("limit",String(limit));p.set("offset",String(offset));
    const pid=productId.trim();if(pid)p.set("product_id",pid);
    const qq=q.trim();if(qq)p.set("q",qq);
    if(from)p.set("from",from);if(to)p.set("to",to);
    const mt=moveType.trim().toUpperCase();if(mt)p.set("move_type",mt);
    return `/inventory/kardex/?${p.toString()}`;
  },[warehouseId,productId,q,from,to,moveType,limit,offset]);

  async function load(){
    if(!endpoint)return;
    setLoading(true);setErr(null);
    try{
      const data=(await apiFetch(endpoint)) as KardexResponse;
      setRows(data?.results?.results??[]);setCount(data?.count??0);
    }catch(e:any){setErr(e?.message??"Error cargando historial de movimientos");setRows([]);setCount(0);}
    finally{setLoading(false);}
  }

  useEffect(()=>{if(!endpoint)return;const t=setTimeout(()=>load(),250);return()=>clearTimeout(t);},[endpoint]); // eslint-disable-line

  const canPrev=offset>0;
  const canNext=offset+limit<count;
  const whName=warehouses.find(w=>w.id===warehouseId)?.name??`Bodega #${warehouseId}`;

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}} className="no-print">
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
            <div style={{width:4,height:26,background:C.accent,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:22,fontWeight:800,letterSpacing:"-0.04em"}}>Historial de movimientos</h1>
          </div>
          <p style={{margin:0,fontSize:13,color:C.mute,paddingLeft:14}}>
            Registro cronológico de todas las entradas, salidas y ajustes de stock
          </p>
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          <Link href="/dashboard/inventory/kardex-report" style={{display:"inline-flex",alignItems:"center",gap:6,height:36,padding:"0 14px",borderRadius:C.r,fontSize:13,fontWeight:600,border:`1px solid ${C.accentBd}`,background:C.accentBg,color:C.accent,textDecoration:"none"}}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
            Reporte
          </Link>
          <button type="button" onClick={()=>dlCsv(`movimientos_${whName.replace(/\s+/g,"_")}.csv`,toCsv(rows))} disabled={loading||rows.length===0} className="xb"
            style={{height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6}}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Exportar
          </button>
          <button type="button" onClick={()=>window.print()} disabled={rows.length===0} className="xb"
            style={{height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6}}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
            Imprimir
          </button>
          <button type="button" onClick={load} disabled={loading||!warehouseId} className="xb"
            style={{height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6}}>
            {loading?<Spinner/>:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>}
            Actualizar
          </button>
        </div>
      </div>

      {err&&<div style={{padding:"10px 12px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13}} className="no-print">{err}</div>}

      {/* FILTERS */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,padding:"12px 16px",boxShadow:C.sh,display:"flex",gap:10,flexWrap:"wrap",alignItems:"flex-end"}} className="no-print">
        {/* Bodega */}
        <div style={{display:"flex",flexDirection:"column",gap:4}}>
          <label style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.06em"}}>Bodega</label>
          <select value={warehouseId??""} onChange={e=>setWarehouseId(e.target.value?Number(e.target.value):null)}
            style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg,minWidth:180}}>
            {warehouses.length===0?<option value="">(sin bodegas)</option>:warehouses.map(w=><option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
          </select>
        </div>

        {/* Buscar producto */}
        <div style={{display:"flex",flexDirection:"column",gap:4,flex:1,minWidth:200}}>
          <label style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.06em"}}>Buscar producto</label>
          <div style={{position:"relative"}}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
              style={{position:"absolute",left:9,top:"50%",transform:"translateY(-50%)",pointerEvents:"none"}}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Nombre, SKU o código de barras"
              style={{width:"100%",height:36,padding:"0 10px 0 30px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg}}/>
          </div>
        </div>

        {/* Fechas */}
        {([{v:from,set:setFrom,label:"Desde"},{v:to,set:setTo,label:"Hasta"}] as const).map((f: any)=>(
          <div key={f.label} style={{display:"flex",flexDirection:"column",gap:4}}>
            <label style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.06em"}}>{f.label}</label>
            <input type="date" value={f.v} onChange={(e: React.ChangeEvent<HTMLInputElement>)=>f.set(e.target.value)}
              style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg}}/>
          </div>
        ))}

        {/* Tipo de movimiento */}
        <div style={{display:"flex",flexDirection:"column",gap:4}}>
          <label style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.06em"}}>Tipo de movimiento</label>
          <select value={moveType} onChange={e=>setMoveType(e.target.value)}
            style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg,minWidth:150}}>
            <option value="">Todos los tipos</option>
            <option value="IN">↑ Entradas</option>
            <option value="OUT">↓ Salidas</option>
            <option value="ADJ">≈ Ajustes</option>
            <option value="TRANSFER">⇄ Traslados</option>
          </select>
        </div>

        {/* Registros por página */}
        <div style={{display:"flex",flexDirection:"column",gap:4}}>
          <label style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.06em"}}>Mostrar</label>
          <select value={limit} onChange={e=>setLimit(Number(e.target.value))}
            style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg,minWidth:100}}>
            {[100,200,500,1000].map(n=><option key={n} value={n}>{n} filas</option>)}
          </select>
        </div>
      </div>

      {/* PAGINATION INFO */}
      <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap"}} className="no-print">
        <span style={{fontSize:13,color:C.mute}}>
          Mostrando <b style={{color:C.text}}>{rows.length}</b> de <b style={{color:C.text}}>{count}</b> movimientos en <b style={{color:C.text}}>{whName}</b>
        </span>
        <div style={{display:"flex",gap:6}}>
          <button type="button" onClick={()=>setOffset(Math.max(0,offset-limit))} disabled={!canPrev||loading} className="xb"
            style={{height:30,padding:"0 10px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:12,fontWeight:600,color:canPrev?C.text:C.mute,display:"inline-flex",alignItems:"center",gap:4}}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
            Anterior
          </button>
          <button type="button" onClick={()=>setOffset(offset+limit)} disabled={!canNext||loading} className="xb"
            style={{height:30,padding:"0 10px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:12,fontWeight:600,color:canNext?C.text:C.mute,display:"inline-flex",alignItems:"center",gap:4}}>
            Siguiente
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
        </div>
      </div>

      {/* TABLE */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
       <div style={{overflowX:"auto"}}>
        {/* Header */}
        <div style={{display:"grid",gridTemplateColumns:mob?"100px 80px 1fr 70px 80px":"140px 110px 1fr 90px 100px 180px 110px",columnGap:mob?6:10,padding:mob?"10px 10px":"10px 16px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em",minWidth:mob?420:undefined}}>
          <div>Fecha</div>
          <div style={{textAlign:"center"}}>Mov.</div>
          <div>Producto</div>
          <div style={{textAlign:"right"}}>Cant.</div>
          <div style={{textAlign:"right"}}>Stock</div>
          {!mob&&<div>Origen</div>}
          {!mob&&<div>Registrado por</div>}
        </div>

        {loading&&<div style={{padding:"48px 0",display:"flex",alignItems:"center",justifyContent:"center",gap:10,color:C.mute}}><Spinner size={16}/><span style={{fontSize:13}}>Cargando movimientos…</span></div>}

        {!loading&&rows.length===0&&(
          <div style={{padding:"48px 24px",textAlign:"center"}}>
            <div style={{fontSize:36,marginBottom:10}}>📋</div>
            <div style={{fontSize:15,fontWeight:700,marginBottom:4}}>Sin movimientos</div>
            <div style={{fontSize:13,color:C.mute}}>Cambia los filtros o el rango de fechas para ver resultados</div>
          </div>
        )}

        {!loading&&rows.map((r,i)=>{
          const href=refHref(r.ref_type,r.ref_id);
          const qty=Number(r.qty);
          const bal=Number(r.balance);
          const balNeg=bal<0;
          const qtyPositive=qty>0;
          const qtyColor=qtyPositive?C.green:(qty<0?C.red:C.mid);
          const dt=fDt(r.created_at);
          const moveStyle=getMoveStyle(r.move_type);
          return(
            <div key={r.id} className="krow" style={{display:"grid",gridTemplateColumns:mob?"100px 80px 1fr 70px 80px":"140px 110px 1fr 90px 100px 180px 110px",columnGap:mob?6:10,padding:mob?"12px 10px":"12px 16px",borderBottom:i<rows.length-1?`1px solid ${C.border}`:"none",alignItems:"start",minWidth:mob?420:undefined}}>

              {/* Fecha */}
              <div>
                <div style={{fontSize:mob?11:12,fontWeight:600,color:C.text}}>{dt.date}</div>
                <div style={{fontSize:mob?10:11,color:C.mute,marginTop:1}}>{dt.time}</div>
              </div>

              {/* Movimiento */}
              <div style={{display:"flex",justifyContent:"center",paddingTop:2}}>
                <MoveBadge type={r.move_type}/>
              </div>

              {/* Producto */}
              <div style={{minWidth:0}}>
                <div style={{fontWeight:600,fontSize:mob?12:13,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{r.product?.name??"—"}</div>
                {r.product?.sku&&<div style={{fontSize:mob?10:11,color:C.mute,marginTop:2,fontFamily:C.mono}}>{r.product.sku}</div>}
              </div>

              {/* Cantidad */}
              <div style={{textAlign:"right",fontWeight:800,fontSize:mob?13:14,fontVariantNumeric:"tabular-nums",fontFamily:C.mono,color:qtyColor,paddingTop:2}}>
                {qtyPositive?"+":""}{fQty(r.qty)}
              </div>

              {/* Stock final */}
              <div style={{textAlign:"right",paddingTop:2}}>
                <div style={{fontWeight:700,fontSize:mob?12:13,fontVariantNumeric:"tabular-nums",fontFamily:C.mono,color:balNeg?C.red:C.text}}>
                  {fQty(r.balance)}
                </div>
                {balNeg&&<div style={{fontSize:10,color:C.red,fontWeight:600,marginTop:1}}>⚠</div>}
              </div>

              {/* Origen — desktop only */}
              {!mob&&<div style={{display:"flex",flexDirection:"column",gap:3}}>
                <span style={{fontSize:12,fontWeight:600,color:C.mid}}>
                  {refText(r.ref_type,r.ref_id)}
                </span>
                {href&&(
                  <Link href={href} style={{fontSize:11,color:moveStyle.color,textDecoration:"none",fontWeight:600,display:"inline-flex",alignItems:"center",gap:3}}>
                    Ver detalle →
                  </Link>
                )}
                {r.note&&(
                  <span style={{fontSize:11,color:C.mute,fontStyle:"italic",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={r.note}>
                    {r.note}
                  </span>
                )}
              </div>}

              {/* Usuario — desktop only */}
              {!mob&&<div style={{fontSize:12,color:C.mid,paddingTop:2}}>
                {r.created_by?.username
                  ?<span style={{display:"inline-flex",alignItems:"center",gap:4}}>
                    <span style={{width:20,height:20,borderRadius:"50%",background:C.accentBg,border:`1px solid ${C.accentBd}`,display:"inline-flex",alignItems:"center",justifyContent:"center",fontSize:9,fontWeight:700,color:C.accent,flexShrink:0}}>
                      {(r.created_by.username[0]??"").toUpperCase()}
                    </span>
                    <span style={{overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{r.created_by.username}</span>
                  </span>
                  :"—"
                }
              </div>}
            </div>
          );
        })}
       </div>
      </div>
    </div>
  );
}
