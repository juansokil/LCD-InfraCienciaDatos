-- 1. Esquema Origen (Donde caen los datos crudos del sistema externo)
CREATE SCHEMA IF NOT EXISTS "InfraCienciaDatos";

-- 2. Esquemas de Arquitectura Medallón (Procesamiento ELT)
CREATE SCHEMA IF NOT EXISTS "bronze";
CREATE SCHEMA IF NOT EXISTS "silver";
CREATE SCHEMA IF NOT EXISTS "gold";