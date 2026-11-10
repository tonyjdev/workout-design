# Workout App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App Android (Vue + Capacitor) que funciona primero en el móvil: login con doble factor, historial, plantillas, reproductor por tiempo o por repeticiones, y sincronización con la API mediante cola offline.

**Architecture:** SPA Vue 3 + TypeScript empaquetada con Capacitor. Datos locales en IndexedDB (Dexie) como fuente para la UI; un motor de sincronización hace *pull* incremental (`GET /api/sync?since=`) y *push* de una cola FIFO (`outbox`) de PUT/DELETE idempotentes. La lógica (reproductor, progresión, estadísticas, duración, kcal) son funciones puras en `src/features/*/` probadas con Vitest; las vistas solo las orquestan. Organización por funcionalidad, no por capa.

**Tech Stack:** Vue 3.5, TypeScript, Vite, Tailwind 4 (`@tailwindcss/vite`), shadcn-vue (`new-york-v4`, `neutral`, lucide), vue-router 4, Pinia, Dexie 4, Capacitor 7 (`@capacitor/android`, `@capacitor/app`, `@capacitor/preferences`, `@capacitor-community/text-to-speech`, `@capacitor-community/keep-awake`), Vitest + jsdom + `fake-indexeddb` + `@vue/test-utils`, ESLint/Prettier, pnpm.

**Spec:** `~/Projects/workout-design/2026-11-10-workout-design.md`. **Contrato de la API:** `~/Projects/workout-api/docs/api-contract.md` (lo produce el plan de la API; este plan lo consume tal cual). Ejecutar este plan **después** del de la API.

## Global Constraints

- Repo privado `tonyjdev/workout-app` en `~/Projects/workout-app`; pnpm.
- Convenciones de `~/Projects/controlpanel`: `components.json` (shadcn-vue `new-york-v4`, `baseColor neutral`, `cssVariables true`, `iconLibrary lucide`, alias `@/components`, `@/components/ui`, `@/lib`, `@/composables`), `eslint.config.js`, `prettier` con `prettier-plugin-tailwindcss`.
- Textos de la UI en español. Voz `es-ES`.
- Fechas mostradas en `Europe/Madrid`; semanas de lunes a domingo; peso en kg.
- Calentamiento y estiramiento siempre por tiempo; el modo de la plantilla (`time|reps|choose`) aplica al bloque `main`.
- Modo tiempo → **circuito** (A→B→C, repetir `rounds`). Modo reps → **ejercicio a ejercicio** (todas las series de A, luego B).
- Unilaterales: en tiempo, el trabajo se parte en dos mitades con aviso "cambia de lado"; en reps, las reps son por lado.
- Al preparar un entreno por reps se precarga lo **último realizado** de ese ejercicio en esa plantilla; si no hay, los valores de la plantilla.
- Los ajustes en la previa del entreno **no** modifican la plantilla.
- El login necesita conexión; todo lo demás funciona offline.
- Commits con el pie `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Requisito de máquina: **JDK 21 y Android SDK** (Android Studio) para la Task 11; ahora no están instalados.

## Review Focus

1. **Cerrar la app a mitad de entreno** — al reabrir se ofrece continuar en el mismo paso con los resultados ya apuntados. Test en Task 9.
2. **Sin red al terminar** — la sesión queda en local y en `outbox`, aparece en el historial y se sube al volver la red; si el push falla por red, la cola no pierde el elemento. Test en Task 4.
3. **Token caducado o revocado** — un 401 en sync no borra datos locales ni la cola; lleva al login y, tras entrar, la cola se sube. Test en Task 4.
4. **Saltar bloque o ejercicio** — el salto queda reflejado en la sesión guardada (`skipped: true`) y no rompe la progresión (un ejercicio saltado no cuenta como "último realizado"). Tests en Tasks 7 y 8.
5. **Plantilla de un solo ejercicio y 1 ronda** — el reproductor no genera descansos finales ni pasos vacíos. Test en Task 8.

---

### Task 1: Esqueleto del proyecto

**Files:**
- Create: proyecto `pnpm create vite workout-app --template vue-ts`; `vite.config.ts` (alias `@` → `src`, `@tailwindcss/vite`), `src/assets/main.css` (Tailwind 4 + variables shadcn), `components.json`, `eslint.config.js`, `.prettierrc`, `vitest.config.ts` (jsdom, `setupFiles: ['fake-indexeddb/auto']`), `capacitor.config.ts` (`appId: 'dev.tonyj.workout'`, `appName: 'Workout'`, `webDir: 'dist'`), `src/router/index.ts`, `src/App.vue` (layout con barra inferior: Entrenar · Historial · Ajustes), `AGENTS.md`, `CLAUDE.md`, `docs/superpowers/plans/2026-11-10-workout-app.md`
- Test: `tests/App.spec.ts`

**Interfaces:**
- Produces: rutas con nombre `train`, `history`, `settings` (placeholders), `login`, `two-factor`; componentes shadcn `button`, `card`, `input`, `label`, `dialog`, `badge`, `tabs`, `sonner`, `switch`, `select`.

- [ ] **Step 1:** Crear proyecto; instalar dependencias del Tech Stack; `pnpm dlx shadcn-vue@latest init` y `add` de los componentes listados; `pnpm cap add android`.
- [ ] **Step 2: Test que falla:** `it('renders the bottom navigation')` — monta `App` con router en memoria y espera los textos "Entrenar", "Historial", "Ajustes".
- [ ] **Step 3:** `pnpm vitest run` → FAIL; implementar layout; → PASS.
- [ ] **Step 4:** `pnpm lint:check && pnpm vue-tsc --noEmit && pnpm build` → sin errores.
- [ ] **Step 5:** `gh repo create tonyjdev/workout-app --private --source . --push`; commit `chore: scaffold Vue + Tailwind + shadcn-vue + Capacitor app`.

---

### Task 2: Cliente de la API y ajustes persistentes

**Files:**
- Create: `src/lib/api/types.ts` (tipos del contrato: `User`, `LoginChallenge`, `Exercise`, `TemplateDoc`, `TemplateBlock`, `TemplateItem`, `SessionDoc`, `SessionBlock`, `SessionItem`, `SyncPayload`), `src/lib/api/client.ts`, `src/lib/settings.ts`
- Test: `tests/lib/api/client.spec.ts`, `tests/lib/settings.spec.ts`

**Interfaces:**
- `settings.ts`: `getSetting<K extends keyof AppSettings>(k: K): Promise<AppSettings[K]>`, `setSetting(k, v): Promise<void>` sobre `@capacitor/preferences`. `AppSettings = { apiUrl: string; token: string | null; voiceEnabled: boolean; soundsEnabled: boolean; lastSyncAt: string | null }`; por defecto `apiUrl: 'http://10.0.2.2:8000'`, `voiceEnabled: true`, `soundsEnabled: true`.
- `client.ts`: `api<T>(method: 'GET'|'POST'|'PUT'|'DELETE', path: string, body?: unknown): Promise<T>` — prefija `${apiUrl}/api`, añade `Accept: application/json` y `Authorization: Bearer` si hay token. Errores: `class ApiError extends Error { status: number; fieldErrors: Record<string,string[]> }`; fallo de red → `class NetworkError extends Error`. `204` → `undefined`.

- [ ] **Step 1: Tests que fallan:** `it('sends the bearer token')`, `it('maps 422 to ApiError with field errors')`, `it('throws NetworkError when fetch rejects')`, `it('returns undefined on 204')`; `settings`: `it('returns defaults when unset')`, `it('persists values')` (mock de `@capacitor/preferences`).
- [ ] **Step 2:** Ejecutar → FAIL; implementar; → PASS.
- [ ] **Step 3:** Commit `feat: add API client and persistent settings`.

---

### Task 3: Login con doble factor

**Files:**
- Create: `src/features/auth/authStore.ts`, `src/features/auth/LoginView.vue`, `src/features/auth/TwoFactorView.vue`, `src/router/guards.ts`
- Test: `tests/features/auth/authStore.spec.ts`, `tests/features/auth/TwoFactorView.spec.ts`

**Interfaces:**
- `useAuthStore()` (Pinia): estado `user: User | null`, `challenge: LoginChallenge | null`; acciones `restore(): Promise<void>` (lee token; si hay, `GET /me`; 401 → limpia token), `login(email, password): Promise<void>` (`POST /auth/login`, `device_name: 'workout-app'`), `verify(input: { code?: string; recoveryCode?: string }): Promise<void>` (guarda token y user; dispara `syncNow()` de la Task 4), `logout(): Promise<void>` (`POST /auth/logout`, borra token; **no** borra datos locales ni la cola); getter `isAuthenticated`.
- Guard: rutas sin `meta.public` exigen `isAuthenticated`; si no → `login`.
- `TwoFactorView`: texto según `challenge.method` — `totp`: "Introduce el código de tu app autenticadora" + enlace "Usar un código de recuperación"; `email`: "Te hemos enviado un código a tu email". Errores de `fieldErrors` bajo el campo.

- [ ] **Step 1: Tests que fallan:** `it('stores the challenge after login')`, `it('stores token and user after verify')`, `it('clears the token when me returns 401')`, `it('keeps local data on logout')`; vista: `it('shows the email copy for email challenges')`, `it('switches to recovery code input')`.
- [ ] **Step 2:** Ejecutar → FAIL; implementar; → PASS.
- [ ] **Step 3:** Commit `feat: add two-step login with TOTP or email code`.

---

### Task 4: Base de datos local y sincronización

**Files:**
- Create: `src/lib/db.ts`, `src/lib/sync/outbox.ts`, `src/lib/sync/syncEngine.ts`, `src/lib/sync/useSyncTriggers.ts`
- Test: `tests/lib/sync/syncEngine.spec.ts`

**Interfaces:**
- `db.ts` (Dexie `workout`): tablas `exercises` (`&code`), `templates` (`&id, updated_at`), `sessions` (`&id, started_at, template_id`), `outbox` (`++seq, status`), `runs` (`&id`, reproductor en curso, Task 9).
- `outbox.ts`: `enqueue(op: { method: 'PUT'|'DELETE'; path: string; body?: unknown }): Promise<void>`; `OutboxItem = op & { seq: number; status: 'pending'|'failed'; error?: string }`.
- `syncEngine.ts`:
  - `pushOutbox(): Promise<{ pushed: number; failed: number }>` — FIFO; 2xx → borra; `ApiError` 4xx≠401 → `status 'failed'` + mensaje y sigue; `NetworkError` → para sin tocar el elemento; 401 → para y emite `auth-expired`.
  - `pull(): Promise<void>` — `GET /sync?since=lastSyncAt`; aplica en una transacción (plantillas con `deleted_at` → borrar local); guarda `server_time` como `lastSyncAt`.
  - `syncNow(): Promise<void>` — `pushOutbox()` y luego `pull()`; ignora llamadas concurrentes.
  - Al guardar un `PUT /templates` local pendiente, `pull()` no sobrescribe esa plantilla mientras esté en la cola.
- `useSyncTriggers()`: llama `syncNow()` al arrancar con sesión, tras `verify`, en `window 'online'`, en `App.addListener('resume')` y cada 5 min.

- [ ] **Step 1: Tests que fallan** (fetch mockeado, `fake-indexeddb`): `it('pushes in order and removes on success')`, `it('keeps the item on network error')`, `it('marks 422 as failed and continues')`, `it('stops and emits auth-expired on 401 without deleting data')`, `it('applies a pull and stores server_time')`, `it('deletes templates that come with deleted_at')`, `it('does not overwrite a template pending in the outbox')`, `it('ignores concurrent syncNow calls')`.
- [ ] **Step 2:** Ejecutar → FAIL; implementar; → PASS.
- [ ] **Step 3:** Commit `feat: add local database and offline sync engine`.

---

### Task 5: Historial

**Files:**
- Create: `src/features/history/weeklyStats.ts`, `src/features/history/HistoryView.vue`, `src/features/history/SessionDetailView.vue`, `src/lib/dates.ts`
- Test: `tests/features/history/weeklyStats.spec.ts`, `tests/features/history/HistoryView.spec.ts`

**Interfaces:**
- `dates.ts`: `weekStart(iso: string): string` (`YYYY-MM-DD` del lunes en `Europe/Madrid`, con `Intl`), `formatDateTime(iso): string` (`dd/mm/aa, HH:mm`).
- `weeklyStats(sessions: SessionDoc[], weeks: number, today: string): WeekStat[]`, `WeekStat = { weekStart: string; sessions: number; minutes: number; kcal: number }`, más reciente primero, con semanas vacías. Se calcula en local (offline).
- `HistoryView`: cabecera con minutos y kcal de la semana actual; lista agrupada por semana; cada sesión: fecha, nombre, minutos, kcal, insignia "Pendiente de subir" si su id está en `outbox`.
- `SessionDetailView` (ruta `session/:id`): bloques con ejercicios y lo realizado (series `reps × kg` o segundos), bloques/ejercicios saltados atenuados; botón "Repetir" → ruta `prepare/:templateId` (Task 7); deshabilitado si la plantilla no existe.

- [ ] **Step 1: Tests que fallan:** `weekStart('2026-10-25T22:30:00Z')` → `2026-10-19` (domingo 23:30 Madrid) y `weekStart('2026-10-25T23:30:00Z')` → `2026-10-26` (lunes 00:30 Madrid); `weeklyStats` incluye semana vacía con ceros; vista: `it('groups sessions by week')`, `it('flags sessions pending upload')`.
- [ ] **Step 2:** Ejecutar → FAIL; implementar; → PASS.
- [ ] **Step 3:** Commit `feat: add history list, detail and weekly stats`.

---

### Task 6: Lista de plantillas y editor

**Files:**
- Create: `src/features/templates/templateMath.ts`, `src/features/templates/templateRepo.ts`, `src/features/templates/TrainView.vue`, `src/features/templates/TemplateEditorView.vue`, `src/features/templates/ExercisePicker.vue`
- Test: `tests/features/templates/templateMath.spec.ts`, `tests/features/templates/templateRepo.spec.ts`

**Interfaces:**
- `estimateDurationSeconds(t: TemplateDoc, mode: 'time'|'reps'): number` — tiempo: `rounds × Σ(work+rest) + (rounds−1) × round_rest_seconds` por bloque; reps: `Σ sets × (reps × 3 s × (unilateral ? 2 : 1) + set_rest_seconds)`. El valor de 3 s por repetición es decisión del plan.
- `lastPerformedAt(templateId: string, sessions: SessionDoc[]): string | null`.
- `templateRepo`: `saveTemplate(t: TemplateDoc): Promise<void>` (Dexie + `enqueue PUT /templates/{id}`), `deleteTemplate(id)` (Dexie + `enqueue DELETE`), `duplicateTemplate(id): Promise<TemplateDoc>` (nuevo `crypto.randomUUID()`, nombre `"<nombre> (copia)"`).
- `validateTemplate(t: TemplateDoc): string[]` — mismas reglas que la API (Task 5 del plan de la API), mensajes en español; el editor no guarda si hay errores.
- `TrainView`: lista de plantillas (nombre, insignia de modo "Tiempo"/"Reps"/"Elegir", duración estimada, "Última vez: dd/mm"), ordenadas por última vez realizada; tocar → `prepare/:id`; menú → editar, duplicar, borrar (con confirmación).
- `TemplateEditorView` (ruta `templates/:id/edit`): nombre, modo, rondas y descanso entre rondas por bloque, por ejercicio sus valores de tiempo y/o reps según modo, `unilateral`, añadir (desde `ExercisePicker` con búsqueda), quitar y reordenar.

- [ ] **Step 1: Tests que fallan:** duración de una plantilla de tiempo de 2 rondas con 3 ejercicios `{40,20}` y `round_rest 60` → `420`; reps `3×12` unilateral con descanso 60 → `3 × (72 + 60) = 396`; `validateTemplate` detecta `main` sin `reps` en modo `reps`; `duplicateTemplate` encola un PUT con id nuevo; `deleteTemplate` encola DELETE.
- [ ] **Step 2:** Ejecutar → FAIL; implementar; → PASS.
- [ ] **Step 3:** Commit `feat: add template list and editor`.

---

### Task 7: Previa del entreno y progresión

**Files:**
- Create: `src/features/player/runPlan.ts`, `src/features/player/PrepareView.vue`
- Test: `tests/features/player/runPlan.spec.ts`

**Interfaces:**
- `RunPlan = { templateId: string; name: string; mode: 'time'|'reps'; blocks: RunBlock[] }`, `RunBlock = { kind; rounds; roundRestSeconds; skipped: boolean; items: RunItem[] }`, `RunItem = { exerciseCode; name; unilateral; time?: {workSeconds; restSeconds}; reps?: {sets; reps; weightKg: number|null; setRestSeconds} }`.
- `buildRunPlan(t: TemplateDoc, mode: 'time'|'reps', sessions: SessionDoc[], exercises: Exercise[]): RunPlan` — `mode` debe ser el de la plantilla salvo en `choose`. En `reps`: para cada ejercicio del `main`, busca la sesión más reciente **de esa plantilla** donde ese ejercicio no esté saltado y tenga `sets`; precarga `sets.length`, `reps` de la última serie y `weight_kg` de la última serie.
- `PrepareView` (ruta `prepare/:templateId`): en `choose` pide elegir "Por tiempo" / "Por repeticiones"; muestra el plan editable (solo en memoria) y la duración estimada; "Empezar" → crea el run (Task 9) y navega a `player/:runId`.

- [ ] **Step 1: Tests que fallan:** `it('preloads reps and weight from the last session of the same template')`, `it('ignores sessions from other templates')`, `it('ignores skipped exercises when preloading')`, `it('falls back to template values')`, `it('rejects time mode for a reps template')`.
- [ ] **Step 2:** Ejecutar → FAIL; implementar; → PASS.
- [ ] **Step 3:** Commit `feat: add workout preparation with progression preload`.

---

### Task 8: Motor del reproductor (puro)

**Files:**
- Create: `src/features/player/steps.ts`, `src/features/player/playerMachine.ts`
- Test: `tests/features/player/steps.spec.ts`, `tests/features/player/playerMachine.spec.ts`

**Interfaces:**
- `Step = { kind: 'work'; blockIndex; itemIndex; round; seconds; side?: 'first'|'second' } | { kind: 'rest'; blockIndex; seconds; nextLabel: string } | { kind: 'set'; blockIndex; itemIndex; setIndex; targetReps; targetWeightKg: number|null }`.
- `buildSteps(plan: RunPlan): Step[]` — bloques no saltados en orden; bloques por tiempo (`warmup`, `cooldown`, `main` en `time`) en **circuito** por `rounds`, unilateral → dos `work` de `floor(work/2)` y `ceil(work/2)` con `side`; `rest` tras cada ejercicio si `restSeconds > 0`, `roundRestSeconds` entre rondas; `main` en `reps` ejercicio a ejercicio con `set` + `rest(setRestSeconds)` entre series. **Nunca** un `rest` como último paso del bloque ni del entreno.
- `PlayerState = { steps; index; remaining: number; paused: boolean; results: Record<string /* `${block}:${item}` */, { sets: {reps:number; weightKg:number|null}[]; workSeconds: number; skipped: boolean }>; skippedBlocks: number[]; finished: boolean }`.
- `playerReducer(state, event): PlayerState` con eventos `{type:'tick'}` (−1 s; a 0 avanza), `{type:'pause'}`, `{type:'resume'}`, `{type:'completeSet', reps, weightKg}` (apunta y avanza), `{type:'skipExercise'}` (marca `skipped` y salta todos sus pasos restantes), `{type:'skipBlock'}`, `{type:'previous'}`.
- `announcements(prev: PlayerState, next: PlayerState): string[]` — textos de voz: al empezar un `work` "<nombre>", al empezar `side: 'second'` "Cambia de lado", en `rest` "Descanso. Siguiente: <nombre>", y "3", "2", "1" en los últimos segundos de cada paso con tiempo; al acabar "Entrenamiento completado".

- [ ] **Step 1: Tests que fallan:** circuito: 2 rondas × A,B `{40,20}` con `roundRest 60` → `work A, rest, work B, rest(60 ronda), work A, rest, work B` (sin rest final); unilateral `work 45` → `22` + `23` con `side`; reps `2×10` de A y `1×8` de B con descanso 60 → `set A1, rest, set A2, rest, set B1`; bloque saltado no genera pasos; plantilla de 1 ejercicio y 1 ronda → un único paso; `tick` hasta 0 avanza; `pause` ignora `tick`; `completeSet` guarda reps y peso; `skipExercise` deja `skipped: true` y salta sus series; `announcements` emite "Cambia de lado" y la cuenta 3‑2‑1.
- [ ] **Step 2:** Ejecutar → FAIL; implementar; → PASS.
- [ ] **Step 3:** Commit `feat: add pure player engine`.

---

### Task 9: Pantalla del reproductor, guardado y reanudación

**Files:**
- Create: `src/features/player/PlayerView.vue`, `src/features/player/runStore.ts`, `src/features/player/finishRun.ts`, `src/lib/device/voice.ts`, `src/lib/device/sounds.ts`, `src/lib/device/keepAwake.ts`, `public/sounds/{beep,whistle,done}.wav` (copiar `ding.wav`, `whistle.wav`, `applause.wav` de `assets/fx` del repo archivado `tonyjdev/workout-app-web`, renombrados)
- Test: `tests/features/player/finishRun.spec.ts`, `tests/features/player/runStore.spec.ts`

**Interfaces:**
- `voice.speak(text: string): Promise<void>` (`@capacitor-community/text-to-speech`, `lang 'es-ES'`; en web `speechSynthesis`; no-op si `voiceEnabled` es false); `sounds.play(name: 'beep'|'whistle'|'done')`; `keepAwake.on()/off()`.
- `runStore`: `createRun(plan: RunPlan): Promise<string>` (guarda `{id, plan, state, startedAt}` en `db.runs`), `saveRunState(id, state)` (tras cada evento), `loadUnfinishedRun(): Promise<Run | null>`, `discardRun(id)`.
- `estimateKcal(name: string, durationSeconds: number, sessions: SessionDoc[]): number` — media kcal/min de las sesiones con el mismo `name`; si no hay, **6 kcal/min** (decisión del plan); redondeo a entero.
- `buildSessionDoc(run: Run, endedAt: string, sessions: SessionDoc[]): SessionDoc` — `id = run.id`, `template_id`, `mode`, `source 'app'`, bloques con `skipped` y por ejercicio `sets` (reps) o `work_seconds` (tiempo); `duration_seconds` real descontando pausas.
- `finishRun(run)`: guarda la sesión en `db.sessions`, `enqueue PUT /sessions/{id}`, borra el run, `keepAwake.off()`, `syncNow()` sin esperar.
- `PlayerView` (ruta `player/:runId`): en `work`/`rest`, cuenta atrás grande, nombre del ejercicio, "Ronda x/y", siguiente; en `set`, "Serie x/y", objetivo `reps × kg`, campos para reps y peso reales prerrellenos con el objetivo y botón "Hecho" (lanza el descanso); botones pausa, anterior, saltar ejercicio, saltar bloque y terminar. Al entrar, `keepAwake.on()`. Al terminar, resumen (duración, kcal, ejercicios) y "Guardar".
- Al arrancar la app, si `loadUnfinishedRun()` devuelve algo → diálogo "Tienes un entrenamiento a medias" con "Continuar" / "Descartar".

- [ ] **Step 1: Tests que fallan:** `estimateKcal('Series de fuerza', 3300, sessions)` con dos sesiones del mismo nombre de 8,5 kcal/min → `468`; sin historial → `6 × 55 = 330`; `buildSessionDoc` refleja `skipped` y las series apuntadas; `it('restores an unfinished run with its results')` (crear run, guardar estado tras 2 `completeSet`, recargar → mismo `index` y resultados); `finishRun` deja la sesión en `db.sessions` y un PUT en `outbox` sin red.
- [ ] **Step 2:** Ejecutar → FAIL; implementar; → PASS.
- [ ] **Step 3:** Probar en navegador (`pnpm dev`) un entreno de tiempo y uno de reps de punta a punta contra la API local.
- [ ] **Step 4:** Commit `feat: add player screen with voice, keep-awake, resume and save`.

---

### Task 10: Ajustes y seguridad

**Files:**
- Create: `src/features/settings/SettingsView.vue`, `src/features/settings/SecurityView.vue`, `src/features/settings/securityApi.ts`
- Test: `tests/features/settings/securityApi.spec.ts`, `tests/features/settings/SettingsView.spec.ts`

**Interfaces:**
- `securityApi`: `enableTotp(password): Promise<{secret; otpauthUrl; qrSvg}>`, `confirmTotp(code): Promise<string[]>`, `getRecoveryCodes(): Promise<string[]>`, `regenerateRecoveryCodes(password): Promise<string[]>`, `disableTotp(password): Promise<void>` — endpoints de la Task 4 del plan de la API.
- `SettingsView`: interruptores voz y sonidos, URL de la API (valida `http(s)://`), estado de sincronización ("Pendientes: N · Con error: N", botón "Sincronizar ahora", lista de errores con opción de descartar), enlace a Seguridad, "Cerrar sesión".
- `SecurityView`: si TOTP no está activo: "Activar app autenticadora" → pide contraseña → muestra QR (`qrSvg` con `v-html` solo de esta respuesta) y secreto → pide código → muestra los 8 códigos de recuperación con aviso de guardarlos. Si está activo: ver y regenerar códigos y desactivar (con contraseña). Requiere conexión; sin red muestra "Necesitas conexión".

- [ ] **Step 1: Tests que fallan:** `securityApi` llama a los endpoints y métodos correctos; `SettingsView` muestra los contadores de `outbox` y rechaza una URL sin esquema.
- [ ] **Step 2:** Ejecutar → FAIL; implementar; → PASS.
- [ ] **Step 3:** Commit `feat: add settings and TOTP security screens`.

---

### Task 11: Build Android y prueba en el móvil

**Files:**
- Create: `android/app/src/debug/res/xml/network_security_config.xml` (cleartext permitido solo en debug) y su referencia en `android/app/src/debug/AndroidManifest.xml`
- Modify: `README.md` (requisitos, `pnpm build && pnpm cap sync android`, instalar con `adb`, URL de la API en red local)

- [ ] **Step 1:** Comprobar requisitos: `java -version` (21) y `$ANDROID_HOME`. Si faltan, **parar y pedir a Tony** que instale Android Studio (no instalar paquetes del sistema sin permiso).
- [ ] **Step 2:** `pnpm build && pnpm cap sync android && cd android && ./gradlew assembleDebug` → APK en `android/app/build/outputs/apk/debug/`.
- [ ] **Step 3:** `adb install -r` en el móvil conectado (`V8XW7TXS5PY9R8G6`); API con `sail up` y `apiUrl` = IP del PC en la wifi.
- [ ] **Step 4: Checklist en el dispositivo** (anotar resultado de cada punto): login con código por email (Mailpit) · activar TOTP y login con TOTP · historial con las 11 sesiones importadas · entreno por tiempo con voz y pantalla encendida · entreno por reps con peso y precarga en la segunda vez · cerrar la app a mitad y continuar · modo avión al terminar y subida al volver la red.
- [ ] **Step 5:** Commit `chore: android debug build config and setup docs`.
