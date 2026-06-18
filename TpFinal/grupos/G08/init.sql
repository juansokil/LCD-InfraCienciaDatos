-- Este archivo se ejecuta automaticamente solo la primera vez que Postgres
-- inicializa un volumen vacio. Los schemas se crean dentro de la base indicada
-- por POSTGRES_DB, definida en .env como SOURCE_DB_NAME.
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
