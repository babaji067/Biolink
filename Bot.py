import nest_asyncio
import asyncio
import re
import os
import sys
from datetime import datetime, timedelta
from telegram import (
    Update, ChatPermissions, InlineKeyboardButton,
    InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

nest_asyncio.apply()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID"))
UPDATE_CHANNEL = os.environ.get("UPDATE_CHANNEL")
ABOUT_URL = os.environ.get("ABOUT_URL")

warn_counts = {}
mute_duration = {}
DEFAULT_MUTE_HOURS = 2
MAX_MUTE_HOURS = 72
MIN_MUTE_HOURS = 2

GROUPS_FILE = "groups.txt"
USERS_FILE = "users.txt"

def save_group_id(group_id):
    if not os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, "w") as f:
            f.write(str(group_id) + "\n")
    else:
        with open(GROUPS_FILE, "r") as f:
            ids = f.read().splitlines()
        if str(group_id) not in ids:
            with open(GROUPS_FILE, "a") as f:
                f.write(str(group_id) + "\n")

def save_user_id(user_id):
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            f.write(str(user_id) + "\n")
    else:
        with open(USERS_FILE, "r") as f:
            ids = f.read().splitlines()
        if str(user_id) not in ids:
            with open(USERS_FILE, "a") as f:
                f.write(str(user_id) + "\n")

def has_username_or_link(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"(http|www\.|t\.me)", text, re.IGNORECASE))

async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    chat = update.effective_chat
    user_id = user.id
    chat_id = chat.id

    if chat.type in ["group", "supergroup"]:
        save_group_id(chat_id)

    if re.search(r"(http|www\.|t\.me|@[\w\d_]+)", user.first_name or "", re.IGNORECASE):
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
                [InlineKeyboardButton("🔓 Unmute – @" + context.bot.username, url=f"https://t.me/{context.bot.username}")]
            ])
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⛔ You are permanently muted in *{chat.title}* because your name contains a link or username.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"[❌] Failed to permanently mute: {e}")
        return

    if has_username_or_link(update.message.text or ""):
        try:
            await update.message.delete()
        except:
            pass

        warn_counts.setdefault(user_id, 0)
        warn_counts[user_id] += 1
        count = warn_counts[user_id]

        warn_text = f"⚠️ {user.first_name}, links are not allowed! Warning {count}/3"

        # Send warning to group
        await update.effective_chat.send_message(warn_text)

        # Send warning to DM
        try:
            await context.bot.send_message(chat_id=user_id, text=warn_text)
        except:
            pass

        if count >= 4:
            hours = mute_duration.get(chat_id, DEFAULT_MUTE_HOURS)
            hours = max(MIN_MUTE_HOURS, min(hours, MAX_MUTE_HOURS))
            mute_until = datetime.utcnow() + timedelta(hours=hours)

            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat.id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=mute_until
                )

keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
                    [InlineKeyboardButton("🔓 Unmute – @" + context.bot.username, url=f"https://t.me/{context.bot.username}")]
                ])

                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"⚔️ *You’ve been muted in {chat.title}*\n\n"
                        f"👤 Name: {user.first_name}\n🆔 ID: {user.id}\n\n"
                        f"⛔ Reason: Link in message\n"
                        f"⏳ Duration: {hours} hour(s)"
                    ),
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                warn_counts[user_id] = 0
            except Exception as e:
                print("Mute failed:", e)

async def set_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Only the owner can set mute duration.")
        return

    chat = update.effective_chat
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("❌ Usage: /setmute <hours>\nExample: /setmute 4")
        return

    hours = int(context.args[0])
    if hours < MIN_MUTE_HOURS or hours > MAX_MUTE_HOURS:
        await update.message.reply_text(f"⚠️ Mute duration must be between {MIN_MUTE_HOURS}-{MAX_MUTE_HOURS} hours.")
        return

    mute_duration[chat.id] = hours
    await update.message.reply_text(f"✅ Mute duration is now set to {hours} hour(s).")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        save_group_id(chat.id)
    if chat.type == "private":
        save_user_id(user_id)

    try:
        member = await context.bot.get_chat_member(chat_id=UPDATE_CHANNEL, user_id=user_id)
        if member.status not in ["member", "administrator", "creator"]:
            raise Exception("Not joined")
    except:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Join Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")]
        ])
        await update.message.reply_text("📛 Please join the update channel to use the bot.", reply_markup=keyboard)
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me To Your Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="show_help")]
    ])

    try:
        with open("start.jpg", "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo,
                caption="👋 *Welcome to BioMuteBot!*\n\n🚫 I protect your group from users having links in their bios or messages.\n\n⚙️ Use /setmute <hours> to customize mute time.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except:
        await update.message.reply_text(
            "👋 *Welcome to BioMuteBot!*\n\n🚫 I protect your group from users having links in their bios or messages.\n\n⚙️ Use /setmute <hours> to customize mute time.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 *BioMuteBot Help*

🔹 /start – Show the bot's welcome menu  
🔹 /setmute <hours> – Set mute duration (owner only)  
🔹 /broadcast -user – Broadcast to groups + users  
🔹 /broadcast -user -pin – Broadcast & pin in groups  
🔹 /status – Check bot status (owner only)  
🔹 /restart – Restart the bot (owner only)  
🔹 /help – Show this help message

⚠️ The bot mutes users who post links or have them in bios/names.
""", parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    g = len(open(GROUPS_FILE).readlines()) if os.path.exists(GROUPS_FILE) else 0
    u = len(open(USERS_FILE).readlines()) if os.path.exists(USERS_FILE) else 0
    await update.message.reply_text(f"📊 Groups: {g}\n👤 Users: {u}")

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text("🔄 Restarting bot...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    pin = "-pin" in context.args
    is_user = "-user" in context.args

    text = " ".join(arg for arg in context.args if not arg.startswith("-"))
    msg = update.message.reply_to_message or update.message

    groups = open(GROUPS_FILE).read().splitlines() if os.path.exists(GROUPS_FILE) else []
    users = open(USERS_FILE).read().splitlines() if os.path.exists(USERS_FILE) else []

    success_g = success_u = fail_g = fail_u = 0

    async def send(to_id, is_group):
        nonlocal success_g, success_u, fail_g, fail_u
        try:
            if msg.photo:
                sent = await context.bot.send_photo(chat_id=int(to_id), photo=msg.photo[-1].file_id, caption=msg.caption or text)
            elif msg.text:
                sent = await context.bot.send_message(chat_id=int(to_id), text=msg.text or text)
            else:
                return
            if is_group and pin:
                await context.bot.pin_chat_message(chat_id=int(to_id), message_id=sent.message_id)
            if is_group:
                success_g += 1
            else:
                success_u += 1
        except Exception as e:
            if is_group:
                fail_g += 1
            else:
                fail_u += 1

    for gid in groups:
        await send(gid, True)
    if is_user:
        for uid in users:
            await send(uid, False)

    await update.message.reply_text(
        f"✅ Broadcast Done!\n"
        f"Groups: {success_g}✅ | {fail_g}❌\n"
        f"Users: {success_u}✅ | {fail_u}❌"
    )

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await help_command(update.callback_query, context)

# Main runner
async def main():
    print("🤖 Bot is starting...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setmute", set_mute))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("restart", restart))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="show_help"))
    app.add_handler(MessageHandler(filters.ALL, check_user))

    await app.initialize()
    await app.start()
    print("✅ Bot is running...")
    await app.updater.start_polling()
    await asyncio.Event().wait()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
