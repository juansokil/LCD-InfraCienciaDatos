# TP Final - G06 - Open-Meteo

---

## Integrantes

- Julian Tello (@jtello94)
- Agostina Bravo (@agostbravo)
- Camila Dasso (@camiladasso)
- Javier Valdez (@JavierGValdez)
- Donato Scarinci (@donascarinci)

## API elegida

- **Nombre**: Open-Meteo
- **URL**: https://open-meteo.com/en/docs
- **Descripcion**: devuelve el clima actual y el pronóstico a varios días (temperatura, lluvia, humedad, viento) para las coordenadas de las ciudades que se consulten.
- **Auth**: sin auth
- **API key**: no necesita
- **Refresh**: cada hora

## Modelo de datos

Para nuestro trabajo utilizaremos una estructura Medallion (Bronze, Silver y Gold) para recopilar, transformar y analizar la información meteorológica de tres destinos turisticos de Argentina.

Decisiones:
período de tiempo: 5 años (definir fecha exacta)

Destinos elegidos: 
-Purmamarca (Cerro de los siete colores, Jujuy)
-Bariloche (Río Negro)
-Puerto Iguazu (Misiones)

Vamos a utilizar la información diaria para poder comparar los mismos meses entre distintos años.

Selección de variables:
-temperature_2m_min: temperatura mínima del día.
-temperature_2m_mean: temperatura media del día.
-temperature_2m_max: temperatura máxima del día.
-precipitation_sum: cantidad de precipitaciones acumuladas durante el día.
-daylight_duration: duración de la luz natural durante el día.
-wind_gusts_10m_max: ráfagas máximas de viento durante el día.

### Bronze

Clima actual y pronóstico de 7 días para N ciudades elegidas, guardado crudo (temperatura, lluvia, humedad, viento), con metadatos de auditoría (`ingested_at`, `source`).

### Silver

Normalización de unidades (Celsius, km/h), separación entre pronóstico y medición real, y cálculo de sensación térmica.

### Gold

Modelo dimensional con `fact_clima_diario` (temperatura promedio, máxima y mínima, y lluvia acumulada por ciudad), `dim_ciudad` y `dim_tiempo`. El dashboard responde: comparación entre ciudades, alertas de temperatura extrema e historial de lluvia.

## Como levantar el stack

```bash
cd TpFinal/grupos/G06/
docker compose up -d --build   # el .env ya viene en el repo
# Esperar ~30s a que Airflow termine de inicializar
```

**Accesos**:
- Airflow UI: http://localhost:8080 (`admin` / `admin`)
- Dashboard (Gold): http://localhost:8501
- Postgres: `localhost:5432` (user/pass en `.env`)

**Apagar**:
```bash
docker compose down            # apaga, conserva datos
docker compose down -v         # apaga y BORRA volumenes (cuidado)
```

## Estructura del proyecto

Ver la seccion **"Esqueleto de entrega"** en [`TpFinal/README.md`](../../README.md) — es una estructura sugerida, no obligatoria.