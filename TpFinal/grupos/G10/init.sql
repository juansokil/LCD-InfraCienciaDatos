-- LogiWeather - Inicialización del Data Warehouse
-- TP Final - Grupo 10

-- Bronze: datos originales de Open-Meteo
CREATE SCHEMA IF NOT EXISTS bronze;

-- Silver: pronósticos limpios y normalizados
CREATE SCHEMA IF NOT EXISTS silver;

-- Gold: alertas e indicadores de negocio
CREATE SCHEMA IF NOT EXISTS gold;
