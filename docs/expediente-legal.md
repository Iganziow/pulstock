# Expediente para el abogado — Pulstock

Todos los hechos verificados que hacen falta para redactar los Términos de
Servicio, la política de privacidad y el acuerdo de encargo de tratamiento.

**Esto no es asesoría legal ni un borrador de contrato.** Es el trabajo
previo: lo caro de un abogado no es escribir las cláusulas, es averiguar los
hechos. Acá están todos, medidos contra producción el 24-ago-2026, con la
fuente de cada uno.

---

## 1. La situación contractual hoy

| Documento | Estado |
|---|---|
| Términos de Servicio | **No existen** — ni documento, ni página, ni borrador |
| Política de privacidad | **No existe** |
| Acuerdo de encargo de tratamiento (DPA) con clientes | **No existe** |
| DPA con los subprocesadores | **Sin gestionar** |
| Registro de aceptación (fecha, versión, IP) | **No existe** — nada en el modelo de datos |

**Agravante corregido el 24-ago-2026:** la página de registro decía *"Al
registrarte aceptas nuestros términos"* — afirmando un contrato inexistente.
Esa línea ya fue retirada. Cualquier cuenta creada antes de esa fecha se
registró bajo esa afirmación falsa, y no quedó constancia de nada.

**El cliente actual (Cafetería Marbrava) opera sin ningún contrato escrito.**

## 2. Quién licencia a quién — la pregunta previa a todo

El negocio fue vendido: el comprador (Mario Muñoz) es a la vez el operador de
la plataforma y el dueño del primer cliente (su propia cafetería). Antes de
redactar nada hay que definir:

- **¿Quién es el licenciante?** ¿Una sociedad? ¿Una persona natural? Si no
  hay sociedad constituida, la responsabilidad por daños es **personal e
  ilimitada**. Esta es probablemente la primera conversación con el abogado.
- ¿El contrato de compraventa de la aplicación entre las partes existe por
  escrito? (Fuera del alcance de este expediente, pero el abogado va a
  preguntar.)

## 3. Qué hace el producto y cuánto se equivoca — la base de la cláusula clave

Pulstock es un punto de venta con inventario cuyo diferenciador es un **motor
de pronóstico de demanda** que sugiere qué comprar y cuánto.

**Los pronósticos fallan por diseño.** No es un defecto: es la naturaleza del
producto, y está medido sobre 4.167 comparaciones reales de los últimos 30
días del cliente en producción:

| Horizonte | Error promedio (WAPE) |
|---|---|
| Un día | **61%** |
| Tres días | 47% |
| Una semana | **38%** |
| Dos semanas | 33% |

El escenario de daño no es teórico: el sistema sugiere una compra, el
pronóstico falla —lo hará, varias veces al año—, el cliente sobrecompra
perecibles que se pierden, o subcompra y pierde ventas de un fin de semana.
**Sin cláusula de limitación de responsabilidad y de no garantía de
resultados, ese daño consecuencial es reclamable.**

### Hechos de diseño que juegan a favor (mitigación real, no retórica)

- **El sistema propone, la persona decide.** Ninguna compra se ejecuta sola:
  toda sugerencia requiere aprobación humana explícita, y el usuario puede
  modificar las cantidades antes de aprobar.
- **Cada predicción muestra su nivel de confianza**, calculado con el error
  real medido — no con una estimación teórica. Con confianza baja, la
  interfaz recomienda revisar antes de aprobar.
- La pantalla de pedidos permite **descartar** sugerencias (hay 49
  descartadas en el historial del cliente: la función se usa).

Estos tres hechos sostienen el argumento de que la decisión de compra es del
cliente y el sistema es una herramienta de apoyo. La cláusula puede citarlos
como características verificables del producto.

## 4. Lo que promete el marketing vs. lo medido — hay que corregir la landing

Textos actuales de `pulstock.cl` que un abogado debe contrastar con la tabla
de error de arriba:

> «7 días antes de que se agote un producto, recibes una alerta con la
> **cantidad exacta** a pedir.»

> «Sabes **exactamente** cuánto ganaste en cada producto, **no un estimado**.»

Con 38% de error semanal, la palabra "exacta" es indefendible. Y el "no un
estimado" del margen tampoco: el costo de los productos con receta se calcula
con el costo *actual* de los ingredientes (aproximación documentada en el
código), y hasta el 24-ago-2026 141 de 242 productos no tenían costo cargado.

**Recomendación:** la corrección de la landing debería salir junto con los
ToS. Un contrato que limita responsabilidad mientras la publicidad promete
exactitud es un flanco abierto — la Ley 19.496 sanciona la publicidad
engañosa, y la discrepancia entre promesa y contrato debilita la cláusula.

## 5. Inventario de datos personales

Verificado en el modelo de datos:

| Dato | Dónde | Titular |
|---|---|---|
| Nombre, correo, usuario, contraseña (hasheada) | `core.User` | **Trabajadores** del local |
| Nombre de garzón asociado a ventas, propinas y comandas | `sales`, `caja`, `tables` | Trabajadores |
| RUT, teléfono, correo del negocio | `core.Tenant` | El cliente (empresa/dueño) |
| RUT de proveedores | `purchases.Supplier` | Terceros (pueden ser personas naturales) |
| Nombre del cliente final en comanda | `tables.OpenOrder` | Consumidores — **opcional y esporádico** |

**Lo que NO se guarda:** base de datos de consumidores, RUT de compradores,
datos de tarjetas (el pago con tarjeta lo procesa el POS físico del local;
la pasarela Flow solo cobra la suscripción del negocio a Pulstock).

El grueso del tratamiento es **datos de trabajadores del cliente** — eso
orienta la política de privacidad y el DPA más que el caso consumidor.

## 6. Subprocesadores — la lista para declarar

| Proveedor | Función | Ubicación del dato | Nota |
|---|---|---|---|
| **Hetzner** | Servidor y base de datos | **Helsinki, Finlandia** (`hel1`) | Transferencia internacional. Finlandia es UE → régimen GDPR, lo cual facilita el argumento de nivel adecuado de protección |
| **Brevo** | Envío de correos transaccionales | UE (empresa francesa) | Recibe direcciones de correo de usuarios |
| **Flow.cl** | Cobro de suscripciones | Chile | Hoy apunta a *sandbox*: nunca procesó un cobro real |
| **Sentry** | Registro de errores | EE.UU. (por defecto) | Puede capturar datos personales en trazas de error — revisar configuración de scrubbing |
| **Cloudflare** | Solo DNS | — | El tráfico NO pasa por Cloudflare; no ve contenido |
| **Backblaze B2** | Respaldos cifrados | Pendiente de crear | Recibirá solo bloques cifrados AES256 — no puede leer el contenido |

## 7. Retención y término — los hechos para la cláusula de salida

- **Respaldos:** 14 días de retención local, cifrados con AES256 antes de
  cualquier salida del servidor. La clave de cifrado no sale del servidor.
- **Datos operativos** (ventas, stock, auditoría): retención indefinida — no
  existe política de purga.
- **Al terminar la relación:** hoy el único mecanismo es un borrado total
  irreversible que **no exporta nada antes**. No existe función de
  exportación de datos por cliente.

Para la cláusula de "qué pasa con los datos al terminar" hace falta construir
la exportación (está identificado como pendiente de la Ley 21.719 — mismo
trabajo, doble propósito).

## 8. Postura de seguridad — lo declarable con evidencia

- Aislamiento entre clientes verificado con pruebas automatizadas (~2.100
  tests, corridos en integración continua)
- Auditoría de acciones sensibles dentro de la aplicación
- Contraseñas con hashing estándar de Django (nunca en claro)
- Respaldos cifrados AES256; restauración **probada de punta a punta** el
  24-ago-2026, no solo asumida
- Monitoreo de salud con alertas clasificadas por severidad
- HTTPS en todo el tráfico; rate limiting en login y registro

## 8-bis. Marco legal chileno aplicable

Antes de redactar, leer [investigacion-tos-privacidad.md](investigacion-tos-privacidad.md).

Lo más importante que aparece ahí y cambia el diseño de las cláusulas: por el
**artículo 9° de la Ley 20.416 (Estatuto Pyme)**, un café que contrata software
—fuera de su giro— queda protegido por la **Ley del Consumidor**. Es decir:
esto NO es un B2B puro, y las limitaciones **absolutas** de responsabilidad
son nulas por el artículo 16 de la 19.496.

## 9. Las cláusulas que el abogado debe redactar

La lista mínima, con el hecho que sostiene cada una:

1. **Limitación de responsabilidad** — el error de pronóstico está medido y
   es inherente (sección 3). Tope sugerido a discutir: lo pagado en los
   últimos N meses, exclusión de daño consecuencial y lucro cesante.
2. **Sin garantía de resultados** — con la tabla de error como anexo técnico
   si el abogado lo estima útil: no es retórica defensiva, es la medición
   del propio producto.
3. **Propiedad del dato del cliente** — los datos del negocio son del
   cliente; Pulstock los trata por encargo.
4. **Subprocesadores declarados** — la tabla de la sección 6, con mecanismo
   de actualización.
5. **Datos al terminar** — plazo de exportación, luego borrado certificado.
   Requiere construir la exportación primero.
6. **Disponibilidad del servicio** — un solo servidor, sin redundancia: no
   comprometer SLA que la infraestructura no puede cumplir. Uptime real
   monitoreado pero sin historial formal suficiente para prometer un número.

## 10. Lo que ingeniería construye cuando el texto exista

Especificado para que el abogado sepa qué es posible:

- Documento de ToS **versionado** (cada cambio conserva el texto anterior)
- Registro de aceptación por usuario: **fecha, versión aceptada, IP**
- Casilla de aceptación **bloqueante** en el registro (sin marcar, no hay
  cuenta) y re-aceptación al cambiar la versión
- Página pública de términos y de privacidad, enlazadas desde el registro y
  el pie de la aplicación
- Exportación completa de datos por cliente (sección 7)

Nada de esto es difícil; ninguna parte existe todavía.

## 11. Los tres borradores ya escritos

No hay que empezar de una hoja en blanco. Los tres documentos están
redactados sobre los hechos de este expediente, en `docs/legal/`:

| Borrador | Qué cubre |
|---|---|
| [borrador-terminos-de-servicio.md](legal/borrador-terminos-de-servicio.md) | Licencia de uso, precio, pronóstico sin garantía de resultados, limitación de responsabilidad como **tope**, datos al terminar |
| [borrador-politica-privacidad.md](legal/borrador-politica-privacidad.md) | Base de licitud por tratamiento, transferencia a Finlandia, subprocesadores, derechos, retención |
| [borrador-dpa.md](legal/borrador-dpa.md) | Anexo de encargo: roles, instrucciones, subencargados, medidas de seguridad medidas, brechas, devolución |

**Cómo usarlos:** son un punto de partida para que el abogado corrija, no un
contrato listo para firmar. Cada uno lleva el aviso en la primera línea y
`[corchetes]` en las decisiones que no son técnicas (razón social, plazos,
jurisdicción, tope de responsabilidad).

**Dos cosas bloquean la firma del DPA**, y están marcadas dentro del propio
texto:

1. La **exportación de datos por cliente no existe** — la prometen la
   cláusula 12 de los ToS y la cláusula 8 del anexo.
2. El **respaldo fuera del servidor no está operativo** — el anexo lo declara
   hoy como limitación explícita.

Firmar el anexo mientras esas dos líneas sigan siendo ciertas es prometer por
escrito algo que el sistema no hace.
