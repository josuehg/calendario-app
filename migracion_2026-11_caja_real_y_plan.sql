-- Caja real separada de la caja del plan, y colchón de caja para Compras del día.
--   caja_credito_incluido: cuánto del crédito del plan ya está dentro de la caja real
--                          (el Simulador lo resta, porque suma el crédito aparte).
--   compras_colchon:       caja que no se toca al calcular cuánto se puede pedir.
alter table app_settings add column if not exists caja_credito_incluido numeric not null default 0;
alter table app_settings add column if not exists compras_colchon numeric not null default 0;
