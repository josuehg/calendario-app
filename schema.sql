-- Calendario Maestro de Pagos — esquema de base de datos (Supabase / Postgres)
-- Ejecuta este script completo en: Supabase > tu proyecto > SQL Editor > New query > Run
--
-- Si ya tenías una base creada con una versión anterior de este archivo,
-- corre en su lugar migracion_2026-09_pins_proveedores.sql (agrega lo que falta
-- sin borrar datos).

create extension if not exists pgcrypto;

-- Sucursales (editable desde la página "Configuración" de la app).
-- pin: PIN de acceso propio de la sucursal — al entrar con él, la app la
-- identifica sola y le da acceso solo a "Registrar factura".
create table if not exists branches (
  id serial primary key,
  name text not null unique,
  pin text
);

insert into branches (name) values
  ('Sucursal 1'), ('Sucursal 2'), ('Sucursal 3'),
  ('Sucursal 4'), ('Sucursal 5'), ('Sucursal 6')
on conflict (name) do nothing;

-- Proveedores (contado o crédito, con su plazo). El administrador los
-- configura en "Configuración"; las sucursales pueden crear uno nuevo
-- desde "Registrar factura" y queda al contado hasta que se reclasifique.
create table if not exists vendors (
  id serial primary key,
  name text not null unique,
  ruc text unique,
  doc_type text not null default 'contado' check (doc_type in ('contado', 'credito')),
  term_days int,                         -- 30/45/60/75/90, null si es contado
  created_at timestamptz not null default now()
);

-- Ajustes globales de la app (una sola fila, id = 1).
create table if not exists app_settings (
  id int primary key default 1,
  track_contado boolean not null default true
);
insert into app_settings (id) values (1) on conflict (id) do nothing;

-- Facturas registradas por las sucursales
create table if not exists invoices (
  id uuid primary key default gen_random_uuid(),
  branch text not null,
  vendor text not null,
  invoice_number text not null,
  document_type text not null default 'Factura',   -- Factura / Boleta / Nota de compra / Otro
  doc_type text not null check (doc_type in ('contado', 'credito')),
  amount numeric(12,2) not null check (amount > 0),
  issue_date date not null,
  term_days int,                         -- 30/45/60/75/90, null si es contado
  due_date date not null,                -- vencimiento original (antes de cualquier canje)
  status text not null default 'pendiente' check (status in ('pendiente', 'canjeada', 'pagada')),
  notes text,
  paid_at date,                          -- solo cuando se paga directo, sin pasar por canje
  created_at timestamptz not null default now()
);

-- Un canje agrupa N facturas -> M letras (muchas-a-muchas)
create table if not exists canjes (
  id uuid primary key default gen_random_uuid(),
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists canje_facturas (
  canje_id uuid not null references canjes(id) on delete cascade,
  invoice_id uuid not null references invoices(id) on delete cascade,
  primary key (canje_id, invoice_id)
);

-- Letras resultantes de un canje
create table if not exists letras (
  id uuid primary key default gen_random_uuid(),
  canje_id uuid not null references canjes(id) on delete cascade,
  numero text,
  monto numeric(12,2) not null check (monto > 0),
  fecha_vencimiento date not null,
  estado text not null default 'pendiente' check (estado in ('pendiente', 'pagada')),
  fecha_pago date
);

create index if not exists idx_invoices_status on invoices(status);
create index if not exists idx_invoices_due_date on invoices(due_date);
create index if not exists idx_letras_estado on letras(estado);
create index if not exists idx_letras_fecha on letras(fecha_vencimiento);
create index if not exists idx_canje_facturas_invoice on canje_facturas(invoice_id);
