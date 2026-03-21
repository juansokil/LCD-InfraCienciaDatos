# Clase 07: Ingenieria de Datos — Data Pipelines - Arquitectura Medallion

## 🎯 Objetivos de la Clase
- Entender que es la **Ingenieria de Datos** y los roles en el ecosistema de datos.
- Comprender la jerarquia del dato: del dato crudo a la **Base de Datos**.
- Conocer los niveles de **Modelado de Datos** (conceptual, logico, fisico).
- Entender los componentes de un **Data Pipeline** profesional.
- Comprender la **Arquitectura Medallion** (Bronze, Silver, Gold).
- Realizar tu primer **push con Git** al repositorio de la materia.

---

## 🏗️ Estrategia de Trabajo: Resiliencia y Portabilidad
1. **Postgres (Eje Central)**: base de datos de persistencia profesional.
2. **DuckDB (Plan B / Fallback)**: motor analitico de contingencia para trabajar sin Docker.

---

## 🚀 Ejercicio: Mi primer push con Git

El ejercicio completo esta en [`ejercicio/ejercicio.ipynb`](ejercicio/ejercicio.ipynb). Resumen de los pasos:

**Paso 0 — Registro en el Onboarding**
1. Ir a [https://asistencia-api-unsam-production.up.railway.app/unirse](https://asistencia-api-unsam-production.up.railway.app/unirse)
2. Completar con tu Nombre, Email y **Usuario de GitHub**.
3. Codigo de clase: `UNSAM-2026-1C`.
4. Revisar tu email y aceptar la invitacion de GitHub.

> **Nota**: El repositorio es publico (lo podes ver), pero solo podes subir contenido (push) si aceptaste la invitacion.

**Paso 1 — Clonar el repositorio**
```bash
git clone https://github.com/juansokil/LCD-InfraCienciaDatos.git
cd LCD-InfraCienciaDatos
```

**Paso 2 — Crear tu rama personal** (nunca trabajamos directo en `main`)
```bash
git checkout -b registro-apellido-nombre
```
Por ejemplo: `git checkout -b registro-garcia-juan`

**Paso 3 — Realizar el Ejercicio**

Abrir `clase07/ejercicio/ejercicio.ipynb`, completar tus datos en la celda indicada y ejecutarla. Esto genera tu archivo en la carpeta `alumnos/`.

**Paso 4 — Commit y Push**

Volvé a la terminal (que debería estar en la carpeta `LCD-InfraCienciaDatos/`) y ejecutá:

```bash
git add clase07/ejercicio/alumnos/
git commit -m "registro: Garcia Juan"
git push origin registro-garcia-juan
```

> **Importante**: Reemplaza `Garcia Juan` y `garcia-juan` con **tu nombre real** en ambos comandos.

> **Nota**: Si es la primera vez que pusheas esta rama, Git te va a pedir que ejecutes:
> `git push --set-upstream origin registro-garcia-juan`
> Esto es normal, solo pasa la primera vez.

**Paso 5 — Abrir el Pull Request**
1. Ir a [github.com/juansokil/LCD-InfraCienciaDatos](https://github.com/juansokil/LCD-InfraCienciaDatos).
2. Click en el boton **"Compare & pull request"**.
3. Crear el PR con titulo: `registro-garcia-juan`.
4. Luego se revisa y aprueba el merge a `main`.
---
