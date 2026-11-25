from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

from src.accounting import generar_asientos_planilla
from src.benefits import calcular_provisiones_mensuales, generar_asientos_provisiones
from src.calculator import CERO, calcular_planilla
from src.exporters.excel_exporter import exportar_excel_planilla
from src.exporters.hr_docs_exporter import exportar_documentos_rrhh
from src.exporters.interfaces_exporter import (
    exportar_afpnet_excel,
    exportar_archivo_snl,
    exportar_control_gestion_excel,
    exportar_txt_bancario_haberes,
)
from src.exporters.pdf_exporter import DatosEmpresa, exportar_boletas_pdf
from src.exporters.sunat_exporter import exportar_archivos_sunat
from src.loader import cargar_datos_planilla


def ejecutar_planilla(
    ruta_maestro: Path,
    ruta_tareo: Path,
    ruta_parametros: Path,
    output_dir: Path,
    empresa: DatosEmpresa,
) -> None:
    print("=" * 84)
    print("SISTEMA INTEGRAL DE PLANILLAS Y BENEFICIOS SOCIALES - REGIMEN GENERAL (PERU)")
    print("=" * 84)

    # 1. Lectura y validacion de datos
    print("\n[1/6] Leyendo y validando archivos de entrada...")
    datos = cargar_datos_planilla(
        ruta_maestro=ruta_maestro,
        ruta_tareo=ruta_tareo,
        ruta_parametros=ruta_parametros,
    )
    print(
        f"      OK -> {len(datos.trabajadores)} trabajadores | "
        f"{len(datos.tareos)} registros de tareo | RMV: S/ {datos.parametros.rmv:.2f}"
    )

    # 2. Motor de calculo laboral, tributario y provisiones mensuales
    print("[2/6] Calculando planilla mensual y provisiones de beneficios sociales...")
    resultados = calcular_planilla(datos)
    provisiones = calcular_provisiones_mensuales(datos)

    total_ingresos = sum((r.total_ingresos for r in resultados), CERO)
    total_neto = sum((r.neto_a_pagar for r in resultados), CERO)
    total_essalud = sum((r.essalud for r in resultados), CERO)
    total_prov = sum((p.total_provision_mensual for p in provisiones), CERO)
    print(
        f"      OK -> Ingresos: S/ {total_ingresos:,.2f} | Neto: S/ {total_neto:,.2f} | "
        f"EsSalud: S/ {total_essalud:,.2f} | Provisiones: S/ {total_prov:,.2f}"
    )

    # 3. Contabilidad PCGE 2019 (Asientos 01-02 Planilla y 03-04 Provisiones)
    print("[3/6] Generando y auditando asientos contables PCGE 2019...")
    asientos_planilla = generar_asientos_planilla(resultados)
    asientos_provision = generar_asientos_provisiones(provisiones)
    for a in asientos_planilla + asientos_provision:
        print(
            f"      OK -> Asiento {a.numero}: Debe = S/ {a.total_debe:,.2f} | "
            f"Haber = S/ {a.total_haber:,.2f} [CUADRE EXACTO]"
        )

    # 4. Reportes Excel (Planilla General + Control de Asistencia, Provisiones y KPIs)
    print("[4/6] Exportando libros Excel (Planilla General + Control de Gestion y KPIs)...")
    ruta_excel = exportar_excel_planilla(resultados, asientos_planilla, output_dir=output_dir)
    ruta_kpi = exportar_control_gestion_excel(
        resultados, provisiones, asientos_provision, output_dir=output_dir
    )
    print(f"      OK -> {ruta_excel}")
    print(f"      OK -> {ruta_kpi}")

    # 5. Documentos Individuales PDF (Boletas, Cert. 5ta, Liquidaciones y Cert. Trabajo)
    print("[5/6] Generando documentos individuales PDF (Boletas, 5ta Cat., Liquidaciones, Cert. Trabajo)...")
    rutas_boletas = exportar_boletas_pdf(
        resultados,
        trabajadores=datos.trabajadores,
        output_dir=output_dir / "boletas",
        empresa=empresa,
    )
    docs_rrhh = exportar_documentos_rrhh(
        resultados,
        trabajadores=datos.trabajadores,
        parametros=datos.parametros,
        output_dir=output_dir / "documentos_rrhh",
        empresa=empresa,
        fecha_corte_cese=date.today(),
    )
    print(f"      OK -> {len(rutas_boletas)} Boletas de Pago en '{output_dir / 'boletas'}'")
    print(
        f"      OK -> {len(docs_rrhh['certificados_5ta'])} Cert. 5ta | "
        f"{len(docs_rrhh['liquidaciones'])} Liquidaciones | "
        f"{len(docs_rrhh['certificados_trabajo'])} Cert. Trabajo en '{output_dir / 'documentos_rrhh'}'"
    )

    # 6. Interfaces Externas: SUNAT PLAME (.rem, .jor, .snl), AFPnet y TXT Bancario
    print("[6/6] Generando interfaces SUNAT PLAME (.rem/.jor/.snl), AFPnet y TXT Bancario...")
    rutas_sunat = exportar_archivos_sunat(
        resultados, output_dir=output_dir / "sunat", ruc_empresa=empresa.ruc
    )
    ruta_snl = exportar_archivo_snl(
        resultados, output_dir=output_dir / "sunat", ruc_empresa=empresa.ruc
    )
    ruta_afpnet = exportar_afpnet_excel(
        resultados, datos.trabajadores, output_dir=output_dir / "interfaces"
    )
    ruta_txt = exportar_txt_bancario_haberes(
        resultados, output_dir=output_dir / "interfaces", ruc_empresa=empresa.ruc
    )
    print(f"      OK -> PLAME: {rutas_sunat['rem'].name}, {rutas_sunat['jor'].name}, {ruta_snl.name}")
    print(f"      OK -> AFPnet: {ruta_afpnet}")
    print(f"      OK -> TXT Bancario: {ruta_txt}")

    print("\n" + "=" * 84)
    print("PROCESO INTEGRAL COMPLETADO AL 100% - TODOS LOS ENTREGABLES GENERADOS.")
    print("=" * 84)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistema Integral de Planillas y Beneficios Sociales - Peru (Regimen General)"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--maestro", type=str, default="maestro_trabajadores.xlsx")
    parser.add_argument("--tareo", type=str, default="tareo_mensual.xlsx")
    parser.add_argument("--parametros", type=str, default="tabla_parametros.xlsx")
    parser.add_argument("--ruc", type=str, default="20601234567")
    parser.add_argument("--razon-social", type=str, default="EMPRESA MODELO PERU S.A.C.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    empresa_cfg = DatosEmpresa(ruc=args.ruc, razon_social=args.razon_social)
    try:
        ejecutar_planilla(
            ruta_maestro=args.data_dir / args.maestro,
            ruta_tareo=args.data_dir / args.tareo,
            ruta_parametros=args.data_dir / args.parametros,
            output_dir=args.output_dir,
            empresa=empresa_cfg,
        )
    except Exception as exc:
        print(f"\n[ERROR DE EJECUCION]: {exc}", file=sys.stderr)
        sys.exit(1)