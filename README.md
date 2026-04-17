# Eurostars AI Marketing Command Center

Demo end-to-end de personalizacion para hoteleria. El repositorio combina:

- un pipeline batch que genera emails y reportes HTML a partir de datos de clientes, hoteles e imagenes;
- un dashboard de marketing con chat, propuestas de campana y contexto editable;
- un subsistema autonomo que genera recomendaciones y campanas usando el mismo backend.

La documentacion de este `README` esta ajustada al comportamiento actual del codigo del repositorio.

## Estado actual del proyecto

Validado sobre el contenido incluido en el repo:

- `data/raw/customer_data.csv`: 260 reservas, 200 huespedes unicos.
- `data/raw/hotel_data.csv`: 10 hoteles.
- `images/`: 500 imagenes repartidas en 10 carpetas de hotel.
- `python3 main.py --phase all`: genera 600 HTML en `output/`:
  - 200 `pre_arrival_*`
  - 200 `checkin_report_*`
  - 200 `post_stay_*`
- `python3 -m backend.autonomous.cli --mode demo --force-mock`: genera 5 emails en `output/autonomous/emails/` y 1 JSON de campanas genericas en `output/autonomous/generic_campaigns/`.

## Que incluye

| Componente | Que hace | Entrada principal |
| --- | --- | --- |
| Pipeline batch | Embeddings, segmentacion, autoetiquetado de imagenes, generacion de campanas, render HTML y snapshot del dashboard | `python3 main.py --phase all` |
| Dashboard de marketing | Panel analitico, chat IA, propuestas de campana, contexto editable y stream autonomo live | `python3 demos/marketing/server.py` |
| Sistema autonomo | Tick, loop y demo para generar campanas proactivas y propuestas genericas | `python3 -m backend.autonomous.cli --mode demo` |
| Demos web | Gmail demo, recepcion y dashboard de marketing | `./start_services.sh` |

## Arquitectura real

```text
data/raw/*.csv,json
   |
   +--> backend/personalization/embeddings.py
   +--> backend/personalization/segmentation.py
   +--> backend/assets/image_metadata.py
   +--> backend/campaigns/planner.py
   +--> backend/campaigns/copy.py
   +--> backend/campaigns/renderer.py
   +--> backend/campaigns/channels.py
   +--> backend/campaigns/delivery.py
   |
   +--> data/generated/{embeddings,segments,campaign_log,marketing_dashboard_snapshot}.json
   +--> output/*.html
   |
   +--> demos/mail + demos/receptionist + demos/marketing
   |
   +--> backend/autonomous/{oracle,scheduler,generator,heartbeat,live}.py
         |
         +--> data/runtime/{oracle_context,autonomous_state,marketing_context}.json
         +--> output/autonomous/{emails,generic_campaigns}/
```

## Requisitos

- Python 3.11+
- `pip`

No hace falta Node, npm ni un build frontend: las tres demos son servidores Python basados en `http.server`.

## Instalacion

```bash
git clone <url-del-repo>
cd eurostarsAD

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

## Variables de entorno

El proyecto carga `.env` desde la raiz.

### Gemini / Vertex AI

| Variable | Uso |
| --- | --- |
| `GOOGLE_APPLICATION_CREDENTIALS` | Ruta al JSON de la service account. Puede ser relativa a la raiz del repo. |
| `VERTEX_PROJECT_ID` | Proyecto de Google Cloud. Sin esto Gemini queda desactivado. |
| `VERTEX_LOCATION` | Region de Vertex AI. Default: `us-central1`. |
| `GEMINI_MODEL` | Modelo compartido por chat, batch y sistema autonomo. |
| `GEMINI_TEMPERATURE` | Temperatura compartida. |
| `GEMINI_COPY_IN_DRY_RUN` | Si vale `true`, el batch puede usar Gemini aunque la entrega siga en dry-run. |

### Batch pipeline

| Variable | Uso |
| --- | --- |
| `CAMPAIGN_MAX_WORKERS` | Numero maximo de hilos para procesar campanas en paralelo. |
| `SENDGRID_API_KEY` | Solo necesaria para `--send`. |
| `SENDER_EMAIL` | Remitente para SendGrid. |

### Sistema autonomo

| Variable | Uso |
| --- | --- |
| `AUTONOMOUS_DRY_RUN` | Declarada en configuracion, pero hoy no activa un envio real ni cambia materialmente el flujo del CLI. |
| `AUTONOMOUS_ORACLE_INTERVAL_HOURS` | Frecuencia de refresco del Oraculo. |
| `AUTONOMOUS_HEARTBEAT_INTERVAL_MINUTES` | Intervalo entre ticks del loop. |
| `AUTONOMOUS_GENERIC_CAMPAIGN_INTERVAL_HOURS` | Frecuencia de propuestas genericas. |
| `AUTONOMOUS_USER_COOLDOWN_DAYS` | Cooldown entre contactos al mismo usuario. |
| `AUTONOMOUS_SEND_WINDOW_DAYS` | Ventana de activacion alrededor de la fecha ideal. |
| `AUTONOMOUS_MAX_USERS_PER_TICK` | Maximo de usuarios por tick. |
| `AUTONOMOUS_MIN_SEGMENT_SIZE_FOR_GENERIC` | Tamano minimo de segmento para propuestas genericas. |

### Servidor del dashboard

| Variable | Uso |
| --- | --- |
| `MARKETING_HOST` | Host de bind del dashboard. Default: vacio. |
| `MARKETING_PORT` | Puerto del dashboard. Default: `3003`. |

### Correccion importante sobre la prediccion temporal

En `.env.example` aparecen:

- `TRAVEL_PREDICTION_MODE`
- `TRAVEL_REGRESSION_SEND_OFFSET_DAYS`
- `TRAVEL_REGRESSION_MIN_HISTORY`

Pero la implementacion actual de [`backend/personalization/travel_prediction.py`](/home/adrianql/Hackatones/eurostarsAD/backend/personalization/travel_prediction.py:1) solo usa un modo heuristico. La opcion de regresion no esta cableada al comportamiento real del pipeline ni al CLI actual.

## Comportamiento con y sin Gemini

- Sin credenciales validas de Vertex AI, el batch usa copy mock, el chat cae a un motor heuristico y el sistema autonomo usa contenido mock.
- Con credenciales validas:
  - el chat, las propuestas y el modificador de messaging del dashboard pueden usar Gemini;
  - el sistema autonomo puede usar Gemini para copy y propuestas;
  - el batch solo usa Gemini por defecto cuando ejecutas `--send`, o si activas `GEMINI_COPY_IN_DRY_RUN=true`.

## Ejecucion rapida

```bash
python3 main.py --phase all
./start_services.sh
```

Abrir:

- `http://localhost:3001` -> Gmail demo
- `http://localhost:3002` -> Recepcion
- `http://localhost:3003` -> Marketing dashboard

## Pipeline batch

Punto de entrada: [`main.py`](/home/adrianql/Hackatones/eurostarsAD/main.py:1)

### Que genera

| Fase | Modulo principal | Salida |
| --- | --- | --- |
| `embeddings` | `backend/personalization/embeddings.py` | `data/generated/embeddings.json` |
| `segment` | `backend/personalization/segmentation.py` | `data/generated/segments.json` |
| `auto_tag` | `backend/assets/image_metadata.py` | `images/*/metadata.json` |
| `campaign` | `backend/campaigns/*` | `output/*.html` y `data/generated/campaign_log.json` |
| `marketing` | `backend/marketing/dashboard.py` | `data/generated/marketing_dashboard_snapshot.json` |

### Comandos

```bash
# Pipeline completo
python3 main.py --phase all

# Fases sueltas
python3 main.py --phase embeddings
python3 main.py --phase segment
python3 main.py --phase auto_tag
python3 main.py --phase marketing

# Campanas por momento
python3 main.py --phase campaign --moment pre_arrival
python3 main.py --phase campaign --moment checkin_report
python3 main.py --phase campaign --moment post_stay

# Campana para un huesped concreto
python3 main.py --phase campaign --moment pre_arrival --guest_id 1014907189

# Envio real por SendGrid
python3 main.py --phase campaign --moment pre_arrival --send
```

### Notas importantes del batch

- El batch trabaja en dry-run por defecto. El flag `--dry-run` existe, pero el comportamiento ya es dry-run salvo que uses `--send`.
- `run_all()` limpia antes los HTML batch existentes y reinicia `data/generated/campaign_log.json`.
- El envio real del batch usa destinatarios placeholder `guest_<id>@example.com`. Es una demo, no una integracion productiva con los emails del CSV.
- Los SMS y push no generan archivos dedicados en `output/`; quedan reflejados en `campaign_log.json`.
- `checkin_report` siempre se renderiza como informe interno HTML.
- `--phase marketing` escribe `data/generated/marketing_dashboard_snapshot.json`, pero el dashboard web recalcula su payload directamente desde log, segmentos, clientes y contexto runtime.

### Como funciona hoy la prediccion de viaje

La prediccion de `pre_arrival` usa el modulo [`backend/personalization/travel_prediction.py`](/home/adrianql/Hackatones/eurostarsAD/backend/personalization/travel_prediction.py:1):

- mes habitual de viaje del cliente;
- `AVG_BOOKING_LEADTIME`;
- `AVG_LENGTH_STAY`.

No hay regresion temporal activa en la implementacion actual.

## Sistema autonomo

Punto de entrada: [`backend/autonomous/cli.py`](/home/adrianql/Hackatones/eurostarsAD/backend/autonomous/cli.py:1)

### Modos disponibles

```bash
python3 -m backend.autonomous.cli --mode tick
python3 -m backend.autonomous.cli --mode loop
python3 -m backend.autonomous.cli --mode demo
python3 -m backend.autonomous.cli --mode demo --force-mock
python3 -m backend.autonomous.cli --mode demo -v
```

### Que hace cada modo

- `tick`: ejecuta un ciclo completo del heartbeat.
- `loop`: repite ticks cada `AUTONOMOUS_HEARTBEAT_INTERVAL_MINUTES`.
- `demo`: reinicia `output/autonomous/`, genera contexto del Oraculo, crea 5 emails personalizados y 1 propuesta generica.

### Salidas

- `output/autonomous/emails/`: emails `pre_arrival_*.html`
- `output/autonomous/generic_campaigns/`: informes JSON de campanas genericas
- `data/runtime/oracle_context.json`
- `data/runtime/autonomous_state.json`

### Correcciones importantes sobre el sistema autonomo

- El heartbeat de [`backend/autonomous/heartbeat.py`](/home/adrianql/Hackatones/eurostarsAD/backend/autonomous/heartbeat.py:1) es secuencial.
- La concurrencia "multi-agente" existe en el modo live del dashboard, implementado en [`backend/autonomous/live.py`](/home/adrianql/Hackatones/eurostarsAD/backend/autonomous/live.py:1), que levanta varios workers y emite NDJSON.
- `--no-dry-run` en el CLI autonomo no activa un envio real de emails: el propio CLI avisa de que ese envio no esta implementado.
- `AUTONOMOUS_DRY_RUN` existe en la configuracion, pero el comportamiento efectivo del CLI depende de `--dry-run` / `--no-dry-run`, y aun asi el envio real no esta implementado.

### Que es realmente el Oraculo

El Oraculo de [`backend/autonomous/oracle.py`](/home/adrianql/Hackatones/eurostarsAD/backend/autonomous/oracle.py:1):

- no consume feeds reales ni hace scraping web;
- genera contexto con un pool mock local o con Gemini;
- clasifica entradas como `cultural_event`, `seasonal_offer`, `tourism_trend`, `travel_alert` o `extreme_weather`.

Debe entenderse como una capa de contexto generativo para demo, no como una fuente factual en tiempo real.

## Demos web

### Arranque conjunto

```bash
./start_services.sh
```

El script usa `.venv/bin/python` si existe; en caso contrario usa `python3`.

### Arranque individual

```bash
python3 demos/mail/server.py
python3 demos/receptionist/server.py
python3 demos/marketing/server.py
```

### Gmail demo

Ruta: `http://localhost:3001`

Lee:

- identidades desde `data/raw/customer_data.csv`
- emails desde `output/*.html`

Correccion importante: la bandeja solo indexa emails `pre_arrival_*` y `post_stay_*`. Los `checkin_report_*` no aparecen aqui; van a la demo de recepcion.

### Recepcion

Ruta: `http://localhost:3002`

Lee e indexa:

- `output/checkin_report_*.html`

Permite buscar huespedes y abrir el informe interno de check-in renderizado por el pipeline.

### Marketing dashboard

Ruta: `http://localhost:3003`

Usa:

- `data/generated/campaign_log.json`
- `data/generated/segments.json`
- `data/raw/customer_data.csv`
- `data/runtime/marketing_context.json`

Incluye:

- KPIs y rankings de segmentos;
- contexto editable de negocio;
- chat IA con fallback heuristico;
- propuestas de campana;
- modificador de messaging;
- stream autonomo live con NDJSON.

### API del dashboard

| Metodo | Ruta | Descripcion |
| --- | --- | --- |
| `GET` | `/api/dashboard` | Payload completo del dashboard |
| `GET` | `/api/context` | Contexto editable actual |
| `POST` | `/api/context` | Guarda contexto y devuelve dashboard recalculado |
| `POST` | `/api/chat` | Mensaje al asistente |
| `GET` | `/api/campaigns` | Propuestas de campana |
| `POST` | `/api/campaigns/modify` | Reescritura de messaging |
| `GET` | `/api/autonomous/stream` | Stream NDJSON del modo autonomo live |
| `GET` | `/api/autonomous/email/{guest_id}` | Preview de email autonomo generado |

## Datos y artefactos

### Datos de entrada

| Ruta | Contenido |
| --- | --- |
| `data/raw/customer_data.csv` | Reservas historicas de clientes |
| `data/raw/hotel_data.csv` | Catalogo de hoteles |
| `data/raw/city_events.json` | Catalogo local de eventos por ciudad |
| `data/raw/upsell_catalog.json` | Catalogo de upsells |
| `images/<hotel_id>/` | Imagenes por hotel |

### Salidas generadas

| Ruta | Contenido |
| --- | --- |
| `data/generated/embeddings.json` | Embeddings de hoteles y usuarios |
| `data/generated/segments.json` | Segmentacion enriquecida |
| `data/generated/campaign_log.json` | Registro de campanas y canales |
| `data/generated/marketing_dashboard_snapshot.json` | Snapshot del dashboard |
| `data/runtime/marketing_context.json` | Contexto editable del dashboard |
| `data/runtime/oracle_context.json` | Ultimo contexto del Oraculo |
| `data/runtime/autonomous_state.json` | Estado persistido del sistema autonomo |
| `output/` | Emails batch y reportes de check-in |
| `output/autonomous/` | Emails y propuestas del sistema autonomo |

## Estructura del repo

```text
backend/
  ai/
  assets/
  autonomous/
  campaigns/
  marketing/
  personalization/
  storage/
data/
  raw/
  generated/
  runtime/
demos/
  mail/
  marketing/
  receptionist/
images/
main.py
start_services.sh
```

## Notas finales

- `output/`, `.env` y `.secrets/` estan ignorados por Git.
- El proyecto se puede ejecutar completamente en local sin claves externas.
- Si quieres ver las demos con datos coherentes, ejecuta antes `python3 main.py --phase all`.
