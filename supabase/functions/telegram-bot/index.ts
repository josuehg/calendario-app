// Bot de Telegram para Control Compras — responde comandos bajo demanda
// (/hoy, /manana, /semana, /meses, /atrasados, /ventana, /pagados, /buscar,
// /resumen, /saldo, /simular) y permite registrar ingresos (/ingreso) y
// marcar pagos como pagados (/pagar, /deshacer), consultando y escribiendo
// en Supabase directamente.
//
// /pagar funciona sobre la última lista numerada que el bot le mostró a
// ESE chat (ver LISTAS_PAGABLES — la guardan en la tabla bot_list_cache al
// responder, incluido el reporte diario) — "N" siempre se refiere a esa
// lista, no a una posición fija.
//
// También manda el reporte diario (antes lo mandaba
// scripts/telegram_daily_report.py vía GitHub Actions, que no garantiza la
// hora — puede atrasarse varias horas sin avisar). Ahora lo dispara un cron
// de Supabase (pg_cron + pg_net), que llama a esta misma función con
// {"type":"daily_report","cron_secret":"..."} en el body — ver
// supabase/sql/cron_reporte_diario.sql.
//
// Reimplementa en TypeScript la misma lógica que utils.get_payment_events()
// de la app: una letra "vive", para efectos de fecha, en vencimiento +
// plazo típico de pago, y se considera vencida solo pasado vencimiento +
// plazo máximo de gracia.
//
// Variables de entorno requeridas (ver supabase/functions/telegram-bot/README.md):
//   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY  (inyectadas automáticamente por Supabase)
//   TELEGRAM_BOT_TOKEN                        (secret propio, puesto a mano)
//   TELEGRAM_WEBHOOK_SECRET                    (secret propio, puesto a mano)
//   TELEGRAM_CHAT_ID                           (secret propio — a quién mandar el reporte diario)
//   CRON_SECRET                                (secret propio — protege el disparo del reporte diario)

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
  paidBy?: string;
  refId: string;
  /** Para agrupar las listas de pagos: categoría del gasto, "Letras", "Contado"... */
  tipo?: string;
}

interface Settings {
  track_contado: boolean;
  letra_dias_pago_tipico: number;
  letra_dias_gracia_max: number;
  caja_saldo_inicial: number;
  caja_saldo_inicial_fecha: string | null;
}

/** Una sola lectura de app_settings por comando (antes cada handler la
 * volvía a pedir, con sus propios defaults). */
async function loadSettings(supabase: any): Promise<Settings> {
  const { data: settingsRow } = await supabase.from("app_settings").select("*").eq("id", 1).single();
  const tipico = settingsRow?.letra_dias_pago_tipico ?? 8;
  return {
    track_contado: settingsRow?.track_contado ?? true,
    letra_dias_pago_tipico: tipico,
    letra_dias_gracia_max: settingsRow?.letra_dias_gracia_max ?? tipico,
    caja_saldo_inicial: Number(settingsRow?.caja_saldo_inicial ?? 0),
    caja_saldo_inicial_fecha: settingsRow?.caja_saldo_inicial_fecha ?? null,
  };
}

/** Acepta 2026-10-25, 25/10, 25/10/2026 o 25-10-2026 (sin año = año de
 * hoy). null si no es una fecha real (ej. 31/02 o 2026-13-40). */
function parseFecha(token: string, today: string): string | null {
  let y: number, m: number, d: number;
  let mt = token.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (mt) {
    [y, m, d] = [Number(mt[1]), Number(mt[2]), Number(mt[3])];
  } else if ((mt = token.match(/^(\d{1,2})[\/-](\d{1,2})(?:[\/-](\d{2}|\d{4}))?$/))) {
    [d, m] = [Number(mt[1]), Number(mt[2])];
    y = !mt[3] ? parseISO(today).getUTCFullYear() : mt[3].length === 2 ? 2000 + Number(mt[3]) : Number(mt[3]);
  } else {
    return null;
  }
  const dt = new Date(Date.UTC(y, m - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
  return toISO(dt);
}

const FECHA_INVALIDA = "La fecha no es válida. Usa 25/10, 25/10/2026 o 2026-10-25.";

/** Valida la fecha opcional de /pagar y /ingreso: real y no futura. */
function fechaPasadaOHoy(token: string | undefined, today: string): { fecha?: string; error?: string } {
  if (!token) return { fecha: today };
  const fecha = parseFecha(token, today);
  if (!fecha) return { error: FECHA_INVALIDA };
  if (fecha > today) return { error: `La fecha ${fmtLong(fecha)} es futura — solo hoy o días pasados.` };
  return { fecha };
}

/** Quita espacios y signos para comparar nombres: "mym" encuentra "M Y M PROMEFAR". */
function normalizar(s: string): string {
  return s.toLowerCase().normalize("NFD").replace(/[^a-z0-9]/g, "");
}

async function buildEvents(supabase: any, today: string, settings?: Settings): Promise<Evento[]> {
  settings = settings ?? await loadSettings(supabase);

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
      refId: inv.id,
      tipo: inv.doc_type === "contado" ? "Contado" : "Facturas a crédito",
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
      refId: l.id,
      tipo: "Letras",
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
      refId: x.id,
      tipo: x.category || "Gastos",
    });
  }

  return events;
}

async function buildPaidEvents(supabase: any): Promise<Evento[]> {
  const { data: invoicesPaid } = await supabase
    .from("invoices")
    .select("id,vendor,branch,invoice_number,doc_type,amount,paid_at,paid_by")
    .eq("status", "pagada");

  const { data: letrasPaid } = await supabase
    .from("letras")
    .select("id,canje_id,numero,monto,vendor,branch,fecha_pago,paid_by")
    .eq("estado", "pagada");

  // Las letras de canje no guardan vendor/branch propios (quedan null): se
  // sacan de sus facturas agrupadas — si no, /pagados y /buscar las
  // mostraban como "—".
  const canjeIds = [...new Set((letrasPaid ?? []).map((l: any) => l.canje_id).filter((x: any) => x))];
  const canjeInfo = new Map<string, { vendor: string; branch: string }>();
  if (canjeIds.length) {
    const { data: cfs } = await supabase.from("canje_facturas").select("canje_id,invoice_id").in("canje_id", canjeIds);
    const invIds = [...new Set((cfs ?? []).map((cf: any) => cf.invoice_id))];
    const { data: invs } = invIds.length
      ? await supabase.from("invoices").select("id,vendor,branch").in("id", invIds)
      : { data: [] };
    const invById = new Map((invs ?? []).map((i: any) => [i.id, i]));
    const porCanje = new Map<string, any[]>();
    for (const cf of cfs ?? []) {
      const inv = invById.get(cf.invoice_id);
      if (!inv) continue;
      if (!porCanje.has(cf.canje_id)) porCanje.set(cf.canje_id, []);
      porCanje.get(cf.canje_id)!.push(inv);
    }
    for (const [cid, grouped] of porCanje) {
      canjeInfo.set(cid, {
        vendor: [...new Set(grouped.map((i) => i.vendor))].sort().join(", ") || "—",
        branch: [...new Set(grouped.map((i) => i.branch))].sort().join(", ") || "—",
      });
    }
  }

  const { data: expensesPaid } = await supabase
    .from("expenses")
    .select("id,kind,name,category,branch,amount,paid_at,paid_by")
    .eq("status", "pagado");

  const events: Evento[] = [];

  for (const inv of invoicesPaid ?? []) {
    if (!inv.paid_at) continue;
    events.push({
      date: inv.paid_at,
      amount: Number(inv.amount),
      vendor: inv.vendor,
      branch: inv.branch,
      invoice_number: inv.invoice_number,
      label: inv.doc_type === "contado" ? "Contado" : "Factura a crédito",
      overdue: false,
      kind: "invoice",
      paidBy: inv.paid_by ?? undefined,
      refId: inv.id,
    });
  }

  for (const l of letrasPaid ?? []) {
    if (!l.fecha_pago) continue;
    const info = l.canje_id ? canjeInfo.get(l.canje_id) : undefined;
    events.push({
      date: l.fecha_pago,
      amount: Number(l.monto),
      vendor: info?.vendor || l.vendor || "—",
      branch: info?.branch || l.branch || "—",
      invoice_number: "—",
      label: `Letra ${l.numero || "—"}`,
      overdue: false,
      kind: "letra",
      paidBy: l.paid_by ?? undefined,
      refId: l.id,
    });
  }

  for (const x of expensesPaid ?? []) {
    if (!x.paid_at) continue;
    events.push({
      date: x.paid_at,
      amount: Number(x.amount),
      vendor: x.name,
      branch: x.branch || "General",
      invoice_number: "",
      label: `Gasto ${x.kind} · ${x.category}`,
      overdue: false,
      kind: "expense",
      paidBy: x.paid_by ?? undefined,
      refId: x.id,
    });
  }

  return events;
}

// Una letra se marca atrasada recién pasado el plazo máximo (ver buildEvents),
// pero sus días de atraso se cuentan desde el vencimiento real, igual que en
// la app (utils.get_payment_events).
function referenciaVencimiento(e: Evento): string {
  if (e.kind === "letra" && e.vencimiento_real) return e.vencimiento_real;
  return e.date;
}

function diasAtraso(e: Evento, today: string): number {
  const ref = referenciaVencimiento(e);
  const ms = parseISO(today).getTime() - parseISO(ref).getTime();
  return Math.round(ms / 86400000);
}

/** Letras ya vencidas por contrato (vencimiento_real <= hoy) pero todavía
 * dentro del plazo TÍPICO de pago (vencimiento_real + plazo_tipico, ej. 8
 * días) — la ventana "normal" en la que sueles pagarle al proveedor. El
 * plazo MÁXIMO de gracia (ej. 10 días) queda aparte, solo para cuándo se
 * marca "oficialmente atrasada" en /atrasados — no limita esta ventana. */
function letrasEnVentana(events: Evento[], today: string, plazoTipico: number): Evento[] {
  return events
    .filter((e) => {
      if (e.kind !== "letra" || !e.vencimiento_real) return false;
      if (e.vencimiento_real > today) return false;
      return today <= addDays(e.vencimiento_real, plazoTipico);
    })
    .sort((a, b) => (a.vencimiento_real! < b.vencimiento_real! ? -1 : a.vencimiento_real! > b.vencimiento_real! ? 1 : 0));
}

function diasDesdeVencimiento(e: Evento, today: string): number {
  const ms = parseISO(today).getTime() - parseISO(e.vencimiento_real!).getTime();
  return Math.round(ms / 86400000);
}

function lineaVentana(e: Evento, n: number, today: string, graciaMax: number): string {
  const limite = addDays(e.vencimiento_real!, graciaMax);
  const dias = diasDesdeVencimiento(e, today);
  return `${n}. ${e.vendor} · ${e.label} · ${e.branch} · ${money(e.amount)} · venció hace ${dias} día(s) · límite ${fmtLong(limite)}`;
}

// Solo las facturas muestran su número: en una letra de canje serían las 10+
// facturas agrupadas, una línea larguísima ("Letra X (10 factura(s))" ya
// dice cuántas son).
function refFactura(e: Evento): string {
  return e.kind === "invoice" && e.invoice_number && e.invoice_number !== "—" ? ` · Fact. ${e.invoice_number}` : "";
}

function linea(e: Evento, n: number): string {
  return `${n}. ${e.vendor}${refFactura(e)} · ${e.label} · ${e.branch} · ${money(e.amount)}`;
}

function lineaPagado(e: Evento, n: number): string {
  const quien = e.paidBy ? ` · pagó ${e.paidBy}` : "";
  return `${n}. ${e.vendor}${refFactura(e)} · ${e.label} · ${e.branch} · ${money(e.amount)}${quien}`;
}

/** Lista numerada 1. 2. 3. ... para los comandos del bot (en vez de viñetas).
 * `desde` permite seguir la numeración entre secciones de un mismo mensaje
 * (reporte diario, /semana), para que cada N sea único y sirva para /pagar. */
function numeradas(items: Evento[], fn: (e: Evento, n: number) => string, desde = 1): string[] {
  return items.map((e, i) => fn(e, i + desde));
}

function sumAmount(events: Evento[]): number {
  return events.reduce((acc, e) => acc + e.amount, 0);
}

// Marcas de negrita: sendTelegram escapa el texto (un "&" o "<" en un nombre
// rompería el HTML de Telegram) y recién después las cambia por <b></b>.
const NEGRITA_INI = "\u0001";
const NEGRITA_FIN = "\u0002";

function negrita(s: string): string {
  return `${NEGRITA_INI}${s}${NEGRITA_FIN}`;
}

/** Línea de un pago dentro de su grupo: el tipo ya va en el título del
 * grupo, así que no se repite (salvo el n° de letra o de factura). */
function lineaEnGrupo(e: Evento, n: number): string {
  const detalle = e.kind === "letra" ? ` · ${e.label}` : refFactura(e);
  return `${n}. ${e.vendor}${detalle} · ${e.branch} · ${money(e.amount)}`;
}

/** Agrupa una lista de pagos por tipo (Prestamos Pers. Jur., Letras, ...):
 * título en negrita con cantidad y total, y debajo sus pagos. Los grupos van
 * de mayor a menor monto; dentro de cada uno se respeta el orden recibido.
 * Devuelve también el orden en que quedaron numerados, que es el que hay que
 * guardar para /pagar. */
function listaPorTipo(
  items: Evento[], fmt: (e: Evento, n: number) => string, desde = 1,
): { lines: string[]; orden: Evento[] } {
  const grupos = new Map<string, Evento[]>();
  for (const e of items) {
    const t = e.tipo ?? "Otros";
    if (!grupos.has(t)) grupos.set(t, []);
    grupos.get(t)!.push(e);
  }
  const lines: string[] = [];
  const orden: Evento[] = [];
  for (const [tipo, evs] of [...grupos.entries()].sort((a, b) => sumAmount(b[1]) - sumAmount(a[1]))) {
    if (lines.length) lines.push("");
    lines.push(negrita(`${tipo} · ${evs.length} · ${money(sumAmount(evs))}`));
    for (const e of evs) {
      orden.push(e);
      lines.push(fmt(e, desde + orden.length - 1));
    }
  }
  return { lines, orden };
}

/** Guarda la lista numerada que se le acaba de mostrar a este chat, para
 * que /pagar <N> sepa a qué factura/letra/gasto se refiere ese número. Se
 * sobrescribe cada vez que se muestra una lista (LISTAS_PAGABLES, incluido
 * el reporte diario) — "N" siempre apunta a la ÚLTIMA lista que vio ese chat. */
async function guardarListaParaPagar(supabase: any, chatId: number | string, items: Evento[]) {
  if (!items.length) return;
  const payload = items.map((e, i) => ({
    n: i + 1, kind: e.kind, ref_id: e.refId,
    vendor: e.vendor, label: e.label, branch: e.branch, amount: e.amount,
  }));
  await supabase.from("bot_list_cache").upsert({
    chat_id: chatId, items: payload, created_at: new Date().toISOString(),
  });
}

async function handleHoy(supabase: any, chatId: number | string): Promise<string> {
  const today = todayLima();
  const events = await buildEvents(supabase, today);
  const hoy = events.filter((e) => e.date === today).sort((a, b) => b.amount - a.amount);
  const lines = [`📅 Pagos de hoy, ${fmtLong(today)}`, ""];
  if (!hoy.length) {
    lines.push("No hay pagos programados para hoy. 🎉");
    return lines.join("\n");
  }
  const lista = listaPorTipo(hoy, lineaEnGrupo);
  lines.push(...lista.lines);
  lines.push("", `Total del día: ${money(sumAmount(hoy))}`);
  await guardarListaParaPagar(supabase, chatId, lista.orden);
  return lines.join("\n");
}

async function handleManana(supabase: any, chatId: number | string): Promise<string> {
  const today = todayLima();
  const manana = addDays(today, 1);
  const events = await buildEvents(supabase, today);
  const items = events.filter((e) => e.date === manana).sort((a, b) => b.amount - a.amount);
  const lines = [`📅 Pagos de mañana, ${fmtLong(manana)}`, ""];
  if (!items.length) {
    lines.push("No hay pagos programados para mañana. 🎉");
    return lines.join("\n");
  }
  const lista = listaPorTipo(items, lineaEnGrupo);
  lines.push(...lista.lines);
  lines.push("", `Total: ${money(sumAmount(items))}`);
  await guardarListaParaPagar(supabase, chatId, lista.orden);
  return lines.join("\n");
}

const LISTAS_PAGABLES = "/hoy, /manana, /semana, /atrasados, /ventana, /buscar, /resumen o el reporte diario";

async function handleSemana(supabase: any, chatId: number | string): Promise<string> {
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
  const enOrden: Evento[] = [];
  for (const fecha of [...porDia.keys()].sort()) {
    const dia = porDia.get(fecha)!.sort((a, b) => b.amount - a.amount);
    lines.push(fmtLong(fecha) + ":");
    lines.push(...numeradas(dia, linea, enOrden.length + 1));
    lines.push("");
    enOrden.push(...dia);
  }
  lines.push(`Total de la semana: ${money(sumAmount(items))}`);
  await guardarListaParaPagar(supabase, chatId, enOrden);
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

async function handleAtrasados(supabase: any, chatId: number | string): Promise<string> {
  const today = todayLima();
  const events = await buildEvents(supabase, today);
  const atrasados = events
    .filter((e) => e.overdue)
    .sort((a, b) => diasAtraso(b, today) - diasAtraso(a, today));
  const lines = ["⚠️ Atrasados (aún sin pagar)", ""];
  if (!atrasados.length) {
    lines.push("No tienes nada atrasado. 🎉");
    return lines.join("\n");
  }
  const lista = listaPorTipo(atrasados, (e, n) => `${lineaEnGrupo(e, n)} · ${diasAtraso(e, today)} día(s) de atraso`);
  lines.push(...lista.lines);
  lines.push("", `Total atrasado: ${money(sumAmount(atrasados))}`);
  await guardarListaParaPagar(supabase, chatId, lista.orden);
  return lines.join("\n");
}

async function handleVentana(supabase: any, chatId: number | string): Promise<string> {
  const today = todayLima();
  const settings = await loadSettings(supabase);
  const graciaMax = settings.letra_dias_gracia_max;
  const plazoTipico = settings.letra_dias_pago_tipico;
  const events = await buildEvents(supabase, today, settings);
  const ventana = letrasEnVentana(events, today, plazoTipico);

  const lines = [`🧾 Letras en ventana de pago (ya vencieron, dentro de los ${plazoTipico} días típicos)`, ""];
  if (!ventana.length) {
    lines.push("No hay letras en ese rango ahora mismo. 🎉");
    return lines.join("\n");
  }
  ventana.forEach((e, i) => lines.push(lineaVentana(e, i + 1, today, graciaMax)));
  lines.push("", `Total en ventana: ${money(sumAmount(ventana))}`);
  await guardarListaParaPagar(supabase, chatId, ventana);
  return lines.join("\n");
}

async function handlePagados(supabase: any, weeksBack: number): Promise<string> {
  const today = todayLima();
  const objetivo = addDays(today, -7 * weeksBack);
  const inicio = startOfWeek(objetivo);
  const fin = addDays(inicio, 6);

  const events = await buildPaidEvents(supabase);
  const items = events
    .filter((e) => e.date >= inicio && e.date <= fin)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : b.amount - a.amount));

  const etiqueta = weeksBack === 0 ? "esta semana" : weeksBack === 1 ? "la semana pasada" : `hace ${weeksBack} semanas`;
  const lines = [`✅ Pagado ${etiqueta} (${fmtLong(inicio)} – ${fmtLong(fin)})`, ""];
  if (!items.length) {
    lines.push("No hay nada pagado registrado en ese rango.");
    return lines.join("\n");
  }
  lines.push(...numeradas(items, lineaPagado));
  lines.push("", `Total pagado: ${money(sumAmount(items))}`);
  return lines.join("\n");
}

async function handleResumen(supabase: any, chatId: number | string): Promise<string> {
  const today = todayLima();
  const hasta = addDays(today, 6);
  const events = await buildEvents(supabase, today);

  const hoy = events.filter((e) => e.date === today).sort((a, b) => b.amount - a.amount);
  const atrasados = events.filter((e) => e.overdue);
  const semana = events.filter((e) => e.date >= today && e.date <= hasta);

  const lines = [`📊 Resumen rápido — ${fmtLong(today)}`, ""];

  lines.push(`📅 Hoy: ${hoy.length} pago(s) · ${money(sumAmount(hoy))}`);
  const listaHoy = listaPorTipo(hoy, lineaEnGrupo);
  lines.push(...listaHoy.lines);
  lines.push("");

  lines.push(`⚠️ Atrasados: ${atrasados.length} pago(s) · ${money(sumAmount(atrasados))}`);
  if (atrasados.length) lines.push("(escribe /atrasados para el detalle)");
  lines.push("");

  lines.push(`📈 Próximos 7 días: ${money(sumAmount(semana))} (escribe /semana para el detalle)`);

  await guardarListaParaPagar(supabase, chatId, listaHoy.orden);
  return lines.join("\n");
}

async function resolveBranchNames(supabase: any): Promise<string[]> {
  const { data } = await supabase.from("branches").select("name").order("name");
  return (data ?? []).map((r: any) => r.name as string);
}

/** Sucursales sin un ingreso registrado para esa fecha — para el aviso del
 * reporte diario, igual que _sucursales_sin_ingreso en
 * scripts/telegram_daily_report.py (que este reporte reemplaza). */
async function sucursalesSinIngreso(supabase: any, fecha: string): Promise<string[]> {
  const names = await resolveBranchNames(supabase);
  const { data } = await supabase.from("incomes").select("branch").eq("date", fecha);
  const registradas = new Set((data ?? []).map((r: any) => r.branch));
  return names.filter((n) => !registradas.has(n));
}

/** Compras del día (igual que la página "Compras del día" de la app): cuánto
 * queda de la meta de compras del mes y, si se pide hoy a 30/60/75/90 días,
 * en qué mes vencería y si ese mes tiene espacio. La meta sale del escenario
 * guardado del Simulador (el que diga "FINAL"; si no, el último con meta) o,
 * sin escenarios, del promedio de compras de los últimos 3 meses. */
async function comprasDelDia(supabase: any, today: string, events?: Evento[]): Promise<string[]> {
  const evs = events ?? await buildEvents(supabase, today);
  const { data: escenarios } = await supabase
    .from("sim_scenarios").select("name,data,created_at").order("created_at", { ascending: false });
  const conMeta = (escenarios ?? []).filter((e: any) => Number(e?.data?.sim_compras) > 0);
  const elegido = conMeta.find((e: any) => /final/i.test(e.name)) ?? conMeta[0];
  const mes0 = today.slice(0, 7);
  const [y0, m0] = mes0.split("-").map(Number);
  const hace3 = toISO(new Date(Date.UTC(y0, m0 - 4, 1)));
  const { data: facturas } = await supabase.from("invoices").select("amount,issue_date").gte("issue_date", hace3);
  let meta = elegido ? Number(elegido.data.sim_compras) : 0;
  const origen = elegido ? `del ${elegido.name}` : "promedio de los últimos 3 meses";
  if (!meta) {
    const previas = (facturas ?? []).filter((f: any) => String(f.issue_date).slice(0, 7) < mes0);
    meta = Math.round(previas.reduce((a: number, f: any) => a + Number(f.amount), 0) / 3);
  }
  const pedido = (facturas ?? [])
    .filter((f: any) => String(f.issue_date).slice(0, 7) === mes0)
    .reduce((a: number, f: any) => a + Number(f.amount), 0);

  const lines = [negrita("🛒 Compras de hoy") + ` (meta ${money(meta)} al mes, ${origen})`];
  const queda = meta - pedido;
  lines.push(queda >= 0
    ? `Este mes ya se pidió ${money(pedido)}: quedan ${money(queda)} para pedir.`
    : `⚠️ Este mes ya se pidió ${money(pedido)}: te pasaste de la meta por ${money(-queda)}. Mejor balancear antes de pedir.`);
  const filas = [30, 60, 75, 90].map((plazo) => {
    const vence = addDays(today, plazo);
    const mes = vence.slice(0, 7);
    const ya = evs
      .filter((e) => (e.kind === "invoice" || e.kind === "letra") && e.date.slice(0, 7) === mes)
      .reduce((a, e) => a + e.amount, 0);
    return { plazo, vence, ya, espacio: Math.max(0, meta - ya), dia10: Number(vence.slice(8, 10)) <= 10 };
  });
  for (const f of filas) {
    // Entre paréntesis, lo que ya hay por pagar a proveedores ese mes.
    lines.push(`${f.espacio > 0 ? "🟢" : "🔴"} ${f.plazo} días → vence ${fmtLong(f.vence)}${f.dia10 ? " ⚠️" : ""} · `
      + (f.espacio > 0 ? `espacio ${money(f.espacio)}` : "ese mes ya está lleno")
      + ` (${money(f.ya)} por pagar ese mes)`);
  }
  const mejor = [...filas].sort((a, b) => b.espacio - a.espacio || b.plazo - a.plazo)[0];
  lines.push(mejor.espacio > 0
    ? `👉 Hoy conviene pedir a ${mejor.plazo} días.`
    : "👉 Ningún plazo tiene espacio: mejor esperar o cubrir con balanceo entre locales.");

  // Solo para emergencias de stock: con letra, el pago se puede correr hasta
  // los días de gracia (el banco cobra un recargo). No es lo recomendable.
  const gracia = (await loadSettings(supabase)).letra_dias_gracia_max;
  if (gracia > 0) {
    lines.push("", `🚨 Solo si es urgente (letra pagada hasta ${gracia} días después, con recargo del banco):`);
    for (const plazo of [60, 75, 90]) {
      const vence = addDays(today, plazo + gracia);
      const mes = vence.slice(0, 7);
      const ya = evs
        .filter((e) => (e.kind === "invoice" || e.kind === "letra") && e.date.slice(0, 7) === mes)
        .reduce((a, e) => a + e.amount, 0);
      const espacio = Math.max(0, meta - ya);
      const dia10 = Number(vence.slice(8, 10)) <= 10;
      lines.push(`${espacio > 0 ? "🟡" : "🔴"} ${plazo}+${gracia} días → ${fmtLong(vence)}${dia10 ? " ⚠️" : ""} · `
        + (espacio > 0 ? `espacio ${money(espacio)}` : "ese mes ya está lleno") + ` (${money(ya)} por pagar ese mes)`);
    }
  }
  lines.push("⚠️ = cae entre el 1 y el 10 (planilla, alquileres y bancos).");
  return lines;
}

async function handleCompras(supabase: any): Promise<string> {
  return (await comprasDelDia(supabase, todayLima())).join("\n");
}

/** El mismo reporte que antes mandaba scripts/telegram_daily_report.py vía
 * GitHub Actions — ahora lo dispara un cron de Supabase (pg_cron) en vez
 * del scheduler gratuito de GitHub Actions, que no garantiza la hora
 * (puede atrasarse varias horas sin avisar). */
async function buildDailyReportMessage(supabase: any): Promise<{ text: string; items: Evento[] }> {
  const today = todayLima();
  const settings = await loadSettings(supabase);
  const graciaMax = settings.letra_dias_gracia_max;
  const plazoTipico = settings.letra_dias_pago_tipico;
  const events = await buildEvents(supabase, today, settings);

  const hoy = events.filter((e) => e.date === today).sort((a, b) => b.amount - a.amount);
  const atrasados = events
    .filter((e) => e.overdue)
    .sort((a, b) => diasAtraso(b, today) - diasAtraso(a, today));
  // Una letra cuyo plazo típico vence hoy ya sale en "hoy": no repetirla en
  // la ventana (tendría dos números distintos para /pagar).
  const enHoy = new Set(hoy.map((e) => e.refId));
  const ventana = letrasEnVentana(events, today, plazoTipico).filter((e) => !enHoy.has(e.refId));

  // Numeración continua entre secciones (hoy 1..n, atrasados n+1.., ventana
  // ...) para que el reporte sirva directo con /pagar <N>.
  const lines = [`📅 Pagos de hoy, ${fmtLong(today)}`, ""];
  const listaHoy = listaPorTipo(hoy, lineaEnGrupo);
  if (hoy.length) {
    lines.push(...listaHoy.lines);
    lines.push("", `Total del día: ${money(sumAmount(hoy))}`);
  } else {
    lines.push("No hay pagos programados para hoy. 🎉");
  }

  const listaAtrasados = listaPorTipo(
    atrasados, (e, n) => `${lineaEnGrupo(e, n)} · ${diasAtraso(e, today)} día(s) de atraso`, hoy.length + 1,
  );
  if (atrasados.length) {
    lines.push("", "⚠️ Atrasados (aún sin pagar):", "");
    lines.push(...listaAtrasados.lines);
    lines.push("", `Total atrasado: ${money(sumAmount(atrasados))}`);
  }

  if (ventana.length) {
    const desde = hoy.length + atrasados.length + 1;
    lines.push("", `🧾 Letras en ventana de pago (ya vencieron, dentro de los ${plazoTipico} días típicos):`);
    ventana.forEach((e, i) => lines.push(lineaVentana(e, i + desde, today, graciaMax)));
    lines.push("", `Total en ventana: ${money(sumAmount(ventana))}`);
  }

  const items = [...listaHoy.orden, ...listaAtrasados.orden, ...ventana];
  if (items.length) lines.push("", "Para marcar uno: /pagar <N> (vale por 2 horas).");

  const ayer = addDays(today, -1);
  const faltantes = await sucursalesSinIngreso(supabase, ayer);
  if (faltantes.length) {
    lines.push("", `⚠️ Falta registrar el ingreso de ayer (${fmtLong(ayer)}) en: ${faltantes.join(", ")}`);
    lines.push("Usa /ingreso <sucursal> <monto> en el bot para ponerlo al día.");
  }

  try {
    lines.push("", ...(await comprasDelDia(supabase, today, events)));
  } catch (err) {
    console.error("Error armando compras del día:", err); // el reporte sale igual
  }

  return { text: lines.join("\n"), items };
}

/** Registra un ingreso (venta/cobro) de una sucursal. Cualquiera en el grupo
 * puede usarlo — no hay un control de permisos más fino que "está en el
 * grupo de Telegram del negocio", igual que los demás comandos. */
async function handleIngreso(supabase: any, argsText: string, fromName: string): Promise<string> {
  const names = await resolveBranchNames(supabase);
  const parts = argsText.trim().split(/\s+/).filter(Boolean);

  if (parts.length < 2) {
    return [
      "Uso: /ingreso <sucursal> <monto> [fecha] [reemplazar|sumar]",
      "Ej: /ingreso 1 1500  → Sucursal 1, hoy",
      "Ej: /ingreso 2 980 25/10",
      "Si ya había un ingreso para ese día: agrega «reemplazar» (cambia el monto) o «sumar» (lo registra aparte).",
      "",
      "Sucursales:",
      ...names.map((n, i) => `${i + 1}. ${n}`),
    ].join("\n");
  }

  // «reemplazar» / «sumar» pueden ir al final, con o sin fecha.
  const ultimo = parts[parts.length - 1].toLowerCase();
  const modo = ultimo === "reemplazar" || ultimo === "sumar" ? ultimo : null;
  if (modo) parts.pop();
  if (parts.length < 2) return "Falta la sucursal o el monto. Ej: /ingreso 1 1500 reemplazar";

  const [branchToken, montoToken, fechaToken] = parts;

  let branch: string | null = null;
  if (/^\d+$/.test(branchToken)) {
    branch = names[parseInt(branchToken, 10) - 1] ?? null;
  } else {
    const lower = branchToken.toLowerCase();
    branch = names.find((n) => n.toLowerCase() === lower || n.toLowerCase() === `sucursal ${lower}`) ?? null;
  }
  if (!branch) {
    return `No reconozco "${branchToken}" como sucursal. Usa el número o el nombre:\n${names.map((n, i) => `${i + 1}. ${n}`).join("\n")}`;
  }

  const monto = parseFloat(montoToken.replace(",", "."));
  // 0 es válido (local cerrado ese día); solo se rechaza negativo o no-numérico.
  if (isNaN(monto) || monto < 0) {
    return "El monto debe ser un número (0 o mayor). Ej: /ingreso 1 1500 o /ingreso 1 0";
  }

  const f = fechaPasadaOHoy(fechaToken, todayLima());
  if (f.error) return f.error;
  const fecha = f.fecha!;
  const montoRed = Math.round(monto * 100) / 100;

  // Un segundo /ingreso para la misma sucursal y día duplicaba la venta (y
  // el saldo de caja). Ahora se pide decir qué hacer con el que ya existe.
  const { data: existentes } = await supabase
    .from("incomes").select("id,amount,registered_by").eq("branch", branch).eq("date", fecha);
  const previos = existentes ?? [];
  if (previos.length && !modo) {
    const detalle = previos
      .map((r: any) => `${money(Number(r.amount))}${r.registered_by ? ` (de ${r.registered_by})` : ""}`)
      .join(" + ");
    return [
      `⚠️ ${branch} ya tiene ingreso el ${fmtLong(fecha)}: ${detalle}. No registré nada.`,
      `Para cambiarlo por ${money(montoRed)}: /ingreso ${branchToken} ${montoToken}${fechaToken ? " " + fechaToken : ""} reemplazar`,
      `Para sumarlo aparte: /ingreso ${branchToken} ${montoToken}${fechaToken ? " " + fechaToken : ""} sumar`,
    ].join("\n");
  }

  if (previos.length && modo === "reemplazar") {
    const { error: delErr } = await supabase.from("incomes").delete().in("id", previos.map((r: any) => r.id));
    if (delErr) {
      console.error("Error reemplazando ingreso:", delErr);
      return "No se pudo reemplazar el ingreso, intenta de nuevo.";
    }
  }

  const { error } = await supabase.from("incomes").insert({
    branch, date: fecha, amount: montoRed,
    registered_by: fromName || null, source: "bot",
  });
  if (error) {
    console.error("Error insertando ingreso:", error);
    return "No se pudo registrar el ingreso, intenta de nuevo.";
  }
  const verbo = previos.length && modo === "reemplazar" ? "Reemplazado" : previos.length ? "Sumado" : "Registrado";
  return `✅ ${verbo}: ${branch} · ${money(montoRed)} · ${fmtLong(fecha)}`;
}

const PAGAR_VIGENCIA_MS = 2 * 60 * 60 * 1000; // 2 horas
const DESHACER_VIGENCIA_MS = 30 * 60 * 1000; // 30 minutos

/** Cómo se marca pagado / pendiente cada tipo — igual que db.mark_invoice_paid,
 * db.mark_letra_paid y db.set_expense_status en la app. */
const TABLAS: Record<Kind, { tabla: string; estado: string; pendiente: string; pagado: string; fecha: string }> = {
  invoice: { tabla: "invoices", estado: "status", pendiente: "pendiente", pagado: "pagada", fecha: "paid_at" },
  letra: { tabla: "letras", estado: "estado", pendiente: "pendiente", pagado: "pagada", fecha: "fecha_pago" },
  expense: { tabla: "expenses", estado: "status", pendiente: "pendiente", pagado: "pagado", fecha: "paid_at" },
};

/** "2", "1 3 5", "1,3", "1-3" → [1, 2, 3...]. null si algún token no es un
 * número o rango válido. */
function parseNumeros(tokens: string[]): number[] | null {
  const out = new Set<number>();
  for (const tok of tokens.flatMap((t) => t.split(",")).filter(Boolean)) {
    const rango = tok.match(/^(\d+)-(\d+)$/);
    if (rango) {
      const [a, b] = [Number(rango[1]), Number(rango[2])];
      if (!a || b < a || b - a > 50) return null;
      for (let i = a; i <= b; i++) out.add(i);
    } else if (/^\d+$/.test(tok) && Number(tok) > 0) {
      out.add(Number(tok));
    } else {
      return null;
    }
  }
  return out.size ? [...out].sort((x, y) => x - y) : null;
}

function descItem(it: any): string {
  return `${it.vendor} · ${it.label} · ${it.branch} · ${money(it.amount)}`;
}

/** Marca como pagados uno o varios ítems de la última lista numerada que vio
 * este chat (ver guardarListaParaPagar). Solo cambia lo que SIGUE pendiente:
 * si alguien ya lo pagó (desde la app u otro /pagar) no le pisa la fecha ni
 * quién pagó — antes sí lo sobrescribía. Por eso la lista ya no se borra
 * después de pagar: /pagar 1 y luego /pagar 3 usan la misma lista que viste.
 * Guarda lo pagado en bot_list_cache.ultimo_pago para /deshacer. */
async function handlePagar(supabase: any, chatId: number | string, argsText: string, fromName: string): Promise<string> {
  const parts = argsText.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) {
    return [
      "Uso: /pagar <N> [más números] [fecha]",
      `El número es el de la última lista que viste (${LISTAS_PAGABLES}).`,
      "Ej: /pagar 2  → marca pagado hoy el ítem 2",
      "Ej: /pagar 1 3 5  o  /pagar 1-3  → varios a la vez",
      "Ej: /pagar 2 25/10  → con esa fecha de pago",
      "Si te equivocas: /deshacer (hasta 30 minutos después).",
    ].join("\n");
  }

  // La fecha va al final y se distingue de un rango "1-3" por tener "/" o
  // ser YYYY-MM-DD.
  const today = todayLima();
  let fechaToken: string | undefined;
  const ultimo = parts[parts.length - 1];
  if (ultimo.includes("/") || /^\d{4}-\d{1,2}-\d{1,2}$/.test(ultimo)) fechaToken = parts.pop();
  const f = fechaPasadaOHoy(fechaToken, today);
  if (f.error) return f.error;
  const fecha = f.fecha!;

  const numeros = parseNumeros(parts);
  if (!numeros) {
    return "No entendí los números. Ej: /pagar 2, /pagar 1 3 5 o /pagar 1-3 (fecha opcional al final: 25/10).";
  }

  const { data: cacheRow } = await supabase
    .from("bot_list_cache")
    .select("items,created_at")
    .eq("chat_id", chatId)
    .maybeSingle();

  if (!cacheRow) {
    return `No tengo una lista reciente — pide una primero (${LISTAS_PAGABLES}) y luego /pagar <N>.`;
  }
  const edadMs = Date.now() - new Date(cacheRow.created_at).getTime();
  if (edadMs > PAGAR_VIGENCIA_MS) {
    return `Esa lista ya es muy vieja (más de 2 horas) — pide una nueva (${LISTAS_PAGABLES}) y luego /pagar <N>.`;
  }

  const items: any[] = cacheRow.items ?? [];
  const faltan = numeros.filter((n) => !items.some((it) => it.n === n));
  if (faltan.length) {
    return `No hay ítem ${faltan.join(", ")} en la última lista (tenía ${items.length}). No marqué nada — revisa los números.`;
  }

  const actor = fromName || null;
  const pagados: any[] = [];
  const lines: string[] = [];
  for (const n of numeros) {
    const item = items.find((it) => it.n === n)!;
    const t = TABLAS[item.kind as Kind];
    const { data, error } = await supabase.from(t.tabla)
      .update({ [t.estado]: t.pagado, [t.fecha]: fecha, paid_by: actor })
      .eq("id", item.ref_id)
      .eq(t.estado, t.pendiente)
      .select("id");
    if (error) {
      console.error("Error marcando como pagado:", error);
      lines.push(`❌ ${n}. No se pudo marcar: ${descItem(item)}`);
    } else if (!data?.length) {
      const { data: actual } = await supabase.from(t.tabla)
        .select(`${t.estado},${t.fecha},paid_by`).eq("id", item.ref_id).maybeSingle();
      const quien = actual?.paid_by ? ` por ${actual.paid_by}` : "";
      const cuando = actual?.[t.fecha] ? ` el ${fmtLong(actual[t.fecha])}` : "";
      lines.push(actual
        ? `ℹ️ ${n}. Ya estaba ${actual[t.estado]}${quien}${cuando} — no lo cambié: ${descItem(item)}`
        : `ℹ️ ${n}. Ya no existe (lo borraron): ${descItem(item)}`);
    } else {
      pagados.push(item);
      lines.push(`✅ ${n}. ${descItem(item)}`);
    }
  }

  if (pagados.length) {
    const { error } = await supabase.from("bot_list_cache")
      .update({ ultimo_pago: { at: new Date().toISOString(), by: actor, fecha, items: pagados } })
      .eq("chat_id", chatId);
    if (error) console.error("No se pudo guardar el pago para /deshacer (¿falta la migración?):", error);
  }

  const titulo = pagados.length
    ? `Marcado como pagado (${fmtLong(fecha)}) — ${pagados.length} ítem(s) · ${money(pagados.reduce((a, it) => a + it.amount, 0))}`
    : "No se marcó nada nuevo.";
  const pie = pagados.length ? ["", "¿Te equivocaste? /deshacer"] : [];
  return [titulo, "", ...lines, ...pie].join("\n");
}

/** Revierte el último /pagar de este chat (hasta DESHACER_VIGENCIA_MS
 * después): vuelve a pendiente solo lo que ese /pagar marcó y que sigue
 * pagado. */
async function handleDeshacer(supabase: any, chatId: number | string): Promise<string> {
  const { data: cacheRow, error } = await supabase
    .from("bot_list_cache").select("ultimo_pago").eq("chat_id", chatId).maybeSingle();
  if (error) {
    console.error("Error leyendo ultimo_pago (¿falta migracion_2026-10_bot_deshacer.sql?):", error);
    return "No pude leer el último pago. Avísale al administrador (falta una migración).";
  }
  const up = cacheRow?.ultimo_pago;
  if (!up?.items?.length) return "No hay ningún /pagar reciente para deshacer.";
  if (Date.now() - new Date(up.at).getTime() > DESHACER_VIGENCIA_MS) {
    return "El último /pagar fue hace más de 30 minutos — corrígelo en la app (Letras / Facturas / Gastos → Gestionar).";
  }

  const lines: string[] = [];
  let revertidos = 0;
  for (const item of up.items) {
    const t = TABLAS[item.kind as Kind];
    const { data, error: upErr } = await supabase.from(t.tabla)
      .update({ [t.estado]: t.pendiente, [t.fecha]: null, paid_by: null })
      .eq("id", item.ref_id)
      .eq(t.estado, t.pagado)
      .select("id");
    if (upErr) {
      console.error("Error deshaciendo pago:", upErr);
      lines.push(`❌ No se pudo revertir: ${descItem(item)}`);
    } else if (!data?.length) {
      lines.push(`ℹ️ Ya no estaba pagado, no lo toqué: ${descItem(item)}`);
    } else {
      revertidos++;
      lines.push(`↩️ ${descItem(item)}`);
    }
  }
  await supabase.from("bot_list_cache").update({ ultimo_pago: null }).eq("chat_id", chatId);
  return [`Deshecho: ${revertidos} ítem(s) volvieron a pendiente.`, "", ...lines].join("\n");
}

/** Todo lo pendiente de un proveedor (o número de factura/letra), con su
 * total, más lo último pagado de ese proveedor — para revisar de un vistazo
 * si falta algo o si algo se marcó pagado por error. */
async function handleBuscar(supabase: any, chatId: number | string, argsText: string): Promise<string> {
  const q = normalizar(argsText);
  if (q.length < 2) {
    return "Uso: /buscar <proveedor o número>\nEj: /buscar mym  ·  /buscar 137857  ·  /buscar FF04-397751";
  }
  const today = todayLima();
  const settings = await loadSettings(supabase);
  const coincide = (e: Evento) => normalizar(`${e.vendor} ${e.label} ${e.invoice_number}`).includes(q);

  const pendientes = (await buildEvents(supabase, today, settings))
    .filter(coincide)
    .sort((a, b) => ((a.vencimiento_real ?? a.date) < (b.vencimiento_real ?? b.date) ? -1 : 1));
  const pagados = (await buildPaidEvents(supabase))
    .filter(coincide)
    .sort((a, b) => (a.date < b.date ? 1 : -1))
    .slice(0, 5);

  const lines = [`🔎 "${argsText.trim()}"`, ""];
  if (pendientes.length) {
    lines.push(`Pendiente: ${pendientes.length} · ${money(sumAmount(pendientes))}`);
    pendientes.forEach((e, i) => {
      const vence = e.vencimiento_real ?? e.date;
      const marca = e.overdue ? " ⚠️ atrasado" : "";
      lines.push(`${linea(e, i + 1)} · vence ${fmtLong(vence)}${marca}`);
    });
    await guardarListaParaPagar(supabase, chatId, pendientes);
  } else {
    lines.push("Nada pendiente con ese nombre o número.");
  }
  if (pagados.length) {
    lines.push("", "Últimos pagados:");
    pagados.forEach((e) => lines.push(`• ${fmtLong(e.date)} · ${e.vendor}${refFactura(e)} · ${e.label} · ${money(e.amount)}${e.paidBy ? ` · ${e.paidBy}` : ""}`));
  }
  return lines.join("\n");
}

/** Saldo de caja actual (ver utils.compute_cash_balance): saldo inicial +
 * ingresos registrados después de esa fecha - egresos ya PAGADOS después de
 * esa fecha. `events` son los eventos pendientes (buildEvents), reusados
 * tanto por /saldo (comprometido = todos, sin importar fecha) como por
 * /simular (comprometido_antes = solo los que vencen antes de cierta
 * fecha). null si todavía no se configuró el saldo inicial. */
async function computeCaja(supabase: any, today: string): Promise<{ saldoActual: number; events: Evento[] } | null> {
  const settings = await loadSettings(supabase);
  const saldoInicial = settings.caja_saldo_inicial;
  const desde = settings.caja_saldo_inicial_fecha;
  if (!desde) return null;

  const { data: incomesAfter } = await supabase.from("incomes").select("amount").gt("date", desde);
  const ingresos = (incomesAfter ?? []).reduce((a: number, r: any) => a + Number(r.amount), 0);

  const { data: invPaid } = await supabase.from("invoices").select("amount").eq("status", "pagada").gt("paid_at", desde);
  const { data: letPaid } = await supabase.from("letras").select("monto").eq("estado", "pagada").gt("fecha_pago", desde);
  const { data: expPaid } = await supabase.from("expenses").select("amount").eq("status", "pagado").gt("paid_at", desde);
  const pagado =
    (invPaid ?? []).reduce((a: number, r: any) => a + Number(r.amount), 0) +
    (letPaid ?? []).reduce((a: number, r: any) => a + Number(r.monto), 0) +
    (expPaid ?? []).reduce((a: number, r: any) => a + Number(r.amount), 0);

  const saldoActual = saldoInicial + ingresos - pagado;
  const events = await buildEvents(supabase, today, settings);
  return { saldoActual, events };
}

async function handleSaldo(supabase: any): Promise<string> {
  const today = todayLima();
  const caja = await computeCaja(supabase, today);
  if (!caja) {
    return "Todavía no configuraste el saldo inicial de caja. Hazlo en la app: Configuración → Saldo inicial de caja.";
  }
  const comprometido = sumAmount(caja.events);
  const disponible = caja.saldoActual - comprometido;

  const lines = [
    "💰 Saldo de caja",
    "",
    `Saldo actual: ${money(caja.saldoActual)}`,
    `Comprometido (pendiente): ${money(comprometido)}`,
    `Disponible para comprometer: ${money(disponible)}`,
  ];
  if (disponible < 0) {
    lines.push("", "⚠️ Ya tienes más comprometido que lo que hay en caja.");
  }
  return lines.join("\n");
}

/** ¿Cuánto se puede comprometer con un proveedor a `plazo` días, o alcanza
 * un `monto` dado? Misma lógica que utils.max_new_purchase / el simulador
 * de Presupuesto: proyecta la caja a la fecha en que vencería la compra
 * (saldo actual + venta promedio proyectada - todo lo ya comprometido que
 * vence en o antes de esa fecha). */
interface SimResult {
  fechaVence: string;
  semanaMasAjustada: string;
  proyectado: number;
  maximo: number;
}

/** Igual que utils.max_new_purchase (Python): revisa semana por semana
 * desde hoy hasta fechaVence (hoy + plazo) en vez de un solo punto final —
 * si algo grande cae unos días antes, esa semana es el verdadero cuello de
 * botella, no el día final (que puede verse bien solo por tener más venta
 * acumulada para entonces). */
function maxNewPurchase(events: Evento[], saldoActual: number, ventaDiaria: number, plazo: number, today: string): SimResult {
  const fechaVence = addDays(today, plazo);
  let ws = startOfWeek(today);
  let peor: { finSemana: string; proyectado: number } | null = null;

  while (ws <= fechaVence) {
    const finSemana = addDays(ws, 6) < fechaVence ? addDays(ws, 6) : fechaVence;
    const dias = Math.round((parseISO(finSemana).getTime() - parseISO(today).getTime()) / 86400000);
    const comprometido = events.filter((e) => e.date <= finSemana).reduce((a, e) => a + e.amount, 0);
    const proyectado = saldoActual + ventaDiaria * dias - comprometido;
    if (!peor || proyectado < peor.proyectado) peor = { finSemana, proyectado };
    ws = addDays(ws, 7);
  }

  const resultado = peor ?? { finSemana: fechaVence, proyectado: saldoActual };
  return {
    fechaVence,
    semanaMasAjustada: resultado.finSemana,
    proyectado: resultado.proyectado,
    maximo: Math.max(0, resultado.proyectado),
  };
}

async function handleSimular(supabase: any, argsText: string): Promise<string> {
  const parts = argsText.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) {
    return [
      "Uso: /simular <plazo_dias> [monto]",
      "Ej: /simular 60  → máximo recomendado a 60 días",
      "Ej: /simular 60 5000  → ¿me alcanza 5000 a 60 días?",
    ].join("\n");
  }

  const plazo = parseInt(parts[0], 10);
  if (!plazo || plazo <= 0) {
    return "El plazo debe ser un número de días mayor a 0. Ej: /simular 60";
  }

  const today = todayLima();
  const caja = await computeCaja(supabase, today);
  if (!caja) {
    return "Todavía no configuraste el saldo inicial de caja. Hazlo en la app: Configuración → Saldo inicial de caja.";
  }

  const desdeVenta = addDays(today, -29);
  const { data: incomesRecent } = await supabase.from("incomes").select("amount").gte("date", desdeVenta).lte("date", today);
  const ventaDiaria = (incomesRecent ?? []).reduce((a: number, r: any) => a + Number(r.amount), 0) / 30;

  const sim = maxNewPurchase(caja.events, caja.saldoActual, ventaDiaria, plazo, today);

  const lines = [
    `🧮 Simulación a ${plazo} días (vencería el ${fmtLong(sim.fechaVence)})`,
    "",
    `Máximo recomendado: ${money(sim.maximo)}`,
  ];
  if (sim.semanaMasAjustada !== sim.fechaVence) {
    lines.push(`📍 Limitado por la semana del ${fmtLong(sim.semanaMasAjustada)}, no por el día final.`);
  }

  const montoToken = parts[1];
  if (montoToken) {
    const monto = parseFloat(montoToken.replace(",", "."));
    if (!isNaN(monto) && monto >= 0) {
      lines.push("");
      lines.push(
        monto > sim.maximo
          ? `⚠️ ${money(monto)} supera lo recomendado (te alcanzaría hasta ${money(sim.maximo)}).`
          : `✅ ${money(monto)} está dentro de lo recomendado.`,
      );
    }
  }

  if (sim.proyectado <= 0) {
    lines.push("", `⚠️ Ya proyectas caja en rojo para la semana del ${fmtLong(sim.semanaMasAjustada)} — no es recomendable comprometer nada nuevo a ese plazo.`);
  }

  return lines.join("\n");
}

const AYUDA = [
  "Hola 👋 Soy el bot de Control Compras. Comandos disponibles:",
  "",
  "/hoy — pagos de hoy",
  "/manana — pagos de mañana",
  "/semana — los próximos 7 días, día por día",
  "/meses — pagos por semana del mes actual y el próximo",
  "/atrasados — lo vencido que aún no se paga",
  "/ventana — letras ya vencidas pero aún no atrasadas (su ventana real de pago)",
  "/pagados [N] — lo pagado esta semana, o N semanas atrás (ej. /pagados 1)",
  "/resumen — panorama rápido: hoy + atrasados + próximos 7 días",
  "/buscar <proveedor o número> — todo lo pendiente de ese proveedor + lo último pagado (ej. /buscar mym)",
  "/ingreso <sucursal> <monto> [fecha] — registra una venta/cobro del día",
  `/pagar <N> [fecha] — marca pagado el ítem N (o varios: 1 3 5, 1-3) de la última lista (${LISTAS_PAGABLES})`,
  "/deshacer — revierte el último /pagar (hasta 30 minutos después)",
  "/saldo — saldo de caja real y cuánto queda disponible para comprometer",
  "/compras — cuánto queda para comprar este mes y qué plazo (30/60/75/90 días) tiene espacio hoy",
  "/simular <plazo_dias> [monto] — ¿cuánto me alcanza (o me alcanza X) con un proveedor a ese plazo?",
].join("\n");

/** Lo que muestra el botón "Menú" de Telegram al lado del cuadro de texto
 * (setMyCommands). Telegram solo acepta minúsculas, números y "_" en el
 * comando, y hasta 256 caracteres en la descripción. */
const MENU_COMANDOS = [
  ["hoy", "Pagos de hoy"],
  ["manana", "Pagos de mañana"],
  ["semana", "Los próximos 7 días, día por día"],
  ["atrasados", "Lo vencido que aún no se paga"],
  ["ventana", "Letras vencidas aún dentro del plazo"],
  ["resumen", "Panorama: hoy, atrasados y la semana"],
  ["buscar", "Pendientes de un proveedor (ej. /buscar mym)"],
  ["pagar", "Marca pagado el N° de la última lista (ej. /pagar 2)"],
  ["deshacer", "Revierte el último /pagar (30 min)"],
  ["ingreso", "Registra la venta de una sucursal"],
  ["pagados", "Lo pagado esta semana (o /pagados 1)"],
  ["meses", "Pagos por semana, este mes y el próximo"],
  ["saldo", "Saldo de caja y disponible"],
  ["compras", "Cuánto comprar hoy y a qué plazo"],
  ["simular", "¿Cuánto me alcanza a N días? (ej. /simular 60)"],
  ["ayuda", "Todos los comandos con su explicación"],
].map(([command, description]) => ({ command, description }));

let menuRegistrado = false;

/** Registra MENU_COMANDOS una vez por arranque de la función (Telegram lo
 * guarda; repetirlo no cambia nada). Si falla, el bot sigue respondiendo. */
async function registrarMenu(token: string) {
  if (menuRegistrado) return;
  menuRegistrado = true;
  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/setMyCommands`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ commands: MENU_COMANDOS }),
    });
    if (!res.ok) {
      menuRegistrado = false;
      console.error("setMyCommands respondió", res.status, await res.text());
    }
  } catch (err) {
    menuRegistrado = false;
    console.error("No se pudo registrar el menú de comandos:", err);
  }
}

/** null => no es un comando dirigido al bot: no se responde nada (el grupo
 * tiene el modo privacidad desactivado, así que el webhook recibe TODOS los
 * mensajes del grupo, no solo los que le escriben al bot). */
async function responderComando(
  supabase: any, text: string, fromName: string, chatId: number | string,
): Promise<string | null> {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) return null;
  const cmd = trimmed.split(/\s+/)[0].split("@")[0].toLowerCase();
  switch (cmd) {
    case "/hoy": return await handleHoy(supabase, chatId);
    case "/manana": case "/mañana": return await handleManana(supabase, chatId);
    case "/semana": return await handleSemana(supabase, chatId);
    case "/meses": case "/mes": return await handleMeses(supabase);
    case "/atrasados": return await handleAtrasados(supabase, chatId);
    case "/ventana": return await handleVentana(supabase, chatId);
    case "/pagados": {
      const arg = trimmed.split(/\s+/)[1];
      const weeksBack = Math.max(0, parseInt(arg ?? "0", 10) || 0);
      return await handlePagados(supabase, weeksBack);
    }
    case "/resumen": return await handleResumen(supabase, chatId);
    case "/ingreso": {
      const argsText = trimmed.split(/\s+/).slice(1).join(" ");
      return await handleIngreso(supabase, argsText, fromName);
    }
    case "/pagar": {
      const argsText = trimmed.split(/\s+/).slice(1).join(" ");
      return await handlePagar(supabase, chatId, argsText, fromName);
    }
    case "/deshacer": return await handleDeshacer(supabase, chatId);
    case "/buscar": {
      const argsText = trimmed.split(/\s+/).slice(1).join(" ");
      return await handleBuscar(supabase, chatId, argsText);
    }
    case "/saldo": return await handleSaldo(supabase);
    case "/compras": return await handleCompras(supabase);
    case "/simular": {
      const argsText = trimmed.split(/\s+/).slice(1).join(" ");
      return await handleSimular(supabase, argsText);
    }
    case "/start": case "/ayuda": case "/help": return AYUDA;
    default: return `No entendí ese comando.\n\n${AYUDA}`;
  }
}

// Telegram rechaza mensajes de más de 4096 caracteres (y el envío fallaba
// sin que nadie se enterara): se parte por líneas, con margen.
const TELEGRAM_MAX = 3900;

function partirMensaje(text: string): string[] {
  const partes: string[] = [];
  let actual = "";
  for (const linea of text.split("\n")) {
    const l = linea.length > TELEGRAM_MAX ? linea.slice(0, TELEGRAM_MAX - 1) + "…" : linea;
    if (actual && actual.length + 1 + l.length > TELEGRAM_MAX) {
      partes.push(actual);
      actual = l;
    } else {
      actual = actual ? `${actual}\n${l}` : l;
    }
  }
  if (actual) partes.push(actual);
  return partes;
}

/** Texto del bot a HTML de Telegram: escapa todo (un "&" o "<" en un nombre
 * de proveedor rompería el envío) y convierte las marcas de negrita(). */
function aHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .split(NEGRITA_INI).join("<b>").split(NEGRITA_FIN).join("</b>");
}

async function sendTelegram(token: string, chatId: number | string, text: string) {
  // HTML y no Markdown: con Markdown un vendor con "_" o "*" en el nombre
  // rompía el parser y el envío fallaba en silencio.
  for (const parte of partirMensaje(text)) {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: aHtml(parte), parse_mode: "HTML" }),
    });
    if (!res.ok) {
      console.error("Telegram respondió", res.status, await res.text());
    }
  }
}

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("ok", { status: 200 });
  }

  const token = Deno.env.get("TELEGRAM_BOT_TOKEN");
  if (!token) {
    console.error("Falta el secret TELEGRAM_BOT_TOKEN");
    return new Response("ok", { status: 200 });
  }
  await registrarMenu(token);

  const body = await req.json().catch(() => null);

  // Disparo del reporte diario (pg_cron -> pg_net), no un webhook de
  // Telegram: no trae el header de Telegram, se valida con su propio
  // secret (CRON_SECRET) en el body.
  if (body?.type === "daily_report") {
    const cronSecret = Deno.env.get("CRON_SECRET");
    const chatId = Deno.env.get("TELEGRAM_CHAT_ID");
    if (!cronSecret || body?.cron_secret !== cronSecret) {
      return new Response("forbidden", { status: 403 });
    }
    if (!chatId) {
      console.error("Falta el secret TELEGRAM_CHAT_ID");
      return new Response("ok", { status: 200 });
    }
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );
    try {
      const reporte = await buildDailyReportMessage(supabase);
      await sendTelegram(token, chatId, reporte.text);
      await guardarListaParaPagar(supabase, chatId, reporte.items);
    } catch (err) {
      console.error("Error generando el reporte diario:", err);
    }
    return new Response("ok", { status: 200 });
  }

  // Webhook normal de Telegram (mensaje de alguien en el grupo).
  // Obligatorio: sin él, cualquiera que conozca la URL de la función podría
  // mandarle comandos (incluidos /pagar e /ingreso) haciéndose pasar por Telegram.
  const webhookSecret = Deno.env.get("TELEGRAM_WEBHOOK_SECRET");
  if (!webhookSecret) {
    console.error("Falta el secret TELEGRAM_WEBHOOK_SECRET — se rechazan todos los mensajes");
    return new Response("forbidden", { status: 403 });
  }
  if (req.headers.get("X-Telegram-Bot-Api-Secret-Token") !== webhookSecret) {
    return new Response("forbidden", { status: 403 });
  }

  const message = body?.message;
  const text: string | undefined = message?.text;
  const chatId = message?.chat?.id;
  const fromName: string = [message?.from?.first_name, message?.from?.last_name]
    .filter(Boolean).join(" ");

  if (!text || !chatId || !text.trim().startsWith("/")) {
    return new Response("ok", { status: 200 });
  }

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  try {
    const reply = await responderComando(supabase, text, fromName, chatId);
    if (reply) await sendTelegram(token, chatId, reply);
  } catch (err) {
    console.error("Error respondiendo comando:", err);
    await sendTelegram(token, chatId, "Ocurrió un error consultando la información, intenta de nuevo en un momento.");
  }

  return new Response("ok", { status: 200 });
});
