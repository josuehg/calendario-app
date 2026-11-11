"""Formulario de ventas del día por sucursal, compartido por Ingresos y el
Calendario (que lo abre en un diálogo)."""
import streamlit as st


def formulario_ventas(branches, incomes, fecha_iso, prefijo, msg_key, al_guardar=None):
    """Un campo por sucursal para la fecha dada. Lo ya registrado ese día sale
    precargado: cambiar el monto corrige ese registro (no agrega otro, que
    sumaría doble en el saldo de caja). Al guardar deja el mensaje en
    session_state[msg_key], llama a `al_guardar` (si hay) y hace rerun."""
    # Importados aquí y no arriba: así siempre se usa el `db` vigente (los
    # tests lo reemplazan por uno en memoria en cada caso).
    import db
    import utils

    registros_del_dia = {}
    for r in incomes:
        if r["date"] == fecha_iso:
            registros_del_dia.setdefault(r["branch"], []).append(r)

    with st.form(f"{prefijo}_form", enter_to_submit=False, border=False):
        st.caption(
            "Deja vacía la sucursal que aún no tengas. Si el local cerró ese día, pon 0. "
            "Lo ya registrado sale cargado: cámbialo para corregirlo."
        )
        montos = {}
        columnas = st.columns(3)
        for i, branch in enumerate(branches):
            col = columnas[i % 3]
            previos = registros_del_dia.get(branch, [])
            if len(previos) > 1:
                # Varios registros el mismo día (p. ej. "sumar" desde el bot): se
                # corrigen uno por uno en el Historial de Ingresos.
                col.markdown(f"**{branch}**")
                total_previo = utils.dsum(float(r["amount"]) for r in previos)
                col.caption(f"✅ {len(previos)} registros: {utils.money(total_previo)} · corrígelos en el Historial de Ingresos")
                continue
            previo = previos[0] if previos else None
            # La key lleva la fecha y el registro: al cambiar de día (o si el
            # registro cambia) el campo se vuelve a cargar con lo guardado.
            montos[branch] = col.number_input(
                f"{branch} ✅" if previo else branch,
                min_value=0.0, step=0.01, format="%.2f",
                value=float(previo["amount"]) if previo else None,
                placeholder="Sin registrar",
                key=f"{prefijo}_monto_{fecha_iso}_{branch}_{previo['id'] if previo else 'nuevo'}_{previo['amount'] if previo else ''}",
            )
        notas = st.text_input("Notas (opcional, se guardan en los nuevos)", key=f"{prefijo}_notas")
        guardar = st.form_submit_button("Guardar ingresos", type="primary")

    if not guardar:
        return
    # None = sin llenar. 0 es válido (local cerrado ese día).
    nuevos, corregidos = {}, {}
    for branch, monto in montos.items():
        if monto is None:
            continue
        previos = registros_del_dia.get(branch, [])
        if not previos:
            nuevos[branch] = monto
        elif utils.round2(monto) != utils.round2(float(previos[0]["amount"])):
            corregidos[branch] = (previos[0]["id"], monto)
    if not nuevos and not corregidos:
        st.warning("No hay montos nuevos ni cambios para guardar.")
        return
    for branch, monto in nuevos.items():
        db.create_income({
            "branch": branch,
            "date": fecha_iso,
            "amount": utils.round2(monto),
            "notes": notas.strip() or None,
            "registered_by": utils.current_actor(),
            "source": "app",
        })
    for branch, (income_id, monto) in corregidos.items():
        db.update_income(income_id, {"amount": utils.round2(monto)})
    partes = []
    if nuevos:
        partes.append(f"{len(nuevos)} nuevo(s) · {utils.money(utils.dsum(nuevos.values()))}")
    if corregidos:
        partes.append(f"{len(corregidos)} corregido(s)")
    st.session_state[msg_key] = f"Guardado: {' · '.join(partes)} · {utils.fmt_short(fecha_iso)}."
    if al_guardar:
        al_guardar()
    st.rerun()
