# Clase 04: La Refinería (Capa Silver)

> **Material de la clase**:
> - [`clase04.ipynb`](clase04.ipynb) — desarrollo teórico: Pydantic, contratos de datos, SCD Tipo 2 con SQL, patrón de cuarentena.
> - [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb) — ejercicio **opcional**: refinería de datos crypto (Bronze → Silver).
> - [`ejercicios/dag_crypto_silver.py`](ejercicios/dag_crypto_silver.py) — DAG productivo de transformación Bronze → Silver (con comentarios educativos).

---

## 🎯 Objetivos

- Transformar datos crudos (**Capa Bronze**) en datos técnicos limpios (**Capa Silver**).
- Definir y validar **Contratos de Datos** profesionales (Data Quality).
- Implementar limpieza avanzada: normalización técnica y deductiva.
- Aplicar el patrón de **Cuarentena** para registros que no cumplen calidad.

---

## 🏗️ El Proceso de Refinería

```mermaid
graph LR
    B[(Capa Bronze)] --> QC{Quality Checks}
    QC -->|Valid| S[(Capa Silver)]
    QC -->|Invalid| Q[(Cuarentena)]

    subgraph Transformaciones_Senior
        T1[Normalización Pydantic]
        T2[Tipado Estricto]
        T3[Deduplicación Idempotente]
        T4[SCD Tipo 2 - SQL]
    end
    S --- Transformaciones_Senior
```

## 🗺️ Linaje de Datos (Column-level)

A diferencia de Bronze donde traemos todo, en Silver refinamos campo a campo:

```mermaid
graph TD
    subgraph Bronze
        B1[id]
        B2[symbol]
        B3[name]
        B4[current_price]
        B5[last_updated]
    end

    subgraph Silver
        S1[id_key]
        S2[symbol_upper]
        S3[name_clean]
        S4[price_usd_float]
        S5[ingested_at]
        S6[processed_at]
    end

    B1 -->|PK Validation| S1
    B2 -->|UPPER + TRIM| S2
    B3 -->|STRIP + TITLE| S3
    B4 -->|COALESCE + RANGE| S4
    B5 -->|TIMESTAMPTZ| S5
    AUTO -->|SYSTEM_TIME| S6
```

---

## 🚀 Setup

- Stack de la **Clase 02** corriendo (`docker compose up -d` desde `stack/`).
- Datos de Bronze ya cargados (los generaste en **Clase 03** corriendo el `dag_crypto_bronze.py`).
- Tu rama personal sincronizada (ver root README → "Cómo Consumir el Repo Semana a Semana").

---

## 📋 Cómo trabajar la clase

### Paso 1 — Leer el notebook teórico

Abrí `clase04.ipynb` para entender Contratos de Datos, normalización Pydantic, SCD Tipo 2 y el patrón de Cuarentena.

### Paso 2 — (Opcional) Hacer el ejercicio práctico

Abrí `ejercicios/ejercicio.ipynb` para refinar tus propios datos crypto (Bronze → Silver). Es práctica personal sin entrega comprometida.

### Paso 3 — Correr el DAG productivo en Airflow

`ejercicios/dag_crypto_silver.py` es el DAG productivo de transformación con comentarios educativos. Para verlo correr en Airflow:

```bash
cp clase04/ejercicios/dag_crypto_silver.py stack/dags/02-silver/
```

Airflow detecta el archivo automáticamente (volumen montado). Activalo en la UI (`localhost:8080`) y mirá los datos llegar a `silver.crypto_markets` y `silver.quarantine_crypto_markets`.

---

## 🏆 Desafío Senior

No te conformes con `replace`. El objetivo es implementar una carga **idempotente** usando SQL nativo (`ON CONFLICT` o `MERGE`), asegurando que tu pipeline pueda fallar y recuperarse sin generar duplicados.

---

## 🛠️ Troubleshooting

| Problema | Solución |
| :--- | :--- |
| El DAG no aparece en Airflow UI | Verificar que el archivo esté en `stack/dags/02-silver/`. Esperar 10-30s para que Airflow lo detecte. |
| `ImportError: pydantic` (en el DAG silver) | El módulo viene en el Dockerfile del stack. Si falla, rebuild: `docker compose down && docker compose up -d --build`. |
| El DAG corre pero `silver.crypto_markets` está vacío | Verificá que el DAG `crypto_bronze` (clase03) haya corrido antes y poblado `bronze.crypto_markets`. |
| Muchos registros van a quarantine | Mirá la tabla `silver.quarantine_crypto_markets` — el campo `quarantine_reason` te dice por qué fueron rechazados. |
