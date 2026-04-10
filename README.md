# Eurostars AI Personalization Engine

Sistema end-to-end de personalización con IA para la cadena hotelera Eurostars.
Genera emails y comunicaciones personalizadas para cada huésped en base a su
historial, preferencias y segmento.

## Arquitectura

```
eurostars-ai/
├── data/
│   ├── hotel_data.csv              ← Datos de 10 hoteles
│   ├── customer_data_200.csv       ← 200 huéspedes, 260 reservas
│   ├── embeddings.json             ← Vectores de hoteles y usuarios (11 dims)
│   ├── segments.json               ← Segmentación por 4 ejes
│   └── campaign_log.json           ← Log de campañas enviadas
├── images/{hotel_id}/
│   └── metadata.json               ← Etiquetas de imágenes
├── templates/
│   ├── template_joven.html         ← Email seg. joven (hero full-bleed)
│   ├── template_adulto.html        ← Email seg. adulto (2 columnas)
│   ├── template_senior.html        ← Email seg. senior (1 columna, tlfno)
│   └── receptionist_report.html    ← Informe de recepción (check-in)
├── output/                         ← HTMLs generados (dry-run)
├── build_embeddings.py             ← Fase 1: Embeddings
├── segment_users.py                ← Fase 2: Segmentación
├── campaign_engine.py              ← Fase 3: Motor de campaña
├── image_selector.py               ← Fase 4: Selección de imágenes
├── auto_tag_images.py              ← Fase 4b: Etiquetado automático
├── text_generator.py               ← Fase 5: Generación de texto (IA)
├── email_renderer.py               ← Fase 6: Renderizado Jinja2
├── channel_selector.py             ← Fase 7: Selección de canal
├── send_campaign.py                ← Fase 8: Envío y tracking
└── main.py                         ← Orquestador del pipeline
```

## Instalación

```bash
# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar API keys (opcional — funciona sin ellas en modo dry-run)
cp .env.example .env
# Editar .env con tus claves
```

## Uso

### Pipeline completo (modo dry-run)
```bash
python main.py --phase all
```

### Por fases
```bash
# Fase 1: Generar embeddings
python main.py --phase embeddings

# Fase 2: Segmentar usuarios
python main.py --phase segment

# Fase 4a: Generar metadatos de imágenes
python main.py --phase auto_tag

# Campañas pre-arrival para todos los usuarios
python main.py --phase campaign --moment pre_arrival

# Informe de recepción para un huésped específico
python main.py --phase campaign --moment checkin_report --guest_id 1014907189

# Emails post-estancia
python main.py --phase campaign --moment post_stay
```

### Envío real (requiere SendGrid API key)
```bash
python main.py --phase campaign --moment pre_arrival --send
```

## Segmentación (4 ejes)

| Eje | Valores | Determina |
|-----|---------|-----------|
| **Edad** | JOVEN (19-35), ADULTO (36-55), SENIOR (56+) | Layout del email |
| **Perfil de viaje** | EXPLORADOR_CULTURAL, LUJO, SOL_Y_PLAYA, AVENTURERO, GASTRONOMIA_CIUDAD | Tono del mensaje |
| **Valor del cliente** | HIGH_VALUE, MID_VALUE, STANDARD | Nivel de upsell |
| **Patrón de viaje** | RECURRENTE_DESTINO, EXPLORADOR, FIEL_CADENA | Comportamiento |

## Momentos de campaña

1. **Pre-arrival**: 2 semanas antes de la ventana de viaje predicha
2. **Check-in report**: Informe para recepcionista al hacer check-in
3. **Post-stay**: 7 días después del checkout

## Sistema de Embeddings

Cada hotel → vector de 11 dimensiones:
- Estrellas, Temperatura, Riesgo de lluvia
- Playa, Montaña, Patrimonio, Precio, Gastronomía
- Clima (one-hot: Atlántico, Continental, Mediterráneo)

El embedding del usuario es la media ponderada por AVG_SCORE de los vectores
de los hoteles visitados. La recomendación se basa en similitud del coseno.

## Plantillas de email

- **Joven**: Hero full-bleed, headline grande (28px), CTA oscuro redondeado
- **Adulto**: Header con logo, 2 columnas, sección "¿Por qué este destino?", trust signals
- **Senior**: 1 columna, tipografía 16px+, alto contraste, teléfono de contacto

Todas las plantillas usan CSS inline para compatibilidad con Gmail, Outlook y Apple Mail.

## Requisitos

- Python 3.11+
- pandas, numpy, scikit-learn, jinja2, Pillow, python-dotenv, premailer
- (Opcional) anthropic, sendgrid
