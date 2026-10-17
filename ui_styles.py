"""
ui_styles.py
------------
Módulo de diseño visual, estilos CSS en modo oscuro y configuración estética
para gráficos de Plotly en la aplicación "Mis Finanzas v4.0".

Separa por completo la capa de presentación visual de la lógica de negocio.
"""

import streamlit as st
import plotly.graph_objects as go

# ==============================================================================
# PALETA DE COLORES GLOBAL Y CONSTANTES DE DISEÑO
# ==============================================================================
PALETA = {
    "fondo_oscuro": "#0f0f1a",
    "fondo_secundario": "#161829",
    "fondo_tarjeta": "rgba(25, 28, 48, 0.82)",
    "verde_neon": "#4fffb0",
    "cian_brillante": "#00c6ff",
    "morado_acento": "#a78bfa",
    "amarillo_alerta": "#ffb703",
    "rojo_peligro": "#ff4d6d",
    "azul_info": "#38bdf8",
    "texto_principal": "#f1f5f9",
    "texto_secundario": "#94a3b8",
    "borde_sutil": "rgba(79, 255, 176, 0.20)",
}

# Secuencia de colores consistente para todos los gráficos de Plotly
SECUENCIA_COLORES_PLOTLY = [
    "#4fffb0",  # Verde neón principal
    "#00c6ff",  # Cian brillante
    "#a78bfa",  # Violeta suave
    "#ffb703",  # Ámbar / advertencia
    "#ff4d6d",  # Coral / alerta
    "#38bdf8",  # Azul cielo
    "#f472b6",  # Rosa neón
    "#34d399",  # Esmeralda
]


# ==============================================================================
# INYECCIÓN DE CSS GLOBAL (MODO OSCURO, TIPOGRAFÍAS Y COMPONENTES)
# ==============================================================================
def aplicar_estilos_globales() -> None:
    """
    Inyecta las hojas de estilo CSS globales en la aplicación Streamlit:
    - Fuentes Google Fonts: 'Sora' (interfaz y títulos) y 'JetBrains Mono' (cifras).
    - Fondo oscuro degradado basado en #0f0f1a.
    - Tarjetas .metric-card con efecto glassmorphism.
    - Botones interactivos con gradiente cian/verde (#4fffb0 -> #00c6ff).
    - Cajas de alerta, insignias de semáforo y banners informativos.
    """
    css = """
    <style>
        /* Importación de tipografías 'Sora' y 'JetBrains Mono' */
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Sora:wght@300;400;500;600;700&display=swap');

        /* Variables globales de diseño */
        :root {
            --bg-primary: #0f0f1a;
            --bg-secondary: #15172b;
            --bg-card: rgba(24, 27, 46, 0.85);
            --accent-green: #4fffb0;
            --accent-cyan: #00c6ff;
            --accent-purple: #a78bfa;
            --accent-warning: #ffb703;
            --accent-danger: #ff4d6d;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --font-sans: 'Sora', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        /* Fondo principal de la aplicación con degradado oscuro #0f0f1a */
        .stApp {
            background: radial-gradient(circle at 12% 15%, rgba(0, 198, 255, 0.08) 0%, transparent 38%),
                        radial-gradient(circle at 88% 80%, rgba(79, 255, 176, 0.07) 0%, transparent 40%),
                        linear-gradient(145deg, #0f0f1a 0%, #141629 55%, #0b0d17 100%) !important;
            color: var(--text-main) !important;
            font-family: var(--font-sans) !important;
        }

        /* Tipografía general */
        html, body, [class*="css"], p, label, span, div {
            font-family: var(--font-sans);
            color: var(--text-main);
        }

        h1, h2, h3, h4, h5, h6 {
            font-family: var(--font-sans) !important;
            font-weight: 700 !important;
            letter-spacing: -0.02em;
            color: #ffffff !important;
        }

        /* Clase utilitaria para números y montos financieros */
        .mono-num, code, pre {
            font-family: var(--font-mono) !important;
        }

        /* Barra lateral (Sidebar) */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #121324 0%, #0d0e1a 100%) !important;
            border-right: 1px solid rgba(79, 255, 176, 0.14) !important;
        }

        /* Tarjetas de métricas (.metric-card) */
        .metric-card {
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(79, 255, 176, 0.20);
            border-left: 4px solid var(--accent-green);
            border-radius: 14px;
            padding: 1.15rem 1.3rem;
            margin-bottom: 1rem;
            box-shadow: 0 8px 26px rgba(0, 0, 0, 0.35);
            transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
        }

        .metric-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 12px 32px rgba(0, 198, 255, 0.15);
            border-color: rgba(0, 198, 255, 0.45);
        }

        /* Variantes de color para .metric-card */
        .metric-card.cyan {
            border-left-color: var(--accent-cyan);
        }
        .metric-card.warning {
            border-left-color: var(--accent-warning);
        }
        .metric-card.danger {
            border-left-color: var(--accent-danger);
        }
        .metric-card.purple {
            border-left-color: var(--accent-purple);
        }

        .metric-card .metric-title {
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
            margin-bottom: 0.35rem;
            display: flex;
            align-items: center;
            gap: 0.4rem;
        }

        .metric-card .metric-value {
            font-family: var(--font-mono) !important;
            font-size: 1.55rem;
            font-weight: 700;
            color: #ffffff;
            line-height: 1.2;
            margin-bottom: 0.3rem;
        }

        .metric-card .metric-sub {
            font-size: 0.80rem;
            color: var(--text-muted);
            line-height: 1.35;
        }

        /* Banner superior para la Tarjeta Recomendada del Día */
        .recommended-card-banner {
            background: linear-gradient(125deg, rgba(79, 255, 176, 0.14) 0%, rgba(0, 198, 255, 0.14) 100%);
            border: 1px solid rgba(79, 255, 176, 0.40);
            border-radius: 16px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1.4rem;
            box-shadow: 0 10px 30px rgba(0, 198, 255, 0.12);
            position: relative;
            overflow: hidden;
        }

        .recommended-card-banner .banner-tag {
            display: inline-block;
            background: linear-gradient(90deg, #4fffb0 0%, #00c6ff 100%);
            color: #090a12;
            font-family: var(--font-mono);
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            padding: 0.22rem 0.65rem;
            border-radius: 999px;
            margin-bottom: 0.55rem;
        }

        .recommended-card-banner .banner-title {
            font-size: 1.3rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 0.25rem;
        }

        .recommended-card-banner .banner-details {
            font-size: 0.88rem;
            color: #cbd5e1;
        }

        /* Botones con gradiente cian/verde (#4fffb0 -> #00c6ff) */
        .stButton > button,
        .stDownloadButton > button,
        div[data-testid="stFormSubmitButton"] > button {
            background: linear-gradient(90deg, #4fffb0 0%, #00c6ff 100%) !important;
            color: #080b14 !important;
            font-family: var(--font-sans) !important;
            font-weight: 700 !important;
            font-size: 0.9rem !important;
            border: none !important;
            border-radius: 10px !important;
            padding: 0.55rem 1.25rem !important;
            box-shadow: 0 4px 15px rgba(79, 255, 176, 0.25) !important;
            transition: all 0.2s ease-in-out !important;
            width: 100%;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 7px 22px rgba(0, 198, 255, 0.45) !important;
            filter: brightness(1.05);
        }

        .stButton > button:active,
        div[data-testid="stFormSubmitButton"] > button:active {
            transform: translateY(0px) !important;
        }

        /* Asegurar texto oscuro legible dentro de los botones */
        .stButton > button p,
        .stDownloadButton > button p,
        div[data-testid="stFormSubmitButton"] > button p {
            color: #080b14 !important;
            font-weight: 700 !important;
        }

        /* Alertas personalizadas */
        .custom-alert {
            border-radius: 12px;
            padding: 0.95rem 1.15rem;
            margin: 0.75rem 0;
            font-size: 0.88rem;
            line-height: 1.45;
            border-left: 4px solid;
            background: rgba(22, 25, 45, 0.85);
        }

        .custom-alert.success {
            border-color: var(--accent-green);
            background: rgba(79, 255, 176, 0.08);
        }

        .custom-alert.info {
            border-color: var(--accent-cyan);
            background: rgba(0, 198, 255, 0.08);
        }

        .custom-alert.warning {
            border-color: var(--accent-warning);
            background: rgba(255, 183, 3, 0.09);
        }

        .custom-alert.danger {
            border-color: var(--accent-danger);
            background: rgba(255, 77, 109, 0.10);
        }

        /* Semáforo de estado para tarjetas y compromisos */
        .semaforo-badge {
            display: inline-block;
            font-family: var(--font-mono);
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            letter-spacing: 0.02em;
        }

        .semaforo-verde {
            background: rgba(79, 255, 176, 0.16);
            color: #4fffb0;
            border: 1px solid rgba(79, 255, 176, 0.4);
        }

        .semaforo-amarillo {
            background: rgba(255, 183, 3, 0.16);
            color: #ffb703;
            border: 1px solid rgba(255, 183, 3, 0.4);
        }

        .semaforo-rojo {
            background: rgba(255, 77, 109, 0.16);
            color: #ff4d6d;
            border: 1px solid rgba(255, 77, 109, 0.4);
        }

        /* Campos de entrada, selectores y contenedores de formulario */
        [data-testid="stForm"] {
            background: rgba(20, 23, 40, 0.65);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 14px;
            padding: 1.25rem;
        }

        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        textarea {
            background-color: rgba(15, 17, 30, 0.85) !important;
            border-color: rgba(148, 163, 184, 0.22) !important;
            border-radius: 8px !important;
            color: var(--text-main) !important;
        }

        /* Métricas nativas de Streamlit estilizadas con JetBrains Mono */
        [data-testid="stMetricValue"] {
            font-family: var(--font-mono) !important;
            color: var(--accent-green) !important;
        }

        /* Separadores suaves */
        hr {
            border-color: rgba(148, 163, 184, 0.14) !important;
        }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# Alias por compatibilidad semántica
cargar_estilos = aplicar_estilos_globales


# ==============================================================================
# ESTANDARIZACIÓN DE GRÁFICOS DE PLOTLY
# ==============================================================================
def estilo_fig(
    fig: go.Figure,
    titulo: str | None = None,
    altura: int | None = None,
    mostrar_leyenda: bool = True,
) -> go.Figure:
    """
    Aplica formato estético uniforme en modo oscuro y fondo transparente
    a cualquier figura de Plotly (`go.Figure`).

    Parámetros:
        fig (go.Figure): Figura de Plotly a estilizar.
        titulo (str, opcional): Título superior del gráfico.
        altura (int, opcional): Altura en píxeles si se desea fijar.
        mostrar_leyenda (bool): Indica si se muestra la leyenda.

    Retorna:
        go.Figure: La misma figura modificada con el tema visual de Mis Finanzas v4.0.
    """
    layout_params = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family="Sora, sans-serif",
            color=PALETA["texto_principal"],
            size=12,
        ),
        colorway=SECUENCIA_COLORES_PLOTLY,
        showlegend=mostrar_leyenda,
        legend=dict(
            bgcolor="rgba(15, 15, 26, 0.65)",
            bordercolor="rgba(79, 255, 176, 0.15)",
            borderwidth=1,
            font=dict(family="Sora, sans-serif", size=11, color="#e2e8f0"),
        ),
        hoverlabel=dict(
            bgcolor="#161829",
            bordercolor="#4fffb0",
            font=dict(family="JetBrains Mono, monospace", size=12, color="#ffffff"),
        ),
        margin=dict(l=20, r=20, t=50 if titulo else 30, b=25),
        xaxis=dict(
            gridcolor="rgba(148, 163, 184, 0.10)",
            zerolinecolor="rgba(148, 163, 184, 0.18)",
            tickfont=dict(family="Sora, sans-serif", color="#94a3b8"),
            title_font=dict(family="Sora, sans-serif", color="#cbd5e1"),
        ),
        yaxis=dict(
            gridcolor="rgba(148, 163, 184, 0.10)",
            zerolinecolor="rgba(148, 163, 184, 0.18)",
            tickfont=dict(family="JetBrains Mono, monospace", color="#94a3b8"),
            title_font=dict(family="Sora, sans-serif", color="#cbd5e1"),
        ),
    )

    if titulo is not None:
        layout_params["title"] = dict(
            text=titulo,
            font=dict(family="Sora, sans-serif", size=16, color="#ffffff"),
            x=0.01,
            xanchor="left",
        )

    if altura is not None:
        layout_params["height"] = altura

    fig.update_layout(**layout_params)
    return fig


# ==============================================================================
# COMPONENTES VISUALES REUTILIZABLES (TARJETAS, ALERTAS Y BANNERS)
# ==============================================================================
def render_metric_card(
    titulo: str,
    valor: str,
    subtitulo: str = "",
    variante: str = "default",
    icono: str = "",
) -> None:
    """
    Renderiza una tarjeta `.metric-card` estilizada mediante HTML seguro.

    Parámetros:
        titulo (str): Etiqueta superior de la métrica.
        valor (str): Cifra o valor principal (se muestra en fuente JetBrains Mono).
        subtitulo (str): Texto descriptivo inferior.
        variante (str): 'default' (verde), 'cyan', 'warning', 'danger' o 'purple'.
        icono (str): Emoji o icono opcional para acompañar el título.
    """
    clase_variante = variante if variante in {"cyan", "warning", "danger", "purple"} else ""
    prefijo_icono = f"<span>{icono}</span>" if icono else ""
    html = f"""
    <div class="metric-card {clase_variante}">
        <div class="metric-title">{prefijo_icono}<span>{titulo}</span></div>
        <div class="metric-value">{valor}</div>
        <div class="metric-sub">{subtitulo}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_alerta(mensaje: str, tipo: str = "info", titulo: str = "") -> None:
    """
    Muestra un recuadro de alerta personalizado acorde al tema oscuro.

    Parámetros:
        mensaje (str): Contenido de la alerta.
        tipo (str): 'success', 'info', 'warning' o 'danger'.
        titulo (str): Encabezado opcional en negrita.
    """
    iconos = {
        "success": "✅",
        "info": "💡",
        "warning": "⚠️",
        "danger": "🚨",
    }
    clase = tipo if tipo in iconos else "info"
    icono = iconos[clase]
    encabezado = f"<strong>{icono} {titulo}:</strong> " if titulo else f"{icono} "
    html = f"""
    <div class="custom-alert {clase}">
        {encabezado}{mensaje}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def obtener_badge_semaforo(texto: str, nivel: str = "verde") -> str:
    """
    Devuelve el fragmento HTML de una insignia tipo semáforo ('verde', 'amarillo', 'rojo').
    """
    clase = f"semaforo-{nivel}" if nivel in {"verde", "amarillo", "rojo"} else "semaforo-verde"
    return f'<span class="semaforo-badge {clase}">{texto}</span>'
