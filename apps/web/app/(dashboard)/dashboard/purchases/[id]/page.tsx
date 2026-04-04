"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { Spinner } from "@/components/ui";
import { useIsMobile } from "@/hooks/useIsMobile";

// ─── Types ──────────────────────────────────────────────────────────────────
type Product={id:number;name:string;sku?:string|null};
type PurchaseLine={id:number;product:Product;qty:string;unit_cost:string;line_total_cost:string;note?:string|null};
type Purchase={
  id:number; created_at:string; warehouse_id:number;
  supplier_name:string; invoice_number:string; invoice_date:string|null;
  subtotal_cost:string; tax_amount:string; total_cost:string;
  status:"DRAFT"|"POSTED"|"VOID"|string; lines:PurchaseLine[];
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function toNum(v:string|number|null|undefined):number{if(v==null)return 0;const n=typeof v==="string"?Number(v):v;return Number.isFinite(n)?n:0;}
function fCLP(v:string|number|null|undefined):string{return Math.round(toNum(v)).toLocaleString("es-CL");}
function fDateTime(iso:string):string{const d=new Date(iso);if(isNaN(d.getTime()))return iso;return d.toLocaleString("es-CL",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"});}
function fDate(iso:string):string{const d=new Date(iso);if(isNaN(d.getTime()))return iso;return d.toLocaleDateString("es-CL",{day:"2-digit",month:"2-digit",year:"numeric"});}

// ─── Components ──────────────────────────────────────────────────────────────

type BtnV="primary"|"secondary"|"ghost"|"danger"|"success"|"teal"|"amber";
function Btn({children,onClick,variant="secondary",disabled,size="md",full}:{children:React.ReactNode;onClick?:()=>void;variant?:BtnV;disabled?:boolean;size?:"sm"|"md"|"lg";full?:boolean;}){
  const vs:Record<BtnV,React.CSSProperties>={
    primary:{background:C.accent,color:"#fff",border:`1px solid ${C.accent}`},
    secondary:{background:C.surface,color:C.text,border:`1px solid ${C.borderMd}`},
    ghost:{background:"transparent",color:C.mid,border:"1px solid transparent"},
    danger:{background:C.redBg,color:C.red,border:`1px solid ${C.redBd}`},
    success:{background:C.greenBg,color:C.green,border:`1px solid ${C.greenBd}`},
    teal:{background:C.teal,color:"#fff",border:`1px solid ${C.teal}`},
    amber:{background:C.amberBg,color:C.amber,border:`1px solid ${C.amberBd}`},
  };
  const h=size==="lg"?46:size==="sm"?30:38;
  const px=size==="lg"?"0 20px":size==="sm"?"0 10px":"0 14px";
  const fs=size==="lg"?14:size==="sm"?11:13;
  return(<button type="button" onClick={onClick} disabled={disabled} className="xb" style={{...vs[variant],display:"inline-flex",alignItems:"center",justifyContent:"center",gap:6,height:h,padding:px,borderRadius:C.r,fontSize:fs,fontWeight:600,letterSpacing:"0.01em",whiteSpace:"nowrap",width:full?"100%":undefined}}>{children}</button>);
}

function StatusBadge({status}:{status:string}){
  const s=(status||"").toUpperCase();
  const cfg:Record<string,{bg:string;bd:string;color:string;label:string}>={
    DRAFT: {bg:C.amberBg,bd:C.amberBd,color:C.amber, label:"Borrador"},
    POSTED:{bg:C.greenBg,bd:C.greenBd,color:C.green, label:"Posteada"},
    VOID:  {bg:C.redBg,  bd:C.redBd,  color:C.red,   label:"Anulada"},
  };
  const c=cfg[s]??{bg:C.bg,bd:C.border,color:C.mid,label:s};
  return(
    <span style={{display:"inline-flex",alignItems:"center",gap:5,padding:"4px 10px",borderRadius:99,fontSize:12,fontWeight:700,border:`1px solid ${c.bd}`,background:c.bg,color:c.color,letterSpacing:"0.03em"}}>
      <span style={{width:7,height:7,borderRadius:"50%",background:"currentColor",display:"inline-block"}}/>
      {c.label}
    </span>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function PurchaseDetailPage(){
  useGlobalStyles();
  const mob=useIsMobile();
  const params=useParams<{id:string}>();
  const router=useRouter();
  const id=Number(params?.id);

  const [purchase,setPurchase] = useState<Purchase|null>(null);
  const [loading,setLoading]   = useState(true);
  const [err,setErr]           = useState<string|null>(null);

  const [postBusy,setPostBusy] = useState(false);
  const [postErr,setPostErr]   = useState<string|null>(null);

  const [showVoid,setShowVoid] = useState(false);
  const [voidBusy,setVoidBusy] = useState(false);
  const [voidErr,setVoidErr]   = useState<string|null>(null);

  async function load(signal?:AbortSignal){
    if(!id){setErr("ID inválido");setLoading(false);return;}
    setLoading(true);setErr(null);
    try{
      const data=(await apiFetch(`/purchases/${id}/`,{signal} as any)) as Purchase;
      setPurchase(data);
    }catch(e:any){
      if(e?.name==="AbortError")return;
      const msg=e?.message??"";
      const friendly=msg.includes("matches the given query")?"No se encontró la orden de compra.":(msg||"No se pudo cargar el detalle");
      setErr(friendly);setPurchase(null);
    }finally{setLoading(false);}
  }

  useEffect(()=>{const ctrl=new AbortController();load(ctrl.signal);return()=>ctrl.abort();},[id]); // eslint-disable-line

  const status=(purchase?.status||"").toUpperCase();
  const isDraft=status==="DRAFT";
  const isPosted=status==="POSTED";
  const isVoid=status==="VOID";

  async function doPost(){
    setPostBusy(true);setPostErr(null);
    try{
      await apiFetch(`/purchases/${id}/post/`,{method:"POST"});
      const data=(await apiFetch(`/purchases/${id}/`)) as Purchase;
      setPurchase(data);
    }catch(e:any){setPostErr(e?.message??"No se pudo postear");}
    finally{setPostBusy(false);}
  }

  async function doVoid(){
    setVoidBusy(true);setVoidErr(null);
    try{
      await apiFetch(`/purchases/${id}/void/`,{method:"POST"});
      setShowVoid(false);
      const data=(await apiFetch(`/purchases/${id}/`)) as Purchase;
      setPurchase(data);
    }catch(e:any){
      setVoidErr(e instanceof ApiError?e.message:(e?.message??"No se pudo anular"));
    }finally{setVoidBusy(false);}
  }

  // Loading state
  if(loading){return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",display:"grid",placeItems:"center"}}>
      <div style={{display:"flex",alignItems:"center",gap:10,color:C.mute}}><Spinner size={18}/><span style={{fontSize:14}}>Cargando compra…</span></div>
    </div>
  );}

  // Error state
  if(err||!purchase){return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",display:"grid",placeItems:"center"}}>
      <div style={{textAlign:"center",padding:32}}>
        <div style={{fontSize:36,marginBottom:12}}>⚠️</div>
        <div style={{fontSize:15,fontWeight:700,marginBottom:6}}>No se pudo cargar la compra</div>
        <div style={{fontSize:13,color:C.mute,marginBottom:20}}>{err}</div>
        <Btn variant="secondary" onClick={()=>router.back()}>← Volver</Btn>
      </div>
    </div>
  );}

  const taxNum=toNum(purchase.tax_amount);

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6}}>
            <div style={{width:4,height:26,background:C.teal,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:mob?20:22,fontWeight:800,letterSpacing:"-0.04em"}}>
              Compra <span style={{fontFamily:C.mono}}>#{purchase.id}</span>
            </h1>
            <StatusBadge status={purchase.status}/>
          </div>
          <p style={{margin:0,fontSize:13,color:C.mute,paddingLeft:14}}>{fDateTime(purchase.created_at)}</p>
        </div>

        <div style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}>
          <Btn variant="ghost" onClick={()=>router.back()}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
            Volver
          </Btn>
          <Link href="/dashboard/purchases" style={{display:"inline-flex",alignItems:"center",gap:5,height:38,padding:"0 14px",borderRadius:C.r,fontSize:13,fontWeight:600,border:`1px solid ${C.borderMd}`,background:C.surface,color:C.mid,textDecoration:"none"}}>
            Ver todas
          </Link>

          {isDraft&&(
            <Btn variant="teal" onClick={doPost} disabled={postBusy||voidBusy}>
              {postBusy?<><Spinner size={14}/>Posteando…</>:<>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                Postear (aplicar stock)
              </>}
            </Btn>
          )}

          {isPosted&&(
            <Btn variant="danger" onClick={()=>{setVoidErr(null);setShowVoid(true);}} disabled={voidBusy||postBusy}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
              </svg>
              Anular
            </Btn>
          )}
        </div>
      </div>

      {/* ALERTS */}
      {isVoid&&(
        <div style={{padding:"11px 14px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13,fontWeight:600,display:"flex",gap:8,alignItems:"center"}}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{flexShrink:0}}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          Compra anulada — el stock fue revertido al inventario.
        </div>
      )}

      {isDraft&&(
        <div style={{padding:"10px 14px",borderRadius:C.r,border:`1px solid ${C.amberBd}`,background:C.amberBg,color:C.amber,fontSize:13,fontWeight:500,display:"flex",gap:8,alignItems:"center"}}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{flexShrink:0}}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          Borrador — el stock <b style={{marginLeft:3}}>aún no fue aplicado</b>. Posteá para actualizar el inventario.
        </div>
      )}

      {postErr&&(
        <div style={{padding:"11px 14px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13,display:"flex",gap:8,alignItems:"center"}}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{flexShrink:0}}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/></svg>
          {postErr}
          <button onClick={()=>setPostErr(null)} className="xb" style={{background:"none",border:"none",color:C.red,fontSize:16,cursor:"pointer",padding:0,marginLeft:"auto",lineHeight:1}}>✕</button>
        </div>
      )}

      {/* MAIN GRID */}
      <div style={{display:"grid",gridTemplateColumns:mob?"1fr":"1fr 300px",gap:16,alignItems:"start"}}>

        {/* LEFT: Lines table */}
        <div style={{display:"flex",flexDirection:"column",gap:12}}>
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh,overflowX:"auto" as const}}>
            {/* Header */}
            <div style={{display:"grid",gridTemplateColumns:"1fr 70px 120px 120px",columnGap:12,padding:mob?"10px 12px":"10px 18px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.08em",minWidth:mob?480:undefined}}>
              <div>Producto</div>
              <div style={{textAlign:"center"}}>Qty</div>
              <div style={{textAlign:"right"}}>Costo unit.</div>
              <div style={{textAlign:"right"}}>Subtotal</div>
            </div>

            {purchase.lines.map((l,i)=>(
              <div key={l.id} style={{display:"grid",gridTemplateColumns:"1fr 70px 120px 120px",columnGap:12,padding:mob?"13px 12px":"13px 18px",borderBottom:i<purchase.lines.length-1?`1px solid ${C.border}`:"none",alignItems:"center",minWidth:mob?480:undefined}}>
                <div>
                  <div style={{fontWeight:600,fontSize:14}}>{l.product?.name??`Producto #${l.id}`}</div>
                  <div style={{display:"flex",gap:10,marginTop:3}}>
                    {l.product?.sku&&<span style={{fontSize:11,color:C.mute,fontFamily:C.mono}}>{l.product.sku}</span>}
                    {l.note&&<span style={{fontSize:11,color:C.mute,fontStyle:"italic"}}>"{l.note}"</span>}
                  </div>
                </div>
                <div style={{textAlign:"center",fontWeight:600,fontSize:13,color:C.mid,fontFamily:C.mono}}>{l.qty}</div>
                <div style={{textAlign:"right",fontSize:13,fontVariantNumeric:"tabular-nums",color:C.mid}}>${fCLP(l.unit_cost)}</div>
                <div style={{textAlign:"right",fontWeight:800,fontSize:14,fontVariantNumeric:"tabular-nums"}}>${fCLP(l.line_total_cost)}</div>
              </div>
            ))}

            {/* Footer totals */}
            <div style={{background:C.bg,borderTop:`1px solid ${C.border}`,padding:"12px 18px",display:"flex",flexDirection:"column",gap:6}}>
              <div style={{display:"flex",justifyContent:"flex-end",gap:24,fontSize:13,color:C.mid}}>
                <span>Subtotal neto: <span style={{fontWeight:700,fontFamily:C.mono,color:C.text}}>${fCLP(purchase.subtotal_cost)}</span></span>
                {taxNum>0&&<span>IVA: <span style={{fontWeight:700,fontFamily:C.mono,color:C.text}}>${fCLP(purchase.tax_amount)}</span></span>}
              </div>
              <div style={{display:"flex",justifyContent:"flex-end",alignItems:"baseline",gap:6}}>
                <span style={{fontSize:13,color:C.mute}}>Total costo:</span>
                <span style={{fontSize:20,fontWeight:800,color:C.teal,fontVariantNumeric:"tabular-nums",letterSpacing:"-0.03em"}}>${fCLP(purchase.total_cost)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT: Info + Financials */}
        <div style={{display:"flex",flexDirection:"column",gap:12,position:mob?undefined:"sticky",top:mob?undefined:24}}>

          {/* Info */}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
            <div style={{padding:"12px 16px",background:C.bg,borderBottom:`1px solid ${C.border}`}}>
              <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Información</div>
            </div>
            <div style={{padding:"14px 16px",display:"flex",flexDirection:"column",gap:10}}>
              {[
                {label:"Proveedor",  value:purchase.supplier_name||<span style={{color:C.mute}}>Sin proveedor</span>},
                {label:"N° Factura", value:purchase.invoice_number?<span style={{fontFamily:C.mono,fontSize:12}}>{purchase.invoice_number}</span>:<span style={{color:C.mute}}>—</span>},
                {label:"Fecha fac.", value:purchase.invoice_date?fDate(purchase.invoice_date):<span style={{color:C.mute}}>—</span>},
                {label:"Bodega",     value:`#${purchase.warehouse_id}`},
                {label:"Creada",     value:fDateTime(purchase.created_at)},
                {label:"Estado",     value:<StatusBadge status={purchase.status}/>},
              ].map(f=>(
                <div key={f.label} style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:8}}>
                  <span style={{fontSize:12,color:C.mute,flexShrink:0}}>{f.label}</span>
                  <span style={{fontSize:13,fontWeight:600,textAlign:"right"}}>{f.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Financials */}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
            <div style={{padding:"12px 16px",background:C.bg,borderBottom:`1px solid ${C.border}`}}>
              <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Financiero</div>
            </div>
            <div style={{padding:"14px 16px",display:"flex",flexDirection:"column",gap:10}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
                <span style={{fontSize:12,color:C.mute}}>Subtotal neto</span>
                <span style={{fontSize:14,fontWeight:700,fontVariantNumeric:"tabular-nums"}}>${fCLP(purchase.subtotal_cost)}</span>
              </div>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
                <span style={{fontSize:12,color:C.mute}}>IVA / Impuesto</span>
                <span style={{fontSize:14,fontWeight:600,color:taxNum>0?C.text:C.mute,fontVariantNumeric:"tabular-nums"}}>{taxNum>0?`$${fCLP(purchase.tax_amount)}`:"—"}</span>
              </div>
              <div style={{height:1,background:C.border}}/>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
                <span style={{fontSize:13,color:C.mid}}>Total costo</span>
                <span style={{fontSize:20,fontWeight:800,color:C.teal,fontVariantNumeric:"tabular-nums",letterSpacing:"-0.02em"}}>${fCLP(purchase.total_cost)}</span>
              </div>
            </div>
          </div>

          {/* Action block for draft */}
          {isDraft&&(
            <Btn variant="teal" size="lg" full onClick={doPost} disabled={postBusy||voidBusy}>
              {postBusy?<><Spinner size={16}/>Posteando…</>:<>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                Postear — aplicar al stock
              </>}
            </Btn>
          )}
        </div>
      </div>

      {/* VOID MODAL */}
      {showVoid&&(
        <div className="bd-in" style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.4)",display:"grid",placeItems:"center",padding:20,zIndex:60}}>
          <div className="m-in" style={{width:"min(480px,100%)",background:C.surface,borderRadius:C.rLg,border:`1px solid ${C.border}`,boxShadow:C.shLg,overflow:"hidden"}}>
            <div style={{height:3,background:C.red}}/>
            <div style={{padding:"20px 24px"}}>
              <div style={{fontSize:15,fontWeight:700,marginBottom:4}}>Anular compra #{id}</div>
              <div style={{fontSize:13,color:C.mute,marginBottom:20,lineHeight:1.6}}>
                Esta acción revertirá el stock de todos los productos ingresados y marcará la compra como anulada. Esta operación no se puede deshacer.
              </div>

              {voidErr&&(
                <div style={{marginBottom:14,padding:"9px 12px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13}}>
                  {voidErr}
                </div>
              )}

              <div style={{display:"flex",justifyContent:"flex-end",gap:8}}>
                <Btn variant="ghost" onClick={()=>{setShowVoid(false);setVoidErr(null);}} disabled={voidBusy}>Cancelar</Btn>
                <Btn variant="danger" onClick={doVoid} disabled={voidBusy}>
                  {voidBusy?<><Spinner/>Anulando…</>:"Confirmar anulación"}
                </Btn>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}