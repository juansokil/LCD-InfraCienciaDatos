-- Schemas utilizados en la arquitectura Medallion. Corre solo la primera vez que se
-- inicializa el volumen del warehouse (docker compose up sobre volumen vacio).
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
