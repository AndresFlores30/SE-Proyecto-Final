"""
agente_atencion.py
==================
Agente 1 — Atención al Cliente
Responsabilidades:
  - Recibir el mensaje en texto libre del cliente
  - Detectar la intención (pedir, consultar menú, cancelar, saludar, etc.)
  - Extraer productos y cantidades solicitados
  - Generar una respuesta amigable
  - Todo usando Gemini API (google-generativeai)

Instalación requerida:
  pip install google-generativeai
"""

import json
import os
import re
from typing import List, Dict, Optional
from database import obtener_menu_completo, guardar_inferencia

# ─────────────────────────────────────────────
#  CONFIGURACIÓN DE GEMINI
# ─────────────────────────────────────────────
try:
    import google.generativeai as genai
    GEMINI_DISPONIBLE = True
except ImportError:
    GEMINI_DISPONIBLE = False
    print("[WARN] google-generativeai no instalado. Ejecuta: pip install google-generativeai")

# Pon aquí tu API Key de Google AI Studio (https://aistudio.google.com)
# O mejor: guárdala en variable de entorno GEMINI_API_KEY
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "TU_API_KEY_AQUI")


def _inicializar_gemini():
    """Inicializa el cliente de Gemini."""
    if not GEMINI_DISPONIBLE:
        return None
    if GEMINI_API_KEY == "TU_API_KEY_AQUI":
        print("[ERROR] Debes configurar tu GEMINI_API_KEY.")
        return None
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-1.5-flash")


# ─────────────────────────────────────────────
#  INTENCIONES RECONOCIDAS
# ─────────────────────────────────────────────
INTENCIONES = {
    "pedir"        : "El cliente quiere ordenar uno o más productos.",
    "ver_menu"     : "El cliente quiere ver el menú o saber qué hay disponible.",
    "consultar"    : "El cliente pregunta por un producto específico (precio, ingredientes, etc.).",
    "cancelar"     : "El cliente quiere cancelar su pedido actual.",
    "confirmar"    : "El cliente confirma o aprueba algo (su pedido, un resumen, etc.).",
    "saludar"      : "El cliente saluda o inicia conversación sin pedir nada.",
    "despedirse"   : "El cliente se despide.",
    "otro"         : "Intención no reconocida o fuera de contexto.",
}


# ─────────────────────────────────────────────
#  CLASE PRINCIPAL
# ─────────────────────────────────────────────
class AgenteAtencion:
    """
    Agente 1: Atención al Cliente.
    Analiza mensajes, detecta intención y extrae pedidos usando Gemini.
    """

    def __init__(self):
        self.modelo = _inicializar_gemini()
        self.menu   = obtener_menu_completo()          # carga el menú desde SQLite
        self.menu_texto = self._construir_texto_menu() # versión de texto para el prompt

    # ── HELPERS ──────────────────────────────────────────────────────────

    def _construir_texto_menu(self) -> str:
        """Convierte el menú de la DB a texto plano para el prompt de Gemini."""
        lineas = []
        categoria_actual = None
        for p in self.menu:
            if p["categoria"] != categoria_actual:
                categoria_actual = p["categoria"]
                lineas.append(f"\n[{categoria_actual}]")
            vegano    = "(vegano)"     if p["es_vegano"]    else ""
            singluten = "(sin gluten)" if p["es_sin_gluten"] else ""
            lineas.append(
                f"  - {p['nombre']}: ${p['precio']:.2f} {vegano}{singluten}"
            )
        return "\n".join(lineas)

    def _llamar_gemini(self, prompt: str) -> str:
        """Envía un prompt a Gemini y retorna el texto de respuesta."""
        if not self.modelo:
            return '{"error": "Gemini no disponible"}'
        try:
            respuesta = self.modelo.generate_content(prompt)
            return respuesta.text.strip()
        except Exception as e:
            print(f"[ERROR Gemini] {e}")
            return '{"error": "' + str(e) + '"}'

    def _limpiar_json(self, texto: str) -> str:
        """Elimina bloques markdown ```json ... ``` si Gemini los incluye."""
        texto = re.sub(r"```json\s*", "", texto)
        texto = re.sub(r"```\s*",     "", texto)
        return texto.strip()

    # ── DETECCIÓN DE INTENCIÓN ────────────────────────────────────────────

    def detectar_intencion(self, mensaje: str) -> dict:
        """
        Usa Gemini para clasificar la intención del mensaje.
        Retorna un dict con:
          - intencion   : str  (una de INTENCIONES)
          - confianza   : float (0.0 – 1.0)
          - razonamiento: str
        """
        prompt = f"""
Eres el sistema de clasificación de intenciones de una cafetería llamada "Cafetería IA".
Analiza el siguiente mensaje de un cliente y clasifica su intención.

Mensaje del cliente: "{mensaje}"

Las intenciones posibles son:
{json.dumps(INTENCIONES, ensure_ascii=False, indent=2)}

Responde ÚNICAMENTE con un objeto JSON válido (sin texto extra, sin markdown) con esta estructura:
{{
  "intencion": "<una de las intenciones listadas>",
  "confianza": <número entre 0.0 y 1.0>,
  "razonamiento": "<explicación breve en español>"
}}
"""
        respuesta_raw = self._llamar_gemini(prompt)
        try:
            return json.loads(self._limpiar_json(respuesta_raw))
        except json.JSONDecodeError:
            return {
                "intencion": "otro",
                "confianza": 0.0,
                "razonamiento": "No se pudo parsear la respuesta de Gemini."
            }

    # ── EXTRACCIÓN DE PRODUCTOS ───────────────────────────────────────────

    def extraer_productos(self, mensaje: str) -> List[Dict]:
        """
        Usa Gemini para extraer qué productos y cantidades pidió el cliente,
        mapeando contra el menú real de la cafetería.

        Retorna lista de dicts:
          [{"nombre": str, "cantidad": int, "personalizacion": str}, ...]
        """
        prompt = f"""
Eres el extractor de pedidos de "Cafetería IA".
El cliente envió este mensaje: "{mensaje}"

Este es el menú disponible:
{self.menu_texto}

Tu tarea es identificar qué productos del menú pidió el cliente y en qué cantidad.
Si el cliente menciona algo que no está en el menú, inclúyelo con nombre_menu = null.
Si el cliente no especifica cantidad, asume 1.
Incluye cualquier personalización mencionada (sin azúcar, leche de avena, etc.).

Responde ÚNICAMENTE con un JSON válido (sin texto extra, sin markdown):
{{
  "productos": [
    {{
      "nombre_mencionado": "<lo que dijo el cliente>",
      "nombre_menu": "<nombre exacto del producto en el menú, o null si no existe>",
      "cantidad": <número entero>,
      "personalizacion": "<personalizaciones o null>"
    }}
  ]
}}
"""
        respuesta_raw = self._llamar_gemini(prompt)
        try:
            data = json.loads(self._limpiar_json(respuesta_raw))
            return data.get("productos", [])
        except json.JSONDecodeError:
            return []

    # ── GENERACIÓN DE RESPUESTA ───────────────────────────────────────────

    def generar_respuesta(self, mensaje: str, contexto: dict) -> str:
        """
        Genera una respuesta amigable y en español para el cliente,
        basada en el mensaje y el contexto del análisis.

        contexto puede incluir:
          - intencion, productos_encontrados, productos_no_encontrados,
            nombre_cliente, pedido_id, etc.
        """
        contexto_str = json.dumps(contexto, ensure_ascii=False, indent=2)
        prompt = f"""
Eres el asistente virtual amigable de "Cafetería IA", una cafetería moderna y acogedora.
Respondes siempre en español, con un tono cálido, breve y profesional.
Usas emojis con moderación (1-2 por mensaje).

Mensaje del cliente: "{mensaje}"

Contexto del análisis:
{contexto_str}

Menú disponible:
{self.menu_texto}

Genera una respuesta natural para el cliente. Sigue estas reglas:
- Si la intención es "saludar": saluda y pregunta en qué puedes ayudar.
- Si la intención es "ver_menu": muestra el menú de forma organizada y atractiva.
- Si la intención es "pedir": confirma los productos encontrados y pregunta si hay algo más o si confirma el pedido.
- Si la intención es "consultar": responde la duda específica sobre el producto.
- Si la intención es "cancelar": confirma la cancelación con amabilidad.
- Si la intención es "confirmar": indica que el pedido está siendo procesado.
- Si hay productos no encontrados: sugiere alternativas del menú.
- Sé conciso (máximo 4-5 líneas).

Responde SOLO con el mensaje para el cliente, sin JSON, sin explicaciones adicionales.
"""
        return self._llamar_gemini(prompt)

    # ── MÉTODO PRINCIPAL ─────────────────────────────────────────────────

    def procesar_mensaje(self, mensaje: str, discord_id: str = "test",
                          nombre_cliente: str = "Cliente") -> dict:
        """
        Punto de entrada principal del Agente 1.
        Orquesta: detección de intención → extracción de productos → respuesta.

        Retorna un dict con toda la información para el Agente 2:
        {
          "intencion"               : str,
          "confianza"               : float,
          "razonamiento_intencion"  : str,
          "productos_solicitados"   : list,   # productos encontrados en menú
          "productos_no_encontrados": list,   # lo que pidió y no existe
          "respuesta_cliente"       : str,
          "mensaje_original"        : str,
          "discord_id"              : str,
          "nombre_cliente"          : str,
        }
        """
        print(f"\n[AGENTE 1] Procesando mensaje: '{mensaje}'")

        # 1. Detectar intención
        analisis_intencion = self.detectar_intencion(mensaje)
        intencion  = analisis_intencion.get("intencion", "otro")
        confianza  = analisis_intencion.get("confianza", 0.0)
        razon      = analisis_intencion.get("razonamiento", "")
        print(f"  → Intención detectada: {intencion} (confianza: {confianza:.0%})")
        print(f"  → Razonamiento: {razon}")

        # 2. Extraer productos si corresponde
        productos_solicitados    = []
        productos_no_encontrados = []

        if intencion in ("pedir", "consultar"):
            productos_raw = self.extraer_productos(mensaje)
            menu_nombres  = {p["nombre"].lower(): p for p in self.menu}

            for item in productos_raw:
                nombre_menu = item.get("nombre_menu")
                if nombre_menu and nombre_menu.lower() in menu_nombres:
                    producto_db = menu_nombres[nombre_menu.lower()]
                    productos_solicitados.append({
                        "nombre"         : producto_db["nombre"],
                        "precio"         : producto_db["precio"],
                        "producto_id"    : producto_db["id"],
                        "cantidad"       : item.get("cantidad", 1),
                        "personalizacion": item.get("personalizacion"),
                        "stock_actual"   : producto_db.get("stock_actual"),
                    })
                    print(f"  → Producto encontrado: {producto_db['nombre']} x{item.get('cantidad', 1)}")
                else:
                    productos_no_encontrados.append(item.get("nombre_mencionado", "?"))
                    print(f"  → Producto NO encontrado: {item.get('nombre_mencionado')}")

        # 3. Guardar inferencia en log
        guardar_inferencia(
            pedido_id   = None,
            agente      = "atencion",
            regla       = "DETECTAR_INTENCION",
            descripcion = f"Mensaje: '{mensaje}' → Intención: {intencion} ({confianza:.0%}). {razon}",
            resultado   = f"Intención clasificada como '{intencion}' con {len(productos_solicitados)} producto(s) identificado(s)."
        )

        # 4. Generar respuesta para el cliente
        contexto = {
            "intencion"               : intencion,
            "confianza"               : confianza,
            "nombre_cliente"          : nombre_cliente,
            "productos_encontrados"   : [p["nombre"] for p in productos_solicitados],
            "productos_no_encontrados": productos_no_encontrados,
        }
        respuesta = self.generar_respuesta(mensaje, contexto)
        print(f"  → Respuesta generada: {respuesta[:80]}...")

        return {
            "intencion"               : intencion,
            "confianza"               : confianza,
            "razonamiento_intencion"  : razon,
            "productos_solicitados"   : productos_solicitados,
            "productos_no_encontrados": productos_no_encontrados,
            "respuesta_cliente"       : respuesta,
            "mensaje_original"        : mensaje,
            "discord_id"              : discord_id,
            "nombre_cliente"          : nombre_cliente,
        }


# ─────────────────────────────────────────────
#  PRUEBA RÁPIDA (ejecutar directamente)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    agente = AgenteAtencion()

    casos_prueba = [
        ("hola buenas tardes!",                          "usuario_001", "Ana"),
        ("quiero un latte y dos brownies por favor",     "usuario_001", "Ana"),
        ("tienen algo vegano para desayunar?",           "usuario_002", "Carlos"),
        ("me das un frappé de mango y un croissant",     "usuario_003", "María"),
        ("cuánto cuesta el cappuccino?",                 "usuario_004", "Luis"),
        ("cancela mi pedido",                            "usuario_001", "Ana"),
    ]

    for mensaje, discord_id, nombre in casos_prueba:
        print("\n" + "═" * 60)
        resultado = agente.procesar_mensaje(mensaje, discord_id, nombre)
        print(f"\n  RESPUESTA AL CLIENTE:\n  {resultado['respuesta_cliente']}")
        print("═" * 60)
