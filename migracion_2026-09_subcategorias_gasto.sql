-- Migración: subcategorías dentro de cada categoría de gasto (fijo y
-- variable), como base para un futuro estado de resultados por rubro.
-- Supabase > SQL Editor > New query > pega todo > Run. Aditivo y re-ejecutable.

-- Cada subcategoría pertenece a UNA categoría (por nombre, igual que
-- fixed_expenses.category / expenses.category se guardan como texto).
create table if not exists expense_subcategories (
  id serial primary key,
  category text not null,
  name text not null,
  sort_order int not null default 0,
  unique (category, name)
);

alter table fixed_expenses add column if not exists subcategory text;
alter table expenses add column if not exists subcategory text;
