# Cómo obtener el ticket de la API de Mercado Público

Sin ticket el sistema funciona, pero con respuestas guardadas: no ve licitaciones
nuevas. Este es el paso que lo pone a operar en vivo.

**Verificado en chilecompra.cl/api en octubre de 2026.**

---

## 1. Antes de empezar

Necesitas **Clave Única** de la persona que va a figurar como titular.

- Si no la tienes o está desactivada: <https://claveunica.gob.cl> o cualquier
  centro ChileAtiende.
- El ticket es **uno por persona**, asociado a un RUT y a un correo. No es de la
  empresa. Conviene decidir **a nombre de quién** va antes de pedirlo.

## 2. Pedirlo

1. Entra a <https://www.chilecompra.cl/api/>
2. Acepta los Términos de Uso.
3. Inicia sesión con Clave Única.
4. Completa el formulario con **datos reales**: nombre y apellido, RUT y correo.
5. El código se genera automáticamente y **llega al correo registrado**.

Es gratis. El portal de acceso es
<https://api.mercadopublico.cl/modules/IniciarSesion.aspx>.

## 3. Cargarlo en el sistema

Abre el archivo `.env` que está en la carpeta del proyecto (con el Bloc de notas
basta) y pega el ticket en la línea `MP_TICKET`:

```
MP_TICKET=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX
```

Guarda, cierra la aplicación si está abierta y vuelve a ejecutar
`Iniciar aplicacion.bat`.

> **El `.env` no se sube al repositorio** (está en `.gitignore`), justo para que
> el ticket no termine en GitHub. No lo pegues en ningún otro archivo.

## 4. Comprobar que funciona de verdad

Tener el ticket escrito no garantiza nada: puede estar mal copiado. Para
confirmarlo:

```bash
python -m backend.consola doctor --probar-api
```

Hace **una** llamada real (de las 10.000 diarias) y responde sin ambigüedad:

**Si está bien:**
```
  MERCADO PUBLICO
    proveedor            mercadopublico
    datos en vivo        si
    ticket               configurado (...2844)
    prueba en vivo       consultando el 09-10-2026 ...
    resultado            OK, 1353 licitaciones recibidas
```

**Si está mal copiado:**
```
  [PROBLEMA] la API respondio algo inesperado. Causa mas habitual: el ticket
  es invalido o esta mal copiado en .env. Detalle: la API respondio: Ticket no válido.
```

Ojo con este detalle: ante un ticket inválido la API responde **HTTP 200**, no un
error. Por eso hace falta la prueba explícita; sin ella, el sistema parecería
funcionar y simplemente no traería nada.

Cuando ya esté operando en vivo, el aviso naranja de "Datos de respaldo, no de la
API en vivo" desaparece de todas las pantallas.

## 5. Primera carga de datos

Con el ticket activo, trae un día concreto:

```bash
python -m backend.consola sync-dia 2026-10-09
```

El sistema queda sincronizando solo: todas las noches a las 23:15, más un
refresco cada 4 horas de lo que cierra en menos de 72 horas.

---

## Límites que hay que respetar

Son de ChileCompra, no nuestros, y el sistema los hace cumplir solo.

| Límite | Valor | Qué hace el sistema |
|---|---|---|
| Solicitudes por día | **10.000**, no modificable | Las cuenta antes de llamar y las persiste |
| Umbral de alerta | 80 % | Degrada: solo refresca lo que cierra en < 48 h, y avisa una vez |
| Descargas masivas | Recomendado **22:00–07:00** | El job nocturno corre a las 23:15 y no se ejecuta fuera de esa ventana |
| Validación | Por IP | Pueden restringir según volumen desde una misma IP |

El consumo del día se ve en la portada de la aplicación y en
`python -m backend.consola doctor`.

## Si el ticket no llega al correo

Pasó en este proyecto, así que queda documentado.

**Lo primero que hay que entender:** si la dirección que escribiste en el
formulario **no existía** en ese momento, el correo con el ticket **rebotó**.
Crear después una casilla con esa misma dirección **no recupera** ese mensaje:
los correos rebotados no se vuelven a entregar solos. Hay que pedir un reenvío.

La buena noticia es que, si ya creaste la casilla, ahora la dirección sí existe
y un reenvío sí llegaría.

Qué hacer, en orden:

1. **Repite el proceso completo** en <https://www.chilecompra.cl/api/> con tu
   Clave Única. Es gratis y toma dos minutos. Como el ticket es *uno por
   persona*, lo más probable es que el sistema reconozca que ya tienes uno y te
   lo muestre o lo reenvíe a la casilla registrada — que ahora sí existe.
2. **Revisa spam y correo no deseado** en las dos casillas: la del formulario y
   la asociada a tu Clave Única. Los correos automáticos de servicios del Estado
   caen ahí con frecuencia.
3. **Si sigue sin llegar, llama a la Mesa de Ayuda** (números vigentes desde
   abril de 2026):
   - **600 0061 211** (desde fijo) · **+56 2 2595 0820** (desde móvil)
   - Lunes a jueves 9:00–18:00, viernes 9:00–17:00
   - Ten a mano tu **RUT**, la **fecha** en que pediste el ticket y la
     **dirección de correo** que quedó registrada.
   - Pide explícitamente: **corregir el correo registrado y reenviar el ticket**.

El Centro de Ayuda (<https://ayuda.mercadopublico.cl/>) no tiene formulario de
contacto ni correo de soporte: solo publica esos mismos teléfonos. El canal real
es el telefónico.

> Mientras tanto el trabajo no se detiene: el sistema opera con respuestas reales
> guardadas y avisa en pantalla que no está en vivo.

## Si algo falla al usarlo

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| "Ticket no válido" | Mal copiado: sobra un espacio o falta un carácter | Vuelve a copiarlo del correo, completo |
| "no se pudo contactar" | El portal está caído (está etiquetado como beta) | Reintentar más tarde; el sistema ya reintenta 3 veces solo |
| "cuota agotada" | Se gastaron las 10.000 del día | Esperar al día siguiente; usar `--limite` en las cargas |
| El aviso naranja sigue | La app no se reinició tras editar `.env` | Cerrarla y volver a abrirla |

## Qué hacer si el titular se va de la empresa

El ticket va asociado a una persona. Si esa persona deja la consultora, el ticket
puede dejar de ser válido. Conviene:

- Emitirlo a nombre de alguien estable en el cargo.
- Dejar registrado quién es el titular (anótalo aquí abajo).
- Si hay que cambiarlo, se pide uno nuevo y se reemplaza `MP_TICKET`. No hay que
  tocar nada más del sistema.

**Titular actual:** _(completar cuando se solicite)_
**Fecha de solicitud:** _(completar)_

---

Fuentes: [chilecompra.cl/api](https://www.chilecompra.cl/api/) ·
[claveunica.gob.cl](https://claveunica.gob.cl)
