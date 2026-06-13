"""
Agente 1 — Atencion al Cliente
Usa Gemini con reintentos automaticos ante error 429.
Si Gemini no esta disponible, usa palabras clave como fallback.
"""

import re
import json
import time
from typing import List, Dict, Optional
from config_gemini import GEMINI_API_KEY, GEMINI_MODEL
from database import obtener_menu_completo, guardar_inferencia

# ─────────────────────────────────────────────
#  CONFIGURACION DE GEMINI
# ─────────────────────────────────────────────
try:
    from google import genai
    GEMINI_DISPONIBLE = True
except ImportError:
    GEMINI_DISPONIBLE = False
    print("[WARN] google-genai no instalado. Ejecuta: pip install google-genai")

MAX_REINTENTOS = 3

def _inicializar_gemini():
    if not GEMINI_DISPONIBLE or not GEMINI_API_KEY or GEMINI_API_KEY == "TU_API_KEY_AQUI":
        return None
    try:
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        return None

# ─────────────────────────────────────────────
#  PALABRAS CLAVE
# ─────────────────────────────────────────────
PALABRAS_CLAVE = {
    "saludar"   : ["hola", "buenos", "buenas", "hey", "que tal", "saludos"],
    "despedirse": ["adios", "hasta luego", "bye", "chao", "chau", "me voy"],
    "ver_menu"  : ["menu", "carta", "que tienen", "que hay", "opciones", "ver menu"],
    "cancelar"  : ["cancela", "cancelar", "no quiero", "olvida", "anula"],
    "confirmar" : ["si", "confirmo", "ok", "dale", "adelante", "acepto", "listo"],
    "consultar" : ["cuanto cuesta", "precio de", "cuanto vale", "ingredientes", "calorias"],
    "pedir"     : ["quiero", "me das", "dame", "quisiera", "me trae", "ponme", "orden"],
}

NUMEROS_TEXTO = {
    "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}

INTENCIONES_DESC = {
    "pedir"      : "El cliente quiere ordenar uno o mas productos.",
    "ver_menu"   : "El cliente quiere ver el menu.",
    "consultar"  : "El cliente pregunta por un producto especifico.",
    "cancelar"   : "El cliente quiere cancelar su pedido.",
    "confirmar"  : "El cliente confirma su pedido.",
    "saludar"    : "El cliente saluda.",
    "despedirse" : "El cliente se despide.",
    "otro"       : "Intencion no reconocida.",
}


# ─────────────────────────────────────────────
#  CLASE PRINCIPAL
# ─────────────────────────────────────────────
class AgenteAtencion:

    def __init__(self):
        self.gemini_cliente = _inicializar_gemini()
        self.menu           = obtener_menu_completo()
        self.menu_texto     = self._construir_texto_menu()
        self._indice        = self._construir_indice()

        if self.gemini_cliente:
            print("[AGENTE 1] Gemini activo.")
        else:
            print("[AGENTE 1] Modo offline (sin Gemini).")

    # ── HELPERS ──────────────────────────────────────────────────────────

    def _normalizar(self, texto: str) -> str:
        reemplazos = {"á":"a","é":"e","í":"i","ó":"o","ú":"u",
                      "ü":"u","ñ":"n","Á":"a","É":"e","Í":"i","Ó":"o","Ú":"u","Ñ":"n"}
        texto = texto.lower()
        for a, n in reemplazos.items():
            texto = texto.replace(a, n)
        return texto

    def _construir_texto_menu(self) -> str:
        lineas = []
        categoria_actual = None
        for p in self.menu:
            if p["categoria"] != categoria_actual:
                categoria_actual = p["categoria"]
                lineas.append(f"\n[{categoria_actual}]")
            vegano    = "(vegano)"     if p["es_vegano"]    else ""
            singluten = "(sin gluten)" if p["es_sin_gluten"] else ""
            lineas.append(f"  - {p['nombre']}: ${p['precio']:.2f} {vegano}{singluten}")
        return "\n".join(lineas)

    def _construir_indice(self) -> Dict[str, dict]:
        indice = {}
        for p in self.menu:
            nombre_norm = self._normalizar(p["nombre"])
            indice[nombre_norm] = p
            for palabra in nombre_norm.split():
                if len(palabra) > 3 and palabra not in indice:
                    indice[palabra] = p
        return indice

    def _limpiar_json(self, texto: str) -> str:
        texto = re.sub(r"```json\s*", "", texto)
        texto = re.sub(r"```\s*",     "", texto)
        return texto.strip()

    # ── GEMINI CON REINTENTOS ─────────────────────────────────────────────

    def _llamar_gemini(self, prompt: str) -> Optional[str]:
        if not self.gemini_cliente:
            return None
        for intento in range(1, MAX_REINTENTOS + 1):
            try:
                resp = self.gemini_cliente.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                )
                return resp.text.strip()
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    match  = re.search(r"retryDelay.*?(\d+)s", msg)
                    espera = int(match.group(1)) + 2 if match else 30
                    if intento < MAX_REINTENTOS:
                        print(f"  [AGENTE 1] Cuota agotada. Esperando {espera}s "
                              f"(intento {intento}/{MAX_REINTENTOS})...")
                        time.sleep(espera)
                    else:
                        print("  [AGENTE 1] Gemini no disponible. Usando modo offline.")
                        return None
                else:
                    print(f"  [AGENTE 1] Error Gemini: {msg[:80]}")
                    return None
        return None

    # ── DETECCION DE INTENCION ────────────────────────────────────────────

    def detectar_intencion(self, mensaje: str) -> dict:
        prompt = f"""
Eres el clasificador de intenciones de "Cafeteria IA".
Mensaje del cliente: "{mensaje}"

Intenciones posibles:
{json.dumps(INTENCIONES_DESC, ensure_ascii=False, indent=2)}

Responde UNICAMENTE con JSON valido (sin markdown):
{{
  "intencion": "<una de las intenciones>",
  "confianza": <0.0 a 1.0>,
  "razonamiento": "<explicacion breve>"
}}
"""
        respuesta = self._llamar_gemini(prompt)
        if respuesta:
            try:
                return json.loads(self._limpiar_json(respuesta))
            except json.JSONDecodeError:
                pass
        return self._detectar_intencion_offline(mensaje)

    def _detectar_intencion_offline(self, mensaje: str) -> dict:
        msg_norm     = self._normalizar(mensaje)
        puntuaciones = {k: 0 for k in PALABRAS_CLAVE}
        for intent, palabras in PALABRAS_CLAVE.items():
            for palabra in palabras:
                if self._normalizar(palabra) in msg_norm:
                    puntuaciones[intent] += 1
        mejor      = max(puntuaciones, key=puntuaciones.get)
        max_puntos = puntuaciones[mejor]
        if max_puntos == 0:
            if self._extraer_productos_offline(mensaje):
                return {"intencion": "pedir",  "confianza": 0.7,
                        "razonamiento": "Productos detectados sin palabra clave."}
            return {"intencion": "otro",   "confianza": 0.0,
                    "razonamiento": "Sin palabras clave reconocidas."}
        return {"intencion": mejor, "confianza": min(1.0, max_puntos * 0.4),
                "razonamiento": f"Palabras clave detectadas para '{mejor}'."}

    # ── EXTRACCION DE PRODUCTOS ───────────────────────────────────────────

    def extraer_productos(self, mensaje: str) -> List[Dict]:
        prompt = f"""
Eres el extractor de pedidos de "Cafeteria IA".
Mensaje del cliente: "{mensaje}"

Menu disponible:
{self.menu_texto}

Identifica los productos del menu que pidio el cliente y sus cantidades.
Responde UNICAMENTE con JSON valido (sin markdown):
{{
  "productos": [
    {{
      "nombre_mencionado": "<texto del cliente>",
      "nombre_menu": "<nombre exacto del menu o null>",
      "cantidad": <entero>,
      "personalizacion": "<personalizacion o null>"
    }}
  ]
}}
"""
        respuesta = self._llamar_gemini(prompt)
        if respuesta:
            try:
                data = json.loads(self._limpiar_json(respuesta))
                return data.get("productos", [])
            except json.JSONDecodeError:
                pass
        return self._extraer_productos_offline(mensaje)

    def _parsear_cantidad(self, texto_antes: str) -> int:
        match = re.search(r"(\d+)\s*$", texto_antes.strip())
        if match:
            return int(match.group(1))
        for palabra, valor in NUMEROS_TEXTO.items():
            if re.search(r"\b" + palabra + r"\b", self._normalizar(texto_antes)):
                return valor
        return 1

    def _extraer_productos_offline(self, mensaje: str) -> List[dict]:
        msg_norm    = self._normalizar(mensaje)
        encontrados = {}
        for p in self.menu:
            nombre_norm = self._normalizar(p["nombre"])
            pos = msg_norm.find(nombre_norm)
            if pos >= 0:
                pid = p["id"]
                if pid not in encontrados:
                    encontrados[pid] = {
                        "nombre_mencionado": p["nombre"],
                        "nombre_menu"      : p["nombre"],
                        "cantidad"         : self._parsear_cantidad(msg_norm[:pos]),
                        "personalizacion"  : None,
                    }
        if not encontrados:
            for keyword, p in self._indice.items():
                if len(keyword) > 4 and keyword in msg_norm:
                    pid = p["id"]
                    if pid not in encontrados:
                        pos = msg_norm.find(keyword)
                        encontrados[pid] = {
                            "nombre_mencionado": keyword,
                            "nombre_menu"      : p["nombre"],
                            "cantidad"         : self._parsear_cantidad(msg_norm[:pos]),
                            "personalizacion"  : None,
                        }
        return list(encontrados.values())

    # ── GENERACION DE RESPUESTA ───────────────────────────────────────────

    def generar_respuesta(self, mensaje: str, contexto: dict) -> str:
        prompt = f"""
Eres el asistente virtual de "Cafeteria IA", una cafeteria moderna.
Respondes siempre en espanol, con tono calido y conciso. Usa 1-2 emojis.

Mensaje del cliente: "{mensaje}"
Contexto: {json.dumps(contexto, ensure_ascii=False)}
Menu: {self.menu_texto}

Reglas:
- saludar: saluda y pregunta en que puedes ayudar.
- ver_menu: muestra el menu organizado.
- pedir: confirma productos y pregunta si confirma el pedido.
- consultar: responde la duda del producto.
- cancelar: confirma la cancelacion.
- confirmar: indica que el pedido se esta procesando.
- Maximo 4-5 lineas.

Responde SOLO con el mensaje para el cliente.
"""
        respuesta = self._llamar_gemini(prompt)
        if respuesta:
            return respuesta
        return self._respuesta_offline(mensaje, contexto)

    def _respuesta_offline(self, mensaje: str, contexto: dict) -> str:
        intencion      = contexto.get("intencion", "otro")
        nombre         = contexto.get("nombre_cliente", "")
        encontrados    = contexto.get("productos_encontrados", [])
        no_encontrados = contexto.get("productos_no_encontrados", [])

        if intencion == "saludar":
            return (f"Hola{' ' + nombre if nombre else ''}! Bienvenido/a a Cafeteria IA. "
                    f"Que te puedo ofrecer hoy? Escribe tu pedido o usa !menu para ver opciones.")
        elif intencion == "ver_menu":
            lineas = ["Nuestro menu:\n"]
            cat_actual = None
            for p in self.menu:
                if p["categoria"] != cat_actual:
                    cat_actual = p["categoria"]
                    lineas.append(f"\n{cat_actual}")
                etiq = " (V)" if p["es_vegano"] else ""
                lineas.append(f"  - {p['nombre']}{etiq}: ${p['precio']:.2f}")
            lineas.append("\n(V) = vegano  |  Usa !menu para mas detalles.")
            return "\n".join(lineas)
        elif intencion == "pedir":
            if encontrados:
                menu_idx = {p["nombre"]: p["precio"] for p in self.menu}
                lineas   = ["Tu pedido:\n"]
                total    = sum(menu_idx.get(n, 0) for n in encontrados)
                for n in encontrados:
                    lineas.append(f"  - {n}: ${menu_idx.get(n, 0):.2f}")
                lineas.append(f"\nTotal estimado: ${total:.2f}")
                lineas.append("Confirmas tu pedido? Escribe 'si' para continuar.")
                if no_encontrados:
                    lineas.append(f"\nNo encontre: {', '.join(no_encontrados)}.")
                return "\n".join(lineas)
            return "Que te gustaria ordenar? Escribe el nombre del producto o usa !menu."
        elif intencion == "consultar":
            msg_norm = self._normalizar(mensaje)
            for p in self.menu:
                if self._normalizar(p["nombre"]) in msg_norm:
                    return (f"{p['nombre']} - ${p['precio']:.2f}\n"
                            f"{p.get('descripcion', '')}\n"
                            f"{p.get('calorias','?')} kcal | "
                            f"Vegano: {'Si' if p['es_vegano'] else 'No'}")
            return "Sobre que producto quieres informacion? Escribe su nombre."
        elif intencion == "confirmar":
            return "Tu pedido esta siendo procesado. Gracias!"
        elif intencion == "cancelar":
            return "Pedido cancelado. Si necesitas algo mas, aqui estoy."
        elif intencion == "despedirse":
            return "Hasta luego! Vuelve pronto a Cafeteria IA!"
        return ("No entendi bien tu mensaje. "
                "Usa !menu para ver opciones o !ayuda para ver comandos.")

    # ── METODO PRINCIPAL ─────────────────────────────────────────────────

    def procesar_mensaje(self, mensaje: str, discord_id: str = "test",
                         nombre_cliente: str = "Cliente") -> dict:
        print(f"\n[AGENTE 1] Procesando mensaje: '{mensaje}'")

        analisis  = self.detectar_intencion(mensaje)
        intencion = analisis.get("intencion", "otro")
        confianza = analisis.get("confianza", 0.0)
        razon     = analisis.get("razonamiento", "")
        print(f"  -> Intencion: {intencion} ({confianza:.0%}) | {razon}")

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
                    print(f"  -> Encontrado: {producto_db['nombre']} x{item.get('cantidad',1)}")
                else:
                    productos_no_encontrados.append(item.get("nombre_mencionado", "?"))

        guardar_inferencia(
            pedido_id   = None,
            agente      = "atencion",
            regla       = "DETECTAR_INTENCION",
            descripcion = f"Mensaje: '{mensaje}' -> Intencion: {intencion} ({confianza:.0%}). {razon}",
            resultado   = f"Clasificado como '{intencion}' con {len(productos_solicitados)} producto(s)."
        )

        contexto = {
            "intencion"               : intencion,
            "confianza"               : confianza,
            "nombre_cliente"          : nombre_cliente,
            "productos_encontrados"   : [p["nombre"] for p in productos_solicitados],
            "productos_no_encontrados": productos_no_encontrados,
        }
        respuesta = self.generar_respuesta(mensaje, contexto)
        print(f"  -> Respuesta: {respuesta[:80]}...")

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


if __name__ == "__main__":
    agente = AgenteAtencion()
    casos  = [
        ("hola buenas tardes!",                         "u001", "Ana"),
        ("quiero un latte y dos brownies de chocolate", "u001", "Ana"),
        ("tienen algo vegano para desayunar?",           "u002", "Carlos"),
        ("cuanto cuesta el cappuccino?",                 "u003", "Luis"),
        ("cancela mi pedido",                            "u001", "Ana"),
        ("quiero ver el menu",                           "u004", "Maria"),
    ]
    for msg, did, nombre in casos:
        print("\n" + "=" * 60)
        r = agente.procesar_mensaje(msg, did, nombre)
        print(f"\n  RESPUESTA:\n  {r['respuesta_cliente']}")
        print("=" * 60)