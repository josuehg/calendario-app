-- Migración: alinea una base de datos creada con el schema.sql viejo
-- (solo branches/invoices/canjes/letras) con lo que la app usa hoy:
-- PIN por sucursal, proveedores, ajustes y tipo de documento.
--
-- Cómo correrlo: Supabase > tu proyecto > SQL Editor > New query >
-- pega todo esto > Run. Es seguro correrlo varias veces (usa IF NOT EXISTS
-- / ON CONFLICT) y no borra datos.

-- 1) PIN de acceso por sucursal ------------------------------------------------
alter table branches add column if not exists pin text;

-- 2) Proveedores --------------------------------------------------------------
create table if not exists vendors (
  id serial primary key,
  name text not null unique,
  ruc text unique,
  doc_type text not null default 'contado' check (doc_type in ('contado', 'credito')),
  term_days int,                         -- 30/45/60/75/90, null si es contado
  created_at timestamptz not null default now()
);

-- 3) Ajustes de la app (una sola fila, id = 1) -------------------------------
create table if not exists app_settings (
  id int primary key default 1,
  track_contado boolean not null default true
);
insert into app_settings (id) values (1) on conflict (id) do nothing;

-- 4) Tipo de documento en facturas -----------------------------------------
alter table invoices add column if not exists document_type text not null default 'Factura';
