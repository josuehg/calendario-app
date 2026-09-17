-- Migración: gastos fijos quincenales (dos pagos al mes, ej. planilla
-- quincenal), además del mensual (un solo pago) que ya existía.
-- Supabase > SQL Editor > New query > pega todo > Run. Aditivo y re-ejecutable.

alter table fixed_expenses add column if not exists frequency text not null default 'mensual';
alter table fixed_expenses add column if not exists pay_day_2 int;
