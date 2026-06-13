"""
agente_supervisor.py
====================
Agente 3 — Supervisor / Explicador
Genera reportes con Gemini. Si no esta disponible, usa texto plano.
"""

import json
import re
from datetime import datetime
from typing import List, Dict, Optional
from config_gemini import GEMINI_API_KEY, GEMINI_MODEL
from database import (
    get_connection, obtener_inferencias_pedido,
    guardar_inferencia, verificar_stock_bajo,
)

try:
    from google import genai
    GEMINI_DISPONIBLE = True
except ImportError:
    GEMINI_DISPONIBLE = False


def _inicializar_gemini():
    if not GEMINI_DISPONIBLE or not GEMINI_API_KEY or GEMINI_API_KEY == "TU_API_KEY_AQUI":
        return None
    try:
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        return None


class AgenteSupervisor:

    def __init__(self):
        self.cliente = _inicializar_gemini()

    def _llamar_gemini(self, prompt: str) -> Optional[str]:
        if not self.cliente:
            return None
        try:
            resp = self.cliente.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            return resp.text.strip()
        except Exception:
            print("[SUPERVISOR] Gemini no disponible, usando resumen de texto plano.")
            return None

    def _construir_resumen_texto(self, datos: Dict) -> str:
        lineas    = []
        cliente   = datos.get("cliente", {})
        estado    = datos.get("estado", "desconocido")
        pedido_id = datos.get("pedido_id")

        lineas.append(f"RESUMEN DEL PEDIDO #{pedido_id or 'N/A'}")
        lineas.append(f"Cliente : {cliente.get('nombre', 'Desconocido')}")
        lineas.append(f"Estado  : {estado.upper()}")
        lineas.append("")

        if estado == "confirmado":
            lineas.append("PRODUCTOS ORDENADOS:")
            for p in datos.get("productos_validos", []):
                pers = f" ({p['personalizacion']})" if p.get("personalizacion") else ""
                lineas.append(f"  - {p['nombre']}{pers} x{p['cantidad']} = ${p['precio'] * p['cantidad']:.2f}")
            lineas.append("")
            lineas.append(f"Subtotal : ${datos.get('subtotal', 0):.2f}")
            if datos.get("descuento_pct", 0) > 0:
                lineas.append(f"Descuento: -{datos['descuento_pct']:.0%} por {datos.get('motivo_descuento','')} (${datos.get('descuento_monto',0):.2f})")
            lineas.append(f"TOTAL    : ${datos.get('total', 0):.2f}")
        elif estado == "rechazado":
            lineas.append(f"MOTIVO: {datos.get('motivo', 'Sin motivo')}")
            for p in datos.get("productos_sin_stock", []):
                lineas.append(f"  - {p['nombre']}: pedido {p['cantidad']}, disponible {p.get('stock_actual',0)}")

        alertas = datos.get("alertas_stock", [])
        if alertas:
            lineas.append("\nALERTAS DE STOCK:")
            for a in alertas:
                nivel = "CRITICO" if a.get("nivel") == "critico" else "bajo"
                lineas.append(f"  [{nivel}] {a['producto']}: {a['stock_actual']} unidades")

        return "\n".join(lineas)

    def _construir_explicacion_inferencias(self, inferencias: List[Dict]) -> str:
        if not inferencias:
            return "No se registraron inferencias."
        lineas = ["INFERENCIAS EJECUTADAS:"]
        for inf in inferencias:
            lineas.append(
                f"  [{inf.get('regla', inf.get('nombre', '?'))}] "
                f"{inf.get('descripcion', '')} -> {inf.get('resultado', '')}"
            )
        return "\n".join(lineas)

    def _generar_narrativa_gemini(self, resumen_texto: str,
                                   explicacion_inf: str, datos: Dict) -> str:
        prompt = f"""
Eres el Agente Supervisor de "Cafeteria IA", un sistema experto de cafeteria.
Genera un reporte claro del pedido procesado.

Informacion del pedido:
{resumen_texto}

Inferencias del sistema:
{explicacion_inf}

Genera un reporte en espanol con estas secciones:
1. RESUMEN: Una o dos oraciones sobre que pidio el cliente y el resultado.
2. DECISIONES TOMADAS: Explica las reglas aplicadas en lenguaje natural.
3. ALERTAS: Menciona alertas de stock. Si no hay, escribe "Sin alertas."
4. VALIDACION: Una linea indicando si el pedido esta listo o fue rechazado.

Tono profesional y conciso. Sin markdown. Maximo un emoji por seccion.
"""
        narrativa = self._llamar_gemini(prompt)
        return narrativa if narrativa else resumen_texto

    def generar_reporte(self, datos_agente2: Dict) -> Dict:
        estado    = datos_agente2.get("estado", "desconocido")
        pedido_id = datos_agente2.get("pedido_id")

        print(f"\n[AGENTE 3] Generando reporte — Estado: {estado} | Pedido: #{pedido_id or 'N/A'}")

        inferencias_db     = obtener_inferencias_pedido(pedido_id) if pedido_id else []
        todas_inferencias  = inferencias_db if inferencias_db else datos_agente2.get("inferencias", [])
        resumen_texto      = self._construir_resumen_texto(datos_agente2)
        explicacion_inf    = self._construir_explicacion_inferencias(todas_inferencias)

        print(f"  -> Inferencias recuperadas: {len(todas_inferencias)}")

        reporte_gemini = self._generar_narrativa_gemini(resumen_texto, explicacion_inf, datos_agente2)

        validacion = "aprobado" if estado == "confirmado" else "rechazado" if estado == "rechazado" else "revision"

        alertas_globales = verificar_stock_bajo()

        guardar_inferencia(
            pedido_id   = pedido_id,
            agente      = "supervisor",
            regla       = "GENERAR_REPORTE",
            descripcion = f"Reporte para pedido #{pedido_id}. Inferencias: {len(todas_inferencias)}.",
            resultado   = f"Validacion final: {validacion.upper()}."
        )

        return {
            "reporte_texto"   : resumen_texto,
            "reporte_gemini"  : reporte_gemini,
            "inferencias"     : todas_inferencias,
            "alertas_pedido"  : datos_agente2.get("alertas_stock", []),
            "alertas_globales": alertas_globales,
            "estado"          : estado,
            "pedido_id"       : pedido_id,
            "validacion"      : validacion,
            "cliente"         : datos_agente2.get("cliente", {}),
        }

    def imprimir_reporte(self, reporte: Dict):
        sep = "=" * 60
        print(f"\n{sep}")
        print("  REPORTE FINAL — AGENTE SUPERVISOR")
        print(sep)
        print("\n" + reporte["reporte_gemini"])
        print(f"\n{'-' * 60}")
        print("  TRAZABILIDAD DE INFERENCIAS:")
        print('-' * 60)
        for inf in reporte["inferencias"]:
            regla = inf.get("regla", inf.get("nombre", "?"))
            print(f"  [{regla}] {inf.get('resultado', inf.get('descripcion', ''))}")
        if reporte["alertas_globales"]:
            print(f"\n{'-' * 60}")
            print("  ALERTAS GLOBALES DE STOCK:")
            for a in reporte["alertas_globales"]:
                print(f"  - {a['nombre']}: {a['stock_actual']} uds (min: {a['stock_minimo']})")
        iconos = {"aprobado": "OK", "rechazado": "RECHAZADO", "revision": "REVISION"}
        print(f"\n{sep}")
        print(f"  VALIDACION FINAL: {iconos.get(reporte['validacion'], '?')}")
        print(sep + "\n")


if __name__ == "__main__":
    from database import crear_tablas
    from menu_cafe import poblar_menu
    crear_tablas()
    poblar_menu()

    agente = AgenteSupervisor()
    datos_prueba = {
        "estado": "confirmado", "pedido_id": 1,
        "cliente": {"id": 1, "nombre": "Ana Garcia", "total_pedidos": 7, "es_frecuente": 1},
        "productos_validos": [
            {"nombre": "Latte",                "precio": 55.0, "producto_id": 4,  "cantidad": 1, "personalizacion": "sin azucar"},
            {"nombre": "Brownie de Chocolate", "precio": 55.0, "producto_id": 28, "cantidad": 2, "personalizacion": None},
        ],
        "productos_sin_stock": [], "alertas_stock": [],
        "subtotal": 165.0, "descuento_pct": 0.10, "descuento_monto": 16.50,
        "motivo_descuento": "cliente frecuente", "total": 148.50,
        "inferencias": [
            {"regla": "R01", "nombre": "VERIFICAR_DISPONIBILIDAD", "descripcion": "Latte y Brownie en menu.", "resultado": "ACEPTADOS."},
            {"regla": "R05", "nombre": "CLIENTE_FRECUENTE",        "descripcion": "7 pedidos previos.",       "resultado": "DESCUENTO 10%."},
        ],
    }
    reporte = agente.generar_reporte(datos_prueba)
    agente.imprimir_reporte(reporte)