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
        return

    save_id(GROUPS_FILE, update.message.chat.id)
    user = update.message.from_user
    text = update.message.text or ""

    try:
        user_chat = await context.bot.get_chat(user.id)
        user_bio = user_chat.bio or ""
    except:
        user_bio = ""

    has_link = contains_link_or_username(text) or contains_link_or_username(user_bio)
    has_username_in_name = contains_link_or_username(user.first_name)

    if has_username_in_name:
        await permanently_mute_user(update, context, user)
        return

    if has_link:
        key = f"{update.message.chat.id}_{user.id}"
        warn_counts[key] = warn_counts.get(key, 0) + 1

        try:
            await update.message.delete()
        except:
            pass

        await send_warning(update, context, user, warn_counts[key])

        if warn_counts[key] >= 4:
            success = await mute_user(update, context, user)
            if success:
                warn_counts[key] = 0  # Reset warn count after mute

async def mute_user(update, context, user):
    chat_id = update.message.chat.id
    user_id = user.id
    hours = mute_duration.get(chat_id, DEFAULT_MUTE_HOURS)
    until_date = datetime.utcnow() + timedelta(hours=hours)

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"⚔️ *Bio mute*\n\n"
                f"👤 Name: {user.first_name}\n🆔 ID: `{user.id}`\n"
                f"⛔ You are muted for {hours} hours due to links in bio or messages."
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
                [InlineKeyboardButton("🔓 Unmute", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}")]
            ])
        )
        return True
    except:
        return False

async def send_warning(update, context, user, count):
    display_count = min(count, 3)  # Max warning display 3/3
    msg = (
        f"⚠️ {user.first_name} (`{user.id}`), "
        "Using links or usernames in your bio or messages is not allowed. "
        f"Please follow our community policies. Warning {display_count}/3."
    )

    await update.message.chat.send_message(msg, parse_mode="Markdown")

    try:
        await context.bot.send_message(user.id, msg, parse_mode="Markdown")
    except:
        remove_id(USERS_FILE, user.id) 


async def check_new_member_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        # ✅ Only check first name (no bio)
        if contains_link_or_username(member.first_name) or contains_username(member.first_name):
            try:
                await context.bot.restrict_chat_member(
                    chat_id=update.message.chat.id,
                    user_id=member.id,
                    permissions=ChatPermissions(can_send_messages=False)
                )

                await context.bot.send_message(
                    chat_id=member.id,
                    text=(
                        f"⚔️ *Bio mute*\n\n"
                        f"👤 Name: {member.first_name}\n"
                        f"🆔 ID: `{member.id}`\n\n"
                        f"⛔ You are permanently muted due to link or username in your name."
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}")],
                        [InlineKeyboardButton(f"🔓 Unmute – {BOT_USERNAME}", url=f"https://t.me/{BOT_USERNAME.lstrip('@')}")]
                    ])
                )
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
    is_user = "-user" in args
    should_pin = "-pin" in args

    users = []
    groups = []

    if is_user and os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            users = [int(i.strip()) for i in f if i.strip().isdigit()]

    if os.path.exists(GROUPS_FILE):
        with open(GROUPS_FILE, "r") as f:
            groups = [int(i.strip()) for i in f if i.strip().isdigit()]

    content = update.message.reply_to_message if update.message.reply_to_message else update.message

    success_groups = 0
    success_users = 0
    failed_groups = 0
    failed_users = 0

    async def send_content(chat_id, is_group=False):
        nonlocal success_groups, success_users, failed_groups, failed_users

        try:
            if content.text and not content.caption and not content.photo:
                msg = await context.bot.send_message(chat_id=chat_id, text=content.text)
            elif content.photo:
                msg = await context.bot.send_photo(chat_id=chat_id, photo=content.photo[-1].file_id, caption=content.caption or "")
            elif content.video:
                msg = await context.bot.send_video(chat_id=chat_id, video=content.video.file_id, caption=content.caption or "")
            elif content.voice:
                msg = await context.bot.send_voice(chat_id=chat_id, voice=content.voice.file_id, caption=content.caption or "")
            elif content.audio:
                msg = await context.bot.send_audio(chat_id=chat_id, audio=content.audio.file_id, caption=content.caption or "")
            elif content.document:
                msg = await context.bot.send_document(chat_id=chat_id, document=content.document.file_id, caption=content.caption or "")
            elif content.animation:
                msg = await context.bot.send_animation(chat_id=chat_id, animation=content.animation.file_id, caption=content.caption or "")
            elif content.sticker:
                msg = await context.bot.send_sticker(chat_id=chat_id, sticker=content.sticker.file_id)
            else:
                msg = await context.bot.send_message(chat_id=chat_id, text="📝 Empty or unsupported message.")
            
            if should_pin and is_group:
                await context.bot.pin_chat_message(chat_id, msg.message_id)

            if is_group:
                success_groups += 1
            else:
                success_users += 1

        except:
            if is_group:
                remove_id(GROUPS_FILE, chat_id)
                failed_groups += 1
            else:
                remove_id(USERS_FILE, chat_id)
                failed_users += 1

    for gid in groups:
        await send_content(gid, is_group=True)

    if is_user:
        for uid in users:
            await send_content(uid, is_group=False)

    await update.message.reply_text(
        f"✅ *Broadcast Report:*\n\n"
        f"👥 Groups Sent: {success_groups}\n"
        f"❌ Groups Failed: {failed_groups}\n"
        f"👤 Users Sent: {success_users}\n"
        f"❌ Users Failed: {failed_users}",
        parse_mode="Markdown"
    )
                
               

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

    # Check name of newly joined members
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, check_new_member_name))

    # Check regular messages (excluding joins)
    non_join_filter = filters.ALL & ~filters.StatusUpdate.NEW_CHAT_MEMBERS
    app.add_handler(MessageHandler(non_join_filter, check_user))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main() 
