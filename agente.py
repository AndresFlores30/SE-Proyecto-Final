"""
agente_pedidos.py
=================

Agente 2 - Gestión de Pedidos

Responsabilidades:
- Verificar stock
- Crear pedido
- Guardar detalle
- Aplicar descuentos
- Reducir inventario
"""

from database import (
    obtener_o_crear_cliente,
    reducir_stock,
    guardar_inferencia,
    crear_pedido,
    agregar_detalle_pedido
)
