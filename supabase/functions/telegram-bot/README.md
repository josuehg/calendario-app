# Bot de Telegram — comandos bajo demanda

Edge Function (Deno/TypeScript) que corre en tu propio proyecto de Supabase
y responde en el momento cuando alguien escribe uno de estos comandos en el
grupo de Telegram:

- `/hoy` — pagos de hoy
- `/manana` — pagos de mañana
- `/semana` — resumen de los próximos 7 días
- `/meses` — totales por semana del mes actual y el próximo
- `/atrasados` — lo vencido que aún no se paga, con días de atraso
- `/pagados` — lo pagado esta semana; `/pagados 1` = la semana pasada, `/pagados 2` = hace dos semanas, etc.
- `/resumen` — panorama rápido: hoy + atrasados + total de los próximos 7 días, en un solo mensaje
- `/ingreso <sucursal> <monto> [fecha]` — registra una venta/cobro del día. Ej: `/ingreso 1 1500` (Sucursal 1, hoy) o `/ingreso 2 980 2026-10-25`. Escribe `/ingreso` solo para ver la lista de sucursales numeradas.
- `/saldo` — saldo de caja real y cuánto queda disponible para comprometer en un pedido nuevo (requiere configurar el saldo inicial una vez, en la app → Configuración)

`/ingreso` es el único comando que **escribe** datos — cualquiera en el
grupo puede usarlo, no hay un control de permisos más fino que "está en
el grupo de Telegram del negocio" (igual que los demás comandos leen datos
sin restricción). Queda registrado con el nombre de quien lo escribió
(`registered_by`) y `source: "bot"`, visible también en la página Ingresos
de la app.

Reusa la misma lógica de fechas que la app (`utils.get_payment_events` /
`utils.compute_cash_balance`): una letra "vive" en vencimiento + plazo
típico de pago, y se considera vencida solo pasado vencimiento + plazo
máximo de gracia (configurables en Configuración de la app).

No afecta el reporte diario automático (`scripts/telegram_daily_report.py`
+ GitHub Actions) — son dos cosas separadas que conviven: una empuja el
reporte todos los días a las 9:30am, esta otra responde bajo demanda.

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
   ```
   `TELEGRAM_WEBHOOK_SECRET` es un valor que tú inventas (ej. una cadena
   larga random) — sirve para que nadie más pueda llamar a tu función
   haciéndose pasar por Telegram. Guárdalo, lo necesitas en el paso 5.

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

7. **(Opcional, pero recomendado) Registrar el menú de comandos en Telegram:**
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
       {"command":"pagados","description":"Lo pagado esta semana (o N semanas atrás)"},
       {"command":"resumen","description":"Panorama rápido: hoy + atrasados + semana"},
       {"command":"ingreso","description":"Registrar venta/cobro de una sucursal"},
       {"command":"saldo","description":"Saldo de caja y disponible para comprometer"}
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
