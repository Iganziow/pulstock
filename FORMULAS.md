# Fórmulas del Sistema — Inventario SaaS

> Documento de referencia para todas las fórmulas y reglas de negocio implementadas en el sistema.
> Actualizado: Marzo 2026

---

## 1. Costeo de Inventario — Promedio Ponderado Móvil (PPP)

### 1.1 Costo promedio ponderado (avg_cost)

Cada vez que **se reciben unidades** (RECEIVE o ADJUST positivo con costo), el costo promedio se recalcula:

```
nuevo_avg_cost = (stock_value_previo + qty_nueva × unit_cost_nueva) / (on_hand_previo + qty_nueva)
```

- `stock_value` = on_hand × avg_cost  (valor total del inventario de ese producto en esa bodega)
- `avg_cost` nunca baja por una salida; solo cambia cuando entran unidades con costo distinto.

### 1.2 Valor total del inventario (stock_value)

```
stock_value = on_hand × avg_cost
```

Se actualiza en cada movimiento:

| Movimiento | Efecto en on_hand | Efecto en avg_cost | Efecto en stock_value |
|---|---|---|---|
| RECEIVE (compra) | + qty | recalculado (PPP) | + qty × unit_cost |
| ADJUST+ (sin costo) | + qty | sin cambio | + qty × avg_cost_actual |
| ADJUST+ (con new_avg_cost) | + qty | = new_avg_cost | = new_on_hand × new_avg_cost |
| ADJUST− | − qty | sin cambio | − qty × avg_cost_actual |
| ISSUE (salida) | − qty | sin cambio | − qty × avg_cost_actual |
| SALE (venta) | − qty | sin cambio | − qty × avg_cost_al_vender |
| TRANSFER OUT | − qty | sin cambio | − qty × avg_cost_actual |
| TRANSFER IN | + qty | recalculado (PPP) | + qty × avg_cost_origen |

### 1.3 Sobrescritura directa de avg_cost (ajuste manual)

Cuando el usuario provee `new_avg_cost` en un ajuste:

```
nuevo_stock_value = (on_hand_previo + qty_ajuste) × new_avg_cost
nuevo_avg_cost    = new_avg_cost
```

Útil para corregir errores históricos de costeo.

---

## 2. Ventas

### 2.1 Línea de venta

```
line_total = qty × unit_price
```

### 2.2 Costo de línea (snapshot al momento de vender)

```
unit_cost_snapshot = avg_cost en esa bodega al momento de la venta
line_cost          = qty × unit_cost_snapshot
```

El `unit_cost_snapshot` se captura en el momento exacto de confirmar la venta y no cambia aunque el avg_cost futuro varíe.

### 2.3 Ganancia bruta por línea

```
line_gross_profit = line_total − line_cost
```

### 2.4 Totales de la venta

```
subtotal    = Σ line_total   (suma de todas las líneas)
total       = subtotal       (sin impuestos por ahora; si se agrega IVA: total = subtotal × 1.19)
total_cost  = Σ line_cost
gross_profit = total − total_cost
```

### 2.5 Margen bruto (%)

> Calculado en frontend para reportes:

```
margen% = (gross_profit / total) × 100
```

---

## 3. Movimientos de inventario (StockMove)

Cada transacción genera uno o más registros en `StockMove`:

| Campo | Descripción |
|---|---|
| `qty` | Positivo para entradas, negativo para salidas |
| `unit_cost` | Costo unitario del movimiento (puede ser null para ajustes sin costo) |
| `cost_snapshot` | avg_cost de la bodega **antes** del movimiento (snapshot) |
| `value_delta` | Cambio en stock_value producido por este movimiento |

```
value_delta (RECEIVE)  = +qty × unit_cost
value_delta (ISSUE)    = −qty × avg_cost_al_momento
value_delta (ADJUST)   = qty × avg_cost_al_momento   (o qty × new_avg_cost si se sobrescribe)
value_delta (SALE)     = −qty × avg_cost_al_vender
```

---

## 4. Kardex

El kardex muestra saldo acumulado por producto en una bodega:

```
balance_i = balance_{i-1} + qty_i
```

- El balance inicial es `0` (o el saldo previo al rango si se filtra por fecha).
- `qty` puede ser positivo (IN) o negativo (OUT).

---

## 5. Transferencias

Una transferencia entre bodegas genera **dos** StockMoves:

```
Move 1: warehouse=ORIGEN,  qty=−qty_transferida, move_type=OUT
Move 2: warehouse=DESTINO, qty=+qty_transferida, move_type=IN
```

El avg_cost en destino se recalcula con PPP usando el avg_cost del origen como unit_cost de entrada.

---

## 6. Indicadores de stock

### 6.1 Stock bajo

```
stock_bajo = on_hand > 0 AND on_hand ≤ 5
```

### 6.2 Sin stock

```
sin_stock = on_hand ≤ 0
```

### 6.3 Días para agotamiento (referencia)

> No implementado actualmente, pero la fórmula de referencia es:

```
días_agotamiento = on_hand / promedio_ventas_diarias
```

---

## 7. Número de venta por tenant

```
sale_number_nuevo = MAX(sale_number) del tenant + 1
```

- Asignado atómicamente con `SELECT FOR UPDATE` para evitar duplicados en concurrencia.
- Restricción única por `(tenant, sale_number)`.
- Empieza en `1` para cada nuevo tenant.

---

## 8. Pagos mixtos

Una venta puede registrar múltiples métodos de pago:

```
Σ payments.amount ≤ total_venta   (el sistema no valida, solo registra)
```

Métodos válidos: `cash`, `card`, `transfer`.

---

## Resumen visual de flujo de costeo

```
Compra:  unit_cost → PPP → nuevo avg_cost → nuevo stock_value
Venta:   avg_cost (snapshot) → line_cost → gross_profit
Ajuste:  qty_delta ± stock_value   [opcional: sobrescribir avg_cost]
Transfer: avg_cost origen → PPP en destino
```
