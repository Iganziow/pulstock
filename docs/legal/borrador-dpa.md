# Anexo de Tratamiento de Datos Personales

> ## ⚠️ BORRADOR — NO PUBLICAR SIN REVISIÓN DE ABOGADO
>
> Anexo al contrato entre Pulstock y cada Cliente, para la Ley 21.719.
>
> **Por qué hace falta:** cuando una cafetería carga en Pulstock los datos de
> sus garzones, ella es la **responsable** de esos datos y Pulstock el
> **encargado**. La ley exige que esa relación conste por escrito. Sin este
> anexo, el Cliente tampoco puede cumplir *su* obligación.
>
> Las medidas de seguridad de la cláusula 6 están **verificadas contra
> producción** el 24-ago-2026 — no son declaraciones aspiracionales.

---

**Anexo al contrato de prestación de servicios de [fecha]**
**Versión:** 1.0

## 1. Las partes y sus roles

**El Cliente** es el **responsable del tratamiento**: decide qué datos
personales carga en Pulstock y para qué.

**Pulstock** es el **encargado del tratamiento**: trata esos datos por cuenta
del Cliente, siguiendo sus instrucciones.

Esta distinción importa: las obligaciones frente a los trabajadores del
Cliente —informarles, atender sus solicitudes— **son del Cliente**. Pulstock
lo asiste, no lo reemplaza.

## 2. Qué se trata, de quién y por cuánto tiempo

| | |
|---|---|
| **Objeto** | Prestación del servicio Pulstock: inventario, punto de venta, pronóstico de demanda |
| **Duración** | Mientras dure el contrato, más el plazo de exportación posterior |
| **Naturaleza** | Almacenamiento, consulta, análisis estadístico, copias de respaldo |
| **Titulares** | Trabajadores del Cliente; contactos de proveedores; ocasionalmente, nombre de un consumidor en una comanda |
| **Categorías** | Identificación (nombre, correo, usuario), RUT de proveedores, registros de actividad laboral asociados a ventas y propinas |
| **Datos sensibles** | **Ninguno.** El sistema no está diseñado para tratar datos sensibles, y el Cliente se obliga a no cargarlos |

## 3. Instrucciones del Cliente

Pulstock trata los datos **únicamente** conforme a las instrucciones
documentadas del Cliente, que son las derivadas del uso normal del servicio y
las que el Cliente comunique por escrito.

Pulstock **no usará los datos del Cliente para fines propios**, ni para
entrenar modelos que se apliquen a otros clientes, ni para publicidad.

> **Nota técnica relevante:** el motor de pronóstico se entrena **con los
> datos de cada cliente por separado**. Los modelos de un negocio no usan ni
> ven datos de otro. Esto está verificado con pruebas automatizadas de
> aislamiento.

Si una instrucción del Cliente pareciera infringir la ley, Pulstock lo
informará y podrá suspender su ejecución.

## 4. Confidencialidad

Pulstock garantiza que quienes acceden a los datos están sujetos a
confidencialidad y acceden solo en la medida necesaria para prestar el
servicio o dar soporte.

## 5. Subencargados

El Cliente autoriza a Pulstock a recurrir a los siguientes subencargados:

| Subencargado | Función | Ubicación |
|---|---|---|
| Hetzner Online GmbH | Alojamiento del servidor y la base de datos | Helsinki, Finlandia (UE) |
| Brevo (Sendinblue) | Envío de correos del sistema | Unión Europea |
| Flow.cl | Procesamiento del cobro de la suscripción | Chile |
| Functional Software (Sentry) | Registro de errores técnicos | Estados Unidos |
| [Backblaze] | Copias de respaldo **cifradas** | [pendiente] |

Pulstock avisará con antelación razonable cualquier incorporación o cambio, y
el Cliente podrá oponerse por motivos fundados.

Pulstock responde ante el Cliente por el cumplimiento de sus subencargados.

## 6. Medidas de seguridad

Verificadas al 24-ago-2026:

**Técnicas**
- Cifrado en tránsito (HTTPS) en la totalidad del servicio
- Copias de respaldo cifradas con **AES-256** antes de salir del servidor, con
  la clave fuera del alcance del proveedor de almacenamiento
- **Restauración de respaldos probada de extremo a extremo**, no solo asumida
- Contraseñas con hashing estándar, nunca en texto plano
- Aislamiento lógico entre clientes, cubierto por pruebas automatizadas que se
  ejecutan en cada cambio del código
- Límites de intentos en autenticación y registro

**Organizativas**
- Registro de auditoría de acciones sensibles
- Acceso a producción restringido y autenticado por clave
- Monitoreo con alertas clasificadas por severidad
- Copias de respaldo diarias automatizadas, con alerta si fallan

**Limitaciones que se declaran con honestidad**
- La infraestructura opera en **un solo servidor**, sin redundancia
  geográfica: una falla mayor del proveedor puede causar indisponibilidad
  temporal
- [⚠️ **Al 24-ago-2026 la copia de respaldo fuera del servidor todavía no
  está operativa.** Esta línea debe eliminarse una vez implementada — y no
  debe firmarse este anexo mientras siga siendo cierta.]

## 7. Asistencia al Cliente

Pulstock asistirá al Cliente, en la medida de lo razonable, para:

a) **Atender solicitudes de titulares** (acceso, rectificación, cancelación,
   oposición, portabilidad). Si un titular se dirige a Pulstock directamente,
   se le derivará al Cliente y se informará a este dentro de **[5] días
   hábiles**.

b) **Notificar brechas de seguridad.** Pulstock informará al Cliente **sin
   dilaciones indebidas y, en todo caso, dentro de [24] horas** desde que
   tome conocimiento, con la información disponible para que el Cliente pueda
   cumplir su propio deber de notificar a la Agencia dentro de las 72 horas
   legales.

c) Elaborar evaluaciones de impacto, cuando correspondan.

## 8. Devolución y eliminación al terminar

Terminado el contrato, el Cliente dispone de **[30] días** para obtener la
exportación completa de sus datos en formato reutilizable.

Cumplido ese plazo, Pulstock eliminará los datos de sus sistemas activos. Las
copias de respaldo cifradas se eliminan conforme a su ciclo de rotación
(**[14] días**).

> ⚠️ **La exportación completa de datos por cliente todavía no está
> implementada.** Es requisito de esta cláusula y de la Ley 21.719. Debe
> construirse antes de firmar este anexo.

## 9. Auditoría

Pulstock pondrá a disposición del Cliente la información razonablemente
necesaria para acreditar el cumplimiento de este anexo.

## 10. Obligaciones del Cliente

El Cliente declara y se obliga a:

- Tener **base de licitud** para los datos que carga, en particular los de sus
  trabajadores
- **Informar a sus trabajadores** sobre el tratamiento, incluido que se
  realiza a través de un proveedor y que los datos se alojan fuera de Chile
- **No cargar datos sensibles** ni datos de menores de edad
- Mantener actualizada la lista de personas con acceso al sistema, dando de
  baja a quienes dejen la empresa

## 11. Prevalencia

En caso de contradicción entre este anexo y los Términos de Servicio,
**prevalece este anexo** en lo relativo a protección de datos personales.
