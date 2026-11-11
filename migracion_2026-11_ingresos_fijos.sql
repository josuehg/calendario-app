-- Ingresos fijos mensuales (p. ej. comisiones del agente BCP): una plantilla
-- con monto aproximado y la ventana de días en que suele llegar, y cada mes
-- se confirma lo que llegó de verdad. Van aparte de `incomes` (ventas de los
-- locales) para no inflar los indicadores ni el promedio de venta diaria.

create table if not exists fixed_incomes (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  amount numeric(12,2) not null check (amount > 0),        -- monto aproximado
  day_from int not null check (day_from between 1 and 31), -- suele llegar desde...
  day_to int not null check (day_to between 1 and 31),     -- ...hasta (se planifica con este)
  start_month text not null,                               -- 'YYYY-MM': primer mes esperado
  active boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  check (day_from <= day_to)
);

-- Lo que llegó de verdad cada mes. Suma al saldo de caja.
create table if not exists fixed_income_receipts (
  id uuid primary key default gen_random_uuid(),
  fixed_income_id uuid references fixed_incomes(id) on delete set null,
  name text not null,
  period text not null,                                    -- 'YYYY-MM'
  date date not null,
  amount numeric(12,2) not null check (amount >= 0),
  registered_by text,
  created_at timestamptz not null default now(),
  unique (fixed_income_id, period)
);

create index if not exists idx_fixed_income_receipts_date on fixed_income_receipts(date);

-- Mismo esquema de seguridad que el resto: solo la service key (la app) entra.
alter table fixed_incomes enable row level security;
alter table fixed_income_receipts enable row level security;

-- La comisión del agente BCP: unos S/ 10,000, llega entre el 13 y el 23.
insert into fixed_incomes (name, amount, day_from, day_to, start_month)
select 'Comisiones BCP', 10000, 13, 23, '2026-11'
where not exists (select 1 from fixed_incomes where name = 'Comisiones BCP');
