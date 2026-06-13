"""
agente_pedido.py
================
Agente 2 — Generador de Pedido
Motor de inferencia forward chaining con 8 reglas IF-THEN.
No usa Gemini.
"""

from datetime import datetime
from typing import List, Dict, Optional
from database import (
    get_connection, guardar_inferencia, reducir_stock,
    actualizar_cliente_frecuente, verificar_stock_bajo, obtener_o_crear_cliente,
)

# ─────────────────────────────────────────────
#  PARAMETROS DEL NEGOCIO
# ─────────────────────────────────────────────
DESCUENTO_CLIENTE_FRECUENTE = 0.10
DESCUENTO_PEDIDO_GRANDE     = 0.05
MINIMO_PEDIDO_GRANDE        = 300.0
PEDIDOS_PARA_FRECUENTE      = 5
STOCK_CRITICO               = 3

REGLAS = [
    {"id": "R01", "nombre": "VERIFICAR_DISPONIBILIDAD", "descripcion": "Verifica que cada producto exista en el menu."},
    {"id": "R02", "nombre": "VERIFICAR_STOCK",          "descripcion": "Verifica que haya stock suficiente."},
    {"id": "R03", "nombre": "STOCK_BAJO",               "descripcion": "IF stock <= minimo THEN alerta reabastecimiento."},
    {"id": "R04", "nombre": "STOCK_CRITICO",            "descripcion": f"IF stock <= {STOCK_CRITICO} THEN alerta critica."},
    {"id": "R05", "nombre": "CLIENTE_FRECUENTE",        "descripcion": f"IF pedidos >= {PEDIDOS_PARA_FRECUENTE} THEN descuento {DESCUENTO_CLIENTE_FRECUENTE:.0%}."},
    {"id": "R06", "nombre": "PEDIDO_GRANDE",            "descripcion": f"IF subtotal >= ${MINIMO_PEDIDO_GRANDE} THEN descuento {DESCUENTO_PEDIDO_GRANDE:.0%}."},
    {"id": "R07", "nombre": "SOLO_UN_DESCUENTO",        "descripcion": "IF ambos descuentos THEN aplicar el mayor."},
    {"id": "R08", "nombre": "PEDIDO_VACIO",             "descripcion": "IF sin productos validos THEN rechazar pedido."},
]


# ─────────────────────────────────────────────
#  MOTOR DE INFERENCIA
# ─────────────────────────────────────────────
class MotorInferencia:

    def __init__(self):
        self.hechos: Dict       = {}
        self.inferencias: List[Dict] = []

    def establecer_hecho(self, clave: str, valor):
        self.hechos[clave] = valor

    def obtener_hecho(self, clave: str, default=None):
        return self.hechos.get(clave, default)

    def registrar_inferencia(self, regla: dict, descripcion: str, resultado: str):
        self.inferencias.append({
            "regla"      : regla["id"],
            "nombre"     : regla["nombre"],
            "descripcion": descripcion,
            "resultado"  : resultado,
            "timestamp"  : datetime.now().isoformat(),
        })
        print(f"  [REGLA {regla['id']}] {regla['nombre']}: {resultado}")

    def ejecutar(self, productos: List[Dict], cliente: Dict) -> Dict:
        self.establecer_hecho("productos_raw",       productos)
        self.establecer_hecho("cliente",             cliente)
        self.establecer_hecho("productos_validos",   [])
        self.establecer_hecho("productos_sin_stock", [])
        self.establecer_hecho("alertas_stock",       [])
        self.establecer_hecho("descuento_pct",       0.0)
        self.establecer_hecho("motivo_descuento",    None)

        self._r01_verificar_disponibilidad()
        self._r02_verificar_stock()
        self._r03_stock_bajo()
        self._r04_stock_critico()
        self._r05_cliente_frecuente()
        self._r06_pedido_grande()
        self._r07_solo_un_descuento()
        self._r08_pedido_vacio()

        productos_validos  = self.obtener_hecho("productos_validos")
        subtotal           = sum(p["precio"] * p["cantidad"] for p in productos_validos)
        descuento_pct      = self.obtener_hecho("descuento_pct")
        descuento_monto    = round(subtotal * descuento_pct, 2)
        total              = round(subtotal - descuento_monto, 2)

        return {
            "productos_validos"   : productos_validos,
            "productos_sin_stock" : self.obtener_hecho("productos_sin_stock"),
            "alertas_stock"       : self.obtener_hecho("alertas_stock"),
            "subtotal"            : round(subtotal, 2),
            "descuento_pct"       : descuento_pct,
            "descuento_monto"     : descuento_monto,
            "motivo_descuento"    : self.obtener_hecho("motivo_descuento"),
            "total"               : total,
            "pedido_rechazado"    : self.obtener_hecho("pedido_rechazado", False),
            "motivo_rechazo"      : self.obtener_hecho("motivo_rechazo", None),
            "inferencias"         : self.inferencias,
        }

    def _r01_verificar_disponibilidad(self):
        regla   = REGLAS[0]
        validos = [p for p in self.obtener_hecho("productos_raw") if p.get("producto_id") and p.get("precio")]
        self.establecer_hecho("productos_validos", validos)
        if validos:
            self.registrar_inferencia(regla, f"{len(validos)} productos en menu.",
                                      f"ACEPTADOS: {len(validos)} producto(s).")

    def _r02_verificar_stock(self):
        regla      = REGLAS[1]
        con_stock  = []
        sin_stock  = self.obtener_hecho("productos_sin_stock")
        conn       = get_connection()
        cursor     = conn.cursor()
        for p in self.obtener_hecho("productos_validos"):
            cursor.execute("SELECT cantidad FROM stock WHERE producto_id = ?", (p["producto_id"],))
            row           = cursor.fetchone()
            stock_actual  = row["cantidad"] if row else 0
            if stock_actual >= p["cantidad"]:
                p["stock_actual"] = stock_actual
                con_stock.append(p)
                self.registrar_inferencia(regla, f"Stock '{p['nombre']}': {stock_actual} >= {p['cantidad']}.",
                                          f"OK: stock suficiente para '{p['nombre']}'.")
            else:
                sin_stock.append({**p, "stock_actual": stock_actual})
                self.registrar_inferencia(regla, f"Stock '{p['nombre']}': {stock_actual} < {p['cantidad']}.",
                                          f"SIN STOCK: '{p['nombre']}' (solo {stock_actual} uds).")
        conn.close()
        self.establecer_hecho("productos_validos",   con_stock)
        self.establecer_hecho("productos_sin_stock", sin_stock)

    def _r03_stock_bajo(self):
        regla   = REGLAS[2]
        alertas = []
        conn    = get_connection()
        cursor  = conn.cursor()
        cursor.execute("""
            SELECT p.nombre, s.cantidad, s.stock_minimo
            FROM stock s JOIN productos p ON s.producto_id = p.id
            WHERE s.cantidad <= s.stock_minimo
        """)
        for fila in cursor.fetchall():
            alertas.append({"producto": fila["nombre"], "stock_actual": fila["cantidad"],
                            "stock_minimo": fila["stock_minimo"], "nivel": "bajo"})
            self.registrar_inferencia(regla, f"'{fila['nombre']}' stock {fila['cantidad']} <= min {fila['stock_minimo']}.",
                                      f"ALERTA: reabastecer '{fila['nombre']}'.")
        conn.close()
        self.establecer_hecho("alertas_stock", alertas)

    def _r04_stock_critico(self):
        regla = REGLAS[3]
        for alerta in self.obtener_hecho("alertas_stock"):
            if alerta["stock_actual"] <= STOCK_CRITICO:
                alerta["nivel"] = "critico"
                self.registrar_inferencia(regla, f"'{alerta['producto']}' stock critico: {alerta['stock_actual']}.",
                                          f"CRITICO: '{alerta['producto']}' urgente.")

    def _r05_cliente_frecuente(self):
        regla   = REGLAS[4]
        cliente = self.obtener_hecho("cliente")
        total_pedidos = cliente.get("total_pedidos", 0)
        if total_pedidos >= PEDIDOS_PARA_FRECUENTE or cliente.get("es_frecuente"):
            self.establecer_hecho("descuento_frecuente", DESCUENTO_CLIENTE_FRECUENTE)
            self.registrar_inferencia(regla, f"{total_pedidos} pedidos previos >= {PEDIDOS_PARA_FRECUENTE}.",
                                      f"DESCUENTO FRECUENTE: {DESCUENTO_CLIENTE_FRECUENTE:.0%}.")
        else:
            self.establecer_hecho("descuento_frecuente", 0.0)
            faltantes = PEDIDOS_PARA_FRECUENTE - total_pedidos
            self.registrar_inferencia(regla, f"{total_pedidos} pedidos (faltan {faltantes}).",
                                      "SIN DESCUENTO por frecuencia.")

    def _r06_pedido_grande(self):
        regla    = REGLAS[5]
        subtotal = sum(p["precio"] * p["cantidad"] for p in self.obtener_hecho("productos_validos"))
        if subtotal >= MINIMO_PEDIDO_GRANDE:
            self.establecer_hecho("descuento_grande", DESCUENTO_PEDIDO_GRANDE)
            self.registrar_inferencia(regla, f"Subtotal ${subtotal:.2f} >= ${MINIMO_PEDIDO_GRANDE}.",
                                      f"DESCUENTO PEDIDO GRANDE: {DESCUENTO_PEDIDO_GRANDE:.0%}.")
        else:
            self.establecer_hecho("descuento_grande", 0.0)
            self.registrar_inferencia(regla, f"Subtotal ${subtotal:.2f} < ${MINIMO_PEDIDO_GRANDE}.",
                                      "SIN DESCUENTO por monto.")

    def _r07_solo_un_descuento(self):
        regla       = REGLAS[6]
        desc_frec   = self.obtener_hecho("descuento_frecuente", 0.0)
        desc_grande = self.obtener_hecho("descuento_grande",    0.0)
        if desc_frec > 0 and desc_grande > 0:
            if desc_frec >= desc_grande:
                self.establecer_hecho("descuento_pct",    desc_frec)
                self.establecer_hecho("motivo_descuento", "cliente frecuente")
                self.registrar_inferencia(regla, "Ambos descuentos aplican.",
                                          f"DESCUENTO FINAL: {desc_frec:.0%} (frecuente).")
            else:
                self.establecer_hecho("descuento_pct",    desc_grande)
                self.establecer_hecho("motivo_descuento", "pedido grande")
                self.registrar_inferencia(regla, "Ambos descuentos aplican.",
                                          f"DESCUENTO FINAL: {desc_grande:.0%} (pedido grande).")
        elif desc_frec > 0:
            self.establecer_hecho("descuento_pct",    desc_frec)
            self.establecer_hecho("motivo_descuento", "cliente frecuente")
        elif desc_grande > 0:
            self.establecer_hecho("descuento_pct",    desc_grande)
            self.establecer_hecho("motivo_descuento", "pedido grande")
        else:
            self.establecer_hecho("descuento_pct",    0.0)
            self.establecer_hecho("motivo_descuento", None)
            self.registrar_inferencia(regla, "Ningun descuento aplica.", "SIN DESCUENTO.")

    def _r08_pedido_vacio(self):
        regla = REGLAS[7]
        if not self.obtener_hecho("productos_validos"):
            self.establecer_hecho("pedido_rechazado", True)
            self.establecer_hecho("motivo_rechazo", "No hay productos validos con stock.")
            self.registrar_inferencia(regla, "Lista de productos validos vacia.",
                                      "PEDIDO RECHAZADO: sin productos disponibles.")
        else:
            self.establecer_hecho("pedido_rechazado", False)


# ─────────────────────────────────────────────
#  AGENTE PEDIDO
# ─────────────────────────────────────────────
class AgentePedido:

    def __init__(self):
        self.motor = MotorInferencia()

    def _resetear_motor(self):
        self.motor = MotorInferencia()

    def procesar_pedido(self, datos_agente1: Dict) -> Dict:
        self._resetear_motor()
        discord_id     = datos_agente1.get("discord_id", "anonimo")
        nombre_cliente = datos_agente1.get("nombre_cliente", "Cliente")
        productos      = datos_agente1.get("productos_solicitados", [])
        intencion      = datos_agente1.get("intencion", "otro")

        print(f"\n[AGENTE 2] Procesando pedido para: {nombre_cliente}")

        if intencion not in ("pedir", "confirmar"):
            return {"estado": "no_aplica", "mensaje": f"Intencion '{intencion}' no genera pedido.", "pedido_id": None}

        cliente = obtener_o_crear_cliente(discord_id, nombre_cliente)
        print(f"  -> Cliente: {cliente['nombre']} | Pedidos previos: {cliente['total_pedidos']}")
        print("\n  [MOTOR DE INFERENCIA] Ejecutando reglas...")
        resultado = self.motor.ejecutar(productos, cliente)

        if resultado["pedido_rechazado"]:
            print(f"  -> Pedido RECHAZADO: {resultado['motivo_rechazo']}")
            return {
                "estado"             : "rechazado",
                "motivo"             : resultado["motivo_rechazo"],
                "productos_sin_stock": resultado["productos_sin_stock"],
                "alertas_stock"      : resultado["alertas_stock"],
                "inferencias"        : resultado["inferencias"],
                "pedido_id"          : None,
                "cliente"            : cliente,
            }

        pedido_id = self._guardar_pedido(cliente, resultado)
        print(f"  -> Pedido #{pedido_id} guardado.")

        for p in resultado["productos_validos"]:
            if reducir_stock(p["producto_id"], p["cantidad"]):
                print(f"  -> Stock reducido: '{p['nombre']}' -{p['cantidad']}")

        self._actualizar_cliente(cliente["id"], resultado["total"])
        actualizar_cliente_frecuente(cliente["id"])

        for inf in resultado["inferencias"]:
            guardar_inferencia(pedido_id, "pedido", inf["nombre"],
                               inf["descripcion"], inf["resultado"])

        print(f"\n  -> TOTAL: ${resultado['total']:.2f} (descuento: {resultado['descuento_pct']:.0%})")

        return {
            "estado"             : "confirmado",
            "pedido_id"          : pedido_id,
            "cliente"            : cliente,
            "productos_validos"  : resultado["productos_validos"],
            "productos_sin_stock": resultado["productos_sin_stock"],
            "alertas_stock"      : resultado["alertas_stock"],
            "subtotal"           : resultado["subtotal"],
            "descuento_pct"      : resultado["descuento_pct"],
            "descuento_monto"    : resultado["descuento_monto"],
            "motivo_descuento"   : resultado["motivo_descuento"],
            "total"              : resultado["total"],
            "inferencias"        : resultado["inferencias"],
        }

    def _guardar_pedido(self, cliente: Dict, resultado: Dict) -> int:
        conn   = get_connection()
        cursor = conn.cursor()
        ahora  = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO pedidos (cliente_id, estado, subtotal, descuento, total, fecha_creacion)
            VALUES (?, 'confirmado', ?, ?, ?, ?)
        """, (cliente["id"], resultado["subtotal"], resultado["descuento_monto"],
              resultado["total"], ahora))
        pedido_id = cursor.lastrowid
        for p in resultado["productos_validos"]:
            cursor.execute("""
                INSERT INTO detalle_pedido
                    (pedido_id, producto_id, cantidad, precio_unit, subtotal, personalizacion)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (pedido_id, p["producto_id"], p["cantidad"], p["precio"],
                  round(p["precio"] * p["cantidad"], 2), p.get("personalizacion")))
        conn.commit()
        conn.close()
        return pedido_id

    def _actualizar_cliente(self, cliente_id: int, monto: float):
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE clientes SET total_pedidos = total_pedidos + 1,
            total_gastado = total_gastado + ? WHERE id = ?
        """, (monto, cliente_id))
        conn.commit()
        conn.close()


if __name__ == "__main__":
    from database import crear_tablas
    from menu_cafe import poblar_menu
    crear_tablas()
    poblar_menu()

    agente = AgentePedido()
    datos_prueba = {
        "discord_id": "usuario_001", "nombre_cliente": "Ana Garcia",
        "intencion": "pedir",
        "productos_solicitados": [
            {"nombre": "Latte",                "precio": 55.0, "producto_id": 4,  "cantidad": 1, "personalizacion": "sin azucar", "stock_actual": 40},
            {"nombre": "Brownie de Chocolate", "precio": 55.0, "producto_id": 28, "cantidad": 2, "personalizacion": None,         "stock_actual": 25},
        ],
    }
    print("\n" + "=" * 60)
    resultado = agente.procesar_pedido(datos_prueba)
    print(f"\n  Estado  : {resultado['estado']}")
    if resultado.get("pedido_id"):
        print(f"  Pedido  : #{resultado['pedido_id']}")
        print(f"  Total   : ${resultado['total']:.2f}")
        print(f"  Descuento: {resultado['descuento_pct']:.0%} ({resultado['motivo_descuento'] or 'ninguno'})")