"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";
import { Spinner } from "@/components/ui";
import { useIsMobile } from "@/hooks/useIsMobile";
type Warehouse={id:number;name:string;is_active:boolean;warehouse_type?:string};
function toNum(v:string|number|null|undefined):number{if(v==null)return NaN;const n=Number(v);return Number.isFinite(n)?n:NaN;}
function sanitizeDelta(v:string):string{let c=v.replace(/[^0-9.\-]/g,"");c=c.replace(/(?!^)-/g,"");const p=c.split(".");return p.length<=2?c:`${p[0]}.${p.slice(1).join("")}`;}

function FieldGroup({label,children,hint,err,req}:{label:string;children:React.ReactNode;hint?:string;err?:string|null;req?:boolean}){
  return(
    <div style={{display:"flex",flexDirection:"column",gap:5}}>
      <label style={{fontSize:11,fontWeight:700,color:C.mid,textTransform:"uppercase",letterSpacing:"0.06em"}}>
        {label}{req&&<span style={{color:C.red,marginLeft:3}}>*</span>}
      </label>
      {children}
      {hint&&!err&&<div style={{fontSize:11,color:C.mute}}>{hint}</div>}
      {err&&<div style={{fontSize:11,color:C.red,fontWeight:600}}>{err}</div>}
    </div>
  );
}

function iS():React.CSSProperties{
  return{width:"100%",height:38,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.surface};
}

export default function StockAdjustPage(){
  useGlobalStyles();
  const mob = useIsMobile();
  const [warehouses,setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId,setWarehouseId] = useState<number|"">("");
  const [productId,setProductId] = useState("");
  const [qty,setQty] = useState("");
  const [note,setNote] = useState("");
  const [busy,setBusy] = useState(false);
  const [ok,setOk] = useState<string|null>(null);
  const [err,setErr] = useState<string|null>(null);

  useEffect(()=>{
    (async()=>{try{const ws=(await apiFetch("/core/warehouses/")) as Warehouse[];const arr=Array.isArray(ws)?ws:[];setWarehouses(arr);if(!warehouseId&&arr.length)setWarehouseId(arr[0].id);}catch{setWarehouses([]);}})();
  },[]); // eslint-disable-line

  const qtyNum=toNum(qty);
  const qtyOk=!isNaN(qtyNum)&&qtyNum!==0;
  const pidNum=Number(productId);
  const pidOk=Number.isFinite(pidNum)&&pidNum>0;

  async function submit(){
    setOk(null);setErr(null);
    if(!warehouseId)return setErr("Selecciona una bodega.");
    if(!pidOk)return setErr("product_id inválido.");
    if(!qtyOk)return setErr("qty debe ser distinto de 0.");
    setBusy(true);
    try{
      const res=await apiFetch("/inventory/stock/adjust/",{method:"POST",body:JSON.stringify({warehouse_id:warehouseId,product_id:pidNum,qty:qtyNum,note:note.trim()})});
      setOk(`Ajuste aplicado. Nuevo stock: ${res?.new_stock??"—"}`);
      setProductId("");setQty("");setNote("");
      setTimeout(()=>setOk(null),4000);
    }catch(e:any){
      if(e instanceof ApiError&&e.status===409){
        setErr(`Stock insuficiente. Actual: ${e.data?.current_on_hand??"?"}, delta: ${e.data?.attempt_delta??"?"}, resultante: ${e.data?.would_be??"?"}`);
      }else{setErr(e?.message??"No se pudo ajustar");}
    }finally{setBusy(false);}
  }

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
            <div style={{width:4,height:26,background:C.accent,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:22,fontWeight:800,letterSpacing:"-0.04em"}}>Ajuste de stock</h1>
          </div>
          <p style={{margin:0,fontSize:13,color:C.mute,paddingLeft:14}}>Qty positivo para entrada · negativo para descuento · no permite quedar en negativo</p>
        </div>
        <Link href="/dashboard/stock" className="xb" style={{height:36,padding:"0 14px",borderRadius:C.r,border:`1px solid ${C.borderMd}`,background:C.surface,fontSize:13,fontWeight:600,color:C.mid,display:"inline-flex",alignItems:"center",gap:6,textDecoration:"none"}}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
          Volver
        </Link>
      </div>

      {/* FEEDBACK */}
      {ok&&(
        <div style={{padding:"10px 14px",borderRadius:C.r,border:`1px solid ${C.greenBd}`,background:C.greenBg,color:C.green,fontSize:13,fontWeight:600,display:"flex",gap:8,alignItems:"center"}}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          {ok}
        </div>
      )}
      {err&&(
        <div style={{padding:"10px 14px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13,display:"flex",gap:8,alignItems:"center"}}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{flexShrink:0}}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/></svg>
          <span style={{flex:1}}>{err}</span>
          <button onClick={()=>setErr(null)} className="xb" style={{background:"none",border:"none",color:C.red,fontSize:15,cursor:"pointer",padding:0}}>✕</button>
        </div>
      )}

      {/* FORM */}
      <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,boxShadow:C.sh,overflow:"hidden",maxWidth:mob?undefined:560}}>
        <div style={{padding:"12px 18px",borderBottom:`1px solid ${C.border}`,background:C.bg}}>
          <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Datos del ajuste</div>
        </div>
        <div style={{padding:"20px 18px",display:"flex",flexDirection:"column",gap:14}}>
          <FieldGroup label="Bodega" req>
            <select value={warehouseId} onChange={e=>setWarehouseId(e.target.value?Number(e.target.value):"")} style={iS()} disabled={busy}>
              <option value="">Seleccionar…</option>
              {warehouses.map(w=><option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
            </select>
          </FieldGroup>

          <FieldGroup label="Product ID" req err={productId.trim()&&!pidOk?"Debe ser un número entero positivo":null}>
            <input value={productId} onChange={e=>setProductId(e.target.value)} placeholder="Ej: 42" inputMode="numeric"
              style={{...iS(),fontFamily:C.mono}} disabled={busy}
              onKeyDown={e=>{if(e.key==="Enter")submit();}}/>
          </FieldGroup>

          <FieldGroup label="Delta (qty)" req hint="Positivo para agregar, negativo para descontar. Ej: 10 o -3"
            err={qty.trim()&&(!qtyOk)?"Ingresa un número distinto de 0":null}>
            <input value={qty} onChange={e=>setQty(sanitizeDelta(e.target.value))} placeholder="Ej: 5 o -2"
              inputMode="decimal" style={{...iS(),fontFamily:C.mono}} disabled={busy}
              onKeyDown={e=>{if(e.key==="Enter")submit();}}/>
          </FieldGroup>

          <FieldGroup label="Nota" hint="Motivo del ajuste (opcional)">
            <input value={note} onChange={e=>setNote(e.target.value)} placeholder="Ej: Carga inicial · Corrección · Merma"
              style={iS()} disabled={busy}/>
          </FieldGroup>

          <div style={{display:"flex",justifyContent:"flex-end",paddingTop:4}}>
            <button type="button" onClick={submit} disabled={busy||!warehouseId||!pidOk||!qtyOk} className="xb"
              style={{height:42,padding:"0 20px",borderRadius:C.r,background:C.accent,color:"#fff",border:`1px solid ${C.accent}`,fontSize:14,fontWeight:600,display:"inline-flex",alignItems:"center",gap:8}}>
              {busy?<><Spinner size={15}/>Guardando…</>:<>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Aplicar ajuste
              </>}
            </button>
          </div>
        </div>
      </div>

      {/* HELPER */}
      <div style={{maxWidth:mob?undefined:560,padding:"12px 14px",borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,fontSize:13,color:C.mid,lineHeight:1.6}}>
        <div style={{fontWeight:700,color:C.text,marginBottom:4}}>¿Dónde encuentro el Product ID?</div>
        Ve a <Link href="/dashboard/catalog" style={{color:C.accent,fontWeight:600,textDecoration:"none"}}>Catálogo</Link>, busca el producto y copia el número en la columna ID. También aparece en la URL del detalle del producto.
      </div>
    </div>
  );
}