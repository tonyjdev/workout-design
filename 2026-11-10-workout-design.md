# Workout — diseño (API + app móvil)

Fecha: 2026-11-10 · Estado: borrador pendiente de aprobación

## 1. Intención

Sustituir Fitify para los entrenos en casa de un único usuario (Tony). Se parte de los 30 entrenos
completados que se extrajeron de Fitify (`~/fitify_export/entrenos.json`, del 14/10/26 al 10/11/26)
y se quiere poder **verlos** y **repetirlos**, registrando cada repetición en el historial.

Se empieza de cero con el stack de los proyectos recientes (`takemanager-app`, `controlpanel`).
Los repos anteriores (`workout-app-web`, `workout-app`, `workout-api`) se archivan en GitHub
(confirmación explícita antes de hacerlo); `workout-app-web` queda como referencia del reproductor
con voz (TTS, keep-awake, cuenta atrás).

## 2. Objetivos, no objetivos y anti-objetivos

**Objetivos v1**
- Importar el historial de Fitify y mostrarlo: lista, detalle (bloques y ejercicios) y estadísticas
  semanales de minutos y kcal.
- Repetir cualquier entreno del historial con un reproductor de dos modos (tiempo / repeticiones).
- Registrar cada sesión completada (incluidas reps y peso reales en modo repeticiones).
- Funcionar sin conexión durante el entreno.

**No objetivos v1**
- Planes por semanas/días tipo "Semana 11 de 12" (posible v2 sobre la misma base).
- Imágenes, vídeos o descripciones de ejercicios.
- Varios usuarios, roles o compartir.
- Sincronización bidireccional con edición en varios dispositivos.
- Despliegue en servidor (se decide más adelante).

**Anti-objetivos** (sería un fracaso aunque funcione)
- Que no se pueda entrenar o guardar una sesión por falta de conexión.
- Que la pantalla se apague o el reproductor se pare a mitad de entreno.
- Que una sesión completada se pierda antes de sincronizarse.

## 3. Proyectos y stack

Dos repos nuevos en GitHub (`tonyjdev`), nombres a confirmar (propuesta: `workout-api` y
`workout-app` tras archivar/renombrar los actuales).

| | API | App |
|---|---|---|
| Base | Laravel 13, PHP 8.4+ | Vue 3 + TypeScript + Vite |
| UI | — (solo JSON) | Tailwind 4 + shadcn-vue (new-york-v4, lucide) |
| Auth | Fortify + Sanctum (tokens Bearer) | login con token guardado en el dispositivo |
| Tests | Pest | Vitest |
| Empaquetado | Sail en local; Dockerfile + compose preparados | Capacitor 7, Android |
| Gestor | composer | pnpm |

Convenciones (Pint, ESLint/Prettier, estructura de carpetas, `components.json`) copiadas de
`controlpanel`/`takemanager-app`. Inertia y Wayfinder no aplican: la app es una SPA separada que
consume una API REST.

## 4. Modelo de dominio

- **Ejercicio** (catálogo): nombre (en inglés, tal como viene de Fitify), código único derivado del
  nombre y marca `unilateral`. Sin media ni material en v1 *(decisión del diseñador: el export no
  trae material y nada en v1 lo usa)*.
  - `unilateral` se deduce al importar por el prefijo "One "/"Single " y se puede corregir en el
    editor de plantilla *(decisión del diseñador)*. En modo tiempo, el reproductor parte el tiempo
    de trabajo en dos mitades con aviso "cambia de lado"; en modo reps, las reps son **por lado**.
- **Plantilla de entreno**: nombre ("Series de fuerza", "Intervalos de fuerza", "Tabata"…),
  **modo** (`tiempo` | `repeticiones` | `elegir al empezar`) y **3 bloques ordenados**:
  calentamiento, principal y estiramiento. Cada bloque tiene ejercicios ordenados.
  - Calentamiento y estiramiento van siempre por tiempo.
  - El modo de la plantilla aplica al bloque principal.
- **Recorrido del bloque** (decidido por Tony):
  - modo tiempo → **circuito**: A→B→C y se repite la vuelta. Las **rondas** y el descanso entre
    rondas son datos del **bloque**.
  - modo repeticiones → **ejercicio a ejercicio**: todas las series de A, luego B…
- **Ejercicio dentro de un bloque**:
  - modo tiempo: segundos de trabajo y segundos de descanso tras el ejercicio.
  - modo repeticiones: series, reps objetivo, peso objetivo opcional (kg), descanso entre series.
  - Una plantilla en modo "elegir al empezar" (Tabata) guarda los dos juegos de valores.
- **Sesión**: instancia realizada de una plantilla: inicio, fin, duración real, kcal, origen
  (`fitify` | `app`), bloques realizados/saltados y, por ejercicio, lo realizado (series con reps y
  peso reales en modo repeticiones).

Rutina habitual de referencia: Día 1 Intervalos de fuerza (tiempo), Día 2 Series de fuerza (reps),
Día 3 Tabata (tiempo o reps), Día 4 Series de fuerza (reps). No se modela como plan en v1.

## 5. Importación desde Fitify

Comando de la API que lee `entrenos.json` (formato actual: `fecha`, `nombre`, `minutos`, `calorias`,
`num_ejercicios`, `ejercicios[]`).
- Agrupa por día las entradas Calentamiento + principal + Estiramiento consecutivas en **una sesión
  de 3 bloques**. Si falta alguno, la sesión queda con los bloques que haya.
- Crea los ejercicios que no existan en el catálogo.
- Crea una plantilla por cada sesión importada (nombre + fecha), para poder repetirla tal cual.
- Duración de la sesión = suma de minutos; kcal = suma de calorías.
- Valores por defecto de la plantilla (editables después):
  - calentamiento: 30 s por ejercicio, sin descanso
  - estiramiento: 40 s por ejercicio, sin descanso
  - Intervalos de fuerza: 40 s trabajo / 20 s descanso, rondas ajustadas para acercarse a los
    minutos registrados
  - Series de fuerza: 3 × 12, descanso 60 s, sin peso
  - Tabata: modo "elegir al empezar"; tiempo 20/10 × 8 rondas; reps 3 × 12
- Idempotente: reimportar no duplica (clave: fecha y hora de la entrada de Fitify).

## 6. App móvil

**Pantallas**
1. Login en dos pasos: email+contraseña y después código (TOTP/recuperación, o el recibido por email
   si no hay TOTP configurado). El login necesita conexión; una vez dentro, el token se guarda en el
   dispositivo y la app funciona offline.
2. Entrenar: lista de plantillas (nombre, modo, duración estimada, última vez realizada).
3. Historial: lista por semanas, con minutos y kcal semanales arriba.
4. Detalle de sesión: bloques, ejercicios y lo realizado; botón "Repetir" (abre su plantilla).
5. Previa del entreno: al empezar se muestran los valores y se pueden **ajustar solo para esa vez**
   (no cambia la plantilla); en Tabata se elige aquí el modo.
6. Editor de plantilla (acceso desde Entrenar): cambios permanentes de nombre, modo, rondas y
   valores por ejercicio. Permite duplicar y borrar plantillas.
7. Reproductor.
8. Ajustes: voz, sonidos, URL de la API, cerrar sesión y **Seguridad**: activar TOTP (QR + confirmar
   código), ver/regenerar códigos de recuperación y desactivarlo.

**Progresión en modo repeticiones** (decidido por Tony): al preparar un entreno, reps y peso
objetivo se precargan con lo **último realizado** en ese ejercicio dentro de esa plantilla; si nunca
se ha hecho, se usan los valores de la plantilla. Calculado en el móvil con el historial local.

**Reproductor**
- Recorre los 3 bloques seguidos; se puede saltar un bloque o un ejercicio.
- Modo tiempo: cuenta atrás de trabajo y descanso, avisos por voz (siguiente ejercicio, últimos
  segundos) y sonidos.
- Modo repeticiones: muestra serie actual, reps y peso objetivo; se apuntan reps y peso reales y se
  pulsa "hecho", lo que lanza el temporizador de descanso.
- Pantalla siempre encendida (keep-awake) mientras dura el entreno.
- Pausa/reanudar; si la app se cierra a mitad, al volver ofrece continuar.
- Al terminar: resumen y guardado de la sesión. kcal estimadas (método a decidir por el builder,
  p. ej. kcal/min medio de las sesiones importadas del mismo tipo).

**Primero en el móvil (offline)**
- Plantillas, catálogo e historial se descargan y se guardan localmente.
- Las sesiones completadas se guardan en local y en una cola de envío; se suben al recuperar
  conexión (al abrir la app y periódicamente). Cada sesión lleva un UUID generado en el móvil para
  que reenviarla no duplique.
- Los cambios en plantillas hechos en el móvil también pasan por la cola. Un único dispositivo, así
  que no se resuelven conflictos: gana el último cambio.

## 7. API

- Auth: login → token Sanctum; logout; `me`. Sin registro público (usuario creado por seeder/comando).
- **Doble factor obligatorio en todo login** (decidido por Tony):
  - Si el usuario tiene **TOTP** configurado (app autenticadora, vía Fortify), se pide ese código o
    un código de recuperación.
  - Si **no** lo tiene configurado, la API envía un **código por email** de un solo uso con caducidad
    corta y se pide ese código.
  - Flujo en dos pasos: email+contraseña devuelve un reto temporal (sin token de acceso) indicando el
    método; el código válido canjea el reto por el token Sanctum. Límite de intentos en ambos pasos.
  - Endpoints protegidos para activar TOTP (secreto/QR, confirmación con código), regenerar códigos
    de recuperación y desactivarlo.
  - Correo: en local, Mailpit de Sail; el servicio real de envío se decide con el despliegue.
- Endpoints REST protegidos para: ejercicios (lectura), plantillas (CRUD), sesiones (lectura,
  alta idempotente por UUID), estadísticas semanales.
- Endpoint de sincronización incremental (cambios desde una fecha) para que la app refresque su
  copia local.
- Tests Pest por endpoint: caso feliz, validación y autorización.

## 8. Lo que queda a decisión del builder
- Almacenamiento local de la app (p. ej. SQLite de Capacitor o IndexedDB) y estructura de la cola.
- Esquema concreto de tablas y forma exacta de los endpoints.
- Plugin de TTS y de keep-awake (en `workout-app-web` se usaron `@capacitor-community/text-to-speech`
  y `@capacitor-community/keep-awake`).
- Diseño visual dentro de shadcn-vue.
- Método de estimación de kcal.

## Dudas resueltas
| # | Duda | Decisión |
|---|---|---|
| 1 | ¿Reutilizar los repos existentes o empezar de cero? | De cero, con el stack actual (Tailwind, shadcn, Laravel 13…) |
| 2 | ¿App instalada (APK) o web Inertia (PWA)? | 2 proyectos: API Laravel + app Vue con Capacitor |
| 3 | ¿Qué hacer con los repos actuales? | Archivar (recomendado); confirmar antes de tocarlos |
| 4 | Alcance v1 | Historial + repetir entrenos (sin planes) |
| 5 | ¿Cómo se definen los tiempos? | Mixto: por tiempo o por series/reps según el entreno |
| 6 | Modo por tipo | Intervalos de fuerza: tiempo · Series de fuerza: reps · Tabata: a veces tiempo, a veces reps |
| 7 | Calentamiento + principal + estiramiento | Una sola sesión con 3 bloques |
| 8 | Sin conexión | Primero en el móvil, con cola de sincronización |
| 9 | Despliegue de la API | Más adelante; local con Sail y Docker preparado |
| 10 | Recorrido del bloque | Circuito en modo tiempo; ejercicio a ejercicio en modo reps |
| 11 | Objetivo de reps/peso al repetir | Precargar lo último realizado |
| 12 | Elegir y editar entrenos | Pantalla "Entrenar" con lista; ajustes puntuales al empezar; edición permanente aparte |
| 13 | Doble factor en el login | Obligatorio: TOTP si está configurado; si no, código por email |
| 14 | Dónde se activa el TOTP | En Ajustes de la app (QR, códigos de recuperación, desactivar) |
| 15 | Descansos automáticos (cambio post-v1) | Ajustes globales que sustituyen al descanso por ejercicio: 15 s entre ejercicios en el bloque principal, 5 s en calentamiento/enfriamiento y 5 s para cambiar de lado en ejercicios unilaterales por tiempo; el descanso entre series se mantiene; entre bloques, pantalla de continuar sin descanso |

## Decisiones del diseñador (a revisar)
- Ejercicios unilaterales: detectados por nombre, tiempo partido con aviso "cambia de lado", reps por lado.
- Sin campo de material en v1.
- Fechas del export en hora de Madrid (Europe/Madrid); semanas de lunes a domingo; peso en kg.
- Clave de idempotencia de una sesión importada: fecha y hora de su primera entrada.
- Los nombres con `&amp;` del export se decodifican al importar.
- Nombres de ejercicio: la UI y la voz usan siempre `name`; si falta, se humaniza el código (`JUMPING_JACKS` → "Jumping jacks").
- Pantalla entre bloques: resumen (ejercicios, series, tiempo) y siguiente bloque; botón Continuar.
- Orientación: todo en vertical salvo el reproductor (vertical u horizontal).
- En desarrollo, el APK habla con la API local por HTTP (cleartext permitido solo en build de desarrollo).
