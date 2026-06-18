import logging
import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

# -------------------------------------------------------------------------
# 1. कॉन्फ़िगरेशन और लॉगिंग (Configuration & Logging)
# -------------------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8826162658:AAGLPgWyJmIkk3H8Ju1xqfLcwjZod9C2DqQ"
ADMIN_ID = 8170952537

QR_IMAGE_URL = "https://kommodo.ai/i/qF4FLWL7wK3SjLsyNmH1"
SUPPORT_USERNAME = "@Narendra_Modih"

APPS = [
    "Rolex Mod",
    "XSilent Mod", 
    "Depend Mod",
    "Citizen Loader"
]

# Conversation States
(
    STATE_MAIN,
    STATE_SELECT_APP,
    STATE_SELECT_PLAN,
    STATE_WAIT_SCREENSHOT,
    STATE_ENTER_REDEEM,
    STATE_ADMIN_PANEL,
    STATE_ADMIN_INPUT
) = range(7)

# -------------------------------------------------------------------------
# 2. डेटाबेस सेटअप (Database Setup)
# -------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('beast_key.db')
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        join_date TEXT,
        is_banned INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS apps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_id INTEGER,
        title TEXT,
        price INTEGER,
        duration_days INTEGER,
        FOREIGN KEY(app_id) REFERENCES apps(id)
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        app_name TEXT,
        license_key TEXT,
        purchase_date TEXT,
        expiry_date TEXT,
        status TEXT
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS payments (
        order_id TEXT PRIMARY KEY,
        user_id INTEGER,
        app_id INTEGER,
        plan_id INTEGER,
        amount INTEGER,
        status TEXT,
        screenshot_file_id TEXT,
        date TEXT
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS redeem_codes (
        code TEXT PRIMARY KEY,
        app_name TEXT,
        duration_days INTEGER,
        usage_limit INTEGER,
        used_count INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        admin_id INTEGER,
        timestamp TEXT
    )''')
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('qr_file_id', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tutorial_file_id', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_link', 'http://BEASTMODOWNER.t.me')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('qr_image_url', ?)", (QR_IMAGE_URL,))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_username', ?)", (SUPPORT_USERNAME,))
    
    cursor.execute("SELECT COUNT(*) FROM apps")
    if cursor.fetchone()[0] == 0:
        for app_name in APPS:
            cursor.execute("INSERT INTO apps (name) VALUES (?)", (app_name,))
            
        default_plans = [
            ("5 hours - ₹30", 30, 0),
            ("1Day - ₹99", 99, 1),
            ("7Day - ₹599", 599, 7),
            ("1 month - ₹1200", 1200, 30),
            ("Season - ₹1800", 1800, 60)
        ]
        
        cursor.execute("SELECT id FROM apps")
        app_ids = [row[0] for row in cursor.fetchall()]
        
        for app_id in app_ids:
            for title, price, duration in default_plans:
                cursor.execute("INSERT INTO plans (app_id, title, price, duration_days) VALUES (?, ?, ?, ?)",
                             (app_id, title, price, duration))

    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------------------
# 3. हेल्पर फंक्शंस (Helper Functions)
# -------------------------------------------------------------------------
def get_setting(key):
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def set_setting(key, value):
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
    conn.commit()
    conn.close()

def log_admin_action(action, admin_id):
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("INSERT INTO admin_logs (action, admin_id, timestamp) VALUES (?, ?, ?)",
              (action, admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def is_admin(user_id):
    return user_id == ADMIN_ID

def is_user_banned(user_id):
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

def get_user_balance(user_id):
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def update_user_balance(user_id, amount):
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def generate_license_key(app_name, user_id):
    return f"{app_name[:4].upper()}-{uuid.uuid4().hex[:12].upper()}"

# -------------------------------------------------------------------------
# 4. कीबोर्ड्स (Keyboards UI Setup)
# -------------------------------------------------------------------------
def main_menu_keyboard(user_id=None):
    keyboard = [
        [KeyboardButton("🔑 Purchase Key")],
        [KeyboardButton("📋 My Keys")],
        [KeyboardButton("🎁 Redeem Code")],
        [KeyboardButton("📚 How to Buy?")],
        [KeyboardButton("🆔 My ID"), KeyboardButton("🆘 Contact Support")]
    ]
    if user_id and is_admin(user_id):
        keyboard.append([KeyboardButton("🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("↩️ Cancel")]], resize_keyboard=True)

# -------------------------------------------------------------------------
# 5. बोट कमांड्स और यूज़र फ्लो (Bot Commands & User Flow)
# -------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_user_banned(user.id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return ConversationHandler.END
    
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, join_date, balance) VALUES (?, ?, ?, ?)",
              (user.id, user.username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "🎮 Welcome to License Key Bot!",
        reply_markup=main_menu_keyboard(user.id)
    )
    return STATE_MAIN

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if is_user_banned(user_id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return STATE_MAIN

    if text == "🔑 Purchase Key":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT name FROM apps")
        apps = [r[0] for r in c.fetchall()]
        conn.close()

        if not apps:
            await update.message.reply_text("❌ No apps available right now.")
            return STATE_MAIN

        keyboard = []
        row = []
        for app in apps:
            row.append(KeyboardButton(app))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([KeyboardButton("↩️ Back")])

        await update.message.reply_text(
            "🎮 Select an App to purchase:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        return STATE_SELECT_APP

    elif text == "📋 My Keys":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT app_name, license_key, purchase_date, expiry_date, status FROM keys WHERE user_id=?", (user_id,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            await update.message.reply_text("📋 You haven't purchased any keys yet.")
            return STATE_MAIN

        msg = "📋 **Your License Keys:**\n\n"
        for row in rows:
            msg += (f"📦 **App:** {row[0]}\n"
                    f"🔑 **Key:** `{row[1]}`\n"
                    f"📅 **Purchased:** {row[2]}\n"
                    f"⌛ **Expiry:** {row[3]}\n"
                    f"🟢 **Status:** {row[4]}\n"
                    f"-------------------------\n")
        await update.message.reply_text(msg, parse_mode="Markdown")
        return STATE_MAIN

    elif text == "🎁 Redeem Code":
        await update.message.reply_text(
            "🎁 Please enter your redeem code:",
            reply_markup=cancel_keyboard()
        )
        return STATE_ENTER_REDEEM

    elif text == "📚 How to Buy?":
        video_id = get_setting('tutorial_file_id')
        if video_id:
            await update.message.reply_video(video=video_id, caption="📚 Tutorial Video on how to buy.")
        else:
            await update.message.reply_text("📚 Tutorial video is not set by Admin yet.")
        return STATE_MAIN

    elif text == "🆔 My ID":
        balance = get_user_balance(user_id)
        await update.message.reply_text(
            f"🆔 Your Telegram ID: `{user_id}`\n"
            f"💰 Balance: ₹{balance}",
            parse_mode="Markdown"
        )
        return STATE_MAIN

    elif text == "🆘 Contact Support":
        support_link = get_setting('support_link')
        await update.message.reply_text(
            f"🆘 **Support Contact**\n\nFor any issues or questions, please contact our support team:\n{support_link}",
            disable_web_page_preview=True,
            parse_mode="Markdown"
        )
        return STATE_MAIN
    
    elif text == "🛠 Admin Panel" and is_admin(user_id):
        return await admin_panel(update, context)
        
    return STATE_MAIN

# -------------------------------------------------------------------------
# 6. परचेज़ फ्लो हैंडलर्स (Purchase Flow Handlers & QR Fixed Here)
# -------------------------------------------------------------------------
async def handle_app_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "↩️ Back":
        await update.message.reply_text("Returning to main menu...", reply_markup=main_menu_keyboard(user_id))
        return STATE_MAIN

    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT id, name FROM apps WHERE name=?", (text,))
    app = c.fetchone()

    if not app:
        await update.message.reply_text("❌ Invalid App. Please select from the menu.")
        conn.close()
        return STATE_SELECT_APP

    app_id, app_name = app
    context.user_data['selected_app_id'] = app_id
    context.user_data['selected_app_name'] = app_name

    c.execute("SELECT id, title, price, duration_days FROM plans WHERE app_id=?", (app_id,))
    plans = c.fetchall()
    conn.close()

    if not plans:
        await update.message.reply_text("❌ No plans available for this app.")
        return STATE_SELECT_APP

    keyboard = []
    row = []
    for pid, title, price, duration in plans:
        row.append(KeyboardButton(f"{title}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([KeyboardButton("↩️ Back to Apps")])

    await update.message.reply_text(
        f"⌛ Select plan for {app_name}:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return STATE_SELECT_PLAN

async def handle_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    app_id = context.user_data.get('selected_app_id')
    app_name = context.user_data.get('selected_app_name')
    user_id = update.effective_user.id

    if text == "↩️ Back to Apps":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT name FROM apps")
        apps = [r[0] for r in c.fetchall()]
        conn.close()
        keyboard = []
        row = []
        for app in apps:
            row.append(KeyboardButton(app))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([KeyboardButton("↩️ Back")])
        await update.message.reply_text("Select an App to purchase:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return STATE_SELECT_APP

    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT id, price, title, duration_days FROM plans WHERE app_id=? AND title=?", (app_id, text))
    plan = c.fetchone()
    conn.close()

    if not plan:
        await update.message.reply_text("❌ Invalid Plan. Please select from the menu.")
        return STATE_SELECT_PLAN

    plan_id, price, title, duration = plan
    order_id = f"order_{uuid.uuid4().hex[:12]}"
    
    context.user_data['current_order'] = {
        'order_id': order_id,
        'plan_id': plan_id,
        'amount': price,
        'title': title,
        'duration': duration
    }

    qr_image_url = get_setting('qr_image_url') or QR_IMAGE_URL
    
    payment_text = (
        f"💳 **Scan to Pay ₹{price}**\n\n"
        f"📱 App: {app_name}\n"
        f"📦 Plan: {title}\n"
        f"🆔 Order ID: `{order_id}`\n\n"
        f"📸 Scan the QR code below to pay.\n"
        f"After payment, click ✅ I have paid and send screenshot.\n\n"
        f"Support: {SUPPORT_USERNAME}"
    )

    inline_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I have paid", callback_data=f"paid_{order_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_pay_{order_id}")]
    ])

    # यहाँ इसे reply_text से reply_photo में बदल दिया है ताकि फोटो के साथ कैप्शन लोड हो
    await update.message.reply_photo(
        photo=qr_image_url, 
        caption=payment_text, 
        reply_markup=inline_kb, 
        parse_mode="Markdown"
    )
    return STATE_MAIN

# -------------------------------------------------------------------------
# 7. इनलाइन बटन कॉलबैक (Callbacks & Verification)
# -------------------------------------------------------------------------
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("paid_"):
        order_id = data.replace("paid_", "")
        context.user_data['verifying_order_id'] = order_id
        await query.message.reply_text(
            "📸 Please send/upload the transaction screenshot for verification:\n\n"
            "⏳ Our admin will verify your payment within 1-2 minutes.",
            reply_markup=cancel_keyboard()
        )
        context.user_data['forced_state'] = STATE_WAIT_SCREENSHOT

    elif data.startswith("cancel_pay_"):
        await query.message.reply_text("Action cancelled.", reply_markup=main_menu_keyboard(user_id))

    elif data.startswith("approve_"):
        if not is_admin(user_id): return
        await process_payment_approval(query, data.replace("approve_", ""), context)

    elif data.startswith("reject_"):
        if not is_admin(user_id): return
        await process_payment_rejection(query, data.replace("reject_", ""), context)

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if update.message.text == "↩️ Cancel":
        await update.message.reply_text("Action cancelled.", reply_markup=main_menu_keyboard(user_id))
        context.user_data.pop('forced_state', None)
        return STATE_MAIN

    if not update.message.photo:
        await update.message.reply_text("❌ Please send a valid image screenshot.")
        return STATE_WAIT_SCREENSHOT

    photo_file_id = update.message.photo[-1].file_id
    order_data = context.user_data.get('current_order')
    app_name = context.user_data.get('selected_app_name', 'Unknown')
    user = update.effective_user

    if not order_data:
        await update.message.reply_text("❌ Session expired. Please start the process again.")
        return STATE_MAIN

    order_id = order_data['order_id']
    
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("INSERT INTO payments (order_id, user_id, app_id, plan_id, amount, status, screenshot_file_id, date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (order_id, user.id, context.user_data['selected_app_id'], order_data['plan_id'], order_data['amount'], 'PENDING', photo_file_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "⏳ **Payment details sent to admin!**\n\n"
        "✅ Please wait for admin verification.\n"
        "⏱ Usually takes 1-2 minutes.\n\n"
        "You will receive your license key here once approved.",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode="Markdown"
    )

    admin_msg = (
        f"📦 **New Pending Payment**\n\n"
        f"👤 User: {user.first_name} (@{user.username})\n"
        f"🆔 User ID: `{user.id}`\n"
        f"🏷 App: {app_name}\n"
        f"💵 Plan: {order_data['title']}\n"
        f"💰 Amount: ₹{order_data['amount']}\n"
        f"🆔 Order ID: `{order_id}`"
    )
    admin_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve & Send Key", callback_data=f"approve_{order_id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}")]
    ])
    
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file_id, caption=admin_msg, reply_markup=admin_kb, parse_mode="Markdown")
    context.user_data.pop('forced_state', None)
    return STATE_MAIN

async def process_payment_approval(query, order_id, context):
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT user_id, amount, app_id, plan_id, status FROM payments WHERE order_id=?", (order_id,))
    payment = c.fetchone()

    if not payment or payment[4] != 'PENDING':
        await query.message.reply_text("❌ Payment already handled or not found.")
        conn.close()
        return

    user_id, amount, app_id, plan_id = payment[0], payment[1], payment[2], payment[3]
    
    c.execute("SELECT name FROM apps WHERE id=?", (app_id,))
    app_name = c.fetchone()[0]
    c.execute("SELECT title, duration_days FROM plans WHERE id=?", (plan_id,))
    plan = c.fetchone()
    plan_title, duration_days = plan[0], plan[1]
    
    license_key = generate_license_key(app_name, user_id)
    p_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    e_date = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("UPDATE payments SET status='APPROVED' WHERE order_id=?", (order_id,))
    c.execute("INSERT INTO keys (user_id, app_name, license_key, purchase_date, expiry_date, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
              (user_id, app_name, license_key, p_date, e_date))
    conn.commit()
    conn.close()

    await query.edit_message_caption(caption=query.message.caption + "\n\n🟢 **Status: APPROVED**")
    
    user_msg = (
        f"🎉 **Payment Approved!**\n\n"
        f"📱 App: {app_name}\n"
        f"📦 Plan: {plan_title}\n"
        f"🔑 **License Key:** `{license_key}`\n"
        f"⌛ **Expiry:** {e_date}\n\n"
        f"✅ You can view this anytime in the 📋 **My Keys** section."
    )
    try:
        await context.bot.send_message(chat_id=user_id, text=user_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error sending key: {e}")

async def process_payment_rejection(query, order_id, context):
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT user_id, status FROM payments WHERE order_id=?", (order_id,))
    payment = c.fetchone()

    if not payment or payment[1] != 'PENDING':
        await query.message.reply_text("❌ Payment already handled.")
        conn.close()
        return

    user_id = payment[0]
    c.execute("UPDATE payments SET status='REJECTED' WHERE order_id=?", (order_id,))
    conn.commit()
    conn.close()

    await query.edit_message_caption(caption=query.message.caption + "\n\n🔴 **Status: REJECTED**")
    try:
        await context.bot.send_message(chat_id=user_id, text="❌ **Payment verification failed.**\n\nPlease contact support.", parse_mode="Markdown")
    except: pass

# -------------------------------------------------------------------------
# 8. रिडीम कोड सिस्टम (Redeem Code System)
# -------------------------------------------------------------------------
async def handle_redeem_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if text == "↩️ Cancel":
        await update.message.reply_text("Action cancelled.", reply_markup=main_menu_keyboard(user_id))
        return STATE_MAIN

    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT app_name, duration_days, usage_limit, used_count, balance FROM redeem_codes WHERE code=?", (text,))
    code_data = c.fetchone()

    if not code_data:
        await update.message.reply_text("❌ Invalid Redeem Code.", reply_markup=main_menu_keyboard(user_id))
        conn.close()
        return STATE_MAIN

    app_name, duration, limit, used, balance = code_data
    if used >= limit:
        await update.message.reply_text("❌ This code limit reached.", reply_markup=main_menu_keyboard(user_id))
        conn.close()
        return STATE_MAIN

    if balance > 0:
        update_user_balance(user_id, balance)
        c.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code=?", (text,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"🎁 **Redeemed Successfully!**\n💰 ₹{balance} added to balance!", reply_markup=main_menu_keyboard(user_id), parse_mode="Markdown")
        return STATE_MAIN
    
    new_key = generate_license_key(app_name, user_id)
    p_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    e_date = (datetime.now() + timedelta(days=duration if duration > 0 else 1)).strftime("%Y-%m-%d %H:%M:%S")

    c.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code=?", (text,))
    c.execute("INSERT INTO keys (user_id, app_name, license_key, purchase_date, expiry_date, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
              (user_id, app_name, new_key, p_date, e_date))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🎁 **Redeemed!**\n📱 App: {app_name}\n🔑 Key: `{new_key}`", reply_markup=main_menu_keyboard(user_id), parse_mode="Markdown")
    return STATE_MAIN

# -------------------------------------------------------------------------
# 9. पूर्णतः बटन-आधारित एडमिन पैनल (100% Button-Based Admin Panel Rework)
# -------------------------------------------------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return STATE_MAIN

    admin_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Total Users", callback_data="adm_total_users"), InlineKeyboardButton("🟢 Active Users", callback_data="adm_active_users")],
        [InlineKeyboardButton("🔴 Banned Users", callback_data="adm_banned_users"), InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban_user_sel")],
        [InlineKeyboardButton("✅ Unban User", callback_data="adm_unban_user_sel"), InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast")],
        [InlineKeyboardButton("🎁 Generate Redeem", callback_data="adm_gen_type_sel"), InlineKeyboardButton("📋 Redeem List", callback_data="adm_redeem_list")],
        [InlineKeyboardButton("📊 Redeem Stats", callback_data="adm_redeem_stats"), InlineKeyboardButton("💰 Price List", callback_data="adm_price_list")],
        [InlineKeyboardButton("📈 Purchase Stats", callback_data="adm_purchase_stats"), InlineKeyboardButton("📊 Bot Stats", callback_data="adm_bot_stats")],
        [InlineKeyboardButton("📋 Admin Logs", callback_data="adm_logs"), InlineKeyboardButton("⚙️ Settings", callback_data="adm_settings")]
    ])
    
    if update.message:
        await update.message.reply_text("🛠 **BEAST ADMIN PANEL** 🛠\nSelect an action below:", reply_markup=admin_kb, parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text("🛠 **BEAST ADMIN PANEL** 🛠\nSelect an action below:", reply_markup=admin_kb, parse_mode="Markdown")
    return STATE_MAIN

async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if not is_admin(user_id): return

    # --- Statistics & Simple views ---
    if data == "adm_total_users":
        conn = sqlite3.connect('beast_key.db')
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        await query.message.reply_text(f"📊 **Total Users:** {count}")

    elif data == "adm_active_users":
        conn = sqlite3.connect('beast_key.db')
        count = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned=0").fetchone()[0]
        conn.close()
        await query.message.reply_text(f"🟢 **Active Users:** {count}")

    elif data == "adm_banned_users":
        conn = sqlite3.connect('beast_key.db')
        count = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned=1").fetchone()[0]
        conn.close()
        await query.message.reply_text(f"🔴 **Banned Users:** {count}")

    elif data == "adm_price_list":
        conn = sqlite3.connect('beast_key.db')
        plans = conn.execute("SELECT apps.name, plans.title, plans.price FROM plans JOIN apps ON plans.app_id = apps.id").fetchall()
        conn.close()
        msg = "💰 **Price List:**\n\n" + "\n".join([f"📱 {p[0]} - {p[1]}: ₹{p[2]}" for p in plans])
        await query.message.reply_text(msg, parse_mode="Markdown")

    # --- 100% Button Flow for Redeem Code Generation ---
    elif data == "adm_gen_type_sel":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 App / License Code", callback_data="adm_gtype_app")],
            [InlineKeyboardButton("💰 Pure Balance Code", callback_data="adm_gtype_bal")]
        ])
        await query.message.edit_text("Select Redeem Code Type:", reply_markup=kb)

    elif data == "adm_gtype_app" or data == "adm_gtype_bal":
        context.user_data['g_type'] = 'BAL' if 'bal' in data else 'APP'
        # App list selection buttons
        conn = sqlite3.connect('beast_key.db')
        apps = conn.execute("SELECT name FROM apps").fetchall()
        conn.close()
        kb = [[InlineKeyboardButton(a[0], callback_data=f"adm_gapp_{a[0]}")] for a in apps]
        await query.message.edit_text("Select Associated Target App:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_gapp_"):
        context.user_data['g_app'] = data.replace("adm_gapp_", "")
        if context.user_data['g_type'] == 'BAL':
            # Balance Amounts Buttons
            amounts = [100, 200, 300, 500, 1000]
            kb = [[InlineKeyboardButton(f"₹{amt}", callback_data=f"adm_gamt_{amt}")] for amt in amounts]
            await query.message.edit_text("Select Balance Amount:", reply_markup=InlineKeyboardMarkup(kb))
        else:
            # Plan selection from DB dynamically via buttons
            conn = sqlite3.connect('beast_key.db')
            plans = conn.execute("SELECT title, duration_days FROM plans WHERE app_id=(SELECT id FROM apps WHERE name=?)", (context.user_data['g_app'],)).fetchall()
            conn.close()
            kb = [[InlineKeyboardButton(p[0], callback_data=f"adm_gdays_{p[1]}")] for p in plans]
            await query.message.edit_text("Select License Plan Duration:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_gamt_"):
        context.user_data['g_amt'] = int(data.replace("adm_gamt_", ""))
        context.user_data['g_days'] = 0
        # Proceed to Device/Usage limit buttons
        limits = [1, 2, 5, 10, 100]
        kb = [[InlineKeyboardButton(f"{l} Devices/Uses", callback_data=f"adm_glim_{l}")] for l in limits]
        await query.message.edit_text("Select Usage / Device Limits:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_gdays_"):
        context.user_data['g_days'] = int(data.replace("adm_gdays_", ""))
        context.user_data['g_amt'] = 0
        limits = [1, 2, 5, 10, 100]
        kb = [[InlineKeyboardButton(f"{l} Devices/Uses", callback_data=f"adm_glim_{l}")] for l in limits]
        await query.message.edit_text("Select Usage / Device Limits:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_glim_"):
        lim = int(data.replace("adm_glim_", ""))
        gtype = context.user_data.get('g_type')
        gapp = context.user_data.get('g_app')
        gdays = context.user_data.get('g_days', 0)
        gamt = context.user_data.get('g_amt', 0)
        
        code = f"BEAST-{uuid.uuid4().hex[:8].upper()}"
        conn = sqlite3.connect('beast_key.db')
        conn.execute("INSERT INTO redeem_codes (code, app_name, duration_days, usage_limit, balance) VALUES (?, ?, ?, ?, ?)",
                     (code, gapp, gdays, lim, gamt))
        conn.commit()
        conn.close()

        msg = (
            f"✅ **Redeem Code Autogenerated!**\n\n"
            f"🔑 **Code:** `{code}`\n"
            f"📱 App Target: {gapp}\n"
            f"💰 Balance: ₹{gamt}\n"
            f"⏱ Validity: {gdays} Days\n"
            f"📊 Device Limit: {lim}"
        )
        await query.message.edit_text(msg, parse_mode="Markdown")

    # --- Ban/Unban Flow via Buttons dynamically ---
    elif data == "adm_ban_user_sel" or data == "adm_unban_user_sel":
        status_check = 0 if "ban_user_sel" in data else 1
        conn = sqlite3.connect('beast_key.db')
        users = conn.execute("SELECT user_id, username FROM users WHERE is_banned=?", (status_check,)).fetchall()
        conn.close()
        if not users:
            await query.message.reply_text("No target users available for action.")
            return
        kb = [[InlineKeyboardButton(f"ID: {u[0]} (@{u[1]})", callback_data=f"adm_tgb_{u[0] if status_check==0 else u[0]}")] for u in users[:10]]
        await query.message.edit_text("Select user to switch status:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_tgb_"):
        target = int(data.replace("adm_tgb_", ""))
        conn = sqlite3.connect('beast_key.db')
        conn.execute("UPDATE users SET is_banned = 1 - is_banned WHERE user_id=?", (target,))
        conn.commit()
        conn.close()
        await query.message.edit_text(f"✅ User Status Updated for ID: `{target}`", parse_mode="Markdown")

    # --- Dynamic text settings triggers ---
    elif data == "adm_broadcast":
        await query.message.reply_text("Please Type broadcast text now:")
        context.user_data['admin_action'] = 'broadcast'

    elif data == "adm_settings":
        settings_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Change Support Link", callback_data="adm_set_support")],
            [InlineKeyboardButton("🖼 Change QR Image Link", callback_data="adm_set_qr")]
        ])
        await query.message.edit_text("⚙️ **Settings Panel**", reply_markup=settings_kb)

    elif data == "adm_set_support":
        await query.message.reply_text("Send the new Support Link:")
        context.user_data['admin_action'] = 'set_support'

    elif data == "adm_set_qr":
        await query.message.reply_text("Send new Direct QR Image URL link:")
        context.user_data['admin_action'] = 'set_qr'

async def handle_admin_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get('admin_action')
    user_id = update.effective_user.id
    if not is_admin(user_id): return STATE_MAIN

    if action == 'broadcast':
        msg = update.message.text
        conn = sqlite3.connect('beast_key.db')
        users = conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()
        conn.close()
        for u in users:
            try: await context.bot.send_message(chat_id=u[0], text=f"📢 **Broadcast:**\n\n{msg}", parse_mode="Markdown")
            except: pass
        await update.message.reply_text("✅ Broadcast complete!")

    elif action == 'set_support':
        set_setting('support_link', update.message.text.strip())
        await update.message.reply_text("✅ Link updated!")

    elif action == 'set_qr':
        set_setting('qr_image_url', update.message.text.strip())
        await update.message.reply_text("✅ Direct QR Link updated!")

    context.user_data.pop('admin_action', None)
    return STATE_MAIN

# -------------------------------------------------------------------------
# 10. फ़ॉलबैक और स्टेट बाईपास (State Bypass Helper)
# -------------------------------------------------------------------------
async def global_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    forced = context.user_data.get('forced_state')
    if forced == STATE_WAIT_SCREENSHOT:
        return await handle_screenshot(update, context)
    return STATE_MAIN

# -------------------------------------------------------------------------
# 11. मेन फंक्शन (Main Execution)
# -------------------------------------------------------------------------
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE_MAIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu),
                MessageHandler(filters.PHOTO, global_message_router)
            ],
            STATE_SELECT_APP: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_app_selection)],
            STATE_SELECT_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_plan_selection)],
            STATE_ENTER_REDEEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_redeem_code)],
            STATE_ADMIN_INPUT: [MessageHandler(filters.ALL, handle_admin_inputs)]
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CallbackQueryHandler(handle_callbacks, pattern="^(paid_|cancel_pay_|approve_|reject_)"))
    application.add_handler(CallbackQueryHandler(handle_admin_callbacks, pattern="^adm_"))
    application.add_handler(MessageHandler(filters.ALL, global_message_router))

    print("🤖 Beast License Bot is running flawlessly...")
    application.run_polling()

if __name__ == '__main__':
    main()
