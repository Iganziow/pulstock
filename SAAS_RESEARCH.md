# SAAS_RESEARCH.md — Análisis completo de Pulstock contra las bases establecidas

> Investigación 17-jul-2026, 6 agentes en paralelo (~60 fuentes): estándares POS/Chile (SII, Transbank),
> arquitectura multi-tenant (AWS, Citus, Ley 21.719), dominio de inventario (Odoo/ERPNext/SAP B1/GS1),
> negocio SaaS SMB vertical (Fudo/Toteat/Toast/casos), ingeniería de producción (Django/Celery/Postgres),
> y benchmark de features (6 competidores). Complementa `FORECAST_RESEARCH.md` (motor de forecast).
> Formato: (a) qué ya hacemos bien, (b) brechas por criticidad, (c) plan por plazos.

---

## A. Qué ya hacemos bien (validado contra el estado del arte)

| Área | Validación |
|---|---|
| **Multi-tenancy** | Shared schema + tenant_id es el patrón correcto a esta escala (consenso AWS/PlanetScale 2026). NO re-arquitecturar; endurecer con capas (tests → scoping ORM → RLS). |
| **Inventario** | Nuestra arquitectura StockMove (ledger append-only con cost_snapshot) + StockItem (caché con invariante) es EXACTAMENTE la de ERPNext (SLE + Bin). WAC por bodega es el método correcto para el segmento y para el kardex chileno (Res. Ex. 985/1975). |
| **UoM/recetas** | Conversión por factor a unidad base + conversión en recetas testeada = patrón núcleo de Odoo. |
| **Mesas** | No comprometer stock por comandas abiertas = idéntico a Odoo POS (descuenta al pagar). |
| **POS** | Comanda impresa correcta para cafés chicos (KDS se justifica con volumen alto). Registrar pagos de tarjeta manualmente = práctica aceptada en POS chicos. Idempotency keys = la pieza que haría seguro un futuro modo offline. |
| **Forecast** | ÚNICO en el tier LatAm (solo Toast IQ en EEUU, ~US$150-250/mes extra). Ni Fudo ni Toteat ni Loyverse lo tienen. ES el diferenciador. |
| **Kardex** | KardexView + cost_snapshot + ref_type ya tienen la materia prima del Libro de Existencias chileno. |
| **Pricing implícito** | Mesas incluidas (Fudo las cobra aparte $4.500); precio plano sin % de venta (Toteat cobra 0,35-0,7%). |

## B. Brechas por criticidad

### 🔴 CRÍTICO — riesgo existencial o bloqueante comercial

1. **Backups solo locales** (mismo servidor Hetzner): si el disco muere/ransomware → datos Y backups perdidos.
   Fix: rclone del dump cifrado a Storage Box/B2 (horas). Luego: PITR con wal-g/Barman (RPO minutos),
   restore de prueba mensual, RPO/RTO por escrito. *(pgBackRest: anunció abandono abr-2026, se retractó may-2026 — wal-g/Barman es la opción conservadora hoy.)*
2. **Boleta electrónica SII** — obligatoria por ley (21.210); sin ella Pulstock es sistema "paralelo" con doble digitación.
   Fudo/Toteat/Bsale la incluyen en todos los planes. Vía: API de proveedor autorizado (Openfactura/Haulmer
   —el que usa Fudo—, SimpleAPI ~5-12 UF/año, LibreDTE). Esfuerzo 2-4 semanas con sandbox. Diseño: modelo Dte
   por venta, folios CAF, certificado digital por tenant, nota de crédito al anular, boleta impresa vía
   pulstock-agent (timbre PDF417). Bonus: alertar folios por agotarse (Fudo no lo hace — queja documentada).
   **Bloqueante para vender al cliente 2.**
3. **Ley 21.719 protección de datos — vigencia plena 1-dic-2026** (~4,5 meses): registro de actividades de
   tratamiento, ARCO ≤30 días, notificación de brechas ~72h, export/borrado por tenant, DPAs con Hetzner/Flow/Brevo,
   política de privacidad. Pymes: amonestación en primera infracción. Mayormente documental + 2 features.
4. **Sin dead man's switch en crons** (forecast, billing renewals, backup): fallo nocturno = silencio.
   healthchecks.io (gratis) o Sentry Crons con `monitor_beat_tasks=True`. Horas.
5. **Sin error tracking**: un 500 en checkout de Flow solo se ve si el cliente reclama. Sentry free tier
   (5k errores/mes, Django+Next). Medio día.

### 🟠 ALTO — producto (brechas vs competencia) y dominio

6. **Modificadores/variantes en POS** — brecha #1: hasta los POS gratis (Loyverse, Square Free) los tienen.
   Ya identificada con los helados de Mario (ítem #2 del doc). Patrón de datos: receta base + "receta delta"
   por modificador (Restaurant365/Toast). Habilita: sabores, leches vegetales, tamaños, auto-86.
7. **Registrar el shortfall del clamp** (venta sin stock → consumo clampeado se pierde del ledger): campo
   `qty_short` o move compensatorio. Kardex fiel + señal real de demanda al forecast. Continuación natural
   del fix de demanda fantasma. Bajo esfuerzo.
8. **Audit log append-only** (django-auditlog): ventas, anulaciones, ajustes, precios, caja, roles — con
   tenant_id. La primera disputa "yo no anulé esa venta" sin trazabilidad destruye confianza. Bajo esfuerzo.
9. **Arqueo estándar**: conteo CIEGO (contar sin ver el esperado — antifraude #1, días de esfuerzo),
   over/short por sesión/cajero como dato de primera clase, retiros parciales (drops) con comprobante.
10. **Tests de aislamiento cross-tenant en CI**: fixtures 2 tenants + test paramétrico de endpoints.
    La defensa más barata contra el incidente más grave. Bajo esfuerzo.
11. **Dunning**: revisar que el middleware 402 NO corte al primer fallo de Flow. Estándar: reintentos días
    1/3/5/7 (~58% recuperación) + email en español + gracia. 20-40% del churn SaaS es involuntario.
12. **Menu engineering report** (matriz popularidad × margen, estrellas/perros): el reporte #1 que piden
    los dueños; casi gratis con nuestro PPP; Fudo/Toteat no lo tienen bien. + ventas por hora, por garzón
    ponderado por margen.
13. **Merma % por línea de receta** (Scrap % de Odoo): merma planificada al costeo + demanda efectiva al
    forecast. Bajo-medio.
14. **Compra a costo 0 exige flag explícito** ("¿bonificación?") — hoy diluye el PPP silenciosamente. Bajo.
15. **Auditoría periódica del ledger**: command `audit_ledger_balance` (on_hand == Σ moves) — el "Stock
    Ledger Variance" de ERPNext. Detectaría el próximo drift antes que el dashboard. Bajo.

### 🟡 MEDIO — endurecimiento y features de segunda ola

16. Celery: `transaction.on_commit()` al despachar, idempotencia + acks_late, retries con backoff (Flow).
17. Migraciones expand-contract + django-pg-zero-downtime-migrations; verificar HUP de Gunicorn sin preload_app.
18. Postgres en dev (docker-compose) + CI contra Postgres — matar SQLite (1.800 tests validan otro motor).
19. Hypothesis (property-based) para invariantes de dinero (stock_value, PPP, IVA) — habría cazado el bug de julio.
20. pg_stat_statements + tuning PGTune + pool nativo Django 5.1 (`OPTIONS: {"pool": True}`) + autovacuum
    en StockMove/SaleLine.
21. Export por tenant (portabilidad 21.719 + offboarding + argumento de venta vs Toteat que "pierde históricos").
22. Menú QR view-only (table stakes: Fudo lo regala; como canal de pedido está sobrevendido — 88-90% prefiere carta).
23. Landed costs (flete prorrateado por monto en compras) — brecha de costeo concreta para Chile.
24. Tolerancia + aprobación en ajustes de conteo (umbral $ → confirmación MANAGER); maker-checker con PIN
    para anular ventas.
25. RLS de Postgres como defensa en profundidad; scoping automático de tenant en ORM (manager base).
26. Rate limiting por tenant (noisy neighbor); telemetría con tenant_id en logs/Celery.
27. 2FA para OWNER/superadmin; pip-audit + npm audit + dependabot en CI; CSP con nonce en Next.
28. Plan anual 15% dcto ("2 meses gratis") — retención 92% vs 68% mensual. Paridad Fudo.
29. Structured logging (django-structlog) con request_id + tenant_id propagado a Celery.
30. Export kardex formato contador chileno (saldo valorizado acumulado por fila + Excel).

### 🟢 LARGO PLAZO — segunda ola de producto

31. Integración pago tarjeta: Transbank POS Integrado (agente local = misma arquitectura que pulstock-agent,
    fusionables) o MP Point Orders API (cloud, 1-2 semanas). Cuando la base lo pida.
32. Modo offline acotado: 1 dispositivo, cola IndexedDB + replay con idempotency_key (ya existente);
    folios CAF precargados permiten timbrar boletas offline. 4-8 semanas bien hecho.
33. KDS web (tablet cocina, bump/recall, color por espera) — evolución natural del flujo de comandas.
34. Fidelización con puntos simple — Fudo y Toteat NO la tienen nativa; Loyverse la regala.
35. Delivery vía agregador (Deliverect integra Rappi/PedidosYa) — para cafetería es nice-to-have
    (comisiones 29-30% + café viaja mal); Fudo lo monetiza a $9.500/mes.
36. Conteo cíclico ABC sugerido ("productos a contar hoy"); stock freeze por período contable.
37. Parser barcode pesables GS1 (prefijo 2X con peso embebido) — solo si aparece cliente con balanza.
38. Tenant demo/sandbox con datos de ejemplo (conversión de trials).

## C. Negocio (calibración de mercado)

- **Precio objetivo**: $35-50k CLP/local + IVA (entre Avanzado y Pro de Fudo: $34.500/$52.500; Toteat $39.900+0,7%;
  piso Loyverse gratis). Anual con 15% dcto. El forecast justifica el premium — pitch en PESOS AHORRADOS
  (inventario reduce food cost 2-5%: $60-150k/mes para una cafetería que compra $3M).
- **Activación**: evento medible = primer conteo completo + primera sugerencia de compra acertada. Vigilar
  semanas 2-8 (el software de inventario se abandona en los primeros 60 días si crea más trabajo del que quita).
  Nuestra ventaja estructural: POS+inventario un solo sistema = cero doble digitación (barrera #1 citada: 26%).
- **Retención**: health score casero = WAU del OWNER + conteo semanal + compras registradas (semáforo en
  superadmin). Entrenar SIEMPRE 2+ personas por local (si el champion se va: 51% churn en 12 meses). Reporte
  semanal por email al dueño aunque no entre.
- **Ventas**: playbook Toteat = concentración geográfica + logos ancla; playbook Toast = founder en terreno,
  cada problema resuelto es roadmap. Canales: Achiga (convenios), distribuidores de insumos, contadores.
  Marbrava como caso de referencia con números.
- **Churn del rubro**: 44% de restaurantes considera cambiar de POS; motivo #1 = analítica/reportes (lo que
  vendemos). SMB churn 3-7% mensual — la retención importa más que la adquisición.
- **Quejas documentadas de Fudo** (argumentos de migración): soporte ausente en peak, comandas triplicadas,
  errores de inventario, 100% nube sin modo offline, alzas de precio sin aviso.

## D. Plan sugerido por plazos

**Semana 0 (horas, sin tocar producto):** backup off-site (rclone→Storage Box) + healthchecks.io en crons
+ Sentry free + UptimeRobot + pip-audit/dependabot en CI.

**Corto (2-6 semanas):** tests cross-tenant CI · audit log · conteo ciego + over/short · revisar dunning/402
· shortfall del clamp · flag costo-0 · audit_ledger_balance · menu engineering report · export kardex contador
· on_commit en Celery · restore de prueba mensual.

**Mediano (1-3 meses):** **boleta electrónica** (bloqueante cliente 2) · **modificadores POS** (brecha #1,
resuelve helados) · pack Ley 21.719 (deadline dic) · Postgres en dev + Hypothesis · merma % receta · landed
costs · menú QR view-only · plan anual · RLS + scoping ORM · maker-checker · migraciones seguras.

**Largo (3+ meses):** Transbank/MP Point · offline acotado · KDS · fidelización · delivery vía Deliverect ·
conteo cíclico ABC · stock freeze · barcode pesables.

*(El plan de forecast — Sprints B-F — corre en paralelo; ver FORECAST_RESEARCH.md §8.)*
