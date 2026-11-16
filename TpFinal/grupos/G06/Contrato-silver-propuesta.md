Contrato de datos silver 

Propuesta para definir cómo vamos a organizar los datos

La idea se basa en consultas realizadas a la API histórica de Open-Meteo para tres destinos de Argentina.

Describimos las variables seleccionadas, sus nombres originales, los nombres nuevos en español, tipos de datos, unidades y algunos chequeos de calidad.

**Destinos y período de tiempo usado**

- Purmamarca, Jujuy.
- San Carlos de Bariloche, Río Negro.
- Puerto Iguazú, Misiones.

Los datos se obtienen mediante consultas a la API histórica de Open-Meteo.

La cantidad de registros puede variar según el período consultado y los datos disponibles en Bronze. En la ejecución verificada el 15/11/2026 se procesaron 6.423 registros en Silver.

**Clave de identificación**

Cada registro representa la información meteorológica correspondiente a un destino en una fecha determinada.

La clave lógica está compuesta por:
- `destino`
- `fecha`

**Variables**

| Nombre original en la API | Nombre en Silver | Descripción | Unidad |
|---|---|---|---|
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


**Zona horaria**

Hicimos las consultas con `timezone=auto`, para que Open-Meteo use la zona horaria de cada destino.

Las fechas se conservan según los valores devueltos por la API y se convierten al tipo DATE durante la transformación a Silver.

**Reglas de transformación y limpieza**

- Se pasa la fecha al formato DATE y las variables meteorológicas a DECIMAL.

- Se controlan los valores de las variables para identificar datos inválidos.

- Los valores negativos de precipitación y ráfagas se reemplazan por NULL. Lo mismo ocurre con la duración de luz cuando está fuera del rango de 0 a 86.400 segundos.

- Se verifica que la temperatura mínima no sea mayor que la media y que la media no sea mayor que la máxima. Si no se cumple esta condición, las tres temperaturas quedan en NULL.

- Cuando hay más de un registro para el mismo destino y fecha, nos quedamos con el que tiene más variables con datos. Si hay un empate, se prioriza el de carga más reciente.


**Reglas por variables**

**precipitacion_mm:**

- No puede tener valores negativos, si no, se considera inválido y queda como NULL.
- Puede valer 0 (no hubo precipitaciones).

**duracion_luz_segundos:**

- No puede tener valores negativos.
- No puede superar los 86.400 segundos (es decir, las 24 h del día)

**rafagas_viento_max_kmh:**
- No puede tener valores negativos.
- Puede valer 0 (no se registraron ráfagas de viento).

**Variables de temperatura (temperatura_minima, temperatura_media, temperatura_maxima):**
- Se debe cumplir que la temperatura mínima sea menor o igual a la media, y la media menor o igual a la máxima.

**Controles de Calidad**
Se realizan controles sobre:
- Cantidad total de registros.
- Valores nulos en las variables meteorológicas.
- Duplicados por destino y fecha.
- Orden lógico de las temperaturas.
- Valores negativos o fuera de los rangos definidos para las variables correspondientes.

**Resultados de nuetra ejecución**
En la ejecución comprobada del 15/11/2026 se obtuvieron los siguientes resultados:

| Control | Resultado |
|---|---:|
| Registros en silver.clima_limpio| 6423 |
| Registros en silver.clima_diario| 6423 |
| Registros con temperatura mínima nula | 0 |
| Registros con temperatura máxima nula | 0 |
| Registros con precipitación nula | 0 |
| Registros con ráfagas de viento nulas | 0 |
| Registros con al menos un valor nulo entre esas variables | 0 |
| Posibles duplicados por destino y fecha | 0 |
| Temperaturas inconsistentes | 0 |
| Registros con valores fuera de los rangos controlados | 0 |