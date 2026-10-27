-- Un local cerrado un día vendió 0 — es un dato válido (evita que el aviso
-- de "falta registrar ingreso" salga por error) y antes la tabla lo rechazaba
-- (check amount > 0). Se relaja a >= 0 (solo bloquea negativos).
alter table incomes drop constraint if exists incomes_amount_check;
alter table incomes add constraint incomes_amount_check check (amount >= 0);
