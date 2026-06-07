"""
agente_supervisor.py
====================
Agente 3 — Supervisor / Explicador
Responsabilidades:
  - Recibir el resultado completo del Agente 2
  - Recuperar todas las inferencias del log de la DB
  - Generar un resumen legible de la venta en lenguaje natural
  - Explicar cada decisión tomada por los agentes
  - Detectar y reportar alertas de stock
  - Solicitar validación final al operador (o confirmar automáticamente)
  - Usar Gemini para generar el resumen narrativo

Este agente es el "auditor" del sistema: garantiza la explicabilidad
del razonamiento del sistema experto.
"""

import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from database import (
    get_connection,
    obtener_inferencias_pedido,
    guardar_inferencia,
    verificar_stock_bajo,
)

# ─────────────────────────────────────────────
#  CONFIGURACIÓN DE GEMINI
# ─────────────────────────────────────────────
try:
    import google.generativeai as genai
    GEMINI_DISPONIBLE = True
except ImportError:
    GEMINI_DISPONIBLE = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "TU_API_KEY_AQUI")


def _inicializar_gemini():
    if not GEMINI_DISPONIBLE:
        return None
    if GEMINI_API_KEY == "TU_API_KEY_AQUI":
        return None
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-1.5-flash")


# ─────────────────────────────────────────────
#  CLASE PRINCIPAL
# ─────────────────────────────────────────────
class AgenteSupervisor:
    """
    Agente 3: Supervisor / Explicador.
    Genera el reporte final de cada pedido con explicación de inferencias.
    """

    def __init__(self):
        self.modelo = _inicializar_gemini()

    # ── HELPERS ──────────────────────────────────────────────────────────

    def _llamar_gemini(self, prompt: str) -> str:
        if not self.modelo:
            return None
        try:
            respuesta = self.modelo.generate_content(prompt)
            return respuesta.text.strip()
        except Exception as e:
            print(f"[ERROR Gemini] {e}")
            return None

    def _limpiar_json(self, texto: str) -> str:
        texto = re.sub(r"```json\s*", "", texto)
        texto = re.sub(r"```\s*",     "", texto)
        return texto.strip()

    def _construir_resumen_texto(self, datos: Dict) -> str:
        """
        Genera un resumen en texto plano del pedido sin usar Gemini.
        Se usa como fallback o como base para el prompt de Gemini.
        """
        lineas = []
        cliente  = datos.get("cliente", {})
        estado   = datos.get("estado", "desconocido")
        pedido_id = datos.get("pedido_id")

        lineas.append(f"RESUMEN DEL PEDIDO #{pedido_id or 'N/A'}")
        lineas.append(f"Cliente      : {cliente.get('nombre', 'Desconocido')}")
        lineas.append(f"Estado       : {estado.upper()}")
        lineas.append("")

        if estado == "confirmado":
            lineas.append("PRODUCTOS ORDENADOS:")
            for p in datos.get("productos_validos", []):
                pers = f" ({p['personalizacion']})" if p.get("personalizacion") else ""
                lineas.append(
                    f"  - {p['nombre']}{pers} x{p['cantidad']} = ${p['precio'] * p['cantidad']:.2f}"
                )
            lineas.append("")
            lineas.append(f"Subtotal     : ${datos.get('subtotal', 0):.2f}")
            desc_pct = datos.get("descuento_pct", 0)
            if desc_pct > 0:
                lineas.append(
                    f"Descuento    : -{desc_pct:.0%} por {datos.get('motivo_descuento', '')} "
                    f"(${datos.get('descuento_monto', 0):.2f})"
                )
            lineas.append(f"TOTAL        : ${datos.get('total', 0):.2f}")

        elif estado == "rechazado":
            lineas.append(f"MOTIVO: {datos.get('motivo', 'Sin motivo especificado')}")
            sin_stock = datos.get("productos_sin_stock", [])
            if sin_stock:
                lineas.append("\nPRODUCTOS SIN STOCK:")
                for p in sin_stock:
                    lineas.append(
                        f"  - {p['nombre']}: solicitado {p['cantidad']}, disponible {p.get('stock_actual', 0)}"
                    )

        alertas = datos.get("alertas_stock", [])
        if alertas:
            lineas.append("\nALERTAS DE STOCK:")
            for a in alertas:
                nivel = "⚠ CRÍTICO" if a.get("nivel") == "critico" else "↓ bajo"
                lineas.append(
                    f"  [{nivel}] {a['producto']}: {a['stock_actual']} unidades restantes"
                )

        return "\n".join(lineas)

    def _construir_explicacion_inferencias(self, inferencias: List[Dict]) -> str:
        """Convierte la lista de inferencias en texto legible."""
        if not inferencias:
            return "No se registraron inferencias."

        lineas = ["INFERENCIAS EJECUTADAS:"]
        for inf in inferencias:
            lineas.append(
                f"  [{inf.get('regla', inf.get('nombre', '?'))}] "
                f"{inf.get('descripcion', '')} → {inf.get('resultado', '')}"
            )
        return "\n".join(lineas)

    # ── GENERACIÓN DEL REPORTE CON GEMINI ────────────────────────────────

    def _generar_narrativa_gemini(self, resumen_texto: str,
                                   explicacion_inf: str, datos: Dict) -> str:
        """
        Usa Gemini para generar un resumen narrativo amigable del pedido.
        """
        prompt = f"""
Eres el Agente Supervisor de "Cafetería IA", un sistema experto de cafetería.
Tu tarea es generar un reporte claro y profesional del pedido procesado.

Aquí está la información del pedido:
{resumen_texto}

Aquí están las inferencias (decisiones) que tomó el sistema:
{explicacion_inf}

Genera un reporte en español con estas secciones exactas:
1. RESUMEN: Una o dos oraciones describiendo qué pidió el cliente y el resultado.
2. DECISIONES TOMADAS: Explica en lenguaje natural (no técnico) las reglas que se aplicaron y por qué.
3. ALERTAS: Si hay alertas de stock, menciónalas claramente. Si no hay, escribe "Sin alertas."
4. VALIDACIÓN: Una línea indicando si el pedido está listo para preparar o fue rechazado.

Usa un tono profesional pero accesible. Sé conciso. No uses markdown, solo texto plano.
Usa emojis con moderación (uno por sección máximo).
"""
        narrativa = self._llamar_gemini(prompt)
        return narrativa if narrativa else resumen_texto

    # ── MÉTODO PRINCIPAL ─────────────────────────────────────────────────

    def generar_reporte(self, datos_agente2: Dict) -> Dict:
        """
        Punto de entrada principal del Agente 3.
        Recibe el dict del Agente 2 y genera el reporte final.

        Retorna:
        {
          "reporte_texto"  : str,   # resumen plano (siempre disponible)
          "reporte_gemini" : str,   # narrativa generada por Gemini
          "inferencias"    : list,  # inferencias del pedido
          "alertas_stock"  : list,
          "estado"         : str,
          "pedido_id"      : int | None,
          "validacion"     : str,   # "aprobado" | "rechazado" | "revision"
        }
        """
        estado    = datos_agente2.get("estado", "desconocido")
        pedido_id = datos_agente2.get("pedido_id")

        print(f"\n[AGENTE 3] Generando reporte — Estado: {estado} | Pedido: #{pedido_id or 'N/A'}")

        # 1. Recuperar inferencias del log de DB (si hay pedido_id)
        inferencias_db = []
        if pedido_id:
            inferencias_db = obtener_inferencias_pedido(pedido_id)

        # Combinar inferencias de DB con las del resultado del Agente 2
        inferencias_agente2 = datos_agente2.get("inferencias", [])
        todas_inferencias = inferencias_db if inferencias_db else inferencias_agente2

        # 2. Construir resumen en texto plano
        resumen_texto      = self._construir_resumen_texto(datos_agente2)
        explicacion_inf    = self._construir_explicacion_inferencias(todas_inferencias)

        print(f"  → Inferencias recuperadas: {len(todas_inferencias)}")

        # 3. Generar narrativa con Gemini
        reporte_gemini = self._generar_narrativa_gemini(
            resumen_texto, explicacion_inf, datos_agente2
        )
        if reporte_gemini and reporte_gemini != resumen_texto:
            print("  → Narrativa Gemini generada correctamente.")
        else:
            print("  → Usando resumen de texto plano (Gemini no disponible).")

        # 4. Determinar validación final
        if estado == "confirmado":
            validacion = "aprobado"
        elif estado == "rechazado":
            validacion = "rechazado"
        else:
            validacion = "revision"

        # 5. Revisar alertas globales de stock (no solo del pedido actual)
        alertas_globales = verificar_stock_bajo()
        alertas_pedido   = datos_agente2.get("alertas_stock", [])

        # 6. Guardar inferencia del supervisor en el log
        guardar_inferencia(
            pedido_id   = pedido_id,
            agente      = "supervisor",
            regla       = "GENERAR_REPORTE",
            descripcion = f"Reporte generado para pedido #{pedido_id}. Estado: {estado}. "
                          f"Inferencias analizadas: {len(todas_inferencias)}.",
            resultado   = f"Validación final: {validacion.upper()}."
        )

        reporte_final = {
            "reporte_texto"   : resumen_texto,
            "reporte_gemini"  : reporte_gemini or resumen_texto,
            "inferencias"     : todas_inferencias,
            "alertas_pedido"  : alertas_pedido,
            "alertas_globales": alertas_globales,
            "estado"          : estado,
            "pedido_id"       : pedido_id,
            "validacion"      : validacion,
            "cliente"         : datos_agente2.get("cliente", {}),
        }

        return reporte_final

    def imprimir_reporte(self, reporte: Dict):
        """Imprime el reporte final de forma legible en consola."""
        sep = "═" * 60

        print(f"\n{sep}")
        print("  📋  REPORTE FINAL — AGENTE SUPERVISOR")
        print(sep)

        # Reporte Gemini (o texto plano como fallback)
        print("\n" + reporte["reporte_gemini"])

        # Inferencias detalladas
        print(f"\n{'─' * 60}")
        print("  TRAZABILIDAD DE INFERENCIAS:")
        print('─' * 60)
        for inf in reporte["inferencias"]:
            regla = inf.get("regla", inf.get("nombre", "?"))
            print(f"  [{regla}] {inf.get('resultado', inf.get('descripcion', ''))}")

        # Alertas globales de stock
        if reporte["alertas_globales"]:
            print(f"\n{'─' * 60}")
            print("  ⚠  ALERTAS GLOBALES DE STOCK:")
            print('─' * 60)
            for a in reporte["alertas_globales"]:
                print(
                    f"  • {a['nombre']}: {a['stock_actual']} unidades "
                    f"(mínimo: {a['stock_minimo']})"
                )

        # Validación final
        iconos = {"aprobado": "✅", "rechazado": "❌", "revision": "🔍"}
        icono  = iconos.get(reporte["validacion"], "❓")
        print(f"\n{sep}")
        print(f"  {icono}  VALIDACIÓN FINAL: {reporte['validacion'].upper()}")
        print(sep + "\n")


# ─────────────────────────────────────────────
#  PRUEBA RÁPIDA
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from database import crear_tablas
    from menu_cafe import poblar_menu

    crear_tablas()
    poblar_menu()

    agente = AgenteSupervisor()

    # Simular salida del Agente 2 (pedido confirmado con descuento)
    datos_prueba = {
        "estado"      : "confirmado",
        "pedido_id"   : 1,
        "cliente"     : {
            "id"           : 1,
            "nombre"       : "Ana García",
            "total_pedidos": 7,
            "es_frecuente" : 1,
        },
        "productos_validos": [
            {
                "nombre"         : "Latte",
                "precio"         : 55.0,
                "producto_id"    : 4,
                "cantidad"       : 1,
                "personalizacion": "sin azúcar",
            },
            {
                "nombre"         : "Brownie de Chocolate",
                "precio"         : 55.0,
                "producto_id"    : 29,
                "cantidad"       : 2,
                "personalizacion": None,
            },
        ],
        "productos_sin_stock": [],
        "alertas_stock"      : [],
        "subtotal"           : 165.0,
        "descuento_pct"      : 0.10,
        "descuento_monto"    : 16.50,
        "motivo_descuento"   : "cliente frecuente",
        "total"              : 148.50,
        "inferencias": [
            {
                "regla"      : "R01",
                "nombre"     : "VERIFICAR_DISPONIBILIDAD",
                "descripcion": "Latte y Brownie encontrados en el menú.",
                "resultado"  : "ACEPTADOS: 2 productos válidos.",
            },
            {
                "regla"      : "R02",
                "nombre"     : "VERIFICAR_STOCK",
                "descripcion": "Stock suficiente para ambos productos.",
                "resultado"  : "OK: stock suficiente.",
            },
            {
                "regla"      : "R05",
                "nombre"     : "CLIENTE_FRECUENTE",
                "descripcion": "Cliente con 7 pedidos previos (>= 5).",
                "resultado"  : "DESCUENTO FRECUENTE: 10% aplicado.",
            },
            {
                "regla"      : "R06",
                "nombre"     : "PEDIDO_GRANDE",
                "descripcion": "Subtotal $165.00 < $300.00.",
                "resultado"  : "SIN DESCUENTO por monto.",
            },
            {
                "regla"      : "R07",
                "nombre"     : "SOLO_UN_DESCUENTO",
                "descripcion": "Solo descuento frecuente aplica.",
                "resultado"  : "DESCUENTO FINAL: 10% (frecuente).",
            },
        ],
    }

    print("\n" + "═" * 60)
    print("  PRUEBA AGENTE 3 — SUPERVISOR / EXPLICADOR")
    print("═" * 60)

    reporte = agente.generar_reporte(datos_prueba)
    agente.imprimir_reporte(reporte)