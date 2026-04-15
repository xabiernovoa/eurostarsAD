# Explicación del backend de este proyecto

## 1. Qué es este backend, dicho de forma sencilla

El backend de este proyecto es **el motor que piensa, organiza y produce** todo lo que luego ves en las demos.

Si el frontend es la parte visual, el backend es la parte que:

- lee los datos de clientes y hoteles,
- decide qué tipo de cliente es cada persona,
- recomienda qué hotel podría interesarle,
- predice cuándo conviene contactar con ella,
- genera el contenido del mensaje,
- selecciona imágenes,
- renderiza emails o informes,
- guarda resultados y métricas,
- y alimenta el dashboard de marketing.

Sin backend, las pantallas del proyecto serían casi decorativas. Tendrían interfaz, pero no inteligencia de negocio detrás.

## 2. Qué problema intenta resolver

El proyecto intenta resolver este problema:

> "Tengo muchos clientes y varios hoteles. ¿Cómo puedo personalizar la comunicación, la experiencia y las acciones de marketing en lugar de enviar lo mismo a todo el mundo?"

La respuesta del proyecto es:

1. analizar el historial de cada huésped,
2. convertir ese historial en un perfil interpretable,
3. usar ese perfil para recomendar destinos, tono, canal e imágenes,
4. generar campañas para distintos momentos del viaje,
5. y dar al equipo de marketing una vista operativa y un asistente para tomar decisiones.

En otras palabras:

- no es solo "un generador de emails",
- es un **sistema de personalización y marketing hotelero**.

## 3. Idea clave: este backend no es una web tradicional con base de datos

Esto es importante para entender bien el proyecto.

Este backend **no está montado como un gran servidor tipo Django/FastAPI con una base de datos SQL detrás**.
Su arquitectura real es más simple y más de demo/prototipo:

- usa **CSV** como datos de entrada,
- usa **JSON** como artefactos intermedios y estado,
- usa scripts Python para procesar fases,
- y expone algunas **APIs HTTP sencillas** desde `demos/*/server.py`.

Eso significa que aquí el backend tiene **tres formas de trabajar**:

1. **Modo batch**  
   Procesa los datos por fases y genera salidas en disco.

2. **Modo servidor demo**  
   Levanta pequeños servidores HTTP para que las interfaces web consulten datos.

3. **Modo autónomo**  
   Simula un sistema que trabaja de forma proactiva, eligiendo usuarios y generando campañas.

## 4. Mapa mental general del sistema

```text
CSV de clientes + CSV de hoteles + imágenes
                |
                v
      [backend/storage]
Carga y normalización de datos
                |
                v
 [backend/personalization/embeddings.py]
Convierte hoteles y usuarios en vectores numéricos
y calcula recomendaciones por similitud + reranqueo
                |
                v
 [backend/personalization/segmentation.py]
Genera perfiles segmentados por huésped con etiquetas
de afinidad, valor, comportamiento, fidelidad y métricas
                |
                v
   [backend/campaigns/planner.py]
Decide qué campaña construir, cuándo hacerlo
y qué hotel recomendar con esas señales
                |
                +------------------------------+
                |                              |
                v                              v
 [backend/assets/*]                    [backend/campaigns/copy.py]
elige imágenes                         genera texto con Gemini o mock
                |                              |
                +--------------+---------------+
                               v
              [backend/campaigns/renderer.py]
              renderiza HTML con plantillas
                               |
                               v
             [backend/campaigns/delivery.py]
             guarda en output/ o enviaría por email
                               |
                               v
       [backend/marketing/*] y [backend/autonomous/*]
       dashboard, chat, recomendaciones, sistema autónomo
```

## 5. Qué datos maneja realmente

Según los archivos del proyecto:

- `data/raw/customer_data.csv`: 260 filas de reservas
- `data/raw/customer_data.csv`: 200 huéspedes únicos
- `data/raw/hotel_data.csv`: 10 hoteles en catálogo
- `images/<hotel_id>/`: fotos reales por hotel

### 5.1. Qué contiene el CSV de clientes

Ejemplo real:

```csv
"1014907189";"PT";"Femenino";"36-45";"2";"2";"2";"109.24";"3.50";"6.00";"8.0";"1";"2024-12-01";"2024-12-06";"041";"Cláudia Costa";"claudia.costa@gmail.com";"Portuguesa"
```

Eso representa una reserva de una persona concreta. Hay columnas como:

- `GUEST_ID`: identificador del huésped
- `COUNTRY_GUEST`: país del cliente
- `GENDER_ID`: género
- `AGE_RANGE`: tramo de edad
- `CONFIRMED_RESERVATIONS_ADR`: gasto medio diario aproximado
- `AVG_LENGTH_STAY`: duración media de estancia
- `AVG_BOOKING_LEADTIME`: cuántos días antes suele reservar
- `AVG_SCORE`: valoración media que da
- `CHECKIN_DATE` y `CHECKOUT_DATE`
- `HOTEL_ID`

### 5.2. Qué contiene el CSV de hoteles

Ejemplo real:

```csv
"243";Eurostars Torre Sevilla;ES;EUROSTARS;"5";244;SEVILLA;MEDITERRANEAN;19.0;LOW;NO;NO;HIGH;HIGH;HIGH
```

Aquí hay información del hotel y del destino:

- nombre,
- país,
- marca,
- estrellas,
- ciudad,
- clima,
- temperatura media,
- riesgo de lluvia,
- si la ciudad tiene playa,
- si tiene montaña,
- si tiene patrimonio histórico,
- nivel de precio,
- valor gastronómico.

## 6. La primera capa: `backend/storage`

Los módulos de `backend/storage` son la capa más básica. Su trabajo no es "hacer IA", sino **leer y escribir datos**.

Archivos importantes:

- `backend/storage/customers.py`
- `backend/storage/hotels.py`
- `backend/storage/embeddings.py`
- `backend/storage/segments.py`
- `backend/storage/campaign_log.py`
- `backend/storage/marketing_context.py`
- `backend/storage/autonomous_state.py`

### 6.1. Qué hacen

- cargan CSV y JSON,
- convierten fechas a formato de fecha real,
- limpian IDs como texto,
- guardan resultados intermedios,
- mantienen el estado del sistema autónomo.

### 6.2. Idea teórica detrás

Antes de hacer IA o personalización, un sistema necesita una capa de **persistencia**.
Persistencia significa: "guardar información de forma que no se pierda cuando termina el programa".

En este proyecto la persistencia no es una base de datos SQL, sino:

- CSV para materia prima,
- JSON para resultados y estado.

Eso simplifica el proyecto y lo hace más fácil de ejecutar localmente.

## 7. La orquestación general: `main.py` y `backend/batch.py`

`main.py` no tiene lógica de negocio real. Solo delega en `backend.batch.main`.

El archivo importante es `backend/batch.py`.

Ese archivo coordina el pipeline por fases:

1. embeddings
2. segmentación
3. autoetiquetado de imágenes
4. campañas
5. snapshot de marketing

### 7.1. Qué significa "pipeline"

Un **pipeline** es una secuencia ordenada de pasos donde la salida de uno alimenta al siguiente.

Ejemplo simple:

```text
datos crudos -> limpieza -> análisis -> decisión -> generación -> salida final
```

En este proyecto el pipeline completo es:

```text
CSV -> embeddings -> segmentos -> campañas -> HTML -> log -> dashboard
```

## 8. Embeddings: qué son aquí y para qué sirven

Archivo principal:

- `backend/personalization/embeddings.py`

### 8.1. Qué significa "embedding" en este proyecto

La palabra "embedding" a veces suena muy avanzada, pero aquí la idea es simple:

> un embedding es una forma de representar algo mediante números para poder compararlo matemáticamente.

En muchos sistemas modernos, un embedding lo genera una red neuronal enorme.  
Aquí no.

Aquí el embedding es **manual y explicable**.

Cada hotel se convierte en un vector de 11 números:

- estrellas normalizadas,
- temperatura,
- lluvia,
- playa,
- montaña,
- patrimonio,
- precio,
- gastronomía,
- clima atlántico,
- clima continental,
- clima mediterráneo.

### 8.2. Ejemplo real de vector de hotel

En `data/generated/embeddings.json`, el hotel `243` tiene algo parecido a:

```json
{
  "STARS_NORM": 1.0,
  "TEMP_NORM": 1.0,
  "RAIN_RISK_NUM": 0.0,
  "BEACH": 0.0,
  "MOUNTAIN": 0.0,
  "HERITAGE": 1.0,
  "PRICE_LEVEL": 1.0,
  "GASTRONOMY": 1.0,
  "CLIMATE_ATLANTIC": 0.0,
  "CLIMATE_CONTINENTAL": 0.0,
  "CLIMATE_MEDITERRANEAN": 1.0
}
```

Eso significa, en lenguaje humano:

- hotel de alta categoría,
- destino cálido,
- poco riesgo de lluvia,
- no playa,
- no montaña,
- mucho patrimonio,
- nivel alto de precio,
- fuerte componente gastronómico,
- clima mediterráneo.

### 8.3. Cómo se genera el embedding del usuario

El usuario no se describe directamente.
Se describe **a partir de los hoteles en los que ya estuvo**.

La lógica es:

1. miro qué hoteles visitó,
2. convierto esos hoteles a vectores,
3. hago una media ponderada,
4. ese promedio se convierte en "su gusto implícito".

Idea intuitiva:

- si alguien visitó hoteles de ciudad histórica y gastronomía alta,
- su vector tenderá a histórico + gastronómico + premium.

### 8.4. Fundamento teórico

Esto pertenece a la idea de **representación vectorial**.

Traducido:

- en vez de decir "a este cliente le gusta el lujo" como texto,
- el sistema lo traduce a números,
- y así puede medir parecidos.

### 8.5. Importante: este embedding no es mágico

No está "aprendiendo solo" a un nivel profundo.
Es un sistema **ingenierizado a mano**:

- alguien eligió las 11 dimensiones,
- alguien decidió cómo mapear `HIGH`, `MEDIUM`, `LOW`,
- alguien decidió cómo promediar.

Esto es útil porque:

- es explicable,
- es fácil de depurar,
- y encaja bien en una demo.

## 9. Recomendación de hoteles: similitud del coseno + reranqueo por etiquetas

También en `backend/personalization/embeddings.py` aparece `recommend_hotel`.

### 9.1. Qué hace

Hace tres pasos:

1. compara el vector del usuario con el vector de cada hotel,
2. descarta hoteles que ya ha visitado,
3. si recibe el `segment` del usuario, reranquea el resultado con etiquetas de negocio.

### 9.2. Qué es la similitud del coseno

No hace falta saber álgebra avanzada para entender la idea.

La similitud del coseno responde a esta pregunta:

> "¿Apuntan estos dos perfiles en una dirección parecida?"

Si dos vectores son parecidos:

- su similitud se acerca a 1.

Si son poco parecidos:

- la similitud baja.

### 9.3. La segunda capa: reranqueo interpretable

La recomendación final ya no es puro coseno.

El backend mezcla:

- una base matemática de similitud entre embeddings,
- y una capa de reglas simples basada en etiquetas.

En la implementación actual, cuando hay segmento disponible, el score final combina aproximadamente:

- `72%` similitud del embedding,
- `28%` score por etiquetas.

Ese score adicional mira:

- `afinidades_destino`,
- `nivel_valor`,
- `fidelidad`,
- `comportamiento_reserva`.

La idea es importante:

> el embedding sigue diciendo "qué hotel se parece al historial del cliente",  
> pero las etiquetas ayudan a decidir "qué hotel tiene más sentido comercial y narrativo para recomendar".

### 9.4. Ejemplo real

Para el huésped `1014907189`, el sistema genera:

- afinidades principales: `cultural`, `gastronomico`, `mediterraneo`
- nivel de valor: `esencial`
- fidelidad principal: `multidestino`
- hotel recomendado: `Aurea Catedral` en Granada
- `recommendation_score`: `0.8489`

Eso significa:

- el sistema considera que ese hotel encaja bien con su embedding,
- y además queda bien posicionado tras aplicar la capa de etiquetas.

## 10. Segmentación: cómo se crean realmente los segmentos

Archivo principal:

- `backend/personalization/segmentation.py`

Aquí conviene distinguir dos cosas, porque en el código la palabra "segmento" se usa en dos niveles distintos:

1. **segmento por huésped**  
   Es lo que se guarda en `data/generated/segments.json`.  
   Cada `guest_id` tiene su propio perfil con `tags` y `metrics`.

2. **segmento de negocio agregado**  
   No se guarda directamente en `segmentation.py`.  
   Se deriva después en `backend/personalization/segment_views.py` como una etiqueta compuesta del tipo:
   `Edad · Afinidad principal · Valor`

3. **tarjeta de segmento del dashboard**  
   Se construye en `backend/marketing/dashboard.py` agrupando campañas por esa etiqueta compuesta.

### 10.1. Qué entra en `segmentation.py`

La función `segment()` mezcla dos fuentes:

- `data/generated/embeddings.json`
- `data/raw/customer_data.csv`

De `embeddings.json` toma:

- `user_embeddings`
- `user_info`
- `hotel_info`

Del CSV toma el histórico de reservas para volver a agregar métricas por huésped.

### 10.2. Qué métricas calcula primero por huésped

Antes de etiquetar, `_build_user_metrics()` agrupa por `GUEST_ID` y calcula:

- número de reservas únicas,
- `confirmed_reservations`,
- `last_2_years_stays`,
- hoteles, ciudades, países y marcas distintas,
- concentración en hotel principal (`top_hotel_share`),
- concentración en marca principal (`top_brand_share`),
- marca y país preferidos,
- lista de hoteles, ciudades, países y marcas visitadas,
- `avg_adr`,
- `avg_leadtime`,
- `avg_stay`,
- `avg_stars`.

Es importante porque muchas etiquetas no salen del embedding, sino de estas agregaciones operativas.

### 10.3. Qué genera para cada huésped

La salida final por usuario tiene esta forma conceptual:

```json
{
  "guest_id": "1001025656",
  "country": "ES",
  "gender": "Masculino",
  "age_range": "46-65",
  "avg_score": 7.0,
  "tags": {
    "afinidades_destino": ["cultural", "gastronomico", "mediterraneo"],
    "nivel_valor": "premium",
    "comportamiento_reserva": {
      "antelacion": "estandar",
      "duracion": "estancia_media",
      "frecuencia": "regular"
    },
    "fidelidad": {
      "principal": "multidestino",
      "secundarias": ["explorador", "fiel_pocos_hoteles"]
    },
    "demografia": {
      "edad": "adulto",
      "genero": "Masculino",
      "pais": "ES"
    }
  },
  "metrics": {
    "avg_adr": 203.26,
    "avg_stars": 4.5,
    "avg_leadtime": 18.5,
    "avg_stay": 3.0,
    "reservations": 2,
    "distinct_hotels": 2,
    "distinct_cities": 2,
    "distinct_countries": 2
  }
}
```

### 10.4. Reglas exactas de creación de etiquetas

#### Edad

`_age_segment()` usa un mapa fijo:

- `19-25` y `26-35` -> `JOVEN`
- `36-45` y `46-65` -> `ADULTO`
- `>65` -> `SENIOR`
- cualquier valor no reconocido -> `ADULTO`

En el JSON final esa edad se guarda en minúsculas dentro de `tags.demografia.edad`.

#### Afinidades de destino

`_destination_affinities()` mira directamente el embedding del usuario y aplica umbrales:

- `BEACH >= 0.55` -> `playero`
- `MOUNTAIN >= 0.55` -> `montana`
- `HERITAGE >= 0.60` -> `cultural`
- `GASTRONOMY >= 0.60` -> `gastronomico`
- `TEMP_NORM >= 0.65` -> `clima_calido`

Para clima solo deja una etiqueta:

- `CLIMATE_MEDITERRANEAN >= 0.45` -> `mediterraneo`
- `CLIMATE_CONTINENTAL >= 0.45` -> `continental`

Si ambas pasan el umbral, se queda con la más alta.

Si nada supera umbral, activa un fallback:

- ordena `cultural`, `gastronomico`, `clima_calido`, `playero`, `montana` por score,
- toma la mejor solo si supera `0.25`.

Después ordena por fuerza, elimina duplicados y limita el resultado a 3 afinidades.

#### Nivel de valor

`_compute_value_levels()` no usa un umbral absoluto de ADR.
Hace un ranking relativo dentro de la base actual:

- percentil de `avg_adr`
- percentil de `avg_stars`
- score final = `0.7 * adr_rank + 0.3 * stars_rank`

Con ese score clasifica así:

- `< 0.25` -> `esencial`
- `< 0.55` -> `confort`
- `< 0.82` -> `premium`
- resto -> `lujo`

Por eso el nivel de valor es relativo al conjunto de usuarios cargado, no a una tabla externa fija.

#### Comportamiento de reserva

`_booking_behavior()` aplica reglas simples:

- antelación:
  - `avg_leadtime <= 7` -> `ultimo_minuto`
  - `avg_leadtime >= 30` -> `planificador`
  - en medio -> `estandar`

- duración:
  - `avg_stay <= 2` -> `escapada_corta`
  - `avg_stay >= 4` -> `estancia_larga`
  - en medio -> `estancia_media`

- frecuencia:
  - `last_2_years_stays >= 3` o `confirmed_reservations >= 4` -> `frecuente`
  - `last_2_years_stays >= 2` o `confirmed_reservations >= 2` -> `regular`
  - resto -> `ocasional`

#### Fidelidad

`_loyalty_tags()` decide primero una etiqueta principal, en este orden:

1. si `reservations <= 1` -> `explorador`
2. si `distinct_hotels == 1` -> `repetidor`
3. si `distinct_countries >= 2` o `distinct_cities >= 3` -> `multidestino`
4. si `distinct_hotels <= 2` y `top_hotel_share >= 0.70` -> `fiel_pocos_hoteles`
5. en otro caso -> `explorador`

Luego puede añadir hasta dos secundarias:

- `multidestino` si viaja por varios países o ciudades y no era ya principal,
- `explorador` si no repite hotel y tiene más de una reserva,
- `repetidor` si solo ha estado en un hotel y tiene más de una reserva,
- `fiel_pocos_hoteles` si concentra reservas en pocas marcas/hoteles con `top_brand_share >= 0.70`.

#### Demografía

`_demographic_tags()` no infiere nada complejo.
Solo guarda:

- edad segmentada,
- género del `user_info`,
- país del `user_info`.

### 10.5. Cómo se convierte eso en "segmentos" legibles de negocio

El archivo `backend/personalization/segment_views.py` traduce cada perfil individual a una etiqueta resumida.

Las funciones importantes son:

- `get_age_key()`
- `get_primary_affinity()`
- `get_value_level()`
- `get_segment_label()`
- `get_segment_slug()`

La lógica es:

- edad: sale de `tags.demografia.edad` y, si falta, cae a `age_range`
- afinidad principal: es la primera posición de `afinidades_destino`; si no hay, usa `cultural`
- valor: sale de `tags.nivel_valor`; si falta, usa `confort`

Con eso construye:

- `segment_label = "Edad · Afinidad principal · Valor"`
- `segment_slug = "edad_afinidad_valor"`

Ejemplo real:

- `Adulto · Cultural · Premium`
- slug: `adulto_cultural_premium`

Esto es lo que usan el copy, el renderer, el delivery, el sistema autónomo y el dashboard cuando hablan de "segmento".

### 10.6. Cómo agrupa el dashboard esos segmentos

`backend/marketing/dashboard.py` no vuelve a segmentar usuarios desde cero.
Hace otra cosa:

1. lee `segments.json`,
2. lee `campaign_log.json`,
3. genera filas de campaña con `segment_label`,
4. agrupa por esa etiqueta,
5. crea tarjetas agregadas.

Cada tarjeta de segmento calcula:

- usuarios únicos,
- campañas asociadas,
- `avg_engagement_index`,
- `avg_adr`,
- canal dominante,
- momento dominante,
- peso sobre la base (`share_of_base`).

Después ordena las tarjetas y se queda con las 8 mejores para el dashboard.

Eso significa que:

- `segments.json` contiene **200 perfiles individuales**,
- pero el dashboard trabaja con **segmentos agregados por etiqueta compuesta**,
- y el KPI `active_segments` depende de las campañas registradas, no solo de la segmentación cruda.

### 10.7. Distribución real actual

En `data/generated/segments.json` hay 200 perfiles individuales.

Distribución de edad:

- `adulto`: 90
- `joven`: 82
- `senior`: 28

Distribución de valor:

- `confort`: 82
- `premium`: 69
- `esencial`: 30
- `lujo`: 19

Fidelidad principal:

- `explorador`: 172
- `multidestino`: 17
- `repetidor`: 11

Afinidades más frecuentes:

- `cultural`: 186 apariciones
- `gastronomico`: 180
- `playero`: 55
- `continental`: 55

Si transformas esos perfiles con `get_segment_label()`, hoy aparecen **30 etiquetas compuestas distintas**.
Las más frecuentes son:

- `Adulto · Cultural · Confort`: 21 usuarios
- `Joven · Cultural · Confort`: 19
- `Adulto · Cultural · Premium`: 12

La conclusión importante es esta:

- el sistema no crea un único segmento rígido por reglas de marketing clásicas,
- crea primero un perfil rico por huésped,
- y luego deriva una etiqueta compacta para operar, explicar y agrupar.

## 11. Predicción temporal: cuándo contactar al usuario

Archivo principal:

- `backend/personalization/travel_prediction.py`

Este módulo responde a una pregunta de negocio muy importante:

> "No basta con saber qué decir. También hay que saber cuándo enviarlo."

### 11.1. Dos modos de predicción

Hay dos estrategias:

1. `heuristic`
2. `regression`

### 11.2. Modo heurístico

El sistema:

- mira en qué mes suele viajar esa persona,
- estima la próxima ocurrencia,
- resta los días de antelación con que suele reservar.

Es una aproximación simple basada en costumbres.

### 11.3. Modo regresión

El sistema intenta ajustar una línea sobre las fechas históricas de check-in.

Traducido:

- toma los viajes pasados,
- observa el patrón temporal,
- proyecta cuándo podría ocurrir el siguiente.

### 11.4. Qué es una regresión lineal

Una regresión lineal es una técnica matemática muy básica que intenta dibujar la recta que mejor explica una tendencia.

Ejemplo intuitivo:

- si alguien viaja cada cierto número de meses,
- la recta puede aproximar esa periodicidad,
- y el sistema puede usarla para extrapolar el siguiente viaje.

### 11.5. Ejemplo real con el usuario `1014907189`

Modo heurístico:

- check-in estimado: `2026-12-15`
- envío estimado: `2026-12-01`
- fuente: `seasonality_leadtime`

Modo regresión:

- check-in estimado: `2026-07-04`
- envío estimado: `2026-06-13`
- fuente: `linear_regression_checkin_dates`

### 11.6. Limitación importante

Si un usuario tiene muy pocos viajes históricos, la regresión puede dar una apariencia de precisión que en realidad no es tan sólida.

Ejemplo:

- con 2 puntos, una línea siempre puede ajustar muy bien.

Por eso este sistema mezcla:

- predicción simple,
- fallback heurístico,
- y varias salvaguardas.

## 12. Planificación de campañas: qué contenido preparar

Archivo principal:

- `backend/campaigns/planner.py`

Este archivo es uno de los más importantes del backend.

Su trabajo es construir el **payload** de campaña.

Payload significa:

> el conjunto de datos que luego usará el generador de texto, el renderizador y el sistema de entrega.

### 12.1. Los tres momentos de campaña

#### `pre_arrival`

Mensaje antes de una futura estancia.

Hace cosas como:

- recomendar hotel,
- predecir fecha,
- detectar temporada,
- recoger eventos del destino,
- resumir preferencias del usuario.

Importante:

- en `backend/campaigns/planner.py`, esos eventos salen de `MOCK_EVENTS`,
- es decir, son datos simulados para la demo y no una conexión real a una API externa.

#### `checkin_report`

Informe interno para recepción.

Incluye:

- perfil del huésped,
- historial de visitas,
- upselling recomendado,
- resumen del comportamiento.

#### `post_stay`

Mensaje después de la estancia.

Incluye:

- recuerdo de la última estancia,
- sugerencia de próximo destino,
- tono de fidelización o reactivación.

### 12.2. Por qué esto es importante conceptualmente

Aquí el backend deja de ser un simple clasificador y pasa a ser un **sistema de orquestación contextual**.

No solo dice "este usuario es adulto premium".
También construye el contexto operativo completo:

- qué hotel,
- cuándo,
- por qué,
- con qué tono,
- con qué oportunidades.

## 13. Selección de imágenes

Archivos:

- `backend/assets/image_metadata.py`
- `backend/assets/image_selector.py`

### 13.1. Qué hace `image_metadata.py`

No analiza imágenes con visión artificial avanzada.
Lo que hace es más simple:

- lee el nombre del archivo,
- detecta categorías como `habitaciones`, `spa`, `restauracion`, `cerca-del-hotel`,
- y les asigna tags manuales.

Ejemplo:

- una imagen de `spa` recibe tags como `spa`, `wellness`, `relax`, `premium`.

### 13.2. Qué hace `image_selector.py`

Puntúa imágenes según:

- embedding del usuario,
- edad derivada del segmento,
- afinidades de destino,
- nivel de valor,
- audiencia estimada de la imagen,
- mood de la imagen.

Luego devuelve las mejores.

### 13.3. Fundamento teórico

Esto es un sistema de **ranking por reglas y pesos**.

No hay un modelo visual complejo.
Hay una tabla de prioridades:

- si el cliente es premium, favorece imágenes premium,
- si le gusta gastronomía, favorece restaurante,
- si sus afinidades dicen `cultural`, favorece fachadas o espacios históricos,
- si es joven, favorece imágenes más aspiracionales o sociales.

## 14. Generación de texto con IA

Archivos:

- `backend/campaigns/copy.py`
- `backend/ai/gemini.py`

### 14.1. Qué hace `copy.py`

Construye un prompt para Gemini y pide un JSON estructurado con:

- `subject`
- `preheader`
- `headline`
- `subheadline`
- `body_paragraphs`
- `cta_text`
- `cta_url_suffix`
- `ps_line`

Si Gemini no está disponible, genera un texto mock determinista.

### 14.2. Qué es un prompt

Un prompt es la instrucción que se le da al modelo.

En este proyecto el prompt le dice al modelo:

- quién es el usuario,
- qué hotel se recomienda,
- qué etiquetas de afinidad, valor y comportamiento tiene,
- qué tono usar,
- qué estructura de salida debe devolver.

### 14.3. Qué papel juega realmente la IA aquí

La IA generativa **no decide sola toda la estrategia**.

La decisión fuerte ya viene antes:

- el backend decide segmento y etiquetas,
- decide hotel,
- decide fecha,
- decide contexto,
- decide canal.

La IA entra sobre todo para:

- redactar mejor,
- adaptar tono,
- resumir,
- dar variedad lingüística.

Esto es importante porque desmonta una idea común:

> el modelo no "piensa todo".  
> El modelo es solo una pieza dentro de una tubería más grande.

### 14.4. Por qué el wrapper `backend/ai/gemini.py` es útil

Ese archivo:

- resuelve credenciales,
- comprueba si Vertex AI está disponible,
- llama al modelo,
- limpia bloques ```json```,
- y parsea la respuesta.

Eso aísla la integración externa del resto del sistema.

En arquitectura de software esto es muy buena práctica:

- si mañana cambias Gemini por otro proveedor,
- tocas menos piezas.

## 15. Renderizado: convertir datos en HTML

Archivo principal:

- `backend/campaigns/renderer.py`

Plantillas:

- `template_joven.html`
- `template_adulto.html`
- `template_senior.html`
- `receptionist_report.html`

### 15.1. Qué hace

Toma:

- datos de campaña,
- copy generado,
- lista de imágenes,
- momento del viaje,

y los inyecta en una plantilla Jinja2.

### 15.2. Qué es una plantilla

Una plantilla es un HTML con huecos.

Ejemplo conceptual:

```html
<h1>{{ copy.headline }}</h1>
<p>{{ hotel_name }}</p>
```

Luego el backend rellena esos huecos con datos reales.

### 15.3. Por qué hay varias plantillas

Porque el proyecto intenta adaptar no solo el texto, sino también la presentación visual según edad.

Eso responde a una idea de marketing:

- personalización no es solo "poner tu nombre",
- también es ajustar lenguaje visual y estructura.

## 16. Selección de canal

Archivo:

- `backend/campaigns/channels.py`

### 16.1. Qué hace

Decide si el canal principal sería:

- `email`
- `sms`
- `push`

### 16.2. Cómo decide

Reglas simples:

- `SENIOR` -> email
- lead time muy corto -> sms
- `JOVEN` -> push + email de respaldo
- lead time largo -> email

### 16.3. Fundamento teórico

Esto es un sistema de **decisión por reglas de negocio**.

La idea es:

- no todos los usuarios responden igual al mismo canal,
- por tanto el backend adapta el medio además del mensaje.

## 17. Entrega y trazabilidad

Archivo:

- `backend/campaigns/delivery.py`

### 17.1. Qué hace

En modo demo:

- guarda HTML en `output/`
- registra cada campaña en `data/generated/campaign_log.json`

En modo real podría enviar por SendGrid.

### 17.2. Por qué esto importa

Aquí aparece un concepto básico de backend real:

> no basta con generar algo; también hay que dejar rastro de lo generado.

Ese rastro sirve para:

- auditoría,
- reporting,
- dashboard,
- depuración.

### 17.3. Qué guarda el log

Ejemplo de campos:

- huésped,
- canal,
- plantilla,
- tipo de campaña,
- hotel recomendado,
- asunto,
- timestamp,
- estado.

## 18. Ejemplo real completo de extremo a extremo

Voy a seguir al huésped real `1014907189`.

### 18.1. Datos de entrada

En el CSV aparece como:

- país: `PT`
- género: `Femenino`
- edad: `36-45`
- ADR medio: `109.24`
- estancia media: `3.5`
- lead time medio: `6`

### 18.2. Segmentación resultante

El backend lo clasifica como:

- `edad`: `adulto`
- `afinidades_destino`: `cultural`, `gastronomico`, `mediterraneo`
- `nivel_valor`: `esencial`
- `comportamiento_reserva`: `ultimo_minuto`, `estancia_media`, `regular`
- `fidelidad.principal`: `multidestino`

### 18.3. Recomendación

El sistema recomienda:

- `Aurea Catedral`
- ciudad: `GRANADA`
- `recommendation_score`: `0.8489`

### 18.4. Preferencias inferidas

El backend resume sus gustos como:

- patrimonio histórico y cultural
- gastronomía local
- experiencias premium y exclusivas
- alojamientos de alta categoría

### 18.5. Predicción temporal

En modo heurístico:

- fecha sugerida de check-in: `2026-12-15`
- fecha sugerida de envío: `2026-12-01`

### 18.6. Qué se haría después

Con eso, el sistema:

1. genera un prompt para copy usando la etiqueta compuesta del segmento y sus tags enriquecidas,
2. selecciona imágenes afines usando embedding y afinidades de destino,
3. renderiza con la plantilla de edad correspondiente,
4. guarda un HTML en `output/`,
5. y registra la acción en `campaign_log.json`.

### 18.7. Qué aprender de este ejemplo

El backend está haciendo tres traducciones seguidas:

1. de datos históricos a perfil,
2. de perfil + etiquetas a decisión,
3. de decisión a contenido.

Ese es el corazón conceptual del proyecto.

## 19. El informe de recepción: personalización operativa

Una parte muy interesante del backend es `checkin_report`.

No genera marketing externo.
Genera inteligencia operativa interna.

Para el mismo usuario `1014907189`, el informe incluye:

- país, género y rango de edad,
- número de estancias,
- hoteles visitados,
- última estancia,
- preferencias,
- recomendaciones de upsell.

Ejemplos reales de upsell calculado:

- inscripción en programa de fidelización
- descuento en próxima reserva directa
- upgrade sujeto a disponibilidad
- transfer privado aeropuerto-hotel

### 19.1. Por qué esto es importante

Aquí se ve que el backend no sirve solo para "mandar un email bonito".
También sirve para que recepción actúe mejor.

Eso une dos mundos:

- marketing,
- operación hotelera.

## 20. El dashboard de marketing

Archivos:

- `backend/marketing/dashboard.py`
- `backend/marketing/chat.py`

### 20.1. Qué hace `dashboard.py`

Construye un payload con:

- KPIs,
- campañas recientes,
- rendimiento por edad,
- rendimiento por perfil,
- rendimiento por valor,
- rendimiento por momento,
- segmentos prioritarios,
- recomendaciones de acción.

### 20.2. De dónde sale esa información

La combina desde:

- `campaign_log.json`
- `segments.json`
- `customer_data.csv`
- `marketing_context.json`

### 20.3. Qué es `marketing_context.json`

Es un archivo editable con contexto humano:

- prioridad estratégica,
- notas del manager,
- notas de recepción,
- señales externas.

Esto es importante porque introduce una idea muy realista:

> un sistema de marketing no vive solo de datos transaccionales.  
> También necesita contexto de negocio.

### 20.4. Qué hace internamente el dashboard

Calcula métricas como:

- campañas totales,
- tamaño de audiencia,
- segmentos activos,
- índice medio de engagement.

Ojo:

- ese `engagement_index` no viene de clics reales en una plataforma de emailing,
- es un índice sintético calculado con pesos y reglas.

Eso convierte el dashboard en un simulador analítico razonable para demo.

## 21. El chat de marketing

Archivo:

- `backend/marketing/chat.py`

### 21.1. Qué hace

Permite que el usuario pregunte cosas como:

- qué segmento funciona peor,
- qué ideas hay para captar familias,
- qué campaña conviene lanzar,
- cómo modificar una propuesta.

### 21.2. Cómo responde

Tiene dos modos:

1. **con Gemini**
2. **con heurísticas**

Si Gemini no está disponible, sigue respondiendo con lógica local.

### 21.3. Idea teórica importante

Lo que hace realmente es:

- reconstruir el contexto del dashboard,
- meterlo en un prompt,
- y pedir una respuesta sobre esos datos.

Es decir:

- no responde "desde el conocimiento general del modelo",
- responde desde el estado del negocio que el backend le inyecta.

## 22. Reescritura y propuestas de campañas

También dentro de `backend/marketing/chat.py` se generan:

- propuestas de campañas,
- variaciones de mensajes,
- cambios de tono o canal.

Cuando no hay IA, cae en heurísticas.

Eso enseña otro principio de ingeniería útil:

> el sistema no depende al 100% de la nube para seguir funcionando.

Tiene fallbacks deterministas.

## 23. El sistema autónomo: qué significa realmente "multi-agente"

Archivos:

- `backend/autonomous/oracle.py`
- `backend/autonomous/scheduler.py`
- `backend/autonomous/generator.py`
- `backend/autonomous/generic_campaigns.py`
- `backend/autonomous/heartbeat.py`
- `backend/autonomous/live.py`

### 23.1. Qué NO significa

"Multi-agente" aquí no significa ciencia ficción ni agentes ultrainteligentes que piensan como personas.

Aquí significa algo más práctico:

- varios módulos con responsabilidades distintas,
- y en el modo `live`, varios workers concurrentes procesando tareas en paralelo.

### 23.2. El Oráculo (`oracle.py`)

Es la fuente de contexto externo.

Puede producir entradas como:

- eventos culturales,
- ofertas estacionales,
- alertas de viaje,
- tendencias turísticas.

Si Gemini no está disponible, usa una base mock plausible.

#### Idea teórica

El Oráculo introduce la variable:

> "además del historial del cliente, qué está pasando ahora en el mundo"

Eso evita que la personalización sea estática.

### 23.3. El Scheduler (`scheduler.py`)

Decide qué usuarios son candidatos a ser contactados en este momento.

Combina:

- fecha ideal de envío,
- ventana de envío,
- cooldown,
- máximo de candidatos por tick.

#### Qué es un cooldown

Un cooldown es un periodo mínimo entre contactos al mismo usuario.

Sirve para no saturarlo.

### 23.4. El estado autónomo (`storage/autonomous_state.py`)

Guarda cosas como:

- última actualización del Oráculo,
- usuarios contactados recientemente,
- destinos bloqueados,
- campañas genéricas ya lanzadas,
- número de ticks ejecutados.

Esto hace al sistema **stateful**.

Stateful significa:

> que recuerda lo ocurrido antes y usa esa memoria para decidir ahora.

### 23.5. El generador autónomo (`generator.py`)

Reutiliza buena parte del pipeline normal, pero añade el contexto del Oráculo.

Hace cosas como:

- mirar el hotel recomendado,
- ver si el destino está bloqueado,
- emparejar eventos del Oráculo con el perfil del usuario,
- incluir esos eventos en el prompt,
- generar el email final.

Aquí aparece una idea potente:

> la recomendación ya no depende solo del historial del huésped,  
> también depende de si "este es un buen momento" para ese destino.

### 23.6. Campañas genéricas (`generic_campaigns.py`)

No apuntan a una persona concreta.
Apuntan a segmentos grandes.

Ejemplo de lógica:

- buscar segmentos con tamaño suficiente,
- buscar ciudades con tendencia positiva,
- emparejarlos,
- proponer una campaña general.

### 23.7. El heartbeat (`heartbeat.py`)

Es el bucle principal del sistema autónomo.

Cada tick hace:

1. refrescar Oráculo si toca,
2. buscar candidatos,
3. generar campañas personalizadas,
4. generar campañas genéricas si toca,
5. guardar estado.

Esto convierte el sistema en algo parecido a un proceso periódico.

## 24. Concurrencia: por qué `live.py` usa varios workers

`backend/autonomous/live.py` está pensado para emitir eventos en tiempo real al dashboard.

### 24.1. Qué hace

- crea una cola compartida,
- lanza varios workers,
- cada worker procesa candidatos,
- y el servidor va enviando eventos NDJSON al frontend.

### 24.2. Qué es un worker

Un worker es simplemente una unidad de trabajo en paralelo.

No significa necesariamente un servidor distinto.
Aquí suele ser un **hilo** de Python.

### 24.3. Qué es la concurrencia

Concurrencia significa poder avanzar en varias tareas al mismo tiempo o casi al mismo tiempo.

En este caso sirve para simular que:

- varios usuarios pueden ser procesados de forma paralela,
- mientras además se generan propuestas de campaña para el dashboard.

## 25. Cómo el frontend usa el backend

### 25.1. Demo de marketing

Archivo:

- `demos/marketing/server.py`

Expone endpoints como:

- `/api/dashboard`
- `/api/context`
- `/api/chat`
- `/api/campaigns`
- `/api/autonomous/stream`

Ese servidor no contiene la lógica principal.
Solo hace de puente hacia `backend/marketing/*` y `backend/autonomous/*`.

### 25.2. Demo de mail

Archivo:

- `demos/mail/server.py`

Lee perfiles y emails generados desde:

- `data/`
- `output/`

Es decir:

- el frontend de mail no inventa nada,
- solo muestra lo que el backend ya produjo.

### 25.3. Demo de recepción

Archivo:

- `demos/receptionist/server.py`

Lee informes `checkin_report_*.html` desde `output/` y extrae información útil para mostrársela al usuario.

## 26. Artefactos que produce el backend

Estos archivos son claves para entender la "huella" del backend:

- `data/generated/embeddings.json`
  Representación numérica de hoteles y usuarios.

- `data/generated/segments.json`
  Segmentación completa por usuario: `tags` enriquecidas y métricas derivadas. Las etiquetas agregadas de negocio se derivan después con `segment_views.py`.

- `data/generated/campaign_log.json`
  Registro de campañas generadas.

- `data/generated/marketing_dashboard_snapshot.json`
  Fotografía del dashboard.

- `data/runtime/marketing_context.json`
  Contexto estratégico editable.

- `data/runtime/autonomous_state.json`
  Estado del sistema autónomo.

- `data/runtime/oracle_context.json`
  Contexto externo del Oráculo.

- `output/*.html`
  Emails e informes renderizados.

## 27. Fundamentos teóricos, explicados sin tecnicismos innecesarios

### 27.1. Representación numérica

Un ordenador compara mucho mejor números que frases ambiguas.
Por eso el backend traduce hoteles y gustos a vectores.

### 27.2. Recomendación híbrida

Si dos perfiles numéricos se parecen, el sistema asume que uno puede interesar al otro.

Pero en este proyecto la recomendación final no se queda ahí:

- primero usa similitud entre embeddings,
- luego reranquea con etiquetas de afinidad, valor, fidelidad y comportamiento.

### 27.3. Segmentación interpretable

Agrupar usuarios sirve para:

- adaptar tono,
- adaptar visual,
- adaptar canal,
- adaptar oferta.

La clave nueva es que la segmentación ya no vive en una sola etiqueta plana.
Ahora hay dos capas:

- un perfil rico por huésped,
- una etiqueta compuesta legible para negocio.

Ese perfil incluye:

- afinidades de destino,
- nivel de valor,
- comportamiento de reserva,
- fidelidad,
- demografía.

### 27.4. Predicción temporal

No solo importa el contenido.
Importa el momento.

Un buen mensaje en mal momento puede rendir mal.

### 27.5. Generación con LLM

El LLM no reemplaza la lógica de negocio.
La embellece y la verbaliza.

### 27.6. Sistemas híbridos

Este proyecto es claramente híbrido:

- parte matemática simple,
- parte reglas de negocio,
- parte IA generativa,
- parte plantillas HTML,
- parte estado operativo.

Y eso, en realidad, es muy típico en productos de IA útiles.

## 28. Qué partes son "IA de verdad" y cuáles no

Para quitar confusión:

### Sí es IA o se parece bastante a IA aplicada

- generación de copy con Gemini,
- generación/síntesis de contexto del Oráculo con Gemini,
- chat de marketing cuando usa Gemini,
- recomendación basada en representación numérica y similitud.

### No es IA avanzada, aunque sea inteligente en sentido práctico

- lectura de CSV,
- reglas de segmentación,
- etiquetado de imágenes por nombre de archivo,
- selección de canal por reglas,
- persistencia en JSON,
- plantillas HTML.

Esto no es un defecto.
De hecho, muchos sistemas útiles mezclan:

- un poco de IA,
- mucha ingeniería clara.

## 29. Limitaciones reales del backend

Conviene entenderlas para no idealizar el sistema.

### 29.1. No aprende automáticamente de conversiones reales

No hay una retroalimentación completa del estilo:

- campaña enviada,
- usuario abrió,
- clicó,
- reservó,
- el modelo aprendió.

### 29.2. Muchas decisiones son heurísticas

Eso lo hace explicable, pero también menos fino.

### 29.3. Los embeddings son manuales

Son útiles para demo, pero no capturan toda la riqueza real del comportamiento humano.

### 29.4. El Oráculo puede usar datos mock

Muy útil para demo local.
Menos realista en producción.

### 29.5. Parte del contexto externo del planner también es mock

En `backend/campaigns/planner.py` hay una tabla `MOCK_EVENTS`.

Eso significa que:

- la lógica de personalización es real,
- pero parte del contexto de eventos está simulado.

### 29.6. La regresión con poco histórico puede ser frágil

Especialmente con 2 o 3 viajes.

### 29.7. La "base de datos" es local y simple

CSV y JSON son cómodos, pero no escalan igual que una base de datos real.

## 30. Si tuvieras que resumir la función de cada carpeta backend

### `backend/storage`

Lee y escribe datos.

### `backend/personalization`

Convierte histórico en perfil y recomendaciones.

### `backend/campaigns`

Construye campañas personalizadas y salidas HTML.

### `backend/assets`

Etiqueta y selecciona imágenes.

### `backend/marketing`

Construye el dashboard, el chat y propuestas de marketing.

### `backend/autonomous`

Hace que el sistema trabaje de forma periódica y proactiva.

### `backend/ai`

Centraliza la llamada al modelo Gemini.

### `backend/config.py` y `backend/paths.py`

Definen configuración, rutas y variables de entorno.

## 31. Qué es lo más importante que deberías quedarte

Si solo quieres entender la esencia del backend, quédate con esto:

1. **Lee datos de clientes y hoteles.**
2. **Convierte esos datos en perfiles numéricos y etiquetas comprensibles.**
3. **Usa esos perfiles para decidir qué campaña conviene y cuándo.**
4. **Genera contenido personalizado con reglas + IA generativa.**
5. **Renderiza resultados útiles para marketing, email y recepción.**
6. **Guarda estado y métricas para que el sistema sea trazable.**

## 32. Resumen en una sola frase

El backend de este proyecto es un sistema que transforma historial hotelero en decisiones personalizadas de marketing y operación, combinando datos, reglas, matemáticas sencillas, plantillas y modelos generativos.

## 33. Cómo leer este proyecto sin perderte

Si quieres recorrer el backend en orden lógico, te recomiendo este camino:

1. `backend/paths.py`
2. `backend/storage/customers.py` y `backend/storage/hotels.py`
3. `backend/personalization/embeddings.py`
4. `backend/personalization/segmentation.py`
5. `backend/personalization/travel_prediction.py`
6. `backend/campaigns/planner.py`
7. `backend/assets/image_selector.py`
8. `backend/campaigns/copy.py`
9. `backend/campaigns/renderer.py`
10. `backend/campaigns/delivery.py`
11. `backend/marketing/dashboard.py`
12. `backend/marketing/chat.py`
13. `backend/autonomous/oracle.py`
14. `backend/autonomous/scheduler.py`
15. `backend/autonomous/generator.py`
16. `backend/autonomous/heartbeat.py`

## 34. Glosario mínimo

### Backend

Parte del sistema que hace el trabajo interno: procesa datos, toma decisiones y genera resultados.

### Frontend

Parte visual con la que interactúa el usuario.

### Embedding

Representación numérica de algo para poder compararlo matemáticamente.

### Segmentación

Clasificación de usuarios en grupos útiles para negocio.

### Heurística

Regla práctica que funciona razonablemente bien sin ser una ley exacta.

### Regresión lineal

Método matemático simple para estimar tendencias.

### Prompt

Instrucción que se le da a un modelo generativo.

### Template / plantilla

Documento con huecos que se rellenan con datos.

### Payload

Conjunto de datos preparados para otra fase del sistema.

### Cooldown

Tiempo mínimo de espera antes de volver a contactar al mismo usuario.

### Tick

Una ejecución del ciclo del sistema autónomo.

---

Si más adelante quieres, puedo hacer una **segunda versión todavía más pedagógica**, pero enfocada a "leer el código línea por línea" y enlazando cada concepto con los archivos concretos del proyecto.
