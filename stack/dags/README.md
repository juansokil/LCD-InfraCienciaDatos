# 🚀 Orquestación de Datos: Serie Progresiva de DAGs

Bienvenido al "motor" de nuestra plataforma. Esta carpeta contiene los **DAGs (Directed Acyclic Graphs)** organizados por capas arquitectónicas.

---

## 📂 Estructura de Carpetas

Hemos organizado los procesos siguiendo el ciclo de vida real del dato:

### 1️⃣ `01-bronze/` (Ingesta)

Procesos de extracción desde fuentes externas (CSV, JSON, APIs) hacia nuestra base de datos **`InfraCienciaDatos`**.

* **Misión**: Mover el dato crudo al esquema `bronze`.

### 2️⃣ `02-silver/` (Refinería)

Refinación y limpieza de datos.

* **Misión**: Filtrar, limpiar y normalizar datos desde `bronze` hacia el esquema `silver`.

### 3️⃣ `03-gold/` (Serving)

Agregaciones, KPIs y modelado analítico.

* **Misión**: Preparar "Datamarts" en el esquema `gold` para ser consumidos por herramientas de BI.

### 4️⃣ `20-tpFinal/` (Proyecto Integrador)

Contiene los DAGs maestros que orquestan el flujo completo Medallón de punta a punta.

---

## 🛠️ Configuración de Conexiones

Todos los DAGs están configurados para usar conexiones centralizadas en Airflow:

1. **`database`**: Conexión principal a nuestra base de datos de trabajo (`InfraCienciaDatos`).
    * *Nota: No hardcodear contraseñas, usar el `PostgresHook`.*
2. **`mssql`**: Conexión opcional para el sistema origen externo Microsoft.

---

## 💡 Mejores Prácticas Incluidas

* **Uso de Esquemas**: Implementación física de la arquitectura Medallón (`bronze`, `silver`, `gold`).
* **TaskFlow API**: Uso intensivo de decoradores `@dag` y `@task`.
* **Configuración desde .env**: Uso de variables de entorno para una gestión limpia.

**¡A orquestar se ha dicho! 🚀🫡**
