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
# 1. कॉन्फ़िगरेशन और लॉबिंग (Configuration & Logging)
# -------------------------------------------------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Token and Admin ID
BOT_TOKEN = "8826162658:AAGLPgWyJmIkk3H8Ju1xqfLcwjZod9C2DqQ"
ADMIN_ID = 8170952537

# QR Configuration
QR_IMAGE_URL = "https://kommodo.ai/i/qF4FLWL7wK3SjLsyNmH1"
SUPPORT_USERNAME = "@Narendra_Modih"

# Apps List
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
    STATE_ADMIN_INPUT,
    STATE_REDEEM_BALANCE
) = range(8)

# -------------------------------------------------------------------------
# 2. डेटाबेस सेटअप (Database Setup)
# -------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('beast_key.db')
    cursor = conn.cursor()
    
    # Users Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        join_date TEXT,
        is_banned INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0
    )''')
    
    # Apps Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS apps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )''')
    
    # Plans Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        app_id INTEGER,
        title TEXT,
        price INTEGER,
        duration_days INTEGER,
        FOREIGN KEY(app_id) REFERENCES apps(id)
    )''')
    
    # License Keys Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        app_name TEXT,
        license_key TEXT,
        purchase_date TEXT,
        expiry_date TEXT,
        status TEXT
    )''')
    
    # Payments Table
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
    
    # Redeem Codes Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS redeem_codes (
        code TEXT PRIMARY KEY,
        app_name TEXT,
        duration_days INTEGER,
        usage_limit INTEGER,
        used_count INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0
    )''')
    
    # Settings Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # Admin Logs Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        admin_id INTEGER,
        timestamp TEXT
    )''')
    
    # Default Settings
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('qr_file_id', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('tutorial_file_id', '')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_link', 'http://BEASTMODOWNER.t.me')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('qr_image_url', ?)", (QR_IMAGE_URL,))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('support_username', ?)", (SUPPORT_USERNAME,))
    
    # Insert default apps if empty
    cursor.execute("SELECT COUNT(*) FROM apps")
    if cursor.fetchone()[0] == 0:
        for app_name in APPS:
            cursor.execute("INSERT INTO apps (name) VALUES (?)", (app_name,))
            
        # Default plans for each app
        default_plans = [
            ("5 hours - ₹30", 30, 0),
            ("1Day - ₹99", 99, 1),
            ("7Day - ₹599", 599, 7),
            ("1 month - ₹1200", 1200, 30),
            ("Season - ₹1800", 1800, 60)
        ]
        
        # Get all app IDs and add plans
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
    
    # Admin button only for admin users
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
    
    # Check if user is banned
    if is_user_banned(user.id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return
    
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
    
    # Check if user is banned
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

        # Create 2x2 grid layout for apps
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
# 6. परचेज़ फ्लो हैंडलर्स (Purchase Flow Handlers)
# -------------------------------------------------------------------------
async def handle_app_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if is_user_banned(user_id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return STATE_MAIN

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
    
    if is_user_banned(user_id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return STATE_MAIN

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

    # Get QR image URL from settings
    qr_image_url = get_setting('qr_image_url')
    if not qr_image_url:
        qr_image_url = QR_IMAGE_URL
    
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

    # Send QR image using URL
    await update.message.reply_photo(
        photo=qr_image_url, 
        caption=payment_text, 
        reply_markup=inline_kb, 
        parse_mode="Markdown"
    )
    
    return STATE_MAIN

# -------------------------------------------------------------------------
# 7. इनलाइन बटन कॉलबैक और स्क्रीनशॉट वेरिफिकेशन (Callbacks & Verification)
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
        if not is_admin(user_id):
            await query.message.reply_text("❌ You are not authorized to approve payments.")
            return
        order_id = data.replace("approve_", "")
        await process_payment_approval(query, order_id, context)

    elif data.startswith("reject_"):
        if not is_admin(user_id):
            await query.message.reply_text("❌ You are not authorized to reject payments.")
            return
        order_id = data.replace("reject_", "")
        await process_payment_rejection(query, order_id, context)

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
    
    # Save payment request to database
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

    # Send to admin for verification
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

# -------------------------------------------------------------------------
# 8. एडमिन एप्रूवल / रिजेक्शन लॉजिक (Admin Approval/Rejection Logic)
# -------------------------------------------------------------------------
async def process_payment_approval(query, order_id, context):
    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT user_id, amount, app_id, plan_id, status FROM payments WHERE order_id=?", (order_id,))
    payment = c.fetchone()

    if not payment or payment[4] != 'PENDING':
        await query.message.reply_text("❌ Payment already handled or not found.")
        conn.close()
        return

    user_id = payment[0]
    amount = payment[1]
    app_id = payment[2]
    plan_id = payment[3]
    
    # Get app name and plan details
    c.execute("SELECT name FROM apps WHERE id=?", (app_id,))
    app = c.fetchone()
    app_name = app[0] if app else "Unknown"
    
    c.execute("SELECT title, duration_days FROM plans WHERE id=?", (plan_id,))
    plan = c.fetchone()
    plan_title = plan[0] if plan else "Standard"
    duration_days = plan[1] if plan else 7
    
    # Generate license key
    license_key = generate_license_key(app_name, user_id)
    p_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    e_date = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("UPDATE payments SET status='APPROVED' WHERE order_id=?", (order_id,))
    c.execute("INSERT INTO keys (user_id, app_name, license_key, purchase_date, expiry_date, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
              (user_id, app_name, license_key, p_date, e_date))
    conn.commit()
    conn.close()

    await query.edit_message_caption(caption=query.message.caption + "\n\n🟢 **Status: APPROVED**")
    
    # Send license key to user
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
        await context.bot.send_message(chat_id=user_id, text="✅ License key delivered successfully!", reply_markup=main_menu_keyboard(user_id))
    except Exception as e:
        logger.error(f"Could not send message to user: {e}")

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
        await context.bot.send_message(chat_id=user_id, text="❌ **Payment verification failed.**\n\nPlease contact support for assistance.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Could not notify user: {e}")

# -------------------------------------------------------------------------
# 9. रिडीम कोड सिस्टम (Redeem Code System)
# -------------------------------------------------------------------------
async def handle_redeem_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if is_user_banned(user_id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return STATE_MAIN

    if text == "↩️ Cancel":
        await update.message.reply_text("Action cancelled.", reply_markup=main_menu_keyboard(user_id))
        return STATE_MAIN

    conn = sqlite3.connect('beast_key.db')
    c = conn.cursor()
    c.execute("SELECT app_name, duration_days, usage_limit, used_count, balance FROM redeem_codes WHERE code=?", (text,))
    code_data = c.fetchone()

    if not code_data:
        await update.message.reply_text("❌ Invalid Redeem Code. Try again or cancel.", reply_markup=cancel_keyboard())
        conn.close()
        return STATE_ENTER_REDEEM

    app_name, duration, limit, used, balance = code_data
    
    if used >= limit:
        await update.message.reply_text("❌ This redeem code has expired (limit reached).", reply_markup=main_menu_keyboard(user_id))
        conn.close()
        return STATE_MAIN

    # Check if it's a balance redeem code
    if balance > 0:
        # Add balance to user
        update_user_balance(user_id, balance)
        c.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code=?", (text,))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"🎁 **Code Redeemed Successfully!**\n\n"
            f"💰 ₹{balance} added to your balance!\n"
            f"📱 App: {app_name}\n"
            f"🆕 New Balance: ₹{get_user_balance(user_id)}",
            reply_markup=main_menu_keyboard(user_id),
            parse_mode="Markdown"
        )
        return STATE_MAIN
    
    # Generate license key for redeem code
    new_key = generate_license_key(app_name, user_id)
    p_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    e_date = (datetime.now() + timedelta(days=duration if duration > 0 else 1)).strftime("%Y-%m-%d %H:%M:%S")

    c.execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code=?", (text,))
    c.execute("INSERT INTO keys (user_id, app_name, license_key, purchase_date, expiry_date, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
              (user_id, app_name, new_key, p_date, e_date))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"🎁 **Code Redeemed Successfully!**\n\n"
        f"📱 App: {app_name}\n"
        f"🔑 Key: `{new_key}`\n"
        f"⌛ Valid Until: {e_date}",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode="Markdown"
    )
    return STATE_MAIN

# -------------------------------------------------------------------------
# 10. पावरफुल एडमिन पैनल (Powerful Admin Panel)
# -------------------------------------------------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    admin_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Total Users", callback_data="adm_total_users"), 
         InlineKeyboardButton("🟢 Active Users", callback_data="adm_active_users")],
        [InlineKeyboardButton("🔴 Banned Users", callback_data="adm_banned_users"), 
         InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban_user")],
        [InlineKeyboardButton("✅ Unban User", callback_data="adm_unban_user"), 
         InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast")],
        [InlineKeyboardButton("🎁 Generate Redeem", callback_data="adm_gen_redeem"), 
         InlineKeyboardButton("💰 Balance Redeem", callback_data="adm_balance_redeem")],
        [InlineKeyboardButton("📋 Redeem List", callback_data="adm_redeem_list"), 
         InlineKeyboardButton("🗑 Delete Redeem", callback_data="adm_del_redeem")],
        [InlineKeyboardButton("📊 Redeem Stats", callback_data="adm_redeem_stats"), 
         InlineKeyboardButton("➕ Add App", callback_data="adm_add_app")],
        [InlineKeyboardButton("📋 Add Plan", callback_data="adm_add_plan"), 
         InlineKeyboardButton("✏️ Edit Plan", callback_data="adm_edit_plan")],
        [InlineKeyboardButton("❌ Delete Plan", callback_data="adm_del_plan"), 
         InlineKeyboardButton("💰 Price List", callback_data="adm_price_list")],
        [InlineKeyboardButton("📈 Purchase Stats", callback_data="adm_purchase_stats"), 
         InlineKeyboardButton("🔍 User Search", callback_data="adm_user_search")],
        [InlineKeyboardButton("👤 User Info", callback_data="adm_user_info"), 
         InlineKeyboardButton("📋 Admin Logs", callback_data="adm_logs")],
        [InlineKeyboardButton("📊 Bot Stats", callback_data="adm_bot_stats"), 
         InlineKeyboardButton("⚙️ Settings", callback_data="adm_settings")],
        [InlineKeyboardButton("🔄 Restart Bot", callback_data="adm_restart")]
    ])
    
    await update.message.reply_text("🛠 **BEAST ADMIN PANEL** 🛠\nSelect an action below:", reply_markup=admin_kb, parse_mode="Markdown")
    return STATE_ADMIN_PANEL

async def handle_admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.message.reply_text("❌ You are not authorized to access admin panel.")
        return

    if data == "adm_total_users":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        count = c.fetchone()[0]
        conn.close()
        await query.message.reply_text(f"📊 **Total Users:** {count}", parse_mode="Markdown")
        log_admin_action("Viewed total users", user_id)

    elif data == "adm_active_users":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned=0")
        count = c.fetchone()[0]
        conn.close()
        await query.message.reply_text(f"🟢 **Active Users:** {count}", parse_mode="Markdown")
        log_admin_action("Viewed active users", user_id)

    elif data == "adm_banned_users":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
        count = c.fetchone()[0]
        conn.close()
        await query.message.reply_text(f"🔴 **Banned Users:** {count}", parse_mode="Markdown")
        log_admin_action("Viewed banned users", user_id)

    elif data == "adm_ban_user":
        await query.message.reply_text("Please send the **User ID** to ban:\n(Format: /ban 123456789)")
        context.user_data['admin_action'] = 'ban_user'
        return STATE_ADMIN_INPUT

    elif data == "adm_unban_user":
        await query.message.reply_text("Please send the **User ID** to unban:\n(Format: /unban 123456789)")
        context.user_data['admin_action'] = 'unban_user'
        return STATE_ADMIN_INPUT

    elif data == "adm_broadcast":
        await query.message.reply_text("Please send the **Broadcast Message** to send to all users:")
        context.user_data['admin_action'] = 'broadcast'
        return STATE_ADMIN_INPUT

    elif data == "adm_gen_redeem":
        await query.message.reply_text("Please send redeem code details in format:\n`app_name,duration_days,usage_limit`\nExample: `Rolex Mod,30,5`")
        context.user_data['admin_action'] = 'gen_redeem'
        return STATE_ADMIN_INPUT
    
    elif data == "adm_balance_redeem":
        await query.message.reply_text("Please send balance redeem code details in format:\n`app_name,balance_amount,usage_limit`\nExample: `Rolex Mod,100,5`")
        context.user_data['admin_action'] = 'balance_redeem'
        return STATE_ADMIN_INPUT

    elif data == "adm_redeem_list":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT code, app_name, duration_days, usage_limit, used_count, balance FROM redeem_codes ORDER BY code")
        codes = c.fetchall()
        conn.close()
        
        if not codes:
            await query.message.reply_text("📋 No redeem codes found.")
            return
        
        msg = "📋 **Redeem Codes:**\n\n"
        for code in codes:
            if code[5] > 0:
                msg += f"🔑 **{code[0]}** (💰 Balance: ₹{code[5]})\n"
            else:
                msg += f"🔑 **{code[0]}**\n"
            msg += f"📱 App: {code[1]}\n"
            msg += f"⏱ Duration: {code[2]} days\n"
            msg += f"📊 Used: {code[4]}/{code[3]}\n"
            msg += f"-------------------------\n"
        await query.message.reply_text(msg, parse_mode="Markdown")

    elif data == "adm_del_redeem":
        await query.message.reply_text("Please send the **Redeem Code** to delete:")
        context.user_data['admin_action'] = 'del_redeem'
        return STATE_ADMIN_INPUT

    elif data == "adm_redeem_stats":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM redeem_codes")
        total = c.fetchone()[0]
        c.execute("SELECT SUM(used_count) FROM redeem_codes")
        used = c.fetchone()[0] or 0
        c.execute("SELECT SUM(balance) FROM redeem_codes")
        total_balance = c.fetchone()[0] or 0
        conn.close()
        await query.message.reply_text(
            f"📊 **Redeem Code Statistics:**\n\n"
            f"📌 Total Codes: {total}\n"
            f"🔑 Total Used: {used}\n"
            f"💰 Total Balance: ₹{total_balance}",
            parse_mode="Markdown"
        )

    elif data == "adm_add_app":
        await query.message.reply_text("Please send the **App Name** to add:\nExample: `New Mod App`")
        context.user_data['admin_action'] = 'add_app'
        return STATE_ADMIN_INPUT

    elif data == "adm_add_plan":
        await query.message.reply_text("Please send plan details in format:\n`app_name,title,price,duration_days`\nExample: `Rolex Mod,Monthly,499,30`")
        context.user_data['admin_action'] = 'add_plan'
        return STATE_ADMIN_INPUT

    elif data == "adm_edit_plan":
        await query.message.reply_text("Please send plan details to edit in format:\n`plan_id,new_title,new_price,new_duration`\nExample: `1,Monthly Premium,599,30`")
        context.user_data['admin_action'] = 'edit_plan'
        return STATE_ADMIN_INPUT

    elif data == "adm_del_plan":
        await query.message.reply_text("Please send the **Plan ID** to delete:")
        context.user_data['admin_action'] = 'del_plan'
        return STATE_ADMIN_INPUT

    elif data == "adm_price_list":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("""SELECT apps.name, plans.title, plans.price, plans.id 
                     FROM plans JOIN apps ON plans.app_id = apps.id 
                     ORDER BY apps.name""")
        plans = c.fetchall()
        conn.close()
        
        if not plans:
            await query.message.reply_text("No plans available.")
            return
        
        msg = "💰 **Price List:**\n\n"
        for plan in plans:
            msg += f"🆔 ID: {plan[3]}\n"
            msg += f"📱 {plan[0]}: {plan[1]}\n"
            msg += f"💰 ₹{plan[2]}\n"
            msg += f"-------------------------\n"
        await query.message.reply_text(msg, parse_mode="Markdown")

    elif data == "adm_purchase_stats":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM payments WHERE status='APPROVED'")
        total_purchases = c.fetchone()[0]
        c.execute("SELECT SUM(amount) FROM payments WHERE status='APPROVED'")
        total_revenue = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM payments WHERE status='PENDING'")
        pending = c.fetchone()[0]
        conn.close()
        
        await query.message.reply_text(
            f"📈 **Purchase Statistics:**\n\n"
            f"💰 Total Revenue: ₹{total_revenue}\n"
            f"📦 Total Purchases: {total_purchases}\n"
            f"⏳ Pending: {pending}",
            parse_mode="Markdown"
        )

    elif data == "adm_user_search":
        await query.message.reply_text("Please send **Username** or **User ID** to search:")
        context.user_data['admin_action'] = 'user_search'
        return STATE_ADMIN_INPUT

    elif data == "adm_user_info":
        await query.message.reply_text("Please send **User ID** to view information:")
        context.user_data['admin_action'] = 'user_info'
        return STATE_ADMIN_INPUT

    elif data == "adm_logs":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT action, admin_id, timestamp FROM admin_logs ORDER BY id DESC LIMIT 20")
        logs = c.fetchall()
        conn.close()
        
        if not logs:
            await query.message.reply_text("📋 No admin logs found.")
            return
        
        msg = "📋 **Recent Admin Logs:**\n\n"
        for log in logs:
            msg += f"🕐 {log[2]}\n👤 Admin {log[1]}: {log[0]}\n-------------------------\n"
        await query.message.reply_text(msg)

    elif data == "adm_bot_stats":
        conn = sqlite3.connect('beast_key.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM keys")
        keys = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM payments WHERE status='APPROVED'")
        purchases = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM payments WHERE status='PENDING'")
        pending = c.fetchone()[0]
        c.execute("SELECT SUM(amount) FROM payments WHERE status='APPROVED'")
        revenue = c.fetchone()[0] or 0
        conn.close()
        
        await query.message.reply_text(
            f"📊 **Bot Statistics:**\n\n"
            f"👥 Total Users: {users}\n"
            f"🔑 Keys Generated: {keys}\n"
            f"📦 Purchases: {purchases}\n"
            f"⏳ Pending Payments: {pending}\n"
            f"💰 Total Revenue: ₹{revenue}",
            parse_mode="Markdown"
        )

    elif data == "adm_settings":
        settings_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Change Support Link", callback_data="adm_set_support")],
            [InlineKeyboardButton("🖼 Change QR Image", callback_data="adm_set_qr")],
            [InlineKeyboardButton("📹 Change Tutorial", callback_data="adm_set_tut")],
            [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="adm_back")]
        ])
        await query.message.reply_text("⚙️ **Settings Management**\nSelect an option:", reply_markup=settings_kb, parse_mode="Markdown")
        return

    elif data == "adm_set_qr":
        await query.message.reply_text("Please send the new **QR Image URL** or upload a new **QR Image**:")
        context.user_data['admin_action'] = 'set_qr'
        return STATE_ADMIN_INPUT

    elif data == "adm_set_tut":
        await query.message.reply_text("Please send the new **Tutorial Video File**:")
        context.user_data['admin_action'] = 'set_tut'
        return STATE_ADMIN_INPUT
        
    elif data == "adm_set_support":
        await query.message.reply_text("Please send the new **Support Link** (e.g., http://t.me/username):")
        context.user_data['admin_action'] = 'set_support'
        return STATE_ADMIN_INPUT

    elif data == "adm_back":
        await query.message.reply_text("🛠 **BEAST ADMIN PANEL** 🛠\nSelect an action below:", 
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton("📊 Total Users", callback_data="adm_total_users"), 
                                           InlineKeyboardButton("🟢 Active Users", callback_data="adm_active_users")],
                                          [InlineKeyboardButton("🔴 Banned Users", callback_data="adm_banned_users"), 
                                           InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban_user")],
                                          [InlineKeyboardButton("✅ Unban User", callback_data="adm_unban_user"), 
                                           InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast")],
                                          [InlineKeyboardButton("🎁 Generate Redeem", callback_data="adm_gen_redeem"), 
                                           InlineKeyboardButton("💰 Balance Redeem", callback_data="adm_balance_redeem")],
                                          [InlineKeyboardButton("📋 Redeem List", callback_data="adm_redeem_list"), 
                                           InlineKeyboardButton("🗑 Delete Redeem", callback_data="adm_del_redeem")],
                                          [InlineKeyboardButton("📊 Redeem Stats", callback_data="adm_redeem_stats"), 
                                           InlineKeyboardButton("➕ Add App", callback_data="adm_add_app")],
                                          [InlineKeyboardButton("📋 Add Plan", callback_data="adm_add_plan"), 
                                           InlineKeyboardButton("✏️ Edit Plan", callback_data="adm_edit_plan")],
                                          [InlineKeyboardButton("❌ Delete Plan", callback_data="adm_del_plan"), 
                                           InlineKeyboardButton("💰 Price List", callback_data="adm_price_list")],
                                          [InlineKeyboardButton("📈 Purchase Stats", callback_data="adm_purchase_stats"), 
                                           InlineKeyboardButton("🔍 User Search", callback_data="adm_user_search")],
                                          [InlineKeyboardButton("👤 User Info", callback_data="adm_user_info"), 
                                           InlineKeyboardButton("📋 Admin Logs", callback_data="adm_logs")],
                                          [InlineKeyboardButton("📊 Bot Stats", callback_data="adm_bot_stats"), 
                                           InlineKeyboardButton("⚙️ Settings", callback_data="adm_settings")],
                                          [InlineKeyboardButton("🔄 Restart Bot", callback_data="adm_restart")]
                                      ]), parse_mode="Markdown")
        return STATE_ADMIN_PANEL

    elif data == "adm_restart":
        await query.message.reply_text("🔄 **Restarting bot...**")
        log_admin_action("Restarted bot", user_id)

async def handle_admin_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get('admin_action')
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ You are not authorized.")
        return STATE_MAIN

    if action == 'ban_user':
        try:
            target_id = int(update.message.text.strip())
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (target_id,))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ User {target_id} has been banned.")
            log_admin_action(f"Banned user {target_id}", user_id)
        except:
            await update.message.reply_text("❌ Invalid User ID format.")

    elif action == 'unban_user':
        try:
            target_id = int(update.message.text.strip())
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (target_id,))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ User {target_id} has been unbanned.")
            log_admin_action(f"Unbanned user {target_id}", user_id)
        except:
            await update.message.reply_text("❌ Invalid User ID format.")

    elif action == 'broadcast':
        try:
            message = update.message.text
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("SELECT user_id FROM users WHERE is_banned=0")
            users = c.fetchall()
            conn.close()
            
            sent = 0
            for user in users:
                try:
                    await context.bot.send_message(chat_id=user[0], text=f"📢 **Broadcast Message:**\n\n{message}", parse_mode="Markdown")
                    sent += 1
                except:
                    pass
            
            await update.message.reply_text(f"✅ Broadcast sent to {sent} users.")
            log_admin_action(f"Sent broadcast to {sent} users", user_id)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    elif action == 'gen_redeem':
        try:
            parts = update.message.text.split(',')
            if len(parts) != 3:
                await update.message.reply_text("❌ Invalid format. Use: `app_name,duration_days,usage_limit`")
                return
            
            app_name = parts[0].strip()
            duration = int(parts[1].strip())
            usage_limit = int(parts[2].strip())
            
            code = f"REDEEM-{uuid.uuid4().hex[:8].upper()}"
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("INSERT INTO redeem_codes (code, app_name, duration_days, usage_limit, balance) VALUES (?, ?, ?, ?, ?)",
                     (code, app_name, duration, usage_limit, 0))
            conn.commit()
            conn.close()
            
            await update.message.reply_text(f"✅ Redeem code generated:\n🔑 `{code}`\n\n📱 App: {app_name}\n⏱ Duration: {duration} days\n📊 Limit: {usage_limit} uses", parse_mode="Markdown")
            log_admin_action(f"Generated redeem code {code}", user_id)
        except:
            await update.message.reply_text("❌ Error generating redeem code.")
    
    elif action == 'balance_redeem':
        try:
            parts = update.message.text.split(',')
            if len(parts) != 3:
                await update.message.reply_text("❌ Invalid format. Use: `app_name,balance_amount,usage_limit`")
                return
            
            app_name = parts[0].strip()
            balance = int(parts[1].strip())
            usage_limit = int(parts[2].strip())
            
            code = f"BAL-{uuid.uuid4().hex[:8].upper()}"
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("INSERT INTO redeem_codes (code, app_name, duration_days, usage_limit, balance) VALUES (?, ?, ?, ?, ?)",
                     (code, app_name, 0, usage_limit, balance))
            conn.commit()
            conn.close()
            
            await update.message.reply_text(f"✅ Balance redeem code generated:\n🔑 `{code}`\n\n💰 Balance: ₹{balance}\n📱 App: {app_name}\n📊 Limit: {usage_limit} uses", parse_mode="Markdown")
            log_admin_action(f"Generated balance redeem code {code}", user_id)
        except:
            await update.message.reply_text("❌ Error generating balance redeem code.")

    elif action == 'del_redeem':
        try:
            code = update.message.text.strip()
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("DELETE FROM redeem_codes WHERE code=?", (code,))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ Redeem code {code} deleted.")
            log_admin_action(f"Deleted redeem code {code}", user_id)
        except:
            await update.message.reply_text("❌ Error deleting redeem code.")

    elif action == 'add_app':
        try:
            app_name = update.message.text.strip()
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("INSERT INTO apps (name) VALUES (?)", (app_name,))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ App '{app_name}' added successfully!")
            log_admin_action(f"Added app {app_name}", user_id)
        except:
            await update.message.reply_text("❌ App already exists or error occurred.")

    elif action == 'add_plan':
        try:
            parts = update.message.text.split(',')
            if len(parts) != 4:
                await update.message.reply_text("❌ Invalid format. Use: `app_name,title,price,duration_days`")
                return
            
            app_name = parts[0].strip()
            title = parts[1].strip()
            price = int(parts[2].strip())
            duration = int(parts[3].strip())
            
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("SELECT id FROM apps WHERE name=?", (app_name,))
            app = c.fetchone()
            
            if not app:
                await update.message.reply_text(f"❌ App '{app_name}' not found.")
                conn.close()
                return
            
            app_id = app[0]
            c.execute("INSERT INTO plans (app_id, title, price, duration_days) VALUES (?, ?, ?, ?)",
                     (app_id, title, price, duration))
            conn.commit()
            conn.close()
            
            await update.message.reply_text(f"✅ Plan added successfully!\n📱 App: {app_name}\n📋 Title: {title}\n💰 Price: ₹{price}\n⏱ Duration: {duration} days")
            log_admin_action(f"Added plan {title} for {app_name}", user_id)
        except:
            await update.message.reply_text("❌ Error adding plan.")

    elif action == 'edit_plan':
        try:
            parts = update.message.text.split(',')
            if len(parts) != 4:
                await update.message.reply_text("❌ Invalid format. Use: `plan_id,new_title,new_price,new_duration`")
                return
            
            plan_id = int(parts[0].strip())
            title = parts[1].strip()
            price = int(parts[2].strip())
            duration = int(parts[3].strip())
            
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("UPDATE plans SET title=?, price=?, duration_days=? WHERE id=?", (title, price, duration, plan_id))
            conn.commit()
            conn.close()
            
            await update.message.reply_text(f"✅ Plan {plan_id} updated successfully!")
            log_admin_action(f"Edited plan {plan_id}", user_id)
        except:
            await update.message.reply_text("❌ Error editing plan.")

    elif action == 'del_plan':
        try:
            plan_id = int(update.message.text.strip())
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            c.execute("DELETE FROM plans WHERE id=?", (plan_id,))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ Plan {plan_id} deleted.")
            log_admin_action(f"Deleted plan {plan_id}", user_id)
        except:
            await update.message.reply_text("❌ Error deleting plan.")

    elif action == 'user_search':
        try:
            search = update.message.text.strip()
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            
            if search.isdigit():
                c.execute("SELECT user_id, username, join_date, is_banned, balance FROM users WHERE user_id=?", (int(search),))
            else:
                c.execute("SELECT user_id, username, join_date, is_banned, balance FROM users WHERE username LIKE ?", ('%' + search + '%',))
            
            users = c.fetchall()
            conn.close()
            
            if not users:
                await update.message.reply_text("❌ No users found.")
                return
            
            msg = "🔍 **User Search Results:**\n\n"
            for user in users:
                status = "🔴 Banned" if user[3] == 1 else "🟢 Active"
                msg += f"🆔 ID: `{user[0]}`\n"
                msg += f"👤 Username: @{user[1] or 'N/A'}\n"
                msg += f"📅 Joined: {user[2]}\n"
                msg += f"💰 Balance: ₹{user[4]}\n"
                msg += f"Status: {status}\n"
                msg += f"-------------------------\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
            log_admin_action(f"Searched users with '{search}'", user_id)
        except:
            await update.message.reply_text("❌ Error searching users.")

    elif action == 'user_info':
        try:
            target_id = int(update.message.text.strip())
            conn = sqlite3.connect('beast_key.db')
            c = conn.cursor()
            
            c.execute("SELECT user_id, username, join_date, is_banned, balance FROM users WHERE user_id=?", (target_id,))
            user = c.fetchone()
            
            if not user:
                await update.message.reply_text(f"❌ User {target_id} not found.")
                conn.close()
                return
            
            c.execute("SELECT COUNT(*) FROM keys WHERE user_id=?", (target_id,))
            keys_count = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM payments WHERE user_id=? AND status='APPROVED'", (target_id,))
            purchases = c.fetchone()[0]
            
            c.execute("SELECT SUM(amount) FROM payments WHERE user_id=? AND status='APPROVED'", (target_id,))
            spent = c.fetchone()[0] or 0
            
            conn.close()
            
            status = "🔴 Banned" if user[3] == 1 else "🟢 Active"
            msg = f"👤 **User Information:**\n\n"
            msg += f"🆔 User ID: `{user[0]}`\n"
            msg += f"👤 Username: @{user[1] or 'N/A'}\n"
            msg += f"📅 Joined: {user[2]}\n"
            msg += f"💰 Balance: ₹{user[4]}\n"
            msg += f"Status: {status}\n"
            msg += f"🔑 Keys: {keys_count}\n"
            msg += f"📦 Purchases: {purchases}\n"
            msg += f"💰 Total Spent: ₹{spent}"
            await update.message.reply_text(msg, parse_mode="Markdown")
            log_admin_action(f"Viewed info for user {target_id}", user_id)
        except:
            await update.message.reply_text("❌ Error fetching user information.")

    elif action == 'set_qr':
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            set_setting('qr_file_id', file_id)
            await update.message.reply_text("✅ QR Image updated successfully!")
            log_admin_action("Updated QR image", user_id)
        elif update.message.text and update.message.text.startswith('http'):
            set_setting('qr_image_url', update.message.text)
            await update.message.reply_text("✅ QR Image URL updated successfully!")
            log_admin_action("Updated QR image URL", user_id)
        else:
            await update.message.reply_text("❌ Please send an Image or a valid URL.")

    elif action == 'set_tut':
        if update.message.video:
            file_id = update.message.video.file_id
            set_setting('tutorial_file_id', file_id)
            await update.message.reply_text("✅ Tutorial video updated successfully!")
            log_admin_action("Updated tutorial video", user_id)
        else:
            await update.message.reply_text("❌ Please send a Video file.")
    
    elif action == 'set_support':
        if update.message.text:
            set_setting('support_link', update.message.text)
            await update.message.reply_text(f"✅ Support link updated successfully!\nNew link: {update.message.text}")
            log_admin_action(f"Updated support link to {update.message.text}", user_id)

    context.user_data.pop('admin_action', None)
    return STATE_MAIN

# -------------------------------------------------------------------------
# 11. फ़ॉलबैक और स्टेट बाईपास (State Bypass Helper)
# -------------------------------------------------------------------------
async def global_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    forced = context.user_data.get('forced_state')
    if forced == STATE_WAIT_SCREENSHOT:
        return await handle_screenshot(update, context)
    return STATE_MAIN

# -------------------------------------------------------------------------
# 12. मेन फंक्शन (Main Execution)
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