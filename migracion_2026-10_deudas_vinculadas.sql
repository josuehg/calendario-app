-- Vincula cada Deuda con su gasto fijo (préstamo) correspondiente, para no
-- repetir el nombre del acreedor y mantener la cuota mensual sincronizada
-- con lo que ya está registrado en Gastos Fijos.
alter table debts add column if not exists fixed_expense_id int references fixed_expenses(id) on delete set null;
