"""PDF de una página (o dos) con el escenario del Simulador, para presentarlo a
los socios: de dónde se parte, en qué se usa el crédito, cómo queda la caja
mes a mes y qué hay que cuidar. Sin gráficos de librerías externas: el
gráfico se dibuja con rectángulos de fpdf."""
from fpdf import FPDF

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
VERDE = (11, 93, 104)
ROJO = (179, 63, 63)
GRIS = (93, 107, 116)
CLARO = (230, 236, 239)


def _t(s):
    """fpdf con fuentes base solo acepta latin-1: reemplaza lo que no entra."""
    s = str(s).replace("–", "-").replace("—", "-").replace("→", "->").replace("≈", "~")
    return s.encode("latin-1", "replace").decode("latin-1")


def _m(n):
    n = float(n or 0)
    return ("-" if n < 0 else "") + "S/ " + f"{abs(n):,.0f}"


def _mes(m):
    return f"{MESES[int(m[5:7]) - 1].capitalize()} {m[2:4]}"


class _PDF(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*GRIS)
        self.cell(0, 5, _t("Control Compras - Simulador de crédito. Proyección con los datos registrados; "
                           "no es asesoría financiera."), align="C")


def pdf_simulador(d):
    """`d`: dict con nombre, fecha, credito, caja_hoy, venta_dia, r (resultado
    de utils.simulate_credit), deudas, pagos, inversiones, ajuste."""
    r = d["r"]
    serie = r["serie"]
    pdf = _PDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_margins(14, 12, 14)
    pdf.add_page()
    W = pdf.w - 28

    def titulo(txt, size=11):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", size)
        pdf.set_text_color(*VERDE)
        pdf.cell(0, 7, _t(txt), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    def texto(txt, size=9, color=(0, 0, 0), bold=False):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.set_text_color(*color)
        pdf.multi_cell(0, 4.6, _t(txt), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    # ---- encabezado ----
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, _t(f"Plan financiero: {d['nombre']}"), new_x="LMARGIN", new_y="NEXT")
    texto(f"Preparado el {d['fecha']} con los datos de la app (deudas, pagos pendientes, ventas e ingresos fijos).",
          8, GRIS)

    # ---- 4 cifras ----
    pdf.ln(2)
    rojo = r["mes_rojo"]
    cifras = [
        ("Crédito", _m(d["credito"])),
        ("Se cancela de deudas", _m(r["usado"])),
        ("Ahorro en intereses", _m(r["ahorro_mensual"]) + " al mes"),
        ("Caja más baja", f"{_m(r['caja_minima'])} ({_mes(r['mes_minimo'])})" if r["mes_minimo"] else "-"),
    ]
    cw = W / 4
    y0 = pdf.get_y()
    for i, (lbl, val) in enumerate(cifras):
        x = 14 + i * cw
        pdf.set_fill_color(*CLARO)
        pdf.rect(x + 1, y0, cw - 2, 16, style="F")
        pdf.set_xy(x + 3, y0 + 2)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*GRIS)
        pdf.cell(cw - 6, 4, _t(lbl))
        pdf.set_xy(x + 3, y0 + 7)
        pdf.set_font("Helvetica", "B", 10.5)
        neg = lbl == "Caja más baja" and r["caja_minima"] < 0
        pdf.set_text_color(*(ROJO if neg else (0, 0, 0)))
        pdf.cell(cw - 6, 6, _t(val))
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y0 + 19)

    # ---- conclusión ----
    if rojo:
        idx = next(i for i, s in enumerate(serie) if s["mes"] == rojo)
        hasta = f"hasta {_mes(serie[idx - 1]['mes'])}" if idx else "ni para este mes"
        concl = (f"Con este plan, la caja y el sobrante del crédito alcanzan {hasta}. Desde {_mes(rojo)} faltaría plata "
                 f"(lo más bajo: {_m(r['caja_minima'])} en {_mes(r['mes_minimo'])}).")
        texto(concl, 9.5, ROJO, bold=True)
    else:
        texto("Con este plan, la caja alcanza en todos los meses proyectados.", 9.5, VERDE, bold=True)

    # ---- de dónde se parte ----
    titulo("1. Punto de partida")
    texto(f"Caja de hoy {_m(d['caja_hoy'])} + crédito {_m(d['credito'])} - deudas que se cancelan {_m(r['usado'])} "
          f"= se arranca con {_m(r['caja_arranque'])}. El sobrante del crédito ({_m(r['sobra_credito'])}) queda en caja "
          "y se va usando cada mes para cubrir lo que falte"
          + (" (primero cubre la caja negativa de hoy)." if d["caja_hoy"] < 0 else "."))

    # ---- uso del crédito ----
    titulo("2. Uso del crédito")
    canceladas = [(dd, d["pagos"].get(dd["id"], 0)) for dd in d["deudas"] if d["pagos"].get(dd["id"], 0)]
    quedan = [dd for dd in d["deudas"] if d["pagos"].get(dd["id"], 0) < dd["saldo"]]
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(*CLARO)
    cols = [("Deuda que se cancela", 80), ("Capital que se paga", 45), ("Interés que se deja de pagar / mes", W - 125)]
    for txt, w in cols:
        pdf.cell(w, 6, _t(txt), border=0, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8.5)
    for dd, monto in canceladas:
        ahorro = dd["cuota"] * min(monto, dd["saldo"]) / dd["saldo"]
        pdf.cell(80, 5.5, _t(dd["nombre"] + (" (parcial)" if monto < dd["saldo"] else "")))
        pdf.cell(45, 5.5, _t(_m(monto)))
        pdf.cell(W - 125, 5.5, _t(_m(ahorro)), new_x="LMARGIN", new_y="NEXT")
    if not canceladas:
        texto("No se cancela ninguna deuda en este plan.", 8.5, GRIS)
    inv = [i for i in d["inversiones"] if i.get("monto")]
    if inv:
        pdf.ln(1)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(W, 5.5, _t("Inversiones y otros usos"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        for i in inv:
            extra = f" (vuelve {_m(i['recupera'])} en {_mes(i['mes_recupera'])})" if i.get("recupera") and i.get("mes_recupera") else ""
            pdf.cell(W, 5, _t(f"- {i.get('concepto') or 'Inversión'}: {_m(i['monto'])} en {_mes(i['mes'])}{extra}"),
                     new_x="LMARGIN", new_y="NEXT")
    if quedan:
        pdf.ln(1)
        texto("Deudas informales que siguen: " + "; ".join(
            f"{dd['nombre']} {_m(dd['saldo'] - d['pagos'].get(dd['id'], 0))} "
            f"(cuota {_m(dd['cuota'] * (dd['saldo'] - d['pagos'].get(dd['id'], 0)) / dd['saldo'])})" for dd in quedan
        ) + ".", 8.5)

    # ---- proyección ----
    titulo("3. Caja mes a mes")
    heads = [("Mes", 18), ("Ventas + ing. fijos", 31), ("Proveedores", 26), ("Gastos y préstamos", 29),
             ("Deudas informales", 27), ("Inversiones", 21), ("Caja fin de mes", W - 152)]
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_fill_color(*CLARO)
    for txt, w in heads:
        pdf.cell(w, 6, _t(txt), fill=True, align="R" if txt != "Mes" else "L")
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for k, s in enumerate(serie):
        fila = [
            _mes(s["mes"]) + (" *" if k == 0 else ""),
            _m(s["ventas"] + s["fijos"]),
            _m(s["proveedores"]),
            _m(s["otros"]),
            _m(s["cuotas_deudas"]) if k else "(en gastos)",
            _m(s["inversiones"]) if s.get("inversiones") else "-",
        ]
        for (txt, w), val in zip(heads, fila):
            pdf.cell(w, 5.5, _t(val), align="R" if txt != "Mes" else "L")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*(ROJO if s["caja_fin"] < 0 else (0, 0, 0)))
        pdf.cell(heads[-1][1], 5.5, _t(_m(s["caja_fin"])), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 8)
    texto("* Este mes: solo lo que falta, e incluye los pagos atrasados.", 7, GRIS)

    # gráfico de barras de la caja a fin de mes
    pdf.ln(2)
    alto = 34
    y_top = pdf.get_y()
    vals = [s["caja_fin"] for s in serie]
    vmax = max(max(vals), 0)
    vmin = min(min(vals), 0)
    rango = (vmax - vmin) or 1
    y_cero = y_top + alto * vmax / rango
    bw = W / len(vals)
    pdf.set_draw_color(*GRIS)
    pdf.line(14, y_cero, 14 + W, y_cero)
    for i, (s, v) in enumerate(zip(serie, vals)):
        h = alto * abs(v) / rango
        x = 14 + i * bw + bw * 0.2
        pdf.set_fill_color(*(ROJO if v < 0 else VERDE))
        if h > 0:
            pdf.rect(x, y_cero - h if v >= 0 else y_cero, bw * 0.6, h, style="F")
        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(*GRIS)
        pdf.set_xy(14 + i * bw, y_top + alto + 1)
        pdf.cell(bw, 3.5, _t(_mes(s["mes"])), align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y_top + alto + 6)

    # ---- supuestos y qué cuidar ----
    titulo("4. Supuestos y qué cuidar")
    ajuste = d.get("ajuste") or {}
    puntos = [
        f"Venta promedio de {_m(d['venta_dia'])} por día (lo registrado este mes).",
        "Compras nuevas a proveedores: " + ", ".join(
            f"{_mes(s['mes'])} {_m(s['prov_nuevas'])}" for s in serie if s.get("prov_nuevas")
        ) + " (además de lo ya registrado)." if any(s.get("prov_nuevas") for s in serie) else
        "Compras a proveedores: solo lo ya registrado.",
        "Lo que se cancela deja de cobrar interés desde el mes siguiente; este mes se paga como está.",
    ]
    inv = d.get("inventario")
    if inv and inv.get("filas"):
        fin = inv["filas"][-1]
        estado = {
            "ok": "nivel sano",
            "alto": "todavía sobra stock",
            "bajo": f"ojo: en algún mes baja a {inv['dias_min']:.0f} días, riesgo de quedarse sin productos",
        }[inv["estado"]]
        puntos.append(
            f"Inventario hoy {_m(inv['inventario_hoy'])} "
            f"({inv['dias_hoy']:.0f} días). Con este plan de compras, a fin de {_mes(fin['mes'])} quedaría en "
            f"{_m(fin['inventario'])} ({fin['dias']:.0f} días): {estado}."
        )
    nuevas = [s["prov_nuevas"] for s in serie if s.get("prov_nuevas")]
    prom_hist = d.get("compras_promedio") or 0
    if nuevas and prom_hist and (sum(nuevas[1:] or nuevas) / len(nuevas[1:] or nuevas)) < prom_hist * 0.85:
        if inv and inv.get("estado") in ("ok", "alto"):
            # El inventario respalda comprar menos: no es una alarma, es algo a vigilar.
            puntos.append(
                f"El plan compra menos que el promedio de los últimos meses ({_m(prom_hist)} al mes), respaldado por "
                "el stock que sobra. Vigilar que no falten los productos que más rotan."
            )
        else:
            puntos.append(
                f"Ojo: el plan compra menos que el promedio de los últimos meses ({_m(prom_hist)} al mes). Funciona "
                "solo si hay stock de sobra; si empiezan a faltar productos que rotan, la venta baja."
            )
    if ajuste.get("compras_mes") or ajuste.get("venta_mes"):
        meta = []
        if ajuste.get("extra_inicio"):
            meta.append(f"conseguir {_m(ajuste['extra_inicio'])} ya")
        if ajuste.get("compras_mes"):
            meta.append(f"comprar {_m(ajuste['compras_mes'])} menos al mes")
        if ajuste.get("venta_mes"):
            meta.append(f"o vender {_m(ajuste['venta_dia'])} más por día")
        puntos.append("Para no entrar en rojo haría falta: " + ", ".join(meta) + ", o reprogramar algún préstamo.")
    # Tendencia: si después del punto más bajo la caja vuelve a subir, decirlo
    # (el promedio de todo el periodo puede ser negativo aunque ya se recupere).
    i_min = next((i for i, s in enumerate(serie) if s["mes"] == r["mes_minimo"]), None)
    if i_min is not None and i_min < len(serie) - 1:
        sube = (serie[-1]["caja_fin"] - serie[i_min]["caja_fin"]) / (len(serie) - 1 - i_min)
        if sube > 0:
            puntos.append(f"Desde {_mes(r['mes_minimo'])} la caja vuelve a subir, unos {_m(sube)} al mes.")
        else:
            puntos.append(f"La caja sigue bajando después de {_mes(r['mes_minimo'])}: hay que ajustar compras o cuotas.")
    elif r["cambio_mensual_promedio"] < 0:
        puntos.append(f"La caja baja en promedio {_m(-r['cambio_mensual_promedio'])} al mes y no se recupera en "
                      "los meses proyectados: hay que ajustar compras o cuotas.")
    for p in puntos:
        texto("- " + p, 8.5)

    return bytes(pdf.output())
