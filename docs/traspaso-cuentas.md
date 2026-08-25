# Traspaso — cuentas, servicios y datos personales

Qué servicios sostienen Pulstock, a nombre de quién están, y qué hay que
resolver para la Ley 21.719.

Verificado contra producción el 24-ago-2026.

> **Este archivo NO lleva contraseñas ni claves.** Ninguna. Las credenciales
> viven en el gestor de contraseñas y en `/etc/` del servidor, nunca en el
> repositorio. Acá va únicamente **qué servicio es, para qué sirve, y con qué
> cuenta se entra** — que es lo que hace falta para traspasarlo.

---

## Los servicios

| Servicio | Para qué | Si se cae… | Cuenta |
|---|---|---|---|
| **Hetzner** | El servidor entero (`65.108.148.200`) | Se cae todo | ✏️ *completar* |
| **Cloudflare** | DNS de `pulstock.cl` | El dominio deja de resolver | ✏️ *completar* |
| **Registrador del dominio** | Titularidad de `pulstock.cl` | Se pierde el nombre | ✏️ *completar* |
| **GitHub** | Código (`Iganziow/pulstock`) | No se puede desplegar | Cuenta personal de Ignacio |
| **Brevo** | Envío de correos (`smtp-relay.brevo.com`) | Nadie recibe avisos | ✏️ *completar* |
| **Flow.cl** | Cobros de suscripción | No se puede cobrar | ✏️ *completar* |
| **Sentry** | Alertas de errores | Los fallos pasan inadvertidos | ✏️ *completar* |
| **Backblaze B2** | Respaldos fuera del servidor | **Aún sin crear** | ⚠️ *pendiente* |

**Los campos con ✏️ hay que completarlos con el correo que administra cada
cuenta.** No los invento: un correo equivocado en un documento de traspaso es
peor que un espacio en blanco, porque parece resuelto.

### Cuentas dentro de la aplicación

Verificado en producción el 24-ago-2026:

| Rol | Acceso |
|---|---|
| Dueño de Marbrava | `mario@marbrava.cl` (rol owner, **sin** superadmin) |
| Superadministrador de la plataforma | ⚠️ **Solo `daniel@dev.cl`** — cuenta sin negocio asignado, creada en marzo, último acceso 21-ago |

**Mario no puede operar la plataforma hoy.** No puede gestionar suscripciones,
ver tenants ni nada del modo superadmin: la única llave la tiene una cuenta
cuya titularidad hay que aclarar (¿es la cuenta de desarrollo de Ignacio? ¿un
tercero?). Antes de la entrega: crear la cuenta superadmin de Mario y decidir
qué pasa con `daniel@dev.cl`.

---

## Tres cosas que hay que arreglar antes de entregar

### 1. Flow apunta al entorno de pruebas

```
PAYMENT_GATEWAY=flow
FLOW_BASE_URL=https://sandbox.flow.cl/api      ← sandbox, no producción
```

**Ningún cobro real puede prosperar.** Coincide con que no existe ni una sola
factura en la historia del sistema. Para cobrar de verdad hay que cambiar esa
URL a `https://www.flow.cl/api` y usar las credenciales productivas de Flow.

Después hace falta **una transacción real de prueba**: el camino de cobro
nunca se ejecutó contra el entorno productivo, así que no está verificado.

### 2. El dominio no puede recibir correo

No hay registro **MX**. Cualquier respuesta a `soporte@pulstock.cl` rebota —
el cliente escribe y nadie lo lee, sin que nada avise.

Tampoco hay **SPF**, así que los correos que salen tienen más probabilidad de
caer en spam. Se arregla agregando dos registros en Cloudflare:

```
TXT   @    v=spf1 include:spf.brevo.com ~all
MX    @    (el proveedor de correo que se elija)
```

### 3. Cloudflare solo administra el DNS

Los servidores de nombres son de Cloudflare, pero el tráfico va **directo** al
servidor: responde nginx sin cabeceras de Cloudflare. O sea que el proxy está
apagado y **la IP del servidor es pública**.

No es un error —es una decisión válida— pero conviene saberlo: no hay
protección contra ataques ni caché de Cloudflare delante de la aplicación.

---

## Ley 21.719 — dónde estamos

> No soy abogado y esto no es asesoría legal. Es un inventario de qué hace y
> qué no hace el sistema, para que quien corresponda evalúe.

**Vigencia plena: 1 de diciembre de 2026.**

### Qué datos personales guarda el sistema

Verificado en el modelo de datos:

| Dato | Dónde | De quién |
|---|---|---|
| Nombre, correo, usuario | `core.User` | **Empleados** del local |
| RUT, teléfono, correo | `core.Tenant` | El negocio y su dueño |
| RUT | `purchases.Supplier` | Proveedores (pueden ser personas) |
| Nombre del cliente | `tables.OpenOrder` | Consumidores, opcional |

Lo más relevante es lo primero: **son datos de trabajadores**. En Marbrava hay
garzones identificados por nombre en propinas, ventas y comandas.

Lo tranquilizador: **no se guardan datos de consumidores finales** más allá de
un nombre opcional en la comanda. No hay base de clientes, ni RUT de
compradores, ni datos de tarjetas.

### Qué falta

| Requisito | Estado |
|---|---|
| Poder **exportar** los datos de un negocio | ❌ No existe |
| Poder **borrar** los datos de un negocio | ⚠️ Existe, pero es destrucción total sin exportar antes |
| **Política de privacidad** publicada | ❌ No existe página |
| **Registro de actividades** de tratamiento | ❌ No existe |
| Contratos de tratamiento (**DPA**) con Hetzner, Brevo, Flow, Sentry | ❌ Sin gestionar |
| Rastro de quién accede a los datos | ✅ Existe auditoría en la aplicación |
| Respaldos **cifrados** | ✅ AES256, y no salen sin cifrar |

### Cómo se ve el esfuerzo

La mayor parte es **documental**, no de programación: política de privacidad,
registro de tratamiento, y pedir los DPA a cuatro proveedores que ya los
tienen estandarizados.

De código hacen falta **dos cosas**:

1. **Exportar todos los datos de un negocio** — hoy no hay forma. Es también
   lo que se necesita para que el borrado deje de ser destrucción a ciegas.
2. **Una política de privacidad accesible** desde la aplicación.

Atenuante relevante para el tamaño de este negocio: la ley contempla
**amonestación escrita en la primera infracción** para pymes, no multa
inmediata.

### Lo que ya juega a favor

- Los respaldos se cifran con AES256 **antes** de salir del servidor, así que
  el proveedor externo solo ve un bloque opaco
- El aislamiento entre negocios está verificado con pruebas automatizadas
- Existe auditoría de acciones sensibles dentro de la aplicación
- Las contraseñas se guardan con el algoritmo de Django, nunca en claro

---

## El hueco más grande: no hay contrato con el cliente

Un SaaS no se vende, se licencia — y esa licencia son los Términos de
Servicio, que **no existen**. Marbrava opera sin contrato escrito, sin
limitación de responsabilidad y sin cláusula de no garantía de resultados,
sobre un producto cuyo pronóstico falla por diseño (38% de error semanal,
medido).

Los hechos completos para el abogado están en
[expediente-legal.md](expediente-legal.md). Esto es **más urgente que el
respaldo externo**: un incendio destruye datos; una demanda por daño
consecuencial sin sociedad de por medio compromete el patrimonio personal.

## Orden sugerido

1. **Completar los correos** de esta tabla — es lo que desbloquea todo lo demás
2. **Crear el superadmin de Mario y aclarar `daniel@dev.cl`** — verificado: hoy Mario no tiene acceso
3. **Crear Backblaze B2** — el respaldo sigue sin salir del servidor
4. **MX y SPF** en Cloudflare — hoy nadie puede responderle un correo al soporte
5. **Flow a producción** + una transacción real de prueba
6. **Ley 21.719** — hay tiempo hasta diciembre, y la mayor parte es papel
