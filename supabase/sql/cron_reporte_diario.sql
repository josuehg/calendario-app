-- Reporte diario de pagos por Telegram, disparado por un cron de Supabase
-- (pg_cron + pg_net) en vez del scheduler gratuito de GitHub Actions, que
-- no garantiza la hora — puede atrasarse varias horas sin avisar.
--
-- Corre esto UNA SOLA VEZ en: Supabase → tu proyecto → SQL Editor → New
-- query → Run. Antes de correrlo, reemplaza los 2 placeholders de abajo:
--
--   <FUNCTION_URL>  → la URL de tu función telegram-bot, la que te dio el
--                     deploy (algo como
--                     https://otdapxgxtormfwqjaiie.supabase.co/functions/v1/telegram-bot)
--   <CRON_SECRET>   → el MISMO valor que pusiste con:
--                     npx supabase secrets set CRON_SECRET="..."
--                     (inventa uno nuevo si todavía no lo pusiste — una
--                     cadena larga random, igual que TELEGRAM_WEBHOOK_SECRET)

create extension if not exists pg_cron with schema extensions;
create extension if not exists pg_net with schema extensions;

select cron.schedule(
  'reporte-diario-telegram',
  '30 14 * * *',  -- 9:30am hora de Perú (UTC-5), todos los días
  $$
  select net.http_post(
    url := '<FUNCTION_URL>',
    headers := jsonb_build_object('Content-Type', 'application/json'),
    body := jsonb_build_object('type', 'daily_report', 'cron_secret', '<CRON_SECRET>')
  );
  $$
);

-- Para revisar que quedó programado:
--   select * from cron.job;
--
-- Para ver el historial de ejecuciones (si falló, el error sale en 'return_message'):
--   select * from cron.job_run_details order by start_time desc limit 5;
--
-- Para desprogramarlo (si alguna vez hace falta):
--   select cron.unschedule('reporte-diario-telegram');
