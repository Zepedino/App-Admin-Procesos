# Despliegue

Render (web service) + Supabase (Postgres, capa gratuita). Un solo servicio
sirve la API y las páginas.

---

## 1. Base de datos en Supabase

1. Crear un proyecto en Supabase.
2. Copiar la cadena de conexión: **Project Settings → Database → Connection
   string → URI**.
3. Usar el **connection pooler** (puerto 6543) si Render agota conexiones. La
   configuración normaliza `postgres://` y `postgresql://` automáticamente, así
   que se pega tal cual viene.

No hace falta crear tablas a mano: el arranque ejecuta `python -m backend.consola init-db`.

---

## 2. Servicio web en Render

El repositorio incluye `render.yaml`. Al conectar el repositorio, Render lo
detecta y propone el servicio.

**Variables de entorno que hay que cargar en el panel** (nunca en el repositorio):

| Variable | Valor |
|---|---|
| `DATABASE_URL` | cadena de conexión de Supabase |
| `MP_TICKET` | ticket de Mercado Público (Clave Única) |
| `SCRAPER_CONTACTO_EMAIL` | correo de contacto, obligatorio si se activa el scraper |
| `GEMINI_API_KEY` | solo cuando se active M3 |
| `SMTP_PASSWORD` | solo cuando se active el envío de correo |

`APP_SECRET_KEY` la genera Render. El resto de la configuración tiene valores
por defecto seguros en `nucleo/config.py`.

---

## 3. Un solo worker, a propósito

`--workers 1` no es un descuido. El planificador de tareas (APScheduler) corre
**dentro del proceso web**. Con dos workers, cada job se ejecutaría dos veces:
la sincronización nocturna gastaría el doble de cuota de la API, y el tope de
10.000 llamadas diarias no es modificable.

Si algún día hace falta escalar el web (no es el caso con 3 a 10 usuarios), hay
que separar el planificador a un *background worker* propio y desactivarlo en el
proceso web.

---

## 4. Después de desplegar

```
GET /salud            → {"ok": true, ...}   (health check de Render)
GET /sistema/modulos  → estado real de construcción
GET /sistema/jobs     → jobs registrados, próxima ejecución y última corrida
```

Y desde la consola de Render:

```bash
python -m backend.consola doctor
```

Verifica conexión a base de datos, proveedor activo, cuota, ventana horaria y
configuración del scraper. Si el scraper está habilitado sin correo de contacto,
`doctor` lo reporta como problema: RF-2.3 exige user-agent identificable.

---

## 5. Antes del primer despliegue real

- [ ] **Alembic.** Hoy las tablas se crean con `init-db`, que no versiona el
      esquema. Para producción hace falta migraciones antes del primer cambio
      de modelo con datos dentro.
- [ ] **Autenticación.** La matriz de permisos existe (`nucleo/seguridad.py`) y
      está testeada, pero falta el login que la active. Hoy todas las acciones
      quedan auditadas como `sistema`.
- [ ] **Respaldos.** El PRD pide respaldo diario de base y repositorio, y
      **probar la restauración una vez, de verdad**. Supabase respalda la base;
      los archivos de `datos/files` no, porque el disco de Render es efímero: al
      activar M2 hay que mover el almacenamiento a S3 o a Supabase Storage.
- [ ] **Zona horaria.** `APP_TIMEZONE=America/Santiago` es lo que determina la
      ventana 22:00–07:00 y el corte diario de la cuota.
