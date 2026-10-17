"""
app.py
------
Aplicación principal de "Mis Finanzas v4.0".
Integra la interfaz de usuario en Streamlit con el motor de cálculo financiero
(`financial_engine.py`), la persistencia dual Google Sheets / SQLite (`database.py`)
y el sistema de diseño en modo oscuro (`ui_styles.py`).
"""

from __future__ import annotations

import ast
from datetime import datetime
import operator
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from database import (
    CATEGORIAS_POR_TIPO,
    PRIORIDAD_POR_DEFECTO,
    cambiar_estado_compromiso,
    cargar_datos_ejemplo,
    eliminar_compromiso,
    eliminar_presupuesto,
    eliminar_tarjeta,
    eliminar_transaccion,
    guardar_compromiso,
    guardar_presupuesto,
    guardar_tarjeta,
    obtener_compromisos,
    obtener_cuentas_disponibles,
    obtener_estado_conexion,
    obtener_presupuestos,
    obtener_tarjetas,
    obtener_transacciones,
    registrar_transaccion,
    reiniciar_compromisos_mes,
)
from financial_engine import (
    calcular_liquidez_libre,
    calcular_pareto_categorias,
    calcular_regla_50_30_20,
    obtener_directorio_consejos,
    recomendar_tarjeta_del_dia,
    simular_compra,
)
from ui_styles import (
    PALETA,
    aplicar_estilos_globales,
    estilo_fig,
    obtener_badge_semaforo,
    render_alerta,
    render_metric_card,
)

# ==============================================================================
# CONFIGURACIÓN INICIAL DE LA PÁGINA DE STREAMLIT
# ==============================================================================
st.set_page_config(
    page_title="Mis Finanzas v4.0 | Arquitectura Financiera Personal",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Aplicar hoja de estilos global en modo oscuro (#0f0f1a, Sora y JetBrains Mono)
aplicar_estilos_globales()


# ==============================================================================
# EVALUADOR SEGURO PARA LA CALCULADORA DE APOYO
# ==============================================================================
_OPERADORES_PERMITIDOS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def evaluar_expresion_calculadora(expresion: str) -> float:
    """
    Evalúa de forma segura una expresión aritmética básica (ej. '1250 + 380 * 2')
    usando el árbol sintáctico de Python (AST) sin recurrir a `eval()` inseguro.
    """
    expresion_limpia = expresion.replace(",", "").replace("$", "").strip()
    if not expresion_limpia:
        raise ValueError("Ingresa una operación matemática (ej. 450 + 189.50).")

    def _evaluar_nodo(nodo):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)):
            return float(nodo.value)
        if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES_PERMITIDOS:
            izq = _evaluar_nodo(nodo.left)
            der = _evaluar_nodo(nodo.right)
            return float(_OPERADORES_PERMITIDOS[type(nodo.op)](izq, der))
        if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERADORES_PERMITIDOS:
            operando = _evaluar_nodo(nodo.operand)
            return float(_OPERADORES_PERMITIDOS[type(nodo.op)](operando))
        raise ValueError("Expresión no válida. Usa únicamente números y operadores (+, -, *, /).")

    arbol = ast.parse(expresion_limpia, mode="eval")
    resultado = _evaluar_nodo(arbol.body)
    return round(resultado, 2)


# ==============================================================================
# ESTADO DE SESIÓN INICIAL PARA CALCULADORA Y MONTO DE TRANSACCIÓN
# ==============================================================================
if "monto_transaccion_input" not in st.session_state:
    st.session_state["monto_transaccion_input"] = 0.0
if "resultado_calculadora" not in st.session_state:
    st.session_state["resultado_calculadora"] = 0.0


# ==============================================================================
# CARGA DE DATOS EN MEMORIA PARA EL CICLO DE RENDERIZADO ACTUAL
# ==============================================================================
df_transacciones = obtener_transacciones()
df_tarjetas = obtener_tarjetas()
df_compromisos = obtener_compromisos()
df_presupuestos = obtener_presupuestos()

# Cálculo global de liquidez libre del mes actual
mes_actual_prefijo = datetime.now().strftime("%Y-%m")
if not df_transacciones.empty:
    df_trx_mes = df_transacciones[
        df_transacciones["Fecha"].astype(str).str.startswith(mes_actual_prefijo)
    ]
    if df_trx_mes.empty:
        df_trx_mes = df_transacciones
else:
    df_trx_mes = df_transacciones

resumen_liquidez = calcular_liquidez_libre(df_trx_mes, df_trx_mes, df_compromisos)


# ==============================================================================
# BARRA LATERAL: NAVEGACIÓN PRINCIPAL Y ESTADO DE CONEXIÓN DUAL
# ==============================================================================
with st.sidebar:
    st.markdown("## 💎 Mis Finanzas v4.0")
    st.caption("Arquitectura de Inteligencia Financiera Personal")
    st.markdown("---")

    # Menú lateral con las 5 pestañas requeridas
    pestana_activa = st.radio(
        "Navegación Principal",
        options=[
            "📝 Registrar Transacción",
            "💳 Tarjetas y Compromisos Fijos",
            "🛒 Simulador de Decisiones",
            "📊 Historial y Gráficos",
            "🧠 Asesor Financiero",
        ],
        index=0,
    )

    st.markdown("---")

    # Indicador de Modo Dual (Google Sheets vs SQLite Local)
    estado_db = obtener_estado_conexion()
    st.markdown(
        f"""
        <div class="metric-card cyan" style="padding: 0.85rem 1rem;">
            <div class="metric-title">{estado_db['icono']} Motor de Persistencia</div>
            <div class="metric-value" style="font-size: 1.02rem;">{estado_db['titulo']}</div>
            <div class="metric-sub">{estado_db['detalle']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Resumen rápido de Liquidez Libre en la barra lateral
    variante_liq = (
        "default"
        if resumen_liquidez["nivel"] == "success"
        else ("warning" if resumen_liquidez["nivel"] == "warning" else "danger")
    )
    render_metric_card(
        titulo="Liquidez Libre del Mes",
        valor=f"${resumen_liquidez['liquidez_libre']:,.2f}",
        subtitulo=(
            f"Descontando ${resumen_liquidez['compromisos_pendientes']:,.2f} "
            f"de {resumen_liquidez['cantidad_pendientes']} servicio(s) pendiente(s)"
        ),
        variante=variante_liq,
        icono="🛡️",
    )

    # Utilidad para poblar datos de demostración si la base está vacía
    with st.expander("⚙️ Herramientas de Datos"):
        st.caption("¿Deseas explorar la aplicación con registros de prueba pre-cargados?")
        if st.button("✨ Cargar Datos de Ejemplo", key="btn_demo_sidebar"):
            ok_demo, msg_demo = cargar_datos_ejemplo()
            if ok_demo:
                st.success(msg_demo)
                st.rerun()
            else:
                st.error(msg_demo)


# ==============================================================================
# PESTAÑA 1: 📝 REGISTRAR TRANSACCIÓN
# ==============================================================================
if pestana_activa == "📝 Registrar Transacción":
    st.title("📝 Registrar Transacción")
    st.caption(
        "Registra tus ingresos y gastos diarios con recomendación inteligente de medio de pago."
    )

    # 1. Banner superior con la tarjeta recomendada para usar hoy
    recomendacion_hoy = recomendar_tarjeta_del_dia(df_tarjetas, datetime.now().date())
    if recomendacion_hoy["disponible"] and recomendacion_hoy["mejor_tarjeta"] is not None:
        mejor_tdc = recomendacion_hoy["mejor_tarjeta"]
        etiqueta_optima = (
            "🌟 VENTANA DORADA DE FINANCIAMIENTO (40-50 DÍAS SIN INTERESES)"
            if mejor_tdc["En_Ventana_Dorada"]
            else "💳 TARJETA ÓPTIMA RECOMENDADA PARA USAR HOY"
        )
        st.markdown(
            f"""
            <div class="recommended-card-banner">
                <div class="banner-tag">{etiqueta_optima}</div>
                <div class="banner-title">
                    Usa hoy: {mejor_tdc['Nombre']} &nbsp;|&nbsp;
                    <span class="mono-num" style="color: #4fffb0;">
                        ~{mejor_tdc['Dias_Financiamiento']} días para pagar
                    </span>
                </div>
                <div class="banner-details">
                    Cortó hace <strong>{mejor_tdc['Dias_Desde_Corte']} día(s)</strong> (día {mejor_tdc['Dia_Corte']}) •
                    Cashback: <strong class="mono-num">{mejor_tdc['Cashback_Pct']:.1f}%</strong> •
                    Disponible: <strong class="mono-num">${mejor_tdc['Credito_Disponible']:,.2f}</strong>
                    {f" • 🎁 {mejor_tdc['Puntos_Promociones']}" if mejor_tdc['Puntos_Promociones'] else ""}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info(
            "💡 Aún no has registrado tarjetas de crédito. Agrégalas en la pestaña "
            "**'💳 Tarjetas y Compromisos Fijos'** para activar el recomendador diario de corte y cashback."
        )

    # 2. Tarjetas de resumen de liquidez superior
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        render_metric_card(
            "Ingresos del Mes",
            f"${resumen_liquidez['ingresos_totales']:,.2f}",
            "Entradas registradas",
            variante="default",
            icono="📈",
        )
    with col_m2:
        render_metric_card(
            "Gastos Ejercidos",
            f"${resumen_liquidez['gastos_totales']:,.2f}",
            "Salidas acumuladas",
            variante="cyan",
            icono="💸",
        )
    with col_m3:
        render_metric_card(
            "Compromisos Pendientes",
            f"${resumen_liquidez['compromisos_pendientes']:,.2f}",
            f"{resumen_liquidez['cantidad_pendientes']} recibo(s) por pagar este mes",
            variante="warning",
            icono="🧾",
        )
    with col_m4:
        render_metric_card(
            "Liquidez Libre Real",
            f"${resumen_liquidez['liquidez_libre']:,.2f}",
            resumen_liquidez["estado"],
            variante=variante_liq,
            icono="🛡️",
        )

    st.markdown("---")

    # 3. Disposición en dos columnas: Formulario Dinámico (izq) y Calculadora de Apoyo (der)
    col_form, col_calc = st.columns([1.85, 1.15], gap="large")

    with col_calc:
        st.subheader("🧮 Calculadora de Apoyo")
        st.caption(
            "Suma tickets, propinas o divide cuentas y envía el resultado directo al campo Monto."
        )
        expresion_calc = st.text_input(
            "Operación aritmética",
            placeholder="Ej: 345.50 + 120 * 2 - 50",
            key="input_expresion_calc",
        )
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button("Calcular Resultado", key="btn_ejecutar_calc"):
                try:
                    res = evaluar_expresion_calculadora(expresion_calc)
                    st.session_state["resultado_calculadora"] = max(0.0, res)
                except ValueError as err:
                    st.warning(str(err))

        with c_btn2:
            if st.button("📥 Cargar al Monto", key="btn_cargar_monto"):
                st.session_state["monto_transaccion_input"] = float(
                    st.session_state.get("resultado_calculadora", 0.0)
                )
                st.toast(
                    f"Monto cargado: ${st.session_state['monto_transaccion_input']:,.2f}",
                    icon="✅",
                )

        render_metric_card(
            titulo="Resultado de Calculadora",
            valor=f"${st.session_state['resultado_calculadora']:,.2f}",
            subtitulo="Haz clic en 'Cargar al Monto' para transferirlo al formulario",
            variante="purple",
            icono="🔢",
        )

    with col_form:
        st.subheader("➕ Nuevo Movimiento")

        # Selector reactivo de Tipo fuera del form para actualizar Categorías en tiempo real
        c_tipo, c_cat = st.columns(2)
        with c_tipo:
            tipo_seleccionado = st.selectbox(
                "Tipo de Movimiento",
                options=["Gasto", "Ingreso"],
                index=0,
                key="sel_tipo_dinamico",
            )

        # Construir lista dinámica de categorías según el tipo elegido
        categorias_base = list(CATEGORIAS_POR_TIPO.get(tipo_seleccionado, ["Otros"]))
        if tipo_seleccionado == "Gasto" and not df_presupuestos.empty:
            for cat_pres in df_presupuestos["Categoria"].tolist():
                if cat_pres and cat_pres not in categorias_base:
                    categorias_base.append(cat_pres)

        with c_cat:
            categoria_seleccionada = st.selectbox(
                "Categoría",
                options=categorias_base,
                key="sel_categoria_dinamica",
            )

        cuentas_disponibles = obtener_cuentas_disponibles()
        # Si hay tarjeta recomendada hoy y es un gasto, sugerirla por defecto
        indice_cuenta_defecto = 0
        if (
            tipo_seleccionado == "Gasto"
            and recomendacion_hoy["disponible"]
            and recomendacion_hoy["mejor_tarjeta"] is not None
        ):
            nombre_rec = recomendacion_hoy["mejor_tarjeta"]["Nombre"]
            if nombre_rec in cuentas_disponibles:
                indice_cuenta_defecto = cuentas_disponibles.index(nombre_rec)

        with st.form("form_registro_transaccion", clear_on_submit=False):
            f_col1, f_col2 = st.columns([1.6, 1.0])
            with f_col1:
                concepto_input = st.text_input(
                    "Concepto o Descripción *",
                    placeholder="Ej: Supermercado semanal, Nómina, Cena...",
                )
            with f_col2:
                monto_input = st.number_input(
                    "Monto ($) *",
                    min_value=0.0,
                    step=50.0,
                    format="%.2f",
                    key="monto_transaccion_input",
                )

            f_col3, f_col4, f_col5 = st.columns([1.3, 1.0, 1.0])
            with f_col3:
                cuenta_input = st.selectbox(
                    "Cuenta / Medio de Pago",
                    options=cuentas_disponibles,
                    index=indice_cuenta_defecto,
                )
            with f_col4:
                msi_input = st.selectbox(
                    "Meses Sin Intereses (MSI)",
                    options=[1, 3, 6, 9, 12, 18, 24],
                    index=0,
                    disabled=(tipo_seleccionado == "Ingreso"),
                )
            with f_col5:
                fecha_input = st.date_input("Fecha", value=datetime.now().date())

            nota_input = st.text_input(
                "Nota adicional (opcional)",
                placeholder="Detalle opcional, comercio o folio...",
            )

            enviado = st.form_submit_button("💾 Guardar Transacción")
            if enviado:
                exito, mensaje = registrar_transaccion(
                    {
                        "Fecha": fecha_input.strftime("%Y-%m-%d"),
                        "Hora": datetime.now().strftime("%H:%M:%S"),
                        "Concepto": concepto_input,
                        "Categoria": categoria_seleccionada,
                        "Tipo": tipo_seleccionado,
                        "Monto": monto_input,
                        "Cuenta": cuenta_input,
                        "Meses_Sin_Intereses": 1 if tipo_seleccionado == "Ingreso" else msi_input,
                        "Nota": nota_input,
                    }
                )
                if exito:
                    st.success(mensaje)
                    st.rerun()
                else:
                    st.error(mensaje)


# ==============================================================================
# PESTAÑA 2: 💳 TARJETAS Y COMPROMISOS FIJOS
# ==============================================================================
elif pestana_activa == "💳 Tarjetas y Compromisos Fijos":
    st.title("💳 Tarjetas de Crédito y Compromisos Fijos")
    st.caption(
        "Administra tus líneas de crédito con semáforo de fechas de corte/pago y controla el checklist de recibos del mes."
    )

    sub_tdc, sub_comp = st.tabs(
        ["💳 Mis Tarjetas de Crédito (Semáforo)", "🧾 Checklist de Compromisos Fijos del Mes"]
    )

    # --------------------------------------------------------------------------
    # SUB-PESTAÑA 2A: DASHBOARD Y GESTIÓN DE TARJETAS DE CRÉDITO
    # --------------------------------------------------------------------------
    with sub_tdc:
        eval_tdc = recomendar_tarjeta_del_dia(df_tarjetas, datetime.now().date())

        if not eval_tdc["disponible"] or eval_tdc["ranking"].empty:
            st.info(
                "💳 No hay tarjetas de crédito registradas todavía. Utiliza el formulario inferior para dar de alta tu primera tarjeta."
            )
        else:
            df_rank_tdc = eval_tdc["ranking"]
            total_limite = float(df_rank_tdc["Limite_Credito"].sum())
            total_saldo = float(df_rank_tdc["Saldo_Actual"].sum())
            total_no_intereses = float(df_rank_tdc["Pago_Para_No_Generar_Intereses"].sum())

            k1, k2, k3 = st.columns(3)
            with k1:
                render_metric_card(
                    "Línea de Crédito Total",
                    f"${total_limite:,.2f}",
                    f"Disponible total: ${(total_limite - total_saldo):,.2f}",
                    variante="cyan",
                    icono="🏦",
                )
            with k2:
                render_metric_card(
                    "Saldo Total Utilizado",
                    f"${total_saldo:,.2f}",
                    f"Uso global: {((total_saldo / total_limite * 100) if total_limite > 0 else 0):.1f}%",
                    variante="warning" if total_saldo > (total_limite * 0.5) else "default",
                    icono="💳",
                )
            with k3:
                render_metric_card(
                    "Pago Para No Generar Intereses",
                    f"${total_no_intereses:,.2f}",
                    "Suma de estados de cuenta vigentes",
                    variante="purple",
                    icono="🛡️",
                )

            st.markdown("### 🚦 Semáforo de Tarjetas Registradas")
            cols_tarjetas = st.columns(min(3, max(1, len(df_rank_tdc))))
            for idx, (_, tdc) in enumerate(df_rank_tdc.iterrows()):
                col_actual = cols_tarjetas[idx % len(cols_tarjetas)]
                with col_actual:
                    badge_corte = obtener_badge_semaforo(
                        f"Corte día {int(tdc['Dia_Corte'])} ({tdc['Dias_Desde_Corte']}d post-corte)",
                        tdc["Semaforo_Corte"],
                    )
                    badge_pago = obtener_badge_semaforo(
                        f"Pago en {int(tdc['Dias_Para_Pago'])} día(s) (día {int(tdc['Dia_Pago'])})",
                        tdc["Semaforo_Pago"],
                    )
                    variante_card = (
                        "default"
                        if tdc["Semaforo_Corte"] == "verde"
                        else ("warning" if tdc["Semaforo_Corte"] == "amarillo" else "danger")
                    )
                    st.markdown(
                        f"""
                        <div class="metric-card {variante_card}">
                            <div class="metric-title">💳 {tdc['Nombre']}</div>
                            <div class="metric-value">${tdc['Saldo_Actual']:,.2f}
                                <span style="font-size:0.82rem; color:#94a3b8; font-weight:400;">
                                    / ${tdc['Limite_Credito']:,.2f}
                                </span>
                            </div>
                            <div style="margin: 0.45rem 0; display:flex; flex-wrap:wrap; gap:0.35rem;">
                                {badge_corte} {badge_pago}
                            </div>
                            <div class="metric-sub">
                                • Ventana hoy: <strong>~{int(tdc['Dias_Financiamiento'])} días sin intereses</strong><br>
                                • Tasa Anual: <span class="mono-num">{tdc['Tasa_Interes_Anual']:.1f}%</span> |
                                  Cashback: <span class="mono-num">{tdc['Cashback_Pct']:.1f}%</span><br>
                                • Pago sin intereses: <span class="mono-num">${tdc['Pago_Para_No_Generar_Intereses']:,.2f}</span> |
                                  Mínimo: <span class="mono-num">${tdc['Pago_Minimo']:,.2f}</span><br>
                                • Comisión impago: <span class="mono-num">${tdc['Comision_Impago']:,.2f}</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st.button(f"🗑️ Eliminar {tdc['Nombre']}", key=f"del_tdc_{tdc['ID']}"):
                        ok_del, msg_del = eliminar_tarjeta(str(tdc["ID"]))
                        if ok_del:
                            st.success(msg_del)
                            st.rerun()

        st.markdown("---")
        with st.expander("➕ Agregar o Actualizar Tarjeta de Crédito", expanded=df_tarjetas.empty):
            with st.form("form_guardar_tarjeta"):
                t_c1, t_c2, t_c3 = st.columns(3)
                with t_c1:
                    nombre_tdc = st.text_input("Nombre de la Tarjeta *", placeholder="Ej: Nu, BBVA Azul, HSBC 2Now")
                    limite_tdc = st.number_input("Límite de Crédito ($)", min_value=0.0, step=1000.0, value=25000.0)
                    saldo_tdc = st.number_input("Saldo Actual Utilizado ($)", min_value=0.0, step=500.0, value=0.0)
                with t_c2:
                    dia_corte_tdc = st.number_input("Día de Corte (1-31)", min_value=1, max_value=31, value=10)
                    dia_pago_tdc = st.number_input("Día Límite de Pago (1-31)", min_value=1, max_value=31, value=30)
                    tasa_tdc = st.number_input("Tasa de Interés Anual (%)", min_value=0.0, max_value=200.0, step=1.0, value=55.0)
                with t_c3:
                    cashback_tdc = st.number_input("Porcentaje de Cashback (%)", min_value=0.0, max_value=20.0, step=0.5, value=1.5)
                    pago_no_int_tdc = st.number_input("Pago para No Generar Intereses ($)", min_value=0.0, step=500.0, value=0.0)
                    pago_min_tdc = st.number_input("Pago Mínimo ($)", min_value=0.0, step=100.0, value=0.0)

                t_c4, t_c5 = st.columns([2, 1])
                with t_c4:
                    promos_tdc = st.text_input("Puntos y Promociones", placeholder="Ej: 2% cashback directo o MSI en viajes")
                with t_c5:
                    comision_tdc = st.number_input("Comisión por Impago ($)", min_value=0.0, step=50.0, value=400.0)

                if st.form_submit_button("💾 Guardar Tarjeta"):
                    ok_t, msg_t = guardar_tarjeta(
                        {
                            "Nombre": nombre_tdc,
                            "Limite_Credito": limite_tdc,
                            "Saldo_Actual": saldo_tdc,
                            "Dia_Corte": dia_corte_tdc,
                            "Dia_Pago": dia_pago_tdc,
                            "Tasa_Interes_Anual": tasa_tdc,
                            "Cashback_Pct": cashback_tdc,
                            "Puntos_Promociones": promos_tdc,
                            "Pago_Para_No_Generar_Intereses": pago_no_int_tdc,
                            "Pago_Minimo": pago_min_tdc,
                            "Comision_Impago": comision_tdc,
                        }
                    )
                    if ok_t:
                        st.success(msg_t)
                        st.rerun()
                    else:
                        st.error(msg_t)

    # --------------------------------------------------------------------------
    # SUB-PESTAÑA 2B: CHECKLIST DE COMPROMISOS FIJOS DEL MES
    # --------------------------------------------------------------------------
    with sub_comp:
        st.markdown("### 🧾 Checklist Interactiva de Servicios del Mes (Luz, Agua, Internet, Renta)")

        registrar_al_pagar = st.checkbox(
            "Registrar automáticamente una transacción de Gasto al marcar un servicio como pagado",
            value=True,
        )

        if df_compromisos.empty:
            st.info(
                "🧾 No tienes compromisos fijos registrados. Agrega tus servicios mensuales (Luz, Agua, Internet, Renta) abajo."
            )
        else:
            dia_actual_num = datetime.now().day
            for _, comp in df_compromisos.iterrows():
                id_c = str(comp["ID"])
                concepto_c = str(comp["Concepto"])
                cat_c = str(comp["Categoria"])
                monto_c = float(comp["Monto_Estimado"])
                dia_venc = int(comp["Dia_Vencimiento"])
                esta_pagado = str(comp["Pagado_Mes_Actual"]).strip().lower() in {"sí", "si"}

                if esta_pagado:
                    badge_comp = obtener_badge_semaforo("✅ Pagado este mes", "verde")
                elif dia_venc < dia_actual_num:
                    badge_comp = obtener_badge_semaforo(f"🚨 Venció el día {dia_venc}", "rojo")
                elif dia_venc - dia_actual_num <= 5:
                    badge_comp = obtener_badge_semaforo(f"⚠️ Vence pronto (día {dia_venc})", "amarillo")
                else:
                    badge_comp = obtener_badge_semaforo(f"⏳ Pendiente (día {dia_venc})", "amarillo")

                col_info, col_acc1, col_acc2 = st.columns([3.0, 1.3, 0.7])
                with col_info:
                    st.markdown(
                        f"""
                        <div class="metric-card {'default' if esta_pagado else 'warning'}" style="padding: 0.85rem 1.1rem; margin-bottom: 0.5rem;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <div>
                                    <strong style="font-size:1.02rem;">{concepto_c}</strong>
                                    <span style="color:#94a3b8; font-size:0.82rem;"> • {cat_c}</span>
                                </div>
                                {badge_comp}
                            </div>
                            <div class="mono-num" style="font-size:1.15rem; font-weight:700; margin-top:0.25rem;">
                                ${monto_c:,.2f} <span style="font-size:0.78rem; color:#94a3b8;">(Día de pago: {dia_venc})</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_acc1:
                    if not esta_pagado:
                        if st.button("✅ Marcar como pagado", key=f"btn_pay_{id_c}"):
                            ok_c, msg_c = cambiar_estado_compromiso(
                                id_c,
                                pagado="Sí",
                                registrar_gasto_automatico=registrar_al_pagar,
                            )
                            if ok_c:
                                st.success(msg_c)
                                st.rerun()
                    else:
                        if st.button("↩️ Marcar pendiente", key=f"btn_unpay_{id_c}"):
                            ok_c, msg_c = cambiar_estado_compromiso(id_c, pagado="No")
                            if ok_c:
                                st.info(msg_c)
                                st.rerun()
                with col_acc2:
                    if st.button("🗑️", key=f"btn_del_comp_{id_c}"):
                        ok_d, _ = eliminar_compromiso(id_c)
                        if ok_d:
                            st.rerun()

            if st.button("🔄 Reiniciar todos los servicios a 'No pagado' (Nuevo Mes)"):
                ok_r, msg_r = reiniciar_compromisos_mes()
                if ok_r:
                    st.success(msg_r)
                    st.rerun()

        st.markdown("---")
        with st.expander("➕ Agregar o Actualizar Compromiso Fijo", expanded=df_compromisos.empty):
            with st.form("form_compromiso_fijo"):
                cc1, cc2, cc3, cc4 = st.columns([1.5, 1.3, 1.0, 1.0])
                with cc1:
                    concepto_comp = st.text_input("Concepto del Servicio *", placeholder="Ej: Luz (CFE), Agua, Internet, Renta")
                with cc2:
                    cat_comp = st.selectbox("Categoría", options=CATEGORIAS_POR_TIPO["Gasto"])
                with cc3:
                    monto_comp = st.number_input("Monto Estimado ($)", min_value=0.0, step=100.0, value=650.0)
                with cc4:
                    dia_comp = st.number_input("Día de Vencimiento (1-31)", min_value=1, max_value=31, value=15)

                if st.form_submit_button("💾 Guardar Compromiso Fijo"):
                    ok_cf, msg_cf = guardar_compromiso(
                        {
                            "Concepto": concepto_comp,
                            "Categoria": cat_comp,
                            "Monto_Estimado": monto_comp,
                            "Dia_Vencimiento": dia_comp,
                            "Pagado_Mes_Actual": "No",
                        }
                    )
                    if ok_cf:
                        st.success(msg_cf)
                        st.rerun()
                    else:
                        st.error(msg_cf)


# ==============================================================================
# PESTAÑA 3: 🛒 SIMULADOR DE DECISIONES
# ==============================================================================
elif pestana_activa == "🛒 Simulador de Decisiones":
    st.title("🛒 Simulador de Decisiones de Compra")
    st.caption(
        "Evalúa en 4 dimensiones si una compra es saludable hoy: impacto en presupuesto, liquidez de servicios, "
        "flujo a 3-6 meses (protegiendo julio y diciembre) y costo real de financiamiento + IVA."
    )

    with st.form("form_simulador_decisiones"):
        s_col1, s_col2, s_col3 = st.columns([1.5, 1.2, 1.3])
        with s_col1:
            producto_sim = st.text_input(
                "Producto o Servicio a Evaluar",
                value="Compra Planeada",
                placeholder="Ej: Laptop, Refrigerador, Viaje, Smartphone...",
            )
        with s_col2:
            monto_sim = st.number_input(
                "Monto Total de la Compra ($)",
                min_value=100.0,
                step=500.0,
                value=6000.0,
            )
        with s_col3:
            categoria_sim = st.selectbox(
                "Categoría del Gasto",
                options=CATEGORIAS_POR_TIPO["Gasto"],
                index=9,  # Compras y Tecnología por defecto
            )

        s_col4, s_col5 = st.columns([1.2, 1.8])
        with s_col4:
            diferir_sim = st.selectbox(
                "Plazo a Diferir (Meses)",
                options=[1, 3, 6, 9, 12, 18],
                index=1,
            )
        with s_col5:
            st.markdown("<div style='height: 1.4rem;'></div>", unsafe_allow_html=True)
            no_liquidar_sim = st.checkbox(
                "⚠️ Simular que NO podré liquidar a tiempo (Calcular Interés Mensual + 16% IVA)",
                value=False,
            )

        ejecutar_simulacion = st.form_submit_button("🔍 Evaluar Impacto Financiero en 4 Dimensiones")

    # Ejecutar diagnóstico (con valores por defecto o al enviar el formulario)
    resultado_sim = simular_compra(
        monto=monto_sim,
        categoria=categoria_sim,
        tarjetas=df_tarjetas,
        compromisos=df_compromisos,
        presupuestos=df_presupuestos,
        diferir_meses=diferir_sim,
        no_podra_liquidar=no_liquidar_sim,
        transacciones=df_transacciones,
        fecha_actual=datetime.now().date(),
    )

    d1 = resultado_sim["dimension_1_presupuesto"]
    d2 = resultado_sim["dimension_2_liquidez"]
    d3 = resultado_sim["dimension_3_proyeccion"]
    d4 = resultado_sim["dimension_4_tarjeta"]

    # Banner de veredicto global
    render_alerta(
        mensaje=(
            f"Evaluación para <strong>{producto_sim}</strong> por <strong>${monto_sim:,.2f}</strong> "
            f"en <strong>{diferir_sim} mes(es)</strong> (Cuota mensual base: <strong>${resultado_sim['cargo_mensual']:,.2f}</strong>)."
        ),
        tipo=resultado_sim["nivel_global"],
        titulo=resultado_sim["veredicto"],
    )

    # Tarjetas de las 4 Dimensiones
    dim_c1, dim_c2, dim_c3, dim_c4 = st.columns(4)
    with dim_c1:
        render_metric_card(
            "1. Presupuesto Categoría",
            f"{d1['pct_despues']:.1f}%" if d1["limite_mensual"] > 0 else f"${d1['nuevo_gasto_categoria']:,.2f}",
            d1["estado"],
            variante="danger" if d1["nivel"] == "danger" else ("warning" if d1["nivel"] == "warning" else "default"),
            icono="🎯",
        )
    with dim_c2:
        render_metric_card(
            "2. Liquidez Post-Compra",
            f"${d2['liquidez_despues']:,.2f}",
            f"Servicios pendientes: ${d2['compromisos_pendientes']:,.2f}",
            variante="danger" if d2["nivel"] == "danger" else ("warning" if d2["nivel"] == "warning" else "cyan"),
            icono="💧",
        )
    with dim_c3:
        temp_txt = "Toca Julio/Diciembre ⚠️" if (d3["toca_julio"] or d3["toca_diciembre"]) else "Temporadas Protegidas ✅"
        render_metric_card(
            "3. Proyección 3-6 Meses",
            f"{diferir_sim} mes(es)",
            temp_txt,
            variante="warning" if (d3["toca_julio"] or d3["toca_diciembre"]) else "default",
            icono="🗓️",
        )
    with dim_c4:
        if d4["tarjeta_optima"]:
            t_opt = d4["tarjeta_optima"]
            sub_t = (
                f"Interés+IVA: ${t_opt['Interes_Mensual_Con_IVA']:,.2f}/mes"
                if no_liquidar_sim
                else f"Cashback: ${t_opt['Cashback_Monto']:,.2f} (~{t_opt['Dias_Financiamiento']}d)"
            )
            render_metric_card(
                "4. Tarjeta Óptima",
                t_opt["Nombre"],
                sub_t,
                variante="purple",
                icono="💳",
            )
        else:
            render_metric_card(
                "4. Tarjeta Óptima",
                "Sin Tarjetas",
                "Registra tarjetas para comparar",
                variante="warning",
                icono="💳",
            )

    # Detalle explicativo de las 4 dimensiones
    col_det1, col_det2 = st.columns(2)
    with col_det1:
        render_alerta(d1["mensaje"], tipo=d1["nivel"], titulo="Dimensión 1 (Presupuesto)")
        render_alerta(d2["mensaje"], tipo=d2["nivel"], titulo="Dimensión 2 (Solvencia de Servicios)")
    with col_det2:
        render_alerta(d3["mensaje"], tipo=d3["nivel"], titulo="Dimensión 3 (Blindaje Julio y Diciembre)")
        render_alerta(d4["mensaje"], tipo=d4["nivel"], titulo="Dimensión 4 (Tarjeta y Costo Financiero)")

    st.markdown("---")

    # Gráficos interactivos del Simulador: Comparativa de Intereses y Proyección Estacional
    g_sim1, g_sim2 = st.columns(2)

    with g_sim1:
        st.subheader("📊 Comparativa de Costo de Intereses + IVA por Tarjeta")
        df_comp_tdc = d4["df_comparativa"]
        if df_comp_tdc.empty:
            st.info("💳 Registra al menos una tarjeta de crédito para visualizar la comparativa de intereses y cashback.")
        else:
            fig_int = go.Figure()
            fig_int.add_trace(
                go.Bar(
                    name="Interés Mensual (con 16% IVA)",
                    x=df_comp_tdc["Nombre"],
                    y=df_comp_tdc["Interes_Mensual_Con_IVA"],
                    marker_color=PALETA["rojo_peligro"],
                    text=[f"${v:,.2f}" for v in df_comp_tdc["Interes_Mensual_Con_IVA"]],
                    textposition="auto",
                )
            )
            fig_int.add_trace(
                go.Bar(
                    name=f"Interés Acumulado ({diferir_sim} mes(es))",
                    x=df_comp_tdc["Nombre"],
                    y=df_comp_tdc["Interes_Total_Plazo"],
                    marker_color=PALETA["amarillo_alerta"],
                    text=[f"${v:,.2f}" for v in df_comp_tdc["Interes_Total_Plazo"]],
                    textposition="auto",
                )
            )
            fig_int.add_trace(
                go.Bar(
                    name="Cashback Recuperado ($)",
                    x=df_comp_tdc["Nombre"],
                    y=df_comp_tdc["Cashback_Monto"],
                    marker_color=PALETA["verde_neon"],
                    text=[f"${v:,.2f}" for v in df_comp_tdc["Cashback_Monto"]],
                    textposition="auto",
                )
            )
            fig_int.update_layout(barmode="group", yaxis_title="Monto ($)")
            st.plotly_chart(
                estilo_fig(fig_int, "Interés Mensual (Monto × Tasa/12 × 1.16) vs Cashback", altura=380),
                use_container_width=True,
            )

    with g_sim2:
        st.subheader("🗓️ Proyección de Flujo a 6 Meses (Temporadas Altas)")
        df_proy = d3["df_proyeccion"]
        fig_proy = go.Figure()
        fig_proy.add_trace(
            go.Bar(
                name="Compromisos Fijos Base",
                x=df_proy["Periodo"],
                y=df_proy["Compromisos_Base"],
                marker_color=PALETA["cian_brillante"],
            )
        )
        fig_proy.add_trace(
            go.Bar(
                name="Reserva Temporada Alta (Jul/Dic)",
                x=df_proy["Periodo"],
                y=df_proy["Reserva_Temporada_Alta"],
                marker_color=PALETA["amarillo_alerta"],
            )
        )
        fig_proy.add_trace(
            go.Bar(
                name="Cuota Nueva Compra",
                x=df_proy["Periodo"],
                y=df_proy["Cuota_Nueva_Compra"],
                marker_color=PALETA["morado_acento"],
            )
        )
        fig_proy.add_trace(
            go.Scatter(
                name="Flujo Libre Proyectado",
                x=df_proy["Periodo"],
                y=df_proy["Flujo_Libre_Proyectado"],
                mode="lines+markers",
                line=dict(color=PALETA["verde_neon"], width=3),
            )
        )
        fig_proy.update_layout(barmode="stack", yaxis_title="Monto ($)")
        st.plotly_chart(
            estilo_fig(fig_proy, "Carga Mensual y Reserva de Verano (Jul) / Navidad (Dic)", altura=380),
            use_container_width=True,
        )


# ==============================================================================
# PESTAÑA 4: 📊 HISTORIAL Y GRÁFICOS
# ==============================================================================
elif pestana_activa == "📊 Historial y Gráficos":
    st.title("📊 Historial de Movimientos y Análisis Visual")
    st.caption(
        "Filtra tus transacciones, exporta reportes compatibles con Excel (UTF-8-SIG) y monitorea el cumplimiento de tus presupuestos."
    )

    # Gestor desplegable de Presupuestos Mensuales
    with st.expander("🎯 Configurar Presupuestos Mensuales por Categoría", expanded=df_presupuestos.empty):
        p_col1, p_col2 = st.columns([1.4, 1.6])
        with p_col1:
            with st.form("form_guardar_presupuesto"):
                cat_pres_in = st.selectbox("Categoría de Gasto", options=CATEGORIAS_POR_TIPO["Gasto"])
                lim_pres_in = st.number_input("Monto Límite Mensual ($)", min_value=100.0, step=250.0, value=3000.0)
                prio_def = PRIORIDAD_POR_DEFECTO.get(cat_pres_in, "Necesidad")
                prio_pres_in = st.selectbox(
                    "Prioridad (Regla 50/30/20)",
                    options=["Necesidad", "Deseo", "Ahorro"],
                    index=["Necesidad", "Deseo", "Ahorro"].index(prio_def)
                    if prio_def in {"Necesidad", "Deseo", "Ahorro"}
                    else 0,
                )
                if st.form_submit_button("💾 Guardar Presupuesto"):
                    ok_p, msg_p = guardar_presupuesto(
                        {
                            "Categoria": cat_pres_in,
                            "Monto_Limite_Mensual": lim_pres_in,
                            "Prioridad": prio_pres_in,
                        }
                    )
                    if ok_p:
                        st.success(msg_p)
                        st.rerun()
                    else:
                        st.error(msg_p)
        with p_col2:
            if df_presupuestos.empty:
                st.info("Aún no has configurado límites de presupuesto.")
            else:
                st.dataframe(
                    df_presupuestos[["Categoria", "Monto_Limite_Mensual", "Prioridad"]],
                    use_container_width=True,
                    hide_index=True,
                )

    st.markdown("---")

    if df_transacciones.empty:
        st.info(
            "📭 No existen transacciones registradas todavía. Dirígete a **'📝 Registrar Transacción'** "
            "o usa el botón **'✨ Cargar Datos de Ejemplo'** en la barra lateral."
        )
    else:
        # Barra de filtros interactivos
        f1, f2, f3, f4 = st.columns([1.0, 1.3, 1.3, 1.4])
        with f1:
            filtro_tipo = st.multiselect(
                "Tipo",
                options= sorted(df_transacciones["Tipo"].unique().tolist()),
                default=sorted(df_transacciones["Tipo"].unique().tolist()),
            )
        with f2:
            opciones_cat = sorted(df_transacciones["Categoria"].unique().tolist())
            filtro_cat = st.multiselect("Categoría", options=opciones_cat, default=opciones_cat)
        with f3:
            opciones_cta = sorted(df_transacciones["Cuenta"].unique().tolist())
            filtro_cta = st.multiselect("Cuenta / Tarjeta", options=opciones_cta, default=opciones_cta)
        with f4:
            busqueda_texto = st.text_input("Buscar por concepto o nota", placeholder="Ej: supermercado, nómina...")

        df_filtrado = df_transacciones[
            df_transacciones["Tipo"].isin(filtro_tipo)
            & df_transacciones["Categoria"].isin(filtro_cat)
            & df_transacciones["Cuenta"].isin(filtro_cta)
        ].copy()

        if busqueda_texto.strip():
            patron = busqueda_texto.strip().lower()
            df_filtrado = df_filtrado[
                df_filtrado["Concepto"].str.lower().str.contains(patron, na=False)
                | df_filtrado["Nota"].str.lower().str.contains(patron, na=False)
            ]

        # Tabla filtrable y botón de exportación CSV con codificación utf-8-sig
        col_tbl_hdr, col_csv_btn = st.columns([3.0, 1.0])
        with col_tbl_hdr:
            st.subheader(f"📋 Movimientos Filtrados ({len(df_filtrado)} registros)")
        with col_csv_btn:
            columnas_exportar = [
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
            ]
            csv_bytes = df_filtrado[columnas_exportar].to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="📥 Exportar CSV (UTF-8-SIG)",
                data=csv_bytes,
                file_name=f"mis_finanzas_historial_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

        st.dataframe(
            df_filtrado[columnas_exportar],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")

        # Sección de 3 gráficos analíticos:
        # 1) Presupuesto vs Gasto Real  2) Distribución por Categorías  3) Evolución Temporal
        g_col1, g_col2 = st.columns(2)

        df_gastos_hist = df_filtrado[df_filtrado["Tipo"] == "Gasto"].copy()

        with g_col1:
            st.subheader("🎯 Presupuesto vs. Gasto Real por Categoría")
            if df_presupuestos.empty and df_gastos_hist.empty:
                st.info("Registra gastos o presupuestos para visualizar la comparativa.")
            else:
                gasto_por_cat = (
                    df_gastos_hist.groupby("Categoria", as_index=False)["Monto"].sum()
                    if not df_gastos_hist.empty
                    else pd.DataFrame(columns=["Categoria", "Monto"])
                )
                df_p_vs_g = pd.merge(
                    df_presupuestos[["Categoria", "Monto_Limite_Mensual"]],
                    gasto_por_cat,
                    on="Categoria",
                    how="outer",
                ).fillna(0.0)

                if df_p_vs_g.empty:
                    st.info("No hay datos suficientes para comparar presupuesto vs gasto.")
                else:
                    fig_pvg = go.Figure()
                    fig_pvg.add_trace(
                        go.Bar(
                            name="Presupuesto Límite",
                            x=df_p_vs_g["Categoria"],
                            y=df_p_vs_g["Monto_Limite_Mensual"],
                            marker_color=PALETA["cian_brillante"],
                        )
                    )
                    fig_pvg.add_trace(
                        go.Bar(
                            name="Gasto Ejercido",
                            x=df_p_vs_g["Categoria"],
                            y=df_p_vs_g["Monto"],
                            marker_color=PALETA["verde_neon"],
                        )
                    )
                    fig_pvg.update_layout(barmode="group", yaxis_title="Monto ($)")
                    st.plotly_chart(
                        estilo_fig(fig_pvg, "Límite Mensual vs Gasto Acumulado", altura=380),
                        use_container_width=True,
                    )

        with g_col2:
            st.subheader("🍩 Distribución de Gastos por Categoría")
            if df_gastos_hist.empty:
                st.info("No hay gastos en la selección actual para graficar su distribución.")
            else:
                dist_cat = (
                    df_gastos_hist.groupby("Categoria", as_index=False)["Monto"]
                    .sum()
                    .sort_values(by="Monto", ascending=False)
                )
                fig_dona = go.Figure(
                    data=[
                        go.Pie(
                            labels=dist_cat["Categoria"],
                            values=dist_cat["Monto"],
                            hole=0.52,
                            textinfo="label+percent",
                        )
                    ]
                )
                st.plotly_chart(
                    estilo_fig(fig_dona, "Participación Porcentual del Gasto", altura=380),
                    use_container_width=True,
                )

        st.subheader("📈 Evolución Temporal de Ingresos y Gastos")
        df_evol = (
            df_filtrado.groupby(["Fecha", "Tipo"], as_index=False)["Monto"]
            .sum()
            .sort_values(by="Fecha")
        )
        if df_evol.empty:
            st.info("Sin registros para mostrar la evolución temporal.")
        else:
            fig_evol = go.Figure()
            for tipo_mov, color_mov in [
                ("Ingreso", PALETA["verde_neon"]),
                ("Gasto", PALETA["rojo_peligro"]),
            ]:
                sub_df = df_evol[df_evol["Tipo"] == tipo_mov]
                if not sub_df.empty:
                    fig_evol.add_trace(
                        go.Scatter(
                            name=tipo_mov,
                            x=sub_df["Fecha"],
                            y=sub_df["Monto"],
                            mode="lines+markers",
                            line=dict(color=color_mov, width=3),
                            fill="tozeroy",
                        )
                    )
            fig_evol.update_layout(xaxis_title="Fecha", yaxis_title="Monto ($)")
            st.plotly_chart(
                estilo_fig(fig_evol, "Flujo Histórico por Fecha", altura=360),
                use_container_width=True,
            )


# ==============================================================================
# PESTAÑA 5: 🧠 ASESOR FINANCIERO (REGLA 50/30/20, PARETO 80/20 Y CONSEJOS)
# ==============================================================================
elif pestana_activa == "🧠 Asesor Financiero":
    st.title("🧠 Asesor Financiero Inteligente")
    st.caption(
        "Diagnóstico patrimonial basado en la Regla 50/30/20, Análisis de Pareto (80/20) y estrategias accionables de ahorro."
    )

    # 1. Sección Regla 50/30/20
    st.subheader("⚖️ Diagnóstico de la Regla 50 / 30 / 20 (Necesidades, Deseos y Ahorro)")
    diag_503020 = calcular_regla_50_30_20(df_transacciones, df_presupuestos)

    if not diag_503020["tiene_datos"] or diag_503020["df_resumen"].empty:
        st.info(diag_503020["mensaje"])
    else:
        df_r50 = diag_503020["df_resumen"]
        r_c1, r_c2, r_c3 = st.columns(3)
        variantes_bloque = ["cyan", "warning", "default"]

        for idx, (_, fila_b) in enumerate(df_r50.iterrows()):
            with [r_c1, r_c2, r_c3][idx]:
                render_metric_card(
                    titulo=fila_b["Bloque"],
                    valor=f"${fila_b['Monto_Real']:,.2f} ({fila_b['Porcentaje_Real']:.1f}%)",
                    subtitulo=f"Meta sugerida ({fila_b['Porcentaje_Meta']:.0f}%): ${fila_b['Monto_Ideal']:,.2f}",
                    variante=variantes_bloque[idx],
                    icono="📊",
                )

        fig_503020 = go.Figure()
        fig_503020.add_trace(
            go.Bar(
                name="Meta Ideal (50/30/20)",
                x=df_r50["Bloque"],
                y=df_r50["Monto_Ideal"],
                marker_color=PALETA["cian_brillante"],
                text=[f"${v:,.2f}" for v in df_r50["Monto_Ideal"]],
                textposition="auto",
            )
        )
        fig_503020.add_trace(
            go.Bar(
                name="Distribución Real Actual",
                x=df_r50["Bloque"],
                y=df_r50["Monto_Real"],
                marker_color=PALETA["verde_neon"],
                text=[f"${v:,.2f}" for v in df_r50["Monto_Real"]],
                textposition="auto",
            )
        )
        fig_503020.update_layout(barmode="group", yaxis_title="Monto ($)")
        st.plotly_chart(
            estilo_fig(fig_503020, "Comparativa Regla 50/30/20: Ideal vs Real", altura=370),
            use_container_width=True,
        )

    st.markdown("---")

    # 2. Diagrama de Pareto (80/20) de Categorías de Gasto
    st.subheader("📉 Diagrama de Pareto (80/20) de Categorías de Gasto")
    res_pareto = calcular_pareto_categorias(df_transacciones)

    if not res_pareto["tiene_datos"] or res_pareto["df_pareto"].empty:
        st.info(
            "📊 Registra gastos en diferentes categorías para generar el Diagrama de Pareto (80/20)."
        )
    else:
        df_par = res_pareto["df_pareto"]
        vitales_str = ", ".join(res_pareto["categorias_vitales"])
        render_alerta(
            mensaje=(
                f"Las categorías que concentran el **80% del impacto de tus gastos** son: "
                f"<strong>{vitales_str}</strong>. Optimizar estas categorías tendrá el mayor retorno en tu liquidez."
            ),
            tipo="info",
            titulo="Principio 80/20 Detectado",
        )

        fig_pareto = make_subplots(specs=[[{"secondary_y": True}]])
        fig_pareto.add_trace(
            go.Bar(
                name="Gasto por Categoría ($)",
                x=df_par["Categoria"],
                y=df_par["Monto"],
                marker_color=[
                    PALETA["verde_neon"] if g == "80% Impacto Vital" else PALETA["cian_brillante"]
                    for g in df_par["Grupo_Pareto"]
                ],
                text=[f"${m:,.0f}" for m in df_par["Monto"]],
                textposition="auto",
            ),
            secondary_y=False,
        )
        fig_pareto.add_trace(
            go.Scatter(
                name="% Acumulado",
                x=df_par["Categoria"],
                y=df_par["Porcentaje_Acumulado"],
                mode="lines+markers+text",
                text=[f"{p:.0f}%" for p in df_par["Porcentaje_Acumulado"]],
                textposition="top center",
                line=dict(color=PALETA["amarillo_alerta"], width=3),
            ),
            secondary_y=True,
        )
        # Línea de referencia del 80%
        fig_pareto.add_hline(
            y=80.0,
            line_dash="dash",
            line_color=PALETA["rojo_peligro"],
            annotation_text="Umbral 80% Pareto",
            secondary_y=True,
        )
        fig_pareto.update_yaxes(title_text="Monto Gastado ($)", secondary_y=False)
        fig_pareto.update_yaxes(title_text="Porcentaje Acumulado (%)", range=[0, 108], secondary_y=True)
        st.plotly_chart(
            estilo_fig(fig_pareto, "Curva de Pareto 80/20 sobre Categorías de Gasto", altura=410),
            use_container_width=True,
        )

    st.markdown("---")

    # 3. Directorio de Consejos de Ahorro y Optimización Financiera
    st.subheader("📚 Directorio de Consejos de Ahorro e Inteligencia Financiera")
    consejos = obtener_directorio_consejos()
    c_dir1, c_dir2 = st.columns(2)
    for i, item in enumerate(consejos):
        with (c_dir1 if i % 2 == 0 else c_dir2):
            st.markdown(
                f"""
                <div class="metric-card cyan">
                    <div class="metric-title">{item['categoria']}</div>
                    <div style="font-size:1.02rem; font-weight:700; color:#ffffff; margin-bottom:0.35rem;">
                        {item['titulo']}
                    </div>
                    <div class="metric-sub">{item['descripcion']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
