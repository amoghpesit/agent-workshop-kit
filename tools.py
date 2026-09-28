"""
tools.py - The backend "service layer" AND the agent's tools.

Key idea of the workshop:
    The SAME Python functions power the normal website (REST API)
    and the AI agent (tool calls). The agent never touches the
    database directly - it can only call the tools we expose here,
    and every tool validates its own inputs.

Each tool has two parts:
    1. A JSON schema (TOOL_SCHEMAS) - this is what the LLM "sees".
       The description is effectively a prompt: write it carefully!
    2. A Python function - this is what actually runs on our server.
"""
import datetime
import re

from db import get_conn

TABLES_PER_SLOT = 8          # how many tables the cafe has for each time slot
MAX_PARTY_SIZE = 8
OPEN_HOUR, CLOSE_HOUR = 11, 22  # bookings allowed 11:00 to 21:00 (last slot)

CAFE_INFO = {
    "hours": "Open every day, 7:00 AM to 10:30 PM. Table bookings: 11:00 AM to 9:00 PM, on the hour.",
    "location": "12 Race Course Road, Coimbatore 641018 (fictional address for this workshop).",
    "wifi": "Free Wi-Fi for customers. Ask the counter for the password.",
    "parking": "Two-wheeler parking in front; car parking in the lane behind the cafe.",
    "delivery": "We deliver within 5 km. Minimum order Rs 150. Delivery is free above Rs 400.",
    "payment": "UPI, cards and cash accepted.",
}


class ToolError(Exception):
    """Raised when a tool receives invalid input. The message is shown to the LLM."""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _parse_date(value):
    value = (value or "").strip().lower()
    today = datetime.date.today()
    if value in ("today", ""):
        return today
    if value == "tomorrow":
        return today + datetime.timedelta(days=1)
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"Invalid date '{value}'. Use YYYY-MM-DD, 'today' or 'tomorrow'.")


def _parse_time(value):
    value = (value or "").strip().lower().replace(".", ":")
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", value)
    if not m:
        raise ToolError(f"Invalid time '{value}'. Use 24-hour HH:MM, e.g. 19:00.")
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if minute != 0:
        raise ToolError("Bookings are only available on the hour (e.g. 19:00).")
    if not (OPEN_HOUR <= hour < CLOSE_HOUR):
        raise ToolError("Bookings are only available between 11:00 and 21:00.")
    return f"{hour:02d}:00"


def _mask_phone(phone):
    return "******" + phone[-4:] if phone else ""


# --------------------------------------------------------------------------
# Tool implementations (also used by the REST API in server.py)
# --------------------------------------------------------------------------
def search_menu(query="", veg_only=False, max_price=None, category=""):
    sql = "SELECT name, category, price, veg, spicy, available, description FROM menu WHERE 1=1"
    params = []
    if query:
        # Match any word of the query against name / category / description
        words = [w for w in re.findall(r"[a-zA-Z]+", query.lower()) if len(w) > 2]
        if words:
            sql += " AND (" + " OR ".join(
                ["lower(name || ' ' || category || ' ' || description) LIKE ?"] * len(words)) + ")"
            params += [f"%{w}%" for w in words]
    if veg_only:
        sql += " AND veg = 1"
    if max_price not in (None, ""):
        sql += " AND price <= ?"
        params.append(int(max_price))
    if category:
        sql += " AND lower(category) = ?"
        params.append(category.lower())
    sql += " ORDER BY category, price"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    for r in rows:
        r["veg"] = bool(r["veg"])
        r["spicy"] = bool(r["spicy"])
        r["available"] = bool(r["available"])
    return {"count": len(rows), "items": rows}


def get_order_status(order_id):
    order_id = str(order_id).strip().lstrip("#")
    if not order_id.isdigit():
        raise ToolError("Order ID must be a number, e.g. 1022.")
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not row:
        return {"found": False, "order_id": order_id, "message": "No order with this ID."}
    order = dict(row)
    order["found"] = True
    return order


def check_table_availability(date, time, party_size=2):
    d = _parse_date(date)
    t = _parse_time(time)
    party_size = int(party_size)
    if party_size < 1 or party_size > MAX_PARTY_SIZE:
        raise ToolError(f"Party size must be between 1 and {MAX_PARTY_SIZE}.")
    if d < datetime.date.today():
        raise ToolError("That date is in the past.")
    with get_conn() as conn:
        booked = conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE date = ? AND time = ? AND status = 'confirmed'",
            (d.isoformat(), t),
        ).fetchone()[0]
    free = TABLES_PER_SLOT - booked
    result = {"date": d.isoformat(), "time": t, "party_size": party_size,
              "tables_free": max(free, 0), "available": free > 0}
    if free <= 0:
        # Suggest the nearest free slots on the same day - helpful for the agent.
        alternatives = []
        with get_conn() as conn:
            for h in range(OPEN_HOUR, CLOSE_HOUR):
                slot = f"{h:02d}:00"
                n = conn.execute(
                    "SELECT COUNT(*) FROM bookings WHERE date=? AND time=? AND status='confirmed'",
                    (d.isoformat(), slot)).fetchone()[0]
                if n < TABLES_PER_SLOT:
                    alternatives.append(slot)
        target = int(t[:2])
        alternatives.sort(key=lambda s: abs(int(s[:2]) - target))
        result["alternatives"] = alternatives[:3]
    return result


def create_booking(name, phone, date, time, party_size):
    name = (name or "").strip()
    phone = re.sub(r"\D", "", str(phone or ""))
    # IMPORTANT: The backend validates everything. Never trust the LLM (or the browser)!
    if len(name) < 2:
        raise ToolError("A customer name is required.")
    if len(phone) != 10:
        raise ToolError("A valid 10-digit phone number is required.")
    availability = check_table_availability(date, time, party_size)
    if not availability["available"]:
        raise ToolError(f"No tables free at {availability['time']} on {availability['date']}. "
                        f"Free slots: {', '.join(availability.get('alternatives', [])) or 'none'}.")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO bookings (name, phone, date, time, party_size, status, created_at) "
            "VALUES (?,?,?,?,?, 'confirmed', ?)",
            (name, phone, availability["date"], availability["time"], int(party_size),
             datetime.datetime.now().isoformat(timespec="seconds")),
        )
        booking_id = cur.lastrowid
    return {"booking_id": booking_id, "status": "confirmed", "name": name,
            "phone": _mask_phone(phone), "date": availability["date"],
            "time": availability["time"], "party_size": int(party_size)}


def get_cafe_info(topic):
    topic = (topic or "").strip().lower()
    if topic not in CAFE_INFO:
        return {"topic": topic, "info": None, "available_topics": list(CAFE_INFO)}
    return {"topic": topic, "info": CAFE_INFO[topic]}


def list_bookings(date=None):
    """Used only by the REST API (staff view). NOT exposed to the agent."""
    sql, params = "SELECT id, name, phone, date, time, party_size, status FROM bookings", []
    if date:
        sql += " WHERE date = ?"
        params.append(_parse_date(date).isoformat())
    sql += " ORDER BY date, time"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    for r in rows:
        r["phone"] = _mask_phone(r["phone"])
    return {"count": len(rows), "bookings": rows}


# --------------------------------------------------------------------------
# EXERCISE 3 and 4: add your new tool functions here
# --------------------------------------------------------------------------
# def get_todays_special():
#     ...
#
# def cancel_booking(booking_id, phone):
#     ...


# --------------------------------------------------------------------------
# Tool schemas - what the LLM is told about each tool (OpenAI format)
# --------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_menu",
            "description": "Search the cafe menu. Use for any question about dishes, drinks, prices, "
                           "vegetarian options or spice level. Returns matching items with price in rupees.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Dish name or keyword, e.g. 'biryani', 'coffee'. Empty for full menu."},
                    "veg_only": {"type": "boolean", "description": "True to return only vegetarian items."},
                    "max_price": {"type": "integer", "description": "Maximum price in rupees."},
                    "category": {"type": "string", "enum": ["Beverages", "Mains", "Wraps", "Starters", "Desserts"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Get the live status of a delivery order by its order ID (e.g. 1022).",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "The numeric order ID."}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_table_availability",
            "description": "Check if a table is free for a date, time and party size. Always call this before create_booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD, or 'today' / 'tomorrow'."},
                    "time": {"type": "string", "description": "24-hour time on the hour, e.g. '19:00'."},
                    "party_size": {"type": "integer", "description": "Number of guests (1-8)."},
                },
                "required": ["date", "time", "party_size"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": "Create a confirmed table booking. Only call after the customer has given name, "
                           "10-digit phone, date, time and party size, and availability has been checked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string", "description": "10-digit mobile number."},
                    "date": {"type": "string", "description": "YYYY-MM-DD, or 'today' / 'tomorrow'."},
                    "time": {"type": "string", "description": "24-hour time, e.g. '19:00'."},
                    "party_size": {"type": "integer"},
                },
                "required": ["name", "phone", "date", "time", "party_size"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cafe_info",
            "description": "Get general information about the cafe.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string", "enum": list(CAFE_INFO)}},
                "required": ["topic"],
            },
        },
    },
    # EXERCISE 3 and 4: add the schemas for your new tools here
]

# Maps the tool name the LLM asks for -> the Python function we run.
TOOL_FUNCTIONS = {
    "search_menu": search_menu,
    "get_order_status": get_order_status,
    "check_table_availability": check_table_availability,
    "create_booking": create_booking,
    "get_cafe_info": get_cafe_info,
    # EXERCISE 3 and 4: register your new tools here
}


def run_tool(name, args):
    """Safely execute a tool requested by the agent. Always returns a dict."""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"error": f"Unknown tool '{name}'."}
    try:
        return func(**(args or {}))
    except ToolError as e:
        return {"error": str(e)}
    except TypeError as e:  # wrong / missing arguments from the LLM
        return {"error": f"Bad arguments for {name}: {e}"}
