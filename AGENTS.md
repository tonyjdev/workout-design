# workout-design

Documentación de diseño del proyecto Workout: especificación (`2026-11-10-workout-design.md`), rediseño
v1.1, planes de implementación por versión (`plans/`) e imágenes de ejercicios con su generador
(`exercise-images/`, `generate.py`). Sin código de aplicación. Todo en español.

## Estructura

- `2026-11-10-*.md` — especificación y rediseño.
- `plans/` — planes de implementación (`<fecha>-<versión o repo>.md`).
- `exercise-images/` — fotogramas por ejercicio y el script que los genera.

## Reglas

- Los planes y la especificación describen lo que implementan `workout-api` y `workout-app`: un cambio
  de comportamiento se decide aquí antes de implementarse allí.
- Rama única `main`. Nunca commits directos: cada cambio entra por una tarea y su PR a `main`.
- Commits convencionales (`docs: ...`).

## Sistema de tareas

Tareas en Workspace (proyecto `WRKD`), nunca en el repositorio. El ciclo (`/init-task` → `/start-task` →
`/close-task`, más `/create-task`) y las reglas de IA son la configuración global de
`~/.agents/workspace-kit` (skills en `~/.claude/skills`, reglas importadas desde `~/.claude/CLAUDE.md`);
este repo solo aporta `.claude/task-system.conf` y lo específico de este fichero. Una tarea = un worktree en `.worktrees/<clave>` + una rama
`<feat|fix|chore|research|docs>/wrkd-NNNN-<slug>` desde `origin/main` + un PR a `main`.

- Sin puerta automática: el cierre describe la revisión manual (enlaces, coherencia entre plan,
  especificación y lo ya implementado).
- Proyectos relacionados: `WRKA` (`~/Projects/workout-api`) y `WRKM` (`~/Projects/workout-app`).
  Cuando un documento cierra una decisión que hay que implementar, crea las tareas en esos proyectos.

