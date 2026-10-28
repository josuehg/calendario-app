-- Permite que el bot de Telegram recuerde la última lista numerada que
-- mostró en cada chat (de /hoy, /manana, /atrasados o /resumen), para que
-- /pagar <N> sepa a qué factura/letra/gasto se refiere ese número.
create table if not exists bot_list_cache (
  chat_id bigint primary key,
  items jsonb not null,
  created_at timestamptz not null default now()
);
