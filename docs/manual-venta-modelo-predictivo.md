# El motor predictivo de Pulstock — manual para venderlo

Para explicar qué hace, por qué es distinto y qué contestar cuando pregunten.

Está escrito con **números reales de Marbrava**, medidos el 24-ago-2026. No hay
cifras infladas: un pronóstico sobrevendido se cae solo en el mes dos, y ahí se
pierde el cliente y la recomendación.

---

## 1. Qué hace, para alguien que no sabe de sistemas

> «El sistema mira lo que vendiste todos los días, aprende tu ritmo y te dice
> qué comprar antes de que se te acabe.»

Eso es todo lo que hay que decir en la primera frase. Si quieren más:

> «Y no lo hace por producto de la carta, lo hace por **ingrediente**. No te
> dice "vas a vender 40 lattes": te dice "te van a faltar 3 litros de leche",
> sumando lo que consume cada café, cada capuccino y cada cortado que la lleva.»

Esa segunda frase es la que engancha, porque es el problema real del dueño. Los
lattes no se compran: se compra leche.

---

## 2. Por qué esto no lo tiene la competencia

Es la parte más fuerte de la venta y conviene decirla sin adornos.

| Sistema | ¿Pronóstico propio? |
|---|---|
| Fudo | No |
| Toteat | No |
| Loyverse | No |
| MarketMan | No (terceriza) |
| Supy | Anunciado, no disponible |
| Crunchtime | Sí (empresa grande, precio de empresa grande) |
| Toast IQ | Sí, solo EE.UU., US$150-250/mes **extra** |

**En el tier latinoamericano, el pronóstico de demanda a nivel ingrediente con
sugerencia de compra no lo tiene nadie más.**

Y hay un dato de mercado que ayuda: el **44% de los restaurantes** considera
cambiar de sistema, y el motivo número uno es **analítica y reportes** — justo
lo que Pulstock vende.

### Munición contra Fudo, que es el que más te vas a cruzar

Quejas documentadas de sus propios usuarios: soporte ausente en hora punta,
comandas que se triplican, errores de inventario, cero modo sin internet, y
alzas de precio sin aviso.

Un detalle chico que vale oro en una demo: **Fudo no avisa cuando se te acaban
los folios de boleta.** Está documentado en su propio centro de ayuda.

---

## 3. Los números reales, para cuando pregunten

Alguien va a preguntar «¿y qué tan bien le achunta?». La respuesta honesta:

> «Depende de para qué lo mires. Para adivinar exactamente cuánto vendes un
> martes, no sirve — y ningún sistema del mundo sirve para eso en un local
> chico. Para decidir cuánto comprar en la semana, sí.»

Medido en Marbrava sobre 4.167 comparaciones reales de los últimos 30 días:

| Si miras… | El error promedio es |
|---|---|
| Un día suelto | 61% |
| Tres días | 47% |
| **Una semana** | **38%** |
| Dos semanas | 33% |

**Por qué mejora al agrupar:** un producto que vende 2 o 3 unidades al día es
impredecible el martes —puede vender 1 o 5— pero muy predecible en la semana.
Y la compra se hace por semana, no por día.

Esto no es una excusa: es un resultado conocido. En la competencia mundial de
pronóstico **M5** (42.840 series reales de Walmart), la ventaja de los modelos
sofisticados **se derrumba a ~3%** justo en el nivel producto-tienda con venta
intermitente. Solo el 7,5% de 2.666 equipos logró ganarle a un promedio
exponencial simple.

### Lo que el sistema tiene hoy en Marbrava

- **192 modelos activos** sobre 242 productos (79% de cobertura)
- **14.311 mediciones** de precisión acumuladas
- **8 algoritmos distintos**, elegidos automáticamente producto por producto

El sistema no usa una fórmula: prueba varias y se queda con la que mejor
funcionó para *ese* producto. Un café que vende todos los días y un syrup que
sale una vez por semana no se predicen igual.

---

## 4. La regla de oro para venderlo

**El sistema propone, la persona decide.**

Esto no es una limitación que hay que disculpar: es el diseño, y es el mismo de
**7-Eleven Japón**, que es el referente mundial en tienda chica. Deliberadamente
NO automatizan el pedido — muestran el contexto y dejan decidir al encargado. Sus
tiendas venden alrededor de US$1.000 diarios **más** que la competencia
automatizada.

Traducido a la demo:

> «No te va a comprar solo. Te llega la sugerencia, la miras, y si sabes algo
> que el sistema no sabe —que viene un partido, que cierras por vacaciones— la
> cambias. El sistema aprende de eso.»

Un dueño que siente que le sacaron el control deja de usar el sistema. Uno que
siente que le sacaron el trabajo aburrido lo defiende.

---

## 5. Objeciones y qué contestar

**«Yo ya sé lo que tengo que comprar.»**
> «Seguro, para los diez productos que más vendes. ¿Y para los otros
> doscientos? El sistema no está para reemplazarte en lo que ya dominas, está
> para los que se te pasan.»

**«¿Y si se equivoca?»**
> «Se equivoca, y te muestra cuánto. Cada producto tiene una etiqueta de
> confianza calculada con el error real medido, no con una promesa. Cuando dice
> confianza baja, te avisa que lo revises antes de aprobar.»

**«Mi negocio es distinto.»**
> «Por eso no hay una fórmula sola. El sistema clasifica cada producto según
> cómo se comporta y le aplica el método que le corresponde. El pan y el syrup
> de avellana no se predicen igual ni en tu local ni en ninguno.»

**«¿Cuánto tarda en servir?»**
> «Empieza a dar resultados en dos semanas y se afina durante los primeros dos
> meses. Antes de eso se apoya en el comportamiento de la categoría, y te lo
> dice.»

**«¿Y si un mes vendo distinto?»**
> «Se ajusta solo. Si un producto se pone de moda, su mínimo y su sugerencia
> suben sin que toques nada.»

---

## 6. Lo que NO hay que prometer

Esta sección es la más importante del documento. Cada promesa de acá abajo
funciona en la reunión y se cobra en el mes dos.

| No digas | Porque |
|---|---|
| «Te acierta el 90%» | A nivel de un día es falso. Se comprueba solo y rápido. |
| «Nunca más vas a quebrar stock» | Reduce quiebres, no los elimina. Un proveedor que falla no lo arregla ningún software. |
| «Compra solo» | No compra solo, y no debería. |
| «Funciona desde el día uno» | Necesita dos semanas de ventas para tener algo que aprender. |
| «Sirve para cualquier negocio» | Está afinado para gastronomía. En otro rubro hay que ajustar. |

Lo que sí se puede prometer, porque es verificable:

- Que va a **ver productos que hoy se le pasan**
- Que el mínimo de cada producto **se recalcula solo todas las noches**
- Que va a poder **ver de dónde sale cada número** y discutirlo
- Que cada predicción viene con **su nivel de confianza medido**

---

## 7. La demo de tres minutos

1. **Abre la sugerencia de compra.** Que vea una lista concreta con cantidades,
   no un gráfico.
2. **Elige un ingrediente y muestra de dónde sale.** En Marbrava el mejor
   ejemplo es el **café en grano: el sistema lo predice sumando lo que
   consumen 46 productos distintos de la carta**. «No mira las ventas del
   café en grano, que no se vende suelto: mira cada americano, cada latte y
   cada cortado que lo lleva.» Es la parte que más impresiona, porque es la
   que él puede verificar de memoria.
3. **Muestra una corrección por día de semana.** «Aprendió solo que los jueves
   vendes menos.» Ahí es donde el dueño dice «es verdad» — y ese momento vale
   más que cualquier número.
4. **Muestra un producto con confianza baja.** Contraintuitivo pero funciona:
   demuestra que el sistema no miente cuando no sabe.

**No abras con el pronóstico.** Abre con la sugerencia de compra. Al dueño no le
interesa el modelo, le interesa qué tiene que comprar mañana.

---

## 8. Precio

Referencias del mercado chileno, por local y por mes:

| | Precio |
|---|---|
| Loyverse | Gratis (el piso) |
| Fudo | $25.500 / $34.500 / $52.500 (el inventario está en el tier medio) |
| Toteat | $39.900 **+ 0,7% de las ventas** |

El 0,7% de Toteat es un argumento fuerte: en un local que factura $15 millones
al mes son $105.000 extra, todos los meses, encima de la mensualidad.

Los planes **anuales retienen 92% contra 68% los mensuales**. Un descuento del
15% —«dos meses gratis»— se paga solo.

---

## 9. Si quieren saber cómo funciona por dentro

Para un cliente técnico o un socio. Detalle completo en
[`docs/entrevista/pulstock-modelo-predictivo.md`](entrevista/pulstock-modelo-predictivo.md).

Todas las noches, en orden y esperando a que cada paso termine:

1. Consolida la demanda del día anterior — **ventas y también lo que se gastó
   por dentro**, porque el papel higiénico no se vende, se usa
2. Recalcula el mínimo de cada producto según su consumo y su variabilidad
3. Compara lo que predijo ayer contra lo que pasó de verdad
4. Reentrena los modelos con los datos frescos
5. Convierte el pronóstico en una lista de compra

Si un local tiene un problema, los demás siguen funcionando: el pipeline aísla
cada negocio. Y si algo falla, deja rastro — no se reporta éxito a medias.
