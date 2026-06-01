"""
menu_cafe.py
============
Puebla la base de datos con el menú completo de la Cafetería IA.
Ejecutar una sola vez para inicializar los datos.

Categorías:
  - Bebidas Calientes
  - Bebidas Frías
  - Alimentos (comida)
  - Postres
  - Extras / Complementos
"""

import sqlite3
from database import get_connection, crear_tablas, DB_PATH


# ──────────────────────────────────────────────
#  DATOS DEL MENÚ
# ──────────────────────────────────────────────

CATEGORIAS = [
    ("Bebidas Calientes", "Café, té y bebidas calientes artesanales"),
    ("Bebidas Frías",     "Frappés, smoothies, aguas y bebidas heladas"),
    ("Alimentos",        "Desayunos, sándwiches, wraps y platillos"),
    ("Postres",          "Pasteles, galletas, muffins y dulces"),
    ("Extras",           "Complementos, toppings y personalizaciones"),
]

# (nombre, descripcion, precio, categoria, calorias, es_vegano, es_sin_gluten, stock_inicial, stock_minimo)
PRODUCTOS = [

    # ── BEBIDAS CALIENTES ──────────────────────────────────────────────────
    ("Espresso",
     "Espresso doble concentrado, origen Chiapas",
     32.0, "Bebidas Calientes", 5, 1, 1, 50, 10),

    ("Americano",
     "Espresso con agua caliente, suave y equilibrado",
     38.0, "Bebidas Calientes", 10, 1, 1, 50, 10),

    ("Cappuccino",
     "Espresso con leche vaporizada y espuma cremosa",
     52.0, "Bebidas Calientes", 120, 0, 1, 40, 8),

    ("Latte",
     "Espresso con abundante leche vaporizada, perfecto para los matutinos",
     55.0, "Bebidas Calientes", 150, 0, 1, 40, 8),

    ("Mocha",
     "Espresso con chocolate belga y leche vaporizada",
     62.0, "Bebidas Calientes", 210, 0, 1, 30, 5),

    ("Macchiato de Caramelo",
     "Espresso marcado con leche y jarabe de caramelo artesanal",
     65.0, "Bebidas Calientes", 190, 0, 1, 30, 5),

    ("Matcha Latte",
     "Té matcha japonés premium con leche de avena",
     68.0, "Bebidas Calientes", 130, 1, 1, 25, 5),

    ("Chai Latte",
     "Mezcla de especias (canela, cardamomo, jengibre) con leche vaporizada",
     60.0, "Bebidas Calientes", 160, 0, 1, 25, 5),

    ("Chocolate Caliente",
     "Cacao 70% con leche entera, denso y reconfortante",
     55.0, "Bebidas Calientes", 220, 0, 1, 30, 6),

    ("Té de la Casa",
     "Selección de tés de hoja: negro, verde, rooibos o manzanilla",
     35.0, "Bebidas Calientes", 5, 1, 1, 60, 10),

    # ── BEBIDAS FRÍAS ──────────────────────────────────────────────────────
    ("Frappé Café",
     "Café helado blended con crema batida y jarabe de vainilla",
     72.0, "Bebidas Frías", 280, 0, 1, 30, 5),

    ("Frappé Matcha",
     "Matcha premium blended con leche de coco y hielo",
     78.0, "Bebidas Frías", 200, 1, 1, 25, 5),

    ("Frappé Chocolate",
     "Chocolate belga blended con crema y granillo",
     75.0, "Bebidas Frías", 320, 0, 1, 25, 5),

    ("Cold Brew",
     "Café extraído en frío durante 24 horas, suave y bajo en acidez",
     65.0, "Bebidas Frías", 15, 1, 1, 20, 4),

    ("Limonada de Menta",
     "Limones frescos, menta y agua mineral con hielo",
     42.0, "Bebidas Frías", 60, 1, 1, 40, 8),

    ("Smoothie de Fresa",
     "Fresa, plátano, yogurt natural y miel",
     68.0, "Bebidas Frías", 180, 0, 1, 20, 4),

    ("Agua de Jamaica",
     "Jamaica artesanal sin azúcar refinada, endulzada con agave",
     35.0, "Bebidas Frías", 40, 1, 1, 30, 6),

    ("Limonada Rosada",
     "Jugo de limón con frambuesa, agua mineral y albahaca",
     45.0, "Bebidas Frías", 70, 1, 1, 30, 6),

    # ── ALIMENTOS ──────────────────────────────────────────────────────────
    ("Croissant de Jamón y Queso",
     "Croissant horneado diario con jamón serrano y queso manchego",
     72.0, "Alimentos", 380, 0, 0, 20, 4),

    ("Avocado Toast",
     "Pan artesanal tostado con aguacate, huevo pochado y chile de árbol",
     95.0, "Alimentos", 420, 0, 0, 15, 3),

    ("Bagel de Salmón",
     "Bagel con queso crema, salmón ahumado, alcaparras y eneldo",
     115.0, "Alimentos", 460, 0, 0, 12, 3),

    ("Bowl de Açaí",
     "Base de açaí con granola, frutas de temporada y miel de abeja",
     110.0, "Alimentos", 390, 1, 0, 15, 3),

    ("Sándwich Club",
     "Pan brioche con pollo asado, tocino, lechuga, jitomate y mayonesa",
     105.0, "Alimentos", 550, 0, 0, 15, 3),

    ("Wrap Vegano",
     "Tortilla de espinaca con hummus, verduras asadas y germinados",
     88.0, "Alimentos", 310, 1, 0, 15, 3),

    ("Oatmeal",
     "Avena cremosa con leche de almendra, chía, mango y granola",
     75.0, "Alimentos", 340, 1, 1, 20, 4),

    ("Panini Caprese",
     "Pan ciabatta con mozzarella fresca, jitomate y albahaca, prensado",
     92.0, "Alimentos", 410, 0, 0, 12, 3),

    # ── POSTRES ────────────────────────────────────────────────────────────
    ("Pay de Queso",
     "Cheesecake cremoso con coulis de frutos rojos",
     75.0, "Postres", 420, 0, 0, 20, 4),

    ("Brownie de Chocolate",
     "Brownie denso con nuez y chocolate semi-amargo, servido tibio",
     55.0, "Postres", 350, 0, 0, 25, 5),

    ("Muffin de Arándano",
     "Muffin esponjoso con arándanos frescos y streusel de avena",
     48.0, "Postres", 280, 0, 0, 25, 5),

    ("Galleta de Avena y Chispas",
     "Galleta artesanal horneada diario con avena y chispas de chocolate",
     32.0, "Postres", 180, 0, 0, 40, 8),

    ("Tiramisú",
     "Clásico italiano con mascarpone, espresso y cacao en polvo",
     85.0, "Postres", 400, 0, 0, 15, 3),

    ("Macarons (3 piezas)",
     "Tres macarons de sabores del día: vainilla, frambuesa y pistache",
     78.0, "Postres", 240, 0, 1, 20, 4),

    # ── EXTRAS ─────────────────────────────────────────────────────────────
    ("Shot extra de espresso",
     "Un shot adicional de espresso para tu bebida",
     12.0, "Extras", 5, 1, 1, 100, 20),

    ("Leche de avena",
     "Sustituto de leche de avena artesanal (+precio de cambio)",
     15.0, "Extras", 30, 1, 1, 80, 15),

    ("Leche de almendra",
     "Sustituto de leche de almendra sin azúcar",
     15.0, "Extras", 25, 1, 1, 80, 15),

    ("Jarabe de vainilla",
     "Jarabe artesanal de vainilla de Papantla",
     10.0, "Extras", 45, 1, 1, 100, 20),

    ("Jarabe de caramelo",
     "Jarabe de caramelo salado artesanal",
     10.0, "Extras", 50, 1, 1, 100, 20),

    ("Crema batida",
     "Crema batida fresca al momento",
     12.0, "Extras", 80, 0, 1, 80, 15),
]


# ──────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL
# ──────────────────────────────────────────────

def poblar_menu():
    """Inserta categorías, productos y stock inicial en la base de datos."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Insertar categorías
    print("\n[MENÚ] Insertando categorías...")
    for nombre, descripcion in CATEGORIAS:
        cursor.execute("""
            INSERT OR IGNORE INTO categorias (nombre, descripcion)
            VALUES (?, ?)
        """, (nombre, descripcion))
    conn.commit()

    # Obtener mapa nombre → id de categorías
    cursor.execute("SELECT id, nombre FROM categorias")
    cat_map = {row["nombre"]: row["id"] for row in cursor.fetchall()}

    # 2. Insertar productos y su stock
    print("[MENÚ] Insertando productos y stock...")
    productos_insertados = 0

    for (nombre, descripcion, precio, categoria, calorias,
         es_vegano, es_sin_gluten, stock_inicial, stock_minimo) in PRODUCTOS:

        categoria_id = cat_map.get(categoria)
        if not categoria_id:
            print(f"  [WARN] Categoría no encontrada: {categoria}")
            continue

        # Insertar producto (ignora si ya existe)
        cursor.execute("""
            INSERT OR IGNORE INTO productos
                (nombre, descripcion, precio, categoria_id, disponible,
                 calorias, es_vegano, es_sin_gluten)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """, (nombre, descripcion, precio, categoria_id,
               calorias, es_vegano, es_sin_gluten))

        # Obtener id del producto
        cursor.execute("SELECT id FROM productos WHERE nombre = ?", (nombre,))
        producto_id = cursor.fetchone()["id"]

        # Insertar stock (ignora si ya existe)
        cursor.execute("""
            INSERT OR IGNORE INTO stock (producto_id, cantidad, stock_minimo, unidad)
            VALUES (?, ?, ?, 'unidades')
        """, (producto_id, stock_inicial, stock_minimo))

        productos_insertados += 1

    conn.commit()
    conn.close()

    print(f"[MENÚ] ✓ {len(CATEGORIAS)} categorías y {productos_insertados} productos insertados.")


def imprimir_menu():
    """Imprime el menú completo en consola para verificación."""
    from database import obtener_menu_completo
    menu = obtener_menu_completo()

    categoria_actual = None
    print("\n" + "═" * 60)
    print("           MENÚ — CAFETERÍA IA  ")
    print("═" * 60)

    for p in menu:
        if p["categoria"] != categoria_actual:
            categoria_actual = p["categoria"]
            print(f"\n  ▸ {categoria_actual.upper()}")
            print("  " + "─" * 50)

        vegano   = "🌱" if p["es_vegano"]    else "  "
        singluten = "🌾" if p["es_sin_gluten"] else "  "
        stock    = p["stock_actual"] if p["stock_actual"] is not None else "?"

        print(f"  {vegano}{singluten} {p['nombre']:<30} ${p['precio']:>6.2f}"
              f"   (stock: {stock})")

    print("\n  🌱 = vegano   🌾 = sin gluten")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    print("Inicializando base de datos de Cafetería IA...")
    crear_tablas()
    poblar_menu()
    imprimir_menu()
    print(f"Base de datos guardada en: {DB_PATH}")