# Impacthon

Motor de personalización para campañas hoteleras de Eurostars. El proyecto toma datos históricos de clientes y hoteles, construye perfiles, segmenta usuarios, genera campañas para distintos momentos del viaje y produce salidas HTML para email y para recepción.

## Qué hace

El flujo completo se ejecuta desde `main.py` y recorre estas fases:

1. `pipeline/embeddings`: construye embeddings de hoteles y usuarios a partir de `data/hotel_data.csv` y `data/customer_data_200.csv`.
2. `pipeline/segmentation`: clasifica a cada usuario por edad, perfil de viaje, valor de cliente y patrón de viaje.
3. `pipeline/campaigns`: prepara la campaña para cada momento del ciclo de vida.
4. `pipeline/assets/auto_tag_images.py`: genera metadatos de imágenes desde los nombres de fichero.
5. `pipeline/assets/image_selector.py`: selecciona imágenes relevantes para cada campaña.
6. `pipeline/content/text_generator.py`: genera el copy del email.
7. `pipeline/rendering/email_renderer.py`: renderiza HTML con Jinja2.
8. `pipeline/channels/channel_selector.py`: decide canal principal.
9. `pipeline/delivery/send_campaign.py`: guarda el HTML en disco o envía por SendGrid.

Los momentos soportados son:

- `pre_arrival`: email personalizado antes de la estancia.
- `checkin_report`: informe interno para recepción.
- `post_stay`: email posterior a la estancia.

## Estructura

```text
.
├── main.py
├── data/
├── images/
├── output/
├── pipeline/
│   ├── orchestration/
│   ├── embeddings/
│   ├── segmentation/
│   ├── campaigns/
│   ├── assets/
│   ├── content/
│   ├── rendering/
│   ├── channels/
│   ├── delivery/
│   └── common/
└── frontend/
    ├── mail/
    └── receptionist/
```

## Datos de entrada y salida

Entradas principales:

- `data/hotel_data.csv`: catálogo de hoteles y atributos del destino.
- `data/customer_data_200.csv`: histórico de reservas de 200 clientes.
- `images/<hotel_id>/`: imágenes por hotel.

Salidas principales:

- `data/embeddings.json`
- `data/segments.json`
- `data/campaign_log.json`
- `output/*.html`: emails e informes generados en modo `dry-run`

## Variables de entorno

El proyecto carga variables desde `.env`. `.env.example` es solo una plantilla.

Variables relevantes:

- `OPENAI_API_KEY`: usada para generar texto real con OpenAI.
- `OPENAI_EMAIL_MODEL`: opcional; por defecto usa `gpt-5.4-nano`.
- `OPENAI_EMAIL_MAX_OUTPUT_TOKENS`: opcional; limita la longitud de salida del copy.
- `SENDGRID_API_KEY`: usada para enviar emails reales.
- `SENDER_EMAIL`: remitente para SendGrid.
- `EVENTBRITE_API_KEY`: aparece como opcional, pero ahora mismo no se usa en el código.

Comportamiento importante:

- Por defecto el proyecto trabaja en `dry-run`.
- En `dry-run`, el texto no llama a OpenAI: usa copy mock.
- Si ejecutas con `--send`, intentará enviar por SendGrid.
- Si falta `OPENAI_API_KEY`, incluso fuera de `dry-run`, el generador cae a texto mock.
- Las campañas se procesan en paralelo con varios hilos; puedes ajustar el límite con `CAMPAIGN_MAX_WORKERS`.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Cómo ejecutar

Pipeline completo:

```bash
python3 main.py --phase all
```

Solo embeddings:

```bash
python3 main.py --phase embeddings
```

Solo segmentación:

```bash
python3 main.py --phase segment
```

Solo autoetiquetado de imágenes:

```bash
python3 main.py --phase auto_tag
```

Una campaña concreta:

```bash
python3 main.py --phase campaign --moment pre_arrival
python3 main.py --phase campaign --moment checkin_report --guest_id 1014907189
python3 main.py --phase campaign --moment post_stay
```

Envío real por email:

```bash
python3 main.py --phase campaign --moment pre_arrival --send
```

## Cómo funciona cada fase

### 1. Embeddings

`pipeline/embeddings/build_embeddings.py` transforma atributos de hotel en un vector de 11 dimensiones y calcula el embedding de cada usuario como media ponderada de los hoteles visitados.

### 2. Segmentación

`pipeline/segmentation/segment_users.py` genera cuatro ejes por usuario:

- `age_segment`: `JOVEN`, `ADULTO`, `SENIOR`
- `travel_profile`: por ejemplo `EXPLORADOR_CULTURAL`, `LUJO`, `SOL_Y_PLAYA`
- `client_value`: `STANDARD`, `MID_VALUE`, `HIGH_VALUE`
- `travel_pattern`: `RECURRENTE_DESTINO`, `EXPLORADOR`, `FIEL_CADENA`

### 3. Campañas

`pipeline/campaigns/campaign_engine.py` crea la estructura de datos de cada campaña:

- predice una ventana probable de viaje
- recomienda hotel
- recupera eventos del destino
- resume preferencias del usuario
- genera upsells para el informe de recepción

Ahora mismo los eventos son mock, definidos en el propio código.

### 4. Imágenes

`pipeline/assets/auto_tag_images.py` crea `metadata.json` dentro de cada carpeta de hotel en `images/`.

`pipeline/assets/image_selector.py` puntúa imágenes según el embedding del usuario y su segmento, y devuelve entre 3 y 5 imágenes por campaña.

### 5. Texto

`pipeline/content/text_generator.py` genera el copy del email. Tiene dos modos:

- mock, usado por defecto en `dry-run`
- real, usando OpenAI si hay `OPENAI_API_KEY`

También genera SMS cortos cuando el canal principal es `sms`.

### 6. Render

`pipeline/rendering/email_renderer.py` renderiza HTML usando estas plantillas:

- `pipeline/rendering/templates/template_joven.html`
- `pipeline/rendering/templates/template_adulto.html`
- `pipeline/rendering/templates/template_senior.html`
- `pipeline/rendering/templates/receptionist_report.html`

### 7. Canal

`pipeline/channels/channel_selector.py` decide entre `email`, `sms` o `push` con reglas simples basadas en segmento y lead time.

### 8. Entrega

`pipeline/delivery/send_campaign.py`:

- guarda HTML en `output/` si `dry_run=True`
- registra cada acción en `data/campaign_log.json`
- usa SendGrid si ejecutas con `--send`

## Frontends de demo

### Mail demo

Simula una bandeja estilo Gmail para visualizar los emails generados.

```bash
python3 frontend/mail/server.py
```

Abre `http://localhost:3001`.

Si regeneras campañas y quieres reconstruir perfiles del demo:

```bash
python3 frontend/mail/build_profiles.py
```

### Reception demo

Sirve una interfaz para consultar informes de check-in generados en `output/`.

```bash
python3 frontend/receptionist/server.py
```

Abre `http://localhost:3002`.

## Estado actual

El proyecto se ha probado con:

```bash
python3 main.py --phase all
```

La ejecución completa genera campañas para los tres momentos y deja los HTML en `output/` en modo `dry-run`.

## Notas

- `output/` está ignorado por git porque contiene artefactos generados.
- `.env` también está ignorado por git; no debe subirse al repositorio.
- El repositorio está preparado para trabajar localmente sin depender de envío real ni de llamadas obligatorias a APIs externas.
