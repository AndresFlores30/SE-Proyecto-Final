"""
Módulo de base de datos para el sistema experto de Cafetería IA.
Gestiona la conexión a SQLite y la creación de todas las tablas.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = "cafeteria.db"


def get_connection():
    """Retorna una conexión a la base de datos SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # permite acceder columnas por nombre
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def crear_tablas():
    """Crea todas las tablas del sistema si no existen."""
    conn = get_connection()
    cursor = conn.cursor()

    # ----- TABLA: categorias -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT NOT NULL UNIQUE,
            descripcion TEXT
        )
    """)

    # ----- TABLA: productos -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre       TEXT NOT NULL UNIQUE,
            descripcion  TEXT,
            precio       REAL NOT NULL,
            categoria_id INTEGER NOT NULL,
            disponible   INTEGER NOT NULL DEFAULT 1,  -- 1 = sí, 0 = no
            calorias     INTEGER,
            es_vegano    INTEGER NOT NULL DEFAULT 0,
            es_sin_gluten INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (categoria_id) REFERENCES categorias(id)
        )
    """)

    # ----- TABLA: stock -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL UNIQUE,
            cantidad    INTEGER NOT NULL DEFAULT 0,
            stock_minimo INTEGER NOT NULL DEFAULT 5,
            unidad      TEXT NOT NULL DEFAULT 'unidades',
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    """)

    # ----- TABLA: clientes -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id      TEXT UNIQUE,        -- ID de usuario en Discord
            nombre          TEXT NOT NULL,
            email           TEXT,
            total_pedidos   INTEGER NOT NULL DEFAULT 0,
            total_gastado   REAL NOT NULL DEFAULT 0.0,
            es_frecuente    INTEGER NOT NULL DEFAULT 0,  -- 1 si >= 5 pedidos
            fecha_registro  TEXT NOT NULL
        )
    """)

    # ----- TABLA: pedidos -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id      INTEGER NOT NULL,
            estado          TEXT NOT NULL DEFAULT 'pendiente',
            -- estados: pendiente, confirmado, preparando, listo, entregado, cancelado
            subtotal        REAL NOT NULL DEFAULT 0.0,
            descuento       REAL NOT NULL DEFAULT 0.0,
            total           REAL NOT NULL DEFAULT 0.0,
            notas           TEXT,
            fecha_creacion  TEXT NOT NULL,
            fecha_actualizacion TEXT,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        )
    """)

    # ----- TABLA: detalle_pedido -----
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detalle_pedido (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id   INTEGER NOT NULL,
            producto_id INTEGER NOT NULL,
            cantidad    INTEGER NOT NULL,
            precio_unit REAL NOT NULL,
            subtotal    REAL NOT NULL,
            personalizacion TEXT,  -- ej: "sin azúcar", "leche de avena"
            FOREIGN KEY (pedido_id)   REFERENCES pedidos(id),
            FOREIGN KEY (producto_id) REFERENCES productos(id)
        )
    """)

    # ----- TABLA: inferencias_log -----
    # Guarda cada decisión/inferencia que tomaron los agentes (explicabilidad)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inferencias_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id   INTEGER,
            agente      TEXT NOT NULL,   -- 'atencion', 'pedido', 'supervisor'
            regla       TEXT NOT NULL,   -- nombre de la regla aplicada
            descripcion TEXT NOT NULL,   -- explicación en lenguaje natural
            resultado   TEXT NOT NULL,   -- acción tomada
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Tablas creadas correctamente.")


# ──────────────────────────────────────────────
#  FUNCIONES DE CONSULTA GENERALES
# ──────────────────────────────────────────────

def obtener_menu_completo():
    """Retorna todos los productos disponibles con su categoría y stock."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            p.id,
            p.nombre,
            p.descripcion,
            p.precio,
            c.nombre AS categoria,
            p.disponible,
            p.calorias,
            p.es_vegano,
            p.es_sin_gluten,
            s.cantidad AS stock_actual,
            s.stock_minimo
        FROM productos p
        JOIN categorias c ON p.categoria_id = c.id
        LEFT JOIN stock s ON s.producto_id = p.id
        WHERE p.disponible = 1
        ORDER BY c.nombre, p.nombre
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_producto_por_nombre(nombre: str):
    """Busca un producto por nombre (búsqueda parcial, sin importar mayúsculas)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            p.id, p.nombre, p.descripcion, p.precio,
            c.nombre AS categoria, p.disponible,
            s.cantidad AS stock_actual
        FROM productos p
        JOIN categorias c ON p.categoria_id = c.id
        LEFT JOIN stock s ON s.producto_id = p.id
        WHERE LOWER(p.nombre) LIKE LOWER(?)
    """, (f"%{nombre}%",))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def obtener_o_crear_cliente(discord_id: str, nombre: str):
    """Busca un cliente por su discord_id; si no existe, lo crea."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM clientes WHERE discord_id = ?", (discord_id,))
    cliente = cursor.fetchone()

    if not cliente:
        ahora = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO clientes (discord_id, nombre, fecha_registro)
            VALUES (?, ?, ?)
        """, (discord_id, nombre, ahora))
        conn.commit()
        cursor.execute("SELECT * FROM clientes WHERE discord_id = ?", (discord_id,))
        cliente = cursor.fetchone()
        print(f"[DB] Nuevo cliente registrado: {nombre}")

    conn.close()
    return dict(cliente)


def actualizar_cliente_frecuente(cliente_id: int):
    """
    Regla de inferencia: si el cliente tiene >= 5 pedidos, 
    se marca como frecuente automáticamente.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE clientes
        SET es_frecuente = CASE WHEN total_pedidos >= 5 THEN 1 ELSE 0 END
        WHERE id = ?
    """, (cliente_id,))
    conn.commit()
    conn.close()


def reducir_stock(producto_id: int, cantidad: int):
    """Reduce el stock de un producto tras confirmar un pedido."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE stock
        SET cantidad = cantidad - ?
        WHERE producto_id = ? AND cantidad >= ?
    """, (cantidad, producto_id, cantidad))
    afectadas = cursor.rowcount
    conn.commit()
    conn.close()
    return afectadas > 0  # False si no había suficiente stock


def verificar_stock_bajo():
    """
    Retorna lista de productos cuyo stock actual está por debajo del mínimo.
    Usado por el Agente Supervisor para generar alertas.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.nombre, s.cantidad, s.stock_minimo, s.unidad
        FROM stock s
        JOIN productos p ON s.producto_id = p.id
        WHERE s.cantidad < s.stock_minimo
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def guardar_inferencia(pedido_id, agente: str, regla: str, descripcion: str, resultado: str):
    """Registra una inferencia/decisión de un agente en el log."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO inferencias_log (pedido_id, agente, regla, descripcion, resultado, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (pedido_id, agente, regla, descripcion, resultado, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def obtener_inferencias_pedido(pedido_id: int):
    """Recupera todas las inferencias registradas para un pedido específico."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT agente, regla, descripcion, resultado, timestamp
        FROM inferencias_log
        WHERE pedido_id = ?
        ORDER BY timestamp
    """, (pedido_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    crear_tablas()
    print("[DB] Base de datos inicializada en:", os.path.abspath(DB_PATH))