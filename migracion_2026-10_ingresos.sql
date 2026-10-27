-- Registro de ingresos (ventas/cobros) por sucursal, para poder calcular un
-- saldo de caja real y saber cuánto queda disponible para comprometer en un
-- pedido nuevo sin ahogar la caja.

create table if not exists incomes (
  id uuid primary key default gen_random_uuid(),
  branch text not null,
  date date not null,
  amount numeric(12,2) not null check (amount > 0),
  notes text,
  registered_by text,
  source text not null default 'app' check (source in ('app', 'bot')),
  created_at timestamptz not null default now()
);

create index if not exists idx_incomes_date on incomes(date);
create index if not exists idx_incomes_branch on incomes(branch);

-- Saldo de caja inicial, configurado una sola vez en Configuración: a partir
-- de esa fecha, el saldo se actualiza solo con cada ingreso registrado y
-- cada pago hecho (ver utils.compute_cash_balance).
alter table app_settings add column if not exists caja_saldo_inicial numeric(12,2) not null default 0;
alter table app_settings add column if not exists caja_saldo_inicial_fecha date;
