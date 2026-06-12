"""
Orquestador principal de Cafetería IA.
Encadena los tres agentes en orden y gestiona el flujo completo:

  Mensaje del usuario
      ↓
  Agente 1 (AgenteAtencion)   → detecta intención y extrae productos
      ↓
  Agente 2 (AgentePedido)     → valida, aplica inferencias y guarda pedido
      ↓
  Agente 3 (AgenteSupervisor) → genera reporte explicado y validación final
      ↓
  Respuesta al usuario

Este archivo también sirve de base para el bot de Discord.
"""

import os
from database import crear_tablas
from menu_cafe import poblar_menu
from agente_atencion import AgenteAtencion
from agente_pedido import AgentePedido
from agente_supervisor import AgenteSupervisor


# ─────────────────────────────────────────────
#  INICIALIZACIÓN DEL SISTEMA
# ─────────────────────────────────────────────

def inicializar_sistema():
    """
    Prepara la base de datos y carga el menú si es la primera vez.
    Debe llamarse una sola vez al arrancar el sistema.
    """
    print("─" * 60)
    print("  ☕  Iniciando Cafetería IA...")
    print("─" * 60)
    crear_tablas()
    poblar_menu()
    print("[SISTEMA] Listo.\n")


# ─────────────────────────────────────────────
#  ORQUESTADOR PRINCIPAL
# ─────────────────────────────────────────────

class CafeteriaIA:
    """
    Orquestador principal del sistema experto de cafetería.
    Gestiona el ciclo de vida completo de cada mensaje/pedido.
    """

    def __init__(self):
        print("[SISTEMA] Cargando agentes...")
        self.agente1 = AgenteAtencion()
        self.agente2 = AgentePedido()
        self.agente3 = AgenteSupervisor()
        print("[SISTEMA] Los tres agentes están listos.\n")

    def procesar(self, mensaje: str,
                 discord_id: str   = "consola_001",
                 nombre_cliente: str = "Usuario") -> dict:
        """
        Procesa un mensaje completo a través de los tres agentes.

        Parámetros:
          mensaje        : texto libre del cliente
          discord_id     : ID único del usuario (Discord user ID o cualquier string)
          nombre_cliente : nombre del usuario

        Retorna un dict con:
          - respuesta_cliente : str   → mensaje de respuesta para mostrar al usuario
          - reporte           : dict  → reporte completo del Agente 3
          - intencion         : str   → intención detectada
          - pedido_id         : int | None
          - estado_pedido     : str
        """

        print("\n" + "═" * 60)
        print(f"  MENSAJE: '{mensaje}'")
        print(f"  USUARIO: {nombre_cliente} ({discord_id})")
        print("═" * 60)

        # ── AGENTE 1: Atención al Cliente ───────────────────────────────
        resultado_a1 = self.agente1.procesar_mensaje(
            mensaje        = mensaje,
            discord_id     = discord_id,
            nombre_cliente = nombre_cliente,
        )

        intencion          = resultado_a1["intencion"]
        respuesta_cliente  = resultado_a1["respuesta_cliente"]

        # Si la intención no implica crear un pedido, retornar solo la respuesta
        if intencion not in ("pedir", "confirmar"):
            print(f"\n[ORQUESTADOR] Intención '{intencion}' → solo respuesta del Agente 1.")
            return {
                "respuesta_cliente": respuesta_cliente,
                "reporte"          : None,
                "intencion"        : intencion,
                "pedido_id"        : None,
                "estado_pedido"    : "no_aplica",
            }

        # ── AGENTE 2: Generador de Pedido ───────────────────────────────
        resultado_a2 = self.agente2.procesar_pedido(resultado_a1)

        estado_pedido = resultado_a2["estado"]

        # Si el pedido fue rechazado, ajustar la respuesta al cliente
        if estado_pedido == "rechazado":
            sin_stock = resultado_a2.get("productos_sin_stock", [])
            if sin_stock:
                nombres_sin_stock = ", ".join(p["nombre"] for p in sin_stock)
                respuesta_cliente += (
                    f"\n\n⚠️ Lo siento, no tenemos stock suficiente de: "
                    f"{nombres_sin_stock}. ¿Te puedo sugerir algo más?"
                )
            else:
                respuesta_cliente += "\n\n❌ No se pudo procesar el pedido."

        # ── AGENTE 3: Supervisor / Explicador ───────────────────────────
        reporte = self.agente3.generar_reporte(resultado_a2)
        self.agente3.imprimir_reporte(reporte)

        # Enriquecer la respuesta al cliente con info del pedido confirmado
        if estado_pedido == "confirmado":
            pedido_id    = resultado_a2["pedido_id"]
            total        = resultado_a2["total"]
            desc_pct     = resultado_a2["descuento_pct"]
            motivo_desc  = resultado_a2.get("motivo_descuento")

            detalle_pago = f"\n\n✅ **Pedido #{pedido_id} confirmado**\n"
            detalle_pago += f"💰 Total: ${total:.2f}"
            if desc_pct > 0:
                detalle_pago += f" (descuento {desc_pct:.0%} por {motivo_desc})"

            respuesta_cliente += detalle_pago

        return {
            "respuesta_cliente": respuesta_cliente,
            "reporte"          : reporte,
            "intencion"        : intencion,
            "pedido_id"        : resultado_a2.get("pedido_id"),
            "estado_pedido"    : estado_pedido,
        }


# ─────────────────────────────────────────────
#  MODO CONSOLA (prueba local sin Discord)
# ─────────────────────────────────────────────

def modo_consola():
    """
    Permite probar el sistema completo desde la terminal
    simulando conversaciones de clientes.
    """
    cafeteria = CafeteriaIA()

    print("\n" + "═" * 60)
    print("  ☕  CAFETERÍA IA — MODO CONSOLA")
    print("  Escribe tu pedido o 'salir' para terminar.")
    print("═" * 60 + "\n")

    # Pedir nombre de usuario para la sesión
    nombre = input("  ¿Cómo te llamas? → ").strip() or "Cliente"
    discord_id = f"consola_{nombre.lower().replace(' ', '_')}"
    print(f"\n  Bienvenido/a, {nombre}! ¿En qué te puedo ayudar?\n")

    while True:
        try:
            mensaje = input(f"  {nombre}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  ¡Hasta luego! ☕")
            break

        if not mensaje:
            continue
        if mensaje.lower() in ("salir", "exit", "quit", "bye", "adiós"):
            print("\n  ¡Gracias por visitarnos! Hasta pronto ☕\n")
            break

        resultado = cafeteria.procesar(
            mensaje        = mensaje,
            discord_id     = discord_id,
            nombre_cliente = nombre,
        )

        print(f"\n  🤖 Cafetería IA:\n  {resultado['respuesta_cliente']}\n")


# ─────────────────────────────────────────────
#  MODO DEMO (casos de prueba automáticos)
# ─────────────────────────────────────────────

def modo_demo():
    """
    Ejecuta una serie de casos de prueba automáticos para
    demostrar el funcionamiento del sistema completo.
    """
    cafeteria = CafeteriaIA()

    casos = [
        # (mensaje, discord_id, nombre)
        ("hola, buenas tardes!",
         "demo_001", "Lucía"),

        ("¿qué tienen de vegano?",
         "demo_001", "Lucía"),

        ("quiero un latte sin azúcar y dos brownies",
         "demo_001", "Lucía"),

        ("me das un cappuccino y un pay de queso",
         "demo_002", "Roberto"),

        ("quiero 2 espressos, 3 lattes, un bagel de salmón y un tiramisú",
         "demo_003", "Carmen"),

        ("cancela mi pedido",
         "demo_001", "Lucía"),
    ]

    print("\n" + "═" * 60)
    print("  ☕  CAFETERÍA IA — MODO DEMO")
    print("═" * 60)

    for mensaje, discord_id, nombre in casos:
        resultado = cafeteria.procesar(
            mensaje        = mensaje,
            discord_id     = discord_id,
            nombre_cliente = nombre,
        )
        print(f"\n  🤖 Respuesta para {nombre}:")
        print(f"  {resultado['respuesta_cliente']}")
        print()
        input("  [Enter para continuar...]\n")


# ─────────────────────────────────────────────
#  PUNTO DE ENTRADA
# ─────────────────────────────────────────────

if __name__ == "__main__":
    inicializar_sistema()

    print("  ¿Qué modo deseas ejecutar?")
    print("  [1] Consola interactiva (escribe tus propios mensajes)")
    print("  [2] Demo automática (casos de prueba predefinidos)")
    print()

    opcion = input("  Elige una opción (1 o 2): ").strip()

    if opcion == "2":
        modo_demo()
    else:
        modo_consola()