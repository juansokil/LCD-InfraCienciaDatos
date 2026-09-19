# Guia de Git para el TP Final

> Esta guia complementa al [`README.md`](README.md) del TP. Cubre los conceptos de Git y GitHub que importan para entregar bien el TP, y los errores que vimos aparecer mas seguido en cuatrimestres anteriores.

---

## 1. Para que sirve esta guia

Durante el desarrollo del TP suelen aparecer **errores recurrentes de Git/GitHub** que no son del codigo sino del flujo:

- Crear la branch desde la rama equivocada y arrastrar archivos viejos al PR.
- Editar archivos desde el boton "Edit" de GitHub web y terminar trabajando en un fork sin saber.
- Commits firmados como "Tu Nombre" porque `git config` quedo sin setear.
- Confundir Issue con PR, branch con fork, draft con final.

Esta guia explica los conceptos minimos para evitarlos. **No es una guia general de Git** — es lo que necesitan saber para que el TP Final entregue limpio y se pueda evaluar.

---

## 2. Conceptos en 1 minuto

| Concepto | Que es | Cuando lo usas en el TP |
|---|---|---|
| **Repo** | Un proyecto en GitHub. Tiene archivos, historia, branches. | El repo del curso es `juansokil/LCD-InfraCienciaDatos`. |
| **Branch** (rama) | Una linea de trabajo paralela dentro de un repo. | Cada grupo tiene la suya: `tp/G<NN>`. |
| **Commit** | Una "foto" de los cambios en un momento del tiempo, con un mensaje. | Cada vez que terminas algo, haces un commit. |
| **Push** | Mandar tus commits locales a GitHub. | Despues de cada commit (o varios), `git push`. |
| **Pull** | Traer commits de GitHub a tu maquina. | Antes de empezar a trabajar y antes de cada push. |
| **`main`** | La branch principal del repo. Lo que esta en `main` es "lo oficial". | La branch del grupo se crea **siempre desde `main`** recien actualizado. |
| **PR** (Pull Request) | Propuesta de mergear los commits de una branch a otra. Tiene codigo, comentarios, reviewers. | El TP se entrega como PR-draft de `tp/G<NN>` contra `main`. |
| **Issue** | Un post de discusion en GitHub. **No lleva codigo.** Sirve para preguntas, bugs, propuestas. | Opcional para dudas conceptuales sueltas. |
| **Fork** | Una **copia completa** del repo bajo tu cuenta personal. | **No se usa en el TP**. Detalle abajo. |
| **Draft PR** | Un PR marcado como "en progreso". Sigue siendo publico y muestra el codigo, pero indica "todavia no esta para revisar". | Asi se mantiene el PR desde el dia 1 hasta la entrega. |

### Repo del curso vs fork — diferencia clave

```
juansokil/LCD-InfraCienciaDatos                       ← repo del curso (donde se evalua)
    │
    │  (alguien aprieta "Fork" en GitHub o GitHub lo crea automatico)
    ▼
tu-usuario/LCD-InfraCienciaDatos                      ← fork: copia bajo tu cuenta personal
```

Son **dos repos fisicamente distintos**. Lo que esta en uno no esta en el otro automaticamente. **En este curso el flujo correcto es trabajar directo en el repo del curso** (todos son colaboradores invitados con permisos de escritura). No hace falta usar fork.

---

## 3. Setup inicial (antes de tocar el TP)

### 3.1. Configurar tu identidad de Git

Cada commit lleva el nombre y email de quien lo hizo. Si no configuras esto, los commits aparecen como "Tu Nombre" sin email, o con el usuario por defecto del sistema. Eso despues no se ve quien aporto que.

Una vez por maquina:

```bash
git config --global user.name "Tu Nombre Real"
git config --global user.email "tu-email@unsam.edu.ar"
```

Verificar:

```bash
git config --global user.name
git config --global user.email
```

> **Importante para trabajo grupal**: cada integrante del grupo configura sus propios datos en su propia maquina. Asi en el git log se ve quien hizo cada commit.

### 3.2. Clonar el repo del curso (no un fork)

En un lugar limpio de la maquina (Desktop, Documents, etc.):

```bash
git clone https://github.com/juansokil/LCD-InfraCienciaDatos.git
cd LCD-InfraCienciaDatos
```

Si ya lo tienen clonado de otras clases, basta con actualizar:

```bash
git checkout main
git pull origin main
```

---

## 4. Flujo del TP paso a paso

### Regla de oro: SIEMPRE crear la branch desde `main` recien actualizado

Esto es lo que evita la mitad de los problemas que vimos en cuatrimestres anteriores. Antes de hacer cualquier cosa relacionada al TP:

```bash
git checkout main
git pull origin main
```

Asi te aseguras de que tu branch nueva parte del estado mas actual del curso, sin arrastrar commits viejos de tu rama personal o de otras clases.

### Paso a paso completo

```bash
# 1. Posicionarte en main y actualizar
git checkout main
git pull origin main

# 2. Crear la branch del grupo (despues de que el docente te asigne el numero G<NN>)
git checkout -b tp/G07

# 3. Crear la carpeta del grupo y copiar el README template
mkdir -p TpFinal/grupos/G07
cp TpFinal/grupos/G00/README.md TpFinal/grupos/G07/README.md

# 4. Editar el README con datos del grupo (integrantes, API, idea Gold)
# (con VS Code, nano, o el editor que prefieran)

# 5. Primer commit
git add TpFinal/grupos/G07/
git commit -m "tp/G07: setup inicial (API: <X>)"

# 6. Push (la primera vez con -u para asociar la branch local con la remota)
git push -u origin tp/G07
```

GitHub te va a responder con un link para abrir el PR:

```
remote: Create a pull request for 'tp/G07' on GitHub by visiting:
remote:      https://github.com/juansokil/LCD-InfraCienciaDatos/pull/new/tp/G07
```

Click ahi, completas titulo (`TP Final - G07 - <API>`) y body (integrantes + API + idea Gold), y eliges **"Create draft pull request"** (la flechita ▼ al lado del boton verde).

A partir de ahi, cada `git push` actualiza el PR automaticamente.

---

## 5. Trabajo en equipo sobre la misma branch

Cuando son varios integrantes commiteando a la misma branch, hay una regla simple: **`git pull --rebase` antes de cada push**.

### Por que? El problema

```
Alice empieza a trabajar:
   commit A (Alice)
   commit B (Alice)
   git push origin tp/G07          ✓

Mientras tanto Bob trabaja en otra computadora:
   git pull origin tp/G07           ← trae A y B
   commit C (Bob)
   commit D (Bob)
   git push origin tp/G07          ✓

Alice quiere pushear mas:
   commit E (Alice)
   git push origin tp/G07          ❌ ERROR: tu branch local esta atras

   → tiene que hacer:
   git pull --rebase origin tp/G07  ← trae C y D, pone E despues
   git push origin tp/G07          ✓
```

### El comando clave

Antes de hacer `git push`:

```bash
git pull --rebase origin tp/G07
```

Eso trae los commits que otros pushearon mientras vos trabajabas, y pone tus commits despues de los de ellos. Despues sí podes hacer push tranquilo.

### Conflictos

Si dos integrantes editan **la misma linea del mismo archivo** al mismo tiempo, al hacer `pull --rebase` git no sabe cual de las dos versiones quedarse y te avisa:

```
CONFLICT (content): Merge conflict in TpFinal/grupos/G07/dags/01-bronze/api_bronze.py
```

Para resolver: abris el archivo en tu editor, ves marcas como estas:

```python
<<<<<<< HEAD
codigo de los otros
=======
tu codigo
>>>>>>> tu commit
```

Eliges cual version queda (o las combinas a mano), borras las marcas (`<<<<<<<`, `=======`, `>>>>>>>`), guardas el archivo, y haces:

```bash
git add <archivo-resuelto>
git rebase --continue
git push origin tp/G07
```

Si te perdes en el conflicto y queres salir sin resolver:

```bash
git rebase --abort
```

Te deja como estabas antes del `pull --rebase`.

---

## 6. Errores comunes (lecciones del cuatrimestre 2026-1C)

### 6.1. "Cree la branch desde mi rama personal en vez de main"

**Sintoma**: el PR del grupo muestra muchos archivos que no son del TP (notebooks de clases anteriores, entregas personales, archivos del stack del curso).

**Por que pasa**: el estudiante estaba parado en su rama personal (`estudiante/apellido-nombre`, la de las entregas semanales) y hizo `git checkout -b tp/G<NN>` directo, sin pasar antes por `main`. La branch nueva parte de donde estaba parado, no de `main`.

```
main:                       A───B───C───D───E───F   (con los merges de todos al dia)
                                 \
estudiante/apellido-nombre:       G───H              (rama personal, atrasada)
                                       \
tp/G07:                           I───J───K    (TP + arrastra G, H, archivos viejos)
```

**Como evitarlo**: SIEMPRE hacer `git checkout main && git pull origin main` antes del `git checkout -b tp/G<NN>`.

**Como arreglarlo si ya paso**: rehacer la branch desde cero. Guardar copia de `TpFinal/grupos/G<NN>/` aparte, borrar la branch local, recrearla desde `main` actualizado, pegar los archivos copiados, hacer push con `--force-with-lease`. Ver seccion **7. Troubleshooting**.

### 6.2. "Edite un archivo desde la UI de GitHub y se creo un fork"

**Sintoma**: el PR aparece con `<usuario>:<branch>` en vez de simplemente `<branch>`. Ej: `tu-usuario:patch-1` en vez de `tp/G07`.

**Por que pasa**: cuando editas un archivo desde el boton "Edit this file" en la web de GitHub, si GitHub no detecta bien tus permisos te ofrece automaticamente "Fork and edit" y crea un fork sin avisarte. Despues de editar, te abre un PR desde el fork al repo original.

**Como evitarlo**: **no usar el boton "Edit this file"** en GitHub web. Trabajar siempre desde local con `git clone` + editor + commits + push.

**Como arreglarlo si ya paso**: como casi no hay codigo todavia, arrancar de nuevo en el repo del curso: alguno del grupo clona el repo del curso (no el fork), crea `tp/G<NN>` desde `main`, copia el contenido del README del fork (a mano o con `git remote add fork ...`), commit + push, abre PR nuevo. El docente cierra el PR del fork sin mergear. El fork queda abandonado.

### 6.3. "Mi commit aparece como 'Tu Nombre' sin email"

**Sintoma**: en el git log (o en la pestaña "Commits" del PR) algun commit aparece firmado por "Tu Nombre" o por un email tipo `tu@email.com`.

**Por que pasa**: `git config user.name` y `user.email` quedaron sin setear (o con valores de ejemplo del tutorial).

**Como evitarlo**: configurar la identidad **antes** del primer commit (ver seccion 3.1).

**Como arreglarlo si ya paso**: corregir la config para los **proximos** commits:

```bash
git config --global user.name "Tu Nombre Real"
git config --global user.email "tu-email@unsam.edu.ar"
```

Los commits viejos quedan asi en la historia (cambiarlos requiere reescribir historia, no vale la pena para el TP). Lo importante es que los proximos commits tuyos queden firmados bien.

### 6.4. "El PR esta abierto pero no en draft"

**Sintoma**: el PR figura como abierto sin la etiqueta "Draft".

**Por que pasa**: al crear el PR, en vez de elegir "Create draft pull request" se eligio "Create pull request" directo.

**Como evitarlo**: al crear el PR, click en la flechita ▼ al lado del boton verde y elegir "Create draft pull request".

**Como arreglarlo si ya paso**: en la pagina del PR, hay un boton **"Convert to draft"** abajo a la derecha. Click ahi.

---

## 7. Troubleshooting / si algo sale mal

### 7.1. Limpiar una branch contaminada (rehacer desde cero)

Si tu branch arrastro archivos que no son del TP y queres dejarla solo con lo del grupo:

```bash
# 1. Backup local (por si algo sale mal)
git checkout tp/G07
git checkout -b tp/G07-backup    # snapshot local
git push origin tp/G07-backup    # tambien en el remoto, por las dudas

# 2. Recrear la branch desde main
git checkout main
git pull origin main
git branch -D tp/G07             # borrar la rota
git checkout -b tp/G07           # crear de nuevo desde main

# 3. Traer SOLO la carpeta del grupo desde el backup
git checkout tp/G07-backup -- TpFinal/grupos/G07/

# 4. Verificar: solo TpFinal/grupos/G07/ deberia aparecer
git status

# 5. Commit y force-push
git add TpFinal/grupos/G07/
git commit -m "tp/G07: limpieza de scope"
git push --force-with-lease origin tp/G07
```

El PR existente se actualiza automaticamente y ahora muestra solo el contenido correcto.

> **`--force-with-lease`** es como `--force` pero seguro: aborta si alguien mas pusheo a la branch mientras vos trabajabas. Usar siempre esta variante.

### 7.2. Recuperar trabajo "perdido"

Si borraste algo por error o queres volver a un estado anterior:

```bash
# Ver historico de TODO lo que hiciste localmente (incluso lo "borrado")
git reflog

# Te muestra cosas tipo:
# a1b2c3d HEAD@{0}: reset: moving to HEAD~1
# d4e5f6g HEAD@{1}: commit: TP G07 silver listo
# ...

# Si queres volver al commit "TP G07 silver listo" (d4e5f6g):
git reset --hard d4e5f6g
```

**Antes de hacer `reset --hard`**: hace backup (`git branch backup-temp`) por si te equivocas.

### 7.3. "Borre la branch local pero el remoto sigue ahi" (o viceversa)

```bash
# Branch local existe, remoto no: pushear
git push -u origin tp/G07

# Branch remoto existe, local no: traerlo
git checkout -b tp/G07 origin/tp/G07

# Borrar branch local (la remota queda)
git branch -D tp/G07

# Borrar branch remota (la local queda)
git push origin --delete tp/G07
```

---

## 8. Resumen de comandos mas usados en el TP

```bash
# Setup (una vez)
git config --global user.name "Tu Nombre"
git config --global user.email "tu@email"
git clone https://github.com/juansokil/LCD-InfraCienciaDatos.git

# Antes de empezar a trabajar cada vez
git checkout main && git pull origin main
git checkout tp/G07
git pull --rebase origin tp/G07

# Hacer cambios
# (editar archivos con tu editor)
git add <archivos>
git commit -m "descripcion clara de que hiciste"
git push origin tp/G07
```

---

## 9. Si nada de esto te sirve

- **Si tenes una duda especifica de Git no cubierta aca**: abri un Issue en el repo del curso o preguntame en clase.
- **Si te quedaste atascado y no podes pushear**: no toques nada mas, mandame un mensaje con un screenshot del `git status` y veo como ayudarte.
- **Si perdiste trabajo importante**: `git reflog` casi siempre puede recuperarlo (ver 7.2). No entres en panico ni borres nada hasta que veamos juntos.

> **Recordatorio**: el resto del flujo del TP (entregables, fechas, estructura de carpetas, esqueleto del proyecto) esta en [`README.md`](README.md). Esta guia cubre solo lo de Git.
