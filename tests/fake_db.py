"""Base de datos en memoria que imita la superficie pública de db.py.

Se instala en sys.modules['db'] (ver conftest.py) para que las páginas de
Streamlit y las utilidades corran en los tests sin Supabase.
"""
import itertools
from datetime import date


class FakeDB:
    def __init__(self):
        self._branches = [
            {"id": i + 1, "name": n, "pin": None}
            for i, n in enumerate(["Sucursal 1", "Sucursal 2", "Sucursal 3"])
        ]
        self.vendors = []
        self.invoices = []
        self.canjes = []
        self.canje_facturas = []
        self.letras = []
        self.settings = {"track_contado": True}
        self.expense_categories = [
            {"id": 1, "name": "Alquiler", "sort_order": 1},
            {"id": 2, "name": "Servicios", "sort_order": 2},
            {"id": 3, "name": "Planilla", "sort_order": 3},
        ]
        self.fixed_expenses = []
        self.expenses = []
        self._seq = itertools.count(1)

    def _nid(self, prefix):
        return f"{prefix}{next(self._seq)}"

    # ---- sucursales ----
    def get_branches(self):
        return [b["name"] for b in self._branches]

    def get_branches_full(self):
        return [dict(b) for b in self._branches]

    def save_branches(self, rows):
        self._branches = [
            {"id": i + 1, "name": r["name"].strip(), "pin": (r.get("pin") or "").strip() or None}
            for i, r in enumerate(rows) if r["name"].strip()
        ]

    def find_branch_by_pin(self, pin):
        pin = (pin or "").strip()
        return next((b["name"] for b in self._branches if b.get("pin") and b["pin"] == pin), None)

    # ---- proveedores ----
    def get_vendors(self):
        return [dict(v) for v in sorted(self.vendors, key=lambda v: v["name"].lower())]

    def get_vendor_by_name(self, name):
        return next((dict(v) for v in self.vendors if v["name"] == name), None)

    def get_vendor_by_ruc(self, ruc):
        ruc = (ruc or "").strip()
        if not ruc:
            return None
        return next((dict(v) for v in self.vendors if (v.get("ruc") or "") == ruc), None)

    def create_vendor(self, data):
        low = data["name"].strip().lower()
        if any(v["name"].strip().lower() == low for v in self.vendors):
            raise ValueError("nombre duplicado")
        if data.get("ruc") and any((v.get("ruc") or "") == data["ruc"] for v in self.vendors):
            raise ValueError("ruc duplicado")
        row = {"id": next(self._seq), **data}
        self.vendors.append(row)
        return row

    def update_vendor(self, vid, data):
        for v in self.vendors:
            if v["id"] == vid:
                v.update(data)

    def delete_vendor(self, vid):
        self.vendors[:] = [v for v in self.vendors if v["id"] != vid]

    # ---- ajustes ----
    def get_settings(self):
        return dict(self.settings)

    def save_settings(self, data):
        self.settings.update(data)

    # ---- facturas ----
    def list_invoices(self):
        return [dict(i) for i in sorted(self.invoices, key=lambda i: i.get("issue_date", ""), reverse=True)]

    def create_invoice(self, data):
        row = {"id": self._nid("inv"), **data}
        self.invoices.append(row)
        return row

    def update_invoice(self, iid, data):
        for i in self.invoices:
            if i["id"] == iid:
                i.update(data)

    def delete_invoice(self, iid):
        self.invoices[:] = [i for i in self.invoices if i["id"] != iid]

    def mark_invoice_paid(self, iid, paid_at):
        self.update_invoice(iid, {"status": "pagada", "paid_at": paid_at})

    # ---- canjes / letras ----
    def list_canjes(self):
        return [dict(c) for c in self.canjes]

    def list_canje_facturas(self):
        return [dict(c) for c in self.canje_facturas]

    def list_letras(self):
        return [dict(l) for l in sorted(self.letras, key=lambda l: l["fecha_vencimiento"])]

    def create_canje(self, invoice_ids, letras, notes=""):
        cid = self._nid("canje")
        self.canjes.append({"id": cid, "notes": notes})
        for iid in invoice_ids:
            self.canje_facturas.append({"canje_id": cid, "invoice_id": iid})
            self.update_invoice(iid, {"status": "canjeada"})
        for l in letras:
            self.letras.append({
                "id": self._nid("letra"), "canje_id": cid, "numero": l.get("numero", ""),
                "monto": l["monto"], "fecha_vencimiento": l["fecha_vencimiento"], "estado": "pendiente",
            })
        return cid

    def mark_letra_paid(self, lid, fecha_pago):
        for l in self.letras:
            if l["id"] == lid:
                l.update({"estado": "pagada", "fecha_pago": fecha_pago})

    # ---- categorías de gasto ----
    def list_expense_categories(self):
        return [dict(c) for c in sorted(self.expense_categories, key=lambda c: (c["sort_order"], c["name"]))]

    def add_expense_category(self, name):
        self.expense_categories.append({"id": next(self._seq), "name": name.strip(), "sort_order": 50})

    def rename_expense_category(self, cid, new_name):
        cat = next((c for c in self.expense_categories if c["id"] == cid), None)
        if not cat:
            return
        prev, new_name = cat["name"], new_name.strip()
        cat["name"] = new_name
        for f in self.fixed_expenses:
            if f["category"] == prev:
                f["category"] = new_name
        for e in self.expenses:
            if e["category"] == prev:
                e["category"] = new_name

    def delete_expense_category(self, cid):
        self.expense_categories[:] = [c for c in self.expense_categories if c["id"] != cid]

    # ---- gastos fijos ----
    def list_fixed_expenses(self, active_only=False):
        rows = [dict(f) for f in sorted(self.fixed_expenses, key=lambda f: f["name"].lower())]
        return [f for f in rows if f["active"]] if active_only else rows

    def create_fixed_expense(self, data):
        row = {
            "id": max([f["id"] for f in self.fixed_expenses], default=0) + 1,
            "active": True, "start_month": None, "end_month": None, "notes": None,
            **data,
        }
        self.fixed_expenses.append(row)
        return row

    def update_fixed_expense(self, fid, data):
        for f in self.fixed_expenses:
            if f["id"] == fid:
                f.update(data)

    def delete_fixed_expense(self, fid):
        self.fixed_expenses[:] = [f for f in self.fixed_expenses if f["id"] != fid]

    # ---- gastos concretos ----
    def list_expenses(self):
        return [dict(e) for e in sorted(self.expenses, key=lambda e: e["due_date"])]

    def create_expense(self, data):
        row = {"id": self._nid("exp"), "fixed_expense_id": None, "period": None, "notes": None, **data}
        self.expenses.append(row)
        return row

    def update_expense(self, eid, data):
        for e in self.expenses:
            if e["id"] == eid:
                e.update(data)

    def delete_expense(self, eid):
        self.expenses[:] = [e for e in self.expenses if e["id"] != eid]

    def set_expense_status(self, eid, status, paid_at=None):
        self.update_expense(eid, {"status": status, "paid_at": paid_at})

    def ensure_expense_instances(self, months_ahead=3):
        import utils

        active = self.list_fixed_expenses(active_only=True)
        rows = utils.fixed_expense_rows_to_create(active, self.list_expenses(), date.today(), months_ahead)
        for r in rows:
            self.create_expense(r)
