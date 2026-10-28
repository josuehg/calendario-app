// Bot de Telegram para Control Compras — responde comandos bajo demanda
// (/hoy, /manana, /semana, /meses, /atrasados, /pagados, /resumen, /saldo,
// /simular) y permite registrar ingresos (/ingreso), consultando y
// escribiendo en Supabase directamente.
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

async function buildPaidEvents(supabase: any): Promise<Evento[]> {
  const { data: invoicesPaid } = await supabase
    .from("invoices")
    .select("id,vendor,branch,invoice_number,doc_type,amount,paid_at,paid_by")
    .eq("status", "pagada");

  const { data: letrasPaid } = await supabase
    .from("letras")
    .select("id,numero,monto,vendor,branch,fecha_pago,paid_by")
    .eq("estado", "pagada");

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
    });
  }

  for (const l of letrasPaid ?? []) {
    if (!l.fecha_pago) continue;
    events.push({
      date: l.fecha_pago,
      amount: Number(l.monto),
      vendor: l.vendor || "—",
      branch: l.branch || "—",
      invoice_number: "—",
      label: `Letra ${l.numero || "—"}`,
      overdue: false,
      kind: "letra",
      paidBy: l.paid_by ?? undefined,
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

function linea(e: Evento, n: number): string {
  const ref = e.invoice_number && e.kind !== "expense" ? ` · Fact. ${e.invoice_number}` : "";
  return `${n}. ${e.vendor}${ref} · ${e.label} · ${e.branch} · ${money(e.amount)}`;
}

function lineaPagado(e: Evento, n: number): string {
  const ref = e.invoice_number && e.invoice_number !== "—" && e.kind !== "expense" ? ` · Fact. ${e.invoice_number}` : "";
  const quien = e.paidBy ? ` · pagó ${e.paidBy}` : "";
  return `${n}. ${e.vendor}${ref} · ${e.label} · ${e.branch} · ${money(e.amount)}${quien}`;
}

/** Lista numerada 1. 2. 3. ... para los comandos del bot (en vez de viñetas). */
function numeradas(items: Evento[], fn: (e: Evento, n: number) => string): string[] {
  return items.map((e, i) => fn(e, i + 1));
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
  lines.push(...numeradas(hoy, linea));
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
  lines.push(...numeradas(items, linea));
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
    lines.push(...numeradas(dia, linea));
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
  atrasados.forEach((e, i) => {
    lines.push(`${linea(e, i + 1)} · ${diasAtraso(e, today, graciaMax)} día(s) de atraso`);
  });
  lines.push("", `Total atrasado: ${money(sumAmount(atrasados))}`);
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

async function handleResumen(supabase: any): Promise<string> {
  const today = todayLima();
  const hasta = addDays(today, 6);
  const events = await buildEvents(supabase, today);

  const hoy = events.filter((e) => e.date === today).sort((a, b) => b.amount - a.amount);
  const atrasados = events.filter((e) => e.overdue);
  const semana = events.filter((e) => e.date >= today && e.date <= hasta);

  const lines = [`📊 Resumen rápido — ${fmtLong(today)}`, ""];

  lines.push(`📅 Hoy: ${hoy.length} pago(s) · ${money(sumAmount(hoy))}`);
  lines.push(...numeradas(hoy, linea));
  lines.push("");

  lines.push(`⚠️ Atrasados: ${atrasados.length} pago(s) · ${money(sumAmount(atrasados))}`);
  if (atrasados.length) lines.push("(escribe /atrasados para el detalle)");
  lines.push("");

  lines.push(`📈 Próximos 7 días: ${money(sumAmount(semana))} (escribe /semana para el detalle)`);

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

/** El mismo reporte que antes mandaba scripts/telegram_daily_report.py vía
 * GitHub Actions — ahora lo dispara un cron de Supabase (pg_cron) en vez
 * del scheduler gratuito de GitHub Actions, que no garantiza la hora
 * (puede atrasarse varias horas sin avisar). */
async function buildDailyReportMessage(supabase: any): Promise<string> {
  const today = todayLima();
  const { data: settingsRow } = await supabase.from("app_settings").select("*").eq("id", 1).single();
  const graciaMax = settingsRow?.letra_dias_gracia_max ?? 10;
  const events = await buildEvents(supabase, today);

  const hoy = events.filter((e) => e.date === today).sort((a, b) => b.amount - a.amount);
  const atrasados = events
    .filter((e) => e.overdue)
    .sort((a, b) => diasAtraso(b, today, graciaMax) - diasAtraso(a, today, graciaMax));

  const lines = [`📅 Pagos de hoy, ${fmtLong(today)}`, ""];
  if (hoy.length) {
    lines.push(...numeradas(hoy, linea));
    lines.push("", `Total del día: ${money(sumAmount(hoy))}`);
  } else {
    lines.push("No hay pagos programados para hoy. 🎉");
  }

  if (atrasados.length) {
    lines.push("", "⚠️ Atrasados (aún sin pagar):");
    atrasados.forEach((e, i) => {
      lines.push(`${linea(e, i + 1)} · ${diasAtraso(e, today, graciaMax)} día(s) de atraso`);
    });
    lines.push("", `Total atrasado: ${money(sumAmount(atrasados))}`);
  }

  const ayer = addDays(today, -1);
  const faltantes = await sucursalesSinIngreso(supabase, ayer);
  if (faltantes.length) {
    lines.push("", `⚠️ Falta registrar el ingreso de ayer (${fmtLong(ayer)}) en: ${faltantes.join(", ")}`);
    lines.push("Usa /ingreso <sucursal> <monto> en el bot para ponerlo al día.");
  }

  return lines.join("\n");
}

/** Registra un ingreso (venta/cobro) de una sucursal. Cualquiera en el grupo
 * puede usarlo — no hay un control de permisos más fino que "está en el
 * grupo de Telegram del negocio", igual que los demás comandos. */
async function handleIngreso(supabase: any, argsText: string, fromName: string): Promise<string> {
  const names = await resolveBranchNames(supabase);
  const parts = argsText.trim().split(/\s+/).filter(Boolean);

  if (parts.length < 2) {
    return [
      "Uso: /ingreso <sucursal> <monto> [fecha YYYY-MM-DD]",
      "Ej: /ingreso 1 1500  → Sucursal 1, hoy",
      "Ej: /ingreso 2 980 2026-10-25",
      "",
      "Sucursales:",
      ...names.map((n, i) => `${i + 1}. ${n}`),
    ].join("\n");
  }

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

  let fecha = todayLima();
  if (fechaToken) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(fechaToken)) {
      return "La fecha debe ir como YYYY-MM-DD, ej: 2026-10-25";
    }
    fecha = fechaToken;
  }

  const { error } = await supabase.from("incomes").insert({
    branch, date: fecha, amount: Math.round(monto * 100) / 100,
    registered_by: fromName || null, source: "bot",
  });
  if (error) {
    console.error("Error insertando ingreso:", error);
    return "No se pudo registrar el ingreso, intenta de nuevo.";
  }
  return `✅ Registrado: ${branch} · ${money(monto)} · ${fmtLong(fecha)}`;
}

/** Saldo de caja actual (ver utils.compute_cash_balance): saldo inicial +
 * ingresos registrados después de esa fecha - egresos ya PAGADOS después de
 * esa fecha. `events` son los eventos pendientes (buildEvents), reusados
 * tanto por /saldo (comprometido = todos, sin importar fecha) como por
 * /simular (comprometido_antes = solo los que vencen antes de cierta
 * fecha). null si todavía no se configuró el saldo inicial. */
async function computeCaja(supabase: any, today: string): Promise<{ saldoActual: number; events: Evento[] } | null> {
  const { data: settingsRow } = await supabase.from("app_settings").select("*").eq("id", 1).single();
  const saldoInicial = Number(settingsRow?.caja_saldo_inicial ?? 0);
  const desde: string | null = settingsRow?.caja_saldo_inicial_fecha ?? null;
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
  const events = await buildEvents(supabase, today);
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
  "/semana — resumen de los próximos 7 días",
  "/meses — pagos por semana del mes actual y el próximo",
  "/atrasados — lo vencido que aún no se paga",
  "/pagados [N] — lo pagado esta semana, o N semanas atrás (ej. /pagados 1)",
  "/resumen — panorama rápido: hoy + atrasados + próximos 7 días",
  "/ingreso <sucursal> <monto> [fecha] — registra una venta/cobro del día",
  "/saldo — saldo de caja real y cuánto queda disponible para comprometer",
  "/simular <plazo_dias> [monto] — ¿cuánto me alcanza (o me alcanza X) con un proveedor a ese plazo?",
].join("\n");

/** null => no es un comando dirigido al bot: no se responde nada (el grupo
 * tiene el modo privacidad desactivado, así que el webhook recibe TODOS los
 * mensajes del grupo, no solo los que le escriben al bot). */
async function responderComando(supabase: any, text: string, fromName: string): Promise<string | null> {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) return null;
  const cmd = trimmed.split(/\s+/)[0].split("@")[0].toLowerCase();
  switch (cmd) {
    case "/hoy": return await handleHoy(supabase);
    case "/manana": case "/mañana": return await handleManana(supabase);
    case "/semana": return await handleSemana(supabase);
    case "/meses": case "/mes": return await handleMeses(supabase);
    case "/atrasados": return await handleAtrasados(supabase);
    case "/pagados": {
      const arg = trimmed.split(/\s+/)[1];
      const weeksBack = Math.max(0, parseInt(arg ?? "0", 10) || 0);
      return await handlePagados(supabase, weeksBack);
    }
    case "/resumen": return await handleResumen(supabase);
    case "/ingreso": {
      const argsText = trimmed.split(/\s+/).slice(1).join(" ");
      return await handleIngreso(supabase, argsText, fromName);
    }
    case "/saldo": return await handleSaldo(supabase);
    case "/simular": {
      const argsText = trimmed.split(/\s+/).slice(1).join(" ");
      return await handleSimular(supabase, argsText);
    }
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

  const token = Deno.env.get("TELEGRAM_BOT_TOKEN");
  if (!token) {
    console.error("Falta el secret TELEGRAM_BOT_TOKEN");
    return new Response("ok", { status: 200 });
  }

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
      await sendTelegram(token, chatId, reporte);
    } catch (err) {
      console.error("Error generando el reporte diario:", err);
    }
    return new Response("ok", { status: 200 });
  }

  // Webhook normal de Telegram (mensaje de alguien en el grupo).
  const webhookSecret = Deno.env.get("TELEGRAM_WEBHOOK_SECRET");
  if (webhookSecret) {
    const got = req.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (got !== webhookSecret) {
      return new Response("forbidden", { status: 403 });
    }
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
    const reply = await responderComando(supabase, text, fromName);
    if (reply) await sendTelegram(token, chatId, reply);
  } catch (err) {
    console.error("Error respondiendo comando:", err);
    await sendTelegram(token, chatId, "Ocurrió un error consultando la información, intenta de nuevo en un momento.");
  }

  return new Response("ok", { status: 200 });
});
