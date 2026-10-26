# Subir este proyecto a GitHub

GitHub CLI ya está instalado (`gh` 2.103.2). Falta solo iniciar sesión, que
requiere tus credenciales y por eso lo haces tú.

## 1. Iniciar sesión

Abre una terminal **nueva** (para que tome el `gh` recién instalado) y ejecuta:

```bash
gh auth login
```

Responde: **GitHub.com** → **HTTPS** → **Yes** (autenticar git) → **Login with a
web browser**. Copia el código que aparece, pulsa Enter y pégalo en el navegador.

## 2. Crear el repositorio y subir

Desde la carpeta del proyecto, un solo comando:

```bash
gh repo create app-admin-procesos --private --source=. --remote=origin --push
```

Eso crea el repositorio **privado**, lo conecta y sube los 16 commits.

> **Privado, no público.** El repositorio contiene el PRD y los antecedentes de
> la consultora. Si más adelante quieres mostrárselo a otra área, invítalos
> desde *Settings → Collaborators*, que es mejor que hacerlo público.

## 3. Comprobar

```bash
gh repo view --web
```

---

## Qué NO se sube (verificado)

| | |
|---|---|
| `.env` | Tu ticket de Mercado Público. Está en `.gitignore`. |
| `datos/` | Base de datos local y archivos descargados. Se recrean solos. |
| `informe/` | HTML generados. Son salida del comando, no fuente. |
| `.venv/` | Entorno virtual. |

Antes de preparar esto se hizo un barrido sobre los 114 archivos versionados
buscando tickets, claves y RUT de personas. Resultado: limpio. Los RUT que
quedan son de organismos del Estado (60.x, 61.x), que son institucionales, y los
de los tests son inventados.

## Si prefieres no usar la terminal

1. Entra a <https://github.com/new>
2. Nombre: `app-admin-procesos`, visibilidad **Private**, sin README ni
   `.gitignore` (este proyecto ya los trae).
3. Luego, en la carpeta del proyecto:

```bash
git remote add origin https://github.com/TU-USUARIO/app-admin-procesos.git
git push -u origin master
```
