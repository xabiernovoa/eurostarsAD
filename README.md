# Eurostars AI Marketing Command Center

Motor de personalización y plataforma de marketing inteligente para la cadena hotelera Eurostars. El sistema toma datos históricos de clientes y un catálogo de hoteles, construye perfiles, segmenta usuarios, genera campañas personalizadas para distintos momentos del viaje y proporciona un dashboard de marketing con asistente conversacional IA, un sistema autónomo multi-agente y demos interactivas.

**No es un generador de campañas: es un ecosistema vivo que transforma datos en decisiones y decisiones en experiencias.**

---

## Qué hace

### Hiperpersonalización 1-a-1
Cada cliente recibe una comunicación única. El sistema analiza el historial de reservas, perfil de viaje, segmento de edad y valor del cliente para generar **emails con texto, tono e imágenes adaptados individualmente**. Un viajero cultural recibe un copy inspiracional con fotos de monumentos; un cliente de lujo recibe un tono premium con imágenes del spa. No es un template con campos dinámicos: es un mensaje pensado para una persona concreta.

### Informes inteligentes para recepción
Antes del check-in, recepción dispone de un **informe personalizado por huésped**: preferencias detectadas, oportunidades de upsell (upgrade de habitación, late checkout, experiencias gastronómicas), historial de estancias y recomendaciones de trato según perfil. El recepcionista no improvisa: llega preparado.

### Adaptación de la experiencia a cada usuario
El sistema no se limita al email. Adapta la experiencia completa del viaje en tres momentos clave:
- **Pre-arrival**: campaña personalizada antes de la estancia, con hotel recomendado, imágenes seleccionadas por IA y eventos relevantes del destino.
- **Check-in**: informe interno con contexto del huésped para que recepción personalice la bienvenida.
- **Post-stay**: comunicación de seguimiento adaptada al perfil para fidelización y reactivación.

### Sistema de sugerencias de acción
Un motor de recomendaciones analiza los datos de campañas, segmentos, señales de recepción y contexto externo (eventos, tendencias, estacionalidad) para proponer **acciones concretas y ejecutables** en tres ejes: redes sociales, acciones dentro del hotel y publicidad externa. El equipo de marketing no parte de una hoja en blanco.

### Sistema autónomo multi-agente
Un motor independiente que opera de forma proactiva: un **Oráculo** recopila contexto externo (eventos culturales, ofertas estacionales, alertas de viaje), un **Scheduler** identifica qué usuarios contactar en este momento, y **múltiples agentes concurrentes** generan campañas personalizadas en paralelo usando Gemini. Todo se visualiza en streaming en tiempo real desde el dashboard.

### Agente conversacional de marketing
Un chat IA integrado en el dashboard que **conoce todos los datos operativos**: KPIs, segmentos, rendimiento por canal, campañas recientes. El responsable de marketing puede preguntar «¿qué segmento funciona peor?», «dame ideas para captar familias este fin de semana» o «analiza la situación actual», y recibe respuestas basadas en datos reales, no genéricos.

---

## Visión general

El proyecto se compone de tres capas principales:

| Capa | Descripción | Entrada |
|------|-------------|---------|
| **Backend batch** | Procesamiento batch de datos → embeddings → segmentación → campañas → render → entrega | `python3 main.py --phase all` |
| **Sistema Autónomo** | Motor multi-agente que consulta un Oráculo de contexto externo, selecciona usuarios candidatos y genera campañas personalizadas en tiempo real con IA (Gemini vía Vertex AI) | `python3 -m backend.autonomous.cli --mode demo` |
| **Demos** | Tres aplicaciones web de demostración (Marketing Dashboard, Gmail demo, Recepción) | `./start_services.sh` |

---

## Arquitectura

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        EUROSTARS AI ENGINE                         │
├──────────────┬──────────────────────┬───────────────────────────────┤
│  Backend     │  Sistema Autónomo    │  Demos                        │
│ (batch)      │  (multi-agente)      │  (demos interactivas)         │
│              │                      │                               │
│ embeddings   │ oracle.py            │ Marketing Dashboard (:3003)   │
│ segmentation │ user_scheduler.py    │   ├── Dashboard analítico     │
│ campaigns    │ campaign_generator   │   ├── Generador de campañas   │
│ assets       │ heartbeat.py         │   ├── Chat IA con Gemini      │
│ content      │ live.py (streaming)  │   └── Modo autónomo live      │
│ rendering    │ gemini_client.py     │                               │
│ channels     │ generic_campaigns    │ Gmail demo (:3001)            │
│ delivery     │ state.py             │   └── Bandeja personalizada   │
│ marketing    │ config.py            │                               │
│              │                      │ Recepción demo (:3002)        │
│              │                      │   └── Informes check-in       │
└──────────────┴──────────────────────┴───────────────────────────────┘
```

---


## Datos de entrada

| Archivo | Descripción |
|---------|-------------|
| `data/raw/customer_data.csv` | Historial de reservas de 200 clientes. Campos: `GUEST_ID`, `HOTEL_ID`, `CHECKIN_DATE`, `CHECKOUT_DATE`, `AVG_BOOKING_LEADTIME`, `AVG_LENGTH_STAY`, `AVG_SCORE`, `CONFIRMED_RESERVATIONS_ADR`, entre otros. Separador: `;` |
| `data/raw/hotel_data.csv` | Catálogo de hoteles con nombre, ciudad, país, estrellas, marca y atributos del destino |
| `images/<hotel_id>/` | Imágenes reales de cada hotel. El pipeline genera automáticamente `metadata.json` con tags |

---

## Instalación

### Requisitos

- Python 3.11+
- pip

### Pasos

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd eurostars

# 2. Crear y activar el entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus claves (ver sección siguiente)
```

### Dependencias principales

| Paquete | Uso |
|---------|-----|
| `pandas`, `numpy`, `scikit-learn` | Procesamiento de datos y embeddings |
| `jinja2`, `premailer` | Renderizado de plantillas HTML de email |
| `google-genai` | Generación de copy y contexto con Gemini vía Vertex AI |
| `anthropic` | Recomendaciones del dashboard (opcional) |
| `Pillow` | Procesamiento de imágenes |
| `sendgrid` | Envío real de emails (opcional) |
| `python-dotenv` | Carga de variables de entorno |

---

## Variables de entorno

El proyecto carga variables desde un archivo `.env` en la raíz. Copia `.env.example` como punto de partida.

### Pipeline batch

| Variable | Obligatoria | Descripción |
|----------|:-----------:|-------------|
| `OPENAI_API_KEY` | No | Genera copy real con OpenAI. Sin ella, usa texto mock |
| `OPENAI_EMAIL_MODEL` | No | Modelo a usar (default: `gpt-5.4-nano`) |
| `OPENAI_EMAIL_MAX_OUTPUT_TOKENS` | No | Límite de tokens para el copy |
| `SENDGRID_API_KEY` | No | Solo necesaria si ejecutas con `--send` |
| `SENDER_EMAIL` | No | Remitente para SendGrid |
| `CAMPAIGN_MAX_WORKERS` | No | Hilos para procesamiento paralelo de campañas |

### Sistema autónomo

| Variable | Obligatoria | Descripción |
|----------|:-----------:|-------------|
| `GOOGLE_APPLICATION_CREDENTIALS` | No | Ruta al JSON de cuenta de servicio de Vertex AI. Puede ser relativa al proyecto |
| `VERTEX_PROJECT_ID` | No | ID del proyecto de Google Cloud |
| `VERTEX_LOCATION` | No | Región de Vertex (default: `us-central1`) |
| `AUTONOMOUS_GEMINI_MODEL` | No | Modelo Gemini (default: `gemini-2.5-flash`) |
| `AUTONOMOUS_GEMINI_TEMPERATURE` | No | Temperatura del modelo (default: `0.7`) |
| `AUTONOMOUS_DRY_RUN` | No | Default: `True` |

### Comportamiento sin API keys

- **Sin `OPENAI_API_KEY`**: el pipeline genera texto mock realista, sin llamar a ningún API.
- **Sin `GOOGLE_APPLICATION_CREDENTIALS`**: el sistema autónomo genera copy mock y el Oráculo usa datos mock de eventos plausibles.
- **Sin `SENDGRID_API_KEY`**: los emails se guardan en disco (`output/`) en vez de enviarse.
- **El proyecto funciona completamente en local sin ninguna API key.** Todas las funcionalidades tienen fallback determinista.

---

## Cómo ejecutar

### 1. Pipeline batch (procesamiento completo)

Ejecuta todas las fases en orden:

```bash
python3 main.py --phase all
```

Esto genera embeddings, segmenta usuarios, crea campañas para los 3 momentos del viaje, selecciona imágenes, genera copy, renderiza HTML y guarda todo en `output/`.

#### Fases individuales

```bash
# Fase 1: Embeddings de hoteles y usuarios
python3 main.py --phase embeddings

# Fase 2: Segmentación de usuarios
python3 main.py --phase segment

# Fase 4a: Auto-etiquetado de imágenes
python3 main.py --phase auto_tag

# Fases 3-8: Campaña por momento del viaje
python3 main.py --phase campaign --moment pre_arrival
python3 main.py --phase campaign --moment checkin_report
python3 main.py --phase campaign --moment post_stay

# Campaña para un usuario concreto
python3 main.py --phase campaign --moment pre_arrival --guest_id 1014907189

# Fase 9: Snapshot del dashboard de marketing
python3 main.py --phase marketing

# Envío real de emails (requiere SendGrid)
python3 main.py --phase campaign --moment pre_arrival --send
```

### 2. Sistema autónomo

El sistema autónomo es un motor independiente que reutiliza los módulos del pipeline para generar campañas de forma proactiva, consultando un Oráculo de contexto externo.

```bash
# Demo end-to-end (5 campañas personalizadas + 1 genérica)
python3 -m backend.autonomous.cli --mode demo

# Un único tick del heartbeat
python3 -m backend.autonomous.cli --mode tick

# Bucle continuo (cada 30 min por defecto)
python3 -m backend.autonomous.cli --mode loop

# Forzar contenido mock (sin llamar a Gemini)
python3 -m backend.autonomous.cli --mode demo --force-mock

# Logs detallados
python3 -m backend.autonomous.cli --mode demo -v
```

### 3. Frontends de demostración

#### Opción A: Todos a la vez

```bash
./start_services.sh
```

Esto arranca los 3 servicios en paralelo. `Ctrl+C` los detiene todos.

#### Opción B: Individualmente

```bash
# Marketing Dashboard → http://localhost:3003
python3 demos/marketing/server.py

# Gmail demo → http://localhost:3001
python3 demos/mail/server.py

# Recepción demo → http://localhost:3002
python3 demos/receptionist/server.py
```

La demo de Gmail lee los perfiles desde `data/raw/customer_data.csv` y los
correos directamente desde `output/`, así que no necesita un paso extra de
regeneración.

---

## Cómo funciona cada componente

### Backend batch

#### Fase 1 — Embeddings

`backend/personalization/embeddings.py`

Transforma atributos de hotel (ciudad, estrellas, marca, país) en vectores de 11 dimensiones. El embedding de cada usuario se calcula como media ponderada de los hoteles que ha visitado. Se guarda en `data/generated/embeddings.json`.

#### Fase 2 — Segmentación

`backend/personalization/segmentation.py`

Clasifica a cada usuario en 4 ejes:

| Eje | Valores posibles |
|-----|-----------------|
| `age_segment` | `JOVEN`, `ADULTO`, `SENIOR` |
| `travel_profile` | `EXPLORADOR_CULTURAL`, `LUJO`, `SOL_Y_PLAYA`, `AVENTURERO`, `GASTRONOMIA_CIUDAD` |
| `client_value` | `STANDARD`, `MID_VALUE`, `HIGH_VALUE` |
| `travel_pattern` | `RECURRENTE_DESTINO`, `EXPLORADOR`, `FIEL_CADENA` |

Se guarda en `data/generated/segments.json`.

#### Fase 3 — Campañas

`backend/campaigns/planner.py`

Genera la estructura de datos de cada campaña:

- Predice la ventana probable de viaje del usuario
- Recomienda un hotel basado en embeddings
- Recupera eventos del destino (mock)
- Resume preferencias del usuario
- Genera oportunidades de upsell para informes de recepción

Tres momentos del ciclo de vida:

| Momento | Descripción |
|---------|-------------|
| `pre_arrival` | Email personalizado antes de la estancia |
| `checkin_report` | Informe interno para recepción |
| `post_stay` | Email posterior a la estancia |

#### Fase 4 — Imágenes

- `backend/assets/image_metadata.py`: Genera `metadata.json` por hotel analizando nombres de archivo e infiriendo tags (spa, gastronomía, habitación, etc.)
- `backend/assets/image_selector.py`: Puntúa imágenes por afinidad con el embedding y segmento del usuario. Devuelve 3-5 imágenes por campaña.

#### Fase 5 — Texto

`backend/campaigns/copy.py`

Dos modos de generación:

| Modo | Condición | Fuente |
|------|-----------|--------|
| Mock | `dry_run=True` o sin credenciales | Copy determinista basado en segmento |
| Real | `dry_run=False` + credenciales Vertex disponibles | Gemini |

También genera SMS cortos (≤160 caracteres) cuando el canal principal es `sms`.

#### Fase 6 — Render HTML

`backend/campaigns/renderer.py`

Renderiza HTML responsive con Jinja2 usando plantillas diferenciadas por segmento:

| Plantilla | Segmento |
|-----------|----------|
| `template_joven.html` | Diseño dinámico, visual, tono cercano |
| `template_adulto.html` | Equilibrado, profesional |
| `template_senior.html` | Claro, legible, tono formal |
| `receptionist_report.html` | Informe interno de check-in |

#### Fase 7 — Canal

`backend/campaigns/channels.py`

Decide entre `email`, `sms` o `push` con reglas basadas en:

- Segmento de edad (jóvenes → push, adultos/senior → email)
- Lead time de reserva (< 7 días → sms)

#### Fase 8 — Entrega

`backend/campaigns/delivery.py`

- `dry_run=True` (default): guarda HTML en `output/`
- `dry_run=False` + `--send`: envía vía SendGrid
- Registra cada acción en `data/generated/campaign_log.json`

#### Fase 9 — Dashboard marketing

`backend/marketing/dashboard.py`

Construye un payload JSON completo para el dashboard:

- KPIs agregados (campañas, audiencia, engagement, presión estratégica)
- Tarjetas de segmento con engagement, ADR y canal dominante
- Desglose por edad, perfil de viaje, valor de cliente y momento
- Recomendaciones de RRSS, hotel y publicidad (heurísticas o vía Anthropic)
- Campañas recientes y ciudades en foco

`backend/marketing/chat.py`

Asistente conversacional de marketing con:

- **Motor heurístico**: detecta intención (análisis, segmento, RRSS, hotel, publicidad, canal, destino, ideas, debilidades, fortalezas) y genera respuestas contextuales con datos reales del dashboard
- **Motor Gemini**: cuando hay credenciales de Vertex AI, delega al LLM con todo el contexto del dashboard inyectado como system prompt
- **Generador de campañas**: propone campañas diversas en 8 categorías (RRSS, hotel, local, branding, geolocalización, evento, decoración, pre-arrival)
- **Modificador de messaging**: reescribe el copy de campañas según instrucciones del usuario (tono, urgencia, canal)

---

### Sistema autónomo

El sistema autónomo es una capa independiente que opera sobre el backend existente para generar campañas de forma proactiva. Su arquitectura se basa en un **heartbeat** periódico.

#### Flujo de un tick

```
1. Oráculo → consulta/genera contexto externo para las ciudades
2. Scheduler → selecciona usuarios cuya ventana de contacto es ahora
3. Campañas → genera email personalizado por usuario (Gemini o mock)
4. Genéricas → propone campañas por segmento si toca
5. Estado → persiste en `data/runtime/autonomous_state.json`
```

#### Componentes

| Módulo | Función |
|--------|---------|
| `oracle.py` | Consulta y clasifica eventos/noticias por ciudad. Con Gemini genera inteligencia turística real; sin él, usa una base de datos mock de eventos plausibles por ciudad (Feria de Abril, Alhambra, Fiestas de Lisboa, etc.). Clasificación: `cultural_event`, `seasonal_offer`, `tourism_trend`, `travel_alert`, `extreme_weather` |
| `user_scheduler.py` | Calcula el mes de viaje habitual de cada usuario, resta su lead time medio, y determina si hoy cae dentro de la ventana de contacto (±7 días por defecto). Aplica cooldown para evitar contacto repetitivo |
| `campaign_generator.py` | Reutiliza `campaign_engine`, `channel_selector` y `email_renderer` del pipeline. Genera el copy con Gemini cuando está disponible, incluyendo eventos del Oráculo como gancho. Con afinidad perfil-evento (explorador cultural → eventos culturales, aventurero → tendencias turísticas, lujo → ofertas estacionales) |
| `heartbeat.py` | Bucle principal que coordina las 4 fases. Modo `tick` (una vez), `loop` (periódico) o `demo` (5 campañas + 1 genérica) |
| `live.py` | Orquestador **multi-agente concurrente** para el dashboard: N workers de recomendación + 1 worker de propuestas operando sobre una cola compartida. Emite eventos NDJSON en streaming para visualización en tiempo real |
| `gemini_client.py` | Wrapper sobre Gemini vía Vertex AI con `google-genai` SDK. Autenticación por cuenta de servicio. Si no hay credenciales, devuelve `None` y todos los módulos caen a mocks |
| `backend/storage/autonomous_state.py` | Persistencia en `data/runtime/autonomous_state.json`: último refresco del Oráculo, historial de contactos, contadores de ticks y campañas |

---

### Demos

#### Marketing Dashboard (`localhost:3003`)

Dashboard analítico completo tipo SPA con soporte dark/light mode. Incluye:

- **Panel de KPIs**: campañas activas, tamaño de audiencia, segmentos, engagement medio, presión estratégica
- **Contexto editable**: prioridad estratégica, notas del jefe de marketing, señales de recepción y señales externas
- **Rendimiento por segmento**: heatmaps, gráficos por edad/perfil/valor/momento
- **Generador de campañas**: propuestas de campaña en 8 categorías con engaging estimado, timing, rationale y deliverables
- **Modificador de messaging**: reescribe campañas según instrucciones (tono formal, urgencia, descuento, premium, etc.)
- **Chat IA**: agente conversacional que conoce todos los datos del dashboard
- **Modo autónomo live**: visualización en streaming de los agentes generando campañas en tiempo real con workers concurrentes

**API endpoints**:

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/dashboard` | Payload completo del dashboard |
| `GET` | `/api/context` | Contexto editable actual |
| `POST` | `/api/context` | Guardar contexto y re-generar dashboard |
| `POST` | `/api/chat` | Enviar mensaje al asistente IA |
| `GET` | `/api/campaigns` | Generar propuestas de campaña |
| `POST` | `/api/campaigns/modify` | Modificar messaging de una campaña |
| `GET` | `/api/autonomous/stream` | Streaming NDJSON del modo autónomo |
| `GET` | `/api/autonomous/email/{id}` | Preview de email generado por agente |

#### Gmail Demo (`localhost:3001`)

Interfaz estilo Gmail con 200 perfiles de clientes. Cada perfil tiene una bandeja con emails personalizados (pre-arrival, check-in, post-stay) generados por el pipeline. Permite navegar entre perfiles para ver cómo la personalización varía según segmento, hotel y contexto.

Los perfiles se leen directamente de `data/raw/customer_data.csv` y el inbox se
construye desde los HTML generados en `output/`.

#### Recepción Demo (`localhost:3002`)

Interfaz para consultar los informes de check-in generados por el pipeline (`output/checkin_report_*.html`). Muestra información interna para recepción: preferencias del huésped, oportunidades de upsell, historial y recomendaciones.

---

## Flujo de datos

```
data/raw/customer_data.csv ──┐
                             ├── embeddings ──► data/generated/embeddings.json
data/raw/hotel_data.csv ─────┘
                                │
data/raw/customer_data.csv ────├── segmentation ──► data/generated/segments.json
                                │
images/<hotel_id>/*.jpg ────────├── auto_tag ──► metadata.json
                                │
data/generated/embeddings.json + data/generated/segments.json ├── campaigns ──► campaign data
                                │
metadata.json + embeddings ─────├── image_selector ──► selected images
                                │
campaign data ──────────────────├── copy ──► copy (Gemini/mock)
                                │
copy + images + template ───────├── renderer ──► HTML
                                │
segment + leadtime ─────────────├── channels ──► email/sms/push
                                │
HTML + copy + channel ──────────├── delivery ──► output/*.html / SendGrid
                                │
data/generated/campaign_log.json + data/generated/segments.json ───├── dashboard ──► dashboard payload
                                │
oracle context + candidates ────└── backend/autonomous/live.py ──► NDJSON stream
```

---

## Ejecución rápida (demo completa)

Para ver todo el proyecto funcionando desde cero:

```bash
# 1. Instalar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 2. Ejecutar pipeline completo (genera todos los datos)
python3 main.py --phase all

# 3. Arrancar los 3 frontends
./start_services.sh

# 4. Abrir en el navegador:
#    - http://localhost:3003  → Marketing Dashboard (principal)
#    - http://localhost:3001  → Gmail demo con 200 perfiles
#    - http://localhost:3002  → Demo de recepción
```

> **Nota**: No se necesita ninguna API key para la demo básica. Todo funciona con datos y texto mock. Para IA real, configura `GOOGLE_APPLICATION_CREDENTIALS` y `VERTEX_PROJECT_ID` en `.env`; si guardas una cuenta de servicio local, usa una ruta privada como `.secrets/vertex-service-account.json`.

---

## Notas importantes

- `output/` está en `.gitignore` — contiene artefactos generados por el pipeline.
- `.env` también está en `.gitignore` — nunca debe subirse al repositorio.
- `output/autonomous/` contiene las salidas del sistema autónomo (emails HTML y campañas genéricas).
- El proyecto está diseñado para funcionar completamente en local sin APIs externas.
- El procesamiento de campañas es paralelo (configurable con `CAMPAIGN_MAX_WORKERS`).
- El modo autónomo live usa múltiples hilos para demostrar concurrencia real entre agentes.
- Las plantillas de email son responsive y diferenciadas por segmento de edad.
