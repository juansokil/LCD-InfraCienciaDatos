# Clase 04: La Refinería (Capa Silver)

> 📚 **Cómo está estructurada esta clase** (patrón compartido por clase03/04/05):
>
> 1. **Notebook teórico** ([`clase04.ipynb`](clase04.ipynb)) — conceptos + DAGs demo sobre datos sintéticos (`bronze.ventas_demo`)
> 2. **Ejercicio práctico (con entrega)** ([`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb)) — 8 ejercicios de SQL básico sobre **Northwind** (los fundamentos que Silver usa)
> 3. **DAG productivo** ([`ejercicios/dag_crypto_silver.py`](ejercicios/dag_crypto_silver.py)) — para copy-paste a Airflow

> **Material de la clase**:
> - [`clase04.ipynb`](clase04.ipynb) — desarrollo teórico + 2 DAGs pedagógicos progresivos (`silver_01_basico.py`, `silver_02_contrato.py`) que se generan vía `%%writefile` al ejecutar el notebook.
> - [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb) — **el ejercicio entregable**, un solo archivo autocontenido: **Parte 1** carga **Northwind** (setup dual-engine Postgres/DuckDB) y **Parte 2** son **8 ejercicios de SQL básico** (SELECT/WHERE/ORDER BY, COUNT, MIN/MAX, AVG, normalización+nulos con COALESCE, DISTINCT/LIKE, atributo derivado con CASE, un INNER JOIN simple), conectando cada técnica con un patrón real de Silver. La sección **📦 Entrega** genera tu `.txt` en `ejercicios/alumnos/` (ver [`ejercicios/README.md`](ejercicios/README.md)).
> - [`ejercicios/dag_crypto_silver.py`](ejercicios/dag_crypto_silver.py) — DAG productivo (con comentarios educativos), se copia al stack para correr el Silver real de crypto.

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
```

## 🗺️ Linaje de Datos (Bronze → Silver)

A diferencia de Bronze donde traemos todo crudo, en Silver pasa por 3 transformaciones antes de llegar a la tabla final. El DAG productivo `dag_crypto_silver` separa válidos de inválidos sin descartar nada:

```mermaid
graph LR
    subgraph BR["bronze.crypto_markets"]
        B[22+ columnas crudas<br/>de la API CoinGecko]
    end

    subgraph PIPE["dag_crypto_silver"]
        P1[1. Deduplicar<br/>por id + snapshot_ts]
        P2[2. Normalizar strings<br/>symbol → UPPER<br/>name → Title]
        P3[3. Validar con Pydantic<br/>generado dinamicamente<br/>desde crypto_markets.yaml]
    end

    subgraph SV["silver.crypto_markets (validos)"]
        SVOK[Columnas originales<br/>+ _processed_at<br/>+ _source_table<br/>+ _contract_version]
    end

    subgraph SQ["silver.quarantine_crypto_markets (rechazados)"]
        SQNG[Columnas originales<br/>+ quarantine_reason<br/>+ _processed_at<br/>+ _source_table<br/>+ _contract_version]
    end

    B --> P1 --> P2 --> P3
    P3 -->|cumple contrato| SVOK
    P3 -->|falla contrato| SQNG

    style BR fill:#fff3e0,stroke:#e65100
    style PIPE fill:#f3e5f5,stroke:#4a148c
    style SV fill:#e8f5e9,stroke:#1b5e20
    style SQ fill:#ffebee,stroke:#c62828
```

> **Nota**: el lineage NO renombra columnas (no hay `id_key`, `symbol_upper`, etc. — los nombres se mantienen). Lo que cambia es el **contenido** (normalizado) y la **garantía de validez** (Pydantic ya las chequeó).

---

## 🚀 Setup

- Stack de la **Clase 02** corriendo (`docker compose up -d` desde `stack/`).
- Datos de Bronze ya cargados (los generaste en **Clase 03** corriendo el `dag_crypto_bronze.py`).
- Tu rama personal sincronizada (ver root README → "Cómo Consumir el Repo Semana a Semana").

---

## 📋 Cómo trabajar la clase

### Paso 1 — Leer el notebook teórico y correr los DAGs pedagógicos

Abrí `clase04.ipynb`. La primera parte explica conceptos (Contratos de Datos, Pydantic, SCD Tipo 2, Cuarentena). La parte final tiene cells `%%writefile` que generan **2 DAGs sintéticos numerados** — al ejecutarlos, los `.py` aparecen automáticamente en `stack/dags/02-silver/`:

| # | DAG generado | Path destino | Qué aporta |
|---|--------------|--------------|------------|
| 01 | `silver_01_basico.py` | `stack/dags/02-silver/` | Limpieza básica: strip + Title Case + fillna + parser flexible de fechas |
| 02 | `silver_02_contrato.py` | `stack/dags/02-silver/` | **Contract-driven**: Pydantic generado en runtime desde `ventas.yaml` + Pattern Quarantine + Audit metadata |

Después de ejecutar las celdas, los DAGs aparecen en Airflow UI (`localhost:8080`). En la UI, filtrá por **tag `silver`** para verlos juntos. Activalos y verás los datos en `silver.ventas_demo` y `silver.quarantine_ventas_demo`.

> **Convención de carpetas**: cada DAG vive en la carpeta de su **capa Medallion destino** (`02-silver/` para todo lo que escribe a `silver.*`). Mismo patrón que `01-bronze/` en clase 03.
>
> **Convención de tags**: sintéticos didácticos llevan `tags=["silver"]`. El DAG productivo (crypto) lleva `tags=["prod", "silver", "crypto"]` para distinguirlo en la UI con el filtro `prod`.
>
> **🔁 Continuidad con clase 03**: el `silver_02_contrato` lee el **mismo `ventas.yaml`** que usaba `bronze_04_con_contrato`. Bronze validaba la *forma*, Silver valida la *semántica*. Un contrato, dos capas.

### Paso 2 — Hacer el ejercicio práctico (con entrega)

El ejercicio entregable de esta clase es **[`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb)** (un solo archivo): corré la **Parte 1 — Setup** (carga Northwind, dual-engine Postgres/DuckDB) y resolvé los **8 ejercicios de SQL básico** de la **Parte 2** (SELECT/WHERE/ORDER BY, COUNT, MIN/MAX, AVG, normalización+nulos con COALESCE, DISTINCT/LIKE, atributo derivado con CASE, un INNER JOIN simple). Al final, la sección **📦 Entrega** genera automáticamente tu archivo `ejercicios/alumnos/<apellido>-<nombre>.txt` (motor usado + evidencia de que Northwind cargó + cuántos ejercicios corrieron y devolvieron resultado, **extraído automáticamente ejecutando tus queries — no se autoreporta**) y te indica cómo subirlo (commit + push + **PR nuevo** de esta clase). Reglas completas en [`ejercicios/README.md`](ejercicios/README.md).

> Las queries **no se autocorrigen** (las soluciones no se publican — el aprendizaje es pelearla). Silver es SQL-intensivo: estos patrones son exactamente los del DAG productivo `dag_crypto_silver.py`.

> **Una rama para siempre, un PR por clase**: tu rama `apellido-nombre` es la misma desde clase01; el PR es nuevo cada clase (el anterior ya se mergeó). Detalle en el [README raíz](../README.md).

### Paso 3 — Deploy del DAG productivo crypto

Al final del ejercicio.ipynb encontrás un cell con el comando para deployar el DAG productivo:

```bash
cp clase04/ejercicios/dag_crypto_silver.py stack/dags/02-silver/
```

Airflow detecta el archivo automáticamente (refresh cada 10s). Activalo en la UI y mirá los datos en `silver.crypto_markets` y `silver.quarantine_crypto_markets`.

> Filtrá por tag **`prod`** en la UI para ver solo los DAGs productivos (separa el DAG real del crypto de la escalera didáctica `silver_01_*` → `silver_02_*`).
>
> El DAG productivo aplica el **mismo patrón data contract** que `dag_crypto_bronze` — carga `crypto_markets.yaml`, construye `CryptoContract` con `build_pydantic_from_contract()` en runtime y separa filas válidas de inválidas (con `quarantine_reason` por fila). Para verlo en acción: en los logs de la task `clean_and_split` aparece `Contrato cargado: crypto_markets v1.0`.

### ⚠️ Si modificás el DAG productivo

Si tocás `clase04/ejercicios/dag_crypto_silver.py`, **acordate de re-copiar** al stack — sino Airflow corre la versión vieja:

```bash
cp clase04/ejercicios/dag_crypto_silver.py stack/dags/02-silver/
```

---

## 📚 El ejercicio en detalle (SQL básico — Northwind)

El ejercicio entregable (Paso 2) es [`ejercicios/ejercicio.ipynb`](ejercicios/ejercicio.ipynb). Resumen:

| Aspecto | Detalle |
|---|---|
| **Qué practicás** | Fundamentos de SQL que Silver usa todo el tiempo: filtrar, medir para *profiling* (`COUNT`/`MIN`/`MAX`/`AVG`), normalizar y limpiar nulos, derivar atributos con `CASE`, `DISTINCT` y un `JOIN` simple. |
| **Cómo está armado** | Un solo archivo: **Parte 1 — Setup** (carga Northwind, con datos sucios sembrados a propósito) + **Parte 2** con 8 ejercicios básicos (E1 SELECT/WHERE/ORDER BY · E2 COUNT · E3 MIN/MAX · E4 AVG · E5 normalización+nulos COALESCE · E6 DISTINCT/LIKE · E7 atributo derivado CASE · E8 INNER JOIN) + **📦 Entrega**. Podés cortar y volver. |
| **Dónde corre** | Postgres (si tenés el stack) **o** DuckDB (offline). La Parte 1 detecta auto cuál usar y carga Northwind. |
| **Entrega** | Sección **📦 Entrega** al final de `ejercicio.ipynb` → `.txt` en `ejercicios/alumnos/`. |

📖 **Reglas de entrega**: [`ejercicios/README.md`](ejercicios/README.md)

> Cada ejercicio incluye una nota **🔗 En Silver esto sería...** que conecta la técnica SQL con un caso real de la clase. No es SQL desconectado: es la herramienta concreta para construir Silver.

---

## ✅ Verificación end-to-end

Después de correr el pipeline Silver completo (DAG `crypto_silver` activado y triggered), deberías poder responder estas 3 queries:

```sql
-- 1. ¿Hay datos en silver?
SELECT COUNT(*) AS validos FROM silver.crypto_markets;
-- Esperado: > 0 (~50 filas por snapshot)

-- 2. ¿Cuántos fueron a quarantine y por qué?
SELECT quarantine_reason, COUNT(*) AS cantidad
FROM silver.quarantine_crypto_markets
GROUP BY 1
ORDER BY 2 DESC;
-- Esperado: pocos rechazos, motivos claros (ValidationError de Pydantic)

-- 3. ¿La tasa de éxito es razonable?
SELECT
  (SELECT COUNT(*) FROM silver.crypto_markets) AS validos,
  (SELECT COUNT(*) FROM silver.quarantine_crypto_markets) AS rechazados,
  ROUND(
    (SELECT COUNT(*) FROM silver.crypto_markets) * 100.0 /
    NULLIF((SELECT COUNT(*) FROM silver.crypto_markets) +
           (SELECT COUNT(*) FROM silver.quarantine_crypto_markets), 0),
    2
  ) AS tasa_exito_pct;
-- Esperado: tasa > 95% en datos crypto reales
```

Si las 3 queries devuelven valores razonables, tu pipeline Silver está **funcional + observable + auditable**.

---

## 🔮 Forward reference a Gold (clase 05)

Hasta acá tenemos `silver.crypto_markets` con datos limpios y validados (Pydantic + quarantine + audit metadata). En **clase 05** vamos a:

| Concepto | Qué construimos |
|---|---|
| **Star Schema** | Separar **dimensiones** (`dim_crypto`, `dim_tiempo`) de **hechos** (`fact_market_snapshot`). Modelado dimensional clásico de Kimball. |
| **ABT (Analytical Base Table)** | Tabla ancha con features derivadas (avg_price, volatility_category, market_cap_tier) lista para alimentar modelos de ML. |
| **SCD Tipo 2** | Historizar cambios en `dim_crypto` usando los campos del bloque `scd:` del YAML del contrato (`business_key`, `tracked_columns`, `effective_date`). Mismo contrato, otra capa. |
| **Integridad referencial** | Validar FKs antes de publicar a BI/ML — detectar fact rows huérfanos sin dimensión. |

> 🔁 **El círculo se cierra**: el `crypto_markets.yaml` que validó forma en Bronze (clase 03) y semántica en Silver (clase 04), ahora alimenta el modelado dimensional en Gold (clase 05). Un contrato, **tres capas**, tres responsabilidades.

---

## 🛠️ Troubleshooting

| Problema | Solución |
| :--- | :--- |
| El DAG no aparece en Airflow UI | Verificar que el archivo esté en `stack/dags/02-silver/`. Esperar 10-30s para que Airflow lo detecte. |
| `ImportError: pydantic` (en el DAG silver) | El módulo viene en el Dockerfile del stack. Si falla, rebuild: `docker compose down && docker compose up -d --build`. |
| El DAG corre pero `silver.crypto_markets` está vacío | Verificá que el DAG `crypto_bronze` (clase03) haya corrido antes y poblado `bronze.crypto_markets`. |
| Muchos registros van a quarantine | Mirá la tabla `silver.quarantine_crypto_markets` — el campo `quarantine_reason` te dice por qué fueron rechazados. |
| El DAG productivo no aplica el contract refactorizado | La copia en `stack/dags/02-silver/dag_crypto_silver.py` quedó desactualizada. Re-copiá: `cp clase04/ejercicios/dag_crypto_silver.py stack/dags/02-silver/` |
