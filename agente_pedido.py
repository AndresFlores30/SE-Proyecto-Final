"""
agente_pedido.py
================
Agente 2 — Generador de Pedido
Responsabilidades:
  - Recibir los productos detectados por el Agente 1
  - Aplicar reglas de inferencia (motor experto)
  - Validar stock, precios y disponibilidad
  - Aplicar descuentos automáticos
  - Crear y guardar el pedido en la base de datos
  - Registrar cada inferencia realizada para explicabilidad

Motor de inferencia:
  Implementa un sistema de reglas IF-THEN encadenadas hacia adelante
  (forward chaining). Cada regla tiene: nombre, condición y acción.
"""

import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from database import (
    get_connection,
    guardar_inferencia,
    reducir_stock,
    actualizar_cliente_frecuente,
    verificar_stock_bajo,
    obtener_o_crear_cliente,
)


# ─────────────────────────────────────────────
#  CONSTANTES / PARÁMETROS DEL NEGOCIO
# ─────────────────────────────────────────────
DESCUENTO_CLIENTE_FRECUENTE = 0.10   # 10% descuento
DESCUENTO_PEDIDO_GRANDE     = 0.05   # 5% si subtotal >= $300
MINIMO_PEDIDO_GRANDE        = 300.0
PEDIDOS_PARA_FRECUENTE      = 5      # pedidos necesarios para ser cliente frecuente
STOCK_CRITICO               = 3      # si stock <= este valor → alerta crítica


# ─────────────────────────────────────────────
#  DEFINICIÓN DE REGLAS DE INFERENCIA
# ─────────────────────────────────────────────
"""
Cada regla es un dict con:
  - id         : identificador único
  - nombre     : nombre legible
  - descripcion: qué evalúa la regla
Las condiciones y acciones se implementan como métodos del motor.
"""
REGLAS = [
    {
        "id"         : "R01",
        "nombre"     : "VERIFICAR_DISPONIBILIDAD",
        "descripcion": "Verifica que cada producto solicitado esté disponible en el menú.",
    },
    {
        "id"         : "R02",
        "nombre"     : "VERIFICAR_STOCK",
        "descripcion": "Verifica que haya stock suficiente de cada producto.",
    },
    {
        "id"         : "R03",
        "nombre"     : "STOCK_BAJO",
        "descripcion": "IF stock_actual <= stock_minimo THEN registrar alerta de reabastecimiento.",
    },
    {
        "id"         : "R04",
        "nombre"     : "STOCK_CRITICO",
        "descripcion": f"IF stock_actual <= {STOCK_CRITICO} THEN marcar producto como crítico.",
    },
    {
        "id"         : "R05",
        "nombre"     : "CLIENTE_FRECUENTE",
        "descripcion": f"IF total_pedidos >= {PEDIDOS_PARA_FRECUENTE} THEN aplicar descuento del {DESCUENTO_CLIENTE_FRECUENTE:.0%}.",
    },
    {
        "id"         : "R06",
        "nombre"     : "PEDIDO_GRANDE",
        "descripcion": f"IF subtotal >= ${MINIMO_PEDIDO_GRANDE} THEN aplicar descuento del {DESCUENTO_PEDIDO_GRANDE:.0%}.",
    },
    {
        "id"         : "R07",
        "nombre"     : "SOLO_UN_DESCUENTO",
        "descripcion": "IF descuento_frecuente AND descuento_grande THEN aplicar solo el mayor.",
    },
    {
        "id"         : "R08",
        "nombre"     : "PEDIDO_VACIO",
        "descripcion": "IF no hay productos válidos THEN rechazar pedido.",
    },
]


# ─────────────────────────────────────────────
#  MOTOR DE INFERENCIA
# ─────────────────────────────────────────────
class MotorInferencia:
    """
    Motor de encadenamiento hacia adelante (forward chaining).
    Evalúa cada regla en orden y acumula los hechos derivados.
    """

    def __init__(self):
        self.hechos: Dict = {}       # hechos actuales del estado
        self.inferencias: List[Dict] = []  # log de inferencias disparadas

    def establecer_hecho(self, clave: str, valor):
        self.hechos[clave] = valor

    def obtener_hecho(self, clave: str, default=None):
        return self.hechos.get(clave, default)

    def registrar_inferencia(self, regla: dict, descripcion: str, resultado: str):
        entrada = {
            "regla"      : regla["id"],
            "nombre"     : regla["nombre"],
            "descripcion": descripcion,
            "resultado"  : resultado,
            "timestamp"  : datetime.now().isoformat(),
        }
        self.inferencias.append(entrada)
        print(f"  [REGLA {regla['id']}] {regla['nombre']}: {resultado}")

    def ejecutar(self, productos: List[Dict], cliente: Dict) -> Dict:
        """
        Ejecuta todas las reglas sobre los productos y el cliente.
        Retorna un dict con el resultado completo de la inferencia.
        """
        # Cargar hechos iniciales
        self.establecer_hecho("productos_raw",    productos)
        self.establecer_hecho("cliente",          cliente)
        self.establecer_hecho("productos_validos", [])
        self.establecer_hecho("productos_sin_stock", [])
        self.establecer_hecho("alertas_stock",    [])
        self.establecer_hecho("descuento_pct",    0.0)
        self.establecer_hecho("motivo_descuento", None)

        # Ejecutar reglas en orden (forward chaining)
        self._r01_verificar_disponibilidad()
        self._r02_verificar_stock()
        self._r03_stock_bajo()
        self._r04_stock_critico()
        self._r05_cliente_frecuente()
        self._r06_pedido_grande()
        self._r07_solo_un_descuento()
        self._r08_pedido_vacio()

        # Calcular totales
        productos_validos = self.obtener_hecho("productos_validos")
        subtotal = sum(p["precio"] * p["cantidad"] for p in productos_validos)
        descuento_pct = self.obtener_hecho("descuento_pct")
        descuento_monto = round(subtotal * descuento_pct, 2)
        total = round(subtotal - descuento_monto, 2)

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

    # ── IMPLEMENTACIÓN DE REGLAS ─────────────────────────────────────────

    def _r01_verificar_disponibilidad(self):
        regla = REGLAS[0]
        productos_raw = self.obtener_hecho("productos_raw")
        validos = []
        for p in productos_raw:
            if p.get("producto_id") and p.get("precio"):
                validos.append(p)
            else:
                self.registrar_inferencia(
                    regla,
                    f"Producto '{p.get('nombre', '?')}' no encontrado en menú.",
                    f"RECHAZADO: '{p.get('nombre', '?')}' no está en el menú."
                )
        self.establecer_hecho("productos_validos", validos)
        if validos:
            nombres = ", ".join(p["nombre"] for p in validos)
            self.registrar_inferencia(
                regla,
                f"Productos en menú: {nombres}",
                f"ACEPTADOS: {len(validos)} producto(s) válido(s)."
            )

    def _r02_verificar_stock(self):
        regla = REGLAS[1]
        productos_validos  = self.obtener_hecho("productos_validos")
        con_stock          = []
        sin_stock          = self.obtener_hecho("productos_sin_stock")

        conn   = get_connection()
        cursor = conn.cursor()

        for p in productos_validos:
            cursor.execute(
                "SELECT cantidad FROM stock WHERE producto_id = ?",
                (p["producto_id"],)
            )
            row = cursor.fetchone()
            stock_actual = row["cantidad"] if row else 0

            if stock_actual >= p["cantidad"]:
                p["stock_actual"] = stock_actual
                con_stock.append(p)
                self.registrar_inferencia(
                    regla,
                    f"Stock de '{p['nombre']}': {stock_actual} disponibles, se piden {p['cantidad']}.",
                    f"OK: stock suficiente para '{p['nombre']}'."
                )
            else:
                sin_stock.append({**p, "stock_actual": stock_actual})
                self.registrar_inferencia(
                    regla,
                    f"Stock de '{p['nombre']}': {stock_actual} disponibles, se piden {p['cantidad']}.",
                    f"SIN STOCK: '{p['nombre']}' — solo hay {stock_actual} unidad(es)."
                )

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
        filas = cursor.fetchall()
        conn.close()

        for fila in filas:
            alertas.append({
                "producto"    : fila["nombre"],
                "stock_actual": fila["cantidad"],
                "stock_minimo": fila["stock_minimo"],
                "nivel"       : "bajo",
            })
            self.registrar_inferencia(
                regla,
                f"'{fila['nombre']}' tiene stock {fila['cantidad']} <= mínimo {fila['stock_minimo']}.",
                f"ALERTA: reabastecer '{fila['nombre']}' (stock bajo)."
            )

        self.establecer_hecho("alertas_stock", alertas)

    def _r04_stock_critico(self):
        regla   = REGLAS[3]
        alertas = self.obtener_hecho("alertas_stock")

        for alerta in alertas:
            if alerta["stock_actual"] <= STOCK_CRITICO:
                alerta["nivel"] = "critico"
                self.registrar_inferencia(
                    regla,
                    f"'{alerta['producto']}' tiene stock crítico: {alerta['stock_actual']} unidades.",
                    f"CRÍTICO: '{alerta['producto']}' necesita reabastecimiento URGENTE."
                )

    def _r05_cliente_frecuente(self):
        regla   = REGLAS[4]
        cliente = self.obtener_hecho("cliente")
        total_pedidos = cliente.get("total_pedidos", 0)

        if total_pedidos >= PEDIDOS_PARA_FRECUENTE or cliente.get("es_frecuente"):
            self.establecer_hecho("descuento_frecuente", DESCUENTO_CLIENTE_FRECUENTE)
            self.registrar_inferencia(
                regla,
                f"Cliente '{cliente.get('nombre')}' tiene {total_pedidos} pedidos previos.",
                f"DESCUENTO FRECUENTE: {DESCUENTO_CLIENTE_FRECUENTE:.0%} aplicado."
            )
        else:
            self.establecer_hecho("descuento_frecuente", 0.0)
            faltantes = PEDIDOS_PARA_FRECUENTE - total_pedidos
            self.registrar_inferencia(
                regla,
                f"Cliente con {total_pedidos} pedidos (faltan {faltantes} para frecuente).",
                "SIN DESCUENTO por frecuencia (aún no califica)."
            )

    def _r06_pedido_grande(self):
        regla             = REGLAS[5]
        productos_validos = self.obtener_hecho("productos_validos")
        subtotal          = sum(p["precio"] * p["cantidad"] for p in productos_validos)

        if subtotal >= MINIMO_PEDIDO_GRANDE:
            self.establecer_hecho("descuento_grande", DESCUENTO_PEDIDO_GRANDE)
            self.registrar_inferencia(
                regla,
                f"Subtotal ${subtotal:.2f} >= ${MINIMO_PEDIDO_GRANDE} (pedido grande).",
                f"DESCUENTO PEDIDO GRANDE: {DESCUENTO_PEDIDO_GRANDE:.0%} aplicado."
            )
        else:
            self.establecer_hecho("descuento_grande", 0.0)
            self.registrar_inferencia(
                regla,
                f"Subtotal ${subtotal:.2f} < ${MINIMO_PEDIDO_GRANDE}.",
                "SIN DESCUENTO por monto (pedido no supera el mínimo)."
            )

    def _r07_solo_un_descuento(self):
        regla      = REGLAS[6]
        desc_frec  = self.obtener_hecho("descuento_frecuente", 0.0)
        desc_grande = self.obtener_hecho("descuento_grande",   0.0)

        if desc_frec > 0 and desc_grande > 0:
            # Aplicar solo el mayor
            if desc_frec >= desc_grande:
                self.establecer_hecho("descuento_pct",    desc_frec)
                self.establecer_hecho("motivo_descuento", "cliente frecuente")
                self.registrar_inferencia(
                    regla,
                    "Ambos descuentos aplican. Se elige el mayor.",
                    f"DESCUENTO FINAL: {desc_frec:.0%} (frecuente > pedido grande)."
                )
            else:
                self.establecer_hecho("descuento_pct",    desc_grande)
                self.establecer_hecho("motivo_descuento", "pedido grande")
                self.registrar_inferencia(
                    regla,
                    "Ambos descuentos aplican. Se elige el mayor.",
                    f"DESCUENTO FINAL: {desc_grande:.0%} (pedido grande > frecuente)."
                )
        elif desc_frec > 0:
            self.establecer_hecho("descuento_pct",    desc_frec)
            self.establecer_hecho("motivo_descuento", "cliente frecuente")
        elif desc_grande > 0:
            self.establecer_hecho("descuento_pct",    desc_grande)
            self.establecer_hecho("motivo_descuento", "pedido grande")
        else:
            self.establecer_hecho("descuento_pct",    0.0)
            self.establecer_hecho("motivo_descuento", None)
            self.registrar_inferencia(
                regla,
                "Ningún descuento aplica.",
                "SIN DESCUENTO en este pedido."
            )

    def _r08_pedido_vacio(self):
        regla             = REGLAS[7]
        productos_validos = self.obtener_hecho("productos_validos")

        if not productos_validos:
            self.establecer_hecho("pedido_rechazado", True)
            self.establecer_hecho(
                "motivo_rechazo",
                "No hay productos válidos con stock disponible en el pedido."
            )
            self.registrar_inferencia(
                regla,
                "Lista de productos válidos vacía.",
                "PEDIDO RECHAZADO: sin productos disponibles."
            )
        else:
            self.establecer_hecho("pedido_rechazado", False)


# ─────────────────────────────────────────────
#  CLASE PRINCIPAL DEL AGENTE
# ─────────────────────────────────────────────
class AgentePedido:
    """
    Agente 2: Generador de Pedido.
    Usa el MotorInferencia para validar y crear pedidos en la DB.
    """

    def __init__(self):
        self.motor = MotorInferencia()

    def _resetear_motor(self):
        """Crea una instancia nueva del motor para cada pedido."""
        self.motor = MotorInferencia()

    def procesar_pedido(self, datos_agente1: Dict) -> Dict:
        """
        Punto de entrada principal del Agente 2.
        Recibe el dict del Agente 1 y retorna el resultado completo del pedido.
        """
        self._resetear_motor()

        discord_id      = datos_agente1.get("discord_id", "anonimo")
        nombre_cliente  = datos_agente1.get("nombre_cliente", "Cliente")
        productos       = datos_agente1.get("productos_solicitados", [])
        intencion       = datos_agente1.get("intencion", "otro")

        print(f"\n[AGENTE 2] Procesando pedido para: {nombre_cliente}")
        print(f"  → Intención recibida: {intencion}")
        print(f"  → Productos recibidos: {len(productos)}")

        # Si no es un pedido, no procesar
        if intencion not in ("pedir", "confirmar"):
            return {
                "estado"   : "no_aplica",
                "mensaje"  : f"Intención '{intencion}' no genera pedido.",
                "pedido_id": None,
            }

        # Obtener o crear cliente en DB
        cliente = obtener_o_crear_cliente(discord_id, nombre_cliente)
        print(f"  → Cliente: {cliente['nombre']} | Pedidos previos: {cliente['total_pedidos']}")

        # Ejecutar motor de inferencia
        print("\n  [MOTOR DE INFERENCIA] Ejecutando reglas...")
        resultado = self.motor.ejecutar(productos, cliente)

        # Si el pedido fue rechazado, retornar sin guardar
        if resultado["pedido_rechazado"]:
            print(f"  → Pedido RECHAZADO: {resultado['motivo_rechazo']}")
            return {
                "estado"              : "rechazado",
                "motivo"              : resultado["motivo_rechazo"],
                "productos_sin_stock" : resultado["productos_sin_stock"],
                "alertas_stock"       : resultado["alertas_stock"],
                "inferencias"         : resultado["inferencias"],
                "pedido_id"           : None,
                "cliente"             : cliente,
            }

        # Guardar pedido en base de datos
        pedido_id = self._guardar_pedido(cliente, resultado)
        print(f"  → Pedido #{pedido_id} guardado en DB.")

        # Reducir stock de cada producto
        for p in resultado["productos_validos"]:
            exito = reducir_stock(p["producto_id"], p["cantidad"])
            if exito:
                print(f"  → Stock reducido: '{p['nombre']}' -{p['cantidad']}")

        # Actualizar contador del cliente
        self._actualizar_cliente(cliente["id"], resultado["total"])
        actualizar_cliente_frecuente(cliente["id"])

        # Guardar todas las inferencias en el log de DB
        for inf in resultado["inferencias"]:
            guardar_inferencia(
                pedido_id   = pedido_id,
                agente      = "pedido",
                regla       = inf["nombre"],
                descripcion = inf["descripcion"],
                resultado   = inf["resultado"],
            )

        print(f"\n  → TOTAL: ${resultado['total']:.2f} "
              f"(descuento: {resultado['descuento_pct']:.0%})")

        return {
            "estado"              : "confirmado",
            "pedido_id"           : pedido_id,
            "cliente"             : cliente,
            "productos_validos"   : resultado["productos_validos"],
            "productos_sin_stock" : resultado["productos_sin_stock"],
            "alertas_stock"       : resultado["alertas_stock"],
            "subtotal"            : resultado["subtotal"],
            "descuento_pct"       : resultado["descuento_pct"],
            "descuento_monto"     : resultado["descuento_monto"],
            "motivo_descuento"    : resultado["motivo_descuento"],
            "total"               : resultado["total"],
            "inferencias"         : resultado["inferencias"],
        }

    def _guardar_pedido(self, cliente: Dict, resultado: Dict) -> int:
        """Inserta el pedido y su detalle en la base de datos."""
        conn   = get_connection()
        cursor = conn.cursor()
        ahora  = datetime.now().isoformat()

        # Insertar cabecera del pedido
        cursor.execute("""
            INSERT INTO pedidos
                (cliente_id, estado, subtotal, descuento, total, fecha_creacion)
            VALUES (?, 'confirmado', ?, ?, ?, ?)
        """, (
            cliente["id"],
            resultado["subtotal"],
            resultado["descuento_monto"],
            resultado["total"],
            ahora,
        ))
        pedido_id = cursor.lastrowid

        # Insertar líneas del detalle
        for p in resultado["productos_validos"]:
            subtotal_linea = round(p["precio"] * p["cantidad"], 2)
            cursor.execute("""
                INSERT INTO detalle_pedido
                    (pedido_id, producto_id, cantidad, precio_unit, subtotal, personalizacion)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                pedido_id,
                p["producto_id"],
                p["cantidad"],
                p["precio"],
                subtotal_linea,
                p.get("personalizacion"),
            ))

        conn.commit()
        conn.close()
        return pedido_id

    def _actualizar_cliente(self, cliente_id: int, monto: float):
        """Incrementa el contador de pedidos y el total gastado del cliente."""
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE clientes
            SET total_pedidos = total_pedidos + 1,
                total_gastado = total_gastado + ?
            WHERE id = ?
        """, (monto, cliente_id))
        conn.commit()
        conn.close()


# ─────────────────────────────────────────────
#  PRUEBA RÁPIDA
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from database import crear_tablas
    from menu_cafe import poblar_menu

    # Asegurar que la DB existe
    crear_tablas()
    poblar_menu()

    agente = AgentePedido()

    # Simular salida del Agente 1 (pedido normal)
    datos_prueba = {
        "discord_id"    : "usuario_001",
        "nombre_cliente": "Ana García",
        "intencion"     : "pedir",
        "productos_solicitados": [
            {
                "nombre"         : "Latte",
                "precio"         : 55.0,
                "producto_id"    : 4,
                "cantidad"       : 1,
                "personalizacion": "sin azúcar",
                "stock_actual"   : 40,
            },
            {
                "nombre"         : "Brownie de Chocolate",
                "precio"         : 55.0,
                "producto_id"    : 29,
                "cantidad"       : 2,
                "personalizacion": None,
                "stock_actual"   : 25,
            },
        ],
    }

    print("\n" + "═" * 60)
    print("  PRUEBA AGENTE 2 — GENERADOR DE PEDIDO")
    print("═" * 60)

    resultado = agente.procesar_pedido(datos_prueba)

    print("\n── RESULTADO FINAL ──")
    print(f"  Estado   : {resultado['estado']}")
    if resultado.get("pedido_id"):
        print(f"  Pedido # : {resultado['pedido_id']}")
        print(f"  Subtotal : ${resultado['subtotal']:.2f}")
        print(f"  Descuento: {resultado['descuento_pct']:.0%} "
              f"(${resultado['descuento_monto']:.2f}) — {resultado['motivo_descuento'] or 'ninguno'}")
        print(f"  TOTAL    : ${resultado['total']:.2f}")

    print(f"\n  Inferencias ejecutadas: {len(resultado.get('inferencias', []))}")
    for inf in resultado.get("inferencias", []):
        print(f"    [{inf['regla']}] {inf['resultado']}")