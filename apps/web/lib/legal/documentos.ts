/**
 * Contenido de los documentos legales públicos.
 *
 * Fuente única: el índice de la página se genera de acá mismo, así que no
 * puede desincronizarse del cuerpo. Agregar una sección la agrega al índice.
 *
 * El texto sale de `docs/legal/` en el repositorio, que es lo que va a
 * revisar el abogado. Cuando vuelva corregido, se reemplaza acá y se pone
 * BORRADOR en false.
 */

export const BORRADOR = true;

/**
 * Un solo interruptor. Mientras esté en true:
 *   · las páginas muestran el aviso de borrador
 *   · no se indexan en buscadores (robots: noindex)
 *   · no aparecen enlazadas en el pie de la landing
 *
 * Ponerlo en false es lo único que hace falta para publicarlas de verdad.
 * No lo toques hasta que un abogado haya revisado el texto: publicar un
 * contrato es afirmarlo, y afirmar términos que nadie revisó es el problema
 * que estos documentos vienen a cerrar.
 */

export type Bloque =
  | { tipo: "p"; texto: string }
  | { tipo: "sub"; texto: string }
  | { tipo: "lista"; items: string[] }
  | { tipo: "tabla"; encabezados: string[]; filas: string[][] }
  | { tipo: "nota"; texto: string; tono?: "info" | "alerta" };

export type Seccion = { id: string; titulo: string; bloques: Bloque[] };

export type Documento = {
  slug: string;
  titulo: string;
  bajada: string;
  version: string;
  actualizado: string;
  secciones: Seccion[];
};

/* ══════════════════════════════════════════════════════════════════
   TÉRMINOS DE SERVICIO
   ══════════════════════════════════════════════════════════════════ */

export const TERMINOS: Documento = {
  slug: "terminos",
  titulo: "Términos de Servicio",
  bajada:
    "Las reglas del servicio: qué incluye, qué cuesta, de quién son los datos y hasta dónde responde Pulstock.",
  version: "1.0",
  actualizado: "[fecha de publicación]",
  secciones: [
    {
      id: "quienes-somos",
      titulo: "1. Quiénes somos y qué es este documento",
      bloques: [
        {
          tipo: "p",
          texto:
            "Pulstock es un servicio de software para gestión de inventario, punto de venta y pronóstico de demanda, operado por **[razón social]**, RUT **[•]**, con domicilio en **[•]** (en adelante, «Pulstock» o «nosotros»).",
        },
        {
          tipo: "p",
          texto:
            "Estos Términos regulan el uso del servicio por parte de quien lo contrata (en adelante, «el Cliente»). Al crear una cuenta o usar el servicio, el Cliente acepta estos Términos.",
        },
        {
          tipo: "p",
          texto:
            "**Pulstock no se vende: se licencia.** El Cliente obtiene un derecho de uso mientras dure su suscripción; no adquiere propiedad sobre el software.",
        },
      ],
    },
    {
      id: "que-incluye",
      titulo: "2. Qué incluye el servicio",
      bloques: [
        {
          tipo: "lista",
          items: [
            "Registro de ventas, punto de venta y gestión de mesas",
            "Control de inventario con costeo promedio ponderado",
            "Gestión de compras y proveedores",
            "Reportes de ventas, márgenes y stock",
            "Pronóstico de demanda y sugerencias de compra (ver sección 6)",
            "Impresión de comandas y boletas mediante el agente local",
          ],
        },
      ],
    },
    {
      id: "la-cuenta",
      titulo: "3. La cuenta del Cliente",
      bloques: [
        {
          tipo: "p",
          texto:
            "El Cliente es responsable de las credenciales de su cuenta y de las que entregue a su personal, y de las acciones realizadas con ellas.",
        },
        {
          tipo: "p",
          texto:
            "El Cliente debe avisarnos sin demora si detecta un uso no autorizado.",
        },
      ],
    },
    {
      id: "precio",
      titulo: "4. Precio y facturación",
      bloques: [
        {
          tipo: "p",
          texto:
            "El precio es el del plan contratado, informado antes de la contratación y publicado en **[•]**. Se factura por adelantado, por período mensual o anual.",
        },
        {
          tipo: "p",
          texto:
            "**Cambios de precio:** se avisarán con al menos **[30] días** de anticipación. Si el Cliente no acepta el nuevo precio, puede terminar el contrato antes de que entre en vigencia, sin costo.",
        },
      ],
    },
    {
      id: "pagos-fallidos",
      titulo: "5. Pagos fallidos y suspensión",
      bloques: [
        {
          tipo: "p",
          texto:
            "Si un cobro falla, el sistema reintenta automáticamente y avisa al Cliente por correo. Si después de **[N] días** el pago sigue pendiente, el acceso puede suspenderse.",
        },
        {
          tipo: "p",
          texto:
            "**La suspensión no borra los datos.** El Cliente conserva el derecho a exportarlos conforme a la sección 12.",
        },
      ],
    },
    {
      id: "pronostico",
      titulo: "6. El pronóstico de demanda: qué es y qué no es",
      bloques: [
        {
          tipo: "nota",
          tono: "info",
          texto:
            "Esta sección es esencial y conviene leerla completa antes de contratar.",
        },
        {
          tipo: "p",
          texto:
            "Pulstock incluye un motor que estima la demanda futura y sugiere cantidades de compra a partir del historial de ventas del Cliente.",
        },
        {
          tipo: "p",
          texto:
            "**Esas sugerencias son estimaciones, no garantías.** Todo pronóstico tiene error, y el de Pulstock también: al **[fecha]**, el error promedio medido sobre datos reales era de aproximadamente **34% en un horizonte semanal y 60% en un día individual**. Estas cifras se informan por transparencia y varían según el negocio, el producto y la calidad de los datos cargados.",
        },
        { tipo: "sub", texto: "En consecuencia" },
        {
          tipo: "lista",
          items: [
            "**Ninguna compra se ejecuta automáticamente.** Toda sugerencia requiere aprobación explícita del Cliente, que puede modificar o descartar las cantidades antes de aprobarlas.",
            "**La decisión de compra es siempre del Cliente**, que conoce circunstancias que el sistema no puede conocer: eventos, feriados locales, cambios de carta, disponibilidad de proveedores.",
            "El sistema **informa el nivel de confianza** de cada predicción, calculado sobre su error real medido. Cuando la confianza es baja, la interfaz lo advierte y recomienda revisar antes de aprobar.",
            "La calidad del pronóstico depende de que el Cliente mantenga cargados sus productos, recetas y costos. **Datos incompletos producen sugerencias menos precisas.**",
          ],
        },
        {
          tipo: "p",
          texto:
            "**Pulstock no garantiza resultados comerciales** —ni ausencia de quiebres de stock, ni reducción de mermas, ni un nivel determinado de acierto— y no responde por decisiones de compra adoptadas por el Cliente. Ver sección 9.",
        },
      ],
    },
    {
      id: "disponibilidad",
      titulo: "7. Disponibilidad",
      bloques: [
        {
          tipo: "p",
          texto:
            "Trabajamos para mantener el servicio disponible de forma continua, pero **no comprometemos un porcentaje de disponibilidad garantizado**.",
        },
        {
          tipo: "p",
          texto:
            "Puede haber interrupciones por mantenimiento, fallas de terceros proveedores o causas fuera de nuestro control. Cuando sea posible, el mantenimiento programado se avisará con anticipación.",
        },
      ],
    },
    {
      id: "datos-del-cliente",
      titulo: "8. Los datos son del Cliente",
      bloques: [
        {
          tipo: "p",
          texto:
            "**Todos los datos que el Cliente carga o genera usando Pulstock son de su propiedad:** productos, ventas, inventario, recetas, clientes y proveedores.",
        },
        {
          tipo: "p",
          texto:
            "Pulstock los trata **por encargo del Cliente**, únicamente para prestar el servicio, conforme a la Política de Privacidad y al Anexo de Tratamiento de Datos.",
        },
        {
          tipo: "p",
          texto:
            "**No usamos los datos del Cliente para otros fines**, ni los vendemos ni cedemos a terceros, salvo a los subprocesadores declarados o cuando lo exija la ley.",
        },
      ],
    },
    {
      id: "responsabilidad",
      titulo: "9. Limitación de responsabilidad",
      bloques: [
        {
          tipo: "p",
          texto:
            "Pulstock responde por los perjuicios directos que cause por su culpa en la prestación del servicio.",
        },
        { tipo: "sub", texto: "En la medida en que lo permita la ley aplicable" },
        {
          tipo: "lista",
          items: [
            "La responsabilidad total de Pulstock se limita al **monto efectivamente pagado por el Cliente en los [3-6] meses anteriores** al hecho que origina el reclamo.",
            "Pulstock **no responde por perjuicios indirectos ni lucro cesante**, incluyendo pérdidas derivadas de decisiones de compra tomadas por el Cliente a partir de las sugerencias del sistema (sección 6).",
            "Ninguna disposición de este contrato limita la responsabilidad por dolo o culpa grave, ni los derechos irrenunciables que la ley reconozca al Cliente.",
          ],
        },
      ],
    },
    {
      id: "obligaciones",
      titulo: "10. Obligaciones del Cliente",
      bloques: [
        {
          tipo: "lista",
          items: [
            "Usar el servicio conforme a la ley y para su actividad comercial legítima",
            "Mantener sus datos veraces y actualizados",
            "No intentar acceder a datos de otros clientes ni vulnerar la seguridad",
            "No revender ni sublicenciar el servicio sin autorización escrita",
            "Cumplir sus propias obligaciones legales, incluidas las tributarias y las de protección de datos respecto de sus trabajadores y clientes",
          ],
        },
      ],
    },
    {
      id: "duracion",
      titulo: "11. Duración y término",
      bloques: [
        {
          tipo: "p",
          texto:
            "El contrato se renueva automáticamente por períodos iguales, salvo aviso en contrario.",
        },
        {
          tipo: "p",
          texto:
            "**El Cliente puede terminar cuando quiera**, con efecto al final del período pagado. No corresponde devolución del período en curso, salvo lo indicado en la sección 4.",
        },
        {
          tipo: "p",
          texto:
            "Pulstock puede terminar el contrato dando aviso con **[30] días**, o de inmediato si el Cliente incumple gravemente estos Términos.",
        },
      ],
    },
    {
      id: "datos-al-terminar",
      titulo: "12. Qué pasa con los datos al terminar",
      bloques: [
        {
          tipo: "p",
          texto:
            "Terminado el contrato, el Cliente dispone de **[30] días** para solicitar la exportación completa de sus datos en formato reutilizable, sin costo.",
        },
        {
          tipo: "p",
          texto:
            "Cumplido ese plazo, los datos se eliminan de nuestros sistemas activos. Las copias de respaldo cifradas se eliminan conforme a su ciclo de rotación, que al **[fecha]** es de **[14] días**.",
        },
      ],
    },
    {
      id: "cambios",
      titulo: "13. Cambios a estos Términos",
      bloques: [
        {
          tipo: "p",
          texto:
            "Podemos modificar estos Términos avisando con al menos **[30] días** de anticipación por correo y dentro de la aplicación.",
        },
        {
          tipo: "p",
          texto:
            "**Cada versión se conserva y queda identificada.** Si un cambio afecta sustancialmente los derechos del Cliente, se solicitará una nueva aceptación expresa; si el Cliente no la otorga, podrá terminar el contrato sin costo antes de que el cambio entre en vigencia.",
        },
      ],
    },
    {
      id: "ley-aplicable",
      titulo: "14. Ley aplicable y tribunales",
      bloques: [
        {
          tipo: "p",
          texto:
            "Estos Términos se rigen por la **ley chilena**. Cualquier controversia se someterá a **[los tribunales ordinarios de justicia de [ciudad]]**.",
        },
      ],
    },
    {
      id: "contacto",
      titulo: "15. Contacto",
      bloques: [
        { tipo: "p", texto: "**[correo de contacto]**" },
      ],
    },
  ],
};

/* ══════════════════════════════════════════════════════════════════
   POLÍTICA DE PRIVACIDAD
   ══════════════════════════════════════════════════════════════════ */

export const PRIVACIDAD: Documento = {
  slug: "privacidad",
  titulo: "Política de Privacidad",
  bajada:
    "Qué datos personales tratamos, con qué base legal, dónde se guardan, por cuánto tiempo y cómo se ejercen los derechos sobre ellos.",
  version: "1.0",
  actualizado: "[fecha de publicación]",
  secciones: [
    {
      id: "quien-trata",
      titulo: "1. Quién trata los datos",
      bloques: [
        {
          tipo: "p",
          texto:
            "**[Razón social]**, RUT **[•]**, con domicilio en **[•]**, es responsable del tratamiento descrito en esta política.",
        },
        {
          tipo: "p",
          texto: "Contacto para materias de datos personales: **[correo]**",
        },
      ],
    },
    {
      id: "dos-roles",
      titulo: "2. Dos roles distintos, y conviene no confundirlos",
      bloques: [
        {
          tipo: "p",
          texto: "Pulstock trata datos personales en **dos calidades**:",
        },
        {
          tipo: "p",
          texto:
            "**Como responsable**, respecto de los datos de quienes contratan el servicio: nombre, correo, teléfono y RUT del negocio y de la persona que lo contrata.",
        },
        {
          tipo: "p",
          texto:
            "**Como encargado**, respecto de los datos que el Cliente carga en el sistema, principalmente **datos de sus trabajadores**. Ahí el responsable es el Cliente, y Pulstock solo trata esos datos siguiendo sus instrucciones, conforme al Anexo de Tratamiento de Datos.",
        },
      ],
    },
    {
      id: "que-datos",
      titulo: "3. Qué datos tratamos y con qué base de licitud",
      bloques: [
        {
          tipo: "tabla",
          encabezados: ["Dato", "De quién", "Para qué", "Base de licitud"],
          filas: [
            [
              "Nombre, correo, usuario, contraseña (cifrada)",
              "Usuarios del sistema",
              "Dar acceso e identificar quién hizo cada acción",
              "Ejecución del contrato",
            ],
            [
              "Nombre asociado a ventas, propinas y comandas",
              "Trabajadores del Cliente",
              "Trazabilidad operativa y reparto de propinas",
              "Ejecución del contrato / interés legítimo del empleador",
            ],
            [
              "RUT, teléfono y correo del negocio",
              "Cliente",
              "Facturación y contacto",
              "Ejecución del contrato / obligación legal tributaria",
            ],
            [
              "RUT y contacto de proveedores",
              "Proveedores del Cliente",
              "Gestión de compras",
              "Interés legítimo del Cliente",
            ],
            [
              "Nombre del cliente final en una comanda",
              "Consumidores",
              "Identificar un pedido",
              "Interés legítimo — dato opcional",
            ],
            [
              "Registros de acceso y auditoría",
              "Usuarios",
              "Seguridad y trazabilidad",
              "Interés legítimo / acreditar cumplimiento",
            ],
          ],
        },
        {
          tipo: "nota",
          tono: "info",
          texto:
            "**Lo que NO tratamos:** no mantenemos una base de consumidores finales, no almacenamos RUT de compradores ni datos de tarjetas de pago. Los pagos con tarjeta en el local los procesa el terminal del Cliente, no Pulstock.",
        },
      ],
    },
    {
      id: "donde-estan",
      titulo: "4. Dónde están los datos",
      bloques: [
        {
          tipo: "p",
          texto:
            "**Los datos se almacenan en servidores ubicados en Helsinki, Finlandia** (proveedor Hetzner), es decir, **fuera de Chile**.",
        },
        {
          tipo: "p",
          texto:
            "Finlandia pertenece a la Unión Europea y está sujeta al Reglamento General de Protección de Datos (GDPR), un estándar de protección equivalente o superior al chileno.",
        },
      ],
    },
    {
      id: "subprocesadores",
      titulo: "5. Con quién los compartimos",
      bloques: [
        {
          tipo: "tabla",
          encabezados: ["Proveedor", "Para qué", "Dónde"],
          filas: [
            ["Hetzner", "Servidor y base de datos", "Finlandia (UE)"],
            ["Brevo", "Envío de correos del sistema", "Unión Europea"],
            ["Flow.cl", "Cobro de la suscripción", "Chile"],
            ["Sentry", "Registro de errores técnicos", "Estados Unidos"],
            ["Cloudflare", "Resolución del dominio (DNS)", "No accede al contenido"],
            ["[Backblaze B2]", "Copias de respaldo cifradas", "[pendiente]"],
          ],
        },
        {
          tipo: "p",
          texto: "**No vendemos datos personales ni los cedemos con fines publicitarios.**",
        },
        {
          tipo: "p",
          texto:
            "Los respaldos se cifran con AES-256 **antes** de salir de nuestro servidor: el proveedor de almacenamiento no puede leer su contenido.",
        },
        {
          tipo: "p",
          texto:
            "Publicaremos aquí cualquier cambio en esta lista con antelación razonable.",
        },
      ],
    },
    {
      id: "retencion",
      titulo: "6. Cuánto tiempo los conservamos",
      bloques: [
        {
          tipo: "tabla",
          encabezados: ["Dato", "Plazo"],
          filas: [
            ["Datos operativos (ventas, inventario, usuarios)", "Mientras dure el contrato"],
            ["Tras el término del contrato", "**[30] días** para exportar; luego eliminación"],
            ["Copias de respaldo cifradas", "**[14] días** de rotación"],
            ["Registros de auditoría", "**[•]**"],
          ],
        },
      ],
    },
    {
      id: "derechos",
      titulo: "7. Los derechos de las personas",
      bloques: [
        {
          tipo: "p",
          texto:
            "Toda persona cuyos datos tratemos puede ejercer sus derechos de **acceso, rectificación, cancelación, oposición, portabilidad** y **bloqueo**, y oponerse a decisiones automatizadas.",
        },
        {
          tipo: "p",
          texto:
            "Para ejercerlos, escribir a **[correo]** identificándose. Responderemos en un plazo máximo de **30 días corridos**.",
        },
        {
          tipo: "nota",
          tono: "info",
          texto:
            "**Si los datos fueron cargados por un Cliente** —por ejemplo, un trabajador de una cafetería que usa Pulstock— la solicitud debe dirigirse a ese Cliente, que es el responsable. Nosotros lo asistiremos para atenderla.",
        },
        {
          tipo: "p",
          texto:
            "**Cuando el tratamiento se base en el consentimiento**, este puede retirarse en cualquier momento, con la misma facilidad con que se otorgó, sin afectar la licitud del tratamiento previo.",
        },
      ],
    },
    {
      id: "seguridad",
      titulo: "8. Seguridad",
      bloques: [
        { tipo: "sub", texto: "Medidas efectivamente implementadas" },
        {
          tipo: "lista",
          items: [
            "**Cifrado en tránsito** (HTTPS en todo el servicio)",
            "**Copias de respaldo cifradas** con AES-256, con restauración probada",
            "**Contraseñas** almacenadas con algoritmo de hashing, nunca en texto plano",
            "**Aislamiento entre clientes**, verificado con pruebas automatizadas",
            "**Registro de auditoría** de las acciones sensibles",
            "**Límites de intentos** de acceso y de registro",
            "**Monitoreo** con alertas clasificadas por severidad",
          ],
        },
        {
          tipo: "p",
          texto:
            "Ninguna medida elimina por completo el riesgo. Si ocurre una vulneración que afecte datos personales, **la notificaremos a la Agencia de Protección de Datos y a los afectados sin dilaciones indebidas**, dentro de los plazos legales.",
        },
      ],
    },
    {
      id: "cookies",
      titulo: "9. Cookies y tecnologías similares",
      bloques: [
        {
          tipo: "p",
          texto:
            "Pulstock usa almacenamiento local del navegador y cookies **estrictamente necesarias** para mantener la sesión iniciada y el funcionamiento del servicio. **No usamos cookies publicitarias ni de seguimiento de terceros.**",
        },
      ],
    },
    {
      id: "menores",
      titulo: "10. Menores de edad",
      bloques: [
        {
          tipo: "p",
          texto:
            "Pulstock es una herramienta profesional, no dirigida a menores de 14 años, y no recopilamos sus datos a sabiendas.",
        },
      ],
    },
    {
      id: "cambios-politica",
      titulo: "11. Cambios a esta política",
      bloques: [
        {
          tipo: "p",
          texto:
            "Los cambios se publicarán aquí con su fecha y versión. Si son sustanciales, avisaremos por correo y dentro de la aplicación con al menos **[30] días** de anticipación.",
        },
      ],
    },
  ],
};

export const DOCUMENTOS: Record<string, Documento> = {
  terminos: TERMINOS,
  privacidad: PRIVACIDAD,
};
