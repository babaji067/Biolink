from telegram import Update, ChatPermissions
from telegram.ext import Updater, CommandHandler, CallbackContext, ChatMemberHandler
import re
import time

# Replace with your bot token
TOKEN = 'YOUR_BOT_TOKEN_HERE'

# Dictionary to track warnings
warnings = {}

# Regex to detect links
link_pattern = re.compile(r'(https?://|www\.)')

# Function to check bios when user joins or updates profile
def check_bio(update: Update, context: CallbackContext):
    member = update.chat_member.new_chat_member.user
    chat_id = update.chat_member.chat.id
    user_id = member.id

    if member.bio and re.search(link_pattern, member.bio):
        key = f"{chat_id}_{user_id}"
        warnings[key] = warnings.get(key, 0) + 1
        
        if warnings[key] < 4:
            context.bot.send_message(chat_id=chat_id,
                text=f"⚠️ @{member.username or member.first_name}, please remove the link from your bio. Warning {warnings[key]}/3.")
        else:
            # Mute the user for 2 hours
            until = int(time.time()) + 2 * 60 * 60
            context.bot.restrict_chat_member(chat_id, user_id,
                ChatPermissions(can_send_messages=False), until_date=until)
            
            context.bot.send_message(chat_id=chat_id,
                text=f"🔇 @{member.username or member.first_name} has been muted for 2 hours due to repeated bio link violations.")
            warnings[key] = 0  # Reset warnings after mute

# Start command
def start(update: Update, context: CallbackContext):
    update.message.reply_text("✅ Bio Monitor Bot is active.")

# Main function
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(ChatMemberHandler(check_bio, ChatMemberHandler.CHAT_MEMBER))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
