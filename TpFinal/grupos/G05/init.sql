-- ==================================================
-- INICIALIZACIÓN DE BASE DE DATOS - LIC. CIENCIA DE DATOS
-- ==================================================

-- 1. Esquema Origen (Donde caen los datos crudos del sistema externo)
CREATE SCHEMA IF NOT EXISTS "InfraCienciaDatos";

-- 2. Esquemas de Arquitectura Medallón (Procesamiento ELT)
CREATE SCHEMA IF NOT EXISTS "bronze";
CREATE SCHEMA IF NOT EXISTS "silver";
CREATE SCHEMA IF NOT EXISTS "gold";

-- Comentario pedagógico:
-- En 'InfraCienciaDatos' simulamos el sistema origen.
-- En 'bronze', 'silver' y 'gold' realizamos la refinación de los datos.
