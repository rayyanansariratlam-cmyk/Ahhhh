import logging
import json
import os
import random
import string
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# ================= CONFIGURATION =================
BOT_TOKEN = "8603867683:AAHG3li1yqf2WnyiopKB10kd7C_A--V9pu8"
ADMIN_ID = 8170952537  # Admin Integer ID

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation States Matrix
(
    U_MAIN_CHOICE, U_BRAND_CHOICE, U_PLAN_CHOICE, U_SCREENSHOT, U_REDEEM,
    A_MENU_CHOICE, A_BRAND_NAME, A_DEL_BRAND, A_PLAN_BRAND, A_PLAN_DETAILS, A_DEL_PLAN,
    A_RED_BRAND, A_RED_DETAILS, A_DEL_RED, A_QR, A_TUTORIAL, A_SUPPORT, A_BROADCAST
) = range(18)

# ================= DATABASE ENGINE =================
class JSONDatabase:
    def __init__(self, filename="premium_data.json"):
        self.filename = filename
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r') as f:
                self.data = json.load(f)
        else:
            self.data = {
                "users": {},          
                "brands": ["Rolex Mod", "Ztrax"],         
                "plans": {
                    "Rolex Mod": [
                        {"id": "P1", "duration_hours": 5, "price": 30},
                        {"id": "P2", "duration_hours": 24, "price": 99}
                    ]
                },          
                "keys": {},           
                "redeem_codes": {},   
                "payments": {},       
                "settings": {
                    "qr_url": "https://kommodo.ai/i/qF4FLWL7wK3SjLsyNmH1",
                    "tutorial_video": "None", 
                    "support_user": "@Narendra_Modih"
                }
            }
            self.save()

    def save(self):
        with open(self.filename, 'w') as f:
            json.dump(self.data, f, indent=4)

    def register_user(self, uid, username):
        uid_str = str(uid)
        if uid_str not in self.data["users"]:
            self.data["users"][uid_str] = {
                "username": username or "Unknown",
                "joined": datetime.now().isoformat()
            }
            self.save()

db = JSONDatabase()

def generate_id(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# ================= REUSABLE KEYBOARDS (KEYBOARD SIDE) =================
def user_bottom_keyboard():
    return ReplyKeyboardMarkup([
        ["🔑 Purchase Key", "📋 My Keys"],
        ["🎁 Redeem Code", "📚 How To Buy?"],
        ["🆔 My ID", "🆘 Contact Support"]
    ], resize_keyboard=True)

def cancel_bottom_keyboard():
    return ReplyKeyboardMarkup([["🔙 Cancel & Go Back"]], resize_keyboard=True)

def admin_bottom_keyboard():
    return ReplyKeyboardMarkup([
        ["➕ Add Brand", "❌ Delete Brand"],
        ["➕ Add Plan", "❌ Delete Plan"],
        ["➕ Add Redeem Code", "❌ Delete Redeem Code"],
        ["🖼 Change QR", "📹 Change Tutorial"],
        ["📞 Change Support", "📢 Broadcast"],
        ["📊 Stats & Users", "🔙 Exit Admin Panel"]
    ], resize_keyboard=True)

# ================= USER CONTROLLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username)
    
    await update.message.reply_text(
        f"👋 *Welcome {user.first_name} to Premium Key Store!*\n\n"
        "✨ Niche diye gaye keyboard buttons ka use karein:",
        reply_markup=user_bottom_keyboard(),
        parse_mode="Markdown"
    )
    return U_MAIN_CHOICE

async def user_main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid_str = str(update.effective_user.id)

    if text == "🔑 Purchase Key":
        if not db.data["brands"]:
            await update.message.reply_text("⚠️ No active brands configuration available.")
            return U_MAIN_CHOICE
        kb = [[b] for b in db.data["brands"]]
        kb.append(["🔙 Cancel & Go Back"])
        await update.message.reply_text("🛒 *Select Available Brand from bottom keyboard:*", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode="Markdown")
        return U_BRAND_CHOICE

    elif text == "📋 My Keys":
        user_keys = db.data["keys"].get(uid_str, [])
        if not user_keys:
            await update.message.reply_text("📋 *You don't have any active license keys right now.*", parse_mode="Markdown")
            return U_MAIN_CHOICE
        
        out = "📋 *YOUR LICENSE KEYS:*\n\n"
        for idx, k in enumerate(user_keys, 1):
            out += f"*{idx}. Brand:* {k['brand']}\n┗ 🔑 Key: `{k['key']}`\n┗ ⏳ Status: {k['status']}\n\n"
        await update.message.reply_text(out, parse_mode="Markdown")
        return U_MAIN_CHOICE

    elif text == "🎁 Redeem Code":
        await update.message.reply_text("🎁 *Please type/enter your Redeem Code below:*", reply_markup=cancel_bottom_keyboard(), parse_mode="Markdown")
        return U_REDEEM

    elif text == "📚 How To Buy?":
        await update.message.reply_text(f"📚 *How to Purchase Video/Tutorial Link:*\n{db.data['settings']['tutorial_video']}")
        return U_MAIN_CHOICE

    elif text == "🆔 My ID":
        await update.message.reply_text(f"🆔 *Your Telegram ID:* `{uid_str}`", parse_mode="Markdown")
        return U_MAIN_CHOICE

    elif text == "🆘 Contact Support":
        await update.message.reply_text(f"🆘 *Official Customer Support handle:* {db.data['settings']['support_user']}")
        return U_MAIN_CHOICE
    
    return U_MAIN_CHOICE

async def user_brand_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    brand = update.message.text
    if brand == "🔙 Cancel & Go Back":
        await start(update, context)
        return U_MAIN_CHOICE

    if brand not in db.data["brands"]:
        await update.message.reply_text("⚠️ Invalid Brand selection. Please select from the keyboard.")
        return U_BRAND_CHOICE

    context.user_data["selected_brand"] = brand
    plans = db.data["plans"].get(brand, [])
    if not plans:
        await update.message.reply_text(f"⚠️ No active plans found for *{brand}*.", parse_mode="Markdown")
        return U_BRAND_CHOICE

    kb = [[f"{p['duration_hours']} Hours - ₹{p['price']}"] for p in plans]
    kb.append(["🔙 Cancel & Go Back"])
    await update.message.reply_text(f"🛒 *{brand}* plans matrix selection:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return U_PLAN_CHOICE

async def user_plan_choice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice == "🔙 Cancel & Go Back":
        await start(update, context)
        return U_MAIN_CHOICE

    brand = context.user_data.get("selected_brand")
    plans = db.data["plans"].get(brand, [])
    
    selected_plan = None
    for p in plans:
        if f"{p['duration_hours']} Hours - ₹{p['price']}" == choice:
            selected_plan = p
            break

    if not selected_plan:
        await update.message.reply_text("⚠️ Invalid plan structural selection.")
        return U_PLAN_CHOICE

    order_id = f"ORD-{generate_id(5)}"
    context.user_data["current_order"] = {"order_id": order_id, "brand": brand, "amount": selected_plan["price"], "hours": selected_plan["duration_hours"]}

    pay_text = (
        f"✨ *PAYMENT GATEWAY INTERFACE*\n\n"
        f"• *Order ID:* `{order_id}`\n"
        f"• *Brand:* {brand}\n"
        f"• *Amount:* ₹{selected_plan['price']}\n\n"
        f"📸 Scan the QR photo below, fulfill payment, and send the payment receipt screenshot directly here."
    )
    
    # Strictly Photo-based generation matching exact criteria
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=db.data["settings"]["qr_url"],
        caption=pay_text,
        reply_markup=cancel_bottom_keyboard(),
        parse_mode="Markdown"
    )
    return U_SCREENSHOT

async def user_screenshot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 Cancel & Go Back":
        await start(update, context)
        return U_MAIN_CHOICE

    if not update.message.photo:
        await update.message.reply_text("⚠️ Please upload or send a clear payment screenshot photo.")
        return U_SCREENSHOT

    order = context.user_data.get("current_order")
    photo_id = update.message.photo[-1].file_id
    order_id = order["order_id"]

    db.data["payments"][order_id] = {
        "uid": update.effective_user.id, "username": update.effective_user.username or "None",
        "brand": order["brand"], "amount": order["amount"], "hours": order["hours"], "status": "PENDING"
    }
    db.save()

    admin_text = (
        f"📦 *NEW TRANSACTION PAYMENT PENDING*\n\n"
        f"• *Order ID:* `{order_id}`\n"
        f"• *User:* `{update.effective_user.id}`\n"
        f"• *Brand Match:* {order['brand']}\n"
        f"• *Amount:* ₹{order['amount']}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"a_app_{order_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"a_rej_{order_id}")]
    ])
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=admin_text, reply_markup=kb, parse_mode="Markdown")

    await update.message.reply_text("⏳ *Payment Receipt received! Admin is verifying your transaction framework.*", reply_markup=user_bottom_keyboard(), parse_mode="Markdown")
    return U_MAIN_CHOICE

async def user_redeem_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    if code == "🔙 Cancel & Go Back":
        await start(update, context)
        return U_MAIN_CHOICE

    uid_str = str(update.effective_user.id)
    if code not in db.data["redeem_codes"]:
        await update.message.reply_text("❌ Invalid Redeem Code.", reply_markup=user_bottom_keyboard())
        return U_MAIN_CHOICE

    rc = db.data["redeem_codes"][code]
    if len(rc["used_by"]) >= rc["limit"] or uid_str in rc["used_by"]:
        await update.message.reply_text("❌ Code already used or expired limit parameters.", reply_markup=user_bottom_keyboard())
        return U_MAIN_CHOICE

    gen_key = f"{rc['brand'].upper()}-REDEEM-{generate_id(4)}"
    if uid_str not in db.data["keys"]: db.data["keys"][uid_str] = []
    db.data["keys"][uid_str].append({"brand": rc["brand"], "key": gen_key, "status": "ACTIVE"})
    rc["used_by"].append(uid_str)
    db.save()

    await update.message.reply_text(f"🎉 *Redeem Successful!*\n• Key: `{gen_key}`\n• Brand: {rc['brand']}", reply_markup=user_bottom_keyboard(), parse_mode="Markdown")
    return U_MAIN_CHOICE


# ================= FULL ADMIN MASTER INTERFACE =================
async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🛠 *CORE CENTRAL ADMINISTRATIVE OVERRIDE MODES*", reply_markup=admin_bottom_keyboard(), parse_mode="Markdown")
    return A_MENU_CHOICE

async def admin_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Exit Admin Panel":
        await start(update, context)
        return U_MAIN_CHOICE

    if text == "➕ Add Brand":
        await update.message.reply_text("Enter name of the brand to add:", reply_markup=cancel_bottom_keyboard())
        return A_BRAND_NAME
    
    elif text == "❌ Delete Brand":
        if not db.data["brands"]: await update.message.reply_text("No brands to delete."); return A_MENU_CHOICE
        kb = [[b] for b in db.data["brands"]]; kb.append(["🔙 Cancel & Go Back"])
        await update.message.reply_text("Select brand to delete:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return A_DEL_BRAND

    elif text == "➕ Add Plan":
        kb = [[b] for b in db.data["brands"]]; kb.append(["🔙 Cancel & Go Back"])
        await update.message.reply_text("Select Brand target destination map:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return A_PLAN_BRAND

    elif text == "❌ Delete Plan":
        kb = [[b] for b in db.data["brands"]]; kb.append(["🔙 Cancel & Go Back"])
        await update.message.reply_text("Select Brand to remove its plans:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return A_DEL_PLAN

    elif text == "➕ Add Redeem Code":
        kb = [[b] for b in db.data["brands"]]; kb.append(["🔙 Cancel & Go Back"])
        await update.message.reply_text("Select brand for Redeem Code:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return A_RED_BRAND

    elif text == "❌ Delete Redeem Code":
        if not db.data["redeem_codes"]: await update.message.reply_text("No keys available."); return A_MENU_CHOICE
        kb = [[c] for c in db.data["redeem_codes"].keys()]; kb.append(["🔙 Cancel & Go Back"])
        await update.message.reply_text("Select redeem code to delete:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return A_DEL_RED

    elif text == "🖼 Change QR":
        await update.message.reply_text("Send dynamic image checkout direct link target url string:", reply_markup=cancel_bottom_keyboard())
        return A_QR

    elif text == "📹 Change Tutorial":
        await update.message.reply_text("Send tutorial data link documentation string:", reply_markup=cancel_bottom_keyboard())
        return A_TUTORIAL

    elif text == "📞 Change Support":
        await update.message.reply_text("Send support username contact text handle:", reply_markup=cancel_bottom_keyboard())
        return A_SUPPORT

    elif text == "📢 Broadcast":
        await update.message.reply_text("Send text block parameters message to broadcast out:", reply_markup=cancel_bottom_keyboard())
        return A_BROADCAST

    elif text == "📊 Stats & Users":
        await update.message.reply_text(f"📊 *TELEMETRY LOGS ANALYSIS*\n\n• User Node Entries: {len(db.data['users'])}\n• Configured Brands: {len(db.data['brands'])}", parse_mode="Markdown")
        return A_MENU_CHOICE

    return A_MENU_CHOICE

# ================= ADMIN SAVE LOGIC FUNCTIONS =================
async def admin_brand_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    if txt not in db.data["brands"]: db.data["brands"].append(txt); db.save()
    await update.message.reply_text(f"✅ Brand '{txt}' appended effectively.")
    return await admin_entry(update, context)

async def admin_brand_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    if txt in db.data["brands"]: db.data["brands"].remove(txt); db.save()
    await update.message.reply_text(f"✅ Brand '{txt}' dropped successfully.")
    return await admin_entry(update, context)

async def admin_plan_brand_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    context.user_data["adm_plan_brand"] = txt
    await update.message.reply_text("📥 Send configuration values exactly as schema format: `Hours,Price` (e.g. `24,150`)", reply_markup=cancel_bottom_keyboard())
    return A_PLAN_DETAILS

async def admin_plan_details_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    try:
        hrs, prc = map(int, txt.split(","))
        br = context.user_data.get("adm_plan_brand")
        if br not in db.data["plans"]: db.data["plans"][br] = []
        db.data["plans"][br].append({"id": generate_id(3), "duration_hours": hrs, "price": prc})
        db.save()
        await update.message.reply_text("✅ Core storage plan configurations appended.")
    except:
        await update.message.reply_text("⚠️ Matrix format configuration parsing error.")
    return await admin_entry(update, context)

async def admin_plan_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    if txt in db.data["plans"]: db.data["plans"][txt] = []; db.save()
    await update.message.reply_text(f"✅ Plans dropped for {txt}.")
    return await admin_entry(update, context)

async def admin_red_brand_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    context.user_data["adm_red_brand"] = txt
    await update.message.reply_text("📥 Send Redeem matrix specifications exactly as formatting pattern: `Code,Hours,Limit` (e.g. `FREE50,24,5`)", reply_markup=cancel_bottom_keyboard())
    return A_RED_DETAILS

async def admin_red_details_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    try:
        code, hrs, lim = txt.split(",")
        br = context.user_data.get("adm_red_brand")
        db.data["redeem_codes"][code.strip()] = {"brand": br, "duration_hours": int(hrs), "limit": int(lim), "used_by": []}
        db.save()
        await update.message.reply_text(f"✅ Redeem verification code token '{code}' loaded.")
    except:
        await update.message.reply_text("⚠️ Scheme deployment mismatch configuration error.")
    return await admin_entry(update, context)

async def admin_red_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    if txt in db.data["redeem_codes"]: del db.data["redeem_codes"][txt]; db.save()
    await update.message.reply_text("✅ Redeem identifier dropped effectively.")
    return await admin_entry(update, context)

async def admin_qr_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    db.data["settings"]["qr_url"] = txt
    db.save()
    await update.message.reply_text("✅ System transaction payment image target updated.")
    return await admin_entry(update, context)

async def admin_tut_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    db.data["settings"]["tutorial_video"] = txt
    db.save()
    await update.message.reply_text("✅ Documentation sequence modified.")
    return await admin_entry(update, context)

async def admin_sup_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    db.data["settings"]["support_user"] = txt
    db.save()
    await update.message.reply_text("✅ Base customer communication link configured.")
    return await admin_entry(update, context)

async def admin_broadcast_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt == "🔙 Cancel & Go Back": return await admin_entry(update, context)
    users = list(db.data["users"].keys())
    for u in users:
        try: await context.bot.send_message(chat_id=int(u), text=f"📢 *BROADCAST ALERT:*\n\n{txt}", parse_mode="Markdown")
        except: pass
    await update.message.reply_text("✅ Global payload distributed through all clusters.")
    return await admin_entry(update, context)

async def admin_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    oid = data.split("_")[-1]
    pay = db.data["payments"].get(oid)
    if not pay: return

    if data.startswith("a_app_"):
        pay["status"] = "APPROVED"
        gen_key = f"{pay['brand'].upper()}-{generate_id(4)}-{generate_id(4)}"
        
        uid_str = str(pay["uid"])
        if uid_str not in db.data["keys"]: db.data["keys"][uid_str] = []
        db.data["keys"][uid_str].append({"brand": pay["brand"], "key": gen_key, "status": "ACTIVE"})
        db.save()

        try: await context.bot.send_message(chat_id=pay["uid"], text=f"🎉 *ORDER APPROVED!*\nYour Key: `{gen_key}`", parse_mode="Markdown")
        except: pass
        await query.message.edit_caption(caption="✅ Order Verification Check: Approved successfully.")
    else:
        pay["status"] = "REJECTED"
        db.save()
        try: await context.bot.send_message(chat_id=pay["uid"], text="❌ *Your payment verification checklist verification failed.*", parse_mode="Markdown")
        except: pass
        await query.message.edit_caption(caption="❌ Order Verification Check: Manually Rejected.")

# ================= ORCHESTRATION PIPELINE ENGINE =================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("admin", admin_entry)],
        states={
            U_MAIN_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_main_menu_handler)],
            U_BRAND_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_brand_choice_handler)],
            U_PLAN_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_plan_choice_handler)],
            U_SCREENSHOT: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), user_screenshot_handler)],
            U_REDEEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_redeem_handler)],
            
            A_MENU_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_choice)],
            A_BRAND_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_brand_save)],
            A_DEL_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_brand_del)],
            A_PLAN_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plan_brand_sel)],
            A_PLAN_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plan_details_save)],
            A_DEL_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plan_del)],
            A_RED_BRAND: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_red_brand_sel)],
            A_RED_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_red_details_save)],
            A_DEL_RED: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_red_del)],
            A_QR: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_qr_save)],
            A_TUTORIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_tut_save)],
            A_SUPPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_sup_save)],
            A_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_save)]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(admin_inline_callback, pattern="^a_"))
    
    print("🚀 Master Full Suite Bot Engine Framework Operational Interceptors Deploy Mode Live.")
    app.run_polling()

if __name__ == "__main__":
    main()
