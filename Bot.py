import nest_asyncio
import asyncio
import re
import os
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

GROUPS_FILE = "groups.txt"
USERS_FILE = "users.txt"
warn_counts = {}
mute_duration = 2  # default global mute duration


def has_link(text: str) -> bool:
    return bool(re.search(r"(http|www\.|t\.me|instagram\.com|facebook\.com)", text, re.IGNORECASE))


def has_username(text: str) -> bool:
    return bool(re.search(r"@\w+", text)) and not has_link(text)


def save_id(file, id):
    if not os.path.exists(file):
        with open(file, "w") as f:
            f.write(str(id) + "\n")
    else:
        with open(file, "r") as f:
            ids = f.read().splitlines()
        if str(id) not in ids:
            with open(file, "a") as f:
                f.write(str(id) + "\n")


async def get_bio(context, user_id):
    try:
        chat = await context.bot.get_chat(user_id)
        return chat.bio or ""
    except:
        return ""


async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.from_user:
        return

    user = update.message.from_user
    chat = update.effective_chat
    user_id = user.id
    chat_id = chat.id
    msg_text = update.message.text or ""

    if chat.type in ["group", "supergroup"]:
        save_id(GROUPS_FILE, chat_id)
    else:
        save_id(USERS_FILE, user_id)

    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
        if member.status in ["administrator", "creator"]:
            return
    except:
        return

    # FIRST NAME check → Permanent Mute
    if has_link(user.first_name):
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
                [InlineKeyboardButton("🔓 Unmute", url=f"https://t.me/{context.bot.username}")]
            ])
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⚔️ Bio mute ⚔️\n\n👤 {user.first_name} | 🆔 {user.id}\n\n⛔ Permanently muted due to link in name.",
                reply_markup=keyboard
            )
        except:
            pass
        return

    # NORMAL check → link in bio or message
    if has_link(msg_text) or has_link(await get_bio(context, user_id)):
        if not has_link(user.first_name):  # Already muted above
            try:
                await update.message.delete()
            except:
                pass

            warn_counts.setdefault(user_id, 0)
            warn_counts[user_id] += 1
            count = warn_counts[user_id]

            if count < 4:
                warn_msg = f"⚠️ {user.first_name}, links are not allowed in your bio or message ! Warning {count}/3"
                try:
                    await chat.send_message(warn_msg)
                    await context.bot.send_message(user_id, warn_msg)
                except:
                    pass
            else:
                until = datetime.utcnow() + timedelta(hours=mute_duration)
                try:
                    await context.bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until
                    )
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
                        [InlineKeyboardButton("🔓 Unmute", url=f"https://t.me/{context.bot.username}")]
                    ])
                    msg = f"⚔️ Bio mute ⚔️\n\n👤 {user.first_name} | 🆔 {user.id}\n\n⛔ Muted for {mute_duration} hour(s)."
                    await chat.send_message(msg, reply_markup=keyboard)
                    await context.bot.send_message(user_id, msg, reply_markup=keyboard)
                    warn_counts[user_id] = 0
                except:
                    pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        save_id(GROUPS_FILE, chat.id)
    else:
        save_id(USERS_FILE, user_id)

    try:
        member = await context.bot.get_chat_member(UPDATE_CHANNEL, user_id)
        if member.status not in ["member", "administrator", "creator"]:
            raise Exception()
    except:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Join Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")]
        ])
        return await update.message.reply_text(
            "📛 Please join the update channel to use the bot.",
            reply_markup=keyboard
        )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me To Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="show_help")]
    ])

    try:
        with open("start.jpg", "rb") as img:
            await context.bot.send_photo(chat.id, img, caption="👋 Welcome to BioMuteBot! You're now ready to use the bot. Enjoy the features and stay safe! 🚀", reply_markup=keyboard)
    except:
        await update.message.reply_text("👋 Welcome to BioMuteBot! You're now ready to use the bot. Enjoy the features and stay safe! 🚀", reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
🤖 BioMuteBot Help

/start – Show welcome menu
/setmute <hours> – Set global mute duration (owner only)
/broadcast – Send message to all groups + users
/status – Show group/user count
/help – Show this help
""")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.data == "show_help":
        await update.callback_query.answer()
        await help_command(update.callback_query, context)


async def set_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("🚫 Only bot owner can set mute duration.")
    if len(context.args) != 1 or not context.args[0].isdigit():
        return await update.message.reply_text("❌ Usage: /setmute <hours>")
    global mute_duration
    hours = int(context.args[0])
    if hours < 2 or hours > 72:
        return await update.message.reply_text("⚠️ Mute duration must be between 2–72 hours.")
    mute_duration = hours
    await update.message.reply_text(f"✅ Global mute duration set to {hours} hour(s).")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    groups = len(open(GROUPS_FILE).readlines()) if os.path.exists(GROUPS_FILE) else 0
    users = len(open(USERS_FILE).readlines()) if os.path.exists(USERS_FILE) else 0
    await update.message.reply_text(f"📊 Groups: {groups}\n👤 Users: {users}")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    success = 0
    failed = 0

    text = None
    photo_id = None
    caption = None

    if update.message.reply_to_message:
        if update.message.reply_to_message.photo:
            photo_id = update.message.reply_to_message.photo[-1].file_id
            caption = update.message.reply_to_message.caption or ""
        else:
            text = update.message.reply_to_message.text
    else:
        text = " ".join(context.args)

    targets = []

    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE) as f:
            targets += [(int(x.strip()), False) for x in f if x.strip()]
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE) as f:
            targets += [(int(x.strip()), True) for x in f if x.strip()]

    for target_id, is_user in targets:
        try:
            if photo_id:
                msg = await context.bot.send_photo(target_id, photo_id, caption=caption)
            elif text:
                msg = await context.bot.send_message(target_id, text)
            else:
                continue
            if not is_user:
                await msg.pin()
            success += 1
        except Exception as e:
            print(f"[❌] Failed to send to {target_id}: {e}")
            failed += 1

    await update.message.reply_text(f"✅ Broadcast done.\nSuccess: {success} ✅\nFailed: {failed} ❌")


async def main():
    print("🤖 Bot starting...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setmute", set_mute))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.ALL, check_user))

    await app.initialize()
    await app.start()
    print("✅ Bot running...")
    await app.updater.start_polling()
    await asyncio.Event().wait()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
