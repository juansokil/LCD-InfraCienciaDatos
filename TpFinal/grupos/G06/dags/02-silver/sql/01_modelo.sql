-- Capa Silver 
-- Creacion de la tabla con los datos meteorologicos diarios 
-- Hay que revisarlo y hacer cambios una vez que tengamos el JSON definitivo de Bronze

CREATE SCHEMA IF NOT EXISTS silver;
CREATE TABLE IF NOT EXISTS silver.clima_diario (
    destino VARCHAR(100) NOT NULL,
    fecha DATE NOT NULL,
    temperatura_minima DECIMAL,
    temperatura_media DECIMAL,
    temperatura_maxima DECIMAL,
    precipitacion_mm DECIMAL,
    duracion_luz_segundos DECIMAL,
    rafagas_viento_max_kmh DECIMAL,

    PRIMARY KEY (destino, fecha)
);

-- Tabla Silver para los datos meteorologicos horarios
CREATE TABLE IF NOT EXISTS silver.clima_horario (
    destino VARCHAR(100) NOT NULL,
    fecha_hora TIMESTAMPTZ NOT NULL,
    temperatura_2m DECIMAL,
    precipitacion_mm DECIMAL,
    rafagas_viento_kmh DECIMAL,

    PRIMARY KEY (destino, fecha_hora)
);