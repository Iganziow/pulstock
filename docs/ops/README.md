# Manual de Operaciones — Pulstock

Guía práctica para mantener Pulstock en producción sin soporte externo.

## Índice

1. **[Acceso al servidor](01-acceso-servidor.md)** — SSH, usuarios, ubicaciones
2. **[Arquitectura](02-arquitectura.md)** — Qué corre dónde
3. **[Comandos diarios](03-comandos-diarios.md)** — Los 10 comandos que más vas a usar
4. **[Deploy de cambios](04-deploy.md)** — Cómo subir código nuevo
5. **[Revisar logs](05-logs.md)** — Dónde buscar cuando algo falla
6. **[Backups](06-backups.md)** — Respaldos y restauración
7. **[Errores comunes](07-errores-comunes.md)** — Troubleshooting rápido
8. **[Emergencias](08-emergencias.md)** — Servidor caído, pérdida de datos
9. **[Mantenimiento periódico](09-mantenimiento.md)** — Tareas mensuales

## Datos rápidos

| Item | Valor |
|------|-------|
| Servidor | `65.108.148.200` (Hetzner, `ubuntu-4gb-hel1-2`) |
| Usuario SSH | `ignacio` — **no** `root`, root no tiene login |
| App | https://pulstock.cl |
| API | https://api.pulstock.cl |
| Rama producción | `main` |
| Base de datos | PostgreSQL (local, puerto 5432) |
| Frontend | Next.js puerto 3000, bajo PM2 **como root** (`sudo pm2 list`) |
| Backend | Django + Gunicorn, 5 workers, puerto 8000 |
| Proxy | Nginx con HTTPS (certbot renueva solo) |
| Tareas programadas | `/etc/cron.d/pulstock` **y** el crontab de `ignacio` — ver abajo |

### Dos lugares con tareas programadas

Esto sorprende y conviene saberlo antes de necesitarlo:

- **`/etc/cron.d/pulstock`** — facturación, trials, alertas de quiebre, ABC semanal.
- **`crontab -l` del usuario `ignacio`** — el pipeline del forecast **y el backup diario**.

El segundo no está en el repo ni en `/etc/cron.d/`. Si se pierde ese crontab,
el forecast y los respaldos dejan de correr **sin avisar**. Ver
[Mantenimiento periódico](09-mantenimiento.md).

## Contactos de emergencia

- **Flow.cl soporte**: soporte@flow.cl
- **Hetzner soporte**: https://accounts.hetzner.com/
