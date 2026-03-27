"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

type Warehouse={id:number;name:string;is_active:boolean;warehouse_type?:string};
type ReportProduct={id:number;name:string;sku:string|null;barcode:string|null};
type ReportRow={product:ReportProduct;in_qty:string;out_qty:string;adj_qty:string;net_qty:string;moves_count:number};
type ReportResponse={count:number;next:string|null;previous:string|null;results:{warehouse_id:number;results:ReportRow[]}};
function fQty(v:string):string{const n=Number(v);if(!Number.isFinite(n))return v;return n.toLocaleString("es-CL",{maximumFractionDigits:3});}
function isoDate(d:Date):string{return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;}

const PAGE_CSS = `.krow{transition:background 0.1s ease}.krow:hover{background:#F4F4F5}`;

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}

function toCsv(rows:ReportRow[]):string{
  const hdr=["Producto","SKU","Barcode","IN","OUT","ADJ","NETO","#Movs"];
  const esc=(s:any)=>{const v=s==null?"":String(s);return /[",\n]/.test(v)?`"${v.replace(/"/g,'""')}"`:v;};
  const lines=rows.map(r=>[r.product?.name??"",r.product?.sku??"",r.product?.barcode??"",r.in_qty,r.out_qty,r.adj_qty,r.net_qty,r.moves_count]);
  return[hdr,...lines].map(l=>l.map(esc).join(",")).join("\n");
}
function dlCsv(name:string,csv:string){const b=new Blob([csv],{type:"text/csv;charset=utf-8;"});const u=URL.createObjectURL(b);const a=document.createElement("a");a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(u);}
function Spinner({size=14}:{size?:number}){return(<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{animation:"spin 0.7s linear infinite",display:"block",flexShrink:0}}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>);}

export default function KardexReportPage(){
  useGlobalStyles(PAGE_CSS);
  const mob = useIsMobile();
  const [warehouses,setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId,setWarehouseId] = useState<number|null>(null);
  const [q,setQ] = useState("");
  const [from,setFrom] = useState(()=>isoDate(new Date(Date.now()-7*864e5)));
  const [to,setTo]     = useState(()=>isoDate(new Date()));
  const [limit,setLimit] = useState(200);
  const [offset,setOffset] = useState(0);
  const [rows,setRows] = useState<ReportRow[]>([]);
  const [count,setCount] = useState(0);
  const [loading,setLoading] = useState(false);
  const [err,setErr] = useState<string|null>(null);

  useEffect(()=>{
    (async()=>{try{const ws=(await apiFetch("/core/warehouses/")) as Warehouse[];const list=Array.isArray(ws)?ws:[];setWarehouses(list);if(list.length&&!warehouseId)setWarehouseId(list[0].id);}catch(e:any){setErr(e?.message??"Error cargando bodegas");}})();
  },[]); // eslint-disable-line

  useEffect(()=>setOffset(0),[warehouseId,q,from,to,limit]);

  const endpoint=useMemo(()=>{
    if(!warehouseId)return null;
    const p=new URLSearchParams();
    p.set("warehouse_id",String(warehouseId));p.set("limit",String(limit));p.set("offset",String(offset));
    const qq=q.trim();if(qq)p.set("q",qq);
    if(from)p.set("from",from);if(to)p.set("to",to);
    return `/inventory/kardex/report/?${p.toString()}`;
  },[warehouseId,q,from,to,limit,offset]);

  async function load(){
    if(!endpoint)return;
    setLoading(true);setErr(null);
    try{
      const data=(await apiFetch(endpoint)) as ReportResponse;
      setRows(data?.results?.results??[]);setCount(data?.count??0);
    }catch(e:any){setErr(e?.message??"Error cargando reporte");setRows([]);setCount(0);}
    finally{setLoading(false);}
  }

  useEffect(()=>{if(!endpoint)return;const t=setTimeout(()=>load(),250);return()=>clearTimeout(t);},[endpoint]); // eslint-disable-line

  const canPrev=offset>0;
  const canNext=offset+limit<count;
  const whName=warehouses.find(w=>w.id===warehouseId)?.name??`#${warehouseId}`;

  const totals=useMemo(()=>{
    let inS=0,outS=0,adjS=0,netS=0;
    for(const r of rows){inS+=Number(r.in_qty)||0;outS+=Number(r.out_qty)||0;adjS+=Number(r.adj_qty)||0;netS+=Number(r.net_qty)||0;}
    return{inS,outS,adjS,netS};
  },[rows]);

  const fBtn=(style?:React.CSSProperties)=>({height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6,...style});

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
            <div style={{width:4,height:26,background:C.accent,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:22,fontWeight:800,letterSpacing:"-0.04em"}}>Reporte Kardex</h1>
          </div>
          <p style={{margin:0,fontSize:13,color:C.mute,paddingLeft:14}}>Resumen por producto: IN / OUT / ADJ / NETO (rango de fechas)</p>
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          <Link href="/dashboard/inventory/kardex" style={{...fBtn(),textDecoration:"none",color:C.mid}}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
            Kardex
          </Link>
          <button type="button" onClick={()=>dlCsv(`kardex_report_wh${warehouseId}.csv`,toCsv(rows))} disabled={loading||rows.length===0} className="xb" style={fBtn()}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            CSV
          </button>
          <button type="button" onClick={load} disabled={loading||!warehouseId} className="xb" style={fBtn()}>
            {loading?<Spinner/>:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>}
            Recargar
          </button>
        </div>
      </div>

      {err&&<div style={{padding:"10px 12px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13}}>{err}</div>}

      {/* FILTERS */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,padding:"12px 16px",boxShadow:C.sh,display:"flex",gap:10,flexWrap:"wrap",alignItems:"flex-end"}}>
        {[
          {label:"Bodega *",content:(
            <select value={warehouseId??""} onChange={e=>setWarehouseId(e.target.value?Number(e.target.value):null)}
              style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg,minWidth:180}}>
              {warehouses.length===0?<option value="">(sin bodegas)</option>:warehouses.map(w=><option key={w.id} value={w.id}>#{w.id} — {w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
            </select>
          )},
          {label:"Desde",content:<input type="date" value={from} onChange={e=>setFrom(e.target.value)} style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg}}/>},
          {label:"Hasta",content:<input type="date" value={to} onChange={e=>setTo(e.target.value)} style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg}}/>},
          {label:"Buscar",content:(
            <div style={{position:"relative",minWidth:220}}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round"
                style={{position:"absolute",left:9,top:"50%",transform:"translateY(-50%)",pointerEvents:"none"}}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Nombre / SKU / Barcode…"
                style={{height:36,padding:"0 10px 0 30px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg,width:"100%"}}/>
            </div>
          )},
          {label:"Por página",content:(
            <select value={limit} onChange={e=>setLimit(Number(e.target.value))}
              style={{height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.bg,minWidth:100}}>
              {[100,200,500,1000].map(n=><option key={n} value={n}>{n}</option>)}
            </select>
          )},
        ].map(f=>(
          <div key={f.label} style={{display:"flex",flexDirection:"column",gap:4}}>
            <label style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.06em"}}>{f.label}</label>
            {f.content}
          </div>
        ))}
      </div>

      {/* TOTALS STRIP */}
      {!loading&&rows.length>0&&(
        <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,padding:"12px 18px",boxShadow:C.sh,display:"flex",gap:24,flexWrap:"wrap",alignItems:"center"}}>
          <span style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Totales ({rows.length} prods · {whName})</span>
          {[
            {label:"IN",  value:fQty(String(totals.inS)),  color:C.green},
            {label:"OUT", value:fQty(String(totals.outS)), color:C.red},
            {label:"ADJ", value:fQty(String(totals.adjS)), color:C.accent},
            {label:"NETO",value:fQty(String(totals.netS)), color:totals.netS<0?C.red:C.text},
          ].map(t=>(
            <div key={t.label} style={{display:"flex",alignItems:"baseline",gap:6}}>
              <span style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.06em"}}>{t.label}</span>
              <span style={{fontSize:16,fontWeight:800,color:t.color,fontVariantNumeric:"tabular-nums",fontFamily:C.mono}}>{t.value}</span>
            </div>
          ))}
          <div style={{marginLeft:"auto",display:"flex",gap:6}}>
            <button type="button" onClick={()=>setOffset(Math.max(0,offset-limit))} disabled={!canPrev||loading} className="xb"
              style={{height:30,padding:"0 10px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:12,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:4}}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
              Prev
            </button>
            <span style={{fontSize:12,color:C.mute,display:"flex",alignItems:"center",gap:4}}>
              <b style={{color:C.text}}>{rows.length}</b> / <b style={{color:C.text}}>{count}</b>
            </span>
            <button type="button" onClick={()=>setOffset(offset+limit)} disabled={!canNext||loading} className="xb"
              style={{height:30,padding:"0 10px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:12,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:4}}>
              Next
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </div>
        </div>
      )}

      {/* TABLE */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
       <div style={{overflowX:"auto"}}>
        <div style={{display:"grid",gridTemplateColumns:"1fr 110px 140px 90px 90px 90px 100px 70px",columnGap:10,padding:"10px 18px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.08em",minWidth:mob?780:undefined}}>
          <div>Producto</div><div>SKU</div><div>Barcode</div>
          <div style={{textAlign:"right",color:C.green}}>IN</div>
          <div style={{textAlign:"right",color:C.red}}>OUT</div>
          <div style={{textAlign:"right",color:C.accent}}>ADJ</div>
          <div style={{textAlign:"right"}}>NETO</div>
          <div style={{textAlign:"right"}}>#Movs</div>
        </div>

        {loading&&<div style={{padding:"48px 0",display:"flex",alignItems:"center",justifyContent:"center",gap:10,color:C.mute}}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{animation:"spin 0.7s linear infinite"}}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg><span style={{fontSize:13}}>Cargando…</span></div>}

        {!loading&&rows.length===0&&(
          <div style={{padding:"48px 24px",textAlign:"center"}}>
            <div style={{fontSize:32,marginBottom:8}}>📊</div>
            <div style={{fontSize:14,fontWeight:700,marginBottom:4}}>Sin datos</div>
            <div style={{fontSize:13,color:C.mute}}>Ajusta los filtros o el rango de fechas</div>
          </div>
        )}

        {!loading&&rows.map((r,i)=>{
          const net=Number(r.net_qty);
          const netNeg=!isNaN(net)&&net<0;
          return(
            <div key={r.product.id} className="krow" style={{display:"grid",gridTemplateColumns:"1fr 110px 140px 90px 90px 90px 100px 70px",columnGap:10,padding:"11px 18px",borderBottom:i<rows.length-1?`1px solid ${C.border}`:"none",alignItems:"center",minWidth:mob?780:undefined}}>
              <div>
                <div style={{fontWeight:600,fontSize:13,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{r.product.name}</div>
                <div style={{fontSize:10,color:C.mute,marginTop:1}}>#{r.product.id}</div>
              </div>
              <div style={{fontSize:12,color:C.mid,fontFamily:C.mono,overflow:"hidden",textOverflow:"ellipsis"}}>{r.product.sku||"-"}</div>
              <div style={{fontSize:11,color:C.mute,fontFamily:C.mono,overflow:"hidden",textOverflow:"ellipsis"}}>{r.product.barcode||"-"}</div>
              <div style={{textAlign:"right",fontWeight:700,fontSize:13,color:C.green,fontVariantNumeric:"tabular-nums",fontFamily:C.mono}}>{fQty(r.in_qty)}</div>
              <div style={{textAlign:"right",fontWeight:700,fontSize:13,color:C.red,fontVariantNumeric:"tabular-nums",fontFamily:C.mono}}>{fQty(r.out_qty)}</div>
              <div style={{textAlign:"right",fontWeight:600,fontSize:13,color:C.accent,fontVariantNumeric:"tabular-nums",fontFamily:C.mono}}>{fQty(r.adj_qty)}</div>
              <div style={{textAlign:"right",fontWeight:800,fontSize:14,color:netNeg?C.red:C.text,fontVariantNumeric:"tabular-nums",fontFamily:C.mono}}>{fQty(r.net_qty)}</div>
              <div style={{textAlign:"right",fontSize:12,color:C.mute}}>{r.moves_count}</div>
            </div>
          );
        })}
       </div>
      </div>
    </div>
  );
}