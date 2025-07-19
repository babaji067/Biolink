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
from telegram.constants import ChatMemberStatus

nest_asyncio.apply()

# 🔧 CONFIGURATION FROM ENVIRONMENT
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "@yourchannel")
BOT_USERNAME = os.getenv("BOT_USERNAME", "@YourBotUsername")

GROUPS_FILE = "groups.txt"
USERS_FILE = "users.txt"

warn_counts = {}
mute_duration = {}
DEFAULT_MUTE_HOURS = 2
MAX_MUTE_HOURS = 72
MIN_MUTE_HOURS = 2


def save_id(file, _id):
    with open(file, "a+") as f:
        f.seek(0)
        ids = f.read().splitlines()
        if str(_id) not in ids:
            f.write(f"{_id}\n")


def remove_id(file, _id):
    if os.path.exists(file):
        with open(file, "r") as f:
            lines = f.readlines()
        with open(file, "w") as f:
            for line in lines:
                if line.strip() != str(_id):
                    f.write(line)


def contains_link_or_username(text):
    return bool(re.search(r"(https?://|www\.)", text, re.IGNORECASE))


def contains_username(text):
    return bool(re.search(r"@\w+", text))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_id(USERS_FILE, user.id)

    if UPDATE_CHANNEL:
        try:
            member = await context.bot.get_chat_member(UPDATE_CHANNEL, user.id)
            if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                raise Exception
        except:
            join_button = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")]
            ])
            await update.message.reply_text(
                f"👋 Hello {user.first_name},\n\nPlease join our update channel to use this bot.",
                reply_markup=join_button
            )
            return

    buttons = [
        [InlineKeyboardButton("➕ Add Me To Your Group ➕", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}?startgroup=true")],
        [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    await update.message.reply_text(
        f"👋 Welcome, {user.first_name}!\n\nI’m a Bio Mute Bot. I will auto-mute users who have links in their name, bio, or messages.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    help_text = (
        "🤖 *Bio Mute Bot Commands:*\n\n"
        "/start - Show welcome message\n"
        "/setmute <hours> - Set mute duration (Owner only)\n"
        "/broadcast -user -pin (reply/text/photo) - Broadcast to all\n"
        "/status - Show bot status (Owner only)\n"
        "/restart - Restart bot (Owner only)\n"
    )
    await query.message.reply_text(help_text, parse_mode="Markdown")


async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        save_id(USERS_FILE, update.message.from_user.id)
    else:
        save_id(GROUPS_FILE, update.message.chat.id)

        user = update.message.from_user
        text = update.message.text or ""
        user_bio = ""
        try:
            user_info = await context.bot.get_chat_member(update.message.chat.id, user.id)
            user_bio = user_info.user.bio or ""
        except:
            pass

        has_link = contains_link_or_username(text) or contains_link_or_username(user_bio)
        has_username_in_name = contains_link_or_username(user.first_name)

if has_username_in_name:
            await permanently_mute_user(update, context, user)
            return

        if has_link:
            key = f"{update.message.chat.id}_{user.id}"
            warn_counts[key] = warn_counts.get(key, 0) + 1

            await update.message.delete()
            await send_warning(update, context, user, warn_counts[key])

            if warn_counts[key] >= 4:
                await mute_user(update, context, user)


async def permanently_mute_user(update, context, user):
    try:
        await context.bot.restrict_chat_member(
            chat_id=update.message.chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                f"⚔️ *Bio mute*\n\n"
                f"👤 Name: {user.first_name}\n🆔 ID: {user.id}\n"
                "⛔ You are permanently muted due to link in your name."
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
                [InlineKeyboardButton("🔓 Unmute", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}")]
            ])
        )
    except:
        pass


async def send_warning(update, context, user, count):
    msg = f"⚠️ {user.first_name} ({user.id}), you posted a link. Warning {count}/3."
    await update.message.chat.send_message(msg, parse_mode="Markdown")

    try:
        await context.bot.send_message(user.id, msg, parse_mode="Markdown")
    except:
        remove_id(USERS_FILE, user.id)


async def mute_user(update, context, user):
    duration = mute_duration.get(update.message.chat.id, DEFAULT_MUTE_HOURS)
    until_date = datetime.now() + timedelta(hours=duration)

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.message.chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        mute_text = (
            f"⚔️ *Bio mute*\n\n"
            f"👤 Name: {user.first_name}\n🆔 ID: {user.id}\n"
            f"⛔ Muted for {duration} hours."
        )

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
            [InlineKeyboardButton("🔓 Unmute", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}")]
        ])

        await update.message.chat.send_message(mute_text, parse_mode="Markdown", reply_markup=buttons)

        try:
            await context.bot.send_message(user.id, mute_text, parse_mode="Markdown", reply_markup=buttons)
        except:
            remove_id(USERS_FILE, user.id)
    except:
        pass


async def set_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        return

    try:
        hours = int(context.args[0])
        if MIN_MUTE_HOURS <= hours <= MAX_MUTE_HOURS:
            mute_duration[update.message.chat.id] = hours
            await update.message.reply_text(f"✅ Mute duration set to {hours} hours.")
        else:
            await update.message.reply_text(f"⚠️ Enter a value between {MIN_MUTE_HOURS} and {MAX_MUTE_HOURS}.")
    except:
        await update.message.reply_text("⚠️ Usage: /setmute <hours>")


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        return

    args = context.args
    text = update.message.text or ""
    is_user = "-user" in args
    should_pin = "-pin" in args

    users = []
    groups = []

    if is_user:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r") as f:
                users = [int(i.strip()) for i in f if i.strip().isdigit()]

    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, "r") as f:
            groups = [int(i.strip()) for i in f if i.strip().isdigit()]

content = None
    if update.message.reply_to_message:
        content = update.message.reply_to_message

    for gid in groups:
        try:
            if content and content.photo:
                await context.bot.send_photo(chat_id=gid, photo=content.photo[-1].file_id, caption=content.caption)
            elif content and content.text:
                msg = await context.bot.send_message(chat_id=gid, text=content.text)
                if should_pin:
                    await context.bot.pin_chat_message(gid, msg.message_id)
            elif context.args:
                msg = await context.bot.send_message(chat_id=gid, text=" ".join(context.args))
                if should_pin:
                    await context.bot.pin_chat_message(gid, msg.message_id)
        except:
            remove_id(GROUPS_FILE, gid)

    for uid in users:
        try:
            if content and content.photo:
                await context.bot.send_photo(chat_id=uid, photo=content.photo[-1].file_id, caption=content.caption)
            elif content and content.text:
                await context.bot.send_message(chat_id=uid, text=content.text)
            elif context.args:
                await context.bot.send_message(chat_id=uid, text=" ".join(context.args))
        except:
            remove_id(USERS_FILE, uid)

    await update.message.reply_text("✅ Broadcast sent.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        return

    group_count = len(open(GROUPS_FILE).readlines()) if os.path.exists(GROUPS_FILE) else 0
    user_count = len(open(USERS_FILE).readlines()) if os.path.exists(USERS_FILE) else 0
    duration = mute_duration.get(update.message.chat.id, DEFAULT_MUTE_HOURS)

    await update.message.reply_text(
        f"🤖 *Bot Status:*\n"
        f"👥 Groups: {group_count}\n"
        f"👤 Users: {user_count}\n"
        f"⏱ Default Mute: {duration} hrs",
        parse_mode="Markdown"
    )


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != OWNER_ID:
        return

    await update.message.reply_text("🔄 Restarting bot...")
    os.execl(sys.executable, sys.executable, *sys.argv)


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setmute", set_mute))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("restart", restart))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="help"))
    app.add_handler(MessageHandler(filters.ALL, check_user))

    print("Bot is running...")
    app.run_polling()


if name == "main":
    main()
