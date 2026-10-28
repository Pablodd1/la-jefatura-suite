# Guía Actualizada (2026): Conexión Oficial Meta WhatsApp Cloud API + Gmail y Google Calendar de Juan

Esta guía contiene los **pasos exactos actualizados a la interfaz 2026 de Meta Developer Portal (`Use Cases` / Casos de Uso)**, el registro de método de pago en **Meta Billing Hub**, y los pasos para conectar el **Gmail y Google Calendar de Juan**.

---

## PARTE 1: Inscripción, Pago y Conexión en Meta WhatsApp Cloud API (Interfaz Actualizada 2026)

> **¿Cuánto cobra Meta?**
> - **Recibir, monitorear y leer mensajes entrantes:** **$0.00 USD (Gratis e ilimitado).**
> - **Responder mensajes dentro de las 24 horas (Conversaciones de servicio):** **$0.00 USD (Gratis e ilimitado).**
> - **¿Por qué pide tarjeta Meta?** Meta exige registrar una tarjeta en *Facturación y pagos* únicamente para activar el número en modo Producción (fuera de prueba). Solo se cobra ($0.01–$0.08 USD) si envías plantillas masivas de marketing iniciadas por ti fuera de la ventana de 24h.

### Paso 1 — Crear la App en el Nuevo Flujo «Casos de Uso (Use Cases)» de Meta
1. Entra al portal oficial de desarrolladores de Meta:
   👉 **[https://developers.facebook.com/apps/](https://developers.facebook.com/apps/)**
2. Haz clic en el botón verde **Crear app (Create App)**.
3. **Detalles de la app (App details):**
   - **Nombre de la app:** `La Jefatura Suite`
   - **Correo de contacto:** Tu correo o el de Juan
   - Haz clic en **Siguiente (Next)**.
4. **Añadir casos de uso (Add use cases) — *(Nuevo paso 2026)*:**
   - Selecciona la casilla: **«Conectar con los clientes a través de WhatsApp» (`Connect with customers through WhatsApp`)**.
   - Haz clic en **Siguiente (Next)**.
5. **Portafolio comercial (Business portfolio):**
   - Selecciona tu portafolio comercial de Meta (o elige *Crear un portafolio comercial nuevo*).
   - Haz clic en **Siguiente (Next)** -> **Crear app (Create App)**.

### Paso 2 — Conectar el Número de WhatsApp y Copiar `Phone Number ID` + `WABA ID`
1. Dentro del panel de tu nueva app, en el menú izquierdo haz clic en:
   **Casos de uso (Use cases)** -> **Personalizar (Customize)** junto a *Conectar con los clientes a través de WhatsApp* -> **Configuración de la API (API Setup)**.
2. Baja hasta **Paso 5: Agregar un número de teléfono (Add a phone number)**:
   - **Opción Coexistencia (Seguir usando WhatsApp Business en el celular):** Elige *«Conectar tu aplicación WhatsApp Business existente»* y escanea el código QR desde tu celular.
   - **Opción Número Dedicado:** Ingresa el número telefónico de la empresa y verifícalo con el código de 6 dígitos por SMS o llamada.
3. En la parte superior de **Configuración de la API (API Setup)**, selecciona tu número en el desplegable **«De (From)»** y copia estos **2 números de 15 dígitos**:
   - **1) Identificador de número de teléfono (`Phone Number ID`)**
   - **2) Identificador de la cuenta de WhatsApp Business (`WABA ID`)**

### Paso 3 — Registrar Método de Pago en Meta (Activar Producción)
1. Abre directamente el panel de **Administración de WhatsApp -> Facturación y Pagos** (o desde *Paso 6: Agregar método de pago* en Configuración de la API):
   👉 **[https://business.facebook.com/wa/manage/home/](https://business.facebook.com/wa/manage/home/)**
   👉 Enlace directo a tarjetas en Meta Billing: **[https://business.facebook.com/billing_hub/payment_methods](https://business.facebook.com/billing_hub/payment_methods)**
2. Haz clic en **Agregar método de pago (Add payment method)**, registra la tarjeta corporativa (USD / Estados Unidos) y asígnala como método predeterminado de tu cuenta de WhatsApp Business.

### Paso 4 — Generar el Token Permanente (No caduca a las 24 horas)
*(El token que aparece en "Configuración de la API" caduca en 24h; sigue este enlace para generar el token definitivo):*
1. Entra a **Configuración del Negocio -> Usuarios del Sistema**:
   👉 **[https://business.facebook.com/settings/system-users](https://business.facebook.com/settings/system-users)**
2. Haz clic en **Agregar (Add)** -> Nombre: `LaJefaturaBot` -> Rol: **Administrador (Admin)** -> **Crear usuario del sistema**.
3. Haz clic en **Asignar activos (Assign Assets)**:
   - En **Apps**, selecciona `La Jefatura Suite` -> activa **Control total (Manage app)**.
   - En **Cuentas de WhatsApp (WhatsApp Accounts)**, selecciona tu cuenta -> activa **Control total**.
   - Guarda los cambios.
4. Haz clic en **Generar nuevo token (Generate new token)**:
   - Selecciona la app `La Jefatura Suite`.
   - Caducidad (Token expiration): **Nunca (Never)**.
   - Marca estos 2 permisos:
     - ✅ `whatsapp_business_messaging`
     - ✅ `whatsapp_business_management`
   - Haz clic en **Generar token** y copia el código largo que empieza por **`EAA...`** (**3) `Permanent Access Token`**).

### Paso 5 — Conectar el Webhook en Meta (Para Recibir, Leer en Voz Alta y Pre-Redactar)
1. Vuelve a tu app en **[https://developers.facebook.com/apps/](https://developers.facebook.com/apps/)** -> menú izquierdo **Casos de uso (Use cases) -> Personalizar (Customize) -> Configuración (Configuration)**.
2. En la sección **Webhook**, haz clic en **Editar (Edit)** y pega:
   - **URL de devolución de llamada (Callback URL):**
     - **Enlace activo ahora mismo:** `https://networking-jumping-kit-sequence.trycloudflare.com/api/whatsapp/webhook`
     - **En tu dominio de Hostinger:** `https://TU-DOMINIO.com/api/whatsapp/webhook`
   - **Token de verificación (Verify token):** `lajefatura_meta_verify_2026`
3. Haz clic en **Verificar y guardar (Verify and save)**.
4. Debajo, en **Campos del webhook (Webhook fields)**, busca **`messages`** y activa **Suscribir (Subscribe)**.

---

## PARTE 2: Instrucciones Paso a Paso para Juan (Gmail + Google Calendar)

Envíale estos 2 pasos a **Juan** para conectar su correo Gmail (monitoreo + borradores + lectura) y su Google Calendar:

### Paso 1 — Contraseña de Aplicación de Google (16 letras para Gmail)
1. Juan entra con su cuenta de Gmail a este enlace directo de seguridad de Google:
   👉 **[https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)**
   *(Si Google pide activar primero la Verificación en 2 pasos, se activa en 1 minuto aquí: [https://myaccount.google.com/signinoptions/two-step-verification](https://myaccount.google.com/signinoptions/two-step-verification))*
2. En **Nombre de la aplicación (App name)** escribe: `La Jefatura` y pulsa **Crear (Create)**.
3. Google mostrará un recuadro amarillo con **16 letras** (ej. `abcd efgh ijkl mnop`). Juan copia esas 16 letras.

### Paso 2 — Dirección Secreta iCal de Google Calendar
1. Juan entra a la configuración de su Google Calendar desde su computadora:
   👉 **[https://calendar.google.com/calendar/u/0/r/settings](https://calendar.google.com/calendar/u/0/r/settings)**
2. En la columna izquierda, bajo **«Configuración de mis calendarios»**, hace clic en su nombre / calendario principal.
3. Baja hasta la sección **«Integrar el calendario» (Integrate calendar)** y copia el enlace que dice **«Dirección secreta en formato iCal» (Secret address in iCal format)** (termina en `/basic.ics`).

---

## RESUMEN: ¿Qué debes entregarme o pegar en la pestaña «Configuración (1-Vez)» / «Bandeja IA»?

### Para Meta WhatsApp Oficial:
1. **`Phone Number ID`** (15 dígitos)
2. **`WhatsApp Business Account ID (WABA ID)`** (15 dígitos)
3. **`Permanent Access Token`** (`EAA...`)

### Para el Gmail y Google Calendar de Juan:
1. **Correo Gmail de Juan** (ej. `juan@gmail.com`)
2. **Contraseña de aplicación de Google** (16 letras)
3. **URL Secreta en formato iCal de Google Calendar** (`https://calendar.google.com/calendar/ical/.../basic.ics`)
