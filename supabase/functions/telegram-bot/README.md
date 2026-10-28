# Bot de Telegram — comandos bajo demanda

Edge Function (Deno/TypeScript) que corre en tu propio proyecto de Supabase
y responde en el momento cuando alguien escribe uno de estos comandos en el
grupo de Telegram:

- `/hoy` — pagos de hoy
- `/manana` — pagos de mañana
- `/semana` — resumen de los próximos 7 días
- `/meses` — totales por semana del mes actual y el próximo
- `/atrasados` — lo vencido que aún no se paga, con días de atraso
- `/ventana` — letras que ya vencieron por contrato pero siguen dentro del plazo **típico** de pago (ej. 8 días) — tu ventana normal con el proveedor. El plazo **máximo** de gracia (ej. 10 días) es aparte, solo para cuándo se marca "oficialmente" atrasada en `/atrasados`.
- `/pagados` — lo pagado esta semana; `/pagados 1` = la semana pasada, `/pagados 2` = hace dos semanas, etc.
- `/resumen` — panorama rápido: hoy + atrasados + total de los próximos 7 días, en un solo mensaje
- `/ingreso <sucursal> <monto> [fecha]` — registra una venta/cobro del día. Ej: `/ingreso 1 1500` (Sucursal 1, hoy) o `/ingreso 2 980 2026-10-25`. Escribe `/ingreso` solo para ver la lista de sucursales numeradas.
- `/pagar <N> [fecha]` — marca como pagado el ítem **N** de la última lista numerada que viste (`/hoy`, `/manana`, `/atrasados`, `/ventana` o `/resumen`). Ej: ves `/hoy` y el ítem 2 es el que acabas de pagar → `/pagar 2` (o `/pagar 2 2026-10-25` con otra fecha). La lista vale por 2 horas; si pasó más tiempo, pide una lista fresca otra vez.
- `/saldo` — saldo de caja real y cuánto queda disponible para comprometer en un pedido nuevo (requiere configurar el saldo inicial una vez, en la app → Configuración)
- `/simular <plazo_dias> [monto]` — ¿cuánto puedes comprometer con un proveedor a ese plazo (30/45/60/75/90 días)? Revisa tu caja semana por semana desde hoy hasta la fecha en que vencería esa compra, y usa la semana más ajustada del camino (no solo el día final) como límite real. Ej: `/simular 60` o `/simular 60 5000` para además saber si 5000 te alcanza. Mismo cálculo que el simulador de Presupuesto.

`/ingreso` y `/pagar` son los únicos comandos que **escriben** datos —
cualquiera en el grupo puede usarlos, no hay un control de permisos más
fino que "está en el grupo de Telegram del negocio" (igual que los demás
comandos leen datos sin restricción). `/ingreso` queda registrado con el
nombre de quien lo escribió (`registered_by`) y `source: "bot"`, visible
también en la página Ingresos de la app. `/pagar` necesita la tabla
`bot_list_cache` (ver `migracion_2026-10_bot_pagar.sql`), donde se guarda
la última lista numerada mostrada a cada chat.

Reusa la misma lógica de fechas que la app (`utils.get_payment_events` /
`utils.compute_cash_balance`): una letra "vive" en vencimiento + plazo
típico de pago, y se considera vencida solo pasado vencimiento + plazo
máximo de gracia (configurables en Configuración de la app).

Esta misma función también manda el **reporte diario** (pagos de hoy +
atrasados + aviso de sucursales sin ingreso registrado de ayer) a las
9:30am hora de Perú — antes lo mandaba un workflow de GitHub Actions
(`scripts/telegram_daily_report.py`), pero su scheduler gratuito no
garantiza la hora (puede atrasarse varias horas sin avisar). Ahora lo
dispara un cron de **Supabase** (pg_cron + pg_net), que es parte del mismo
proyecto y no depende de GitHub — ver el paso 6 más abajo.

## Despliegue (una sola vez)

Todo esto se corre en **terminal**, parado en la raíz del repo
(`calendario-app/`). Necesitas Node.js instalado (ya lo tienes) — se usa
`npx supabase` para no instalar nada globalmente.

1. **Login en Supabase CLI** (abre el navegador para autenticarte):
   ```bash
   npx supabase login
   ```

2. **Vincular el proyecto** (reemplaza `<PROJECT_REF>` por tu Project ID,
   el que viste en Supabase → Settings → General, ej. `otdap1234`):
   ```bash
   npx supabase link --project-ref <PROJECT_REF>
   ```

3. **Poner los secrets propios de la función** (no los de Supabase — esos
   los inyecta Supabase solo). Reemplaza por tus valores reales:
   ```bash
   npx supabase secrets set TELEGRAM_BOT_TOKEN="TU_TOKEN_DE_BOTFATHER"
   npx supabase secrets set TELEGRAM_WEBHOOK_SECRET="INVENTA_UNA_CLAVE_LARGA_AL_AZAR"
   npx supabase secrets set TELEGRAM_CHAT_ID="-100XXXXXXXXXX"
   npx supabase secrets set CRON_SECRET="INVENTA_OTRA_CLAVE_LARGA_AL_AZAR"
   ```
   `TELEGRAM_WEBHOOK_SECRET` y `CRON_SECRET` son valores que tú inventas
   (cadenas largas random, distintas entre sí) — sirven para que nadie más
   pueda llamar a tu función haciéndose pasar por Telegram o por el cron.
   Guárdalos, los necesitas en los pasos 5 y 6. `TELEGRAM_CHAT_ID` es el ID
   del grupo (el mismo que ya tenías si usabas el reporte por GitHub
   Actions) — a quién se le manda el reporte diario.

4. **Desplegar la función:**
   ```bash
   npx supabase functions deploy telegram-bot --no-verify-jwt
   ```
   El flag `--no-verify-jwt` es obligatorio: por defecto Supabase exige un
   login válido (JWT) en cada llamada a la función, pero Telegram no manda
   eso — manda nuestro propio `secret_token` en su lugar (que sí se valida
   dentro del código). Sin este flag, Telegram recibe "401 Unauthorized" y
   el bot nunca responde, aunque el `setWebhook` del paso 5 haya salido OK.

   Al terminar te muestra la URL pública de la función, algo como:
   `https://<PROJECT_REF>.supabase.co/functions/v1/telegram-bot`

5. **Registrar la URL como webhook de Telegram** (reemplaza `<TU_TOKEN>`,
   `<URL_DEL_PASO_4>` y `<TU_WEBHOOK_SECRET>` del paso 3):
   ```bash
   curl -F "url=<URL_DEL_PASO_4>" -F "secret_token=<TU_WEBHOOK_SECRET>" "https://api.telegram.org/bot<TU_TOKEN>/setWebhook"
   ```
   Debe responder `{"ok":true,"result":true,...}`.

6. **Probar:** escribe `/hoy` en el grupo de Telegram. Debería responder
   en segundos.

7. **Programar el reporte diario (cron de Supabase):** abre
   `supabase/sql/cron_reporte_diario.sql`, reemplaza los 2 placeholders que
   indica ahí (`<FUNCTION_URL>` con la URL del paso 4, `<CRON_SECRET>` con
   el valor del paso 3), y corre el archivo completo en: **Supabase → tu
   proyecto → SQL Editor → New query → Run**. Se ejecuta una sola vez —
   queda programado para siempre a las 9:30am hora de Perú, sin depender de
   GitHub Actions.

   Para probarlo sin esperar al cron, llama a la función directo (reemplaza
   `<FUNCTION_URL>` y `<TU_CRON_SECRET>`):
   ```bash
   curl -X POST "<FUNCTION_URL>" -H "Content-Type: application/json" \
     -d "{\"type\":\"daily_report\",\"cron_secret\":\"<TU_CRON_SECRET>\"}"
   ```
   Debería llegar el reporte al grupo en segundos.

8. **(Opcional, pero recomendado) Registrar el menú de comandos en Telegram:**
   para que al escribir "/" en el chat te salga un menú con los comandos y
   su descripción, en vez de tener que acordarte de cada nombre. Reemplaza
   `<TU_TOKEN>`:
   ```bash
   curl -X POST "https://api.telegram.org/bot<TU_TOKEN>/setMyCommands" \
     -H "Content-Type: application/json" \
     -d '{"commands":[
       {"command":"hoy","description":"Pagos de hoy"},
       {"command":"manana","description":"Pagos de mañana"},
       {"command":"semana","description":"Próximos 7 días"},
       {"command":"meses","description":"Por semana: este mes y el próximo"},
       {"command":"atrasados","description":"Lo vencido sin pagar"},
       {"command":"ventana","description":"Letras vencidas aun no atrasadas"},
       {"command":"pagados","description":"Lo pagado esta semana (o N semanas atrás)"},
       {"command":"resumen","description":"Panorama rápido: hoy + atrasados + semana"},
       {"command":"ingreso","description":"Registrar venta/cobro de una sucursal"},
       {"command":"pagar","description":"Marcar pagado el N de la ultima lista"},
       {"command":"saldo","description":"Saldo de caja y disponible para comprometer"},
       {"command":"simular","description":"Cuanto alcanza con un proveedor a X dias"}
     ]}'
   ```
   Debe responder `{"ok":true,"result":true,...}`. Solo hace falta correrlo
   una vez — no hay que repetirlo cada vez que se redespliega la función.

## Si algo falla

Ver logs en vivo de la función:
```bash
npx supabase functions logs telegram-bot
```

Confirmar que el webhook quedó bien registrado:
```bash
curl "https://api.telegram.org/bot<TU_TOKEN>/getWebhookInfo"
```
(si `last_error_message` tiene algo, ahí dice qué falló)
