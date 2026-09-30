-- Rol "Validador" (un PIN compartido para todas las sucursales): confirma
-- manualmente contra Odoo que cada factura registrada ya esté ahí.
alter table invoices add column if not exists validated boolean not null default false;
alter table invoices add column if not exists validated_by text;
alter table invoices add column if not exists validated_at date;
