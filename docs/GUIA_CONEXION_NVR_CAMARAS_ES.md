# Guía Paso a Paso de Conexión de Cámaras y NVR — La Jefatura (El Jefesito)

> **Para el Cliente / Técnico de Cámaras (IT):**
> **La Jefatura** no reemplaza tu grabador actual ni consume tu internet transmitiendo video pesado las 24 horas. Se conecta de forma ligera y en **solo lectura** a tu **NVR (Grabador Central / Programa Visor)** para tomar capturas puntuales (snapshots) y alertas de eventos, analizando todo con Inteligencia Artificial para el reporte del CEO.

---

## Resumen Rápido: ¿Qué necesitamos de tu empresa? (1 Sola Vez · 10 Minutos)

Para conectar todas las cámaras de una sede a **La Jefatura**, el técnico o encargado de sistemas solo debe realizar **4 pasos sencillos**:

1. **Crear un usuario de "Solo Lectura" (`lajefatura_ai`)** en el NVR / Grabador.
2. **Activar el protocolo estándar RTSP y ONVIF** en el menú de Red del NVR.
3. **Compartir la IP local del NVR y la cantidad de canales** (ej. `192.168.1.100`, canales `1` al `8`).
4. **Activar el puente seguro (Cloudflare Tunnel o Agente Local)** en una PC de la oficina para que el servidor en la nube pueda leer el NVR sin abrir puertos peligrosos en el router.

---

## Paso 1: Crear un Usuario de Solo Lectura en el NVR (Seguridad para el Cliente)

Por seguridad empresarial, **nunca pedimos la clave de administrador principal**. Entra a tu grabador (Hikvision, Dahua, UniFi, Reolink, Amcrest, Uniview, etc.) y crea un usuario exclusivo para el asistente:

- **Usuario sugerido:** `lajefatura_ai`
- **Contraseña:** *(Una contraseña alfanumérica sin símbolos especiales como `@` o `#`, por ejemplo: `Jefatura2026Cam`)*
- **Permisos requeridos (Solo Lectura):**
  - `[✓]` Vista en vivo remota (*Remote Live View / RTSP*)
  - `[✓]` Notificación de eventos / alarmas (*Event / Motion Notification*)
  - `[ ]` *Sin permiso de borrar grabaciones ni cambiar configuración.*

---

## Paso 2: Activar RTSP y ONVIF en el NVR

Todos los grabadores comerciales traen el estándar universal **RTSP / ONVIF** integrado. Solo hay que verificar que esté encendido:

1. Entra al menú del NVR: **Configuración (`Configuration`) → Red (`Network`) → Ajustes Avanzados (`Advanced Settings`) → Protocolo de Integración (`Integration Protocol` / `ONVIF`)**.
2. Marca la casilla **Habilitar ONVIF (`Enable ONVIF`)** (o verifica que el servicio **RTSP** esté activo en el puerto `554`).
3. En la misma pantalla de ONVIF, agrega el usuario `lajefatura_ai` que creaste en el Paso 1 y guarda los cambios.

---

## Paso 3: Formato de Conexión según la Marca de tu NVR (`cameras.json`)

Una vez activo, **un solo NVR nos da acceso a todas las cámaras conectadas** cambiando únicamente el número de canal (`1`, `2`, `3`...).

Nuestro módulo [`server/cameras.py`](../server/cameras.py) utiliza las rutas oficiales de cada fabricante en [`data/samples/cameras.json`](../data/samples/cameras.json):

### 1. Hikvision / Epcom / HiLook / Annke (NVR)
```text
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/Streaming/Channels/101
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/Streaming/Channels/201
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/Streaming/Channels/301
```
*(Donde `101` = Cámara 1 en alta definición, `201` = Cámara 2, `301` = Cámara 3; o `102`, `202` para flujo ligero).*

### 2. Dahua / Lorex / Amcrest / IMOU (NVR)
```text
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/cam/realmonitor?channel=1&subtype=0
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/cam/realmonitor?channel=2&subtype=0
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/cam/realmonitor?channel=3&subtype=0
```
*(Donde `channel=1, 2, 3...` indica el número de cámara y `subtype=0` es alta resolución / `subtype=1` flujo rápido).*

### 3. Uniview (UNV)
```text
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/unicast/c1/s0/live
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/unicast/c2/s0/live
```

### 4. Reolink NVR / Cámaras IP
```text
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/h264Preview_01_main
rtsp://lajefatura_ai:CONTRASEÑA@IP_DEL_NVR:554/h264Preview_02_main
```

### 5. Ubiquiti UniFi Protect
- En la consola de **UniFi Protect**, haz clic en la cámara → **Settings → Advanced → RTSPS Stream**, activa el stream y copia el enlace `rtsps://...` que entrega el sistema.

---

## Paso 4: Prueba Rápida de Verificación (Sin Instalar Nada Complejo)

Antes de guardarlo en **La Jefatura**, el técnico puede comprobar en 10 segundos si el NVR ya responde:

1. **Con VLC Media Player (desde cualquier PC en la misma red Wi-Fi/LAN de la oficina):**
   - Abre VLC → **Medio → Abrir ubicación de red** → pega la dirección `rtsp://...` del Paso 3. Si se ve la imagen, el NVR está 100% listo.
2. **Con el Diagnóstico Automático de La Jefatura (`server/cameras.py`):**
   - Nuestro servidor ejecuta una captura instantánea de 1 cuadro (`ffmpeg -rtsp_transport tcp -i URL -frames:v 1`) que toma menos de 1 segundo y no consume ancho de banda continuo.

---

## Paso 5: ¿Qué Recibe el CEO una vez Conectado? (Cero Adivinanzas)

Una vez ingresados los canales en [`cameras.json`](../data/samples/cameras.json), **El Jefesito** procesa automáticamente y entrega en el Panel de Mando, por Voz y en el Informe PDF Diario:

1. **Control de Apertura y Cierre Puntual:** Hora exacta del primer movimiento en recepción/entrada por la mañana y cierre por la noche.
2. **Alertas Fuera de Horario (`fuera_horario`):** Si hay movimiento o personas en bodega, archivo o caja después de la hora de cierre (`19:00` a `08:00`), guarda la fotografía (snapshot) como evidencia y envía alerta inmediata.
3. **Afluencia en Recepción / Sala de Espera:** Conteo de personas presentes en sala de espera o showroom por franja horaria.
4. **Supervisión de Puestos Clave:** Detecta si la recepción o mostrador quedó desatendido en horario laboral.
5. **Salud de Cámaras (Anti-Sabotaje):** Avisa al instante si alguna cámara o canal del NVR se desconecta o pierde señal.

---

## Plantilla para Llenar por el Cliente / Técnico de la Empresa

Copia y envíanos estos 5 datos para dejar tus cámaras activas en **La Jefatura**:

- **Marca del NVR o Programa Visor:** `________________________`
- **IP Local del NVR (ej. 192.168.1.100) y Puerto RTSP (normalmente 554):** `________________________`
- **Usuario y Contraseña de Solo Lectura creados para La Jefatura:** `________________________`
- **Lista de Canales y Nombre de cada Zona (ej. Canal 1 = Recepción, Canal 2 = Bodega, Canal 3 = Sala de Espera):** `________________________`
- **Horario Laboral de la Sede (ej. Lunes a Viernes 08:00 AM – 06:00 PM):** `________________________`
