import os
import re
import sys
import asyncio
from pyrogram import Client, filters
from pyrogram.types import *
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL")

app = Client("bio_mute_bot", bot_token=BOT_TOKEN)

WARNINGS = {}
MUTE_DURATION = 2  # default hours

def save_id(file, id):
    if not os.path.exists(file):
        open(file, "w").close()
    with open(file, "r") as f:
        ids = f.read().splitlines()
    if str(id) not in ids:
        with open(file, "a") as f:
            f.write(f"{id}\n")

def remove_id(file, id):
    if os.path.exists(file):
        with open(file, "r") as f:
            lines = f.readlines()
        with open(file, "w") as f:
            for line in lines:
                if line.strip() != str(id):
                    f.write(line)

def has_link_or_username(text):
    return bool(re.search(r"(https?://|t\.me/|@[\w\d_]+)", text, re.IGNORECASE))

async def mute_user(client, chat_id, user_id, duration):
    try:
        await client.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False))
        await asyncio.sleep(duration * 3600)
        await client.restrict_chat_member(chat_id, user_id, ChatPermissions())
    except:
        pass

@app.on_message(filters.private & filters.command("start"))
async def start(_, m):
    save_id("users.txt", m.from_user.id)
    try:
        member = await app.get_chat_member(UPDATE_CHANNEL, m.from_user.id)
        if member.status in ["member", "administrator", "creator"]:
            await m.reply_text(
                f"👋 Hello {m.from_user.mention}, welcome to Bio Mute Bot!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Add Me To Your Group", url=f"https://t.me/{app.me.username}?startgroup=true")],
                    [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL}")],
                    [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
                ])
            )
        else:
            raise Exception
    except:
        await m.reply_text(
            "🔒 Please join our update channel to use this bot.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{UPDATE_CHANNEL}")]
            ])
        )

@app.on_callback_query(filters.regex("help"))
async def help_cb(_, q):
    await q.message.edit_text(
        "**📚 Bot Commands:**\n\n"
        "`/setmute <hours>` - Set mute duration (owner only)\n"
        "`/status` - Show user/group count (owner only)\n"
        "`/broadcast -user` - Broadcast to users and groups\n"
        "`/broadcast -user -pin` - Broadcast + pin in groups\n"
        "`/restart` - Restart bot (owner only)\n\n"
        "🔗 Auto mute if:\n"
        "- Name contains link → permanent mute (DM only)\n"
        "- Bio or message contains link → 3 warnings → mute (DM + group)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="start_back")]
        ])
    )

@app.on_callback_query(filters.regex("start_back"))
async def back_cb(_, q):
    await q.message.edit_text(
        f"👋 Hello {q.from_user.mention}, welcome to Bio Mute Bot!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Me To Your Group", url=f"https://t.me/{app.me.username}?startgroup=true")],
            [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL}")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
        ])
    )

@app.on_message(filters.new_chat_members)
async def new_member_check(_, m):
    for user in m.new_chat_members:
        save_id("groups.txt", m.chat.id)
        name = user.first_name or ""
        if has_link_or_username(name):
            await m.chat.restrict_member(user.id, ChatPermissions())
            try:
                await app.send_message(
                    user.id,
                    f"⚔️ Bio mute ⚔️\n\n👤 {name} (`{user.id}`)\n⛔ You have been *permanently muted* due to link in your name.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL}")],
                        [InlineKeyboardButton("🔓 Unmute", url=f"https://t.me/{app.me.username}")]
                    ])
                )
            except:
                pass

@app.on_message(filters.group & filters.text)
async def group_msg_check(_, m):
    user = m.from_user
    if not user or user.is_bot:
        return

    uid = user.id
    text = m.text or ""
    first = user.first_name or ""

    if has_link_or_username(first):
        await m.chat.restrict_member(uid, ChatPermissions())
        try:
            await app.send_message(
                uid,
                f"⚔️ Bio mute ⚔️\n\n👤 {first} (`{uid}`)\n⛔ You have been *permanently muted* due to link in your name.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL}")],
                    [InlineKeyboardButton("🔓 Unmute", url=f"https://t.me/{app.me.username}")]
                ])
            )
        except:
            pass
        return

    try:
        bio = (await app.get_chat_member(m.chat.id, uid)).user.bio or ""
    except:
        bio = ""

    if has_link_or_username(bio) or has_link_or_username(text):
        await m.delete()
        WARNINGS.setdefault(uid, 0)
        WARNINGS[uid] += 1

        if WARNINGS[uid] >= 4:
            await m.chat.restrict_member(uid, ChatPermissions())
            await mute_user(app, m.chat.id, uid, MUTE_DURATION)
            msg = f"⚔️ Bio mute ⚔️\n\n👤 {first} (`{uid}`)\n⛔ Muted for {MUTE_DURATION} hours."
            btns = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Update Channel", url=f"https://t.me/{UPDATE_CHANNEL}")],
                [InlineKeyboardButton("🔓 Unmute", url=f"https://t.me/{app.me.username}")]
            ])
            try:
                await m.reply(msg, reply_markup=btns)
                await app.send_message(uid, msg, reply_markup=btns)
            except:
                pass
        else:
            try:
                warn = WARNINGS[uid]
                await m.reply(f"⚠️ {user.mention}, link detected! Warning {warn}/3")
                await app.send_message(uid, f"⚠️ You have received warning {warn}/3 for link usage.")
            except:
                pass

@app.on_message(filters.command("setmute") & filters.user(OWNER_ID))
async def set_mute(_, m):
    global MUTE_DURATION
    parts = m.text.split()
    if len(parts) == 2 and parts[1].isdigit():
        MUTE_DURATION = int(parts[1])
        await m.reply(f"✅ Mute duration set to {MUTE_DURATION} hours.")
    else:
        await m.reply("Usage: /setmute <hours>")

@app.on_message(filters.command("status") & filters.user(OWNER_ID))
async def status(_, m):
    u = len(open("users.txt").readlines()) if os.path.exists("users.txt") else 0
    g = len(open("groups.txt").readlines()) if os.path.exists("groups.txt") else 0
    await m.reply(f"📊 Status:\n👤 Users: {u}\n👥 Groups: {g}")

@app.on_message(filters.command("restart") & filters.user(OWNER_ID))
async def restart(_, m):
    await m.reply("♻️ Restarting...")
    os.execl(sys.executable, sys.executable, *sys.argv)

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(_, m):
    args = m.text.split()
    to_users = "-user" in args
    pin_msg = "-pin" in args
    content = m.reply_to_message if m.reply_to_message else None

    sent = 0
    failed = 0
    ids = []

    if os.path.exists("groups.txt"):
        ids += [(int(i.strip()), 'group') for i in open("groups.txt")]
    if to_users and os.path.exists("users.txt"):
        ids += [(int(i.strip()), 'user') for i in open("users.txt")]

    for id, typ in ids:
        try:
            if content:
                msg = await content.copy(id)
            else:
                msg = await app.send_message(id, "📢 " + m.text.split(None, 1)[-1])
            if pin_msg and typ == 'group':
                await app.pin_chat_message(id, msg.id)
            sent += 1
        except:
            remove_id("groups.txt" if typ == 'group' else "users.txt", id)
            failed += 1

    await m.reply(f"✅ Broadcast Done.\nSent: {sent}\nFailed: {failed}")

app.run()
