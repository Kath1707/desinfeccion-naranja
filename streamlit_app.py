"""
Control de Desinfección de Naranja — María Almenara
====================================================

App Streamlit para registrar el control de desinfección de naranja (MA-FR-033),
siguiendo el mismo patrón que la app de Desinfección de Huevo:
- Carpeta en Drive: "Desinfeccion naranja" (misma raíz que las demás carpetas)
- Spreadsheet mensual: "<Mes> <Año> - Naranja" (debe existir previamente)
- Cada FECHA crea/usa una hoja (tab) distinta dentro del spreadsheet mensual,
  duplicando la plantilla "Hoja 1" la primera vez que se usa esa fecha.

Columnas del registro (en este orden):
FECHA | LÍNEA | PRODUCTO | LAVADO | DESINFECCIÓN [ ] ppm | TIEMPO (min) |
ACCIÓN CORRECTIVA | EJECUTOR | SUPERVISOR CALIDAD | PRODUCTO STBX A TRABAJAR |
VºBº JEFE DE CALIDAD

Cada registro nuevo se INSERTA (nunca se sobrescribe) justo encima de la fila
donde está la imagen de la firma del Jefe de Calidad, para no pisarla nunca.
"""

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

# ──────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN — AJUSTA ESTOS VALORES FIJOS SEGÚN CORRESPONDA
# ──────────────────────────────────────────────────────────────────────────
CARPETA_NOMBRE = "Desinfeccion naranja"        # ⚠️ AJUSTA si el nombre exacto de tu carpeta en Drive es distinto
HOJA_PLANTILLA = "Hoja 1"                       # nombre de la hoja plantilla dentro de cada spreadsheet mensual
FILA_ENCABEZADO = 4                             # fila donde están los títulos de columna (A4:K4)
MARCADOR_FIRMA = "JEFE DE CALIDAD"              # texto de la leyenda que está justo DEBAJO de la imagen de firma
                                                 # (la imagen de la firma ocupa la fila inmediatamente anterior a este texto; no tocar)

# Valores fijos del registro (se muestran como recordatorio y se guardan tal cual en cada fila).
# EDITA estos valores si no corresponden exactamente a tu proceso real.
CAMPOS_FIJOS = {
    "LÍNEA": "PROCESOS",
    "PRODUCTO": "Naranja",
    "VºBº JEFE DE CALIDAD": "V. IRIARTE",
}

OPCIONES_MINUTOS = ["3 minutos", "4 minutos", "5 minutos", "> 5 minutos"]
OPCIONES_LAVADO = ["Conforme", "No conforme"]
OPCIONES_PPM = ["Mayor a 200 ppm", "Menor a 200 ppm"]
COMENTARIO_VACIO = "Sin comentarios correctivos"

# ──────────────────────────────────────────────────────────────────────────
# CONEXIÓN A GOOGLE DRIVE / SHEETS
# ──────────────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource
def conectar_gspread():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    return gspread.authorize(creds)


def obtener_carpeta_id(gc, nombre_carpeta, root_folder_id):
    """Busca una subcarpeta por nombre dentro de ROOT_FOLDER_ID."""
    # Usamos el cliente HTTP interno de gspread para consultar la API de Drive v3 directamente
    resp = gc.http_client.request(
        "get",
        "https://www.googleapis.com/drive/v3/files",
        params={
            "q": (
                f"'{root_folder_id}' in parents and "
                f"name = '{nombre_carpeta}' and "
                "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            ),
            "fields": "files(id, name)",
        },
    )
    archivos = resp.json().get("files", [])
    if not archivos:
        raise FileNotFoundError(
            f"No se encontró la carpeta '{nombre_carpeta}' dentro de la carpeta raíz. "
            "Verifica el nombre exacto y que la cuenta de servicio tenga acceso."
        )
    return archivos[0]["id"]


def obtener_spreadsheet_mensual(gc, carpeta_id, nombre_spreadsheet):
    """Busca (no crea) el spreadsheet mensual dentro de la carpeta de desinfección de naranja."""
    resp = gc.http_client.request(
        "get",
        "https://www.googleapis.com/drive/v3/files",
        params={
            "q": (
                f"'{carpeta_id}' in parents and "
                f"name = '{nombre_spreadsheet}' and "
                "mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
            ),
            "fields": "files(id, name)",
        },
    )
    archivos = resp.json().get("files", [])
    if not archivos:
        raise FileNotFoundError(
            f"No se encontró el spreadsheet '{nombre_spreadsheet}' dentro de la carpeta "
            f"'{CARPETA_NOMBRE}'. Confirma que el nombre coincide exactamente."
        )
    return gc.open_by_key(archivos[0]["id"])


def nombre_spreadsheet_mensual(fecha: date) -> str:
    meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
    }
    return f"{meses[fecha.month]} {fecha.year} - Naranja"


def obtener_o_crear_hoja_del_dia(spreadsheet, fecha: date):
    """Devuelve la worksheet (tab) correspondiente a la fecha, duplicando la plantilla si no existe."""
    nombre_tab = fecha.strftime("%Y-%m-%d")
    try:
        return spreadsheet.worksheet(nombre_tab)
    except gspread.WorksheetNotFound:
        plantilla = spreadsheet.worksheet(HOJA_PLANTILLA)
        nueva = plantilla.duplicate(new_sheet_name=nombre_tab)
        return nueva


def encontrar_fila_firma(worksheet):
    """
    Ubica la fila de la IMAGEN de firma: es la fila inmediatamente anterior a la
    leyenda "VºB JEFE DE CALIDAD" (MARCADOR_FIRMA), buscando solo debajo del
    encabezado para no confundirla con la columna del encabezado (fila 4).

    Insertar SIEMPRE una fila nueva justo en esta posición (en vez de sobrescribir
    filas vacías) empuja la imagen y todo lo que está debajo un lugar hacia abajo,
    sin tocarla ni desordenar nada — así nunca se pisa ni se borra la firma.
    """
    valores_col_a = worksheet.col_values(1)
    for idx in range(FILA_ENCABEZADO + 1, len(valores_col_a) + 1):
        valor = valores_col_a[idx - 1] if idx - 1 < len(valores_col_a) else ""
        if MARCADOR_FIRMA in (valor or ""):
            return idx - 1  # la fila de la imagen está una posición arriba de la leyenda
    raise ValueError(
        f"No se encontró la leyenda '{MARCADOR_FIRMA}' en la hoja. "
        "Verifica que la plantilla no haya cambiado de estructura."
    )


def guardar_registro(
    worksheet, fecha, lavado, ppm, minutos, accion_correctiva,
    ejecutor, supervisor_calidad, producto_stbx,
):
    fila_destino = encontrar_fila_firma(worksheet)
    nueva_fila = [
        fecha.strftime("%d/%m/%Y"),
        CAMPOS_FIJOS["LÍNEA"],
        CAMPOS_FIJOS["PRODUCTO"],
        lavado,
        ppm,
        minutos,
        accion_correctiva,
        ejecutor,
        supervisor_calidad,
        producto_stbx,
        CAMPOS_FIJOS["VºBº JEFE DE CALIDAD"],
    ]
    # Siempre se INSERTA (nunca se sobrescribe) justo encima de la fila de la firma,
    # empujando la imagen y la leyenda un lugar hacia abajo en cada registro.
    worksheet.insert_row(nueva_fila, index=fila_destino, value_input_option="USER_ENTERED")


# ──────────────────────────────────────────────────────────────────────────
# INTERFAZ STREAMLIT
# ──────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Control Desinfección Naranja", page_icon="🍊", layout="centered")

st.title("🍊 Control de Desinfección de Naranja")
st.caption("MA-FR-033 · Control de procesos · María Almenara")

with st.expander("ℹ️ Recordatorio del proceso", expanded=True):
    st.markdown(
        f"""
        - **Línea:** {CAMPOS_FIJOS['LÍNEA']}
        - **Producto:** {CAMPOS_FIJOS['PRODUCTO']}
        - **Solución:** hipoclorito de sodio
        - **Concentración mínima:** > 200 ppm — **tiempo mínimo:** 5 min
        - Si la concentración es inferior al LC: preparar nuevamente la solución y desinfectar de nuevo.
        - Si el tiempo fue inferior al LC: enjuagar y desinfectar nuevamente.
        """
    )

st.divider()
st.subheader("Nuevo registro")

if "form_key" not in st.session_state:
    st.session_state.form_key = 0
if "guardado_ok" not in st.session_state:
    st.session_state.guardado_ok = False

k = st.session_state.form_key  # sufijo de las keys, cambia al pulsar "Nuevo registro"

fecha_seleccionada = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key=f"fecha_{k}")
lavado = st.selectbox("Lavado", options=OPCIONES_LAVADO, key=f"lavado_{k}")
ppm = st.selectbox("Desinfección [ ] ppm", options=OPCIONES_PPM, key=f"ppm_{k}")
minutos = st.selectbox("Tiempo de desinfección (min)", options=OPCIONES_MINUTOS, key=f"minutos_{k}")

dejar_sin_comentario = st.checkbox("Dejar acción correctiva vacía", value=True, key=f"sin_comentario_{k}")
if dejar_sin_comentario:
    accion_correctiva = COMENTARIO_VACIO
    st.caption(f"Se guardará como: “{COMENTARIO_VACIO}”")
else:
    accion_correctiva = st.text_area(
        "Comentario de acción correctiva", placeholder="Escribe el comentario...", key=f"accion_{k}"
    )

ejecutor = st.text_input("Ejecutor (Supervisor de Calidad)", placeholder="Nombre completo", key=f"ejecutor_{k}")
supervisor_calidad = st.text_input(
    "Supervisor Calidad que registró", placeholder="Nombre completo", key=f"supervisor_calidad_{k}"
)
producto_stbx = st.text_input(
    "Producto STBX a trabajar", placeholder="Producto para el que se usarán estas naranjas", key=f"producto_stbx_{k}"
)

st.divider()

col_guardar, col_nuevo = st.columns(2)

with col_guardar:
    if st.button("💾 Guardar registro", type="primary", use_container_width=True):
        if not ejecutor.strip():
            st.error("Por favor ingresa el nombre del ejecutor antes de guardar.")
        elif not supervisor_calidad.strip():
            st.error("Por favor ingresa el nombre del Supervisor de Calidad antes de guardar.")
        elif not producto_stbx.strip():
            st.error("Por favor ingresa el producto STBX a trabajar antes de guardar.")
        elif not dejar_sin_comentario and not accion_correctiva.strip():
            st.error("Escribe un comentario de acción correctiva o marca la casilla para dejarlo vacío.")
        else:
            accion_final = accion_correctiva if dejar_sin_comentario else accion_correctiva.strip()
            try:
                with st.spinner("Guardando en Google Sheets..."):
                    gc = conectar_gspread()
                    root_folder_id = st.secrets["ROOT_FOLDER_ID"]
                    carpeta_id = obtener_carpeta_id(gc, CARPETA_NOMBRE, root_folder_id)
                    nombre_ss = nombre_spreadsheet_mensual(fecha_seleccionada)
                    spreadsheet = obtener_spreadsheet_mensual(gc, carpeta_id, nombre_ss)
                    worksheet = obtener_o_crear_hoja_del_dia(spreadsheet, fecha_seleccionada)
                    guardar_registro(
                        worksheet, fecha_seleccionada, lavado, ppm, minutos, accion_final,
                        ejecutor.strip(), supervisor_calidad.strip(), producto_stbx.strip(),
                    )
                st.session_state.guardado_ok = True
                st.success(
                    f"✅ Registro guardado correctamente en '{nombre_ss}' → "
                    f"hoja '{fecha_seleccionada.strftime('%Y-%m-%d')}'."
                )
                st.balloons()
            except FileNotFoundError as e:
                st.session_state.guardado_ok = False
                st.error(str(e))
            except Exception as e:
                st.session_state.guardado_ok = False
                st.error(f"Ocurrió un error al guardar: {e}")

with col_nuevo:
    if st.button("➕ Nuevo registro", use_container_width=True):
        st.session_state.form_key += 1
        st.session_state.guardado_ok = False
        st.rerun()
