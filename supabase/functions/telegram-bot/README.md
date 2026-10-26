# Bot de Telegram — comandos bajo demanda

Edge Function (Deno/TypeScript) que corre en tu propio proyecto de Supabase
y responde en el momento cuando alguien escribe uno de estos comandos en el
grupo de Telegram:

- `/hoy` — pagos de hoy
- `/manana` — pagos de mañana
- `/semana` — resumen de los próximos 7 días
- `/atrasados` — lo vencido que aún no se paga, con días de atraso

Reusa la misma lógica de fechas que la app (`utils.get_payment_events`):
una letra "vive" en vencimiento + plazo típico de pago, y se considera
vencida solo pasado vencimiento + plazo máximo de gracia (configurables en
Configuración de la app).

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
