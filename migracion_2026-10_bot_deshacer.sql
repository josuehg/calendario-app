-- /deshacer en el bot de Telegram: guarda qué marcó el último /pagar de cada
-- chat (ítems, quién, cuándo) para poder volverlos a pendiente si fue un
-- error. Se limpia al deshacer; /deshacer solo vale 30 minutos después.
alter table bot_list_cache add column if not exists ultimo_pago jsonb;
