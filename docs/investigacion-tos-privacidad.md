# Investigación — Términos de Servicio y privacidad para un SaaS chileno

Qué exige la ley chilena, qué se puede pactar y qué no, y cómo estructurar
los tres documentos que faltan. Investigado el 24-ago-2026; fuentes al final.

**Esto no es asesoría legal.** Es la investigación previa para que la
redacción —propia o de un abogado— parta de los hechos correctos y no de una
plantilla genérica de otro país.

---

## 1. Las tres leyes que se cruzan

| Ley | Qué regula | Por qué aplica a Pulstock |
|---|---|---|
| **21.719** (datos personales) | Tratamiento de datos; reemplaza a la 19.628 | El sistema guarda datos de trabajadores de los clientes. Vigencia plena: **1-dic-2026** |
| **19.496** (consumidor) | Contratos de adhesión y cláusulas abusivas | Los ToS de un SaaS **son** un contrato de adhesión |
| **20.416** (Estatuto Pyme, art. 9°) | Extiende la protección de consumidor a micro y pequeñas empresas | **El hallazgo decisivo** — ver abajo |

## 2. El hallazgo decisivo: el cliente pyme cuenta como consumidor

La intuición natural es "esto es B2B, la ley del consumidor no aplica".
**En Chile es al revés para este caso.**

El artículo 9° de la Ley 20.416 extiende las protecciones de la Ley del
Consumidor a las micro y pequeñas empresas **en su rol de consumidoras** —
cuando compran algo **fuera de su giro principal**. Un café que contrata un
software de inventario es exactamente ese caso: el software no es el giro del
café.

Consecuencia directa, por el artículo 16 de la 19.496: en un contrato de
adhesión **no producen efecto las limitaciones absolutas de responsabilidad**
que priven al cliente de resarcimiento por deficiencias que afecten la
utilidad esencial del servicio.

### Qué significa para la cláusula más importante

| Diseño de cláusula | Resultado esperable |
|---|---|
| "Pulstock no responde por nada" (exoneración total) | **Nula.** Y arrastra desconfianza sobre el resto del contrato |
| Tope razonable: lo pagado en los últimos 3-6 meses + exclusión de daño consecuencial + el pronóstico descrito honestamente como estimación | **Defendible** — es el estándar de la industria y no es "absoluta" |

Esto conecta con lo ya hecho: la cláusula de "sin garantía de resultados" no
puede ser retórica — se sostiene en que **el error del pronóstico está medido
(38% semanal) y el sistema lo muestra por producto**, y en que ninguna compra
se ejecuta sin aprobación humana. Los hechos están en
[expediente-legal.md](expediente-legal.md).

**Corolario:** corregir la landing deja de ser cosmético. "La cantidad
**exacta** a pedir" es publicidad que contradice al contrato que se quiere
firmar, y la publicidad engañosa está sancionada por la misma 19.496 que
protege al café-pyme.

## 3. Lo que la 21.719 exige de la política de privacidad

Para el 1-dic-2026, la política tiene que declarar:

- **Base de licitud** de cada tratamiento (consentimiento, ejecución de
  contrato, interés legítimo…) — no basta "tratamos tus datos"
- **Derechos ARCO+** (acceso, rectificación, cancelación, oposición **y
  portabilidad**) con canal y plazo de respuesta (≤30 días)
- **Transferencias internacionales** — el dato vive en Hetzner **Helsinki**;
  que sea UE/GDPR facilita el argumento de nivel adecuado, pero hay que
  declararlo
- **Subprocesadores** — la tabla ya está en el expediente
- **Notificación de brechas** a la nueva Agencia en ~72 horas
- Plazos de **retención** (hoy: respaldos 14 días; datos operativos
  indefinido — habría que definir una política)

Sobre el consentimiento, la ley es explícita: **libre, informado, específico
e inequívoco**. Nada de casillas pre-marcadas ni consentimientos generales
escondidos en el texto. Revocable con la misma facilidad con que se otorgó.
Esto valida el diseño técnico ya especificado (casilla bloqueante sin
pre-marcar + registro de fecha/versión/IP).

**Sanciones:** hasta 20.000 UTM (~USD 1,5M) las gravísimas. Atenuante real
para este tamaño: **amonestación escrita en la primera infracción** para
pymes.

## 4. La estructura de los tres documentos

Esqueleto para redactar sobre él — el orden y el contenido, no las cláusulas.

### A. Términos de Servicio

1. Identificación del **licenciante** (la pregunta previa: ¿sociedad o
   persona natural? — sin resolver)
2. Objeto: licencia de uso del software como servicio, no venta
3. Cuenta y responsabilidad sobre credenciales
4. **El pronóstico es una estimación** — descripción honesta, con la decisión
   de compra siempre en el cliente (hechos del expediente, §3)
5. Precio, facturación, mora y suspensión (los plazos reales del sistema:
   reintentos día 1/3/5, suspensión ~día 4)
6. **Limitación de responsabilidad** — tope razonable, nunca absoluta (§2)
7. Propiedad del dato: **del cliente**; Pulstock lo trata por encargo
8. Disponibilidad: sin SLA numérico (un solo servidor — no prometer lo que la
   infraestructura no puede cumplir)
9. Término: plazo de exportación de datos, luego borrado (requiere construir
   la exportación)
10. Modificaciones de los términos: aviso previo + re-aceptación versionada
11. Ley aplicable y jurisdicción (Chile; el abogado define el fuero)

### B. Política de privacidad

1. Responsable del tratamiento
2. Qué datos, de quién y para qué (el inventario del expediente §5 — el
   grueso es de **trabajadores** de los clientes)
3. Base de licitud por tratamiento
4. Subprocesadores y transferencia internacional (Helsinki)
5. Retención
6. Derechos ARCO+ y canal de ejercicio
7. Brechas de seguridad
8. Contacto (**requiere resolver el MX del dominio** — hoy ese correo rebota)

### C. Anexo de encargo de tratamiento (DPA con cada cliente)

1. Roles: cliente = responsable; Pulstock = encargado
2. Instrucciones documentadas y confidencialidad
3. Medidas de seguridad (las declarables con evidencia: cifrado AES256,
   aislamiento probado, auditoría, HTTPS)
4. Subprocesadores autorizados + mecanismo de actualización
5. Asistencia ante derechos ARCO y brechas
6. Devolución/supresión al término

## 5. Los tres caminos para tenerlos, y mi recomendación

| Camino | Costo aproximado | Riesgo |
|---|---|---|
| **Abogado tradicional** redacta de cero | El más caro | Bajo, pero paga horas de averiguar hechos que ya están averiguados |
| **Plantilla genérica de internet** | Gratis | Alto: casi todas ignoran la 20.416 y traen exoneraciones absolutas → nulas justo cuando se necesitan |
| **Borrador propio sobre esta investigación + revisión de abogado** | Medio | El abogado corrige en vez de crear: menos horas facturables |

**Recomendación: el tercero.** El expediente tiene los hechos, esta
investigación tiene el marco, y el esqueleto está arriba. Un abogado chileno
revisando un borrador bien fundado cobra una fracción de redactar de cero —
y dado que Mario no quiere gastos nuevos, es la vía realista. Lo que **no**
es negociable es que un abogado lo revise antes de publicarlo: la cláusula
de limitación es exactamente donde un error sale caro.

## Fuentes

- [Contrato SaaS en Chile: requisitos y claves — Von Marttens](https://vonmarttens.cl/contrato-saas-chile/)
- [Ley 21.719: guía 2026 para empresas — Prey Project](https://preyproject.com/es/blog/ley-de-proteccion-de-datos-en-chile)
- [Ley 21.719 y sus efectos en contratos — Cheers Contracts](https://www.cheerscontracts.com/articles/nueva-ley-de-proteccion-de-datos-en-chile-ley-21-719-que-deben-hacer-tus-contratos-ahora)
- [Ley 19.496, artículo 16 (cláusulas abusivas) — SERNAC](https://www.sernac.cl/portal/609/w3-propertyvalue-58716.html)
- [Cláusulas limitativas de responsabilidad: validez y límites — Revista Chilena de Derecho (SciELO)](https://www.scielo.cl/scielo.php?script=sci_arttext&pid=S0718-34372011000100005)
- [Lineamientos del estatuto del consumidor empresario — SciELO](https://www.scielo.cl/scielo.php?script=sci_arttext&pid=S0718-97532023000100206)
- [La protección de las pymes por la Ley del Consumidor — Sergio Arenas](https://sergioarenasabogado.com/2025/07/31/la-proteccion-de-las-pymes-por-la-ley-del-consumidor/)
- [Ley 20.416, texto oficial (PDF)](http://www.sice.oas.org/SME_CH/CHL/Ley_20416_s.pdf)
