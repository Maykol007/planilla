import io
import subprocess
import sys
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Calculadora y Sistema de Planillas - Perú",
    page_icon="🧮",
    layout="wide",
)

CERO = Decimal("0.00")


def r2(valor: Decimal) -> Decimal:
    """Redondeo contable estricto a 2 decimales (ROUND_HALF_UP)."""
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_5ta_individual(
    rem_mensual_afecta: Decimal,
    bonif_extra: Decimal,
    mes: int,
    uit: Decimal,
) -> Decimal:
    """Proyección anual de Renta de 5ta Categoría según tramos de UIT vigentes."""
    meses_restantes = Decimal(str(12 - mes + 1))
    # Proyección: remuneración del mes * meses restantes + 2 gratificaciones (jul/dic si aún no pasan)
    gratifs_pendientes = Decimal("0")
    if mes <= 7:
        gratifs_pendientes += rem_mensual_afecta
    if mes <= 12:
        gratifs_pendientes += rem_mensual_afecta

    rem_bruta_anual = (rem_mensual_afecta * meses_restantes) + gratifs_pendientes + bonif_extra
    deduccion_7uit = uit * Decimal("7")
    renta_neta_anual = max(CERO, rem_bruta_anual - deduccion_7uit)

    if renta_neta_anual <= CERO:
        return CERO

    tramos = [
        (uit * Decimal("5"), Decimal("0.08")),
        (uit * Decimal("20"), Decimal("0.14")),
        (uit * Decimal("35"), Decimal("0.17")),
        (uit * Decimal("45"), Decimal("0.20")),
        (None, Decimal("0.30")),
    ]

    impuesto_anual = CERO
    limite_anterior = CERO
    for tope, tasa in tramos:
        if tope is None:
            exceso = max(CERO, renta_neta_anual - limite_anterior)
            impuesto_anual += exceso * tasa
            break
        if renta_neta_anual > limite_anterior:
            base_tramo = min(renta_neta_anual, tope) - limite_anterior
            impuesto_anual += base_tramo * tasa
            limite_anterior = tope
        else:
            break

    divisor = Decimal(str(12 - mes + 1))
    return r2(impuesto_anual / divisor)


st.title("🧮 Calculadora y Sistema Integral de Planillas — Perú (Régimen General)")
st.caption("Motor financiero exacto al céntimo (Decimal) • Normativa Laboral Peruana • PCGE • Boletas D.S. 001-98-TR • PLAME")

DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

tab_calc, tab_planilla, tab_outputs = st.tabs([
    "🧮 1. Calculadora Interactiva (Simulador)",
    "📝 2. Editor de Planilla Completa (Maestro / Tareo / Parámetros)",
    "📊 3. Resultados, Auditoría PCGE y Descargas",
])

# ==============================================================================
# TAB 1: CALCULADORA INTERACTIVA EN VIVO (1 TRABAJADOR)
# ==============================================================================
with tab_calc:
    st.subheader("Simulador de Boleta y Asiento Contable en Tiempo Real")
    st.markdown("Modifica cualquier variable laboral o parámetro legal y observa el cálculo al céntimo al instante.")

    with st.expander("⚙️ Parámetros Legales Vigentes (Editables)", expanded=False):
        p1, p2, p3, p4 = st.columns(4)
        rmv_in = Decimal(str(p1.number_input("RMV Vigente (S/)", min_value=500.0, value=1230.00, step=10.0)))
        uit_in = Decimal(str(p2.number_input("UIT Vigente (S/)", min_value=1000.0, value=5500.00, step=50.0)))
        tasa_onp_in = Decimal(str(p3.number_input("% ONP", min_value=0.0, max_value=30.0, value=13.00, step=0.5))) / Decimal("100")
        tasa_essalud_in = Decimal(str(p4.number_input("% EsSalud", min_value=0.0, max_value=20.0, value=9.00, step=0.5))) / Decimal("100")

        a1, a2, a3, a4 = st.columns(4)
        afp_oblig_in = Decimal(str(a1.number_input("% Aporte Obligatorio AFP", min_value=0.0, value=10.00, step=0.1))) / Decimal("100")
        afp_prima_in = Decimal(str(a2.number_input("% Prima Seguro AFP", min_value=0.0, value=1.70, step=0.05))) / Decimal("100")
        afp_tope_in = Decimal(str(a3.number_input("Tope Prima Seguro SBS (S/)", min_value=1000.0, value=13524.38, step=100.0)))
        afp_com_in = Decimal(str(a4.number_input("% Comisión Flujo AFP", min_value=0.0, value=1.55, step=0.05))) / Decimal("100")

    c_izq, c_der = st.columns([1.1, 1.4], gap="large")

    with c_izq:
        st.markdown("#### Datos del Trabajador y Tareo del Mes")
        col_a, col_b = st.columns(2)
        sueldo_basico = Decimal(str(col_a.number_input("Sueldo Básico Mensual (S/)", min_value=0.0, value=2500.00, step=50.0)))
        mes_calculo = col_b.selectbox("Mes de Cálculo", options=list(range(1, 13)), index=10)

        col_c, col_d = st.columns(2)
        dias_laborados = col_c.number_input("Días Laborados (Base 30)", min_value=0, max_value=30, value=28)
        dias_falta = col_d.number_input("Días de Falta", min_value=0, max_value=30, value=2)

        col_e, col_f = st.columns(2)
        tiene_asig_fam = col_e.checkbox("Asignación Familiar (10% RMV)", value=True)
        centro_costo = col_f.selectbox("Centro de Costo", ["94 - Administración", "95 - Ventas"])

        col_g, col_h = st.columns(2)
        he_25 = Decimal(str(col_g.number_input("Horas Extras 25%", min_value=0.0, value=2.0, step=0.5)))
        he_35 = Decimal(str(col_h.number_input("Horas Extras 35%", min_value=0.0, value=3.0, step=0.5)))

        col_i, col_j = st.columns(2)
        bonif_extra = Decimal(str(col_i.number_input("Bonificación Extraordinaria (S/)", min_value=0.0, value=0.0, step=50.0)))
        sistema_pension = col_j.selectbox("Sistema Pensionario", ["AFP Integra", "AFP Prima", "AFP Profuturo", "AFP Habitat", "ONP"])

        tipo_comision = "Flujo"
        if sistema_pension != "ONP":
            tipo_comision = st.radio("Tipo de Comisión AFP", ["Flujo", "Mixta"], horizontal=True)

    # --- CÁLCULOS EN DECIMAL ---
    rem_basica = r2((sueldo_basico / Decimal("30")) * Decimal(str(dias_laborados)))
    asig_familiar = r2(rmv_in * Decimal("0.10")) if tiene_asig_fam else CERO

    rem_ordinaria_mensual = sueldo_basico + asig_familiar
    valor_hora = rem_ordinaria_mensual / Decimal("240")
    monto_he_25 = r2(valor_hora * Decimal("1.25") * he_25)
    monto_he_35 = r2(valor_hora * Decimal("1.35") * he_35)

    total_ingresos = r2(rem_basica + asig_familiar + monto_he_25 + monto_he_35 + bonif_extra)
    # Bonificación extraordinaria no es remuneración asegurable para pensión ni EsSalud
    rem_asegurable = r2(rem_basica + asig_familiar + monto_he_25 + monto_he_35)

    if sistema_pension == "ONP":
        desc_onp = r2(rem_asegurable * tasa_onp_in)
        afp_oblig = afp_prima = afp_com = CERO
    else:
        desc_onp = CERO
        afp_oblig = r2(rem_asegurable * afp_oblig_in)
        base_prima = min(rem_asegurable, afp_tope_in)
        afp_prima = r2(base_prima * afp_prima_in)
        tasa_com_efectiva = CERO if tipo_comision == "Mixta" else afp_com_in
        afp_com = r2(rem_asegurable * tasa_com_efectiva)

    renta_5ta = calcular_5ta_individual(rem_ordinaria_mensual, bonif_extra, mes_calculo, uit_in)
    total_descuentos = r2(desc_onp + afp_oblig + afp_prima + afp_com + renta_5ta)
    neto_pagar = r2(total_ingresos - total_descuentos)

    base_essalud = max(rem_asegurable, rmv_in) if rem_asegurable > CERO else CERO
    essalud = r2(base_essalud * tasa_essalud_in)
    costo_total = r2(total_ingresos + essalud)

    with c_der:
        st.markdown("#### Resultado de Liquidación Mensual")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Ingresos", f"S/ {total_ingresos:,.2f}")
        m2.metric("Total Descuentos", f"S/ {total_descuentos:,.2f}")
        m3.metric("Neto a Pagar", f"S/ {neto_pagar:,.2f}")
        m4.metric("EsSalud (9%)", f"S/ {essalud:,.2f}")

        if rem_asegurable < rmv_in and rem_asegurable > CERO:
            st.info(f"ℹ️ Remuneración asegurable (S/ {rem_asegurable:,.2f}) menor a 1 RMV: EsSalud calculado sobre RMV mínima (S/ {rmv_in:,.2f}).")

        df_boleta = pd.DataFrame([
            {"Rubro": "Ingreso", "Concepto": f"Remuneración Básica ({dias_laborados} días)", "Importe (S/)": f"{rem_basica:,.2f}"},
            {"Rubro": "Ingreso", "Concepto": "Asignación Familiar (Íntegra 10% RMV)", "Importe (S/)": f"{asig_familiar:,.2f}"},
            {"Rubro": "Ingreso", "Concepto": f"Horas Extras 25% ({he_25} hrs)", "Importe (S/)": f"{monto_he_25:,.2f}"},
            {"Rubro": "Ingreso", "Concepto": f"Horas Extras 35% ({he_35} hrs)", "Importe (S/)": f"{monto_he_35:,.2f}"},
            {"Rubro": "Ingreso", "Concepto": "Bonificación Extraordinaria", "Importe (S/)": f"{bonif_extra:,.2f}"},
            {"Rubro": "Descuento", "Concepto": "ONP (13%)", "Importe (S/)": f"-{desc_onp:,.2f}"},
            {"Rubro": "Descuento", "Concepto": "AFP - Aporte Obligatorio", "Importe (S/)": f"-{afp_oblig:,.2f}"},
            {"Rubro": "Descuento", "Concepto": "AFP - Prima de Seguro (Tope SBS)", "Importe (S/)": f"-{afp_prima:,.2f}"},
            {"Rubro": "Descuento", "Concepto": f"AFP - Comisión ({tipo_comision})", "Importe (S/)": f"-{afp_com:,.2f}"},
            {"Rubro": "Descuento", "Concepto": "Retención Renta 5ta Categoría", "Importe (S/)": f"-{renta_5ta:,.2f}"},
            {"Rubro": "Aporte Empleador", "Concepto": "EsSalud (9%)", "Importe (S/)": f"{essalud:,.2f}"},
        ])
        st.dataframe(df_boleta, width="stretch", hide_index=True)

        # Asiento PCGE rápido
        cta_destino = "941" if centro_costo.startswith("94") else "951"
        asiento_rows = [
            {"Cuenta": "6211", "Descripción": "Sueldos y salarios (Ingresos)", "Debe": total_ingresos, "Haber": CERO},
            {"Cuenta": "6271", "Descripción": "Régimen de prestaciones de salud (EsSalud)", "Debe": essalud, "Haber": CERO},
            {"Cuenta": "4031", "Descripción": "EsSalud por pagar", "Debe": CERO, "Haber": essalud},
        ]
        if desc_onp > CERO:
            asiento_rows.append({"Cuenta": "4032", "Descripción": "ONP por pagar", "Debe": CERO, "Haber": desc_onp})
        if renta_5ta > CERO:
            asiento_rows.append({"Cuenta": "40173", "Descripción": "Renta de quinta categoría", "Debe": CERO, "Haber": renta_5ta})
        total_afp = afp_oblig + afp_prima + afp_com
        if total_afp > CERO:
            asiento_rows.append({"Cuenta": "417", "Descripción": "Administradoras de fondos de pensiones (AFP)", "Debe": CERO, "Haber": total_afp})
        asiento_rows.append({"Cuenta": "4111", "Descripción": "Remuneraciones por pagar (Neto)", "Debe": CERO, "Haber": neto_pagar})
        asiento_rows.append({"Cuenta": cta_destino, "Descripción": f"Destino {centro_costo}", "Debe": costo_total, "Haber": CERO})
        asiento_rows.append({"Cuenta": "791", "Descripción": "Cargas imputables a cuentas de costos", "Debe": CERO, "Haber": costo_total})

        df_asiento = pd.DataFrame(asiento_rows)
        tot_debe = sum((x["Debe"] for x in asiento_rows), CERO)
        tot_haber = sum((x["Haber"] for x in asiento_rows), CERO)
        df_asiento["Debe"] = df_asiento["Debe"].apply(lambda x: f"{x:,.2f}")
        df_asiento["Haber"] = df_asiento["Haber"].apply(lambda x: f"{x:,.2f}")

        st.markdown(f"**Asiento Contable PCGE (Cuadre: Debe S/ {tot_debe:,.2f} == Haber S/ {tot_haber:,.2f})**")
        st.dataframe(df_asiento, width="stretch", hide_index=True)

# ==============================================================================
# TAB 2: EDITOR EN VIVO DE LA PLANILLA COMPLETA (EXCEL/CSV)
# ==============================================================================
with tab_planilla:
    st.subheader("Gestión y Edición en Vivo de Archivos de Entrada")
    st.markdown("Edita celdas directamente en las tablas (puedes agregar o eliminar filas) o sube un nuevo set de archivos en la barra lateral.")

    st.sidebar.header("📂 Carga Rápida de Archivos")
    uploaded_files = st.sidebar.file_uploader(
        "Subir nuevos Excel/CSV (sobrescribe data/)",
        type=["xlsx", "csv"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        for uf in uploaded_files:
            with open(DATA_DIR / uf.name, "wb") as f:
                f.write(uf.getbuffer())
        st.sidebar.success(f"{len(uploaded_files)} archivo(s) actualizado(s) en data/.")

    archivos_excel = sorted([f for f in DATA_DIR.glob("*.xlsx") if not f.name.startswith("~$")])
    editores_guardados = {}

    if not archivos_excel:
        st.warning("No se encontraron archivos .xlsx en la carpeta data/. Sube los archivos desde la barra lateral.")
    else:
        for archivo in archivos_excel:
            with st.expander(f"📄 Editar: {archivo.name}", expanded=(archivo.name != "tabla_parametros.xlsx")):
                xls = pd.ExcelFile(archivo)
                hojas_editadas = {}
                for hoja in xls.sheet_names:
                    if len(xls.sheet_names) > 1:
                        st.markdown(f"**Hoja: `{hoja}`**")
                    df_orig = pd.read_excel(archivo, sheet_name=hoja)
                    for col in df_orig.columns:
                        if str(col).strip().lower() == "dni":
                            df_orig[col] = df_orig[col].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(8)
                    df_editado = st.data_editor(
                        df_orig,
                        key=f"editor_{archivo.name}_{hoja}",
                        num_rows="dynamic",
                        width="stretch",
                    )
                    hojas_editadas[hoja] = df_editado
                editores_guardados[archivo] = hojas_editadas

        if st.button("💾 Guardar Cambios y Recalcular Toda la Planilla", type="primary", width="stretch"):
            try:
                for archivo_path, hojas_dict in editores_guardados.items():
                    with pd.ExcelWriter(archivo_path, engine="openpyxl") as writer:
                        for nombre_hoja, df_mod in hojas_dict.items():
                            for col in df_mod.columns:
                                if str(col).strip().lower() == "dni":
                                    df_mod[col] = (
                                        df_mod[col]
                                        .astype(str)
                                        .str.replace(r"\.0$", "", regex=True)
                                        .str.zfill(8)
                                    )
                            df_mod.to_excel(writer, sheet_name=nombre_hoja, index=False)

                with st.spinner("Calculando planilla, asientos PCGE, boletas PDF y archivos SUNAT..."):
                    proc = subprocess.run(
                        [sys.executable, "main.py"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )

                if proc.returncode == 0:
                    st.success("✅ ¡Planilla recalculada con éxito! Revisa los resultados y descargas en la Pestaña 3.")
                else:
                    st.error("⚠️ Error al ejecutar main.py (asegúrate de tener cerrados los Excel de la carpeta output/).")
                st.code(proc.stdout + ("\n" + proc.stderr if proc.stderr else ""), language="text")
            except PermissionError:
                st.error("⚠️ No se pudo guardar porque tienes uno de los archivos Excel abierto en Windows. Ciérralo e intenta de nuevo.")

# ==============================================================================
# TAB 3: RESULTADOS, PLANOS SUNAT Y DESCARGAS
# ==============================================================================
with tab_outputs:
    st.subheader("Entregables Oficiales Generados")

    todos_los_archivos = sorted(
        [p for p in OUTPUT_DIR.rglob("*") if p.is_file() and not p.name.startswith("~$")]
    )

    if not todos_los_archivos:
        st.info("Aún no hay entregables generados. Ve a la Pestaña 2 y presiona **Guardar Cambios y Recalcular Toda la Planilla**.")
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in todos_los_archivos:
                zf.write(file_path, arcname=file_path.relative_to(OUTPUT_DIR))
        zip_buffer.seek(0)

        st.download_button(
            label="📦 Descargar TODOS los Entregables (.ZIP: Excel + Boletas PDF + SUNAT)",
            data=zip_buffer,
            file_name="entregables_planilla_peru.zip",
            mime="application/zip",
            type="primary",
            width="stretch",
        )

        st.divider()
        col_vis1, col_vis2 = st.columns([1.3, 1])

        with col_vis1:
            st.markdown("#### Vista Previa de Libros Excel")
            excels_out = sorted([p for p in OUTPUT_DIR.rglob("*.xlsx") if not p.name.startswith("~$")])
            if excels_out:
                sel_xl = st.selectbox("Libro Excel:", excels_out, format_func=lambda p: p.name)
                hojas_xl = pd.ExcelFile(sel_xl).sheet_names
                sel_hoja = st.selectbox("Hoja:", hojas_xl)
                df_prev = pd.read_excel(sel_xl, sheet_name=sel_hoja).fillna("").astype(str)
                st.dataframe(df_prev, width="stretch")

        with col_vis2:
            st.markdown("#### Vista Previa de Archivos Planos SUNAT / Banco")
            planos = sorted(
                [p for p in OUTPUT_DIR.rglob("*") if p.suffix.lower() in (".rem", ".jor", ".snl", ".txt")]
            )
            if planos:
                sel_plano = st.selectbox("Archivo plano:", planos, format_func=lambda p: p.name)
                contenido_plano = sel_plano.read_text(encoding="utf-8", errors="replace")
                st.code(contenido_plano if contenido_plano.strip() else "(Archivo vacío)", language="text")

        st.divider()
        st.markdown("#### Descarga Individual de Archivos (Boletas PDF, Excel, SUNAT)")
        c1, c2 = st.columns(2)
        for idx, file_path in enumerate(todos_los_archivos):
            col = c1 if idx % 2 == 0 else c2
            with open(file_path, "rb") as f:
                col.download_button(
                    label=f"⬇️ {file_path.relative_to(OUTPUT_DIR)}",
                    data=f.read(),
                    file_name=file_path.name,
                    key=f"btn_dl_{idx}",
                    width="stretch",
                )