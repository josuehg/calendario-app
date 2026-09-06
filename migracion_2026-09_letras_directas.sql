-- Migración: letras "sueltas" (ya programadas, sin pasar por un canje).
-- Supabase > SQL Editor > New query > pega todo > Run. Aditivo y re-ejecutable.

-- Una letra ya no obliga a tener un canje detrás.
alter table letras alter column canje_id drop not null;

-- Datos propios para las letras sueltas (las de un canje los derivan de sus facturas).
alter table letras add column if not exists vendor text;
alter table letras add column if not exists branch text;
alter table letras add column if not exists notes text;
