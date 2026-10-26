-- Plazo de gracia real para pagar letras: no se pagan exacto en su
-- vencimiento. letra_dias_pago_tipico se usa para ubicar la letra en
-- Calendario/Presupuesto (vencimiento + este plazo = fecha esperada de
-- pago); letra_dias_gracia_max define cuándo se considera de verdad vencida
-- (vencimiento + este plazo < hoy).
alter table app_settings add column if not exists letra_dias_pago_tipico int not null default 8;
alter table app_settings add column if not exists letra_dias_gracia_max int not null default 10;
