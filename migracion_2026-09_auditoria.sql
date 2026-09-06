-- Migración: campos de auditoría (quién registró / quién pagó).
-- Supabase > SQL Editor > New query > pega todo > Run. Aditivo y re-ejecutable.

alter table invoices add column if not exists registered_by text;
alter table invoices add column if not exists paid_by text;

alter table expenses add column if not exists registered_by text;
alter table expenses add column if not exists paid_by text;

alter table letras  add column if not exists paid_by text;
alter table canjes  add column if not exists created_by text;
