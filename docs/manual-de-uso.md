# Manual de uso de Pulstock

Qué hace cada pantalla, para quién es y cómo se usa.

Escrito recorriendo la instalación real de Cafetería Marbrava el 24-ago-2026,
así que los ejemplos son datos verdaderos y no inventados.

---

## Antes de empezar: quién ve qué

Pulstock tiene cuatro roles, y la barra lateral cambia según cuál tengas:

| Rol | Para quién | Qué puede hacer |
|---|---|---|
| **Dueño** | Mario | Todo, incluida la configuración y los precios |
| **Gerente** | Encargado de turno | Casi todo, menos facturación de la cuenta |
| **Cajero** | Garzones y caja | Vender, mesas, caja. No toca costos ni precios |
| **Inventario** | Bodega | Stock, compras, recetas. No vende |

Si alguien no encuentra una pantalla de este manual, lo más probable es que su
rol no la tenga. No está roto.

---

## Dashboard — la foto del día

**Para quién:** el dueño, primera cosa de la mañana.

Cuatro números arriba, que son los que importan antes del café:

- **Ventas hoy** — total y cuántas ventas, con la utilidad al lado
- **Stock bajo mínimo** — cuántos productos hay que reponer
- **Stock valorizado** — cuánta plata tienes inmovilizada en bodega
- **Compras pendientes** — órdenes empezadas y sin cerrar

Abajo, el gráfico de los últimos 7 días. Los domingos aparecen en blanco porque
Marbrava cierra: **eso no es un error**, y el sistema lo aprendió solo — no
predice ventas para un día que sabe que estás cerrado.

---

## Punto de Venta — vender rápido

**Para quién:** cajero, todo el día.

Es la pantalla más usada y está pensada para el teclado, no para el mouse:

1. **Escaneás el código de barras** o escribís nombre o SKU
2. Las flechas ↑↓ navegan los resultados, **Enter** agrega
3. El carrito se arma a la izquierda; el total y el método de pago a la derecha
4. **Efectivo / Débito / Crédito / Transferencia**, o *Dividir pago* si el
   cliente paga con dos medios

Arriba a la derecha se elige la **bodega** de la que sale el stock. Si tienes
un solo local no lo toques.

> **Si se corta internet a mitad de una venta**, al volver la conexión el
> carrito sigue ahí. El sistema guarda un identificador único por venta, así
> que recargar la página no cobra dos veces.

---

## Mesas — el salón

**Para quién:** garzones.

Una grilla con todas las mesas. El color dice el estado de un vistazo:

- **Verde** — libre
- **Naranja** — ocupada, con el total en curso y hace cuánto se abrió

A la derecha, **Comandas activas**: qué pidió cada mesa, sin tener que entrar.
En la instalación de Marbrava se ve, por ejemplo, la mesa 5 con $7.800 en tres
ítems abierta hace 3 minutos.

**Para llevar** abre una comanda sin mesa asignada.

> **Varios garzones pueden trabajar la misma mesa al mismo tiempo** sin pisarse:
> si dos agregan productos a la vez, se suman los dos pedidos. No se pierde
> ninguno ni gana "el último que guardó".

---

## Caja — el dinero del turno

**Para quién:** cajero al abrir y cerrar; el dueño para revisar.

Cuatro secciones:

- **Arqueo activo** — el turno en curso: quién lo abrió, a qué hora, y las
  ventas separadas por método de pago
- **Historial** — turnos anteriores
- **Propinas** — cuánto se juntó, para repartir
- **Movimientos** — entradas y salidas de efectivo que no son ventas

El total de ventas del turno se calcula solo. Al cerrar, se cuenta el efectivo
real y el sistema muestra la diferencia si la hay.

---

## Stock — qué hay en bodega

**Para quién:** inventario y dueño.

Cuatro tarjetas arriba: productos en bodega, unidades totales, cuántos están
**bajo su mínimo** y cuántos **sin stock**.

En la tabla, cada producto muestra su stock actual y **debajo, en chico, su
mínimo**. Los que tienen asterisco (`min 11*`) son los que **calcula el sistema
cada noche según tu consumo real y se ajustan solos**. Si defines uno a mano,
ese manda siempre.

Tres acciones por fila:

| Acción | Cuándo |
|---|---|
| **Recibir** | Llegó mercadería |
| **Egresar** | Merma, consumo interno, rotura |
| **Ajustar** | El conteo físico no coincide con el sistema |

> **El mínimo automático es lo que evita las sorpresas.** Antes había que
> configurarlo a mano producto por producto y casi nadie lo hacía: en Marbrava
> solo 8 de 252 lo tenían. Hoy lo tienen 188, calculados según cuánto se
> consume de cada cosa y qué tan parejo es ese consumo.

---

## Predicción — qué comprar

**Para quién:** el dueño, una o dos veces por semana.

Esta es la pantalla que no tiene la competencia. Abre con la pregunta correcta:
**"¿Qué productos necesito reponer?"**

Arriba, los avisos que requieren acción: productos que se van a agotar en menos
de tres días con la plata en riesgo, y productos sin costo cargado (sin costo
no se puede calcular el margen, y la sugerencia sale conservadora).

Después, tres números: cuántos necesitan reposición, cuántos pedidos hay listos
para aprobar, y sobre cuántos productos se hizo el análisis.

**Lo importante de entender:** el sistema predice **por ingrediente**, no por
producto de carta. No dice "vas a vender 40 lattes": dice cuánta leche te va a
faltar, sumando lo que consume cada bebida que la lleva. En Marbrava, el café
en grano se predice sumando lo que consumen **46 productos distintos**.

---

## Pedidos sugeridos — la lista de compra

**Para quién:** el dueño, antes de llamar al proveedor.

Los pedidos vienen armados y agrupados por urgencia, con productos, unidades y
costo total. Tres pestañas: **Pendientes**, **Aprobados** y **Descartados**.

**El sistema propone, tú decides.** Si sabes algo que el sistema no sabe —viene
un fin de semana largo, cierras por vacaciones— cambias la cantidad antes de
aprobar. Eso no es una limitación: es a propósito, y es cómo funcionan las
cadenas de tiendas que mejor operan en el mundo.

Cada producto muestra su **nivel de confianza**, calculado con el error real
medido, no con una promesa. Cuando dice confianza baja, conviene revisar antes
de aprobar.

---

## Ventas — el historial

**Para quién:** dueño y gerente.

Cuatro números: total de ventas, ingresos, **utilidad bruta con su margen**, y
cuántas anuladas.

Filtros rápidos por Hoy / 7 días / 30 días / Mes / Año, más filtros por estado
y bodega. La tabla muestra folio, fecha, origen (mesa o para llevar), bodega,
total, **utilidad por venta** y estado.

Se puede hacer clic en cualquier fila para ver el detalle: qué se vendió, quién
lo vendió, cómo se pagó.

---

## Catálogo, Recetas y Precios

**Para quién:** dueño e inventario.

- **Catálogo** — todos los productos, con precio, costo y categoría. Se importan
  en bloque desde Excel y se asignan códigos de barra.
- **Recetas** — qué lleva cada preparado. **Es lo que hace funcionar la
  predicción por ingrediente**: si un latte lleva 170 ml de leche, hay que
  decírselo acá una vez.
- **Precios** — lista de precios y márgenes, editable en bloque.

> Si la predicción de un ingrediente parece rara, lo primero a revisar es la
> receta. El sistema no puede saber cuánta leche lleva un capuccino si nadie
> se lo dijo.

---

## Reportes — ocho informes

**Para quién:** el dueño, y el contador una vez al mes.

Agrupados en tres bloques:

**Ventas y rentabilidad** — resumen de ventas, análisis ABC (qué productos son
el 80% de tu facturación) y mermas y pérdidas.

**Inventario y stock** — valorización, productos sin movimiento, y la planilla
de toma física para imprimir y contar a mano.

**Auditoría** — quién hizo qué y cuándo.

---

## Configuración

**Para quién:** solo el dueño.

Empresa, tiendas, usuarios y roles, impresoras, alertas por correo, y el plan
contratado.

**Impresoras** merece una nota: para imprimir comandas y boletas hace falta el
**Agente Pulstock**, un programa chico que corre en el PC del local y conecta
la impresora con el sistema. Se descarga desde ahí mismo y se vincula con un
código de un solo uso.

---

## Lo que el sistema hace solo, de madrugada

Todas las noches, sin que nadie lo toque:

1. Consolida la demanda del día — ventas **y también lo que se gastó por
   dentro**, porque el papel higiénico no se vende, se usa
2. Recalcula el mínimo de cada producto según su consumo
3. Compara lo que predijo ayer contra lo que pasó de verdad
4. Reentrena los modelos con los datos frescos
5. Arma la lista de compra

Al mediodía sale el correo de quiebres de stock, y los lunes el reporte ABC.

Si algo de esto falla, queda registrado y se puede ver — no se reporta éxito
a medias.
