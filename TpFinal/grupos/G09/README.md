# TP Final - Grupo 09

## Integrantes
* [Lisandro Farina] - [@lisandrofarina06]
* [Lucas Feller] - [lucasfeller]
* Juan Pablo Varini - [JuanPablo0620]
* Matias Bardelli - [@stx-06]

## API Elegida
**Open-Meteo (Clima)**: https://open-meteo.com/

## Idea para Gold
Construir un modelo en estrella con:
* `fact_clima_diario`: temperaturas, lluvia y viento por ciudad y día.
* `dim_ciudad`: nombre de la ciudad, latitud y longitud.
* `dim_tiempo`: fecha, mes y estación del año.
**Dashboard:** Un mapa o gráfico comparativo de temperaturas entre ciudades y alertas de temperaturas extremas.

## Objetivo

Analizar cómo varían las condiciones climáticas entre distintas regiones de la provincia de Buenos Aires.

Localidades seleccionadas:

- Mar del Plata — Costa.
- Tandil — Interior.
- Bahía Blanca — Sur.

## Arquitectura

El proyecto utiliza la infraestructura general de InfraCienciaDatos:

- Apache Airflow para la orquestación.
- PostgreSQL para el almacenamiento.
- Docker para la ejecución de los servicios.
- Open-Meteo como fuente de datos.

## Estructura

```text
G09/
├── README.md
├── requirements.txt
├── docs/
│   └── ARQUITECTURA_BRONZE.md
└── dags/
    └── bronze/
        └── dag_g09_bronze_open_meteo.py
```

## Estado del proyecto

- [x] Integración de DAGs G09 con Airflow.
- [x] Primera implementación de ingesta Bronze.
- [ ] Validación de extracción de las tres localidades.
- [ ] Diseño de Silver.
- [ ] Diseño de Gold.
- [ ] Análisis exploratorio.
- [ ] Dashboard.

## Ejecución

Desde la carpeta `stack/`:

```powershell
docker compose up -d airflow
```

Interfaz de Airflow:

http://localhost:8080

DAG:

`g09_bronze_open_meteo`

Para más información sobre la arquitectura Bronze, consultar:

`docs/ARQUITECTURA_BRONZE.md`