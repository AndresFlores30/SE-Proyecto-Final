# SE-Proyecto-Final
# ☕ Cafetería IA — Sistema Experto con Agentes Inteligentes

Sistema experto basado en agentes inteligentes para la gestión de pedidos de una cafetería. Implementa ingeniería del conocimiento, motor de inferencia con encadenamiento hacia adelante, base de datos SQLite y generación de reportes explicativos mediante Gemini API. Diseñado para ejecutarse de forma local y desplegarse como bot de Discord.

---

## Índice

- [Descripción del proyecto](#descripción-del-proyecto)
- [Arquitectura del sistema](#arquitectura-del-sistema)
- [Requisitos previos](#requisitos-previos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Ejecución](#ejecución)
- [Agentes y motor de inferencia](#agentes-y-motor-de-inferencia)
- [Base de datos](#base-de-datos)
- [Bot de Discord](#bot-de-discord)
- [Estructura del proyecto](#estructura-del-proyecto)

---

## Descripción del proyecto

Cafetería IA es un sistema experto moderno que simula la atención al cliente en una cafetería. Integra tres agentes inteligentes que trabajan en cadena para procesar pedidos en lenguaje natural, aplicar reglas de negocio con explicabilidad completa y generar reportes automáticos.

**Temas académicos cubiertos:**

| Tema | Implementación |
|------|---------------|
| Ingeniería del conocimiento | Menú estructurado con 37 productos, categorías y restricciones alimenticias |
| Sistemas expertos | Motor de inferencia con 8 reglas IF-THEN encadenadas |
| Motor de inferencia | Forward chaining en `agente_pedido.py` |
| Bases de datos | SQLite con 7 tablas, relaciones y log de inferencias |
| Agentes inteligentes | 3 agentes especializados con roles y comunicación entre ellos |
| IA moderna | Gemini API para NLU, extracción de entidades y generación de reportes |
| Explicabilidad | Log completo de cada inferencia con descripción y resultado |
| Arquitectura local | Todo corre en la máquina del usuario, Discord como interfaz |

---

## Arquitectura del sistema

```
Mensaje del usuario
        │
        ▼
┌─────────────────────┐
│  Agente 1           │  Detecta intención (8 tipos)
│  AgenteAtencion     │  Extrae productos y cantidades
│  agente_atencion.py │  Genera respuesta amigable (Gemini)
└────────┬────────────┘
         │ productos + intención
         ▼
┌─────────────────────┐
│  Agente 2           │  Motor de inferencia (R01–R08)
│  AgentePedido       │  Valida stock y disponibilidad
│  agente_pedido.py   │  Aplica descuentos automáticos
│                     │  Guarda pedido en SQLite
└────────┬────────────┘
         │ resultado + inferencias
         ▼
┌─────────────────────┐
│  Agente 3           │  Recupera log de inferencias
│  AgenteSupervisor   │  Genera reporte narrativo (Gemini)
│  agente_supervisor  │  Emite validación final
└────────┬────────────┘
         │
         ▼
  Respuesta al usuario
  (consola / Discord)
```

---

## Requisitos previos

- Python 3.9 o superior (recomendado: 3.14)
- Cuenta de Google para obtener Gemini API Key (gratuita)
- Cuenta de Discord y servidor propio para el bot (opcional)
- Conexión a internet para Gemini API

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/cafeteria-ia.git
cd cafeteria-ia
```

### 2. Instalar dependencias de Python

```bash
pip install google-generativeai
pip install discord.py
```

O usando el archivo de dependencias:

```bash
pip install -r requirements.txt
```

**`requirements.txt`:**
```
google-generativeai>=0.7.0
discord.py>=2.3.0
```

### 3. Inicializar la base de datos y el menú

```bash
python menu_cafe.py
```

Esto crea el archivo `cafeteria.db` con todas las tablas y el menú completo de 37 productos.

---

## Configuración

### API Key de Gemini

1. Ve a [aistudio.google.com](https://aistudio.google.com)
2. Inicia sesión con tu cuenta de Google
3. Haz clic en **Get API Key → Create API Key**
4. Copia la clave generada

**Configurar como variable de entorno (recomendado):**

```powershell
# Windows PowerShell
$env:GEMINI_API_KEY = "tu-api-key-aqui"
```

```bash
# Mac / Linux
export GEMINI_API_KEY="tu-api-key-aqui"
```

### Token de Discord (solo para el bot)

1. Ve a [discord.com/developers/applications](https://discord.com/developers/applications)
2. **New Application** → ponle nombre
3. Sección **Bot** → **Add Bot** → copia el **Token**
4. Activa los tres **Privileged Gateway Intents**: Presence, Server Members y **Message Content**
5. En **OAuth2 → URL Generator**: marca `bot` y los permisos `Send Messages`, `Read Message History`, `Embed Links`
6. Usa la URL generada para invitar el bot a tu servidor

```powershell
# Windows PowerShell
$env:DISCORD_TOKEN = "tu-token-aqui"
```

---

## Ejecución

### Modo consola (sin Discord)

```bash
python main.py
```

Selecciona la opción:
- `1` → Consola interactiva: escribe mensajes y recibe respuestas en tiempo real
- `2` → Demo automática: ejecuta 6 casos de prueba predefinidos

### Bot de Discord

```bash
python bot_discord.py
```

El bot se conecta a Discord, inicializa los agentes y queda listo para recibir mensajes.

### Probar agentes individualmente

```bash
# Solo Agente 1
python agente_atencion.py

# Solo Agente 2
python agente_pedido.py

# Solo Agente 3
python agente_supervisor.py
```

---

## Agentes y motor de inferencia

### Agente 1 — Atención al Cliente

Recibe el texto libre del usuario y realiza dos llamadas a Gemini:

1. **Clasificación de intención** entre 8 tipos: `pedir`, `ver_menu`, `consultar`, `cancelar`, `confirmar`, `saludar`, `despedirse`, `otro`
2. **Extracción de entidades**: identifica productos del menú, cantidades y personalizaciones

### Agente 2 — Motor de Inferencia (Forward Chaining)

Evalúa 8 reglas IF-THEN en cadena sobre el estado actual:

| Regla | Condición | Acción |
|-------|-----------|--------|
| R01 | Producto existe en menú | Aceptar / rechazar ítem |
| R02 | Stock >= cantidad pedida | Permitir / bloquear producto |
| R03 | Stock actual <= stock mínimo | Generar alerta de reabastecimiento |
| R04 | Stock <= 3 unidades | Alerta crítica urgente |
| R05 | Cliente con 5+ pedidos previos | Aplicar descuento del 10% |
| R06 | Subtotal >= $300 | Aplicar descuento del 5% |
| R07 | Ambos descuentos aplican | Tomar solo el mayor |
| R08 | Sin productos válidos | Rechazar pedido completo |

Cada regla disparada queda registrada en la tabla `inferencias_log` con su descripción y resultado.

### Agente 3 — Supervisor / Explicador

Recupera el log de inferencias de la base de datos y genera:

- **Reporte narrativo** en lenguaje natural (Gemini)
- **Trazabilidad completa** de cada decisión tomada
- **Alertas de stock** globales del sistema
- **Validación final**: `aprobado`, `rechazado` o `revision`

---

## Base de datos

El archivo `cafeteria.db` (SQLite) contiene 7 tablas:

```
categorias       → categorías del menú
productos        → 37 productos con precio, calorías, etiquetas
stock            → inventario con nivel mínimo por producto
clientes         → registro de usuarios con historial
pedidos          → cabecera de cada orden
detalle_pedido   → líneas de productos por pedido
inferencias_log  → log completo de decisiones de los agentes
```

La tabla `inferencias_log` es el corazón de la explicabilidad: registra cada agente, regla aplicada, descripción y resultado con timestamp.

---

## Bot de Discord

### Comandos disponibles

| Comando | Descripción |
|---------|-------------|
| Escribir en `#pedidos-cafe` | Pedido en lenguaje natural (sin prefijo) |
| `!pedir <mensaje>` | Hacer un pedido desde cualquier canal |
| `!menu` | Ver el menú completo con embeds por categoría |
| `!pedido <id>` | Ver detalle e inferencias de un pedido |
| `!historial` | Tus últimos 5 pedidos |
| `!alertas` | Ver stock bajo (solo admins) |
| `!ayuda` | Lista de todos los comandos |

### Ejemplos de uso

```
quiero un latte sin azúcar y dos brownies
me das un cappuccino y un pay de queso
¿tienen algo vegano para desayunar?
cancela mi pedido
!pedido 3
!menu
```

---

## Estructura del proyecto

```
cafeteria-ia/
├── database.py          # Base de datos SQLite y funciones de acceso
├── menu_cafe.py         # Datos del menú y población inicial de la DB
├── agente_atencion.py   # Agente 1: NLU con Gemini
├── agente_pedido.py     # Agente 2: Motor de inferencia (forward chaining)
├── agente_supervisor.py # Agente 3: Reporte y explicabilidad
├── main.py              # Orquestador + modo consola
├── bot_discord.py       # Bot de Discord
├── requirements.txt     # Dependencias Python
├── cafeteria.db         # Base de datos SQLite (se genera automáticamente)
└── README.md            # Este archivo
```

---

## Licencia

Proyecto académico — libre para uso educativo.