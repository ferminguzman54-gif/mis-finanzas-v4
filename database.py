"""
database.py
-----------
Capa de persistencia híbrida (Modo Dual) para "Mis Finanzas v4.0".

Arquitectura de almacenamiento:
1. Modo Nube (Google Sheets): Si existen credenciales configuradas en `st.secrets`
   para `gsheets`, utiliza `st.connection("gsheets", type=GSheetsConnection)`
   para leer y escribir en vivo sobre las 4 pestañas:
   `transacciones`, `tarjetas`, `compromisos_fijos` y `presupuestos`.
2. Modo Local (SQLite Fallback): Si no existen secrets configurados o la conexión
   remota no está disponible, utiliza automáticamente una base de datos SQLite local
   (`finanzas.db`) mediante SQLAlchemy sin interrumpir la ejecución.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import uuid

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

# Importación segura del conector de Google Sheets
try:
    from streamlit_gsheets import GSheetsConnection
    GSHEETS_DISPONIBLE = True
except ImportError:
    GSheetsConnection = None
    GSHEETS_DISPONIBLE = False

# ==============================================================================
# CONFIGURACIÓN DE ARCHIVO LOCAL SQLITE Y ESQUEMAS DE TABLAS
# ==============================================================================
RUTA_DB_LOCAL = Path(__file__).resolve().parent / "finanzas.db"
ENGINE_SQLITE = create_engine(f"sqlite:///{RUTA_DB_LOCAL.as_posix()}", future=True)

# Definición canónica de columnas para las 4 tablas del sistema
ESQUEMAS_TABLAS: dict[str, list[str]] = {
    "transacciones": [
        "ID",
        "Fecha",
        "Hora",
        "Concepto",
        "Categoria",
        "Tipo",
        "Monto",
        "Cuenta",
        "Meses_Sin_Intereses",
        "Nota",
    ],
    "tarjetas": [
        "ID",
        "Nombre",
        "Limite_Credito",
        "Saldo_Actual",
        "Dia_Corte",
        "Dia_Pago",
        "Tasa_Interes_Anual",
        "Cashback_Pct",
        "Puntos_Promociones",
        "Pago_Para_No_Generar_Intereses",
        "Pago_Minimo",
        "Comision_Impago",
    ],
    "compromisos_fijos": [
        "ID",
        "Concepto",
        "Categoria",
        "Monto_Estimado",
        "Dia_Vencimiento",
        "Pagado_Mes_Actual",
    ],
    "presupuestos": [
        "ID",
        "Categoria",
        "Monto_Limite_Mensual",
        "Prioridad",
    ],
}

# Columnas numéricas por tabla para garantizar conversión limpia en Pandas
COLUMNAS_NUMERICAS: dict[str, list[str]] = {
    "transacciones": ["Monto", "Meses_Sin_Intereses"],
    "tarjetas": [
        "Limite_Credito",
        "Saldo_Actual",
        "Dia_Corte",
        "Dia_Pago",
        "Tasa_Interes_Anual",
        "Cashback_Pct",
        "Pago_Para_No_Generar_Intereses",
        "Pago_Minimo",
        "Comision_Impago",
    ],
    "compromisos_fijos": ["Monto_Estimado", "Dia_Vencimiento"],
    "presupuestos": ["Monto_Limite_Mensual"],
}

# Columnas enteras específicas (días del mes y plazos en meses)
COLUMNAS_ENTERAS: set[str] = {
    "Meses_Sin_Intereses",
    "Dia_Corte",
    "Dia_Pago",
    "Dia_Vencimiento",
}

# Catálogo base de categorías según tipo de movimiento
CATEGORIAS_POR_TIPO: dict[str, list[str]] = {
    "Gasto": [
        "Supermercado y Despensa",
        "Vivienda y Renta",
        "Servicios Básicos",
        "Transporte y Gasolina",
        "Salud y Farmacia",
        "Educación",
        "Restaurantes y Café",
        "Entretenimiento y Ocio",
        "Suscripciones Digitales",
        "Compras y Tecnología",
        "Ropa y Cuidado Personal",
        "Pago de Tarjetas / Deuda",
        "Ahorro e Inversión",
        "Otros Gastos",
    ],
    "Ingreso": [
        "Nómina / Salario",
        "Honorarios / Freelance",
        "Ventas / Negocio",
        "Rendimientos / Inversiones",
        "Cashback y Reembolsos",
        "Aguinaldo / Bonos",
        "Otros Ingresos",
    ],
}

# Clasificación por defecto de categorías para la regla 50/30/20
PRIORIDAD_POR_DEFECTO: dict[str, str] = {
    "Supermercado y Despensa": "Necesidad",
    "Vivienda y Renta": "Necesidad",
    "Servicios Básicos": "Necesidad",
    "Transporte y Gasolina": "Necesidad",
    "Salud y Farmacia": "Necesidad",
    "Educación": "Necesidad",
    "Pago de Tarjetas / Deuda": "Necesidad",
    "Restaurantes y Café": "Deseo",
    "Entretenimiento y Ocio": "Deseo",
    "Suscripciones Digitales": "Deseo",
    "Compras y Tecnología": "Deseo",
    "Ropa y Cuidado Personal": "Deseo",
    "Otros Gastos": "Deseo",
    "Ahorro e Inversión": "Ahorro",
}


# ==============================================================================
# DETECCIÓN DE MODO DUAL (GOOGLE SHEETS VS SQLITE LOCAL)
# ==============================================================================
def _tiene_secrets_gsheets() -> bool:
    """
    Verifica de forma segura si existen credenciales válidas de Google Sheets
    en `st.secrets["connections"]["gsheets"]` sin lanzar excepciones cuando
    no existe el archivo `.streamlit/secrets.toml`.
    """
    if not GSHEETS_DISPONIBLE or GSheetsConnection is None:
        return False
    try:
        conexiones = st.secrets.get("connections", {})
        cfg_gsheets = conexiones.get("gsheets", {})
        if not cfg_gsheets:
            return False
        # Verificar que al menos exista la URL o ID de la hoja de cálculo
        spreadsheet = str(cfg_gsheets.get("spreadsheet", "")).strip()
        return bool(spreadsheet)
    except Exception:
        return False


def obtener_conexion_gsheets():
    """
    Intenta instanciar y devolver la conexión `GSheetsConnection` de Streamlit.
    Retorna `None` si no hay configuración o si ocurre algún fallo al inicializar.
    """
    if not _tiene_secrets_gsheets():
        return None
    try:
        return st.connection("gsheets", type=GSheetsConnection)
    except Exception:
        return None


def obtener_estado_conexion() -> dict[str, str]:
    """
    Devuelve información descriptiva sobre el motor de base de datos activo
    para mostrarla en la interfaz de usuario.
    """
    conn = obtener_conexion_gsheets()
    if conn is not None:
        return {
            "modo": "gsheets",
            "titulo": "Google Sheets (En Vivo)",
            "icono": "☁️",
            "detalle": "Sincronización activa con Google Sheets.",
        }
    return {
        "modo": "sqlite",
        "titulo": "SQLite Local (finanzas.db)",
        "icono": "💾",
        "detalle": f"Almacenamiento local activo en {RUTA_DB_LOCAL.name}.",
    }


# ==============================================================================
# INICIALIZACIÓN DE TABLAS EN SQLITE LOCAL
# ==============================================================================
def inicializar_base_datos() -> None:
    """
    Crea las 4 tablas requeridas en la base de datos SQLite local (`finanzas.db`)
    si aún no existen. Garantiza que el fallback local funcione desde el primer arranque.
    """
    sentencias_ddl = [
        """
        CREATE TABLE IF NOT EXISTS transacciones (
            ID TEXT PRIMARY KEY,
            Fecha TEXT,
            Hora TEXT,
            Concepto TEXT,
            Categoria TEXT,
            Tipo TEXT,
            Monto REAL,
            Cuenta TEXT,
            Meses_Sin_Intereses INTEGER,
            Nota TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS tarjetas (
            ID TEXT PRIMARY KEY,
            Nombre TEXT UNIQUE,
            Limite_Credito REAL,
            Saldo_Actual REAL,
            Dia_Corte INTEGER,
            Dia_Pago INTEGER,
            Tasa_Interes_Anual REAL,
            Cashback_Pct REAL,
            Puntos_Promociones TEXT,
            Pago_Para_No_Generar_Intereses REAL,
            Pago_Minimo REAL,
            Comision_Impago REAL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS compromisos_fijos (
            ID TEXT PRIMARY KEY,
            Concepto TEXT UNIQUE,
            Categoria TEXT,
            Monto_Estimado REAL,
            Dia_Vencimiento INTEGER,
            Pagado_Mes_Actual TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS presupuestos (
            ID TEXT PRIMARY KEY,
            Categoria TEXT UNIQUE,
            Monto_Limite_Mensual REAL,
            Prioridad TEXT
        );
        """,
    ]

    with ENGINE_SQLITE.begin() as conn:
        for ddl in sentencias_ddl:
            conn.execute(text(ddl))


# Asegurar que SQLite tenga la estructura lista al importar el módulo
inicializar_base_datos()


# ==============================================================================
# NORMALIZACIÓN, LIMPIEZA Y PREVENCIÓN DE DUPLICADOS EN DATAFRAMES
# ==============================================================================
def _generar_id(prefijo: str) -> str:
    """Genera un identificador corto único con prefijo de entidad (ej. TRX-8F3A12)."""
    sufijo = uuid.uuid4().hex[:6].upper()
    marca_tiempo = datetime.now().strftime("%m%d")
    return f"{prefijo}-{marca_tiempo}-{sufijo}"


def normalizar_dataframe(nombre_tabla: str, df: pd.DataFrame | None) -> pd.DataFrame:
    """
    Asegura que un DataFrame cumpla estrictamente con el esquema de `nombre_tabla`:
    - Unifica el alias 'Categoría' (con tilde) y 'Categoria' (sin tilde).
    - Agrega columnas faltantes con valores por defecto seguros.
    - Convierte columnas numéricas y enteras sin lanzar errores ante nulos o textos.
    - Elimina filas completamente vacías y registros duplicados por ID o clave única.
    """
    if nombre_tabla not in ESQUEMAS_TABLAS:
        raise ValueError(f"Tabla desconocida: {nombre_tabla}")

    columnas_esperadas = ESQUEMAS_TABLAS[nombre_tabla]

    if df is None or df.empty:
        df_limpio = pd.DataFrame(columns=columnas_esperadas)
        # Mantener compatibilidad si algún módulo consulta 'Categoría' con tilde
        if "Categoria" in columnas_esperadas and nombre_tabla == "transacciones":
            df_limpio["Categoría"] = pd.Series(dtype="object")
        return df_limpio

    df_limpio = df.copy()

    # Unificar 'Categoría' -> 'Categoria' si proviene de una hoja con tilde
    if "Categoría" in df_limpio.columns and "Categoria" not in df_limpio.columns:
        df_limpio = df_limpio.rename(columns={"Categoría": "Categoria"})
    elif "Categoría" in df_limpio.columns and "Categoria" in df_limpio.columns:
        df_limpio["Categoria"] = df_limpio["Categoria"].fillna(df_limpio["Categoría"])

    # Eliminar filas donde absolutamente todas las columnas sean nulas o vacías
    df_limpio = df_limpio.dropna(how="all")

    # Asegurar existencia de todas las columnas del esquema
    for col in columnas_esperadas:
        if col not in df_limpio.columns:
            df_limpio[col] = 0 if col in COLUMNAS_NUMERICAS.get(nombre_tabla, []) else ""

    # Ordenar sólo las columnas del esquema principal
    df_limpio = df_limpio[columnas_esperadas].copy()

    # Limpieza de columnas de texto
    columnas_num = set(COLUMNAS_NUMERICAS.get(nombre_tabla, []))
    for col in columnas_esperadas:
        if col not in columnas_num:
            df_limpio[col] = (
                df_limpio[col]
                .fillna("")
                .astype(str)
                .replace({"nan": "", "None": "", "<NA>": ""})
                .str.strip()
            )

    # Descartar filas sin datos reales (por ejemplo, filas en blanco de Google Sheets)
    if nombre_tabla == "transacciones":
        df_limpio = df_limpio[
            (df_limpio["Concepto"] != "") | (pd.to_numeric(df_limpio["Monto"], errors="coerce").fillna(0) > 0)
        ]
    elif nombre_tabla == "tarjetas":
        df_limpio = df_limpio[df_limpio["Nombre"] != ""]
    elif nombre_tabla == "compromisos_fijos":
        df_limpio = df_limpio[df_limpio["Concepto"] != ""]
    elif nombre_tabla == "presupuestos":
        df_limpio = df_limpio[df_limpio["Categoria"] != ""]

    # Conversión segura de columnas numéricas
    for col in COLUMNAS_NUMERICAS.get(nombre_tabla, []):
        # Limpiar símbolos monetarios o comas si vienen desde Google Sheets
        serie_str = (
            df_limpio[col]
            .astype(str)
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.replace("%", "", regex=False)
            .str.strip()
        )
        serie_num = pd.to_numeric(serie_str, errors="coerce").fillna(0.0)
        if col in COLUMNAS_ENTERAS:
            df_limpio[col] = serie_num.round(0).astype(int)
        else:
            df_limpio[col] = serie_num.round(2).astype(float)

    # Generar IDs faltantes si alguna fila manual en Google Sheets no tenía ID
    prefijos = {
        "transacciones": "TRX",
        "tarjetas": "TDC",
        "compromisos_fijos": "CMP",
        "presupuestos": "PRE",
    }
    prefijo = prefijos.get(nombre_tabla, "REG")
    df_limpio["ID"] = df_limpio["ID"].apply(
        lambda x: x if str(x).strip() != "" else _generar_id(prefijo)
    )

    # Prevención de duplicados conservando la versión más reciente ('last')
    df_limpio = df_limpio.drop_duplicates(subset=["ID"], keep="last")

    # Claves únicas de negocio adicionales por tabla
    claves_negocio = {
        "tarjetas": "Nombre",
        "compromisos_fijos": "Concepto",
        "presupuestos": "Categoria",
    }
    if nombre_tabla in claves_negocio and not df_limpio.empty:
        col_clave = claves_negocio[nombre_tabla]
        df_limpio["_clave_norm"] = df_limpio[col_clave].str.lower().str.strip()
        df_limpio = df_limpio.drop_duplicates(subset=["_clave_norm"], keep="last").drop(
            columns=["_clave_norm"]
        )

    df_limpio = df_limpio.reset_index(drop=True)

    # En transacciones exponemos también la columna espejo 'Categoría' (con tilde)
    # para compatibilidad total con cualquier consulta que use o no tilde.
    if nombre_tabla == "transacciones":
        df_limpio["Categoría"] = df_limpio["Categoria"]

    return df_limpio


def _preparar_para_persistir(nombre_tabla: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepara el DataFrame con las columnas exactas del esquema antes de escribirlo
    en Google Sheets o SQLite (removiendo columnas espejo auxiliares).
    """
    df_norm = normalizar_dataframe(nombre_tabla, df)
    columnas_esquema = ESQUEMAS_TABLAS[nombre_tabla]
    return df_norm[columnas_esquema].copy()


# ==============================================================================
# OPERACIONES BASE DE LECTURA Y ESCRITURA (MODO DUAL)
# ==============================================================================
def leer_tabla(nombre_tabla: str) -> pd.DataFrame:
    """
    Lee una de las 4 tablas (`transacciones`, `tarjetas`, `compromisos_fijos`, `presupuestos`).
    Intenta primero desde Google Sheets si está configurado; en caso contrario o ante
    cualquier error de red/configuración, lee desde SQLite local (`finanzas.db`).
    """
    if nombre_tabla not in ESQUEMAS_TABLAS:
        raise ValueError(f"Nombre de tabla inválido: {nombre_tabla}")

    conn_gs = obtener_conexion_gsheets()
    if conn_gs is not None:
        try:
            df_remoto = conn_gs.read(worksheet=nombre_tabla, ttl=0)
            return normalizar_dataframe(nombre_tabla, df_remoto)
        except Exception:
            # Fallback transparente a SQLite si la pestaña aún no existe o falla la red
            pass

    # Fallback a SQLite local
    inicializar_base_datos()
    try:
        with ENGINE_SQLITE.connect() as conn:
            df_local = pd.read_sql_table(nombre_tabla, con=conn)
        return normalizar_dataframe(nombre_tabla, df_local)
    except Exception:
        return normalizar_dataframe(nombre_tabla, pd.DataFrame())


def guardar_tabla(nombre_tabla: str, df: pd.DataFrame) -> bool:
    """
    Sobrescribe de manera segura y sin duplicados una tabla completa tanto en
    el almacenamiento activo (Google Sheets si está disponible) como en el respaldo
    SQLite local (`finanzas.db`).
    """
    df_persistir = _preparar_para_persistir(nombre_tabla, df)

    exito_gsheets = False
    conn_gs = obtener_conexion_gsheets()
    if conn_gs is not None:
        try:
            conn_gs.update(worksheet=nombre_tabla, data=df_persistir)
            st.cache_data.clear()
            exito_gsheets = True
        except Exception:
            exito_gsheets = False

    # Siempre sincronizamos también en SQLite local como respaldo transaccional
    try:
        inicializar_base_datos()
        with ENGINE_SQLITE.begin() as conn:
            conn.execute(text(f"DELETE FROM {nombre_tabla}"))
            if not df_persistir.empty:
                df_persistir.to_sql(
                    nombre_tabla,
                    con=conn,
                    if_exists="append",
                    index=False,
                )
        return True
    except Exception:
        return exito_gsheets


# ==============================================================================
# FUNCIONES CRUD: 1. TRANSACCIONES
# ==============================================================================
def obtener_transacciones() -> pd.DataFrame:
    """Devuelve todas las transacciones ordenadas de la más reciente a la más antigua."""
    df = leer_tabla("transacciones")
    if df.empty:
        return df
    df_ord = df.sort_values(by=["Fecha", "Hora"], ascending=[False, False]).reset_index(drop=True)
    return df_ord


def registrar_transaccion(
    datos: dict[str, Any],
    actualizar_saldo_tarjeta: bool = True,
) -> tuple[bool, str]:
    """
    Inserta o actualiza una transacción evitando duplicados.
    Si la cuenta asociada corresponde a una tarjeta de crédito registrada:
    - Un 'Gasto' incrementa el `Saldo_Actual` de dicha tarjeta.
    - Un 'Ingreso' (o abono a tarjeta) disminuye el `Saldo_Actual`.
    """
    concepto = str(datos.get("Concepto", "")).strip()
    if not concepto:
        return False, "El concepto de la transacción es obligatorio."

    monto = float(datos.get("Monto", 0.0) or 0.0)
    if monto <= 0:
        return False, "El monto de la transacción debe ser mayor a $0.00."

    categoria = str(datos.get("Categoria") or datos.get("Categoría") or "Otros Gastos").strip()
    tipo = str(datos.get("Tipo", "Gasto")).strip()
    cuenta = str(datos.get("Cuenta", "Efectivo / Débito")).strip()
    msi = int(datos.get("Meses_Sin_Intereses", 1) or 1)
    fecha = str(datos.get("Fecha") or datetime.now().strftime("%Y-%m-%d")).strip()
    hora = str(datos.get("Hora") or datetime.now().strftime("%H:%M:%S")).strip()
    nota = str(datos.get("Nota", "")).strip()
    id_trx = str(datos.get("ID") or "").strip() or _generar_id("TRX")

    df_actual = leer_tabla("transacciones")

    # Prevenir doble clic accidental en el mismo minuto con los mismos datos exactos
    if not df_actual.empty and not datos.get("ID"):
        posibles_duplicados = df_actual[
            (df_actual["Fecha"] == fecha)
            & (df_actual["Concepto"].str.lower() == concepto.lower())
            & (df_actual["Categoria"].str.lower() == categoria.lower())
            & (df_actual["Tipo"] == tipo)
            & (df_actual["Cuenta"] == cuenta)
            & ((df_actual["Monto"] - monto).abs() < 0.005)
            & (df_actual["Hora"].str[:5] == hora[:5])
        ]
        if not posibles_duplicados.empty:
            return False, "Esta transacción ya fue registrada hace unos instantes (duplicado prevenido)."

    nueva_fila = pd.DataFrame(
        [
            {
                "ID": id_trx,
                "Fecha": fecha,
                "Hora": hora,
                "Concepto": concepto,
                "Categoria": categoria,
                "Tipo": tipo,
                "Monto": round(monto, 2),
                "Cuenta": cuenta,
                "Meses_Sin_Intereses": max(1, msi),
                "Nota": nota,
            }
        ]
    )

    df_base = df_actual[ESQUEMAS_TABLAS["transacciones"]] if not df_actual.empty else pd.DataFrame(columns=ESQUEMAS_TABLAS["transacciones"])
    df_nuevo = pd.concat([df_base, nueva_fila], ignore_index=True)

    guardado_ok = guardar_tabla("transacciones", df_nuevo)
    if not guardado_ok:
        return False, "No fue posible guardar la transacción en la base de datos."

    # Actualizar el saldo de la tarjeta de crédito si el movimiento se hizo con una tarjeta
    if actualizar_saldo_tarjeta:
        df_tarjetas = leer_tabla("tarjetas")
        if not df_tarjetas.empty:
            mascara = df_tarjetas["Nombre"].str.lower() == cuenta.lower()
            if mascara.any():
                delta = monto if tipo == "Gasto" else -monto
                df_tarjetas.loc[mascara, "Saldo_Actual"] = (
                    df_tarjetas.loc[mascara, "Saldo_Actual"] + delta
                ).clip(lower=0.0)
                guardar_tabla("tarjetas", df_tarjetas)

    return True, f"Transacción '{concepto}' por ${monto:,.2f} registrada correctamente."


def eliminar_transaccion(id_transaccion: str) -> tuple[bool, str]:
    """Elimina una transacción por su `ID`."""
    df = leer_tabla("transacciones")
    if df.empty or id_transaccion not in df["ID"].values:
        return False, "No se encontró la transacción especificada."
    df_filtrado = df[df["ID"] != id_transaccion].copy()
    ok = guardar_tabla("transacciones", df_filtrado)
    return (True, "Transacción eliminada.") if ok else (False, "Error al eliminar la transacción.")


# ==============================================================================
# FUNCIONES CRUD: 2. TARJETAS DE CRÉDITO
# ==============================================================================
def obtener_tarjetas() -> pd.DataFrame:
    """Devuelve el catálogo de tarjetas registradas."""
    return leer_tabla("tarjetas")


def guardar_tarjeta(datos: dict[str, Any]) -> tuple[bool, str]:
    """
    Crea o actualiza una tarjeta de crédito sin duplicar filas.
    Si ya existe una tarjeta con el mismo `ID` o `Nombre`, actualiza sus parámetros.
    """
    nombre = str(datos.get("Nombre", "")).strip()
    if not nombre:
        return False, "El nombre de la tarjeta es obligatorio."

    limite = float(datos.get("Limite_Credito", 0.0) or 0.0)
    if limite <= 0:
        return False, "El límite de crédito debe ser mayor a $0.00."

    dia_corte = int(datos.get("Dia_Corte", 1) or 1)
    dia_pago = int(datos.get("Dia_Pago", 15) or 15)
    if not (1 <= dia_corte <= 31 and 1 <= dia_pago <= 31):
        return False, "Los días de corte y pago deben estar entre 1 y 31."

    df_actual = leer_tabla("tarjetas")
    id_existente = str(datos.get("ID") or "").strip()

    if not id_existente and not df_actual.empty:
        coincidencia = df_actual[df_actual["Nombre"].str.lower() == nombre.lower()]
        if not coincidencia.empty:
            id_existente = str(coincidencia.iloc[-1]["ID"])

    id_tarjeta = id_existente or _generar_id("TDC")

    registro = {
        "ID": id_tarjeta,
        "Nombre": nombre,
        "Limite_Credito": round(limite, 2),
        "Saldo_Actual": round(float(datos.get("Saldo_Actual", 0.0) or 0.0), 2),
        "Dia_Corte": dia_corte,
        "Dia_Pago": dia_pago,
        "Tasa_Interes_Anual": round(float(datos.get("Tasa_Interes_Anual", 0.0) or 0.0), 2),
        "Cashback_Pct": round(float(datos.get("Cashback_Pct", 0.0) or 0.0), 2),
        "Puntos_Promociones": str(datos.get("Puntos_Promociones", "")).strip(),
        "Pago_Para_No_Generar_Intereses": round(
            float(datos.get("Pago_Para_No_Generar_Intereses", 0.0) or 0.0), 2
        ),
        "Pago_Minimo": round(float(datos.get("Pago_Minimo", 0.0) or 0.0), 2),
        "Comision_Impago": round(float(datos.get("Comision_Impago", 0.0) or 0.0), 2),
    }

    df_base = (
        df_actual[ESQUEMAS_TABLAS["tarjetas"]]
        if not df_actual.empty
        else pd.DataFrame(columns=ESQUEMAS_TABLAS["tarjetas"])
    )
    df_nuevo = pd.concat([df_base, pd.DataFrame([registro])], ignore_index=True)

    ok = guardar_tabla("tarjetas", df_nuevo)
    accion = "actualizada" if id_existente else "registrada"
    return (
        (True, f"Tarjeta '{nombre}' {accion} exitosamente.")
        if ok
        else (False, "Error al guardar la tarjeta.")
    )


def eliminar_tarjeta(id_tarjeta: str) -> tuple[bool, str]:
    """Elimina una tarjeta por su `ID`."""
    df = leer_tabla("tarjetas")
    if df.empty or id_tarjeta not in df["ID"].values:
        return False, "No se encontró la tarjeta seleccionada."
    df_filtrado = df[df["ID"] != id_tarjeta].copy()
    ok = guardar_tabla("tarjetas", df_filtrado)
    return (True, "Tarjeta eliminada correctamente.") if ok else (False, "No se pudo eliminar la tarjeta.")


# ==============================================================================
# FUNCIONES CRUD: 3. COMPROMISOS FIJOS
# ==============================================================================
def obtener_compromisos() -> pd.DataFrame:
    """Devuelve los compromisos fijos del mes ordenados por día de vencimiento."""
    df = leer_tabla("compromisos_fijos")
    if df.empty:
        return df
    return df.sort_values(by=["Dia_Vencimiento", "Concepto"], ascending=[True, True]).reset_index(
        drop=True
    )


def guardar_compromiso(datos: dict[str, Any]) -> tuple[bool, str]:
    """
    Crea o actualiza un compromiso fijo mensual (Luz, Agua, Internet, Renta, etc.)
    sin duplicar registros con el mismo concepto.
    """
    concepto = str(datos.get("Concepto", "")).strip()
    if not concepto:
        return False, "El concepto del compromiso fijo es obligatorio."

    monto_estimado = float(datos.get("Monto_Estimado", 0.0) or 0.0)
    if monto_estimado <= 0:
        return False, "El monto estimado debe ser mayor a $0.00."

    dia_vencimiento = int(datos.get("Dia_Vencimiento", 1) or 1)
    if not (1 <= dia_vencimiento <= 31):
        return False, "El día de vencimiento debe estar entre 1 y 31."

    pagado = str(datos.get("Pagado_Mes_Actual", "No")).strip()
    pagado = "Sí" if pagado.lower() in {"sí", "si", "true", "1", "pagado"} else "No"

    df_actual = leer_tabla("compromisos_fijos")
    id_existente = str(datos.get("ID") or "").strip()

    if not id_existente and not df_actual.empty:
        coincidencia = df_actual[df_actual["Concepto"].str.lower() == concepto.lower()]
        if not coincidencia.empty:
            id_existente = str(coincidencia.iloc[-1]["ID"])

    id_comp = id_existente or _generar_id("CMP")

    registro = {
        "ID": id_comp,
        "Concepto": concepto,
        "Categoria": str(datos.get("Categoria", "Servicios Básicos")).strip(),
        "Monto_Estimado": round(monto_estimado, 2),
        "Dia_Vencimiento": dia_vencimiento,
        "Pagado_Mes_Actual": pagado,
    }

    df_base = (
        df_actual[ESQUEMAS_TABLAS["compromisos_fijos"]]
        if not df_actual.empty
        else pd.DataFrame(columns=ESQUEMAS_TABLAS["compromisos_fijos"])
    )
    df_nuevo = pd.concat([df_base, pd.DataFrame([registro])], ignore_index=True)

    ok = guardar_tabla("compromisos_fijos", df_nuevo)
    accion = "actualizado" if id_existente else "registrado"
    return (
        (True, f"Compromiso fijo '{concepto}' {accion} correctamente.")
        if ok
        else (False, "Error al guardar el compromiso fijo.")
    )


def cambiar_estado_compromiso(
    id_compromiso: str,
    pagado: str = "Sí",
    registrar_gasto_automatico: bool = False,
    cuenta_pago: str = "Efectivo / Débito",
) -> tuple[bool, str]:
    """
    Actualiza el campo `Pagado_Mes_Actual` ('Sí' / 'No') de un compromiso fijo.
    Opcionalmente registra el pago como una transacción de gasto en el historial.
    """
    df = leer_tabla("compromisos_fijos")
    if df.empty or id_compromiso not in df["ID"].values:
        return False, "No se encontró el compromiso fijo indicado."

    estado_normalizado = "Sí" if str(pagado).lower() in {"sí", "si", "true", "1"} else "No"
    mascara = df["ID"] == id_compromiso
    fila = df.loc[mascara].iloc[0]

    df.loc[mascara, "Pagado_Mes_Actual"] = estado_normalizado
    ok = guardar_tabla("compromisos_fijos", df)
    if not ok:
        return False, "No fue posible actualizar el estado del compromiso."

    if estado_normalizado == "Sí" and registrar_gasto_automatico:
        registrar_transaccion(
            {
                "Concepto": f"Pago de servicio: {fila['Concepto']}",
                "Categoria": fila["Categoria"],
                "Tipo": "Gasto",
                "Monto": float(fila["Monto_Estimado"]),
                "Cuenta": cuenta_pago,
                "Meses_Sin_Intereses": 1,
                "Nota": "Generado al marcar compromiso fijo como pagado",
            }
        )

    return True, f"Estado de '{fila['Concepto']}' actualizado a: {estado_normalizado}."


def reiniciar_compromisos_mes() -> tuple[bool, str]:
    """Restablece todos los compromisos fijos a 'No' pagado al iniciar un nuevo mes."""
    df = leer_tabla("compromisos_fijos")
    if df.empty:
        return False, "No hay compromisos fijos registrados para reiniciar."
    df["Pagado_Mes_Actual"] = "No"
    ok = guardar_tabla("compromisos_fijos", df)
    return (
        (True, "Todos los compromisos fueron reiniciados a 'No' pagado para el nuevo ciclo.")
        if ok
        else (False, "Error al reiniciar los compromisos.")
    )


def eliminar_compromiso(id_compromiso: str) -> tuple[bool, str]:
    """Elimina un compromiso fijo por su `ID`."""
    df = leer_tabla("compromisos_fijos")
    if df.empty or id_compromiso not in df["ID"].values:
        return False, "No se encontró el compromiso fijo."
    df_filtrado = df[df["ID"] != id_compromiso].copy()
    ok = guardar_tabla("compromisos_fijos", df_filtrado)
    return (True, "Compromiso eliminado.") if ok else (False, "Error al eliminar el compromiso.")


# ==============================================================================
# FUNCIONES CRUD: 4. PRESUPUESTOS
# ==============================================================================
def obtener_presupuestos() -> pd.DataFrame:
    """Devuelve los presupuestos mensuales configurados por categoría."""
    df = leer_tabla("presupuestos")
    if df.empty:
        return df
    return df.sort_values(by=["Prioridad", "Categoria"], ascending=[True, True]).reset_index(
        drop=True
    )


def guardar_presupuesto(datos: dict[str, Any]) -> tuple[bool, str]:
    """
    Crea o actualiza el presupuesto mensual de una categoría sin duplicar filas.
    """
    categoria = str(datos.get("Categoria") or datos.get("Categoría") or "").strip()
    if not categoria:
        return False, "La categoría del presupuesto es obligatoria."

    limite = float(datos.get("Monto_Limite_Mensual", 0.0) or 0.0)
    if limite <= 0:
        return False, "El monto límite mensual debe ser mayor a $0.00."

    prioridad = str(
        datos.get("Prioridad") or PRIORIDAD_POR_DEFECTO.get(categoria, "Necesidad")
    ).strip()
    if prioridad not in {"Necesidad", "Deseo", "Ahorro"}:
        prioridad = "Necesidad"

    df_actual = leer_tabla("presupuestos")
    id_existente = str(datos.get("ID") or "").strip()

    if not id_existente and not df_actual.empty:
        coincidencia = df_actual[df_actual["Categoria"].str.lower() == categoria.lower()]
        if not coincidencia.empty:
            id_existente = str(coincidencia.iloc[-1]["ID"])

    id_pres = id_existente or _generar_id("PRE")

    registro = {
        "ID": id_pres,
        "Categoria": categoria,
        "Monto_Limite_Mensual": round(limite, 2),
        "Prioridad": prioridad,
    }

    df_base = (
        df_actual[ESQUEMAS_TABLAS["presupuestos"]]
        if not df_actual.empty
        else pd.DataFrame(columns=ESQUEMAS_TABLAS["presupuestos"])
    )
    df_nuevo = pd.concat([df_base, pd.DataFrame([registro])], ignore_index=True)

    ok = guardar_tabla("presupuestos", df_nuevo)
    accion = "actualizado" if id_existente else "creado"
    return (
        (True, f"Presupuesto para '{categoria}' {accion} en ${limite:,.2f}/mes.")
        if ok
        else (False, "Error al guardar el presupuesto.")
    )


def eliminar_presupuesto(id_presupuesto: str) -> tuple[bool, str]:
    """Elimina un presupuesto por su `ID`."""
    df = leer_tabla("presupuestos")
    if df.empty or id_presupuesto not in df["ID"].values:
        return False, "No se encontró el presupuesto indicado."
    df_filtrado = df[df["ID"] != id_presupuesto].copy()
    ok = guardar_tabla("presupuestos", df_filtrado)
    return (True, "Presupuesto eliminado.") if ok else (False, "Error al eliminar el presupuesto.")


# ==============================================================================
# UTILIDADES DE CATÁLOGOS Y DATOS DE DEMOSTRACIÓN (OPCIONAL)
# ==============================================================================
def obtener_cuentas_disponibles() -> list[str]:
    """
    Retorna la lista de métodos de pago disponibles combinando cuentas líquidas
    y los nombres de las tarjetas de crédito registradas.
    """
    cuentas_base = ["Efectivo / Débito", "Transferencia SPEI", "Fondo de Ahorro"]
    df_tarjetas = obtener_tarjetas()
    if not df_tarjetas.empty:
        nombres_tdc = [str(n).strip() for n in df_tarjetas["Nombre"].tolist() if str(n).strip()]
        for tdc in nombres_tdc:
            if tdc not in cuentas_base:
                cuentas_base.append(tdc)
    return cuentas_base


def cargar_datos_ejemplo() -> tuple[bool, str]:
    """
    Carga un conjunto de datos financieros de ejemplo en las 4 tablas para pruebas
    rápidas si el usuario desea explorar el sistema con registros pre-cargados.
    """
    hoy = datetime.now()
    mes_actual = hoy.strftime("%Y-%m")
    dia_hoy = hoy.day

    # Calcular un día de corte que esté entre 1 y 4 días antes de hoy para demostrar la ventana óptima
    corte_optimo = max(1, ((dia_hoy - 3 - 1) % 28) + 1)
    pago_optimo = ((corte_optimo + 19) % 28) + 1

    tarjetas_demo = [
        {
            "ID": "TDC-DEMO-01",
            "Nombre": "Nu Crédito",
            "Limite_Credito": 35000.0,
            "Saldo_Actual": 4200.0,
            "Dia_Corte": corte_optimo,
            "Dia_Pago": pago_optimo,
            "Tasa_Interes_Anual": 62.5,
            "Cashback_Pct": 1.5,
            "Puntos_Promociones": "MSI en comercios participantes y meses flexibles",
            "Pago_Para_No_Generar_Intereses": 4200.0,
            "Pago_Minimo": 450.0,
            "Comision_Impago": 400.0,
        },
        {
            "ID": "TDC-DEMO-02",
            "Nombre": "BBVA Azul",
            "Limite_Credito": 60000.0,
            "Saldo_Actual": 11800.0,
            "Dia_Corte": max(1, ((dia_hoy - 14 - 1) % 28) + 1),
            "Dia_Pago": max(1, ((dia_hoy + 6 - 1) % 28) + 1),
            "Tasa_Interes_Anual": 48.9,
            "Cashback_Pct": 1.8,
            "Puntos_Promociones": "Puntos BBVA dobles en viajes y restaurantes",
            "Pago_Para_No_Generar_Intereses": 8900.0,
            "Pago_Minimo": 980.0,
            "Comision_Impago": 448.0,
        },
        {
            "ID": "TDC-DEMO-03",
            "Nombre": "HSBC 2Now",
            "Limite_Credito": 45000.0,
            "Saldo_Actual": 6500.0,
            "Dia_Corte": max(1, ((dia_hoy - 2 - 1) % 28) + 1),
            "Dia_Pago": max(1, ((dia_hoy + 18 - 1) % 28) + 1),
            "Tasa_Interes_Anual": 54.0,
            "Cashback_Pct": 2.0,
            "Puntos_Promociones": "2% Cashback directo en todas las compras",
            "Pago_Para_No_Generar_Intereses": 6500.0,
            "Pago_Minimo": 650.0,
            "Comision_Impago": 499.0,
        },
    ]

    compromisos_demo = [
        {
            "ID": "CMP-DEMO-01",
            "Concepto": "Renta / Hipoteca",
            "Categoria": "Vivienda y Renta",
            "Monto_Estimado": 8500.0,
            "Dia_Vencimiento": 5,
            "Pagado_Mes_Actual": "Sí",
        },
        {
            "ID": "CMP-DEMO-02",
            "Concepto": "Luz (CFE)",
            "Categoria": "Servicios Básicos",
            "Monto_Estimado": 680.0,
            "Dia_Vencimiento": 18,
            "Pagado_Mes_Actual": "No",
        },
        {
            "ID": "CMP-DEMO-03",
            "Concepto": "Agua Potable",
            "Categoria": "Servicios Básicos",
            "Monto_Estimado": 320.0,
            "Dia_Vencimiento": 20,
            "Pagado_Mes_Actual": "No",
        },
        {
            "ID": "CMP-DEMO-04",
            "Concepto": "Internet Fibra Óptica",
            "Categoria": "Servicios Básicos",
            "Monto_Estimado": 699.0,
            "Dia_Vencimiento": 22,
            "Pagado_Mes_Actual": "No",
        },
    ]

    presupuestos_demo = [
        {
            "ID": "PRE-DEMO-01",
            "Categoria": "Vivienda y Renta",
            "Monto_Limite_Mensual": 8500.0,
            "Prioridad": "Necesidad",
        },
        {
            "ID": "PRE-DEMO-02",
            "Categoria": "Supermercado y Despensa",
            "Monto_Limite_Mensual": 5000.0,
            "Prioridad": "Necesidad",
        },
        {
            "ID": "PRE-DEMO-03",
            "Categoria": "Servicios Básicos",
            "Monto_Limite_Mensual": 2000.0,
            "Prioridad": "Necesidad",
        },
        {
            "ID": "PRE-DEMO-04",
            "Categoria": "Transporte y Gasolina",
            "Monto_Limite_Mensual": 2500.0,
            "Prioridad": "Necesidad",
        },
        {
            "ID": "PRE-DEMO-05",
            "Categoria": "Restaurantes y Café",
            "Monto_Limite_Mensual": 2200.0,
            "Prioridad": "Deseo",
        },
        {
            "ID": "PRE-DEMO-06",
            "Categoria": "Entretenimiento y Ocio",
            "Monto_Limite_Mensual": 1800.0,
            "Prioridad": "Deseo",
        },
        {
            "ID": "PRE-DEMO-07",
            "Categoria": "Compras y Tecnología",
            "Monto_Limite_Mensual": 2500.0,
            "Prioridad": "Deseo",
        },
    ]

    transacciones_demo = [
        {
            "ID": "TRX-DEMO-01",
            "Fecha": f"{mes_actual}-01",
            "Hora": "09:00:00",
            "Concepto": "Nómina Quincena 1",
            "Categoria": "Nómina / Salario",
            "Tipo": "Ingreso",
            "Monto": 16500.0,
            "Cuenta": "Transferencia SPEI",
            "Meses_Sin_Intereses": 1,
            "Nota": "Depósito quincenal principal",
        },
        {
            "ID": "TRX-DEMO-02",
            "Fecha": f"{mes_actual}-15",
            "Hora": "09:15:00",
            "Concepto": "Nómina Quincena 2",
            "Categoria": "Nómina / Salario",
            "Tipo": "Ingreso",
            "Monto": 16500.0,
            "Cuenta": "Transferencia SPEI",
            "Meses_Sin_Intereses": 1,
            "Nota": "Segundo depósito quincenal",
        },
        {
            "ID": "TRX-DEMO-03",
            "Fecha": f"{mes_actual}-05",
            "Hora": "11:20:00",
            "Concepto": "Pago de Renta Mensual",
            "Categoria": "Vivienda y Renta",
            "Tipo": "Gasto",
            "Monto": 8500.0,
            "Cuenta": "Transferencia SPEI",
            "Meses_Sin_Intereses": 1,
            "Nota": "Renta departamento",
        },
        {
            "ID": "TRX-DEMO-04",
            "Fecha": f"{mes_actual}-07",
            "Hora": "18:40:00",
            "Concepto": "Despensa quincenal supermercado",
            "Categoria": "Supermercado y Despensa",
            "Tipo": "Gasto",
            "Monto": 2650.0,
            "Cuenta": "HSBC 2Now",
            "Meses_Sin_Intereses": 1,
            "Nota": "2% cashback aplicado",
        },
        {
            "ID": "TRX-DEMO-05",
            "Fecha": f"{mes_actual}-10",
            "Hora": "14:10:00",
            "Concepto": "Carga de gasolina",
            "Categoria": "Transporte y Gasolina",
            "Tipo": "Gasto",
            "Monto": 1150.0,
            "Cuenta": "Nu Crédito",
            "Meses_Sin_Intereses": 1,
            "Nota": "Tanque lleno",
        },
        {
            "ID": "TRX-DEMO-06",
            "Fecha": f"{mes_actual}-12",
            "Hora": "21:05:00",
            "Concepto": "Cena fin de semana",
            "Categoria": "Restaurantes y Café",
            "Tipo": "Gasto",
            "Monto": 1380.0,
            "Cuenta": "BBVA Azul",
            "Meses_Sin_Intereses": 1,
            "Nota": "Salida familiar",
        },
    ]

    ok_t = guardar_tabla("tarjetas", pd.DataFrame(tarjetas_demo))
    ok_c = guardar_tabla("compromisos_fijos", pd.DataFrame(compromisos_demo))
    ok_p = guardar_tabla("presupuestos", pd.DataFrame(presupuestos_demo))
    ok_x = guardar_tabla("transacciones", pd.DataFrame(transacciones_demo))

    if ok_t and ok_c and ok_p and ok_x:
        return True, "Datos de demostración cargados correctamente en las 4 tablas."
    return False, "Ocurrió un problema al cargar los datos de ejemplo."
