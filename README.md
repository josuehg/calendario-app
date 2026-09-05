# Calendario Maestro de Pagos

Sistema de cuentas por pagar para una cadena de 6 sucursales: registro de
facturas, canje de facturas a letras (varias facturas pueden agruparse en
una o varias letras), calendario mensual de vencimientos y presupuesto
semanal a 90 días.

## 1. Crear la base de datos (Supabase, gratis)

1. Entra a [supabase.com](https://supabase.com) y crea una cuenta gratuita.
2. Crea un proyecto nuevo (elige una contraseña de base de datos, guárdala).
3. Ve a **SQL Editor > New query**, pega el contenido completo de
   `schema.sql` (en esta misma carpeta) y presiona **Run**. Esto crea las
   tablas de facturas, canjes y letras.
4. Ve a **Project Settings > API**. Copia:
   - **Project URL** → será tu `SUPABASE_URL`
   - **service_role key** (no la "anon" key) → será tu `SUPABASE_SERVICE_KEY`

   La `service_role` key tiene permisos completos y nunca debe exponerse en
   una página web pública — aquí es segura porque Streamlit la usa solo del
   lado del servidor, nunca llega al navegador.

## 2. Configurar los secretos localmente (opcional, para probar en tu compu)

Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y
completa `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` y una `APP_PASSWORD` (la
clave que usarán tú y las 6 sucursales para entrar a la app).

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 3. Desplegar en Streamlit Community Cloud (gratis)

1. Sube esta carpeta completa a un repositorio de GitHub (puede ser
   privado).
2. Entra a [share.streamlit.io](https://share.streamlit.io), conecta tu
   cuenta de GitHub y elige "New app".
3. Selecciona el repositorio, la rama, y como archivo principal `app.py`.
4. Antes de desplegar (o después, en **Settings > Secrets**), pega el
   mismo contenido que usaste en `secrets.toml`:

   ```toml
   SUPABASE_URL = "https://tu-proyecto.supabase.co"
   SUPABASE_SERVICE_KEY = "tu-service-role-key"
   APP_PASSWORD = "la-clave-que-elijas"
   ```

5. Deploy. En unos minutos tendrás una URL pública (algo como
   `tuapp.streamlit.app`) que puedes compartir con las 6 sucursales.

## 4. Uso diario

- **Nueva Factura**: cada sucursal registra sus facturas (contado o
  crédito, con plazo de 30/45/60/75/90 días). El vencimiento se calcula
  solo.
- **Consolidado**: tú ves todo lo registrado, filtras por sucursal,
  proveedor o estado, marcas pagos directos, y seleccionas facturas a
  crédito para canjear.
- **Canjear a Letras**: agrupa una o varias facturas seleccionadas en una o
  varias letras (no necesitan coincidir 1 a 1) con su propio número y
  fecha de vencimiento.
- **Calendario**: vista mensual con el monto total que vence cada día.
- **Presupuesto**: proyección semana a semana a 90 días, para ver de
  inmediato el impacto de una factura nueva en tu flujo de caja futuro.
- **Configuración**: renombra tus 6 sucursales.

## Notas

- Los nombres de sucursal se guardan como texto en cada factura al
  momento de registrarla; si renombras una sucursal después, las facturas
  ya registradas conservan el nombre anterior.
- La clave de acceso (`APP_PASSWORD`) es una protección básica para que no
  cualquiera con el enlace pueda editar tus datos — no reemplaza un login
  individual por sucursal.
