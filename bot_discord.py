"""
bot_discord.py
==============
Bot de Discord para Cafeteria IA.
El bot NO usa Gemini — toda la logica corre offline.
Token cargado desde config_discord.py
"""

import asyncio
from datetime import datetime
from typing import Optional

try:
    import discord
    from discord.ext import commands
except ImportError:
    print("[ERROR] discord.py no instalado. Ejecuta: pip install discord.py")
    exit(1)

from config_discord import DISCORD_TOKEN, PREFIJO, CANAL_PEDIDOS_NOMBRE
from database import crear_tablas, get_connection, obtener_inferencias_pedido, obtener_menu_completo, verificar_stock_bajo
from menu_cafe import poblar_menu
from main import CafeteriaIA


# ─────────────────────────────────────────────
#  HELPERS DE FORMATO
# ─────────────────────────────────────────────

def crear_embed_menu(menu: list) -> list:
    embeds = []
    categorias = {}
    for p in menu:
        cat = p["categoria"]
        if cat not in categorias:
            categorias[cat] = []
        categorias[cat].append(p)

    iconos = {
        "Bebidas Calientes": "☕",
        "Bebidas Frias"    : "🧋",
        "Alimentos"        : "🍽️",
        "Postres"          : "🍰",
        "Extras"           : "✨",
    }
    for cat, productos in categorias.items():
        icono = iconos.get(cat, "•")
        embed = discord.Embed(
            title = f"{icono} {cat}",
            color = discord.Color.from_rgb(139, 90, 43),
        )
        for p in productos:
            etiquetas = []
            if p["es_vegano"]:    etiquetas.append("🌱 vegano")
            if p["es_sin_gluten"]: etiquetas.append("🌾 sin gluten")
            etiq_str  = f" • {', '.join(etiquetas)}" if etiquetas else ""
            stock     = p.get("stock_actual", 0)
            stock_str = "" if stock > 5 else f" ⚠️ últimas {stock}" if stock > 0 else " ❌ agotado"
            embed.add_field(
                name   = f"{p['nombre']} — ${p['precio']:.2f}{etiq_str}{stock_str}",
                value  = p.get("descripcion", ""),
                inline = False,
            )
        embeds.append(embed)
    return embeds


def crear_embed_historial(pedidos: list, nombre: str) -> discord.Embed:
    embed = discord.Embed(
        title = f"📋 Historial de {nombre}",
        color = discord.Color.blurple(),
    )
    if not pedidos:
        embed.description = "Aún no tienes pedidos registrados."
        return embed
    for p in pedidos[:5]:
        embed.add_field(
            name  = f"Pedido #{p['id']} — {p['estado'].upper()}",
            value = f"Total: ${p['total']:.2f} | {p['fecha_creacion'][:10]}",
            inline = False,
        )
    return embed


# ─────────────────────────────────────────────
#  CONFIGURACION DEL BOT
# ─────────────────────────────────────────────

intents              = discord.Intents.default()
intents.message_content = True
bot                  = commands.Bot(command_prefix=PREFIJO, intents=intents, help_command=None)
cafeteria: Optional[CafeteriaIA] = None


# ─────────────────────────────────────────────
#  EVENTOS
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    global cafeteria
    print(f"\n[BOT] Conectado como: {bot.user} (ID: {bot.user.id})")
    print(f"[BOT] Servidores: {len(bot.guilds)}")
    print("[BOT] Inicializando sistema experto...")
    cafeteria = CafeteriaIA()
    print("[BOT] Sistema listo!\n")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="☕ pedidos de cafe")
    )


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    if message.content.startswith(PREFIJO):
        return
    if CANAL_PEDIDOS_NOMBRE and message.channel.name == CANAL_PEDIDOS_NOMBRE:
        await _procesar_mensaje_libre(message)


async def _procesar_mensaje_libre(message: discord.Message):
    global cafeteria
    if not cafeteria:
        await message.reply("El sistema esta iniciando, intenta en un momento.")
        return
    async with message.channel.typing():
        discord_id     = str(message.author.id)
        nombre_cliente = message.author.display_name
        texto          = message.content.strip()
        loop           = asyncio.get_event_loop()
        resultado      = await loop.run_in_executor(
            None, lambda: cafeteria.procesar(texto, discord_id, nombre_cliente)
        )
    await _enviar_resultado(message, resultado, reply=True)


# ─────────────────────────────────────────────
#  COMANDOS
# ─────────────────────────────────────────────

@bot.command(name="ayuda", aliases=["comandos"])
async def cmd_ayuda(ctx: commands.Context):
    embed = discord.Embed(
        title       = "☕ Cafeteria IA — Comandos",
        description = f"Escribe directamente en **#{CANAL_PEDIDOS_NOMBRE}** o usa estos comandos:",
        color       = discord.Color.from_rgb(139, 90, 43),
    )
    embed.add_field(name="📝 Hacer un pedido",  value=f"`!pedir <tu pedido>` — Ej: `!pedir quiero un latte`\nO escribe en **#{CANAL_PEDIDOS_NOMBRE}**", inline=False)
    embed.add_field(name="🍽️ Ver el menu",      value="`!menu` — Muestra todos los productos", inline=False)
    embed.add_field(name="🔍 Consultar pedido", value="`!pedido <numero>` — Ej: `!pedido 5`",  inline=False)
    embed.add_field(name="📋 Historial",        value="`!historial` — Tus ultimos 5 pedidos",  inline=False)
    embed.add_field(name="❓ Ejemplos",
                    value="• `quiero un cappuccino sin azucar`\n• `me das 2 lattes y un brownie`\n• `tienen algo vegano?`\n• `cancela mi pedido`",
                    inline=False)
    embed.set_footer(text="Cafeteria IA • Sistema Experto")
    await ctx.send(embed=embed)


@bot.command(name="pedir", aliases=["order", "quiero"])
async def cmd_pedir(ctx: commands.Context, *, mensaje: str):
    global cafeteria
    if not cafeteria:
        await ctx.reply("El sistema esta iniciando, intenta en un momento.")
        return
    async with ctx.typing():
        discord_id     = str(ctx.author.id)
        nombre_cliente = ctx.author.display_name
        loop           = asyncio.get_event_loop()
        resultado      = await loop.run_in_executor(
            None, lambda: cafeteria.procesar(mensaje, discord_id, nombre_cliente)
        )
    await _enviar_resultado(ctx, resultado, reply=True)


@bot.command(name="menu", aliases=["carta", "productos"])
async def cmd_menu(ctx: commands.Context):
    async with ctx.typing():
        menu = obtener_menu_completo()
    if not menu:
        await ctx.send("No se pudo cargar el menu.")
        return
    await ctx.send("☕ **Nuestro menu:**")
    for embed in crear_embed_menu(menu):
        await ctx.send(embed=embed)


@bot.command(name="pedido", aliases=["estado", "orden"])
async def cmd_estado_pedido(ctx: commands.Context, pedido_id: int):
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, c.nombre as nombre_cliente, c.discord_id
        FROM pedidos p JOIN clientes c ON p.cliente_id = c.id
        WHERE p.id = ?
    """, (pedido_id,))
    pedido = cursor.fetchone()

    if not pedido:
        await ctx.reply(f"No encontre el pedido #{pedido_id}.")
        conn.close()
        return

    if pedido["discord_id"] != str(ctx.author.id):
        if not ctx.author.guild_permissions.administrator:
            await ctx.reply("Solo puedes consultar tus propios pedidos.")
            conn.close()
            return

    cursor.execute("""
        SELECT d.cantidad, d.precio_unit, d.subtotal, d.personalizacion, pr.nombre as producto
        FROM detalle_pedido d JOIN productos pr ON d.producto_id = pr.id
        WHERE d.pedido_id = ?
    """, (pedido_id,))
    detalle     = cursor.fetchall()
    conn.close()
    inferencias = obtener_inferencias_pedido(pedido_id)

    estado_iconos = {"pendiente": "⏳","confirmado": "✅","preparando": "👨‍🍳",
                     "listo": "🔔","entregado": "📦","cancelado": "❌"}
    icono = estado_iconos.get(pedido["estado"], "•")

    embed = discord.Embed(
        title = f"{icono} Pedido #{pedido_id}",
        color = discord.Color.green() if pedido["estado"] == "confirmado" else discord.Color.orange(),
        timestamp = datetime.now(),
    )
    embed.add_field(name="Estado",  value=pedido["estado"].upper(),        inline=True)
    embed.add_field(name="Cliente", value=pedido["nombre_cliente"],        inline=True)
    embed.add_field(name="Fecha",   value=pedido["fecha_creacion"][:10],   inline=True)

    productos_str = ""
    for d in detalle:
        pers = f" *({d['personalizacion']})*" if d["personalizacion"] else ""
        productos_str += f"• {d['producto']}{pers} x{d['cantidad']} — ${d['subtotal']:.2f}\n"
    embed.add_field(name="Productos", value=productos_str or "—", inline=False)
    embed.add_field(name="Subtotal",  value=f"${pedido['subtotal']:.2f}",  inline=True)
    embed.add_field(name="Descuento", value=f"-${pedido['descuento']:.2f}", inline=True)
    embed.add_field(name="TOTAL",     value=f"**${pedido['total']:.2f}**", inline=True)

    if inferencias:
        inf_str = "\n".join(f"`[{i['regla']}]` {i['resultado']}" for i in inferencias[:5])
        embed.add_field(name="🧠 Decisiones del sistema", value=inf_str, inline=False)

    embed.set_footer(text="Cafeteria IA • Sistema Experto")
    await ctx.reply(embed=embed)


@bot.command(name="historial", aliases=["mis_pedidos"])
async def cmd_historial(ctx: commands.Context):
    discord_id = str(ctx.author.id)
    conn       = get_connection()
    cursor     = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.estado, p.total, p.fecha_creacion
        FROM pedidos p JOIN clientes c ON p.cliente_id = c.id
        WHERE c.discord_id = ?
        ORDER BY p.fecha_creacion DESC LIMIT 5
    """, (discord_id,))
    pedidos = [dict(r) for r in cursor.fetchall()]
    conn.close()
    await ctx.reply(embed=crear_embed_historial(pedidos, ctx.author.display_name))


@bot.command(name="alertas", aliases=["stock_bajo"])
@commands.has_permissions(administrator=True)
async def cmd_alertas(ctx: commands.Context):
    alertas = verificar_stock_bajo()
    if not alertas:
        await ctx.send("✅ Todo el stock esta en niveles normales.")
        return
    embed = discord.Embed(title="⚠️ Alertas de Stock", color=discord.Color.orange())
    for a in alertas:
        nivel = "🔴 CRITICO" if a["stock_actual"] <= 3 else "🟡 Bajo"
        embed.add_field(
            name  = f"{nivel} — {a['nombre']}",
            value = f"Stock: **{a['stock_actual']}** | Minimo: {a['stock_minimo']}",
            inline=False,
        )
    await ctx.send(embed=embed)


@cmd_alertas.error
async def alertas_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("Este comando es solo para administradores.")


# ─────────────────────────────────────────────
#  HELPER ENVIAR RESULTADO
# ─────────────────────────────────────────────

async def _enviar_resultado(ctx_or_msg, resultado: dict, reply: bool = False):
    estado    = resultado.get("estado_pedido", "no_aplica")
    respuesta = resultado.get("respuesta_cliente", "")
    send_fn   = ctx_or_msg.reply if reply else ctx_or_msg.send

    if len(respuesta) > 1900:
        partes = [respuesta[i:i+1900] for i in range(0, len(respuesta), 1900)]
        for parte in partes:
            await ctx_or_msg.channel.send(parte)
    else:
        await send_fn(respuesta)


# ─────────────────────────────────────────────
#  ARRANQUE
# ─────────────────────────────────────────────

def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "TU_TOKEN_AQUI":
        print("[ERROR] Abre config_discord.py y reemplaza TU_TOKEN_AQUI con tu token real.")
        return

    print("[SISTEMA] Inicializando base de datos...")
    crear_tablas()
    poblar_menu()
    print(f"[BOT] Iniciando con prefijo '{PREFIJO}'...")
    print(f"[BOT] Canal de pedidos: #{CANAL_PEDIDOS_NOMBRE}")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()