import os
import re
import json
import base64
import sqlite3
import tempfile
import logging
from datetime import datetime
from typing import Optional

import httpx
import yt_dlp

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==============================================================================
# CONFIGURATION & BRANDING
# ==============================================================================
BOT_TOKEN = (os.getenv("9265141111:AAFv9t1EdaHekqiH0V2j6n42MTJKeo_lXGU") or "").strip()
ADMIN_IDS = {8419760844}
FORCE_JOIN_CHANNEL = "https://t.me/SUPPOR8TNIROB"
FORCE_JOIN_USERNAME = "SUPPOR8TNIROB"
OWNER_TAG = "👑 𝗡𝗜𝗥𝗢𝗕 𝗕𝗢𝗦𝗦 𝗚𝗫™ 𝗢𝗪𝗡𝗘𝗥: @NIROB_GX_LEADER"
BOT_HANDLE = "🤖 Telegram Bot: @nirob_gxteam_Obucsate_bot"
OBFUSCATOR_REF = "https://www.infyways.com/tools/html-obfuscator/"
DB_PATH = os.path.join(tempfile.gettempdir(), "bot_data.db")

DEFAULT_BUTTONS = {
    "html_enc": "HTML Encrypt",
    "link_to_html": "Link to HTML",
    "link_to_video": "Link to Video",
    "pic_to_link": "Pic to Link",
    "developer": "Developer",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ==============================================================================
# DATABASE LAYER (SQLITE)
# ==============================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_banned INTEGER DEFAULT 0,
                joined_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_premium_buttons (
                user_id INTEGER,
                button_key TEXT,
                badge_emoji TEXT,
                PRIMARY KEY (user_id, button_key)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def register_user(user_id: int, username: Optional[str], first_name: Optional[str]):
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, is_banned, joined_at)
            VALUES (?, ?, ?, 0, ?)
        """, (user_id, username or "", first_name or "", datetime.utcnow().isoformat()))
        cur.execute("""
            UPDATE users SET username = ?, first_name = ? WHERE user_id = ?
        """, (username or "", first_name or "", user_id))
        conn.commit()
    finally:
        conn.close()


def is_user_banned(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return False
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return bool(row and row[0] == 1)
    finally:
        conn.close()


def set_user_ban_status(user_id: int, banned: bool):
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, is_banned, joined_at)
            VALUES (?, '', '', ?, ?)
        """, (user_id, 1 if banned else 0, datetime.utcnow().isoformat()))
        cur.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (1 if banned else 0, user_id))
        conn.commit()
    finally:
        conn.close()


def get_all_users(limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, first_name, is_banned FROM users ORDER BY rowid DESC LIMIT ?", (limit,))
        return cur.fetchall()
    finally:
        conn.close()


def get_user_premium_map(user_id: int) -> dict[str, str]:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT button_key, badge_emoji FROM user_premium_buttons WHERE user_id = ?", (user_id,))
        rows = cur.fetchall()
        return {k: v for k, v in rows}
    finally:
        conn.close()


def toggle_user_button_premium(user_id: int, button_key: str, emoji: str) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT badge_emoji FROM user_premium_buttons WHERE user_id = ? AND button_key = ?",
            (user_id, button_key),
        )
        row = cur.fetchone()
        if row and row[0] == emoji:
            cur.execute(
                "DELETE FROM user_premium_buttons WHERE user_id = ? AND button_key = ?",
                (user_id, button_key),
            )
            result = None
        else:
            cur.execute("""
                INSERT OR REPLACE INTO user_premium_buttons (user_id, button_key, badge_emoji)
                VALUES (?, ?, ?)
            """, (user_id, button_key, emoji))
            result = emoji
        conn.commit()
        return result
    finally:
        conn.close()


# ==============================================================================
# MULTI-LAYER HTML SECURITY & OBFUSCATION ENGINE
# ==============================================================================
def extract_title(raw_html: str) -> str:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.IGNORECASE | re.DOTALL)
    return title_match.group(1) if title_match else "Protected Page"


def multi_layer_html_encrypt(raw_html: str) -> str:
    title_text = extract_title(raw_html)
    raw_bytes = raw_html.encode("utf-8")

    xor_key = [0x5A, 0xA5, 0x3C, 0xC3, 0x7E]
    xored = bytes(b ^ xor_key[i % len(xor_key)] for i, b in enumerate(raw_bytes))

    b64_str = base64.b64encode(xored).decode("ascii")[::-1]
    hex_payload = b64_str.encode("utf-8").hex()

    chunk_size = 24
    chunks = [hex_payload[i:i + chunk_size] for i in range(0, len(hex_payload), chunk_size)]
    chunks_json = json.dumps(chunks)
    key_json = json.dumps(xor_key)

    source_warning = (
        "<!--\n"
        "  ====================================================================\n"
        f"  {OWNER_TAG}\n"
        f"  {BOT_HANDLE}\n"
        "  SOURCE PROTECTION ACTIVE // DO NOT COPY OR INSPECT SOURCE\n"
        "  ====================================================================\n"
        "-->"
    )

    return f"""{source_warning}
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_text}</title>
<style>
  html, body {{ margin: 0; padding: 0; background: #050507; color: #fff; }}
</style>
</head>
<body>
<script>
(function(){{
  document.addEventListener("contextmenu", e => e.preventDefault());
  document.addEventListener("keydown", e => {{
    if (
      e.key === "F12" ||
      (e.ctrlKey && e.shiftKey && ["I","J","C","K"].includes(e.key.toUpperCase())) ||
      (e.ctrlKey && ["U","S"].includes(e.key.toUpperCase()))
    ) {{
      e.preventDefault();
      return false;
    }}
  }});

  const _parts = {chunks_json};
  const _k = {key_json};

  function _decodeHex(hexStr) {{
    let out = "";
    for (let i = 0; i < hexStr.length; i += 2) {{
      out += String.fromCharCode(parseInt(hexStr.substr(i, 2), 16));
    }}
    return out;
  }}

  try {{
    const joinedHex = _parts.join("");
    const revB64 = _decodeHex(joinedHex);
    const normalB64 = revB64.split("").reverse().join("");
    const binStr = atob(normalB64);
    const bytes = new Uint8Array(binStr.length);
    for (let i = 0; i < binStr.length; i++) {{
      bytes[i] = binStr.charCodeAt(i) ^ _k[i % _k.length];
    }}
    const htmlOut = new TextDecoder("utf-8").decode(bytes);
    document.open();
    document.write(htmlOut);
    document.close();
  }} catch (err) {{
    document.body.innerHTML = "<h3 style='font-family:sans-serif;padding:20px;'>Protected Content Error</h3>";
  }}
}})();
</script>
</body>
</html>
"""


# ==============================================================================
# FORCE JOIN & KEYBOARDS
# ==============================================================================
async def is_joined_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False
    if user.id in ADMIN_IDS:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{FORCE_JOIN_USERNAME}", user_id=user.id)
        return member.status in {
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }
    except Exception:
        return False


def force_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Required Group / Channel", url=FORCE_JOIN_CHANNEL)],
        [InlineKeyboardButton("✅ Joined — Verify Again", callback_data="check_join")],
    ])


def build_user_menu(user_id: int) -> InlineKeyboardMarkup:
    prem_map = get_user_premium_map(user_id)

    def label(key: str) -> str:
        base = DEFAULT_BUTTONS[key]
        return f"{prem_map[key]} {base} [PRO]" if key in prem_map else base

    rows = [
        [
            InlineKeyboardButton(label("html_enc"), callback_data="mode_html_enc"),
            InlineKeyboardButton(label("link_to_html"), callback_data="mode_link_to_html"),
        ],
        [
            InlineKeyboardButton(label("link_to_video"), callback_data="mode_link_to_video"),
            InlineKeyboardButton(label("pic_to_link"), callback_data="mode_pic_to_link"),
        ],
        [
            InlineKeyboardButton(label("developer"), callback_data="mode_developer"),
        ],
    ]
    if user_id in ADMIN_IDS:
        rows.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(rows)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 Unban User", callback_data="adm_unban")],
        [InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban")],
        [InlineKeyboardButton("💎 Set/Toggle Premium Button", callback_data="adm_prem_select_btn")],
        [InlineKeyboardButton("🗄 Real Database Stats", callback_data="adm_db_stats")],
        [InlineKeyboardButton("⬅️ Back to User Menu", callback_data="back_user_menu")],
    ])


def admin_button_picker_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("HTML Encrypt", callback_data="adm_pick_btn_html_enc")],
        [InlineKeyboardButton("Link to HTML", callback_data="adm_pick_btn_link_to_html")],
        [InlineKeyboardButton("Link to Video", callback_data="adm_pick_btn_link_to_video")],
        [InlineKeyboardButton("Pic to Link", callback_data="adm_pick_btn_pic_to_link")],
        [InlineKeyboardButton("Developer", callback_data="adm_pick_btn_developer")],
        [InlineKeyboardButton("⬅️ Cancel", callback_data="admin_panel")],
    ])


# ==============================================================================
# HANDLERS
# ==============================================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    register_user(user.id, user.username, user.first_name)

    if is_user_banned(user.id):
        await update.message.reply_text("🚫 আপনি বট থেকে ব্যান হয়ে আছেন।")
        return

    if not await is_joined_group(update, context):
        await update.message.reply_text(
            f"⚠️ বট ব্যবহার করার আগে অবশ্যই নিচের গ্রুপ/চ্যানেলে জয়েন করতে হবে:\n{FORCE_JOIN_CHANNEL}\n\n"
            "জয়েন করার পর নিচের **Joined — Verify Again** বাটনে চাপ দিন।",
            reply_markup=force_join_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    context.user_data["mode"] = None
    await update.message.reply_text(
        f"{OWNER_TAG}\n{BOT_HANDLE}\n\nএকটি অপশন সিলেক্ট করুন:",
        reply_markup=build_user_menu(user.id),
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    user = query.from_user
    await query.answer()

    if is_user_banned(user.id):
        await query.edit_message_text("🚫 আপনি ব্যান হয়ে আছেন।")
        return

    data = query.data or ""

    if data == "check_join":
        if await is_joined_group(update, context):
            await query.edit_message_text(
                f"✅ জয়েন ভেরিফাইড!\n\n{OWNER_TAG}\n{BOT_HANDLE}\n\nএকটি অপশন সিলেক্ট করুন:",
                reply_markup=build_user_menu(user.id),
            )
        else:
            await query.edit_message_text(
                f"❌ এখনো জয়েন পাওয়া যায়নি। আগে জয়েন করুন:\n{FORCE_JOIN_CHANNEL}",
                reply_markup=force_join_keyboard(),
            )
        return

    if not await is_joined_group(update, context):
        await query.edit_message_text(
            f"⚠️ আগে গ্রুপ/চ্যানেলে জয়েন করুন:\n{FORCE_JOIN_CHANNEL}",
            reply_markup=force_join_keyboard(),
        )
        return

    if data == "back_user_menu":
        context.user_data["mode"] = None
        await query.edit_message_text(
            f"{OWNER_TAG}\n{BOT_HANDLE}\n\nএকটি অপশন সিলেক্ট করুন:",
            reply_markup=build_user_menu(user.id),
        )
        return

    if data == "mode_html_enc":
        context.user_data["mode"] = "html_enc"
        await query.edit_message_text(
            "🔐 **HTML Encrypt মোড চালু হয়েছে**\n\n"
            "আপনার `.html` ফাইল পাঠান অথবা HTML কোড মেসেজে পেস্ট করুন।",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "mode_link_to_html":
        context.user_data["mode"] = "link_to_html"
        await query.edit_message_text(
            "🌐 **Link to HTML মোড চালু হয়েছে**\n\n"
            "একটি ওয়েবসাইট লিংক পাঠান। লিংক থেকে মূল HTML কোড ফাইল আকারে দেওয়া হবে।",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "mode_link_to_video":
        context.user_data["mode"] = "link_to_video"
        await query.edit_message_text(
            "🎬 **Link to Video মোড চালু হয়েছে**\n\n"
            "ভিডিও লিংক পাঠান। সাপোর্টেড প্ল্যাটফর্ম থেকে ভিডিও ডাউনলোড করে পাঠানো হবে।",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "mode_pic_to_link":
        context.user_data["mode"] = "pic_to_link"
        await query.edit_message_text(
            "🖼 **Pic to Link মোড চালু হয়েছে**\n\n"
            "একটি ছবি (Photo) পাঠান, সেটির লিংক তৈরি করে দেওয়া হবে।",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "mode_developer":
        await query.edit_message_text(
            f"👨‍💻 **Developer Info**\n\n{OWNER_TAG}\n{BOT_HANDLE}\n"
            f"📢 Support: {FORCE_JOIN_CHANNEL}\n"
            f"🔧 Ref: {OBFUSCATOR_REF}",
            reply_markup=build_user_menu(user.id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if user.id not in ADMIN_IDS:
        await query.edit_message_text("⛔ শুধুমাত্র অ্যাডমিন এই অপশন ব্যবহার করতে পারেন।")
        return

    if data == "admin_panel":
        context.user_data["mode"] = None
        await query.edit_message_text(
            "⚙️ **Admin Control Panel**",
            reply_markup=admin_panel_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "adm_unban":
        context.user_data["mode"] = "adm_unban_wait_id"
        await query.edit_message_text("🔓 আনব্যান করার জন্য **User ID** পাঠান।", parse_mode=ParseMode.MARKDOWN)
        return

    if data == "adm_ban":
        context.user_data["mode"] = "adm_ban_wait_id"
        await query.edit_message_text("🚫 ব্যান করার জন্য **User ID** পাঠান।", parse_mode=ParseMode.MARKDOWN)
        return

    if data == "adm_prem_select_btn":
        await query.edit_message_text(
            "💎 কোন বাটনটি প্রিমিয়াম করতে/ইমোজি বদলাতে চান তা সিলেক্ট করুন:",
            reply_markup=admin_button_picker_keyboard(),
        )
        return

    if data.startswith("adm_pick_btn_"):
        btn_key = data.replace("adm_pick_btn_", "")
        context.user_data["mode"] = "adm_prem_wait_user_emoji"
        context.user_data["target_btn_key"] = btn_key
        await query.edit_message_text(
            f"💎 সিলেক্টেড বাটন: **{DEFAULT_BUTTONS.get(btn_key, btn_key)}**\n\n"
            "এখন `User_ID Emoji` পাঠান (যেমন: `123456789 👑`)",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "adm_db_stats":
        users = get_all_users(limit=20)
        lines = [f"🗄 **Real Database Users (Latest {len(users)}):**\n"]
        for uid, uname, fname, banned in users:
            st = "BANNED" if banned else "ACTIVE"
            lines.append(f"• `{uid}` | @{uname or 'none'} | {fname or ''} | **{st}**")
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=admin_panel_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message or not update.message.text:
        return
    register_user(user.id, user.username, user.first_name)

    if is_user_banned(user.id):
        await update.message.reply_text("🚫 আপনি ব্যান হয়ে আছেন।")
        return

    if not await is_joined_group(update, context):
        await update.message.reply_text(
            f"⚠️ আগে জয়েন করুন:\n{FORCE_JOIN_CHANNEL}",
            reply_markup=force_join_keyboard(),
        )
        return

    text = update.message.text.strip()
    mode = context.user_data.get("mode")

    if mode == "adm_unban_wait_id" and user.id in ADMIN_IDS:
        try:
            target_id = int(text)
            set_user_ban_status(target_id, False)
            context.user_data["mode"] = None
            await update.message.reply_text(f"✅ User `{target_id}` আনব্যান করা হয়েছে।", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ সঠিক User ID পাঠান।")
        return

    if mode == "adm_ban_wait_id" and user.id in ADMIN_IDS:
        try:
            target_id = int(text)
            set_user_ban_status(target_id, True)
            context.user_data["mode"] = None
            await update.message.reply_text(f"🚫 User `{target_id}` ব্যান করা হয়েছে।", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ সঠিক User ID পাঠান।")
        return

    if mode == "adm_prem_wait_user_emoji" and user.id in ADMIN_IDS:
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ ফরম্যাট: `123456789 👑`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            target_uid = int(parts[0])
        except ValueError:
            await update.message.reply_text("❌ প্রথম অংশে সঠিক User ID দিন।")
            return
        emoji = parts[1].strip()
        btn_key = context.user_data.get("target_btn_key", "html_enc")
        active_emoji = toggle_user_button_premium(target_uid, btn_key, emoji)
        context.user_data["mode"] = None
        if active_emoji:
            await update.message.reply_text(
                f"✅ User `{target_uid}`-এর **{DEFAULT_BUTTONS.get(btn_key)}** বাটনে {active_emoji} প্রিমিয়াম যুক্ত হয়েছে।",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await update.message.reply_text(
                f"🔄 User `{target_uid}`-এর **{DEFAULT_BUTTONS.get(btn_key)}** বাটনের প্রিমিয়াম ইমোজি রিমুভ করা হয়েছে।",
                parse_mode=ParseMode.MARKDOWN,
            )
        return

    if mode == "html_enc":
        protected = multi_layer_html_encrypt(text)
        out_path = os.path.join(tempfile.gettempdir(), f"protected_{user.id}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(protected)
        with open(out_path, "rb") as doc_file:
            await update.message.reply_document(
                document=doc_file,
                filename="protected_index.html",
                caption=f"🔐 হাই-সিকিউরিটি HTML এনক্রিপ্ট সম্পন্ন!\n{OWNER_TAG}",
            )
        return

    if mode == "link_to_html":
        if not text.startswith(("http://", "https://")):
            await update.message.reply_text("❌ সঠিক `http://` বা `https://` লিংক পাঠান।", parse_mode=ParseMode.MARKDOWN)
            return
        await update.message.reply_text("⏳ লিংক থেকে মূল HTML সংগ্রহ করা হচ্ছে...")
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(text)
                resp.raise_for_status()
                raw_html = resp.text
            out_path = os.path.join(tempfile.gettempdir(), f"fetched_{user.id}.html")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(raw_html)
            with open(out_path, "rb") as doc_file:
                await update.message.reply_document(
                    document=doc_file,
                    filename="source_page.html",
                    caption="✅ লিংকের মূল HTML কোড (কোনো পরিবর্তন ছাড়া)।",
                )
        except Exception as e:
            await update.message.reply_text(f"❌ HTML আনা যায়নি: {e}")
        return

    if mode == "link_to_video":
        if not text.startswith(("http://", "https://")):
            await update.message.reply_text("❌ সঠিক ভিডিও লিংক পাঠান।")
            return
        await update.message.reply_text("⏳ ভিডিও ডাউনলোড হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...")
        out_tmpl = os.path.join(tempfile.gettempdir(), f"vid_{user.id}_%(id)s.%(ext)s")
        ydl_opts = {
            "outtmpl": out_tmpl,
            "format": "best[ext=mp4]/best",
            "noplaylist": True,
            "quiet": True,
        }
        downloaded_file = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(text, download=True)
                downloaded_file = ydl.prepare_filename(info)

            if downloaded_file and os.path.exists(downloaded_file):
                with open(downloaded_file, "rb") as vid_file:
                    await update.message.reply_video(
                        video=vid_file,
                        caption=f"🎬 ভিডিও ডাউনলোড সম্পন্ন!\n{OWNER_TAG}",
                    )
            else:
                await update.message.reply_text("❌ ভিডিও ফাইল পাওয়া যায়নি।")
        except Exception as e:
            await update.message.reply_text(f"❌ ভিডিও ডাউনলোড ব্যর্থ: {e}")
        finally:
            if downloaded_file and os.path.exists(downloaded_file):
                try:
                    os.remove(downloaded_file)
                except OSError:
                    pass
        return

    await update.message.reply_text(
        "একটি বাটন সিলেক্ট করুন অথবা /start দিন।",
        reply_markup=build_user_menu(user.id),
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message or not update.message.document:
        return
    if is_user_banned(user.id) or not await is_joined_group(update, context):
        return

    if context.user_data.get("mode") != "html_enc":
        await update.message.reply_text("ℹ️ HTML ফাইল এনক্রিপ্ট করতে আগে **HTML Encrypt** বাটনে চাপ দিন।", parse_mode=ParseMode.MARKDOWN)
        return

    doc = update.message.document
    tg_file = await doc.get_file()
    raw_bytes = await tg_file.download_as_bytearray()
    raw_html = raw_bytes.decode("utf-8", errors="ignore")

    protected = multi_layer_html_encrypt(raw_html)
    safe_name = os.path.basename(doc.file_name or "index.html")
    out_path = os.path.join(tempfile.gettempdir(), f"enc_{user.id}_{safe_name}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(protected)

    with open(out_path, "rb") as out_doc:
        await update.message.reply_document(
            document=out_doc,
            filename=f"protected_{safe_name}",
            caption=f"🔐 ফাইল হাই-সিকিউরিটিতে এনক্রিপ্ট হয়েছে!\n{OWNER_TAG}",
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message or not update.message.photo:
        return
    if is_user_banned(user.id) or not await is_joined_group(update, context):
        return

    if context.user_data.get("mode") != "pic_to_link":
        await update.message.reply_text("ℹ️ ছবি থেকে লিংক বানাতে আগে **Pic to Link** বাটনে চাপ দিন।", parse_mode=ParseMode.MARKDOWN)
        return

    photo = update.message.photo[-1]
    tg_file = await photo.get_file()
    file_url = tg_file.file_path
    await update.message.reply_text(
        f"🖼 **Pic to Link প্রস্তুত:**\n`{file_url}`",
        parse_mode=ParseMode.MARKDOWN,
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing! Set BOT_TOKEN in Render Environment.")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Bot polling started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
