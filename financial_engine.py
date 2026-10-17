"""
financial_engine.py
-------------------
Motor de cálculo matemático, simulación financiera y reglas de negocio
para "Mis Finanzas v4.0".

Este módulo es completamente independiente de la capa visual (Streamlit UI),
recibiendo DataFrames/valores numéricos y retornando estructuras de datos
listas para ser graficadas o presentadas.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any

import pandas as pd

from database import PRIORIDAD_POR_DEFECTO


# ==============================================================================
# UTILIDADES DE FECHAS Y CORTES DE TARJETA
# ==============================================================================
NOMBRES_MESES_ES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio (Verano ☀️)",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre (Navidad 🎄)",
}


def _normalizar_fecha(fecha_actual: date | datetime | str | None = None) -> date:
    """Convierte cualquier entrada de fecha en un objeto `datetime.date` válido."""
    if fecha_actual is None:
        return datetime.now().date()
    if isinstance(fecha_actual, datetime):
        return fecha_actual.date()
    if isinstance(fecha_actual, date):
        return fecha_actual
    if isinstance(fecha_actual, str):
        try:
            return datetime.strptime(fecha_actual[:10], "%Y-%m-%d").date()
        except ValueError:
            return datetime.now().date()
    return datetime.now().date()


def _construir_fecha_segura(anio: int, mes: int, dia_deseado: int) -> date:
    """
    Construye una fecha ajustando el día al máximo permitido del mes
    (por ejemplo, día 31 en febrero se ajusta al 28 o 29).
    """
    ultimo_dia_mes = calendar.monthrange(anio, mes)[1]
    dia_real = max(1, min(int(dia_deseado), ultimo_dia_mes))
    return date(anio, mes, dia_real)


def _sumar_meses(fecha_base: date, meses: int) -> tuple[int, int]:
    """Devuelve la tupla `(anio, mes)` resultante de sumar `meses` a `fecha_base`."""
    indice_mes = (fecha_base.month - 1) + meses
    anio = fecha_base.year + (indice_mes // 12)
    mes = (indice_mes % 12) + 1
    return anio, mes


def calcular_ciclo_tarjeta(
    dia_corte: int,
    dia_pago: int,
    fecha_actual: date | datetime | str | None = None,
) -> dict[str, Any]:
    """
    Calcula las fechas exactas del último corte, próximo corte, fecha límite de pago
    y la ventana real de financiamiento sin intereses si se compra hoy.
    """
    hoy = _normalizar_fecha(fecha_actual)
    dia_corte = max(1, min(31, int(dia_corte or 1)))
    dia_pago = max(1, min(31, int(dia_pago or 15)))

    corte_este_mes = _construir_fecha_segura(hoy.year, hoy.month, dia_corte)

    if hoy >= corte_este_mes:
        ultimo_corte = corte_este_mes
        anio_sig, mes_sig = _sumar_meses(hoy, 1)
        proximo_corte = _construir_fecha_segura(anio_sig, mes_sig, dia_corte)
    else:
        anio_ant, mes_ant = _sumar_meses(hoy, -1)
        ultimo_corte = _construir_fecha_segura(anio_ant, mes_ant, dia_corte)
        proximo_corte = corte_este_mes

    dias_desde_corte = (hoy - ultimo_corte).days
    dias_para_corte = (proximo_corte - hoy).days

    # Calcular próxima fecha límite de pago del estado de cuenta actual
    pago_este_mes = _construir_fecha_segura(hoy.year, hoy.month, dia_pago)
    if pago_este_mes >= hoy:
        proximo_pago = pago_este_mes
    else:
        anio_p, mes_p = _sumar_meses(hoy, 1)
        proximo_pago = _construir_fecha_segura(anio_p, mes_p, dia_pago)

    dias_para_pago = (proximo_pago - hoy).days

    # Ventana de financiamiento para compras realizadas HOY:
    # Si hoy ya pasó el corte (1 a 5 días post-corte), la compra entra en el siguiente corte
    # y se paga ~20 días después de ese próximo corte (40 a 50 días totales).
    if dias_desde_corte == 0:
        # Día exacto de corte: la compra puede entrar hoy mismo y pagarse en ~20 días
        dias_financiamiento = 20
    else:
        dias_financiamiento = dias_para_corte + 20

    en_ventana_dorada = 1 <= dias_desde_corte <= 5

    return {
        "ultimo_corte": ultimo_corte,
        "proximo_corte": proximo_corte,
        "proximo_pago": proximo_pago,
        "dias_desde_corte": dias_desde_corte,
        "dias_para_corte": dias_para_corte,
        "dias_para_pago": dias_para_pago,
        "dias_financiamiento": dias_financiamiento,
        "en_ventana_dorada": en_ventana_dorada,
    }


# ==============================================================================
# 1. CÁLCULO DE LIQUIDEZ LIBRE DEL MES ACTUAL
# ==============================================================================
def _extraer_monto_total(origen: float | int | pd.DataFrame | pd.Series | None, tipo_filtro: str | None = None) -> float:
    """
    Permite que `calcular_liquidez_libre` reciba tanto montos flotantes directos
    como un DataFrame de transacciones o una Serie de Pandas.
    """
    if origen is None:
        return 0.0
    if isinstance(origen, (int, float)):
        return float(origen)
    if isinstance(origen, pd.Series):
        return float(pd.to_numeric(origen, errors="coerce").fillna(0.0).sum())
    if isinstance(origen, pd.DataFrame):
        if origen.empty or "Monto" not in origen.columns:
            return 0.0
        df_temp = origen
        if tipo_filtro and "Tipo" in df_temp.columns:
            df_temp = df_temp[df_temp["Tipo"].astype(str).str.lower() == tipo_filtro.lower()]
        return float(pd.to_numeric(df_temp["Monto"], errors="coerce").fillna(0.0).sum())
    return 0.0


def calcular_liquidez_libre(
    ingresos: float | int | pd.DataFrame,
    gastos: float | int | pd.DataFrame,
    compromisos_fijos: pd.DataFrame | float | int | None,
) -> dict[str, Any]:
    """
    Calcula el saldo disponible real (liquidez libre) descontando los gastos ya
    efectuados y los compromisos fijos pendientes de pago en el mes actual.

    Fórmula:
        Saldo Contable = Ingresos - Gastos
        Liquidez Libre = Saldo Contable - Compromisos Fijos Pendientes ('No' pagados)

    Retorna:
        dict con el desglose matemático y nivel de solvencia.
    """
    total_ingresos = _extraer_monto_total(ingresos, tipo_filtro="Ingreso")
    total_gastos = _extraer_monto_total(gastos, tipo_filtro="Gasto")

    compromisos_pendientes = 0.0
    compromisos_pagados = 0.0
    compromisos_totales = 0.0
    cantidad_pendientes = 0

    if isinstance(compromisos_fijos, (int, float)):
        compromisos_pendientes = float(compromisos_fijos)
        compromisos_totales = float(compromisos_fijos)
    elif isinstance(compromisos_fijos, pd.DataFrame) and not compromisos_fijos.empty:
        df_comp = compromisos_fijos.copy()
        montos = pd.to_numeric(df_comp.get("Monto_Estimado", 0.0), errors="coerce").fillna(0.0)
        estados = (
            df_comp.get("Pagado_Mes_Actual", pd.Series(["No"] * len(df_comp)))
            .astype(str)
            .str.strip()
            .str.lower()
        )
        mascara_pagado = estados.isin({"sí", "si", "true", "1", "pagado"})
        compromisos_pagados = float(montos[mascara_pagado].sum())
        compromisos_pendientes = float(montos[~mascara_pagado].sum())
        compromisos_totales = compromisos_pagados + compromisos_pendientes
        cantidad_pendientes = int((~mascara_pagado).sum())

    saldo_contable = total_ingresos - total_gastos
    liquidez_libre = saldo_contable - compromisos_pendientes

    # Porcentaje del ingreso que sigue disponible libremente
    if total_ingresos > 0:
        pct_liquidez = (liquidez_libre / total_ingresos) * 100.0
    else:
        pct_liquidez = 0.0 if liquidez_libre <= 0 else 100.0

    if liquidez_libre < 0:
        estado = "Déficit de Liquidez"
        nivel = "danger"
    elif liquidez_libre < (compromisos_pendientes * 0.25) or pct_liquidez < 15.0:
        estado = "Liquidez Ajustada"
        nivel = "warning"
    else:
        estado = "Liquidez Saludable"
        nivel = "success"

    return {
        "ingresos_totales": round(total_ingresos, 2),
        "gastos_totales": round(total_gastos, 2),
        "saldo_contable": round(saldo_contable, 2),
        "compromisos_pendientes": round(compromisos_pendientes, 2),
        "compromisos_pagados": round(compromisos_pagados, 2),
        "compromisos_totales": round(compromisos_totales, 2),
        "cantidad_pendientes": cantidad_pendientes,
        "liquidez_libre": round(liquidez_libre, 2),
        "pct_liquidez": round(pct_liquidez, 1),
        "estado": estado,
        "nivel": nivel,
    }


# ==============================================================================
# 2. RECOMENDADOR DE TARJETA ÓPTIMA DEL DÍA
# ==============================================================================
def recomendar_tarjeta_del_dia(
    tarjetas: pd.DataFrame,
    fecha_actual: date | datetime | str | None = None,
) -> dict[str, Any]:
    """
    Evalúa los días transcurridos desde el último corte de cada tarjeta y su
    porcentaje de Cashback para recomendar la mejor tarjeta para comprar hoy.

    Regla de prioridad máxima:
    - Tarjetas que se encuentran entre 1 y 5 días posteriores a su fecha de corte
      (ofrecen la ventana máxima de financiamiento sin intereses: entre 40 y 50 días)
      combinado con su porcentaje de Cashback y crédito disponible.
    """
    hoy = _normalizar_fecha(fecha_actual)

    if tarjetas is None or tarjetas.empty:
        return {
            "disponible": False,
            "mejor_tarjeta": None,
            "ranking": pd.DataFrame(),
            "mensaje": "No hay tarjetas registradas. Agrega una en la pestaña 'Tarjetas y Compromisos Fijos'.",
        }

    evaluaciones: list[dict[str, Any]] = []

    for _, fila in tarjetas.iterrows():
        nombre = str(fila.get("Nombre", "Tarjeta")).strip()
        limite = float(fila.get("Limite_Credito", 0.0) or 0.0)
        saldo = float(fila.get("Saldo_Actual", 0.0) or 0.0)
        credito_disponible = max(0.0, limite - saldo)
        pct_uso = (saldo / limite * 100.0) if limite > 0 else 100.0

        dia_corte = int(fila.get("Dia_Corte", 1) or 1)
        dia_pago = int(fila.get("Dia_Pago", 15) or 15)
        tasa_anual = float(fila.get("Tasa_Interes_Anual", 0.0) or 0.0)
        cashback = float(fila.get("Cashback_Pct", 0.0) or 0.0)
        promociones = str(fila.get("Puntos_Promociones", "")).strip()
        pago_no_intereses = float(fila.get("Pago_Para_No_Generar_Intereses", 0.0) or 0.0)
        pago_minimo = float(fila.get("Pago_Minimo", 0.0) or 0.0)
        comision_impago = float(fila.get("Comision_Impago", 0.0) or 0.0)

        ciclo = calcular_ciclo_tarjeta(dia_corte, dia_pago, hoy)
        dias_desde_corte = ciclo["dias_desde_corte"]
        dias_financiamiento = ciclo["dias_financiamiento"]
        en_ventana_dorada = ciclo["en_ventana_dorada"]

        # Cálculo de puntaje compuesto (Ventana post-corte + Cashback + Disponibilidad)
        if en_ventana_dorada:
            # Prioridad máxima: 1 a 5 días después del corte (40 a 50 días para pagar)
            puntaje_base = 100.0 + (6 - dias_desde_corte) * 5.0
            etiqueta_ventana = "🔥 Ventana Dorada (1-5 días post-corte)"
            semaforo_corte = "verde"
        elif 6 <= dias_desde_corte <= 14:
            puntaje_base = 70.0 + (15 - dias_desde_corte) * 1.8
            etiqueta_ventana = "✅ Buena ventana de financiamiento"
            semaforo_corte = "verde"
        elif 15 <= dias_desde_corte <= 23:
            puntaje_base = 42.0 + (24 - dias_desde_corte) * 1.2
            etiqueta_ventana = "⏳ Ventana media (corte acercándose)"
            semaforo_corte = "amarillo"
        else:
            # Mismo día de corte (0) o a pocos días del próximo corte (>23 días)
            puntaje_base = 15.0 + max(0, 30 - dias_desde_corte) * 0.5
            etiqueta_ventana = "⚠️ Próxima a cortar (menor plazo)"
            semaforo_corte = "rojo"

        # Bonificación por Cashback (peso relevante para desempatar y premiar recompensas)
        bono_cashback = cashback * 12.0

        # Penalización si la utilización de línea de crédito es muy alta (>80%) o sin saldo disponible
        penalizacion_uso = 0.0
        if credito_disponible <= 0:
            penalizacion_uso = 200.0
        elif pct_uso >= 80.0:
            penalizacion_uso = 20.0

        puntaje_total = round(puntaje_base + bono_cashback - penalizacion_uso, 2)

        # Semáforo de pago próximo
        dias_para_pago = ciclo["dias_para_pago"]
        if dias_para_pago <= 3 and saldo > 0:
            semaforo_pago = "rojo"
        elif dias_para_pago <= 7 and saldo > 0:
            semaforo_pago = "amarillo"
        else:
            semaforo_pago = "verde"

        motivo = (
            f"Cortó hace {dias_desde_corte} día(s) (día {dia_corte}). "
            f"Te otorga ~{dias_financiamiento} días sin intereses y {cashback:.1f}% de Cashback."
        )

        evaluaciones.append(
            {
                "ID": str(fila.get("ID", "")),
                "Nombre": nombre,
                "Dia_Corte": dia_corte,
                "Dia_Pago": dia_pago,
                "Dias_Desde_Corte": dias_desde_corte,
                "Dias_Para_Corte": ciclo["dias_para_corte"],
                "Dias_Para_Pago": dias_para_pago,
                "Dias_Financiamiento": dias_financiamiento,
                "En_Ventana_Dorada": en_ventana_dorada,
                "Etiqueta_Ventana": etiqueta_ventana,
                "Cashback_Pct": cashback,
                "Tasa_Interes_Anual": tasa_anual,
                "Limite_Credito": limite,
                "Saldo_Actual": saldo,
                "Credito_Disponible": round(credito_disponible, 2),
                "Pct_Uso": round(pct_uso, 1),
                "Puntos_Promociones": promociones,
                "Pago_Para_No_Generar_Intereses": pago_no_intereses,
                "Pago_Minimo": pago_minimo,
                "Comision_Impago": comision_impago,
                "Semaforo_Corte": semaforo_corte,
                "Semaforo_Pago": semaforo_pago,
                "Puntaje": puntaje_total,
                "Motivo": motivo,
            }
        )

    df_ranking = pd.DataFrame(evaluaciones).sort_values(
        by=["Puntaje", "Cashback_Pct", "Dias_Financiamiento"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    mejor = df_ranking.iloc[0].to_dict()

    return {
        "disponible": True,
        "mejor_tarjeta": mejor,
        "ranking": df_ranking,
        "mensaje": mejor["Motivo"],
    }


# ==============================================================================
# 3. SIMULADOR DE DECISIONES DE COMPRA (DIAGNÓSTICO EN 4 DIMENSIONES)
# ==============================================================================
def simular_compra(
    monto: float,
    categoria: str,
    tarjetas: pd.DataFrame,
    compromisos: pd.DataFrame,
    presupuestos: pd.DataFrame,
    diferir_meses: int = 1,
    no_podra_liquidar: bool = False,
    transacciones: pd.DataFrame | None = None,
    fecha_actual: date | datetime | str | None = None,
) -> dict[str, Any]:
    """
    Evalúa el impacto financiero de una compra potencial en 4 dimensiones:
    1) % consumido del presupuesto mensual de esa categoría.
    2) Impacto en la liquidez libre para pagar servicios obligatorios del mes.
    3) Proyección de flujo de efectivo a 3-6 meses protegiendo temporadas altas
       (julio/verano y diciembre/navidad).
    4) Recomendación de tarjeta óptima: si no podrá liquidar a tiempo, calcula el
       interés mensual con IVA `Monto * (Tasa Anual / 12) * 1.16` y compara el
       costo financiero entre todas las tarjetas registradas.
    """
    hoy = _normalizar_fecha(fecha_actual)
    monto = max(0.0, float(monto or 0.0))
    plazo = max(1, int(diferir_meses or 1))
    cargo_mensual_compra = round(monto / plazo, 2)
    mes_actual_str = hoy.strftime("%Y-%m")

    # Extraer ingresos y gastos del mes actual desde `transacciones` si se provee
    ingresos_mes = 0.0
    gastos_mes = 0.0
    gasto_actual_categoria = 0.0

    if transacciones is not None and not transacciones.empty:
        df_trx = transacciones.copy()
        df_trx["Fecha_Str"] = df_trx["Fecha"].astype(str).str[:7]
        df_mes = df_trx[df_trx["Fecha_Str"] == mes_actual_str]
        if df_mes.empty:
            # Si no hay movimientos del mes en curso, usar el total histórico como referencia
            df_mes = df_trx

        ingresos_mes = _extraer_monto_total(df_mes, tipo_filtro="Ingreso")
        gastos_mes = _extraer_monto_total(df_mes, tipo_filtro="Gasto")

        col_cat = "Categoria" if "Categoria" in df_mes.columns else "Categoría"
        if col_cat in df_mes.columns:
            mascara_cat = (
                (df_mes["Tipo"].astype(str).str.lower() == "gasto")
                & (df_mes[col_cat].astype(str).str.lower() == str(categoria).strip().lower())
            )
            gasto_actual_categoria = float(
                pd.to_numeric(df_mes.loc[mascara_cat, "Monto"], errors="coerce").fillna(0.0).sum()
            )

    # --------------------------------------------------------------------------
    # DIMENSIÓN 1: % CONSUMIDO DEL PRESUPUESTO DE LA CATEGORÍA
    # --------------------------------------------------------------------------
    limite_categoria = 0.0
    prioridad_categoria = PRIORIDAD_POR_DEFECTO.get(categoria, "Deseo")

    if presupuestos is not None and not presupuestos.empty:
        coincidencia_pres = presupuestos[
            presupuestos["Categoria"].astype(str).str.lower() == str(categoria).strip().lower()
        ]
        if not coincidencia_pres.empty:
            limite_categoria = float(coincidencia_pres.iloc[0]["Monto_Limite_Mensual"] or 0.0)
            prioridad_categoria = str(coincidencia_pres.iloc[0].get("Prioridad", prioridad_categoria))

    nuevo_gasto_categoria = gasto_actual_categoria + cargo_mensual_compra

    if limite_categoria > 0:
        pct_antes = round((gasto_actual_categoria / limite_categoria) * 100.0, 1)
        pct_despues = round((nuevo_gasto_categoria / limite_categoria) * 100.0, 1)
        excede_presupuesto = nuevo_gasto_categoria > limite_categoria
        if pct_despues > 100:
            estado_presupuesto = "Excedido"
            nivel_presupuesto = "danger"
            mensaje_presupuesto = (
                f"La mensualidad de ${cargo_mensual_compra:,.2f} eleva el gasto de '{categoria}' "
                f"al {pct_despues:.1f}% de su presupuesto (${limite_categoria:,.2f})."
            )
        elif pct_despues >= 80:
            estado_presupuesto = "En Límite (>80%)"
            nivel_presupuesto = "warning"
            mensaje_presupuesto = (
                f"Consumirás el {pct_despues:.1f}% del presupuesto asignado a '{categoria}' "
                f"(${nuevo_gasto_categoria:,.2f} de ${limite_categoria:,.2f})."
            )
        else:
            estado_presupuesto = "Dentro de Presupuesto"
            nivel_presupuesto = "success"
            mensaje_presupuesto = (
                f"El gasto en '{categoria}' quedará en {pct_despues:.1f}% del límite mensual "
                f"(${nuevo_gasto_categoria:,.2f} / ${limite_categoria:,.2f})."
            )
    else:
        pct_antes = 0.0
        pct_despues = 0.0
        excede_presupuesto = False
        estado_presupuesto = "Sin Presupuesto Definido"
        nivel_presupuesto = "info"
        mensaje_presupuesto = (
            f"No has fijado un presupuesto mensual para '{categoria}'. "
            f"El impacto mensual estimado será de ${cargo_mensual_compra:,.2f}."
        )

    dimension_presupuesto = {
        "categoria": categoria,
        "prioridad": prioridad_categoria,
        "limite_mensual": round(limite_categoria, 2),
        "gasto_actual": round(gasto_actual_categoria, 2),
        "cargo_mensual_compra": cargo_mensual_compra,
        "nuevo_gasto_categoria": round(nuevo_gasto_categoria, 2),
        "pct_antes": pct_antes,
        "pct_despues": pct_despues,
        "excede_presupuesto": excede_presupuesto,
        "estado": estado_presupuesto,
        "nivel": nivel_presupuesto,
        "mensaje": mensaje_presupuesto,
    }

    # --------------------------------------------------------------------------
    # DIMENSIÓN 2: IMPACTO EN LA LIQUIDEZ Y SERVICIOS OBLIGATORIOS DEL MES
    # --------------------------------------------------------------------------
    info_liquidez = calcular_liquidez_libre(ingresos_mes, gastos_mes, compromisos)
    liquidez_antes = info_liquidez["liquidez_libre"]
    compromisos_pendientes = info_liquidez["compromisos_pendientes"]
    compromisos_totales = info_liquidez["compromisos_totales"]
    liquidez_despues = round(liquidez_antes - cargo_mensual_compra, 2)

    # Verificar si pone en riesgo el pago de servicios básicos pendientes (Luz, Agua, Internet, Renta)
    compromete_servicios = liquidez_despues < 0
    colchon_restante = liquidez_despues

    if ingresos_mes == 0 and gastos_mes == 0:
        # Si aún no hay transacciones registradas, evaluar contra compromisos fijos
        nivel_liquidez = "warning"
        mensaje_liquidez = (
            f"Tienes ${compromisos_pendientes:,.2f} en compromisos fijos pendientes este mes. "
            f"Registra tus ingresos para calcular tu liquidez neta exacta tras descontar ${cargo_mensual_compra:,.2f}."
        )
    elif compromete_servicios:
        nivel_liquidez = "danger"
        faltante = abs(liquidez_despues)
        mensaje_liquidez = (
            f"¡Alerta de Solvencia! Realizar esta compra compromete el pago de tus servicios obligatorios "
            f"pendientes (${compromisos_pendientes:,.2f}), generando un déficit de ${faltante:,.2f}."
        )
    elif liquidez_despues < (compromisos_totales * 0.25):
        nivel_liquidez = "warning"
        mensaje_liquidez = (
            f"Podrás cubrir tus servicios pendientes (${compromisos_pendientes:,.2f}), pero tu liquidez "
            f"libre bajará a sólo ${liquidez_despues:,.2f} para imprevistos del mes."
        )
    else:
        nivel_liquidez = "success"
        mensaje_liquidez = (
            f"Solvencia confirmada: tras reservar ${compromisos_pendientes:,.2f} de servicios pendientes "
            f"y ${cargo_mensual_compra:,.2f} de esta compra, conservas ${liquidez_despues:,.2f} libres."
        )

    dimension_liquidez = {
        "liquidez_antes": liquidez_antes,
        "liquidez_despues": liquidez_despues,
        "compromisos_pendientes": compromisos_pendientes,
        "compromisos_totales": compromisos_totales,
        "cargo_mensual": cargo_mensual_compra,
        "compromete_servicios": compromete_servicios,
        "colchon_restante": colchon_restante,
        "nivel": nivel_liquidez,
        "mensaje": mensaje_liquidez,
    }

    # --------------------------------------------------------------------------
    # DIMENSIÓN 3: PROYECCIÓN DE FLUJO A 3-6 MESES (PROTECCIÓN JULIO Y DICIEMBRE)
    # --------------------------------------------------------------------------
    horizonte_meses = max(6, min(12, plazo))
    base_ingreso_proyectado = ingresos_mes if ingresos_mes > 0 else max(compromisos_totales * 1.8, 15000.0)
    base_gasto_fijo = compromisos_totales if compromisos_totales > 0 else gastos_mes * 0.5

    filas_proyeccion: list[dict[str, Any]] = []
    toca_julio = False
    toca_diciembre = False
    meses_criticos: list[str] = []

    for i in range(horizonte_meses):
        anio_p, mes_p = _sumar_meses(hoy, i)
        nombre_mes = f"{NOMBRES_MESES_ES[mes_p]} {anio_p}"
        es_temporada_alta = mes_p in {7, 12}

        # Reserva de protección estacional (+25% sobre compromisos en Julio/Verano y Diciembre/Navidad)
        reserva_estacional = round(base_gasto_fijo * 0.25, 2) if es_temporada_alta else 0.0
        cuota_compra_mes = cargo_mensual_compra if i < plazo else 0.0

        if i < plazo and mes_p == 7:
            toca_julio = True
        if i < plazo and mes_p == 12:
            toca_diciembre = True

        flujo_comprometido = round(base_gasto_fijo + reserva_estacional + cuota_compra_mes, 2)
        flujo_libre_estimado = round(base_ingreso_proyectado - flujo_comprometido, 2)

        if es_temporada_alta and cuota_compra_mes > 0 and flujo_libre_estimado < (base_ingreso_proyectado * 0.15):
            meses_criticos.append(nombre_mes)

        filas_proyeccion.append(
            {
                "Mes_Indice": i + 1,
                "Anio": anio_p,
                "Mes_Numero": mes_p,
                "Periodo": nombre_mes,
                "Temporada_Alta": "Sí (Reserva Activa)" if es_temporada_alta else "Normal",
                "Compromisos_Base": round(base_gasto_fijo, 2),
                "Reserva_Temporada_Alta": reserva_estacional,
                "Cuota_Nueva_Compra": cuota_compra_mes,
                "Flujo_Libre_Proyectado": flujo_libre_estimado,
            }
        )

    df_proyeccion = pd.DataFrame(filas_proyeccion)

    if toca_julio or toca_diciembre:
        temporadas_tocadas = []
        if toca_julio:
            temporadas_tocadas.append("Julio (Verano ☀️)")
        if toca_diciembre:
            temporadas_tocadas.append("Diciembre (Navidad 🎄)")
        lista_temp = " y ".join(temporadas_tocadas)
        nivel_proyeccion = "warning" if not meses_criticos else "danger"
        mensaje_proyeccion = (
            f"Atención Estacional: El plazo de {plazo} mes(es) traslapa con {lista_temp}. "
            f"Se incluyó una reserva preventiva del +25% en gastos fijos durante esos meses para proteger tu flujo."
        )
    else:
        nivel_proyeccion = "success"
        mensaje_proyeccion = (
            f"El horizonte de pago de {plazo} mes(es) no compromete las temporadas críticas "
            f"de Julio (Verano) ni Diciembre (Navidad)."
        )

    dimension_proyeccion = {
        "horizonte_meses": horizonte_meses,
        "toca_julio": toca_julio,
        "toca_diciembre": toca_diciembre,
        "meses_criticos": meses_criticos,
        "df_proyeccion": df_proyeccion,
        "nivel": nivel_proyeccion,
        "mensaje": mensaje_proyeccion,
    }

    # --------------------------------------------------------------------------
    # DIMENSIÓN 4: RECOMENDACIÓN DE TARJETA Y CÁLCULO DE INTERESES + IVA (1.16)
    # Fórmula obligatoria: Interés Mensual = Monto * (Tasa Anual / 12) * 1.16
    # --------------------------------------------------------------------------
    filas_comparativa: list[dict[str, Any]] = []
    tarjeta_optima: dict[str, Any] | None = None

    if tarjetas is not None and not tarjetas.empty:
        rec_hoy = recomendar_tarjeta_del_dia(tarjetas, hoy)
        df_rank = rec_hoy["ranking"]

        for _, t in df_rank.iterrows():
            tasa_anual_pct = float(t["Tasa_Interes_Anual"] or 0.0)
            tasa_anual_dec = tasa_anual_pct / 100.0
            cashback_pct = float(t["Cashback_Pct"] or 0.0)
            comision_impago = float(t["Comision_Impago"] or 0.0)
            credito_disp = float(t["Credito_Disponible"] or 0.0)

            # Fórmula exacta solicitada: Monto * (Tasa Anual / 12) * 1.16 IVA
            interes_mensual_iva = round(monto * (tasa_anual_dec / 12.0) * 1.16, 2)
            interes_total_plazo = round(interes_mensual_iva * plazo, 2)
            recompensa_cashback = round(monto * (cashback_pct / 100.0), 2)

            # Costo neto si no puede liquidar vs si paga a tiempo
            costo_total_con_intereses = round(monto + interes_total_plazo, 2)
            costo_caso_impago_extremo = round(monto + interes_total_plazo + comision_impago, 2)

            filas_comparativa.append(
                {
                    "Nombre": t["Nombre"],
                    "Tasa_Interes_Anual": tasa_anual_pct,
                    "Interes_Mensual_Con_IVA": interes_mensual_iva,
                    "Interes_Total_Plazo": interes_total_plazo,
                    "Comision_Impago": comision_impago,
                    "Cashback_Pct": cashback_pct,
                    "Cashback_Monto": recompensa_cashback,
                    "Costo_Total_Financiado": costo_total_con_intereses,
                    "Costo_Con_Comision_Impago": costo_caso_impago_extremo,
                    "Dias_Financiamiento": int(t["Dias_Financiamiento"]),
                    "En_Ventana_Dorada": bool(t["En_Ventana_Dorada"]),
                    "Credito_Disponible": credito_disp,
                    "Alcanza_Linea": credito_disp >= monto,
                    "Puntaje_Uso_Hoy": float(t["Puntaje"]),
                }
            )

        df_comparativa = pd.DataFrame(filas_comparativa)

        # Filtrar primero las tarjetas que tienen línea disponible suficiente para la compra
        df_viables = df_comparativa[df_comparativa["Alcanza_Linea"]].copy()
        if df_viables.empty:
            df_viables = df_comparativa.copy()

        if no_podra_liquidar:
            # Si no podrá liquidar, ordenar por menor interés mensual con IVA (menor tasa anual)
            df_viables = df_viables.sort_values(
                by=["Interes_Mensual_Con_IVA", "Comision_Impago"],
                ascending=[True, True],
            ).reset_index(drop=True)
            tarjeta_optima = df_viables.iloc[0].to_dict()
            peor_tarjeta = df_viables.iloc[-1].to_dict()
            ahorro_intereses = round(
                peor_tarjeta["Interes_Total_Plazo"] - tarjeta_optima["Interes_Total_Plazo"], 2
            )
            mensaje_tarjeta = (
                f"Dado que simularás financiamiento con intereses, la tarjeta menos costosa es "
                f"**{tarjeta_optima['Nombre']}** (Tasa {tarjeta_optima['Tasa_Interes_Anual']:.1f}% anual), "
                f"generando ${tarjeta_optima['Interes_Mensual_Con_IVA']:,.2f}/mes de interés + IVA "
                f"(${tarjeta_optima['Interes_Total_Plazo']:,.2f} en {plazo} mes(es)). "
                f"Te ahorras ${ahorro_intereses:,.2f} frente a la tarjeta más cara."
            )
            nivel_tarjeta = "warning"
        else:
            # Si liquidará a tiempo (totalero o MSI), elegir por mayor ventana post-corte + cashback
            df_viables = df_viables.sort_values(
                by=["Puntaje_Uso_Hoy", "Cashback_Monto"],
                ascending=[False, False],
            ).reset_index(drop=True)
            tarjeta_optima = df_viables.iloc[0].to_dict()
            mensaje_tarjeta = (
                f"Para compra sin intereses, usa **{tarjeta_optima['Nombre']}**: te brinda "
                f"~{tarjeta_optima['Dias_Financiamiento']} días de financiamiento y recuperas "
                f"${tarjeta_optima['Cashback_Monto']:,.2f} en Cashback ({tarjeta_optima['Cashback_Pct']:.1f}%)."
            )
            nivel_tarjeta = "success"
    else:
        df_comparativa = pd.DataFrame()
        mensaje_tarjeta = "No hay tarjetas registradas para comparar tasas de interés ni Cashback."
        nivel_tarjeta = "info"

    dimension_tarjeta = {
        "no_podra_liquidar": no_podra_liquidar,
        "tarjeta_optima": tarjeta_optima,
        "df_comparativa": df_comparativa,
        "nivel": nivel_tarjeta,
        "mensaje": mensaje_tarjeta,
    }

    # Veredicto global consolidado del simulador
    if compromete_servicios or (excede_presupuesto and no_podra_liquidar):
        veredicto = "Compra No Recomendada Hoy 🚨"
        nivel_global = "danger"
    elif excede_presupuesto or no_podra_liquidar or toca_julio or toca_diciembre:
        veredicto = "Compra Viable con Precaución ⚠️"
        nivel_global = "warning"
    else:
        veredicto = "Compra Saludable y Viable ✅"
        nivel_global = "success"

    return {
        "veredicto": veredicto,
        "nivel_global": nivel_global,
        "monto": monto,
        "plazo": plazo,
        "cargo_mensual": cargo_mensual_compra,
        "dimension_1_presupuesto": dimension_presupuesto,
        "dimension_2_liquidez": dimension_liquidez,
        "dimension_3_proyeccion": dimension_proyeccion,
        "dimension_4_tarjeta": dimension_tarjeta,
    }


# ==============================================================================
# 4. ASESOR FINANCIERO: REGLA 50/30/20 Y DIAGRAMA DE PARETO (80/20)
# ==============================================================================
def calcular_regla_50_30_20(
    transacciones: pd.DataFrame,
    presupuestos: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Evalúa la distribución de ingresos y gastos bajo la metodología 50/30/20:
    - 50% Necesidades básicas (Vivienda, Supermercado, Servicios, Transporte, Salud, etc.)
    - 30% Deseos y estilo de vida (Restaurantes, Ocio, Suscripciones, Compras, etc.)
    - 20% Ahorro, inversión o pago acelerado de deuda.
    """
    if transacciones is None or transacciones.empty:
        return {
            "tiene_datos": False,
            "ingresos": 0.0,
            "df_resumen": pd.DataFrame(),
            "mensaje": "Registra ingresos y gastos para visualizar tu diagnóstico de la Regla 50/30/20.",
        }

    # Mapa de prioridad por categoría (combinando catálogo base y presupuestos personalizados)
    mapa_prioridad = {k.lower(): v for k, v in PRIORIDAD_POR_DEFECTO.items()}
    if presupuestos is not None and not presupuestos.empty:
        for _, fila in presupuestos.iterrows():
            cat_k = str(fila.get("Categoria", "")).strip().lower()
            prio_v = str(fila.get("Prioridad", "Necesidad")).strip()
            if cat_k:
                mapa_prioridad[cat_k] = prio_v

    ingresos_totales = _extraer_monto_total(transacciones, tipo_filtro="Ingreso")
    df_gastos = transacciones[transacciones["Tipo"].astype(str).str.lower() == "gasto"].copy()

    gasto_necesidades = 0.0
    gasto_deseos = 0.0
    gasto_ahorro_explicito = 0.0

    if not df_gastos.empty:
        col_cat = "Categoria" if "Categoria" in df_gastos.columns else "Categoría"
        for _, fila in df_gastos.iterrows():
            cat = str(fila.get(col_cat, "Otros Gastos")).strip().lower()
            monto = float(fila.get("Monto", 0.0) or 0.0)
            clasificacion = mapa_prioridad.get(cat, "Deseo")
            if clasificacion == "Necesidad":
                gasto_necesidades += monto
            elif clasificacion == "Ahorro":
                gasto_ahorro_explicito += monto
            else:
                gasto_deseos += monto

    total_gastos_consumo = gasto_necesidades + gasto_deseos
    # El ahorro real incluye lo destinado a 'Ahorro e Inversión' más el excedente no gastado del ingreso
    remanente_no_gastado = max(0.0, ingresos_totales - total_gastos_consumo - gasto_ahorro_explicito)
    ahorro_total_efectivo = gasto_ahorro_explicito + remanente_no_gastado

    base_referencia = ingresos_totales if ingresos_totales > 0 else max(1.0, total_gastos_consumo + gasto_ahorro_explicito)

    ideal_necesidades = round(base_referencia * 0.50, 2)
    ideal_deseos = round(base_referencia * 0.30, 2)
    ideal_ahorro = round(base_referencia * 0.20, 2)

    df_resumen = pd.DataFrame(
        [
            {
                "Bloque": "50% Necesidades",
                "Clave": "Necesidad",
                "Porcentaje_Meta": 50.0,
                "Monto_Ideal": ideal_necesidades,
                "Monto_Real": round(gasto_necesidades, 2),
                "Porcentaje_Real": round((gasto_necesidades / base_referencia) * 100.0, 1),
                "Diferencia": round(ideal_necesidades - gasto_necesidades, 2),
            },
            {
                "Bloque": "30% Deseos y Ocio",
                "Clave": "Deseo",
                "Porcentaje_Meta": 30.0,
                "Monto_Ideal": ideal_deseos,
                "Monto_Real": round(gasto_deseos, 2),
                "Porcentaje_Real": round((gasto_deseos / base_referencia) * 100.0, 1),
                "Diferencia": round(ideal_deseos - gasto_deseos, 2),
            },
            {
                "Bloque": "20% Ahorro e Inversión",
                "Clave": "Ahorro",
                "Porcentaje_Meta": 20.0,
                "Monto_Ideal": ideal_ahorro,
                "Monto_Real": round(ahorro_total_efectivo, 2),
                "Porcentaje_Real": round((ahorro_total_efectivo / base_referencia) * 100.0, 1),
                "Diferencia": round(ahorro_total_efectivo - ideal_ahorro, 2),
            },
        ]
    )

    return {
        "tiene_datos": True,
        "ingresos": round(ingresos_totales, 2),
        "base_referencia": round(base_referencia, 2),
        "gasto_necesidades": round(gasto_necesidades, 2),
        "gasto_deseos": round(gasto_deseos, 2),
        "ahorro_efectivo": round(ahorro_total_efectivo, 2),
        "df_resumen": df_resumen,
    }


def calcular_pareto_categorias(transacciones: pd.DataFrame) -> dict[str, Any]:
    """
    Construye el análisis de Pareto (80/20) sobre las categorías de gasto para
    identificar el ~20% de las categorías que concentran el ~80% de las salidas de dinero.
    """
    if transacciones is None or transacciones.empty:
        return {
            "tiene_datos": False,
            "df_pareto": pd.DataFrame(),
            "categorias_vitales": [],
        }

    df_gastos = transacciones[transacciones["Tipo"].astype(str).str.lower() == "gasto"].copy()
    if df_gastos.empty:
        return {
            "tiene_datos": False,
            "df_pareto": pd.DataFrame(),
            "categorias_vitales": [],
        }

    col_cat = "Categoria" if "Categoria" in df_gastos.columns else "Categoría"
    df_gastos["Monto"] = pd.to_numeric(df_gastos["Monto"], errors="coerce").fillna(0.0)

    agrupado = (
        df_gastos.groupby(col_cat, as_index=False)["Monto"]
        .sum()
        .rename(columns={col_cat: "Categoria"})
        .sort_values(by="Monto", ascending=False)
        .reset_index(drop=True)
    )

    total_gasto = float(agrupado["Monto"].sum())
    if total_gasto <= 0:
        return {
            "tiene_datos": False,
            "df_pareto": pd.DataFrame(),
            "categorias_vitales": [],
        }

    agrupado["Porcentaje_Individual"] = ((agrupado["Monto"] / total_gasto) * 100.0).round(1)
    agrupado["Porcentaje_Acumulado"] = agrupado["Porcentaje_Individual"].cumsum().clip(upper=100.0).round(1)

    # Identificar categorías que componen hasta el primer cruce del 80% del gasto total
    categorias_vitales: list[str] = []
    acum_previo = 0.0
    for _, fila in agrupado.iterrows():
        if acum_previo < 80.0:
            categorias_vitales.append(str(fila["Categoria"]))
        acum_previo = float(fila["Porcentaje_Acumulado"])

    agrupado["Grupo_Pareto"] = agrupado["Categoria"].apply(
        lambda c: "80% Impacto Vital" if c in categorias_vitales else "20% Restante"
    )

    return {
        "tiene_datos": True,
        "total_gasto": round(total_gasto, 2),
        "df_pareto": agrupado,
        "categorias_vitales": categorias_vitales,
    }


def obtener_directorio_consejos() -> list[dict[str, str]]:
    """
    Devuelve un directorio estructurado de estrategias prácticas de ahorro,
    optimización de tarjetas de crédito y blindaje de liquidez.
    """
    return [
        {
            "categoria": "💳 Estrategia de Tarjetas (Ventana de 40-50 días)",
            "titulo": "Compra siempre entre el día 1 y 5 después de tu fecha de corte",
            "descripcion": (
                "Cualquier compra realizada inmediatamente después del día de corte aparecerá hasta el "
                "estado de cuenta del mes siguiente, otorgándote ~30 días de ciclo más ~20 días de gracia "
                "para pagar sin un solo centavo de interés."
            ),
        },
        {
            "categoria": "🛡️ Fondo de Emergencia y Liquidez",
            "titulo": "Separa tus Compromisos Fijos el mismo día que recibes tu ingreso",
            "descripcion": (
                "Tu verdadera liquidez no es el saldo que ves en tu cuenta bancaria, sino ese saldo menos "
                "los recibos de Luz, Agua, Internet y Renta pendientes del mes."
            ),
        },
        {
            "categoria": "❄️ Blindaje de Temporadas Altas (Julio y Diciembre)",
            "titulo": "Evita comprometer Meses Sin Intereses que se encimen en Verano o Navidad",
            "descripcion": (
                "En julio (vacaciones escolares/verano) y diciembre (fiestas/regalos) el gasto familiar "
                "sube entre 25% y 40%. Antes de diferir a 6 o 12 meses, revisa que tus cuotas acumuladas "
                "no superen el 15% de tu ingreso mensual en esos meses."
            ),
        },
        {
            "categoria": "📉 Control de Fugas Hormiga (Principio de Pareto 80/20)",
            "titulo": "Ataca primero las 2 o 3 categorías que concentran el 80% de tu gasto",
            "descripcion": (
                "Reducir un 15% en tus 2 categorías principales del diagrama de Pareto genera más ahorro "
                "neto que recortar decenas de gastos pequeños aislados."
            ),
        },
        {
            "categoria": "⚡ Costo Real del Crédito Revolvente (Tasa + IVA)",
            "titulo": "Nunca financies gastos corrientes con la tasa ordinaria de una tarjeta",
            "descripcion": (
                "En tarjetas de crédito, a los intereses ordinarios se les suma un 16% de IVA. "
                "Si no puedes ser totalero en una emergencia, utiliza el Simulador de Decisiones para "
                "elegir la tarjeta con menor Costo Anual Total y liquidar el saldo lo antes posible."
            ),
        },
    ]
