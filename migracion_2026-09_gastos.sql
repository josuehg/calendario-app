-- Migración: módulo de Gastos (fijos recurrentes + variables).
-- Supabase > SQL Editor > New query > pega todo > Run. Aditivo y re-ejecutable.

-- 1) Categorías de gasto (lista fija editable desde Configuración) ------------
create table if not exists expense_categories (
  id serial primary key,
  name text not null unique,
  sort_order int not null default 0
);
insert into expense_categories (name, sort_order) values
  ('Alquiler', 1), ('Servicios', 2), ('Planilla', 3), ('Impuestos', 4),
  ('Mantenimiento', 5), ('Transporte', 6), ('Otros', 99)
on conflict (name) do nothing;

-- 2) Plantillas de gasto fijo recurrente -----------------------------------
create table if not exists fixed_expenses (
  id serial primary key,
  name text not null,
  category text not null,
  branch text,                       -- null = general / oficina central
  amount numeric(12,2) not null check (amount > 0),
  pay_day int not null check (pay_day between 1 and 31),
  active boolean not null default true,
  start_month date,                  -- primer día del mes desde el que aplica
  end_month date,                    -- primer día del último mes (opcional)
  notes text,
  created_at timestamptz not null default now()
);

-- 3) Gastos concretos: instancias de los fijos + los variables manuales -----
create table if not exists expenses (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('fijo', 'variable')),
  fixed_expense_id int references fixed_expenses(id) on delete set null,
  period text,                       -- 'YYYY-MM' para instancias de gasto fijo
  name text not null,
  category text not null,
  branch text,
  amount numeric(12,2) not null check (amount > 0),
  due_date date not null,
  status text not null default 'pendiente' check (status in ('pendiente', 'pagado', 'omitido')),
  paid_at date,
  notes text,
  created_at timestamptz not null default now()
);

-- Evita generar dos veces el mismo gasto fijo para el mismo mes
create unique index if not exists uq_expenses_fixed_period
  on expenses (fixed_expense_id, period) where fixed_expense_id is not null;
create index if not exists idx_expenses_status on expenses(status);
create index if not exists idx_expenses_due_date on expenses(due_date);
