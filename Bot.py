from telegram import Update, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
import os
import re
import time
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Warning tracker
warnings = {}

# Link detector
link_pattern = re.compile(r"(https?://|www\.)")

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bio-Link Monitor Bot is active.")

# Main handler
async def monitor_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    user_id = user.id
    key = f"{chat_id}_{user_id}"
    try:
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    bio = chat_member.user.bio  # <-- this line fixed
        if bio and re.search(link_pattern, bio):
            # Delete the message
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)

            # Track warning count
            warnings[key] = warnings.get(key, 0) + 1

            if warnings[key] < 4:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ @{user.username or user.first_name}, please remove the link from your bio! Warning {warnings[key]}/3."
                )
            else:
                # Mute user for 2 hours
                until = int(time.time()) + 2 * 60 * 60
                await context.bot.restrict_chat_member(
                    chat_id,
                    user_id,
                    ChatPermissions(can_send_messages=False),
                    until_date=until
                )

                # Custom inline button
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💬 Appeal Unmute", url="https://t.me/YourSupportBot")]
                ])

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔇 @{user.username or user.first_name} has been muted for 2 hours due to repeated bio link violations.",
                    reply_markup=keyboard
                )

                warnings[key] = 0  # Reset after mute

    except Exception as e:
        print(f"[Error] Could not check bio for user {user_id}: {e}")

# Main function
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, monitor_bio))

    print("🤖 Bot is running...")
    await app.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
