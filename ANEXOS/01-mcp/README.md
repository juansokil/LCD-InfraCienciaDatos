# 🔌 Anexo 01 · MCP para Data Engineering

> **Material optativo.** No se evalúa. Es para que te lo lleves.
>
> Escrito en **octubre de 2026**. El servidor de Airflow está **probado de punta
> a punta** contra el stack del curso (Airflow 3.1.5): ver [Probalo](#️-probalo-vos-sin-instalar-ningún-cliente).
> Los de Postgres y MLflow están verificados contra su documentación, no corridos.

---

## 🤔 El problema que resuelve

Te llega un mensaje un lunes a la mañana: *"el dashboard está vacío"*. Lo que
hacés es siempre lo mismo:

1. Abrís Airflow y mirás si el DAG corrió.
2. Encontrás el run que falló y abrís el log de la task.
3. Leés el traceback.
4. Vas a Postgres y contás filas en `bronze`, `silver` y `gold` para ver dónde se
   cortó.

Son cuatro herramientas distintas, cuatro ventanas, y diez minutos antes de
empezar a pensar. Nada de eso es el trabajo difícil: el trabajo difícil es la
hipótesis de qué pasó.

**MCP** (*Model Context Protocol*) es un protocolo abierto para que un asistente
de IA haga esos cuatro pasos por vos y te traiga el material ya junto, para que
vos pongas la hipótesis.

---

## 🧩 Qué es, técnicamente

Antes de MCP, conectar *N* asistentes con *M* herramientas eran *N × M*
integraciones a medida. MCP define **un solo contrato**: una herramienta publica
un **servidor MCP**, y cualquier cliente que hable el protocolo lo usa sin saber
nada de esa herramienta en particular.

```mermaid
graph LR
    C["💬 Cliente MCP<br/>(Claude Code, Cursor,<br/>tu propia app)"] -->|protocolo MCP| S1["🔌 Servidor<br/>Airflow"]
    C -->|protocolo MCP| S2["🔌 Servidor<br/>Postgres"]
    C -->|protocolo MCP| S3["🔌 Servidor<br/>MLflow"]
    S1 --> A["⚙️ API REST<br/>de Airflow"]
    S2 --> P["🐘 PostgreSQL"]
    S3 --> M["📊 MLflow"]

    style C fill:#e1f5ff,stroke:#01579b,color:#1a1a1a
    style S1 fill:#f3e5f5,stroke:#4a148c,color:#1a1a1a
    style S2 fill:#f3e5f5,stroke:#4a148c,color:#1a1a1a
    style S3 fill:#f3e5f5,stroke:#4a148c,color:#1a1a1a
    style A fill:#fef9c3,stroke:#fbc02d,color:#1a1a1a
    style P fill:#e8f5e9,stroke:#1b5e20,color:#1a1a1a
    style M fill:#fef9c3,stroke:#fbc02d,color:#1a1a1a
```

Si ya trabajaste con bases, la analogía es **ODBC/JDBC**: tu programa no habla
"PostgreSQL", habla "driver", y abajo puede haber cualquier motor. MCP es eso,
pero para que un modelo use herramientas.

Un servidor MCP expone tres cosas:

| Qué | Para qué | Ejemplo en Airflow |
| :--- | :--- | :--- |
| **Tools** | funciones que el asistente puede ejecutar | `listar DAGs`, `traer el log de una task` |
| **Resources** | datos que puede leer | la config del scheduler, la lista de providers |
| **Prompts** | plantillas de tareas comunes | "diagnosticá este DAG run" |

---

## 🧪 Los tres del stack del curso

### ⚙️ Airflow

**Cuál usar: [`astro-airflow-mcp`](https://github.com/astronomer/agents/tree/main/astro-airflow-mcp)**, de Astronomer.

> [!IMPORTANT]
> Hay otro servidor muy difundido, `mcp-server-apache-airflow`, que apunta por
> defecto a la **API v1**. Airflow 3 cambió a `/api/v2`, así que **contra el stack
> de este curso no te va a funcionar**. El de Astronomer detecta la versión sola
> y usa el endpoint que corresponda.

```json
{
  "mcpServers": {
    "airflow": {
      "command": "uvx",
      "args": ["astro-airflow-mcp", "--transport", "stdio"],
      "env": {
        "AIRFLOW_API_URL": "http://localhost:8080",
        "AIRFLOW_USERNAME": "admin",
        "AIRFLOW_PASSWORD": "admin",
        "AF_READ_ONLY": "true"
      }
    }
  }
}
```

Trae tres herramientas que valen por sí solas — `explore_dag`,
`diagnose_dag_run` y `get_system_health` — más otras treinta para DAGs, runs,
tasks, pools, variables y conexiones. Las credenciales de las conexiones **no**
las devuelve, a propósito.

`AF_READ_ONLY=true` es el seguro. **Arrancá siempre así.** Un detalle que
conviene saber, porque lo probamos: las herramientas de escritura **siguen
apareciendo** en la lista (`trigger_dag`, `pause_dag`, `delete_dag_run`...), así
que el asistente las ve y puede intentarlas. Lo que pasa es que el servidor las
**rechaza al ejecutarlas**:

```
"error": "Operation 'DELETE dags/.../dagRuns/...' is blocked:
          running in read-only mode ($AF_READ_ONLY=true).
          Only read operations are allowed."
"error_type": "ReadOnlyError"
```

O sea: la protección es real, pero no funciona escondiendo botones sino negando
la operación. Si ves al asistente intentar un `trigger_dag`, no te asustes: no
lo pudo hacer.

---

### 🐘 PostgreSQL

**Cuál usar: [`crystaldba/postgres-mcp`](https://github.com/crystaldba/postgres-mcp)** (Postgres MCP Pro).

> [!WARNING]
> El servidor de referencia de Anthropic (`@modelcontextprotocol/server-postgres`)
> **está archivado**: salió de la lista de servidores oficiales y vive en el repo
> `servers-archived`. Vas a encontrar cientos de tutoriales que todavía lo
> recomiendan. No lo uses para nada nuevo.

Además de consultar, analiza: corre `EXPLAIN`, detecta índices que faltan y mide
el costo de una query. Tiene un **modo restringido** que limita a lectura y pone
un tope de tiempo de ejecución, para que una consulta pesada no te tire la base.

Contra el warehouse del curso, la cadena de conexión es la de siempre:
`postgresql://admin:admin@localhost:5432/InfraCienciaDatos`.

---

### 📊 MLflow

**Cuál usar: [`mlflow-mcp`](https://pypi.org/project/mlflow-mcp/)** (v0.4.1, agosto 2026).

Pide **MLflow ≥ 3.4.0**, que es exactamente lo que pinea el stack del curso.

```json
{
  "mcpServers": {
    "mlflow": {
      "command": "uvx",
      "args": ["mlflow-mcp"],
      "env": { "MLFLOW_TRACKING_URI": "http://localhost:5000" }
    }
  }
}
```

Lista experimentos, compara runs, lee métricas y artefactos, y maneja el Model
Registry.

> [!CAUTION]
> **No es read-only y no tiene modo seguro**: puede registrar modelos, mover
> aliases, promover a producción y **borrar runs y experimentos**. Apuntalo a tu
> MLflow local, nunca al de un equipo.

---

## 🚨 Lo que hay que entender antes de enchufar nada

Un servidor MCP con credenciales de escritura **es** acceso de escritura. Si le
das al asistente un usuario que puede hacer `DROP TABLE`, el asistente puede
hacer `DROP TABLE`. No hay una capa mágica en el medio que lo impida.

Cuatro reglas que valen siempre:

1. **Read-only por defecto.** `AF_READ_ONLY`, el modo restringido de Postgres, un
   usuario de base con permisos de solo lectura. El permiso de escritura se
   habilita para una tarea puntual y se vuelve atrás.
2. **Un usuario de base aparte para el asistente.** No el `admin`. Uno con
   `GRANT SELECT` sobre los schemas que necesita y nada más.
3. **Nunca apuntes a producción desde tu asistente personal.** El riesgo no es
   solo que escriba: es que *lea* datos que no deberían salir de ahí.
4. **Lo que entra al contexto, salió de tu base.** Si el servidor devuelve filas,
   esas filas viajan al modelo. Con datos personales o sensibles, eso es una
   decisión que no se toma sola.

> [!TIP]
> La regla práctica: configurá cada servidor como si el asistente fuera un
> pasante al que le das acceso el primer día. Lectura, un entorno de prueba, y
> nada que no puedas revertir.

---

## ▶️ Probalo vos, sin instalar ningún cliente

En esta carpeta hay un script que levanta el servidor y le habla directamente.
**No necesitás Claude Code ni Cursor**: un servidor MCP por stdio recibe JSON por
la entrada estándar y contesta JSON por la salida, así que se lo puede manejar
desde Python. Sirve, además, para sacarle la magia al asunto.

```bash
# con el stack levantado (docker compose up -d desde stack/)
python ANEXOS/01-mcp/probar_mcp.py
```

Hace seis pasos: `initialize`, `tools/list`, una llamada liviana, el listado de
DAGs, una herramienta que encadena varias llamadas, y una prueba del seguro de
solo lectura. Salida real contra el stack del curso:

```
1. initialize
   servidor:  Airflow MCP Server v3.4.8
   protocolo: 2025-06-18

2. tools/list -> 34 herramientas
   - list_connections             Get connection configurations for external systems
   - get_airflow_version          Get version information for the Airflow instance.
   ...

3. tools/call get_airflow_version
   { "version": "3.1.5", ... }

4. tools/call list_dags
   16 DAGs en tu Airflow:
     [pausado] bronze_01_simple
     [activo ] crypto_bronze
     [activo ] crypto_gold
     [activo ] crypto_ml
     [activo ] crypto_silver
     ...

5. tools/call get_system_health
   { "version": {...}, "import_errors": {"count": 0},
     "overall_status": "healthy" }

6. El seguro: llamo a delete_dag_run con ids inventados
   BLOQUEADA. El servidor contesto ReadOnlyError sin tocar Airflow.
```

> [!NOTE]
> La primera corrida tarda: `uvx` baja el paquete y sus dependencias. El paso 5
> usa una herramienta "consolidada" que encadena varias llamadas a la API y
> puede tomarse un rato; si no contesta, no invalida nada.

### Y ahora enchufalo a tu asistente

En esta carpeta está el [`.mcp.json`](.mcp.json) listo. Dos formas de usarlo:

**Por proyecto** — copialo a la raíz del repo donde trabajes:

```bash
cp ANEXOS/01-mcp/.mcp.json .
```

La próxima vez que abras ese proyecto, el cliente te va a pedir que apruebes el
servidor. Desde ahí podés preguntarle cosas como:

- *¿Qué DAGs hay y cuál fue el último que falló?*
- *Traeme el log de la última corrida de `crypto_silver`.*
- *¿Hace cuánto que no corre `crypto_gold`?*

**Por usuario** — con `claude mcp add`, y queda disponible en todos tus
proyectos, con los mismos valores del JSON.

Vas a ver que el asistente encadena varias llamadas: lista, filtra, abre el run,
baja el log. Eso es lo que te ahorra. **Lo que no te ahorra es saber qué
significa el error**, y para eso están las seis clases de atrás.

---

## 🧭 Un matiz que confunde

MLflow 3.15 sumó una función llamada **MCP Registry**, y no es un servidor MCP de
MLflow. Es lo contrario: un **catálogo donde registrás servidores MCP**, con
versionado, aliases (`@production`, `@staging`) y descubrimiento automático de las
herramientas que expone cada uno. Es para equipos que ya tienen muchos servidores
y necesitan gobernarlos.

Resumido:

| | Qué es |
| :--- | :--- |
| `mlflow-mcp` | un servidor MCP **para hablar con** MLflow |
| MLflow MCP Registry | un catálogo **de** servidores MCP, que vive adentro de MLflow |

---

## 📚 Para seguir

- [Documentación oficial del protocolo](https://modelcontextprotocol.io) — la especificación y los SDK.
- [Servidores de referencia](https://github.com/modelcontextprotocol/servers) — los que mantiene el proyecto: Filesystem, Git, Fetch, Memory, Time.
- [`astronomer/agents`](https://github.com/astronomer/agents) — el monorepo donde vive el MCP de Airflow.
- [MCP Registry de MLflow](https://mlflow.org/docs/latest/genai/mcp-registry/) — si te interesa el lado de gobierno.

> [!NOTE]
> El protocolo se mueve rápido: la versión de julio de 2026 lo pasó de
> bidireccional con estado a **sin estado**. Si leés algo de 2024 o 2025, puede
> estar describiendo otra cosa.
