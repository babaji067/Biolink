import nest_asyncio
import asyncio
import re
import os
from datetime import datetime, timedelta
from telegram import (
    Update, ChatPermissions, InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

nest_asyncio.apply()

# 🔧 BOT SETTINGS
BOT_TOKEN = "7592940604:AAE5BKNUFQ7kMqke6dqDfDVzHmkzJqRYWSM"
OWNER_ID = 6562948749
UPDATE_CHANNEL = "@biomute_bot"
ABOUT_URL = "https://t.me/biomute_bot"

warn_counts = {}
mute_duration = {}
DEFAULT_MUTE_HOURS = 2
MAX_MUTE_HOURS = 72
MIN_MUTE_HOURS = 2

GROUPS_FILE = "groups.txt"

def has_username_or_link_in_bio(bio: str) -> bool:
    if not bio:
        return False
    return bool(re.search(r"(http|www\.|t\.me|instagram\.com|facebook\.com|@[\w\d_]+)", bio, re.IGNORECASE))

def save_group_id(group_id):
    try:
        if not os.path.exists(GROUPS_FILE):
            with open(GROUPS_FILE, "w") as f:
                f.write(str(group_id) + "\n")
        else:
            with open(GROUPS_FILE, "r") as f:
                ids = f.read().splitlines()
            if str(group_id) not in ids:
                with open(GROUPS_FILE, "a") as f:
                    f.write(str(group_id) + "\n")
    except Exception as e:
        print(f"[❌] Failed to save group ID: {e}")

async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    chat = update.effective_chat
    user_id = user.id
    chat_id = chat.id

    if chat.type in ["group", "supergroup"]:
        save_group_id(chat_id)

    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
        if member.status in ["administrator", "creator"]:
            return
    except:
        return

    try:
        user_info = await context.bot.get_chat(user_id)
        bio = user_info.bio
    except:
        return

    if has_username_or_link_in_bio(bio) or re.search(r"(http|www\.|t\.me|@[\w\d_]+)", update.message.text or "", re.IGNORECASE):
        try:
            await update.message.delete()
        except:
            pass

        warn_counts.setdefault(user_id, 0)
        warn_counts[user_id] += 1
        count = warn_counts[user_id]

        if count < 4:
            await chat.send_message(
                f"⚠️ {user.first_name}, links or usernames are not allowed in your bio or message! Warning {count}/3"
            )
        else:
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
                    [InlineKeyboardButton("🔁 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
                    [InlineKeyboardButton("🔓 Unmute", url="https://t.me/BioMuteBot")]
                ])

                await chat.send_message(
                    f"⚔️ Bio mute ⚔️\n\n👤 {user.first_name} | 🆔 {user.id}\n\n⛔ Muted for {hours} hour(s).",
                    reply_markup=keyboard
                )
                warn_counts[user_id] = 0
            except Exception as e:
                print("Mute failed:", e)

# /setmute command
async def set_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ["administrator", "creator"]:
            await update.message.reply_text("🚫 Only admins can set mute duration.")
            return
    except:
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("❌ Usage: /setmute <hours>\nExample: /setmute 4")
        return

    hours = int(context.args[0])
    if hours < MIN_MUTE_HOURS or hours > MAX_MUTE_HOURS:
        await update.message.reply_text(f"⚠️ Mute duration must be between {MIN_MUTE_HOURS}-{MAX_MUTE_HOURS} hours.")
        return

    mute_duration[chat.id] = hours
    await update.message.reply_text(f"✅ Mute duration is now set to {hours} hour(s).")

# /start with channel check
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        save_group_id(chat.id)

    try:
        member = await context.bot.get_chat_member(chat_id=UPDATE_CHANNEL, user_id=user_id)
        if member.status not in ["member", "administrator", "creator"]:
            raise Exception("Not joined")
    except:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Join Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")]
        ])
        await update.message.reply_text(
            "📛 Please join the update channel to use the bot.",
            reply_markup=keyboard
        )
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me To Your Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton("ℹ️ About Bot", url=ABOUT_URL)]
    ])

    try:
        with open("start.jpg", "rb") as photo:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo,
                caption="👋 *Welcome to BioMuteBot!*\n\n🚫 I protect your group from users having links or usernames in their bios or messages.\n\n⚙️ Use /setmute <hours> to customize mute time.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except:
        await update.message.reply_text(
            "👋 *Welcome to BioMuteBot!*\n\n🚫 I protect your group from users having links or usernames in their bios or messages.\n\n⚙️ Use /setmute <hours> to customize mute time.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 *BioMuteBot Help*

🔹 /start – Show the bot's welcome menu  
🔹 /setmute <hours> – Set mute duration (admins only)  
🔹 /broadcast <message> – Broadcast to all groups (owner only)  
🔹 /status – Check bot status (owner only)  
🔹 /help – Show this help message

⚠️ The bot automatically mutes users who have links or usernames in their bio or messages.
""", parse_mode="Markdown")

# /status command
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    total = len(open(GROUPS_FILE).readlines()) if os.path.exists(GROUPS_FILE) else 0
    await update.message.reply_text(f"📊 Bot is connected to {total} group(s).")

# /broadcast command
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    if not context.args:
        await update.message.reply_text("❌ Usage: /broadcast <message>")
        return

    text = " ".join(context.args)
    failed = 0
    success = 0

    if not os.path.exists(GROUPS_FILE):
        await update.message.reply_text("📭 No groups found.")
        return

    with open(GROUPS_FILE, "r") as f:
        groups = f.read().splitlines()

    for group_id in groups:
        try:
            await context.bot.send_message(chat_id=int(group_id), text=text)
            success += 1
        except Exception as e:
            print(f"[❌] Text failed in {group_id}: {e}")
            failed += 1

    await update.message.reply_text(f"✅ Broadcast complete!\nSuccess: {success} ✅\nFailed: {failed} ❌")

# Main function
async def main():
    print("🤖 Bot is starting...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setmute", set_mute))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.ALL, check_user))

    await app.initialize()
    await app.start()
    print("✅ Bot is running...")
    await app.updater.start_polling()
    await asyncio.Event().wait()

# Run the bot
loop = asyncio.get_event_loop()
loop.run_until_complete(main())
