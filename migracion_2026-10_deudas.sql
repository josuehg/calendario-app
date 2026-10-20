-- Módulo de Deudas: capital, tasa y saldo, separado de la cuota mensual que
-- ya se registra en Gastos Fijos. Permite ver cuánto se debe en total
-- (no solo cuánto se paga cada mes).
create table if not exists debts (
  id uuid primary key default gen_random_uuid(),
  creditor text not null,
  debt_type text not null default 'bancario' check (debt_type in ('bancario', 'informal')),
  principal numeric(12,2) not null check (principal > 0),
  balance numeric(12,2) not null check (balance >= 0),
  rate_pct numeric(6,3),
  rate_period text check (rate_period in ('mensual', 'anual')),
  monthly_payment numeric(12,2),
  start_date date,
  end_date date,
  notes text,
  active boolean not null default true,
  created_at timestamptz not null default now()
);
