"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api";
import { C } from "@/lib/theme";
import { useGlobalStyles } from "@/lib/useGlobalStyles";

function useIsMobile(){const[m,setM]=useState(false);useEffect(()=>{const fn=()=>setM(window.innerWidth<768);fn();window.addEventListener("resize",fn);return()=>window.removeEventListener("resize",fn);},[]);return m;}
function Spinner({size=14}:{size?:number}){return(<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{animation:"spin 0.7s linear infinite",display:"block",flexShrink:0}}><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>);}
type Warehouse={id:number;name:string;is_active:boolean;warehouse_type?:string};
type ProductRow={id:number;name:string;sku?:string|null;is_active?:boolean};
type Line={product_id:number|"";qty:string;unit_cost:string;note:string};

function toDec(v:string){const n=Number(String(v).replace(",","."));return Number.isFinite(n)?n:NaN;}
function fCLP(v:number|string):string{const n=Number(v);if(!Number.isFinite(n))return String(v);return Math.round(n).toLocaleString("es-CL");}

type BtnV="primary"|"secondary"|"ghost"|"danger"|"teal";
function Btn({children,onClick,variant="secondary",disabled,size="md",full}:{children:React.ReactNode;onClick?:()=>void;variant?:BtnV;disabled?:boolean;size?:"sm"|"md"|"lg";full?:boolean;}){
  const vs:Record<BtnV,React.CSSProperties>={
    primary:{background:C.accent,color:"#fff",border:`1px solid ${C.accent}`},
    secondary:{background:C.surface,color:C.text,border:`1px solid ${C.borderMd}`},
    ghost:{background:"transparent",color:C.mid,border:"1px solid transparent"},
    danger:{background:C.redBg,color:C.red,border:`1px solid ${C.redBd}`},
    teal:{background:C.tealBg,color:C.teal,border:`1px solid ${C.tealBd}`},
  };
  const h=size==="lg"?46:size==="sm"?30:38;
  const px=size==="lg"?"0 20px":size==="sm"?"0 10px":"0 14px";
  const fs=size==="lg"?14:size==="sm"?11:13;
  return(<button type="button" onClick={onClick} disabled={disabled} className="xb" style={{...vs[variant],display:"inline-flex",alignItems:"center",justifyContent:"center",gap:6,height:h,padding:px,borderRadius:C.r,fontSize:fs,fontWeight:600,letterSpacing:"0.01em",whiteSpace:"nowrap",width:full?"100%":undefined}}>{children}</button>);
}

function FLabel({children,req}:{children:React.ReactNode;req?:boolean}){
  return(<div style={{fontSize:11,fontWeight:700,color:C.mid,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:5}}>{children}{req&&<span style={{color:C.red,marginLeft:3}}>*</span>}</div>);
}

function iS(extra?:React.CSSProperties):React.CSSProperties{
  return{width:"100%",height:36,padding:"0 10px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:13,background:C.surface,...extra};
}

export default function PurchaseNewPage(){
  useGlobalStyles();
  const mob = useIsMobile();
  const router=useRouter();

  const [warehouseId,setWarehouseId] = useState<number|"">("");
  const [supplierName,setSupplierName] = useState("");
  const [invoiceNumber,setInvoiceNumber] = useState("");
  const [invoiceDate,setInvoiceDate] = useState("");
  const [note,setNote] = useState("");
  const [taxAmount,setTaxAmount] = useState("0");

  const [warehouses,setWarehouses] = useState<Warehouse[]>([]);
  const [products,setProducts] = useState<ProductRow[]>([]);
  const [qProd,setQProd] = useState("");

  const [lines,setLines] = useState<Line[]>([{product_id:"",qty:"1",unit_cost:"0",note:""}]);
  const [saving,setSaving] = useState(false);
  const [err,setErr] = useState<string|null>(null);
  const [success,setSuccess] = useState<string|null>(null);

  useEffect(()=>{
    (async()=>{try{const ws=(await apiFetch("/core/warehouses/")) as Warehouse[];setWarehouses(Array.isArray(ws)?ws:[]);}catch{setWarehouses([]);}})();
    (async()=>{try{const data=(await apiFetch("/catalog/products/")) as any;const arr=data?.results??data??[];setProducts(Array.isArray(arr)?arr:[]);}catch{setProducts([]);}})();
  },[]);

  const filteredProducts=useMemo(()=>{
    const qq=qProd.trim().toLowerCase();
    const base=products.filter(p=>(p.is_active??true)!==false);
    if(!qq) return base.slice(0,200);
    return base.filter(p=>{const name=(p.name||"").toLowerCase();const sku=(p.sku||"").toLowerCase();return name.includes(qq)||sku.includes(qq)||String(p.id).includes(qq);}).slice(0,200);
  },[products,qProd]);

  const subtotal=useMemo(()=>{let s=0;for(const l of lines){const qty=toDec(l.qty);const cost=toDec(l.unit_cost);if(!Number.isFinite(qty)||!Number.isFinite(cost)||qty<=0||cost<0)continue;s+=qty*cost;}return s;},[lines]);
  const tax=useMemo(()=>{const t=toDec(taxAmount);return Number.isFinite(t)?t:0;},[taxAmount]);
  const total=useMemo(()=>subtotal+tax,[subtotal,tax]);

  const addLine=()=>setLines(p=>[...p,{product_id:"",qty:"1",unit_cost:"0",note:""}]);
  const removeLine=(idx:number)=>setLines(p=>p.length<=1?p:p.filter((_,i)=>i!==idx));
  const setLine=(idx:number,patch:Partial<Line>)=>setLines(p=>p.map((l,i)=>i===idx?{...l,...patch}:l));

  function validate():string|null{
    if(!warehouseId) return "Debes seleccionar una bodega.";
    for(let i=0;i<lines.length;i++){
      const l=lines[i];
      if(!l.product_id) return `Línea ${i+1}: falta producto`;
      const qty=toDec(l.qty);
      if(!Number.isFinite(qty)||qty<=0) return `Línea ${i+1}: cantidad inválida`;
      const cost=toDec(l.unit_cost);
      if(!Number.isFinite(cost)||cost<0) return `Línea ${i+1}: costo inválido`;
    }
    if(!Number.isFinite(toDec(taxAmount))||toDec(taxAmount)<0) return "IVA inválido";
    return null;
  }

  async function submit(){
    const v=validate();
    if(v){setErr(v);return;}
    setSaving(true);setErr(null);
    try{
      const payload={
        warehouse_id:warehouseId,
        supplier_name:supplierName.trim(),
        invoice_number:invoiceNumber.trim(),
        invoice_date:invoiceDate||null,
        note:note.trim(),
        tax_amount:taxAmount||"0",
        lines:lines.map(l=>({product_id:l.product_id,qty:l.qty,unit_cost:l.unit_cost,note:l.note?.trim()||""})),
      };
      const res=await apiFetch("/purchases/create/",{method:"POST",body:JSON.stringify(payload)});
      const id=res?.id;
      setSuccess("Orden de compra creada correctamente");
      setTimeout(()=>{setSuccess(null);router.push(id?`/dashboard/purchases/${id}`:"/dashboard/purchases");},1200);
    }catch(e:any){
      setErr(e instanceof ApiError?e.message:(e?.message??"No se pudo crear la compra"));
    }finally{setSaving(false);}
  }

  return(
    <div style={{fontFamily:C.font,color:C.text,background:C.bg,minHeight:"100vh",padding:mob?"16px 12px":"24px 28px",display:"flex",flexDirection:"column",gap:16}}>

      {/* HEADER */}
      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",gap:12,flexWrap:"wrap"}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:4}}>
            <div style={{width:4,height:26,background:C.teal,borderRadius:2}}/>
            <h1 style={{margin:0,fontSize:22,fontWeight:800,color:C.text,letterSpacing:"-0.04em"}}>Nueva compra</h1>
            <span style={{display:"inline-flex",alignItems:"center",gap:5,padding:"3px 9px",borderRadius:99,fontSize:11,fontWeight:700,border:`1px solid ${C.amberBd}`,background:C.amberBg,color:C.amber}}>
              <span style={{width:6,height:6,borderRadius:"50%",background:"currentColor",display:"inline-block"}}/>
              DRAFT
            </span>
          </div>
          <p style={{margin:0,fontSize:13,color:C.mute,paddingLeft:14}}>Crea la orden y luego posteala para aplicar stock y costeo al inventario</p>
        </div>
        <div style={{display:"flex",gap:8}}>
          <Btn variant="ghost" onClick={()=>router.back()} disabled={saving}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="15 18 9 12 15 6"/></svg>
            Volver
          </Btn>
          <Btn variant="teal" onClick={submit} disabled={saving}>
            {saving?<><Spinner/>Guardando…</>:<><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>Guardar DRAFT</>}
          </Btn>
        </div>
      </div>

      {/* SUCCESS */}
      {success&&(
        <div style={{padding:"10px 14px",borderRadius:C.r,background:C.greenBg,border:`1px solid ${C.greenBd}`,color:C.green,fontSize:13,fontWeight:600}}>{success}</div>
      )}

      {/* ERROR */}
      {err&&(
        <div style={{padding:"11px 14px",borderRadius:C.r,border:`1px solid ${C.redBd}`,background:C.redBg,color:C.red,fontSize:13,display:"flex",gap:8,alignItems:"center"}}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{flexShrink:0}}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span style={{flex:1}}>{err}</span>
          <button onClick={()=>setErr(null)} className="xb" style={{background:"none",border:"none",color:C.red,fontSize:16,cursor:"pointer",padding:0,lineHeight:1}}>✕</button>
        </div>
      )}

      {/* MAIN GRID */}
      <div style={{display:"grid",gridTemplateColumns:mob?"1fr":"1fr 300px",gap:16,alignItems:"start"}}>

        {/* LEFT: header form + lines */}
        <div style={{display:"flex",flexDirection:"column",gap:14}}>

          {/* Header fields */}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
            <div style={{padding:"12px 18px",borderBottom:`1px solid ${C.border}`,background:C.bg}}>
              <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Datos de la compra</div>
            </div>
            <div style={{padding:"18px",display:"grid",gridTemplateColumns:mob?"1fr":"1fr 1fr",gap:14}}>
              <div style={{gridColumn:"1/-1"}}>
                <FLabel req>Bodega</FLabel>
                <select value={warehouseId} onChange={e=>setWarehouseId(e.target.value?Number(e.target.value):"")} style={{...iS(),height:38}} disabled={saving}>
                  <option value="">Selecciona una bodega…</option>
                  {warehouses.map(w=><option key={w.id} value={w.id}>{w.name}{w.warehouse_type==="sales_floor"?" (Sala)":" (Bodega)"}</option>)}
                </select>
              </div>
              <div>
                <FLabel>Proveedor</FLabel>
                <input value={supplierName} onChange={e=>setSupplierName(e.target.value)} placeholder="Ej: Distribuidora XYZ" style={iS()} disabled={saving}/>
              </div>
              <div>
                <FLabel>N° Factura</FLabel>
                <input value={invoiceNumber} onChange={e=>setInvoiceNumber(e.target.value)} placeholder="Ej: F-001234" style={{...iS(),fontFamily:C.mono}} disabled={saving}/>
              </div>
              <div>
                <FLabel>Fecha factura</FLabel>
                <input type="date" value={invoiceDate} onChange={e=>setInvoiceDate(e.target.value)} style={iS()} disabled={saving}/>
              </div>
              <div>
                <FLabel>IVA / Impuesto ($)</FLabel>
                <input value={taxAmount} onChange={e=>setTaxAmount(e.target.value)} placeholder="0" inputMode="decimal" style={{...iS(),fontFamily:C.mono}} disabled={saving}/>
              </div>
              <div style={{gridColumn:"1/-1"}}>
                <FLabel>Nota</FLabel>
                <input value={note} onChange={e=>setNote(e.target.value)} placeholder="Observaciones internas…" style={iS()} disabled={saving}/>
              </div>
            </div>
          </div>

          {/* Lines */}
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
            <div style={{padding:"12px 18px",borderBottom:`1px solid ${C.border}`,background:C.bg,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
              <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Líneas de compra</div>
              <div style={{display:"flex",gap:8,alignItems:"center"}}>
                <div style={{position:"relative"}}>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.mute} strokeWidth="2.5" strokeLinecap="round" style={{position:"absolute",left:8,top:"50%",transform:"translateY(-50%)",pointerEvents:"none"}}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                  <input value={qProd} onChange={e=>setQProd(e.target.value)} placeholder="Filtrar productos…"
                    style={{height:28,padding:"0 8px 0 26px",border:`1px solid ${C.border}`,borderRadius:C.r,fontSize:12,background:C.bg,width:180}} disabled={saving}/>
                </div>
                <Btn variant="teal" size="sm" onClick={addLine} disabled={saving}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                  Agregar línea
                </Btn>
              </div>
            </div>

           <div style={{overflowX:"auto"}}>
            {/* Lines header */}
            <div style={{display:"grid",gridTemplateColumns:"2fr 90px 110px 1fr 36px",columnGap:10,padding:"8px 18px",background:C.bg,borderBottom:`1px solid ${C.border}`,fontSize:10.5,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em",minWidth:mob?600:undefined}}>
              <div>Producto</div><div style={{textAlign:"center"}}>Cantidad</div>
              <div style={{textAlign:"right"}}>Costo unit.</div><div>Nota</div><div/>
            </div>

            <div style={{display:"flex",flexDirection:"column"}}>
              {lines.map((l,idx)=>{
                const qty=toDec(l.qty); const cost=toDec(l.unit_cost);
                const lineTotal=Number.isFinite(qty)&&Number.isFinite(cost)&&qty>0&&cost>=0?qty*cost:null;
                return(
                  <div key={idx} style={{display:"grid",gridTemplateColumns:"2fr 90px 110px 1fr 36px",columnGap:10,padding:"10px 18px",borderBottom:`1px solid ${C.border}`,alignItems:"center",minWidth:mob?600:undefined}}>
                    <select value={l.product_id} onChange={e=>setLine(idx,{product_id:e.target.value?Number(e.target.value):""})} style={{...iS({height:34,fontSize:12})}} disabled={saving}>
                      <option value="">Producto…</option>
                      {filteredProducts.map(p=><option key={p.id} value={p.id}>#{p.id} — {p.name}{p.sku?` (${p.sku})`:""}</option>)}
                    </select>
                    <input value={l.qty} onChange={e=>setLine(idx,{qty:e.target.value})} inputMode="decimal"
                      style={{...iS({height:34,fontSize:12,textAlign:"center",fontFamily:C.mono})}} disabled={saving}/>
                    <div style={{position:"relative"}}>
                      <span style={{position:"absolute",left:8,top:"50%",transform:"translateY(-50%)",color:C.mute,fontSize:12,fontFamily:C.mono,pointerEvents:"none"}}>$</span>
                      <input value={l.unit_cost} onChange={e=>setLine(idx,{unit_cost:e.target.value})} inputMode="decimal"
                        style={{...iS({height:34,fontSize:12,textAlign:"right",fontFamily:C.mono,paddingLeft:18})}} disabled={saving}/>
                    </div>
                    <input value={l.note} onChange={e=>setLine(idx,{note:e.target.value})} placeholder="Nota…"
                      style={iS({height:34,fontSize:12})} disabled={saving}/>
                    <button type="button" onClick={()=>removeLine(idx)} disabled={saving||lines.length<=1} className="xb"
                      style={{width:28,height:28,borderRadius:C.r,border:`1px solid ${C.border}`,background:C.surface,color:C.mute,fontSize:14,display:"flex",alignItems:"center",justifyContent:"center"}}>✕</button>
                  </div>
                );
              })}
            </div>
           </div>

            {/* Lines footer: subtotal por líneas */}
            {lines.some(l=>toDec(l.qty)>0&&toDec(l.unit_cost)>=0)&&(
              <div style={{padding:"10px 18px",background:C.bg,borderTop:`1px solid ${C.border}`,display:"flex",justifyContent:"flex-end",gap:24}}>
                {lines.map((l,idx)=>{
                  const qty=toDec(l.qty); const cost=toDec(l.unit_cost);
                  if(!Number.isFinite(qty)||!Number.isFinite(cost)||qty<=0||cost<0) return null;
                  const prod=products.find(p=>p.id===l.product_id);
                  return(
                    <div key={idx} style={{fontSize:11,color:C.mute,textAlign:"right"}}>
                      <span style={{fontWeight:600,color:C.mid}}>{prod?.name?.split(" ").slice(0,2).join(" ")||`Línea ${idx+1}`}</span>
                      {" · "}<span style={{fontFamily:C.mono,fontWeight:700,color:C.text}}>${fCLP(qty*cost)}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT: totals + actions */}
        <div style={{display:"flex",flexDirection:"column",gap:12,position:mob?undefined:"sticky",top:mob?undefined:24}}>
          <div style={{background:C.surface,border:`1px solid ${C.border}`,borderRadius:C.rMd,overflow:"hidden",boxShadow:C.sh}}>
            <div style={{padding:"12px 16px",borderBottom:`1px solid ${C.border}`,background:C.bg}}>
              <div style={{fontSize:11,fontWeight:700,color:C.mute,textTransform:"uppercase",letterSpacing:"0.07em"}}>Resumen</div>
            </div>
            <div style={{padding:"16px",display:"flex",flexDirection:"column",gap:10}}>
              <div style={{display:"flex",justifyContent:"space-between",fontSize:13,color:C.mid}}>
                <span>Líneas</span><span style={{fontWeight:600,color:C.text}}>{lines.length}</span>
              </div>
              <div style={{display:"flex",justifyContent:"space-between",fontSize:13,color:C.mid}}>
                <span>Subtotal neto</span>
                <span style={{fontWeight:700,fontFamily:C.mono,color:C.text}}>${fCLP(subtotal)}</span>
              </div>
              <div style={{display:"flex",justifyContent:"space-between",fontSize:13,color:C.mid}}>
                <span>IVA / Impuesto</span>
                <span style={{fontWeight:600,fontFamily:C.mono,color:C.mid}}>${fCLP(tax)}</span>
              </div>
              <div style={{height:1,background:C.border}}/>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}>
                <span style={{fontSize:13,color:C.mid}}>Total costo</span>
                <span style={{fontSize:22,fontWeight:800,color:C.teal,letterSpacing:"-0.03em",fontVariantNumeric:"tabular-nums"}}>${fCLP(total)}</span>
              </div>
            </div>
          </div>

          <Btn variant="teal" size="lg" full onClick={submit} disabled={saving}>
            {saving?<><Spinner size={16}/>Guardando…</>:<><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>Guardar DRAFT</>}
          </Btn>

          <div style={{padding:"10px 12px",borderRadius:C.r,background:C.amberBg,border:`1px solid ${C.amberBd}`,fontSize:12,color:C.amber,fontWeight:500,lineHeight:1.5}}>
            💡 El DRAFT no aplica stock. Posteá la compra desde el detalle para actualizar el inventario.
          </div>
        </div>
      </div>
    </div>
  );
}