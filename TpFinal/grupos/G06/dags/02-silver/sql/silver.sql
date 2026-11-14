-- Capa Silver 
-- Idea inicial de la tabla con los datos metereologicos 
-- Hya que revisarlo y hacer cambios una vez que tengamos el JSON definitivo de Bronze


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