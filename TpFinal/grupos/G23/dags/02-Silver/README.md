# Silver - EcoBici Buenos Aires

## Objetivo

La capa Silver toma los datos crudos almacenados en Bronze y genera una versión limpia y validada para ser utilizada posteriormente por la capa Gold.

Tabla principal:

silver.ecobici_stations

Tabla de cuarentena:

silver.ecobici_stations_quarantine

---

## Transformaciones realizadas

### 1. Lectura desde Bronze

Se leen los registros desde:

bronze.ecobici_stations_raw

---

### 2. Conversión de tipos

Se convierten los siguientes campos a tipos adecuados:

Timestamps:

- ingested_at
- station_timestamp
- last_updated

Numéricos:

- latitude
- longitude
- free_bikes
- empty_slots
- slots
- normal_bikes

Booleanos:

- is_renting
- is_returning
- virtual

---

### 3. Limpieza de texto

Se normalizan campos de texto eliminando espacios duplicados y espacios al inicio o final:

- station_name
- address
- source
- network_id
- network_name
- station_id
- station_uid

---

### 4. Validaciones

Se aplican las siguientes reglas de calidad:

Campos obligatorios:

- snapshot_id
- ingested_at
- source
- network_id
- station_id
- station_name
- latitude
- longitude
- free_bikes
- empty_slots
- station_timestamp
- last_updated
- address
- slots
- normal_bikes

Valores negativos:

- free_bikes >= 0
- empty_slots >= 0
- slots >= 0
- normal_bikes >= 0

Coordenadas válidas para Buenos Aires:

- latitude entre -35 y -34
- longitude entre -59 y -58

Duplicados:

- snapshot_id + station_id

---

### 5. Cuarentena

Los registros que incumplen alguna validación son enviados a:

silver.ecobici_stations_quarantine

Motivos posibles:

- MISSING_CRITICAL_FIELDS
- NEGATIVE_VALUES
- INVALID_COORDINATES
- DUPLICATE_RECORD

Además se registra:

- quarantine_reason
- quarantined_at

---

### 6. Métricas generadas

Se crean métricas adicionales para análisis posteriores.

total_capacity

Capacidad total de la estación.

total_capacity = slots

occupancy_ratio

Porcentaje de bicicletas disponibles respecto de la capacidad total.

occupancy_ratio = free_bikes / total_capacity

---

### 7. Auditoría

Se agrega:

cleaned_at

Fecha y hora en que el registro fue procesado por Silver.

---

## Resultado

La tabla silver.ecobici_stations contiene registros limpios, tipados, validados y enriquecidos listos para ser consumidos por la capa Gold.