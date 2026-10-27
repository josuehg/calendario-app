// Bot de Telegram para Control Compras — responde comandos bajo demanda
// (/hoy, /manana, /semana, /atrasados) consultando Supabase directamente.
//
// Reimplementa en TypeScript la misma lógica que utils.get_payment_events()
// en Python (ver utils.py y scripts/telegram_daily_report.py): una letra
// "vive", para efectos de fecha, en vencimiento + plazo típico de pago, y se
// considera vencida solo pasado vencimiento + plazo máximo de gracia.
//
// Variables de entorno requeridas (ver supabase/functions/telegram-bot/README.md):
//   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY  (inyectadas automáticamente por Supabase)
//   TELEGRAM_BOT_TOKEN                        (secret propio, puesto a mano)
//   TELEGRAM_WEBHOOK_SECRET                    (secret propio, puesto a mano)

import { createClient } from "jsr:@supabase/supabase-js@2";

const MONTHS_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

function parseISO(d: string): Date {
  const [y, m, day] = d.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, day));
}

function toISO(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function addDays(d: string, n: number): string {
  const dt = parseISO(d);
  dt.setUTCDate(dt.getUTCDate() + n);
  return toISO(dt);
}

function fmtLong(d: string): string {
  const dt = parseISO(d);
  return `${dt.getUTCDate()} de ${MONTHS_ES[dt.getUTCMonth()]} ${dt.getUTCFullYear()}`;
}

function startOfWeek(d: string): string {
  // Semana de lunes a domingo, igual que utils.start_of_week en la app.
  const dt = parseISO(d);
  const dow = (dt.getUTCDay() + 6) % 7; // lunes=0 ... domingo=6
  dt.setUTCDate(dt.getUTCDate() - dow);
  return toISO(dt);
}

function money(n: number): string {
  const r = Math.round(n * 100) / 100;
  return "S/ " + r.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function todayLima(): string {
  // Perú es UTC-5 todo el año (sin horario de verano).
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Lima", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

type Kind = "invoice" | "letra" | "expense";

interface Evento {
  date: string;
  vencimiento_real?: string;
  amount: number;
  vendor: string;
  branch: string;
  invoice_number: string;
  label: string;
  overdue: boolean;
  kind: Kind;
}

interface Settings {
  track_contado: boolean;
  letra_dias_pago_tipico: number;
  letra_dias_gracia_max: number;
}

async function buildEvents(supabase: any, today: string): Promise<Evento[]> {
  const { data: settingsRow } = await supabase.from("app_settings").select("*").eq("id", 1).single();
  const settings: Settings = {
    track_contado: settingsRow?.track_contado ?? true,
    letra_dias_pago_tipico: settingsRow?.letra_dias_pago_tipico ?? 8,
    letra_dias_gracia_max: settingsRow?.letra_dias_gracia_max ?? 10,
  };

  const { data: invoicesAll } = await supabase
    .from("invoices")
    .select("id,vendor,branch,invoice_number,doc_type,amount,due_date,status")
    .in("status", ["pendiente", "canjeada"]);
  const invoices = invoicesAll ?? [];
  const invById = new Map(invoices.map((i: any) => [i.id, i]));

  const { data: letras } = await supabase
    .from("letras")
    .select("id,canje_id,numero,monto,fecha_vencimiento,estado,vendor,branch")
    .eq("estado", "pendiente");

  const canjeIds = (letras ?? []).map((l: any) => l.canje_id).filter((x: any) => x);
  let canjeFacturas: any[] = [];
  if (canjeIds.length) {
    const { data } = await supabase.from("canje_facturas").select("canje_id,invoice_id").in("canje_id", canjeIds);
    canjeFacturas = data ?? [];
  }
  const canjeInvoices = new Map<string, any[]>();
  for (const cf of canjeFacturas) {
    const inv = invById.get(cf.invoice_id);
    if (inv) {
      if (!canjeInvoices.has(cf.canje_id)) canjeInvoices.set(cf.canje_id, []);
      canjeInvoices.get(cf.canje_id)!.push(inv);
    }
  }

  const { data: expenses } = await supabase
    .from("expenses")
    .select("id,kind,name,category,branch,amount,due_date,status")
    .eq("status", "pendiente");

  const events: Evento[] = [];

  for (const inv of invoices) {
    if (inv.status !== "pendiente") continue;
    if (!settings.track_contado && inv.doc_type === "contado") continue;
    events.push({
      date: inv.due_date,
      amount: Number(inv.amount),
      vendor: inv.vendor,
      branch: inv.branch,
      invoice_number: inv.invoice_number,
      label: inv.doc_type === "contado" ? "Contado" : "Factura a crédito",
      overdue: inv.due_date < today,
      kind: "invoice",
    });
  }

  for (const l of letras ?? []) {
    const grouped = canjeInvoices.get(l.canje_id) ?? [];
    let vendor: string, branch: string, facturas: string, label: string;
    if (grouped.length) {
      vendor = [...new Set(grouped.map((i) => i.vendor))].sort().join(", ") || "—";
      branch = [...new Set(grouped.map((i) => i.branch))].sort().join(", ") || "—";
      facturas = grouped.map((i) => i.invoice_number).join(", ") || "—";
      label = `Letra ${l.numero || "—"} (${grouped.length} factura(s))`;
    } else {
      vendor = l.vendor || "—";
      branch = l.branch || "—";
      facturas = "—";
      label = `Letra ${l.numero || "—"} (programada)`;
    }
    const fechaEsperada = addDays(l.fecha_vencimiento, settings.letra_dias_pago_tipico);
    const fechaLimite = addDays(l.fecha_vencimiento, settings.letra_dias_gracia_max);
    events.push({
      date: fechaEsperada,
      vencimiento_real: l.fecha_vencimiento,
      amount: Number(l.monto),
      vendor, branch,
      invoice_number: facturas,
      label,
      overdue: fechaLimite < today,
      kind: "letra",
    });
  }

  for (const x of expenses ?? []) {
    events.push({
      date: x.due_date,
      amount: Number(x.amount),
      vendor: x.name,
      branch: x.branch || "General",
      invoice_number: "",
      label: `Gasto ${x.kind} · ${x.category}`,
      overdue: x.due_date < today,
      kind: "expense",
    });
  }

  return events;
}

function referenciaVencimiento(e: Evento, graciaMax: number): string {
  if (e.kind === "letra" && e.vencimiento_real) return addDays(e.vencimiento_real, graciaMax);
  return e.date;
}

function diasAtraso(e: Evento, today: string, graciaMax: number): number {
  const ref = referenciaVencimiento(e, graciaMax);
  const ms = parseISO(today).getTime() - parseISO(ref).getTime();
  return Math.round(ms / 86400000);
}

function linea(e: Evento): string {
  const ref = e.invoice_number && e.kind !== "expense" ? ` · Fact. ${e.invoice_number}` : "";
  return `• ${e.vendor}${ref} · ${e.label} · ${e.branch} · ${money(e.amount)}`;
}

function sumAmount(events: Evento[]): number {
  return events.reduce((acc, e) => acc + e.amount, 0);
}

async function handleHoy(supabase: any): Promise<string> {
  const today = todayLima();
  const events = await buildEvents(supabase, today);
  const hoy = events.filter((e) => e.date === today).sort((a, b) => b.amount - a.amount);
  const lines = [`📅 Pagos de hoy, ${fmtLong(today)}`, ""];
  if (!hoy.length) {
    lines.push("No hay pagos programados para hoy. 🎉");
    return lines.join("\n");
  }
  lines.push(...hoy.map(linea));
  lines.push("", `Total del día: ${money(sumAmount(hoy))}`);
  return lines.join("\n");
}

async function handleManana(supabase: any): Promise<string> {
  const today = todayLima();
  const manana = addDays(today, 1);
  const events = await buildEvents(supabase, today);
  const items = events.filter((e) => e.date === manana).sort((a, b) => b.amount - a.amount);
  const lines = [`📅 Pagos de mañana, ${fmtLong(manana)}`, ""];
  if (!items.length) {
    lines.push("No hay pagos programados para mañana. 🎉");
    return lines.join("\n");
  }
  lines.push(...items.map(linea));
  lines.push("", `Total: ${money(sumAmount(items))}`);
  return lines.join("\n");
}

async function handleSemana(supabase: any): Promise<string> {
  const today = todayLima();
  const hasta = addDays(today, 6);
  const events = await buildEvents(supabase, today);
  const items = events.filter((e) => e.date >= today && e.date <= hasta);
  const lines = [`📅 Próximos 7 días (${fmtLong(today)} – ${fmtLong(hasta)})`, ""];
  if (!items.length) {
    lines.push("No hay pagos programados en los próximos 7 días. 🎉");
    return lines.join("\n");
  }
  const porDia = new Map<string, Evento[]>();
  for (const e of items) {
    if (!porDia.has(e.date)) porDia.set(e.date, []);
    porDia.get(e.date)!.push(e);
  }
  for (const fecha of [...porDia.keys()].sort()) {
    const dia = porDia.get(fecha)!.sort((a, b) => b.amount - a.amount);
    lines.push(fmtLong(fecha) + ":");
    lines.push(...dia.map(linea));
    lines.push("");
  }
  lines.push(`Total de la semana: ${money(sumAmount(items))}`);
  return lines.join("\n");
}

async function handleMeses(supabase: any): Promise<string> {
  const today = todayLima();
  const hoyDt = parseISO(today);
  const year = hoyDt.getUTCFullYear();
  const month = hoyDt.getUTCMonth(); // 0-indexado
  const inicio = toISO(new Date(Date.UTC(year, month, 1)));
  const fin = toISO(new Date(Date.UTC(year, month + 2, 0))); // último día del mes siguiente

  const events = await buildEvents(supabase, today);
  const items = events.filter((e) => e.date >= inicio && e.date <= fin);

  const tituloMeses = `${MONTHS_ES[month]} y ${MONTHS_ES[(month + 1) % 12]}`;
  const lines = [`📊 Pagos por semana — ${tituloMeses}`, ""];
  if (!items.length) {
    lines.push("No hay pagos programados en este periodo. 🎉");
    return lines.join("\n");
  }

  const porSemana = new Map<string, Evento[]>();
  for (const e of items) {
    const wk = startOfWeek(e.date);
    if (!porSemana.has(wk)) porSemana.set(wk, []);
    porSemana.get(wk)!.push(e);
  }
  for (const wk of [...porSemana.keys()].sort()) {
    const semana = porSemana.get(wk)!;
    const finSemana = addDays(wk, 6);
    lines.push(
      `Semana del ${fmtLong(wk)} al ${fmtLong(finSemana)}: ${money(sumAmount(semana))} (${semana.length} pago(s))`,
    );
  }
  lines.push("", `Total del periodo: ${money(sumAmount(items))}`);
  return lines.join("\n");
}

async function handleAtrasados(supabase: any): Promise<string> {
  const today = todayLima();
  const { data: settingsRow } = await supabase.from("app_settings").select("*").eq("id", 1).single();
  const graciaMax = settingsRow?.letra_dias_gracia_max ?? 10;
  const events = await buildEvents(supabase, today);
  const atrasados = events
    .filter((e) => e.overdue)
    .sort((a, b) => diasAtraso(b, today, graciaMax) - diasAtraso(a, today, graciaMax));
  const lines = ["⚠️ Atrasados (aún sin pagar)", ""];
  if (!atrasados.length) {
    lines.push("No tienes nada atrasado. 🎉");
    return lines.join("\n");
  }
  for (const e of atrasados) {
    lines.push(`${linea(e)} · ${diasAtraso(e, today, graciaMax)} día(s) de atraso`);
  }
  lines.push("", `Total atrasado: ${money(sumAmount(atrasados))}`);
  return lines.join("\n");
}

const AYUDA = [
  "Hola 👋 Soy el bot de Control Compras. Comandos disponibles:",
  "",
  "/hoy — pagos de hoy",
  "/manana — pagos de mañana",
  "/semana — resumen de los próximos 7 días",
  "/meses — pagos por semana del mes actual y el próximo",
  "/atrasados — lo vencido que aún no se paga",
].join("\n");

/** null => no es un comando dirigido al bot: no se responde nada (el grupo
 * tiene el modo privacidad desactivado, así que el webhook recibe TODOS los
 * mensajes del grupo, no solo los que le escriben al bot). */
async function responderComando(supabase: any, text: string): Promise<string | null> {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) return null;
  const cmd = trimmed.split(/\s+/)[0].split("@")[0].toLowerCase();
  switch (cmd) {
    case "/hoy": return await handleHoy(supabase);
    case "/manana": case "/mañana": return await handleManana(supabase);
    case "/semana": return await handleSemana(supabase);
    case "/meses": return await handleMeses(supabase);
    case "/atrasados": return await handleAtrasados(supabase);
    case "/start": case "/ayuda": case "/help": return AYUDA;
    default: return `No entendí ese comando.\n\n${AYUDA}`;
  }
}

async function sendTelegram(token: string, chatId: number | string, text: string) {
  // Texto plano (sin parse_mode): un vendor con "_" o "*" en el nombre rompe
  // el parser de Markdown de Telegram y el envío fallaría silenciosamente.
  const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
  if (!res.ok) {
    console.error("Telegram respondió", res.status, await res.text());
  }
}

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("ok", { status: 200 });
  }

  const webhookSecret = Deno.env.get("TELEGRAM_WEBHOOK_SECRET");
  if (webhookSecret) {
    const got = req.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (got !== webhookSecret) {
      return new Response("forbidden", { status: 403 });
    }
  }

  const token = Deno.env.get("TELEGRAM_BOT_TOKEN");
  if (!token) {
    console.error("Falta el secret TELEGRAM_BOT_TOKEN");
    return new Response("ok", { status: 200 });
  }

  const update = await req.json().catch(() => null);
  const message = update?.message;
  const text: string | undefined = message?.text;
  const chatId = message?.chat?.id;

  if (!text || !chatId || !text.trim().startsWith("/")) {
    return new Response("ok", { status: 200 });
  }

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  try {
    const reply = await responderComando(supabase, text);
    if (reply) await sendTelegram(token, chatId, reply);
  } catch (err) {
    console.error("Error respondiendo comando:", err);
    await sendTelegram(token, chatId, "Ocurrió un error consultando la información, intenta de nuevo en un momento.");
  }

  return new Response("ok", { status: 200 });
});
