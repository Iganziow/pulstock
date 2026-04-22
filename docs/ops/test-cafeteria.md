# Checklist de prueba — Pulstock Printer Agent en cafetería

Para validar el sistema de impresión end-to-end con clientes reales **antes
del lanzamiento**. El test cubre los casos críticos del modelo Fudo (PC del
local + agente + celulares del staff).

## Pre-requisitos en el local

- [ ] Un PC del local prendido y con internet.
- [ ] Una impresora térmica de 80mm conectada al PC, instalada en Windows
      como **predeterminada**.
- [ ] Un celular Android o iPhone con datos móviles (para test cross-network).
- [ ] Tu cuenta de admin de Pulstock con rol owner/manager.

## Fase 1 — Instalación del agente

1. [ ] En el PC del local, abrir Chrome → **https://pulstock.cl/agent**.
2. [ ] Apretar "Descargar para Windows" → debe bajar `PulstockAgent.exe` (~30 MB).
3. [ ] **Doble click al .exe**. Esperado:
   - **NO** debe abrir consola negra de cmd.
   - Debe abrir una ventana gráfica con el branding Pulstock.
   - Título: "Conectar este PC al panel".
   - Campo grande para pegar código.
   - Checkbox "Iniciar automáticamente cuando prenda este PC" (default ON).

4. [ ] Si Windows Defender / SmartScreen alerta: apretar "Más información" →
      "Ejecutar de todas formas" (esto pasa porque el .exe no está firmado;
      se puede mejorar después con certificado de Authenticode).

## Fase 2 — Pareo

5. [ ] En tu celular/computadora, ir a **https://pulstock.cl/dashboard/settings**
      → tab "Impresoras" → sección "PC del local".
6. [ ] Apretar "+ Agregar agente PC". Nombre: "PC Cafetería" → "Crear y generar código".
7. [ ] Aparece modal con código tipo `ABCD-1234`. **Copiarlo**.
8. [ ] En el PC, pegar el código en el campo de la ventana del agente.
9. [ ] Apretar "Conectar". Esperado:
   - Mensaje "Conectando…" → ~1-2 segundos → "✓ Conectado como 'PC Cafetería'".
   - La ventana se cierra y aparece un icono morado con "P" al lado del reloj.

10. [ ] Volver al panel web → la página debe mostrar el agente como **🟢 En línea**
       y listar las impresoras detectadas (incluyendo la térmica).

## Fase 3 — Casos críticos de impresión

### 3.1 Imprimir prueba desde el agente (en el PC mismo)

11. [ ] En el PC: click en el icono del system tray → "Mostrar Pulstock" →
       botón **"Imprimir prueba"**. Esperado:
   - Sale un ticket pequeño con texto "PULSTOCK / Prueba de impresion / Si lees esto, todo OK!"
   - Popup en la ventana: "Mandé la prueba a '<nombre impresora>'".

### 3.2 Imprimir desde el celular sin tocar nada local

12. [ ] En el celular (con datos móviles, **no** WiFi del local), ir a
       **https://pulstock.cl/dashboard/pos**.
13. [ ] Hacer una venta de prueba: agregar 1 producto, "Cobrar", método "Efectivo",
       monto exacto.
14. [ ] Después del cobro, en la página del recibo apretar **"Imprimir"**.
       Esperado:
   - **NO** se debe abrir el diálogo "Guardar como PDF" del navegador.
   - En el PC del local, debe sonar/imprimir el ticket de la venta en ~3 segundos.
   - En la ventana del agente, ver: "📄 Imprimiendo job #N en '<impresora>'…"
     → "✓ Job #N impreso correctamente".

### 3.3 Pre-cuenta de mesa

15. [ ] En el celular → tab "Mesas" → abrir/crear una mesa.
16. [ ] Agregar 2-3 items (sin cobrar todavía).
17. [ ] Apretar el botón **"Pre-cuenta"** arriba a la derecha. Esperado:
   - Sale una pre-cuenta en el PC del local.
   - Si la mesa no tiene items pendientes, debe mostrar mensaje "No hay items pendientes" (no debe imprimir vacío).

### 3.4 Boleta automática al cobrar

18. [ ] En la mesa abierta, "Cobrar" → método "Tarjeta débito" → "Confirmar".
       Esperado:
   - Popup verde: "¡Cobro registrado!".
   - **Automáticamente** sale la boleta en el PC del local (sin apretar nada más).

### 3.5 Test negativo: PC apagado

19. [ ] En el PC: click derecho en el icono del tray → "Salir del agente".
       Verificar que el agente no aparece más en el tray.
20. [ ] En el celular, intentar otra venta → "Imprimir". Esperado:
   - **NO** se abre el diálogo de PDF.
   - Aparece un mensaje claro tipo: "El PC 'PC Cafetería' está desconectado. Asegurate de que esté prendido y con internet, después volvé a apretar Imprimir."

21. [ ] Volver a abrir el .exe desde el escritorio o el menú inicio. Esperado:
   - Arranca minimizado al system tray (sin abrir ventana).
   - El panel web muestra el agente como 🟢 En línea otra vez.

22. [ ] Re-imprimir la última boleta desde POS receipt → debe salir bien.

### 3.6 Test del 401 (auto-recovery)

23. [ ] En el panel web, eliminar el agente "PC Cafetería" (botón "Eliminar agente").
24. [ ] En el PC, esperar ~5 segundos. Esperado:
   - Aparece popup: "Sesión cerrada. El servidor desconectó este PC. Esto suele pasar cuando el admin eliminó el agente del panel..."
   - Después del OK, se abre la ventana de re-pareo automáticamente.
25. [ ] Crear un agente nuevo desde el panel, copiar el código, pegarlo en la ventana.
       Apretar Conectar. Esperado:
   - Re-conecta correctamente sin requerir reinstalar el .exe.
   - El config viejo queda como `~/.pulstock_agent/config.invalid_<ts>.json` (auditable).

### 3.7 Test del auto-arranque (requiere reboot)

26. [ ] En el PC, **reiniciar Windows** completamente.
27. [ ] Después del login, esperar 10-20 segundos. Esperado:
   - El icono morado del agente aparece solo en el system tray.
   - El panel muestra el agente como 🟢 En línea sin que nadie haya tocado nada.

## Fase 4 — Caso "tablet con impresora Bluetooth"

> Solo si tenés tablet + impresora térmica BT. Skipeable.

28. [ ] En la tablet, ir a Settings → Impresoras → "+ Agregar impresora" →
       "Bluetooth" → emparejar con la térmica BT.
29. [ ] Marcarla como predeterminada.
30. [ ] Hacer una venta desde la tablet → "Imprimir". Esperado:
   - Sale en la térmica BT directamente (sin pasar por el agente del PC).

## Capturas a tomar (evidencia)

- Screenshot del agente recién conectado (con impresoras detectadas).
- Screenshot del panel web mostrando el agente 🟢 En línea.
- Screenshot del recibo impreso (foto del ticket físico está OK).
- Screenshot del mensaje de error cuando el PC está apagado.

## Si algo falla

- **Logs del agente**: `C:\Users\<tu-usuario>\.pulstock_agent\agent.log`.
- **Backend logs**: `ssh ignacio@65.108.148.200` → `plogs-api`.
- **Frontend logs**: `ssh ignacio@65.108.148.200` → `plogs-web`.
- **Estado rápido**: `ssh ignacio@65.108.148.200` → `pstatus`.

## Resultado esperado

Si todos los checks pasan **EXCEPTO** los marcados como skippeables (sección 4),
el sistema está listo para anunciar a clientes reales del segmento retail/cafetería.

## Issues conocidos (no bloqueantes)

- **Tamaño del .exe**: 30 MB (incluye Tk + pystray + Pillow). Aceptable.
- **Sin firma Authenticode**: Windows SmartScreen alerta al primer arranque. Mitigable comprando un certificado (~$100/año) — no urgente.
- **Migraciones huérfanas en producción**: `pdeploy` lo maneja, sin impacto al cliente. Limpiar en una iteración futura (ver `04-deploy.md` notas).
- **Sin "áreas de impresión" tipo Fudo**: todos los items van a la impresora default del PC. Implementar cuando entre un cliente gastronómico con cocina+barra separadas.
