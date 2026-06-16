# Entrega del TP — Branch + PR (G04)

Todo lo necesario para abrir la entrega en GitHub. Copiá y pegá.

---

## 1. Título exacto del PR

```
TP Final - G04 - CityBikes
```

---

## 2. Body del PR (copiar y pegar)

**Integrantes**
- Di Lacio, Lautaro — @DiLacio-Lautaro
- Lust, Tobias — @lust-tobias
- Melograna, Federico — @Melograma-Federico
- Quinteros Amicone, Lautaro — @Quinteros-Lautaro
- Rial, Alejo — @Alejo-Rial
- Romero, Manuel — @romero-rodrigo

**API elegida**
- CityBikes — https://api.citybik.es/v2 (sin autenticación; refresh cada 2–5 min)
- Redes trackeadas: **Latinoamérica Sur** — ~20 redes de 6 países (Argentina, Brasil, Chile, Colombia, Ecuador, Perú)

**Idea Gold (pregunta de negocio)**
¿Qué estaciones se saturan o se quedan sin bicis, y a qué horas del día? El dashboard sobre las tablas Gold muestra KPIs en vivo, mapa de disponibilidad, patrón de ocupación por hora, ranking de estaciones críticas y comparación entre ciudades.

---

## 3. Comandos de git (branch + primer push)

```bash
# Pararse en main actualizado
git checkout main && git pull

# Crear la branch del grupo
git checkout -b tp-final/G04

# Agregar la carpeta del grupo
git add TpFinal/grupos/G04/

# Commit
git commit -m "tp-final/G04: pipeline CityBikes (Bronze/Silver/Gold) + dashboard + docs"

# Push (crea la branch en el remoto)
git push -u origin tp-final/G04
```

---

## 4. Abrir el PR

1. Entrá al repo en GitHub → aparece el aviso para abrir PR desde `tp-final/G04` hacia `main`.
2. Poné el **título exacto** del punto 1 y el **body** del punto 2.
3. Abrilo como **draft** (Pull Request en borrador) mientras siguen trabajando.

---

## 5. Entrega final (hasta 17-06-26 23:59)

En el PR, hacer click en **"Ready for review"**. Esa acción es la entrega formal.

> Después: presentación oral el **18-06-26** (5–6 min, hasta 10). Tener el stack levantado antes para la demo del dashboard.

---

## Checklist antes de marcar "Ready for review"

- [ ] `docker compose up` levanta los 4 servicios sin error
- [ ] Los 3 DAGs aparecen activos (no en pausa) en Airflow
- [ ] El dashboard (8501) muestra datos en Gold tras ~15 min
- [ ] README con integrantes, API, modelo de datos y cómo levantar — ✅ listo
- [ ] Presentación descargable (PDF/PPTX) subida al campus
- [ ] PR con título y body correctos, marcado "Ready for review"
