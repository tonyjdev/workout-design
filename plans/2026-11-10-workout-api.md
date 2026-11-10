# Workout API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** API REST en Laravel 13 que autentica a un único usuario con doble factor obligatorio, guarda catálogo de ejercicios, plantillas y sesiones, sincroniza con la app móvil offline-first e importa el historial de Fitify.

**Architecture:** Laravel 13 solo-JSON (sin Inertia ni Blade de UI). Controladores finos que delegan en acciones (`app/Application/Actions`), modelos en `app/Domain/Training` y `app/Domain/Auth`. Plantillas y sesiones guardan sus bloques como **documento JSON validado** (la app los edita y sube enteros); solo el catálogo de ejercicios está normalizado. Ids de plantillas y sesiones son UUID generados por el cliente para que la cola offline sea idempotente.

**Tech Stack:** PHP 8.4+, Laravel 13, Fortify (solo sus acciones de 2FA), Sanctum (tokens), Pest 4, Pint, Sail (pgsql + mailpit), SQLite en memoria para tests.

**Spec:** `~/Projects/workout-design/2026-11-10-workout-design.md` (se copia al repo en la Task 1 como `docs/superpowers/specs/2026-11-10-workout-design.md`).

**Contrato compartido con la app:** `docs/api-contract.md` (lo crea la Task 1 y lo amplía cada task). El plan de la app (`2026-11-10-workout-app.md`) consume exactamente esas formas.

## Global Constraints

- Laravel 13, PHP `^8.4`, Pest 4, Pint con preset `laravel` (copiar `pint.json` de `~/Projects/controlpanel`).
- Gestor JS: no aplica (API sin frontend); no instalar Vite/Tailwind en este repo.
- Todas las columnas de fecha con zona: `timestampsTz()`/`timestampTz()`; conexión con `'timezone' => 'UTC'`.
- Fechas del export de Fitify en `Europe/Madrid`; se guardan en UTC. Semanas de lunes a domingo (en `Europe/Madrid`). Peso en kg.
- Sin registro público. Usuario creado por comando.
- Doble factor obligatorio en todo login: TOTP si `two_factor_confirmed_at` no es nulo; si no, código por email.
- Controladores finos; lógica en `app/Application/Actions/<Área>/`.
- Toda ruta de datos bajo `auth:sanctum`.
- Commits con el pie `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Reenvío desde la cola offline** — un `PUT /api/sessions/{id}` repetido con el mismo UUID debe devolver 200 y no duplicar ni modificar. Test en Task 6.
2. **Reto 2FA abusado** — 5 códigos erróneos invalidan el reto; un reto caducado (10 min) o ya canjeado no da token. Test en Task 3.
3. **Reimportar el export** — ejecutar `fitify:import` dos veces no duplica sesiones, plantillas ni ejercicios. Test en Task 7.
4. **Plantilla incoherente con su modo** — un bloque `main` de una plantilla `reps` sin `reps`, o un `warmup` sin `time`, da 422. Test en Task 5.
5. **Sincronización de borrados** — una plantilla borrada aparece en `GET /api/sync?since=` con `deleted_at` para que el móvil la quite. Test en Task 6.

---

### Task 0: Archivar los repos antiguos (requiere confirmación explícita)

**Files:** ninguno (GitHub).

- [ ] **Step 1: Pedir confirmación a Tony** mostrando exactamente lo que se hará:
  - `tonyjdev/workout-api` → renombrar a `workout-api-legacy` y archivar.
  - `tonyjdev/workout-app` → renombrar a `workout-app-legacy` y archivar.
  - `tonyjdev/workout-app-web` → archivar (sin renombrar).
  No continuar sin un "sí" explícito.
- [ ] **Step 2: Ejecutar**
  ```bash
  gh repo rename workout-api-legacy -R tonyjdev/workout-api --yes && gh repo archive tonyjdev/workout-api-legacy --yes
  gh repo rename workout-app-legacy -R tonyjdev/workout-app --yes && gh repo archive tonyjdev/workout-app-legacy --yes
  gh repo archive tonyjdev/workout-app-web --yes
  ```
- [ ] **Step 3: Verificar** `gh repo list tonyjdev --archived --limit 50 | grep workout` → 3 líneas.

---

### Task 1: Esqueleto del proyecto

**Files:**
- Create: proyecto Laravel 13 en `~/Projects/workout-api` (repo privado `tonyjdev/workout-api`)
- Create: `pint.json`, `docker-compose.yml` (Sail: `pgsql`, `mailpit`), `Dockerfile` (producción, sin usar aún), `docs/api-contract.md`, `docs/superpowers/specs/2026-11-10-workout-design.md`, `docs/superpowers/plans/2026-11-10-workout-api.md`, `AGENTS.md`, `CLAUDE.md` (mapa breve: estructura, comandos, reglas de Global Constraints)
- Modify: `config/database.php` (`'timezone' => 'UTC'` en pgsql y sqlite), `phpunit.xml` (`DB_CONNECTION=sqlite`, `DB_DATABASE=:memory:`)
- Test: `tests/Feature/HealthTest.php`

**Interfaces:**
- Produces: `GET /api/health` → `200 {"status":"ok"}`; estructura de carpetas `app/Domain/{Auth,Training}`, `app/Application/Actions/{Auth,Training,Import}`.

- [ ] **Step 1:** `laravel new workout-api --pest --no-interaction` (sin starter kit), `composer require laravel/sanctum laravel/fortify`, `php artisan install:api`, `php artisan sail:install --with=pgsql,mailpit`. Eliminar Vite, `resources/js`, `resources/css`, `package.json`.
- [ ] **Step 2: Test que falla** — `it('reports health')`: `getJson('/api/health')->assertOk()->assertExactJson(['status' => 'ok'])`.
- [ ] **Step 3:** Ejecutar `php artisan test --filter=HealthTest` → FAIL (404).
- [ ] **Step 4:** Ruta en `routes/api.php` devolviendo `['status' => 'ok']`.
- [ ] **Step 5:** `php artisan test` → PASS; `vendor/bin/pint --test` → sin cambios.
- [ ] **Step 6:** `git init`, `gh repo create tonyjdev/workout-api --private --source . --push`, commit `chore: scaffold Laravel 13 API`.

---

### Task 2: Usuario y comando de alta

**Files:**
- Create: `app/Domain/Auth/User.php` (mover el modelo; usa `HasApiTokens`, `TwoFactorAuthenticatable`), `app/Console/Commands/CreateUserCommand.php`, migración de columnas 2FA de Fortify (`two_factor_secret`, `two_factor_recovery_codes`, `two_factor_confirmed_at` `timestampTz`)
- Modify: `config/auth.php` (modelo `App\Domain\Auth\User`), `database/factories/UserFactory.php`, `database/seeders/DatabaseSeeder.php` (crea `tony@example.test` / `password` solo fuera de producción)
- Test: `tests/Feature/Auth/CreateUserCommandTest.php`

**Interfaces:**
- Produces: `php artisan user:create {email} {name} {--password=}` (si falta `--password`, lo pregunta oculto); falla con código 1 si el email existe.

- [ ] **Step 1: Tests que fallan** — `it('creates a user with a hashed password')` (comprueba `Hash::check`), `it('refuses a duplicated email')` (`assertExitCode(1)`).
- [ ] **Step 2:** `php artisan test --filter=CreateUserCommandTest` → FAIL.
- [ ] **Step 3:** Implementar comando y migración.
- [ ] **Step 4:** Tests → PASS.
- [ ] **Step 5:** Commit `feat: add user model with 2FA columns and user:create command`.

---

### Task 3: Login en dos pasos con doble factor obligatorio

**Files:**
- Create: `app/Domain/Auth/LoginChallenge.php` + migración `login_challenges` (`id` uuid, `user_id` fk cascade, `method` string `totp|email`, `code_hash` nullable, `attempts` unsignedTinyInteger default 0, `expires_at` tz, `consumed_at` tz nullable, `device_name` string, `timestampsTz`)
- Create: `app/Application/Actions/Auth/StartLogin.php`, `app/Application/Actions/Auth/CompleteLogin.php`, `app/Notifications/LoginCodeNotification.php`
- Create: `app/Http/Controllers/Api/Auth/LoginController.php`, `TwoFactorChallengeController.php`, `SessionController.php` (me + logout)
- Test: `tests/Feature/Auth/LoginTest.php`, `tests/Feature/Auth/TwoFactorChallengeTest.php`

**Interfaces:**
- `StartLogin::handle(string $email, string $password, string $deviceName): LoginChallenge` — lanza `ValidationException` (`email` → "Credenciales incorrectas.") si no casan.
- `CompleteLogin::handle(LoginChallenge $challenge, ?string $code, ?string $recoveryCode): string` — devuelve el token Sanctum en texto plano.
- HTTP (documentar en `docs/api-contract.md` → sección *Auth*):
  - `POST /api/auth/login` `{email, password, device_name}` → `200 {challenge_id, method: "totp"|"email", expires_at}`; `422` credenciales; `throttle:5,1`.
  - `POST /api/auth/two-factor` `{challenge_id, code?}` o `{challenge_id, recovery_code?}` → `200 {token, user: {id, name, email, two_factor_enabled}}`; `422` código erróneo, reto caducado, consumido o agotado; `throttle:10,1`.
  - `GET /api/me` → `{id, name, email, two_factor_enabled}`; `POST /api/auth/logout` → `204` (borra el token actual).
- Valores fijos: reto caduca a los **10 min**; máximo **5 intentos**; código email de **6 dígitos**, guardado con `Hash::make`; `recovery_code` solo en método `totp` y se consume con `replaceRecoveryCode`.

- [ ] **Step 1: Tests que fallan** (`LoginTest`):
  - `it('returns an email challenge and mails a code when TOTP is not confirmed')` — `Notification::fake()`; respuesta `method === 'email'`; `Notification::assertSentTo($user, LoginCodeNotification::class)`; no hay token en la respuesta.
  - `it('returns a totp challenge without mailing when TOTP is confirmed')` — `method === 'totp'`, `assertNothingSent()`.
  - `it('rejects wrong credentials')` → 422 con error en `email`.
- [ ] **Step 2: Tests que fallan** (`TwoFactorChallengeTest`):
  - `it('exchanges a valid email code for a token')` — captura el código desde la notificación fakeada; `assertOk()`, `token` no vacío, `$user->tokens()->count() === 1`.
  - `it('exchanges a valid TOTP code')` — genera el código con `app(TwoFactorAuthenticationProvider::class)` / `Google2FA::getCurrentOtp(decrypt($user->two_factor_secret))`.
  - `it('accepts a recovery code once')` — segundo uso → 422.
  - `it('invalidates the challenge after 5 wrong codes')` — 5 erróneos → 422; el 6.º con código correcto → 422.
  - `it('rejects an expired challenge')` — `travel(11)->minutes()` → 422.
  - `it('rejects a consumed challenge')` — reutilizar `challenge_id` tras éxito → 422.
  - `it('returns me and logs out')` — con token: `/api/me` 200; `/api/auth/logout` 204; `/api/me` posterior 401.
- [ ] **Step 3:** `php artisan test --filter='LoginTest|TwoFactorChallengeTest'` → FAIL.
- [ ] **Step 4:** Implementar. TOTP se verifica con `Laravel\Fortify\Contracts\TwoFactorAuthenticationProvider::verify(decrypt($user->two_factor_secret), $code)`. Cada intento fallido incrementa `attempts` antes de responder.
- [ ] **Step 5:** Tests → PASS. Pint.
- [ ] **Step 6:** Commit `feat: add mandatory two-step login with TOTP or email code`.

---

### Task 4: Gestión del TOTP desde la app

**Files:**
- Create: `app/Http/Controllers/Api/Auth/TwoFactorSettingsController.php`, `app/Http/Requests/Auth/CurrentPasswordRequest.php`
- Test: `tests/Feature/Auth/TwoFactorSettingsTest.php`

**Interfaces** (documentar en *Auth* del contrato; todas `auth:sanctum`):
- `POST /api/user/two-factor` `{password}` → `200 {secret, otpauth_url, qr_svg}` (usa `EnableTwoFactorAuthentication`; aún no confirmado).
- `POST /api/user/two-factor/confirm` `{code}` → `200 {recovery_codes: string[8]}` (usa `ConfirmTwoFactorAuthentication`).
- `GET /api/user/two-factor/recovery-codes` → `200 {recovery_codes}`; `POST /api/user/two-factor/recovery-codes` `{password}` → regenera (`GenerateNewRecoveryCodes`).
- `DELETE /api/user/two-factor` `{password}` → `204` (`DisableTwoFactorAuthentication`); el siguiente login vuelve al código por email.
- Contraseña incorrecta → `422` en `password`.

- [ ] **Step 1: Tests que fallan:** `it('enables and confirms TOTP')` (tras confirmar, `two_factor_confirmed_at` no nulo y 8 códigos), `it('rejects enabling with a wrong password')`, `it('rejects confirming with a wrong code')`, `it('regenerates recovery codes')` (difieren de los anteriores), `it('disables TOTP so the next login uses email')` (login posterior → `method === 'email'`).
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar con las acciones de Fortify (`Laravel\Fortify\Actions\*`); `config/fortify.php` con `Features::twoFactorAuthentication(['confirm' => true])` y `'views' => false`.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat: add TOTP enable, confirm, recovery codes and disable endpoints`.

---

### Task 5: Catálogo de ejercicios y plantillas

**Files:**
- Create: `app/Domain/Training/Exercise.php` + migración (`id`, `code` string unique, `name`, `unilateral` bool default false, `timestampsTz`)
- Create: `app/Domain/Training/WorkoutTemplate.php` + migración (`id` uuid pk, `user_id` fk cascade, `name`, `mode` string `time|reps|choose`, `blocks` json, `timestampsTz`, `softDeletesTz`)
- Create: `app/Domain/Training/ExerciseCode.php` (valor: `fromName(string $name): string` → slug MAYÚSCULAS con `_`, p. ej. `"Cat-Cow Pose"` → `CAT_COW_POSE`; `isUnilateralName(string $name): bool` → empieza por `"One "` o `"Single "`)
- Create: `app/Http/Requests/Training/UpsertTemplateRequest.php`, `app/Application/Actions/Training/UpsertTemplate.php`, `app/Http/Controllers/Api/ExerciseController.php`, `TemplateController.php`, `app/Http/Resources/ExerciseResource.php`, `TemplateResource.php`
- Test: `tests/Unit/ExerciseCodeTest.php`, `tests/Feature/Training/ExercisesTest.php`, `tests/Feature/Training/TemplatesTest.php`

**Interfaces** (documentar en *Plantillas* del contrato):
- Documento plantilla (entrada y salida):
  ```json
  {"id":"uuid","name":"Series de fuerza","mode":"time|reps|choose",
   "blocks":[{"kind":"warmup|main|cooldown","rounds":1,"round_rest_seconds":0,
     "items":[{"exercise_code":"DEADLIFT","unilateral":false,
       "time":{"work_seconds":40,"rest_seconds":20}|null,
       "reps":{"sets":3,"reps":12,"weight_kg":null,"set_rest_seconds":60}|null}]}],
   "updated_at":"ISO-8601","deleted_at":null}
  ```
- Reglas de validación: `blocks` 1–3, `kind` único por plantilla y en orden `warmup → main → cooldown`; `rounds` ≥ 1; `items` ≥ 1; `exercise_code` existe; `warmup`/`cooldown` exigen `time`; `main` exige `time` si `mode=time`, `reps` si `mode=reps`, ambos si `mode=choose`; `work_seconds` 5–600, `rest_seconds` 0–600, `sets` 1–20, `reps` 1–200, `weight_kg` null o 0–500, `set_rest_seconds` 0–600.
- `GET /api/exercises` → `[{code, name, unilateral}]` ordenado por `name`.
- `PUT /api/templates/{uuid}` → upsert del documento (201 si nuevo, 200 si existía, restaura si estaba borrada); `DELETE /api/templates/{uuid}` → soft delete, 204. Plantilla de otro usuario → 404.
- `ExerciseCode::fromName`, `ExerciseCode::isUnilateralName` los usa también la Task 7.

- [ ] **Step 1: Tests que fallan:** `ExerciseCodeTest` (`"Cat-Cow Pose"` → `CAT_COW_POSE`, `"Romanian Deadlift"` → `ROMANIAN_DEADLIFT`, `isUnilateralName("One Arm Row")` true, `("Single Leg Deadlift")` true, `("Deadlift")` false); `ExercisesTest` (`it('lists exercises sorted by name')`, `it('requires auth')` → 401); `TemplatesTest` (`it('creates a template with 201 and updates it with 200')`, `it('rejects a reps template whose main block lacks reps')` → 422 en `blocks.1.items.0.reps`, `it('rejects a warmup item without time')`, `it('requires both time and reps in choose mode')`, `it('rejects an unknown exercise code')`, `it('soft deletes and restores on upsert')`, `it('hides other users templates')` → 404).
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat: add exercise catalog and template upsert/delete`.

---

### Task 6: Sesiones, sincronización y estadísticas

**Files:**
- Create: `app/Domain/Training/WorkoutSession.php` + migración (`id` uuid pk, `user_id` fk cascade, `workout_template_id` uuid nullable sin fk, `name`, `mode` string `time|reps`, `source` string `fitify|app`, `source_key` string nullable unique, `started_at` tz, `ended_at` tz, `duration_seconds` unsignedInteger, `kcal` unsignedSmallInteger, `blocks` json, `timestampsTz`)
- Create: `app/Http/Requests/Training/StoreSessionRequest.php`, `app/Application/Actions/Training/StoreSession.php`, `app/Application/Actions/Training/BuildSyncPayload.php`, `app/Application/Actions/Training/WeeklyStats.php`, `app/Http/Controllers/Api/SessionController.php`, `SyncController.php`, `StatsController.php`, `app/Http/Resources/SessionResource.php`
- Test: `tests/Feature/Training/SessionsTest.php`, `SyncTest.php`, `WeeklyStatsTest.php`

**Interfaces** (documentar en *Sesiones* y *Sync* del contrato):
- Documento sesión:
  ```json
  {"id":"uuid","template_id":"uuid|null","name":"Series de fuerza","mode":"time|reps",
   "source":"fitify|app","started_at":"ISO","ended_at":"ISO","duration_seconds":3300,"kcal":468,
   "blocks":[{"kind":"warmup|main|cooldown","skipped":false,
     "items":[{"exercise_code":"DEADLIFT","skipped":false,
       "sets":[{"reps":12,"weight_kg":10}]|null,"work_seconds":40|null}]}],
   "created_at":"ISO"}
  ```
- `PUT /api/sessions/{uuid}` → 201 al crear; si el id ya existe para ese usuario → **200 con el existente, sin modificar**. `source` del cliente siempre se guarda como `app`.
- `GET /api/sync?since=ISO` → `{server_time, exercises:[...], templates:[...con deleted_at], sessions:[...]}`; sin `since` devuelve todo (plantillas sin borradas). Filtra por `updated_at > since` (plantillas con `withTrashed`).
- `GET /api/stats/weekly?weeks=12` → `[{week_start:"YYYY-MM-DD", sessions, minutes, kcal}]` semanas lunes–domingo en `Europe/Madrid`, más reciente primero, incluye semanas vacías.

- [ ] **Step 1: Tests que fallan:** `it('stores a session with 201')`, `it('returns 200 and keeps the original on a repeated PUT')` (el segundo PUT con `kcal` distinto no cambia `kcal`), `it('forces source app')`, `it('validates blocks shape')` (sin `ended_at` → 422); `SyncTest`: `it('returns everything without since')`, `it('returns only changes after since')`, `it('includes deleted templates with deleted_at')`, `it('isolates users')`; `WeeklyStatsTest`: sesiones el domingo 25/10/26 23:30 Madrid (`2026-10-25T22:30:00Z`) y el lunes 26/10/26 00:30 Madrid (`2026-10-25T23:30:00Z`) caen en semanas distintas (`2026-10-19` y `2026-10-26`); semana vacía aparece con ceros.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Commit `feat: add idempotent sessions, incremental sync and weekly stats`.

---

### Task 7: Importación desde Fitify

**Files:**
- Create: `app/Application/Actions/Import/GroupFitifyEntries.php`, `app/Application/Actions/Import/ImportFitifyHistory.php`, `app/Application/Actions/Import/DefaultTemplateFactory.php`, `app/Console/Commands/FitifyImportCommand.php`
- Create: `tests/Fixtures/fitify/entrenos.json` (copia de `~/fitify_export/entrenos.json`)
- Test: `tests/Unit/Import/GroupFitifyEntriesTest.php`, `tests/Unit/Import/DefaultTemplateFactoryTest.php`, `tests/Feature/Import/FitifyImportCommandTest.php`

**Interfaces:**
- Entrada: array de `{fecha: "2026-11-10T06:10:00", nombre, minutos, calorias, num_ejercicios, ejercicios: string[]}` (fecha sin zona = `Europe/Madrid`).
- `GroupFitifyEntries::handle(array $entries): array<FitifyGroup>` donde `FitifyGroup` = `{key: string, startedAt: CarbonImmutable, warmup: ?array, main: ?array, cooldown: ?array}`.
  Algoritmo: ordenar ascendente; recorrer por día natural en Madrid; `"Calentamiento"` → warmup, `"Estiramiento corporal completo"` → cooldown, resto → main. Abre grupo nuevo si la entrada es warmup, o si es main y el grupo ya tiene main o cooldown, o si el grupo ya tiene cooldown. `key = "fitify:" . fecha de la primera entrada`.
- `DefaultTemplateFactory::forGroup(FitifyGroup $group): array` (documento plantilla de la Task 5). Valores del spec:
  - warmup: `time {30, 0}`, `rounds 1`; cooldown: `time {40, 0}`, `rounds 1`.
  - main "Intervalos de fuerza": `mode time`, `time {40, 20}`, `rounds = max(1, round(minutos*60 / Σ(work+rest)))`, `round_rest_seconds 60`.
  - main "Series de fuerza": `mode reps`, `reps {3, 12, null, 60}`.
  - main "Tabata": `mode choose`, `time {20, 10}` con `rounds 8`, `reps {3, 12, null, 60}`.
  - cualquier otro main: `mode time`, como Intervalos.
  - sin main: `mode time`.
  - `unilateral = ExerciseCode::isUnilateralName(nombre)`; nombres decodificados con `html_entity_decode`.
  - nombre de plantilla: `"{main o primer bloque} · dd/mm"`.
- `ImportFitifyHistory::handle(User $user, array $entries): ImportResult {sessions, templates, exercises}` — crea ejercicios que falten, una plantilla y una sesión por grupo (`source fitify`, `source_key = key`, `duration_seconds = Σ minutos·60`, `kcal = Σ calorías`, `mode` = `reps` si el modo de la plantilla es `reps`, si no `time`); si `source_key` ya existe, salta el grupo.
- `php artisan fitify:import {path} {--user=}` (email; por defecto el único usuario) → imprime `Sesiones: N · Plantillas: N · Ejercicios nuevos: N`.

- [ ] **Step 1: Tests que fallan:** `GroupFitifyEntriesTest` con el fixture: **11** grupos, el del 10/11/26 tiene warmup 06:06 + main "Series de fuerza" + cooldown 07:10, el del 14/10/26 solo cooldown, el del 21/10/26 tiene warmup + "Tabata" + cooldown; `DefaultTemplateFactoryTest`: Intervalos de 20 min con 9 ejercicios → `rounds = 2` (1200 / 540 = 2,2), Tabata → `mode choose` con ambos valores, `"One Arm Row"` → `unilateral true`; `FitifyImportCommandTest`: `it('imports 11 sessions')`, `it('is idempotent')` (segunda ejecución → mismas cuentas en BD), `it('sums duration and kcal')` (grupo 10/11 → 67 min · 504 kcal), plantillas generadas pasan la validación de `UpsertTemplateRequest`.
  > Cuentas verificadas contra el fixture (30 entradas → 11 grupos): el 19/10 no tiene cooldown; el 14/10 es solo cooldown (su warmup y main no se extrajeron). Intervalos del 09/11: 20 min, 9 ejercicios.
- [ ] **Step 2:** Ejecutar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Ejecutar → PASS.
- [ ] **Step 5:** Ejecutar en local contra Sail: `sail artisan migrate:fresh --seed && sail artisan fitify:import ~/fitify_export/entrenos.json` → cuentas iguales al test.
- [ ] **Step 6:** Commit `feat: add Fitify history import`.

---

### Task 8: Cierre de la API

**Files:**
- Modify: `README.md` (arranque con Sail, crear usuario, importar, Mailpit en `http://localhost:8025`), `docs/api-contract.md` (revisión completa), `config/cors.php` (orígenes `capacitor://localhost`, `http://localhost`, `http://localhost:5173`)
- Test: `tests/Feature/CorsTest.php`

- [ ] **Step 1: Test que falla:** preflight `OPTIONS /api/auth/login` con `Origin: http://localhost` → cabecera `Access-Control-Allow-Origin: http://localhost`.
- [ ] **Step 2:** Ejecutar → FAIL; configurar CORS; → PASS.
- [ ] **Step 3:** `php artisan test` completo y `vendor/bin/pint --test` → todo verde.
- [ ] **Step 4:** Commit `docs: document setup and API contract; configure CORS for the app`.
