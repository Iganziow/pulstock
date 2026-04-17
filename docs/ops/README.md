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
| Servidor | `<TU_SERVIDOR>` (Hetzner) |
| Usuario SSH | `root` |
| URL app | http://<TU_SERVIDOR> |
| Rama producción | `main` |
| Base de datos | PostgreSQL (local, puerto 5432) |
| Frontend | Next.js en puerto 3000 (PM2) |
| Backend | Django + Gunicorn en puerto 8000 |
| Proxy | Nginx (puerto 80) |

## Contactos de emergencia

- **Flow.cl soporte**: soporte@flow.cl
- **Hetzner soporte**: https://accounts.hetzner.com/
