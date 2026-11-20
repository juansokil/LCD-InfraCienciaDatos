-- =============================================================================
-- TP Final G11 - Inicializacion del warehouse
-- =============================================================================
-- Corre UNA vez, cuando el contenedor data_warehouse arranca con el volumen
-- vacio (primer `docker compose up`, o despues de `docker compose down -v`).
--
-- Solo crea los schemas de la arquitectura medallion. Las TABLAS las crea cada
-- DAG con CREATE TABLE IF NOT EXISTS: cada capa es duena de sus tablas, y
-- cambiar una tabla no obliga a borrar el volumen para que init.sql vuelva a
-- correr.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;   -- crudo, tal cual lo entrega la API
CREATE SCHEMA IF NOT EXISTS silver;   -- limpio, validado, una fila por sismo
CREATE SCHEMA IF NOT EXISTS gold;     -- modelo estrella + vistas para el dashboard
