-- Escenarios guardados del Simulador de crédito: los supuestos (crédito,
-- caja, venta, compras), cuánto se cancela de cada deuda y las inversiones.
create table if not exists sim_scenarios (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table sim_scenarios enable row level security;
