-- Plan activo: el escenario del Simulador que usan Compras del día y el bot.
alter table app_settings add column if not exists plan_activo_id text;
