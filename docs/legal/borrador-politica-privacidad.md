# Política de Privacidad de Pulstock

> ## ⚠️ BORRADOR — NO PUBLICAR SIN REVISIÓN DE ABOGADO
>
> Estructurado según lo que exige la **Ley 21.719** (vigencia plena
> 1-dic-2026): base de licitud declarada por tratamiento, derechos ARCO+ con
> portabilidad, transferencias internacionales, subprocesadores, plazos de
> retención y notificación de brechas.
>
> Los datos de hecho (qué se guarda, dónde, cuánto tiempo) están verificados
> contra producción el 24-ago-2026. Los `[corchetes]` son decisiones
> pendientes.

---

**Última actualización:** [fecha]
**Versión:** 1.0

## 1. Quién trata los datos

**[Razón social], RUT [•]**, domicilio en [•], es responsable del tratamiento
descrito en esta política.

Contacto para materias de datos personales: **[correo]**
*(⚠️ requiere resolver el MX del dominio — hoy ese correo rebotaría)*

## 2. Dos roles distintos, y conviene no confundirlos

Pulstock trata datos personales en **dos calidades**:

**a) Como responsable**, respecto de los datos de quienes contratan el
servicio: nombre, correo, teléfono y RUT del negocio y de la persona que lo
contrata.

**b) Como encargado**, respecto de los datos que el Cliente carga en el
sistema — principalmente **datos de sus trabajadores**. Ahí el responsable es
el Cliente, y Pulstock solo trata esos datos siguiendo sus instrucciones,
conforme al [Anexo de Tratamiento](borrador-dpa.md).

## 3. Qué datos tratamos y con qué base de licitud

| Dato | De quién | Para qué | Base de licitud |
|---|---|---|---|
| Nombre, correo, usuario, contraseña (cifrada) | Usuarios del sistema (dueño y trabajadores del Cliente) | Dar acceso, identificar quién hizo cada acción | Ejecución del contrato |
| Nombre asociado a ventas, propinas y comandas | Trabajadores del Cliente | Trazabilidad operativa, cálculo y reparto de propinas | Ejecución del contrato / interés legítimo del Cliente como empleador |
| RUT, teléfono, correo del negocio | Cliente | Facturación y contacto | Ejecución del contrato / obligación legal tributaria |
| RUT y datos de contacto de proveedores | Proveedores del Cliente | Gestión de compras | Interés legítimo del Cliente |
| Nombre del cliente final en una comanda | Consumidores | Identificar un pedido | Interés legítimo — dato **opcional** que carga el Cliente |
| Registros de acceso y auditoría | Usuarios | Seguridad y trazabilidad | Interés legítimo / obligación de acreditar cumplimiento |
| Datos técnicos de errores | Usuarios | Diagnóstico de fallas | Interés legítimo |

**Lo que NO tratamos:** no mantenemos una base de consumidores finales, no
almacenamos RUT de compradores ni datos de tarjetas de pago. Los pagos con
tarjeta en el local los procesa el terminal del Cliente, no Pulstock.

## 4. Dónde están los datos

**Los datos se almacenan en servidores ubicados en Helsinki, Finlandia**
(proveedor Hetzner), es decir, **fuera de Chile**.

Finlandia pertenece a la Unión Europea y está sujeta al Reglamento General de
Protección de Datos (GDPR), un estándar de protección equivalente o superior
al chileno. [⚠️ **Formulación a validar por el abogado**: la 21.719 tiene
reglas específicas sobre transferencia internacional y el mecanismo aplicable
debe declararse con precisión.]

## 5. Con quién los compartimos — subprocesadores

| Proveedor | Para qué | Dónde |
|---|---|---|
| **Hetzner** | Servidor y base de datos | Finlandia (UE) |
| **Brevo** | Envío de correos del sistema | Unión Europea |
| **Flow.cl** | Cobro de la suscripción | Chile |
| **Sentry** | Registro de errores técnicos | Estados Unidos |
| **Cloudflare** | Resolución del dominio (DNS) | No accede al contenido |
| **[Backblaze B2]** | Copias de respaldo **cifradas** | [pendiente de contratar] |

**No vendemos datos personales ni los cedemos con fines publicitarios.**

Los respaldos se cifran con AES-256 **antes** de salir de nuestro servidor: el
proveedor de almacenamiento no puede leer su contenido.

Publicaremos aquí cualquier cambio en esta lista con antelación razonable.

## 6. Cuánto tiempo los conservamos

| Dato | Plazo |
|---|---|
| Datos operativos (ventas, inventario, usuarios) | Mientras dure el contrato |
| Tras el término del contrato | **[30] días** para exportar; luego eliminación |
| Copias de respaldo cifradas | **[14] días** de rotación |
| Registros de auditoría | [•] — *definir; puede haber exigencia tributaria de 6 años* |

## 7. Los derechos de las personas

Toda persona cuyos datos tratemos puede ejercer sus derechos de **acceso,
rectificación, cancelación, oposición, portabilidad** y **bloqueo**, y
oponerse a decisiones automatizadas.

Cómo ejercerlos: escribiendo a **[correo]**, identificándose. Responderemos
en un plazo máximo de **30 días corridos**.

**Si los datos fueron cargados por un Cliente** (por ejemplo, un trabajador
de una cafetería que usa Pulstock), la solicitud debe dirigirse a ese Cliente,
que es el responsable. Nosotros lo asistiremos para atenderla.

**Cuando el tratamiento se base en el consentimiento**, este puede retirarse
en cualquier momento, con la misma facilidad con que se otorgó, sin afectar
la licitud del tratamiento previo.

## 8. Seguridad

Medidas efectivamente implementadas al [fecha]:

- **Cifrado en tránsito** (HTTPS en todo el servicio)
- **Copias de respaldo cifradas** con AES-256, con restauración probada
- **Contraseñas** almacenadas con algoritmo de hashing, nunca en texto plano
- **Aislamiento entre clientes**, verificado con pruebas automatizadas
- **Registro de auditoría** de las acciones sensibles
- **Límites de intentos** de acceso y de registro
- **Monitoreo** con alertas clasificadas por severidad

Ninguna medida elimina por completo el riesgo. Si ocurre una vulneración que
afecte datos personales, **la notificaremos a la Agencia de Protección de
Datos y a los afectados sin dilaciones indebidas**, dentro de los plazos
legales.

## 9. Cookies y tecnologías similares

Pulstock usa almacenamiento local del navegador y cookies **estrictamente
necesarias** para mantener la sesión iniciada y el funcionamiento del
servicio. **No usamos cookies publicitarias ni de seguimiento de terceros.**
[⚠️ verificar antes de publicar si se incorpora cualquier analítica.]

## 10. Menores de edad

Pulstock es una herramienta profesional, no dirigida a menores de 14 años, y
no recopilamos sus datos a sabiendas.

## 11. Cambios a esta política

Los cambios se publicarán aquí con su fecha y versión. Si son sustanciales,
avisaremos por correo y dentro de la aplicación con al menos **[30] días** de
anticipación.
