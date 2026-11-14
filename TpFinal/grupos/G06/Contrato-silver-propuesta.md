**Contrato de datos silver - Propuesta inicial**

Propuesta para definir como vamos a organizar los datos en la capa Silver.

La idea se basa en consultas realizadas a la API historica de Open-Mateo para tres destinos de Argentina.

Describimos las variables seleccionadas, sus nombres originales, los nombres mejores , tipos de datos, unidades y algunos chequeos de calidad.

Queda pendiente chequear esta propuesta con el JSON de ejemplo del grupo y validadrla todos juntos.

**Destinos y periodo de tiempo usado**

- Purmamarca, Jujuy.
- San Carlos de Bariloche, Río Negro.
- Puerto Iguazú, Misiones.

Período consultado: desde el 12/11/2021 hasta el 07/11/2026.

Se obtuvieron 1822 registros diarios para cada destino. En total 5466 registros.

**Variables**

| Nombre original en la API | | Nombre en Silver | | Descripcion | | Unidad| 
|---| |---| |---| |---|
| `temperature_2m_min` | `temperatura_minima` | Temperatura mínima diaria a 2 metros | °C |
| `temperature_2m_mean` | `temperatura_media` | Temperatura media diaria a 2 metros | °C |
| `temperature_2m_max` | `temperatura_maxima` | Temperatura máxima diaria a 2 metros | °C |
| `precipitation_sum` | `precipitacion_mm` | Precipitación acumulada diaria | mm |
| `daylight_duration` | `duracion_luz_segundos` | Duración de la luz del día | segundos |
| `wind_gusts_10m_max` | `rafagas_viento_max_kmh` | Ráfagas máximas de viento a 10 metros | km/h |

**Tipos de datos**

| Campo en Silver | Tipo de dato |
|---|---|
| `destino` | VARCHAR |
| `fecha` | DATE |
| `temperatura_minima` | DECIMAL |
| `temperatura_media` | DECIMAL |
| `temperatura_maxima` | DECIMAL |
| `precipitacion_mm` | DECIMAL |
| `duracion_luz_segundos` | DECIMAL |
| `rafagas_viento_max_kmh` | DECIMAL |


**Clave de identificacion para cada registro**

Decidimos que la clave de identificacion se componga del "destino" y la "fecha". Estas variables permiten identificar un unico registro diario para cada destino.

**Zona horaria**

Hicimos las consultas con `timezone=auto`, para que Open-Meteo use la zona horaria de cada destino.

Pensamos dejar las fechas como las devuelve la API.

**Controles de calidad**

Hicimos algunos chequeos sobre los datos obtenidos:

- Datos faltantes: no se encontraron.
- Fechas duplicadas: no se encontraron.
- Temperaturas inconsistentes: no se encontraron. 
- Miramos los valores minimos y maximos de las variables para ver si habia valores raros

Estos controles son iniciales y pueden ampliarse al implementar Silver.

**Decisiones importantes**
- Si falta el destino o la fecha, descartamos el registro porque son valores necesarios para identificarlo.
- Si encontramos datos faltantes en las variables, vamos a contabilizarlos para ver cuantosregistros estan afectados. Si son pocos los registros con datos faltantes vamos a descartarlos. Si son muchos, completaremos los valores con algun criterio estadistico (media o mediana).
- Si hay valores inconsistentes, el registro se excluye de silver hasta revisarlo.
- Si encontramos registros duplicados (mismo destino y fecha) nos quedamos con uno solo, descartamos el duplicado. Si los dos registros tienen valores diferentes, lo marcamos para revisar.
- Los registros que descartamos, los datos faltantes, las inconsistencias y los valores NULL los vamos a contabilizar para tener un registro y poder medir la calidad de los datos.

**Segun las variables**

**precipitacion_mm:**

- No puede tener valores negativos, sino es considerado invalido y queda como NULL.
- Puede valer 0 (no hubo precipitaciones).

**duracion_luz_segundos:**

- No puede tener valores negativos.
- No puede superara los 86400 segundos (es decir las 24hs del dia)

**rafagas_viento_max_kmh:**
- No puede tener valores negativos.
- Puede valer 0 (no se registraron ráfagas de viento).

**Variables de temperatura (temperatura_minima, temperatura_media, temperatura_maxima):**
- Se debe cumplir que la temperatura mínima sea menor o igual a la media, y la media menor o igual a la máxima.

**Pasos a seguir**

- Comparar la propuesta con el JSON de ejemplo para tener un contrato DEFINITIVO.
- Confirmar los campos y tipos de datos
- Revisar y validar el contrato
- Ajustar la propuesta si es necesario antes de utilizarla en Gold
