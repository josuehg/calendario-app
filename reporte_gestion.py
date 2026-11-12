"""Informe de gestión (uso interno): la proyección hasta salir de las deudas
caras, con dos escenarios (seguir igual / con mejoras), metas mes a mes, plan
de acción y señales de alerta. Reusa el formato del PDF del simulador."""
from reporte_pdf import CLARO, GRIS, ROJO, VERDE, _PDF, _agrupar, _m, _mes, _t


def pdf_gestion(d):
    """`d`: nombre, fecha, base y mejoras (utils.long_projection), params
    (crec_anual, margen_pts, ahorro_mes, liquidacion_mes), renov
    (utils.renewal_schedule o None), inv_hoy, inv_lento, inv_balanceo,
    compras_promedio, venta_dia."""
    base, mej, p = d["base"], d["mejoras"], d["params"]
    rv = d.get("renov") or {}
    pdf = _PDF(format="A4")
    pdf.set_auto_page_break(True, margin=15)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    W = pdf.w - 24

    def titulo(txt):
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*VERDE)
        pdf.cell(0, 7, _t(txt), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    def texto(txt, size=8.5, color=(0, 0, 0), bold=False):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.set_text_color(*color)
        pdf.multi_cell(0, 4.4, _t(txt), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    # ---- encabezado ----
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _t(f"Informe de gestión: {d['nombre']}"), new_x="LMARGIN", new_y="NEXT")
    texto(f"Uso interno de la gerencia. Proyección hasta salir de las deudas caras, preparada el {d['fecha']} "
          "con los datos de la app.", 8, GRIS)

    libre = rv.get("libre_en")
    cifras = [
        ("Libre de deudas caras", _mes(libre) if libre else "Falta cubrir"),
        ("Caja más baja si seguimos igual", f"{_m(base['caja_minima'])} ({_mes(base['mes_minimo'])})"),
        ("Caja más baja con mejoras", f"{_m(mej['caja_minima'])} ({_mes(mej['mes_minimo'])})"),
        ("Stock vuelve a lo normal", _mes(base["stock_normal_en"]) if base.get("stock_normal_en") else "-"),
    ]
    cw = W / 4
    y0 = pdf.get_y() + 1
    for i, (lbl, val) in enumerate(cifras):
        x = 12 + i * cw
        pdf.set_fill_color(*CLARO)
        pdf.rect(x + 1, y0, cw - 2, 15, style="F")
        pdf.set_xy(x + 3, y0 + 2)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*GRIS)
        pdf.cell(cw - 6, 4, _t(lbl))
        pdf.set_xy(x + 3, y0 + 7)
        pdf.set_font("Helvetica", "B", 9.5)
        neg = ("más baja" in lbl and val.startswith("-"))
        pdf.set_text_color(*(ROJO if neg else (0, 0, 0)))
        pdf.cell(cw - 6, 6, _t(val))
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(y0 + 18)

    # ---- qué dice ----
    titulo("1. Qué dice la proyección")
    puntos = []
    if base["mes_rojo"]:
        puntos.append(f"Si seguimos igual, la caja entra en rojo en {_mes(base['mes_rojo'])} "
                      f"(lo más bajo: {_m(base['caja_minima'])} en {_mes(base['mes_minimo'])}).")
    else:
        puntos.append(f"Si seguimos igual, la caja no entra en rojo; lo más bajo es {_m(base['caja_minima'])} "
                      f"en {_mes(base['mes_minimo'])}.")
    if base.get("stock_normal_en"):
        puntos.append(f"El momento delicado es {_mes(base['stock_normal_en'])}: el stock que sobra se acaba y las compras "
                      "tienen que volver a reponer todo lo que se vende. Hay que llegar ahí con las deudas caras ya bajando.")
    if mej["caja_minima"] > base["caja_minima"]:
        puntos.append(f"Con las mejoras de la sección 4, lo más bajo sube a {_m(mej['caja_minima'])} y al final del periodo "
                      f"la caja queda en {_m(mej['serie'][-1]['caja'])} (vs {_m(base['serie'][-1]['caja'])} si seguimos igual).")
    if libre:
        puntos.append(f"Las renovaciones cancelan a todas las prestamistas hasta {_mes(libre)}; desde ahí se dejan de pagar "
                      f"{_m(rv['filas'][-1]['interes_liberado'])} al mes de intereses.")
    for x in puntos:
        texto("- " + x)

    # ---- caja mes a mes ----
    titulo("2. Caja mes a mes: seguir igual vs con mejoras")
    meses_renov = {f["mes"]: f for f in rv.get("filas", [])}
    heads = [("Mes", 15), ("Venta/día", 18), ("Compras pagadas", 24), ("Gastos y bancos", 24),
             ("Prestamistas", 21), ("Renovación", 34), ("Caja igual", 22), ("Caja mejoras", W - 158)]
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_fill_color(*CLARO)
    for h, w in heads:
        pdf.cell(w, 5.5, _t(h), fill=True, align="L" if h in ("Mes", "Renovación") else "R")
    pdf.ln()
    for s, sm in zip(base["serie"], mej["serie"]):
        f = meses_renov.get(s["mes"])
        renov = _agrupar(f["canceladas"]) if f and f["canceladas"] else ("se junta" if f else "")
        vals = [_mes(s["mes"]), _m(s["venta_dia"]), _m(s["compras_pagadas"]), _m(s["otros"]),
                _m(s["intereses"]) if s["intereses"] else "-", renov[:26]]
        pdf.set_font("Helvetica", "", 7)
        for (h, w), v in zip(heads[:6], vals):
            pdf.cell(w, 4.6, _t(v), align="L" if h in ("Mes", "Renovación") else "R")
        for c, w in ((s["caja"], heads[6][1]), (sm["caja"], heads[7][1])):
            pdf.set_font("Helvetica", "B", 7)
            pdf.set_text_color(*(ROJO if c < 0 else (0, 0, 0)))
            pdf.cell(w, 4.6, _t(_m(c)), align="R")
            pdf.set_text_color(0, 0, 0)
        pdf.ln()
    texto("Prestamistas = intereses de las deudas caras que siguen; bajan con cada renovación. "
          "Gastos y bancos = gastos fijos y cuotas bancarias (los préstamos que terminan dejan de sumar).", 7, GRIS)

    # ---- metas ----
    titulo("3. Metas para revisar cada mes")
    heads = [("Mes", 16), ("Compras máximas", 30), ("Venta mínima/día", 30), ("Liquidar stock lento", 32),
             ("Días de inventario", 30), ("Renovación esperada", W - 138)]
    pdf.set_font("Helvetica", "B", 7)
    for h, w in heads:
        pdf.cell(w, 5.5, _t(h), fill=True, align="L" if h in ("Mes", "Renovación esperada") else "R")
    pdf.ln()
    pdf.set_font("Helvetica", "", 7)
    for s, sm in zip(base["serie"], mej["serie"]):
        liq = sm.get("liquidado", 0)
        f = meses_renov.get(s["mes"])
        vals = [_mes(s["mes"]), _m(sm["compra_mes"]), _m(sm["venta_dia"]), _m(liq) if liq else "-",
                f"{sm['dias_inv']:.0f}", _m(f["total"]) if f else ""]
        for (h, w), v in zip(heads, vals):
            pdf.cell(w, 4.6, _t(v), align="L" if h in ("Mes", "Renovación esperada") else "R")
        pdf.ln()
    texto("Compras máximas: lo que se puede comprar en el mes sin pasarse del plan (bajo mientras sobra stock; "
          "luego reponer lo vendido). Días de inventario: sano entre 60 y 120.", 7, GRIS)

    # ---- plan de acción ----
    titulo("4. Plan de acción")
    acciones = []
    if d.get("inv_lento"):
        acciones.append(
            f"Liquidar lo que no rota (responsable: compras/almacén). Hay {_m(d['inv_lento'])} de stock lento. Meta: "
            f"{_m(p.get('liquidacion_mes', 0))} al mes. Cómo: ofertas y packs en lo que no se vendió, devolución o canje "
            "con laboratorios antes del vencimiento (primero lo que vence antes) y no recomprar lo que no se vendió en 60 días.")
    if d.get("inv_balanceo"):
        acciones.append(
            f"Balanceo entre locales (responsable: almacén). {_m(d['inv_balanceo'])} se pueden mover sin comprar: primero "
            "desde los almacenes, luego de las tiendas con sobrestock hacia Zolezzi A y B. Lo que se mueve no se compra.")
    acciones.append(
        f"Vender más (responsable: gerencia y jefes de local). Meta: +{p.get('crec_anual', 0) * 100:.0f}% en el año "
        f"(de {_m(d['venta_dia'])} a {_m(mej['serie'][-1]['venta_dia'])} por día). Metas por local, venta cruzada, "
        "venta fraccionada y seguimiento a pacientes crónicos (recompra).")
    if p.get("margen_pts"):
        ahorro_margen = d["venta_dia"] * 30 * p["margen_pts"] / 100
        acciones.append(
            f"Comprar mejor (responsable: compras). +{p['margen_pts']:.0f} puntos de margen = ~{_m(ahorro_margen)} al mes. "
            "Descuentos por volumen o pronto pago, comprar por rotación con Odoo y evitar compras de urgencia.")
    if p.get("ahorro_mes"):
        acciones.append(
            f"Reprogramar y gastos (responsable: gerencia). {_m(p['ahorro_mes'])} al mes desde el tercer mes: reprogramar "
            "algún préstamo bancario a más plazo y revisar alquileres, servicios y horarios.")
    if rv.get("filas"):
        acciones.append(
            "Renovaciones (responsable: gerencia). Cada 3 meses, según la tabla. Para que el banco apruebe: cuotas al día, "
            "letras sin protesto, ventas depositadas en la cuenta y ninguna deuda nueva entre renovaciones. Lo que se guarda "
            "entre renovaciones es solo para la siguiente prestamista.")
    for i, a in enumerate(acciones, 1):
        texto(f"{i}. {a}")

    # ---- alertas ----
    titulo("5. Señales de alerta (revisión mensual)")
    alertas = [
        "Caja real más de S/ 15,000 por debajo de la proyectada: revisar qué se desvió antes de comprometer más.",
        "Compras del mes por encima de la meta: frenar pedidos y priorizar balanceo.",
        "Menos de 60 días de inventario o quiebres en productos que más rotan: se está comprando muy poco.",
        "Venta por día debajo de la meta dos semanas seguidas: activar promociones y revisar locales.",
        "Una renovación negada: no cancelar esa prestamista todavía, seguir con la siguiente renovación y nunca tomar "
        "deuda nueva cara para cubrir el hueco.",
        "Letras por vencer sin fondos: negociar con el proveedor antes del vencimiento (nunca dejarlas protestar).",
    ]
    for a in alertas:
        texto("- " + a)

    titulo("6. Supuestos")
    texto(f"- Venta de partida: {_m(d['venta_dia'])} por día. Compras promedio de los últimos meses: "
          f"{_m(d.get('compras_promedio') or 0)}.")
    texto("- Mientras el inventario esté sobre 90 días se compra según el plan; después, se repone lo que se vende. "
          "Lo comprado se paga ~2 meses después.")
    texto("- Los gastos fijos de los meses sin cuotas generadas salen de sus plantillas (los préstamos que terminan dejan "
          "de sumar). Las renovaciones dependen de la evaluación del banco.")
    texto(f"- Con mejoras: venta +{p.get('crec_anual', 0) * 100:.0f}% al año, margen +{p.get('margen_pts', 0):.0f} puntos, "
          f"{_m(p.get('ahorro_mes', 0))} al mes de reprogramación/gastos y {_m(p.get('liquidacion_mes', 0))} al mes de "
          "stock lento liquidado o canjeado (se recupera ~70% de su costo).")
    return bytes(pdf.output())
