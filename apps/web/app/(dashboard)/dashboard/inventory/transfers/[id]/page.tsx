"use client";

import Link from "next/link";
import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Spinner } from "@/components/ui";

type TransferProduct={id:number;name:string;sku:string|null;barcode:string|null};
type TransferLine={id:number;product:TransferProduct;qty:string;note:string|null};
type TransferMove={id:number;created_at:string;warehouse_id:number;move_type:string;product_id:number;qty:string;note:string|null;created_by:string|null};
type TransferDetail={
  id:number; created_at:string; note:string|null;
  from_warehouse:{id:number;name:string};
  to_warehouse:{id:number;name:string};
  created_by:{id:number;username:string|null}|null;
  lines:TransferLine[]; moves:TransferMove[];
};

function fDt(iso:string):string{const d=new Date(iso);return isNaN(d.getTime())?iso:d.toLocaleString("es-CL");}
function fQty(v:string):string{const n=Number(v);return !Number.isFinite(n)?v:n.toLocaleString("es-CL",{maximumFractionDigits:3});}

function MoveBadge({type}:{type:string}){
  const t=(type||"").toUpperCase();
  const cfg:Record<string,{bg:string;bd:string;color:string}>={
    IN: {bg:C.greenBg,bd:C.greenBd,color:C.green},
    OUT:{bg:C.redBg,  bd:C.redBd,  color:C.red},
    ADJ:{bg:C.accentBg,bd:C.accentBd,color:C.accent},
    TRANSFER:{bg:C.skyBg,bd:C.skyBd,color:C.sky},
    TRANSFER_IN: {bg:C.greenBg,bd:C.greenBd,color:C.green},
    TRANSFER_OUT:{bg:C.redBg,  bd:C.redBd,  color:C.red},
  };
  const c=cfg[t]??{bg:C.bg,bd:C.border,color:C.mid};
  return(<span style={{display:"inline-flex",padding:"2px 7px",borderRadius:99,fontSize:11,fontWeight:700,border:`1px solid ${c.bd}`,background:c.bg,color:c.color,letterSpacing:"0.03em",whiteSpace:"nowrap"}}>{t||"—"}</span>);
}

export default function TransferDetailPage(){
  useGlobalStyles();
  const mob=useIsMobile();
  const params=useParams();
  const id=String((params as any)?.id??"");
  const [data,setData] = useState<TransferDetail|null>(null);
  const [err,setErr]   = useState<string|null>(null);
  const [loading,setLoading] = useState(false);

  async function load(){
    if(!id)return;
    setLoading(true);setErr(null);
    try{const d=(await apiFetch(`/inventory/transfers/${id}/`)) as TransferDetail;setData(d);}
    catch(e:any){
      const msg=e?.message??"";
      const friendly=msg.includes("matches the given query")?"No se encontró la transferencia.":(msg||"No se pudo cargar la transferencia");
      setErr(friendly);setData(null);
    }
    finally{setLoading(false);}
  }

  useEffect(()=>{load();},[id]); // eslint-disable-line

  // ── Loading ────────────────────────────────────────────────────────────────
  if(loading&&!data){return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",display:"grid",placeItems:"center"}}>
      <div style={{display:"flex",alignItems:"center",gap:10,color:C.mute}}><Spinner/><span style={{fontSize:14}}>Cargando transferencia…</span></div>
    </div>
  );}

  // ── Error ──────────────────────────────────────────────────────────────────
  if(err&&!data){return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",display:"grid",placeItems:"center"}}>
      <div style={{textAlign:"center",padding:32}}>
        <div style={{fontSize:36,marginBottom:12}}>⚠️</div>
        <div style={{fontSize:15,fontWeight:700,marginBottom:6}}>Error cargando transferencia</div>
        <div style={{fontSize:13,color:C.mute,marginBottom:20}}>{err}</div>
        <Link href="/dashboard/inventory/kardex" style={{display:"inline-flex",alignItems:"center",gap:6,height:36,padding:"0 14px",borderRadius:C.r,fontSize:13,fontWeight:600,border:`1px solid ${C.borderMd}`,background:C.surface,color:C.mid,textDecoration:"none"}}>
          ← Kardex
        </Link>
      </div>
    </div>
  );}

  if(!data)return null;

  const totalQty=data.lines?.reduce((a,l)=>a+(Number(l.qty)||0),0)??0;

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6}}>
            <div style={{width:4,height:26,background:C.sky,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:mob?20:22,fontWeight:800,letterSpacing:"-0.04em"}}>
              Transferencia <span style={{fontFamily:C.mono}}>#{data.id}</span>
            </h1>
          </div>
          <div style={{paddingLeft:14,display:"flex",flexDirection:"column",gap:3}}>
            <div style={{fontSize:13,color:C.mute}}>{fDt(data.created_at)}</div>
            <div style={{display:"flex",alignItems:"center",gap:8,fontSize:13}}>
              <span style={{fontWeight:600,color:C.text}}>{data.from_warehouse?.name}</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.sky} strokeWidth="2.5" strokeLinecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
              <span style={{fontWeight:600,color:C.text}}>{data.to_warehouse?.name}</span>
            </div>
          </div>
        </div>
        <div style={{display:"flex",gap:8}}>
          <button type="button" onClick={load} disabled={loading} className="xb"
            style={{height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6}}>
            {loading?<Spinner size={14}/>:<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>}
            Recargar
          </button>
          <Link href="/dashboard/inventory/kardex" className="xb" style={{height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.borderMd}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6,textDecoration:"none"}}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
            Kardex
          </Link>
        </div>
      </div>

      {/* MAIN GRID */}
      <div style={{display:"grid",gridTemplateColumns:mob?"1fr":"1fr 280px",gap:16,alignItems:"start"}}>

        {/* LEFT: lines + moves */}
        <div style={{display:"flex",flexDirection:"column",gap:14}}>

          {/* LINES */}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh,overflowX:"auto" as const}}>
            <div style={{padding:mob?"12px 12px":"12px 18px",borderBottom:`1px solid ${C.border}`,background:C.bg,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Líneas · {data.lines?.length??0}</div>
              <span style={{fontSize:12,color:C.mute}}>Total qty: <span style={{fontWeight:700,color:C.text,fontFamily:C.mono}}>{fQty(String(totalQty))}</span></span>
            </div>

            {!data.lines?.length?(
              <div style={{padding:"32px 18px",textAlign:"center",color:C.mute,fontSize:13}}>Sin líneas</div>
            ):(
              <>
                <div style={{display:"grid",gridTemplateColumns:"1fr 90px 120px 1fr",columnGap:12,padding:mob?"9px 12px":"9px 18px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em",minWidth:mob?480:undefined}}>
                  <div>Producto</div><div>SKU</div><div style={{textAlign:"right"}}>Cantidad</div><div>Nota</div>
                </div>
                {data.lines.map((l,i)=>(
                  <div key={l.id} style={{display:"grid",gridTemplateColumns:"1fr 90px 120px 1fr",columnGap:12,padding:mob?"12px 12px":"12px 18px",borderBottom:i<data.lines.length-1?`1px solid ${C.border}`:"none",alignItems:"center",minWidth:mob?480:undefined}}>
                    <div>
                      <div style={{fontWeight:600,fontSize:13}}>{l.product?.name??`Producto #${l.id}`}</div>
                      <div style={{display:"flex",gap:10,marginTop:2,fontSize:11,color:C.mute}}>
                        <span>ID #{l.product?.id}</span>
                        {l.product?.barcode&&<span style={{fontFamily:C.mono}}>BC: {l.product.barcode}</span>}
                      </div>
                    </div>
                    <div style={{fontSize:12,color:C.mid,fontFamily:C.mono}}>{l.product?.sku||"-"}</div>
                    <div style={{textAlign:"right",fontWeight:800,fontSize:14,fontVariantNumeric:"tabular-nums",fontFamily:C.mono,color:C.sky}}>{fQty(l.qty)}</div>
                    <div style={{fontSize:12,color:C.mute,fontStyle:l.note?"normal":"italic"}}>{l.note||"—"}</div>
                  </div>
                ))}
              </>
            )}
          </div>

          {/* MOVES */}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh,overflowX:"auto" as const}}>
            <div style={{padding:mob?"12px 12px":"12px 18px",borderBottom:`1px solid ${C.border}`,background:C.bg}}>
              <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Movimientos de stock · {data.moves?.length??0}</div>
              <div style={{fontSize:11,color:C.mute,marginTop:2}}>ref_type = TRANSFER</div>
            </div>

            {!data.moves?.length?(
              <div style={{padding:"28px 18px",color:C.mute,fontSize:13}}>
                Sin movimientos asociados — si la transferencia no registró ref_id no aparecerán aquí.
              </div>
            ):(
              <>
                <div style={{display:"grid",gridTemplateColumns:mob?"110px 60px 70px":"150px 90px 70px 80px 90px 1fr",columnGap:mob?6:10,padding:mob?"9px 10px":"9px 18px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>
                  <div>Fecha</div><div style={{textAlign:"center"}}>{mob?"Tipo":"Bodega"}</div>{!mob&&<div style={{textAlign:"center"}}>Tipo</div>}
                  <div style={{textAlign:"right"}}>Cantidad</div>{!mob&&<div>Usuario</div>}{!mob&&<div>Nota</div>}
                </div>
                {data.moves.map((m,i)=>(
                  <div key={m.id} style={{display:"grid",gridTemplateColumns:mob?"110px 60px 70px":"150px 90px 70px 80px 90px 1fr",columnGap:mob?6:10,padding:mob?"11px 10px":"11px 18px",borderBottom:i<data.moves.length-1?`1px solid ${C.border}`:"none",alignItems:"center"}}>
                    <div style={{fontSize:mob?10:11,color:C.mute}}>{fDt(m.created_at)}</div>
                    {mob?<div style={{display:"flex",justifyContent:"center"}}><MoveBadge type={m.move_type}/></div>:<div style={{fontSize:12,color:C.mid}}>#{m.warehouse_id}</div>}
                    {!mob&&<div style={{display:"flex",justifyContent:"center"}}><MoveBadge type={m.move_type}/></div>}
                    <div style={{textAlign:"right",fontWeight:700,fontSize:mob?12:13,fontVariantNumeric:"tabular-nums",fontFamily:C.mono}}>{fQty(m.qty)}</div>
                    {!mob&&<div style={{fontSize:12,color:C.mute}}>{m.created_by||"-"}</div>}
                    {!mob&&<div style={{fontSize:12,color:C.mute,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{m.note||"-"}</div>}
                  </div>
                ))}
              </>
            )}
          </div>
        </div>

        {/* RIGHT: metadata */}
        <div style={{display:"flex",flexDirection:"column",gap:12,position:mob?undefined:"sticky",top:mob?undefined:24}}>
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
            <div style={{padding:"12px 16px",background:C.bg,borderBottom:`1px solid ${C.border}`}}>
              <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Información</div>
            </div>
            <div style={{padding:"14px 16px",display:"flex",flexDirection:"column",gap:10}}>
              {[
                {label:"Creada", value:fDt(data.created_at)},
                {label:"Creada por", value:data.created_by?.username||<span style={{color:C.mute}}>Sistema</span>},
                {label:"Nota", value:data.note||<span style={{color:C.mute}}>—</span>},
              ].map(f=>(
                <div key={f.label} style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:8}}>
                  <span style={{fontSize:12,color:C.mute,flexShrink:0}}>{f.label}</span>
                  <span style={{fontSize:13,fontWeight:600,textAlign:"right"}}>{f.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Route card */}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
            <div style={{padding:"12px 16px",background:C.bg,borderBottom:`1px solid ${C.border}`}}>
              <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Ruta</div>
            </div>
            <div style={{padding:"16px",display:"flex",flexDirection:"column",alignItems:"center",gap:8}}>
              <div style={{width:"100%",padding:"10px 12px",borderRadius:C.r,background:C.skyBg,border:`1px solid ${C.skyBd}`,textAlign:"center",fontSize:13,fontWeight:700,color:C.sky}}>
                {data.from_warehouse?.name}
              </div>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={C.sky} strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12l7 7 7-7"/></svg>
              <div style={{width:"100%",padding:"10px 12px",borderRadius:C.r,background:C.greenBg,border:`1px solid ${C.greenBd}`,textAlign:"center",fontSize:13,fontWeight:700,color:C.green}}>
                {data.to_warehouse?.name}
              </div>
              <div style={{marginTop:4,fontSize:13,color:C.mute}}>
                <span style={{fontWeight:700,color:C.text,fontFamily:C.mono}}>{fQty(String(totalQty))}</span> unidades · {data.lines?.length??0} línea{(data.lines?.length??0)!==1?"s":""}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}