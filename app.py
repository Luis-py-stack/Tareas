from datetime import date, datetime
import streamlit as st
import pandas as pd
from supabase import create_client, Client

st.set_page_config(
    page_title="Visor y Gestor Supabase",
    page_icon="⚡",
    layout="wide"
)

st.title("Visor y Gestor de Datos")

def get_secret(key: str, default: str) -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

# --- CREDENCIALES SUPABASE CRUD ---
default_url = get_secret("SUPABASE_URL", "")
default_key = get_secret("SUPABASE_KEY", "")
default_table = get_secret("TABLE_NAME", "Luis_Pereira")

st.sidebar.header("🔑 Configuración de Conexión")
supabase_url = st.sidebar.text_input("SUPABASE_URL", value=default_url, placeholder="https://xyz.supabase.co")
supabase_key = st.sidebar.text_input("SUPABASE_KEY", value=default_key, type="password", placeholder="sb_secret_...")
table_name = st.sidebar.text_input("TABLE_NAME", value=default_table)

if not supabase_url or not supabase_key or not table_name:
    st.info("👈 Ingresa las credenciales de Supabase en la barra lateral o configúralas en secrets.toml para comenzar.")
    st.stop()

@st.cache_resource(show_spinner=False)
def init_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)

try:
    supabase: Client = init_supabase_client(supabase_url, supabase_key)
except Exception as e:
    st.error(f"Error crítico al inicializar el cliente de Supabase: {e}")
    st.stop()

def clean_input(val):
    if isinstance(val, str):
        val_s = val.strip()
        return val_s if val_s != "" else None
    return val

def format_date_for_db(val):
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, str):
        val_s = val.strip()
        if not val_s:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(val_s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return val_s
    return val

col_form, col_view = st.columns([1, 5.001], gap="large")

with col_form:
    soporta_tabs_dinamicos = True
    try:
        tab_insert, tab_update = st.tabs(
            ["➕ Insertar", "✏️ Actualizar"],
            key="active_tab",
            on_change="rerun"
        )
        active_tab_val = st.session_state.get("active_tab")
        modo_edicion = (active_tab_val == "✏️ Actualizar") or getattr(tab_update, "open", False)
    except TypeError:
        tab_insert, tab_update = st.tabs(["➕ Insertar", "✏️ Actualizar"])
        soporta_tabs_dinamicos = False
        modo_edicion = False

    with tab_insert:
        st.subheader("Nuevo Registro")
        with st.form("insert_form", clear_on_submit=True):
            f_col1, f_col2 = st.columns(2)

            with f_col1:
                input_tarea = st.text_input("Tarea")
                input_fecha_limite = st.date_input("Fecha_Limit", value=None, format="YYYY-MM-DD")

            with f_col2:
                input_descripcion = st.text_input("Descripcion")
                input_avance = st.text_input("Avance")

            st.markdown("<br>", unsafe_allow_html=True)
            btn_submit = st.form_submit_button("Guardar en Supabase", type="primary", use_container_width=True)

            if btn_submit:
                if not clean_input(input_tarea):
                    st.error("El campo Tarea es obligatorio para crear el registro.")
                else:
                    data_to_insert = {
                        "Tarea": clean_input(input_tarea),
                        "Descripcion": clean_input(input_descripcion),
                        "Fecha_Limite": format_date_for_db(input_fecha_limite),
                        "Avance": clean_input(input_avance)
                    }
                    try:
                        supabase.table(table_name).insert(data_to_insert).execute()
                        st.success(f"¡Registro insertado con éxito! (Tarea: {input_tarea})")
                        st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1
                    except Exception as e:
                        st.error(f"Error al insertar en la base de datos: {e}")

    with tab_update:
        st.subheader("Modificar Registro")

        if not soporta_tabs_dinamicos:
            modo_edicion = st.toggle("🔓 Desbloquear tabla para editar", value=False, key="toggle_unlock_table")

        if "update_success_msg" in st.session_state:
            st.success(st.session_state.pop("update_success_msg"))

        if modo_edicion:
            st.caption("🟢 **Modo edición activo:** Edita o vacía cualquier celda en la tabla y presiona el botón para sincronizar.")
        else:
            st.caption("🔒 La tabla está protegida. Entra en esta pestaña para habilitar su edición.")

        editor_version = st.session_state.get("editor_version", 0)
        editor_key = f"main_data_editor_{editor_version}"
        editor_state = st.session_state.get(editor_key, {})
        edited_rows = editor_state.get("edited_rows", {}) if isinstance(editor_state, dict) else getattr(editor_state, "edited_rows", {})

        num_cambios = len(edited_rows)
        if num_cambios > 0 and modo_edicion:
            st.info(f"✏️ Hay cambios listos en **{num_cambios}** fila(s).")
        else:
            st.caption("*(No hay cambios pendientes de guardar)*")

        st.markdown("<br>", unsafe_allow_html=True)
        btn_update = st.button("Actualizar en Supabase", type="primary", use_container_width=True)

        if btn_update:
            if not modo_edicion:
                st.warning("Debes encontrarte en la pestaña 'Actualizar' para aplicar los cambios.")
            elif not edited_rows:
                st.warning("No has modificado ninguna celda en la tabla.")
            else:
                cached_data = st.session_state.get("cached_table_data")
                if not cached_data:
                    try:
                        res = supabase.table(table_name).select("*").order("id", desc=False).execute()
                        cached_data = res.data or []
                    except Exception:
                        cached_data = []

                actualizados = 0
                errores = []

                for r_idx, cambios in edited_rows.items():
                    idx = int(r_idx)
                    if 0 <= idx < len(cached_data):
                        id_reg = cached_data[idx].get("id")
                        if id_reg is not None:
                            update_payload = {}
                            for col_name, val in cambios.items():
                                if col_name in ("id", "created_at"):
                                    continue
                                if col_name == "Fecha_Limite":
                                    update_payload["Fecha_Limite"] = format_date_for_db(val)
                                else:
                                    update_payload[col_name] = clean_input(val)

                            if update_payload:
                                try:
                                    supabase.table(table_name).update(update_payload).eq("id", id_reg).execute()
                                    actualizados += 1
                                except Exception as e:
                                    errores.append(f"ID {id_reg}: {e}")

                if actualizados > 0 and not errores:
                    st.session_state["update_success_msg"] = f"¡Se sincronizaron {actualizados} registro(s) en Supabase!"
                    st.session_state["editor_version"] = editor_version + 1
                    if hasattr(st, "rerun"):
                        st.rerun()
                    else:
                        st.experimental_rerun()
                elif actualizados > 0 and errores:
                    st.session_state["editor_version"] = editor_version + 1
                    st.warning(f"Se actualizaron {actualizados} registro(s), pero ocurrieron fallos:")
                    for err in errores:
                        st.error(err)
                    if hasattr(st, "rerun"):
                        st.rerun()
                    else:
                        st.experimental_rerun()
                else:
                    for err in errores:
                        st.error(f"Fallo al actualizar: {err}")

with col_view:
    st.subheader("📊 Vista de Datos (Tiempo Real)")

    try:
        response = supabase.table(table_name).select("*").order("id", desc=False).limit(5000).execute()
        datos_actuales = response.data

        if datos_actuales:
            st.session_state["cached_table_data"] = datos_actuales

            if modo_edicion:
                editor_version = st.session_state.get("editor_version", 0)
                editor_key = f"main_data_editor_{editor_version}"

                st.data_editor(
                    datos_actuales,
                    key=editor_key,
                    disabled=["id", "created_at"],
                    use_container_width=True,
                    height=1000
                )
                st.caption(f"✏️ Modo edición activo. Modifica celdas directamente en la tabla `{table_name}`.")
            else:
                st.dataframe(datos_actuales, use_container_width=True, height=1000)
                st.caption(f"Mostrando todos los registros de `{table_name}`. (Modo solo lectura)")
        else:
            st.session_state["cached_table_data"] = []
            st.info(f"La tabla `{table_name}` está conectada pero actualmente está vacía.")

    except Exception as e:
        st.error("Ocurrió un error al leer los datos de Supabase.")
        st.error(f"Verifica que la tabla exista y las políticas RLS permitan lectura/escritura. Detalle: {e}")
