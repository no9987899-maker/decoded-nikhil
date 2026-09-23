import os
import asyncio
import sqlite3
import random
import logging
import time
import aiohttp
from aiohttp import web
import urllib.parse
import json
import re
import socket
import hashlib
import hmac
import secrets
import string
import sys
import ast
from html import escape
from urllib.parse import urlparse

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:
    Fernet = None
    InvalidToken = Exception
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message, Dice, BufferedInputFile
)

# ==============================================================================
# 1. BOT CONFIGURATION & CONSTANTS
# ==============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME = "@PANEL_SHOP_DECODED_BOT"
SHOP_NAME = os.getenv("SHOP_NAME", "PREMIUM PANEL SHOP")
ADMIN_ID = 6452869652
SECOND_ADMIN_ID = 0
ADMIN_CONTACT = "@Dery8990"

VIP_DISCOUNT_PERCENTAGE = 15.0
VIP_PRICE_INR = 299.0

WELCOME_STICKER_ID = "CAACAgIAAxkBAAEU-WZmH_..."  # Replace with your sticker ID
SPIN_DELAY_SECONDS = 2.5

FIXED_CATEGORIES = [
    "ANDROID NON ROOT PANEL",
    "ANDROID ROOT PANEL",
    "IPHONE PANEL",
    "PC PANEL",
    "GUILD CALORY CREDIT",
    "CARROM PANEL"
]

# ==============================================================================
# YOUR PREMIUM EMOJIS – all required emoji IDs
# ==============================================================================
DEFAULT_EMOJIS = {
    'product_store': '6163205892834598715',
    'profile': '6035084557378654059',
    'add_balance': '5278467510604160626',
    'history': '6160968017304888311',
    'referral': '6032609071373226027',
    'support': '6161112036148255813',
    'ludo_spin': '6147764669361692707',
    'back': '6039539366177541657',
    'upi': '5807750375033278838',
    'reseller': '6120436698695338614',
    'tutorial': '5368653135101310687',
    'download': '6161336001512874965',
    'telegram': '6161096071754818473',
    'whatsapp': '6118193823823698862',
    'welcome': '5312361253610475399',
    'vip': '6086672466132865380',
    'category_android_non_root': '6161172706856282588',
    'category_android_root': '6161449831031118974',
    'category_iphone': '6161399700172840408',
    'category_pc': '5350554349074391003',
    'grid_id': '5474625972751837256',
    'name': '5215399540814781035',
    'account_level': '6129584162992034014',
    'regular_user': '5904630315946611415',
    'wallet': '6210859306602995217',
    'current_balance': '5316711376876485361',
    'global_stats': '6161437856662298090',
    'total_orders': '6160968017304888311',
    'total_spent': '5197503331215361533',
    'total_referrals': '5938196735200333756',
    'joined_grid': '5433614043006903194',
    'info_icon': '6037421444789440735',
    'check_icon': '6161241250239356403',
    'checkbox_icon': '6161437856662298090',
    'shield_icon': '6086672466132865380',
    'money_icon': '5890848474563352982',
    'redeem_icon': '5377624166436445368',
    'wallet_left': '6210859306602995217',
    'wallet_right': '5305699699204837855',
    'point_down': '6161302621027049305',
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_activity.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Two-admin authorization and notifications
def is_admin(user_id: int) -> bool:
    return user_id in {ADMIN_ID, SECOND_ADMIN_ID}

async def notify_admins(text: str, **kwargs):
    """Send an admin notification to both configured admins."""
    for admin_id in (ADMIN_ID, SECOND_ADMIN_ID):
        try:
            await bot.send_message(admin_id, text, **kwargs)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

def fmt_curr(amount: float) -> str:
    return f"₹{amount:,.2f}"

def natural_sort_key(value: Any) -> List[Any]:
    """Sort names naturally: A, B, C... and 1, 2, 10 instead of 1, 10, 2."""
    text = str(value or "").strip()
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", text)]

# ==============================================================================
# 2. DATABASE FUNCTIONS
# ==============================================================================
def db_query(query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False, commit: bool = True) -> Any:
    conn = sqlite3.connect('yp_shop.db')
    c = conn.cursor()
    try:
        c.execute(query, params)
        if fetchone:
            res = c.fetchone()
        elif fetchall:
            res = c.fetchall()
        else:
            res = None
        if commit: conn.commit()
        return res
    except Exception as e:
        logger.error(f"DB Error: {e} | Query: {query} | Params: {params}")
        if commit: conn.rollback()
        return None
    finally:
        conn.close()

def get_setting(key: str, default: str = "") -> str:
    val = db_query("SELECT value FROM settings WHERE key=?", (key,), fetchone=True)
    return val[0] if val and val[0] else default

def set_setting(key: str, value: str) -> None:
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

def log_activity(user_id: int, action: str, details: str = "") -> None:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_query(
            "INSERT INTO activity_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, action, details, timestamp)
        )
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

def get_emoji(slot: str, default_id: str = None) -> str:
    stored = get_setting(f"emoji_{slot}", "")
    emoji_id = stored if stored and stored.isdigit() else (default_id or DEFAULT_EMOJIS.get(slot, ""))
    if emoji_id:
        return f'<tg-emoji emoji-id="{emoji_id}">✨</tg-emoji>'
    return "✨"

def get_emoji_icon(slot: str, default_id: str = None) -> str:
    stored = get_setting(f"emoji_{slot}", "")
    emoji_id = stored if stored and stored.isdigit() else (default_id or DEFAULT_EMOJIS.get(slot, ""))
    return emoji_id

# ==============================================================================
# 3. STRING RESOURCES – using placeholders for premium emojis
# ==============================================================================
UI_TEXTS = {
    "start_menu": (
        "🔥 <b>{shop_name}</b> 🔥\n\n"
        "🚀 <b>Welcome:</b> {first_name}\n"
        "✅ <b>Account ID:</b> <code>{account_id}</code>\n"
        "💰 <b>Wallet Balance:</b> {balance}\n"
        "❓ <b>Status / Rank:</b> 🟢 {account_type}\n"
        "📦 <b>Available Products:</b> {available_products} Online\n\n"
        "🛡 <b>Status: 100% Safe &amp; Instant Auto-Delivery</b>\n"
        "🛒 <i>Select a product below to view validity plans &amp; keys:</i>"
    ),
    "download_files": (
        "🗂 <b><u>DOWNLOAD PREMIUM APK & FILES 📊</u></b>\n\n"
        "🌐 All our highly secured, premium, and updated files\n"
        "are securely hosted on our private channel! ⚠️⛔️\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📱 <b>WHAT YOU GET:</b> 📌\n\n"
        "✔️ Latest APK Updates 🔔\n"
        "✔️ 100% Virus Free & Secure ‼️\n"
        "✔️ All Configs & Scripts 🌸\n"
        "✔️ Complete Installation Guides 🔺\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⌨️ Tap the button below to access the Download Channel! 📝"
    ),
    "lucky_dice_result": (
        "{ludo_spin} <b><u>LUCKY DICE RESULT 🔨 💯</u></b>\n\n"
        "🎲 <b>Dice Value:</b> {dice_value}\n\n"
        "💸 <b>You Won:</b> {won_amount}\n"
        "💰 <b>Total Balance:</b> {new_balance}\n\n"
        "Congratulations! Come back after 24 hours."
    ),
    "vip_menu": (
        "🌟 <b><u>VIP MEMBERSHIP CLUB</u></b> 🌟\n\n"
        "Unlock premium benefits and permanent discounts!\n\n"
        "💎 <b>VIP Benefits:</b>\n"
        "• Flat 15% off on ALL products (Stacks with Reseller!)\n"
        "• Priority Support\n"
        "• Exclusive VIP-only giveaways\n\n"
        "💳 <b>VIP Price:</b> ₹299.00 (Lifetime)\n"
        "👤 <b>Your Status:</b> {vip_status}"
    ),
    "add_balance_menu": (
        "{add_balance} <b>ADD BALANCE</b> {info_icon}\n\n"
        "{info_icon} Select your preferred payment method. {check_icon}\n\n"
        "┣ {upi} FamPay / UPI — Fast Indian payments {checkbox_icon}\n"
        "{shield_icon} Payments are verified securely. {check_icon}"
    )
}

def get_ui_text(key: str, **kwargs) -> str:
    val = db_query("SELECT value FROM settings WHERE key=?", (f"ui_{key}",), fetchone=True)
    template = val[0] if val and val[0] else UI_TEXTS.get(key, "")

    emoji_map = {
        '{product_store}': get_emoji('product_store'),
        '{profile}': get_emoji('profile'),
        '{add_balance}': get_emoji('add_balance'),
        '{history}': get_emoji('history'),
        '{referral}': get_emoji('referral'),
        '{tutorial}': get_emoji('tutorial'),
        '{support}': get_emoji('support'),
        '{ludo_spin}': get_emoji('ludo_spin'),
        '{download}': get_emoji('download'),
        '{telegram}': get_emoji('telegram'),
        '{whatsapp}': get_emoji('whatsapp'),
        '{upi}': get_emoji('upi'),
        '{info_icon}': get_emoji('info_icon'),
        '{check_icon}': get_emoji('check_icon'),
        '{checkbox_icon}': get_emoji('checkbox_icon'),
        '{shield_icon}': get_emoji('shield_icon'),
        '{money_icon}': get_emoji('money_icon'),
        '{redeem_icon}': get_emoji('redeem_icon'),
        '{wallet_left}': get_emoji('wallet_left'),
        '{wallet_right}': get_emoji('wallet_right'),
        '{point_down}': get_emoji('point_down'),
    }
    for placeholder, emoji_tag in emoji_map.items():
        template = template.replace(placeholder, emoji_tag)

    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing formatting key for template {key}: {e}")
    return template

# ==============================================================================
# 4. DATABASE INITIALISATION & MIGRATION
# ==============================================================================
def init_db() -> None:
    conn = sqlite3.connect('yp_shop.db')
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            phone TEXT, 
            first_name TEXT, 
            username TEXT,
            balance REAL DEFAULT 0.0, 
            account_type TEXT DEFAULT 'Regular', 
            orders_count INTEGER DEFAULT 0, 
            spent REAL DEFAULT 0.0, 
            referrals_count INTEGER DEFAULT 0, 
            referral_earned REAL DEFAULT 0.0, 
            referred_by INTEGER, 
            last_spin TEXT, 
            joined_date TEXT,
            is_reseller INTEGER DEFAULT 0,
            reseller_since TEXT,
            total_saved REAL DEFAULT 0.0,
            is_banned INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            is_vip INTEGER DEFAULT 0,
            vip_since TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            category TEXT, 
            panel_name TEXT DEFAULT '',
            name TEXT, 
            price_inr REAL, 
            reseller_price REAL DEFAULT 0.0,
            stock INTEGER, 
            apk_link TEXT, 
            validity TEXT DEFAULT 'Lifetime', 
            device_limit TEXT DEFAULT '1 Device',
            is_active INTEGER DEFAULT 1,
            api_slot INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS product_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            product_id INTEGER, 
            key_text TEXT, 
            is_used INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            product_name TEXT, 
            price_paid REAL, 
            delivered_key TEXT, 
            purchase_date TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            message TEXT, 
            status TEXT DEFAULT 'Open',
            created_at TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, 
            value TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS youtube_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            video_file_id TEXT DEFAULT '',
            content_type TEXT DEFAULT 'url'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS youtube_course_access (
            user_id INTEGER PRIMARY KEY,
            amount_paid REAL NOT NULL DEFAULT 0.0,
            purchased_at TEXT NOT NULL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS coupons (
            code TEXT PRIMARY KEY, 
            amount REAL, 
            uses_left INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS redeemed (
            user_id INTEGER, 
            code TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            order_id TEXT PRIMARY KEY, 
            user_id INTEGER, 
            amount_inr REAL, 
            gateway_amount REAL DEFAULT 0.0,
            status TEXT, 
            timestamp INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS crypto_txns (
            txid TEXT PRIMARY KEY, 
            user_id INTEGER, 
            amount_usdt REAL, 
            timestamp INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS api_providers (
            slot INTEGER PRIMARY KEY,
            name TEXT DEFAULT '', url TEXT DEFAULT '', method TEXT DEFAULT 'POST',
            headers_json TEXT DEFAULT '{}', body_json TEXT DEFAULT '{}', content_type TEXT DEFAULT 'application/json',
            enabled INTEGER DEFAULT 1, priority INTEGER DEFAULT 100, source_code TEXT DEFAULT '', last_status TEXT DEFAULT ''
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS reseller_api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            key_prefix TEXT DEFAULT 'rsl_',
            key_last4 TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            regenerated_at INTEGER NOT NULL,
            enabled INTEGER DEFAULT 1,
            requests_count INTEGER DEFAULT 0,
            last_used_at INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS reseller_bot_api_access (
            user_id INTEGER PRIMARY KEY,
            purchased_at INTEGER NOT NULL,
            price_inr REAL NOT NULL DEFAULT 90.0,
            enabled INTEGER DEFAULT 1
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS reseller_bot_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bot_username TEXT DEFAULT '',
            bot_id INTEGER DEFAULT 0,
            token_encrypted TEXT NOT NULL,
            webhook_secret TEXT UNIQUE NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL,
            last_update_at INTEGER DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS bot_api_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, endpoint TEXT, method TEXT, status_code INTEGER,
            created_at INTEGER NOT NULL, ip TEXT DEFAULT ''
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, question TEXT NOT NULL,
            created_at INTEGER NOT NULL, status TEXT DEFAULT 'OPEN'
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS binance_pay_txns (
            merchant_trade_no TEXT PRIMARY KEY, user_id INTEGER NOT NULL, amount_inr REAL NOT NULL,
            amount_crypto REAL DEFAULT 0, currency TEXT DEFAULT 'USDT', status TEXT DEFAULT 'INITIAL',
            prepay_id TEXT DEFAULT '', transaction_id TEXT DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS spin_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            amount REAL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp TEXT
        )
    ''')

    migrations = [
        "ALTER TABLE users ADD COLUMN is_vip INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN vip_since TEXT",
        "ALTER TABLE products ADD COLUMN is_active INTEGER DEFAULT 1",
        "ALTER TABLE tickets ADD COLUMN created_at TEXT",
        "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN warnings INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN panel_name TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN external_enabled INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN external_product_id TEXT DEFAULT ''",
        "ALTER TABLE products ADD COLUMN requires_android_id INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN external_duration TEXT DEFAULT ''",
        "ALTER TABLE transactions ADD COLUMN gateway_amount REAL DEFAULT 0.0",
        "ALTER TABLE products ADD COLUMN api_slot INTEGER DEFAULT 0",
        "ALTER TABLE transactions ADD COLUMN purpose TEXT DEFAULT 'wallet'",
        "ALTER TABLE transactions ADD COLUMN product_id INTEGER",
        "ALTER TABLE youtube_lessons ADD COLUMN video_file_id TEXT DEFAULT ''",
        "ALTER TABLE youtube_lessons ADD COLUMN content_type TEXT DEFAULT 'url'",
    ]
    for mig in migrations:
        try: c.execute(mig)
        except sqlite3.OperationalError: pass

    # Backfill the API duration for existing products. The purchase code still
    # has additional fallbacks, so old databases remain compatible.
    try:
        c.execute("UPDATE products SET external_duration = validity WHERE COALESCE(external_duration, '') = ''")
    except sqlite3.OperationalError:
        pass
    
    c.execute("SELECT COUNT(*) FROM spin_rewards")
    if c.fetchone()[0] == 0:
        c.executemany("INSERT INTO spin_rewards (amount) VALUES (?)", [(0.0,), (1.0,), (2.0,), (5.0,), (10.0,)])

    default_settings = [
        ('spin_status', 'ON'),
        ('daily_spin_limit', '50.0'),
        ('reseller_system_status', 'ON'),
        ('bot_status', 'ON'),
        ('how_to_video', 'None'),
        ('youtube_course_price', '99.0'),
        ('youtube_course_contact', ''),
        ('all_files_link', 'None'),
        ('fampay_api_key', ''),
        ('fampay_base_url', 'https://fam.aryanispe.in'),
        ('fampay_gmail', ''),
        ('fampay_upi', ''),
        ('vip_status', 'OFF'),
        ('reseller_setup_fee', '200.0'),
        ('reseller_min_balance', '500.0'),
        ('migration_done', '0'),
        ('support_telegram', 'https://t.me/YOUR_SUPPORT'),
        ('support_whatsapp', 'https://wa.me/YOUR_NUMBER'),
        ('ui_start_menu', UI_TEXTS['start_menu']),
        ('ui_download_files', UI_TEXTS['download_files']),
        ('ui_lucky_dice_result', UI_TEXTS['lucky_dice_result']),
        ('ui_vip_menu', UI_TEXTS['vip_menu']),
        ('ui_add_balance_menu', UI_TEXTS['add_balance_menu']),
        ('external_api_url', 'https://adminpanels.shop/api/reseller_v1.php'),
        ('external_api_key', ''),
        ('external_master_key', ''),
        ('binance_pay_api_key', ''), ('binance_pay_secret_key', ''), ('binance_pay_certificate_sn', ''),
        ('binance_pay_base_url', 'https://bpay.binanceapi.com'), ('binance_pay_currency', 'USDT'), ('binance_pay_exchange_rate', '90'),
        ('ai_support_enabled', 'ON'), ('ai_endpoint', ''), ('ai_api_key', ''), ('ai_model', 'gpt-4o-mini'),
        ('bot_api_enabled', 'ON'), ('bot_api_public_url', ''), ('bot_api_rate_limit', '60'), ('bot_api_price', '90'),
    ]
    for slot, emoji_id in DEFAULT_EMOJIS.items():
        default_settings.append((f"emoji_{slot}", emoji_id))
    
    for key, val in default_settings:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    # Migrate the previous single external API into Multi-API Slot 1.
    c.execute("SELECT COUNT(*) FROM api_providers")
    if c.fetchone()[0] == 0:
        old_url = c.execute("SELECT value FROM settings WHERE key='external_api_url'").fetchone()
        old_key = c.execute("SELECT value FROM settings WHERE key='external_api_key'").fetchone()
        old_master = c.execute("SELECT value FROM settings WHERE key='external_master_key'").fetchone()
        if old_url and old_url[0]:
            headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json, text/plain, */*'}
            if old_master and old_master[0]: headers['x-master-key']=old_master[0]
            body={'api_key':'{{api_key}}','action':'buy','product_id':'{{product_id}}','duration':'{{duration}}'}
            c.execute("INSERT INTO api_providers(slot,name,url,method,headers_json,body_json,content_type,enabled,priority,source_code,last_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (1,'Legacy External API',old_url[0],'POST',json.dumps(headers),json.dumps(body),'application/x-www-form-urlencoded',1,1,'Migrated from external_api_* settings','migrated'))
            if old_key and old_key[0]: c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('api_slot_1_key',?)",(old_key[0],))

    conn.commit()
    conn.close()

def migrate_categories() -> None:
    done = get_setting("migration_done", "0")
    
    # ALWAYS force update emojis and UI texts regardless of migration status
    logger.info("Forcing emoji and UI text updates...")
    
    # Update all emoji settings
    for slot, emoji_id in DEFAULT_EMOJIS.items():
        set_setting(f"emoji_{slot}", emoji_id)
    
    # Force update UI texts
    set_setting("ui_start_menu", UI_TEXTS['start_menu'])
    set_setting("ui_add_balance_menu", UI_TEXTS['add_balance_menu'])
    set_setting("ui_download_files", UI_TEXTS['download_files'])
    set_setting("ui_lucky_dice_result", UI_TEXTS['lucky_dice_result'])
    set_setting("ui_vip_menu", UI_TEXTS['vip_menu'])
    logger.info("UI texts and emojis updated with new placeholders and IDs.")
    
    if done == "1":
        return
    
    logger.info("Running category migration...")
    
    mapping = {
        "android non root panel": "ANDROID NON ROOT PANEL",
        "android root panel": "ANDROID ROOT PANEL",
        "iphone panel": "IPHONE PANEL",
        "pc panel": "PC PANEL",
        "guild calory credit": "GUILD CALORY CREDIT",
        "carrom panel": "CARROM PANEL",
    }
    for old, new in mapping.items():
        db_query("UPDATE products SET category = ? WHERE LOWER(category) = ?", (new, old))
    
    db_query(
        "UPDATE products SET category = 'ANDROID NON ROOT PANEL' "
        "WHERE LOWER(category) NOT IN (?, ?, ?, ?, ?, ?)",
        (
            "android non root panel", "android root panel", "iphone panel",
            "pc panel", "guild calory credit", "carrom panel"
        )
    )
    
    set_setting("migration_done", "1")
    logger.info("Category migration complete.")

# ==============================================================================
# 5. MIDDLEWARES & SECURITY
# ==============================================================================
async def hacker_loading(message: Message, text: str = "Decrypting Data") -> Message:
    msg = await message.answer(f"⚡ {text}\n[□□□] 0%")
    await asyncio.sleep(0.3)
    await msg.edit_text(f"⚡ {text}\n[■□□] 33%", parse_mode='HTML')
    await asyncio.sleep(0.3)
    await msg.edit_text(f"⚡ {text}\n[■■□] 66%", parse_mode='HTML')
    await asyncio.sleep(0.3)
    await msg.edit_text(f"⚡ {text}\n[■■■] 100%", parse_mode='HTML')
    return msg

class GlobalSecurityMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.last_action_times = {}

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id
        now = time.time()
        if user_id in self.last_action_times:
            if now - self.last_action_times[user_id] < 0.3:
                return
        self.last_action_times[user_id] = now

        if not is_admin(user_id):
            user_info = db_query("SELECT is_banned FROM users WHERE user_id=?", (user_id,), fetchone=True)
            if user_info and user_info[0] == 1:
                msg = "🚫 <b>ACCESS DENIED</b>\nYou have been banned from using this bot.\nContact support if you think this is a mistake."
                if isinstance(event, Message): await event.answer(msg)
                elif isinstance(event, CallbackQuery): await event.answer(msg, show_alert=True)
                return
                
            status_check = db_query("SELECT value FROM settings WHERE key='bot_status'", fetchone=True)
            status = status_check[0] if status_check else 'ON'
            if status == 'OFF':
                msg = "⚠️ <b>Store Maintenance</b>\n\nThe store is currently offline for updates. Please check back later!"
                if isinstance(event, Message): await event.answer(msg)
                elif isinstance(event, CallbackQuery): await event.answer("⚠️ Bot is currently OFF for Maintenance.", show_alert=True)
                return
                
        return await handler(event, data)

dp.message.middleware(GlobalSecurityMiddleware())
dp.callback_query.middleware(GlobalSecurityMiddleware())

# ==============================================================================
# 6. FSM STATES
# ==============================================================================
class UserStates(StatesGroup):
    wait_for_ticket = State()
    wait_for_redeem = State()
    custom_amount_input = State()
    ai_chat = State()
    bot_connect_token = State()

class AdminStates(StatesGroup):
    add_prod_category = State()
    quick_add_product = State()
    add_prod_panel_name = State()
    add_prod_name = State()
    add_prod_validity = State()
    add_prod_device_limit = State()
    add_prod_price = State()
    add_prod_reseller_price = State()
    add_prod_apk = State()
    add_prod_keys = State()
    
    edit_prod_field = State()
    wait_for_new_value = State()
    wait_for_add_keys = State()
    wait_for_delete_key = State()
    
    broadcast_msg = State()
    add_coupon_code = State()
    add_coupon_amount = State()
    add_coupon_uses = State()
    
    wait_for_fampay_api = State()
    
    ticket_reply_msg = State()
    reseller_manage_id = State()
    manage_target_user = State()
    wait_for_add_money = State()
    wait_for_minus_money = State()
    wait_for_warning = State()
    
    spin_add_reward = State()
    spin_set_limit = State()
    wait_for_howto_video = State()
    youtube_lesson_title = State()
    youtube_lesson_url = State()
    youtube_course_price = State()
    youtube_course_contact = State()
    wait_for_all_files_link = State()
    
    edit_ui_text = State()
    edit_reseller_price = State()
    wait_for_reseller_setup_fee = State()
    wait_for_reseller_min_balance = State()
    confirm_ban = State()
    
    wait_for_support_telegram = State()
    wait_for_support_whatsapp = State()
    wait_for_category_emoji = State()
    wait_for_panel_emoji_id = State()
    wait_for_emoji_slot = State()
    wait_for_ext_url = State()
    wait_for_ext_key = State()
    wait_for_ext_master = State()
    multi_api_setup = State()
    multi_api_paste = State()
    binance_pay_setup = State()
    add_prod_external = State()
    add_prod_external_product_id = State()
    add_prod_external_duration = State()
    add_prod_api_slot = State()
    ai_setup = State()
    bot_api_public_url = State()

# ==============================================================================
# 7. KEYBOARDS
# ==============================================================================
def get_category_emoji(category: str) -> str:
    slot_map = {
        "ANDROID NON ROOT PANEL": "category_android_non_root",
        "ANDROID ROOT PANEL": "category_android_root",
        "IPHONE PANEL": "category_iphone",
        "PC PANEL": "category_pc",
        "GUILD CALORY CREDIT": "product_store",
        "CARROM PANEL": "product_store",
    }
    slot = slot_map.get(category)
    if slot:
        return get_emoji_icon(slot, DEFAULT_EMOJIS.get(slot, ""))
    return ""

def get_panel_emoji(panel_name: str) -> str:
    stored = get_setting(f"panel_emoji_{panel_name}", "")
    if stored and stored.isdigit():
        return stored
    return get_emoji_icon("product_store")

def contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Verify Contact", request_contact=True)]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )

def main_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    status_check = db_query("SELECT value FROM settings WHERE key='reseller_system_status'", fetchone=True)
    sys_status = status_check[0] if status_check else 'ON'
    vip_sys_check = db_query("SELECT value FROM settings WHERE key='vip_status'", fetchone=True)
    vip_system = vip_sys_check[0] if vip_sys_check else 'OFF'

    is_reseller = False
    if user_id:
        user_check = db_query("SELECT is_reseller FROM users WHERE user_id=?", (user_id,), fetchone=True)
        if user_check:
            is_reseller = bool(user_check[0])

    # Screenshot-inspired premium shop layout. The existing callback_data is
    # intentionally preserved so all current features continue to work.
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✦ ENTER PREMIUM STORE ✦", callback_data="menu_shop",
                icon_custom_emoji_id=get_emoji_icon("product_store"), style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="💳 ADD FUNDS", callback_data="menu_add_balance",
                icon_custom_emoji_id=get_emoji_icon("add_balance"), style="success"
            )
        ],
        [
            InlineKeyboardButton(
                text="👤 Profile", callback_data="menu_profile",
                icon_custom_emoji_id=get_emoji_icon("profile"), style="primary"
            ),
            InlineKeyboardButton(
                text="🧾 My Orders", callback_data="menu_orders",
                icon_custom_emoji_id=get_emoji_icon("history"), style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="📥 Downloads", callback_data="menu_all_files",
                icon_custom_emoji_id=get_emoji_icon("download"), style="success"
            ),
            InlineKeyboardButton(
                text="🎁 Rewards", callback_data="menu_referral",
                icon_custom_emoji_id=get_emoji_icon("referral"), style="success"
            )
        ],
        [
            InlineKeyboardButton(
                text="🎲 Daily Gift", callback_data="menu_spin_landing",
                icon_custom_emoji_id=get_emoji_icon("ludo_spin"), style="success"
            ),
            InlineKeyboardButton(
                text="🎓 YouTube Course", callback_data="menu_how_to",
                icon_custom_emoji_id=get_emoji_icon("tutorial"), style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="🛟 PREMIUM SUPPORT", callback_data="menu_support",
                icon_custom_emoji_id=get_emoji_icon("support"), style="danger"
            )
        ],
    ])

    if sys_status == 'ON' or is_reseller:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text="♛ RESELLER CLUB", callback_data="menu_reseller_dash",
                icon_custom_emoji_id=get_emoji_icon("reseller"), style="success"
            )
        ])
    if vip_system == 'ON':
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text="🌟 VIP CLUB", callback_data="menu_vip_dash",
                icon_custom_emoji_id=get_emoji_icon("vip"), style="success"
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(
            text="🤖 AI SUPPORT", callback_data="menu_ai_support",
            icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary"
        )
    ])
    return kb

def back_kb(callback: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="BACK", callback_data=callback,
                icon_custom_emoji_id=get_emoji_icon("back"),
                style="danger"
            )
        ]]
    )

def admin_kb() -> InlineKeyboardMarkup:
    status = db_query("SELECT value FROM settings WHERE key='bot_status'", fetchone=True)
    status_val = status[0] if status else 'ON'
    vip_status = db_query("SELECT value FROM settings WHERE key='vip_status'", fetchone=True)
    vip_val = vip_status[0] if vip_status else 'OFF'
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Bot Statistics", callback_data="admin_view_stats", icon_custom_emoji_id=get_emoji_icon("global_stats"), style="success")],
        [InlineKeyboardButton(text="👥 User Control Panel", callback_data="admin_user_control_start", icon_custom_emoji_id=get_emoji_icon("profile"), style="success")],
        [InlineKeyboardButton(text="🛠️ Advanced Management", callback_data="admin_advanced_management", icon_custom_emoji_id=get_emoji_icon("shield_icon"), style="success")],
        [
            InlineKeyboardButton(text="➕ Add Product", callback_data="admin_add_prod", icon_custom_emoji_id=get_emoji_icon("product_store"), style="success"),
            InlineKeyboardButton(text="⚡ Quick Add", callback_data="admin_quick_add_prod", icon_custom_emoji_id=get_emoji_icon("product_store"), style="success"),
            InlineKeyboardButton(text="📦 Manage Products", callback_data="admin_manage_prods", icon_custom_emoji_id=get_emoji_icon("product_store"), style="success")
        ],
        [
            InlineKeyboardButton(text="👑 Reseller Mgmt", callback_data="admin_reseller_menu", icon_custom_emoji_id=get_emoji_icon("reseller"), style="success"),
            InlineKeyboardButton(text="🎰 Spin Settings", callback_data="admin_spin_menu", icon_custom_emoji_id=get_emoji_icon("ludo_spin"), style="success")
        ],
        [
            InlineKeyboardButton(text="🎟 Create Coupon", callback_data="admin_create_coupon", icon_custom_emoji_id=get_emoji_icon("redeem_icon"), style="success"),
            InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast_btn", icon_custom_emoji_id=get_emoji_icon("telegram"), style="success")
        ],
        [
            InlineKeyboardButton(text="🎫 View Tickets", callback_data="admin_view_tickets", icon_custom_emoji_id=get_emoji_icon("support"), style="success"),
            InlineKeyboardButton(text="📹 Tutorial Video", callback_data="admin_set_video", icon_custom_emoji_id=get_emoji_icon("tutorial"), style="success")
        ],
        [
            InlineKeyboardButton(text="🎓 YouTube Course", callback_data="admin_youtube_course", icon_custom_emoji_id=get_emoji_icon("tutorial"), style="success")
        ],
        [
            InlineKeyboardButton(text="🔗 All Files Link", callback_data="admin_set_all_files", icon_custom_emoji_id=get_emoji_icon("download"), style="success"),
            InlineKeyboardButton(text="🎨 Edit All Emojis", callback_data="admin_edit_emojis", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="success")
        ],
        [
            InlineKeyboardButton(text="💳 FamPay Gateway Setup", callback_data="admin_setup_fampay", icon_custom_emoji_id=get_emoji_icon("upi"), style="success")
        ],
        [
            InlineKeyboardButton(text="🔗 Multi API Manager", callback_data="admin_multi_api", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="success"),
            InlineKeyboardButton(text="🤖 AI API Paste", callback_data="admin_ai_api", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="success")
        ],
        [
            InlineKeyboardButton(text="🧠 AI Support Setup", callback_data="admin_ai_support", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="success")
        ],
        [
            InlineKeyboardButton(text="🟡 Binance Pay Setup", callback_data="admin_binance_pay", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="success")
        ],
        [
            InlineKeyboardButton(text="🤖 Reseller Bot API", callback_data="admin_bot_api", icon_custom_emoji_id=get_emoji_icon("telegram"), style="primary")
        ],
        [
            InlineKeyboardButton(text="✏️ Edit UI Texts", callback_data="admin_edit_ui_menu", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="success"),
            InlineKeyboardButton(text="📝 Edit Reseller Price", callback_data="admin_edit_reseller_price", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="success")
        ],
        [
            InlineKeyboardButton(text="💰 Reseller Fee", callback_data="admin_set_reseller_fee", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="success"),
            InlineKeyboardButton(text="💳 Min Balance", callback_data="admin_set_reseller_min", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="success")
        ],
        [
            InlineKeyboardButton(text="📞 Set Support Links", callback_data="admin_set_support_links", icon_custom_emoji_id=get_emoji_icon("support"), style="success"),
            InlineKeyboardButton(text="🎨 Set Category Emojis", callback_data="admin_set_category_emojis", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="success")
        ],
        [
            InlineKeyboardButton(text="🖼 Set Panel Emojis", callback_data="admin_set_panel_emojis", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="success")
        ],
        [
            InlineKeyboardButton(
                text=f"Bot Status: {status_val} {'🟢' if status_val == 'ON' else '🔴'}",
                callback_data="admin_toggle_bot",
                icon_custom_emoji_id=get_emoji_icon("check_icon"),
                style="success" if status_val == 'ON' else "danger"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"VIP System: {vip_val} {'🟢' if vip_val == 'ON' else '🔴'}",
                callback_data="admin_toggle_vip_sys",
                icon_custom_emoji_id=get_emoji_icon("vip"),
                style="success" if vip_val == 'ON' else "danger"
            )
        ]
    ])
    return kb

def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Back to Admin", callback_data="admin_panel_back",
            icon_custom_emoji_id=get_emoji_icon("back"),
            style="danger"
        )
    ]])

# ==============================================================================
# 8. NOTIFICATIONS
# ==============================================================================
async def send_advanced_notification(user_id: int, notif_type: str, amount: float, product: str = None, key: str = None, gateway: str = "FamPay") -> None:
    user_info = db_query("SELECT first_name, phone, username, is_reseller, is_vip FROM users WHERE user_id=?", (user_id,), fetchone=True)
    
    name = user_info[0] if user_info else "Unknown"
    phone = user_info[1] if user_info and user_info[1] else "Not Provided"
    username = f"@{user_info[2]}" if user_info and user_info[2] else "None"
    
    tags = []
    if user_info and user_info[3]: tags.append("👑 Reseller")
    if user_info and user_info[4]: tags.append("🌟 VIP")
    tag_str = " | ".join(tags) if tags else "👤 Regular"
        
    time_now = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    
    if notif_type == "ORDER":
        title = "🛒 <b>NEW ORDER PROCESSED!</b> 🛒"
        details = (f"📦 <b>Product:</b> {product}\n🔑 <b>Key:</b> <code>{key}</code>\n💰 <b>Amount Paid:</b> ₹{amount:.2f}\n📅 <b>Time:</b> {time_now}")
    else:
        title = "💰 <b>NEW WALLET DEPOSIT!</b> 💰"
        details = (f"💵 <b>Amount Added:</b> ₹{amount:.2f}\n🧾 <b>Gateway:</b> {gateway}\n🆔 <b>Reference:</b> <code>{product}</code>\n📅 <b>Time:</b> {time_now}")

    msg = f"{title}\n━━━━━━━━━━━━━━━━━━\n👤 <b>Name:</b> {name}\n🆔 <b>User ID:</b> <code>{user_id}</code>\n📱 <b>Phone:</b> {phone}\n🔗 <b>Username:</b> {username}\n🏷 <b>Status:</b> {tag_str}\n━━━━━━━━━━━━━━━━━━\n{details}"
    try: 
        await notify_admins( msg, parse_mode='HTML')
    except Exception as e: 
        logger.error(f"Failed to send admin notification: {e}")

# ==============================================================================
# 9. FAMPAY PAYMENT VERIFIER
# ==============================================================================
FAMPAY_ORDER_TTL = 300

def get_fampay_base_url() -> str:
    base = get_setting("fampay_base_url", "https://fam.aryanispe.in").strip().rstrip("/")
    return base or "https://fam.aryanispe.in"

def get_fampay_create_url() -> str:
    return f"{get_fampay_base_url()}/api/qr.php"

def get_fampay_verify_url() -> str:
    return f"{get_fampay_base_url()}/api/verify-order.php"

def mark_transaction_paid_once(order_id: str, user_id: int, amount: float) -> bool:
    """Atomically mark a pending transaction paid and credit the wallet once."""
    conn = sqlite3.connect('yp_shop.db')
    try:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE transactions SET status='paid' WHERE order_id=? AND user_id=? AND status='pending'", (order_id, user_id))
        if c.rowcount != 1:
            conn.rollback()
            return False
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"FamPay atomic credit failed for {order_id}: {e}")
        return False
    finally:
        conn.close()

async def run_payment_verification(user_id: int, order_id: str, reply_target: Any) -> None:
    txn = db_query("SELECT amount_inr, status, timestamp, COALESCE(gateway_amount, 0) FROM transactions WHERE order_id=? AND user_id=?", (order_id, user_id), fetchone=True)
    if not txn:
        err = "❌ Invalid or fake payment order ID."
        if isinstance(reply_target, CallbackQuery): await reply_target.answer(err, show_alert=True)
        else: await reply_target.answer(err)
        return

    base_amount, status, created_ts, gateway_amount = txn
    if status == 'paid':
        msg = "✅ This payment has already been securely credited to your wallet."
        if isinstance(reply_target, CallbackQuery): await reply_target.answer(msg, show_alert=True)
        else: await reply_target.answer(msg)
        return
    if status in ('expired', 'failed') or time.time() - created_ts > FAMPAY_ORDER_TTL:
        db_query("UPDATE transactions SET status='expired' WHERE order_id=? AND status='pending'", (order_id,))
        msg = "⏳ <b>FamPay Order Expired</b>\nPlease create a new payment request."
        if isinstance(reply_target, CallbackQuery): await reply_target.message.edit_text(msg, reply_markup=back_kb(), parse_mode='HTML')
        else: await reply_target.answer(msg, reply_markup=back_kb(), parse_mode='HTML')
        return

    api_key = get_setting("fampay_api_key", "").strip()
    if not api_key:
        msg = "⚠️ FamPay Gateway API key is not configured. Ask an admin to set it up."
        if isinstance(reply_target, CallbackQuery): await reply_target.answer(msg, show_alert=True)
        else: await reply_target.answer(msg)
        return

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(get_fampay_verify_url(), params={"api_key": api_key, "order_id": order_id}, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                try: res_json = await resp.json(content_type=None)
                except Exception: res_json = {}

                if resp.status == 200 and res_json.get("status") == "success":
                    data = res_json.get("data") or {}
                    paid_amount = float(data.get("amount") or 0)
                    if gateway_amount and paid_amount and abs(paid_amount - float(gateway_amount)) > 0.011:
                        msg = "⚠️ Payment amount mismatch detected. The wallet was NOT credited."
                        if isinstance(reply_target, CallbackQuery): await reply_target.answer(msg, show_alert=True)
                        else: await reply_target.answer(msg)
                        return
                    if mark_transaction_paid_once(order_id, user_id, float(base_amount)):
                        success_msg = (
                            f"🎉 <b>FAMPAY PAYMENT VERIFIED!</b>\n\n"
                            f"✅ {fmt_curr(base_amount)} has been added to your wallet.\n"
                            f"🧾 Order: <code>{order_id}</code>\n"
                            f"🔖 UTR: <code>{data.get('utr', 'N/A')}</code>"
                        )
                        if isinstance(reply_target, CallbackQuery): await reply_target.message.edit_text(success_msg, reply_markup=back_kb(), parse_mode='HTML')
                        else: await reply_target.answer(success_msg, reply_markup=back_kb(), parse_mode='HTML')
                        await send_advanced_notification(user_id, "DEPOSIT", float(base_amount), product=order_id, gateway="FamPay")
                        log_activity(user_id, "DEPOSIT_SUCCESS", f"Amount: {base_amount}, Gateway: FamPay, Order: {order_id}, UTR: {data.get('utr', '')}")
                    else:
                        msg = "✅ Payment already processed. Your wallet was not credited twice."
                        if isinstance(reply_target, CallbackQuery): await reply_target.answer(msg, show_alert=True)
                        else: await reply_target.answer(msg)
                    return

                if resp.status == 408 or res_json.get("status") == "expired":
                    db_query("UPDATE transactions SET status='expired' WHERE order_id=? AND status='pending'", (order_id,))
                    msg = "⏳ <b>FamPay Order Expired</b>\nPlease create a new payment request."
                elif resp.status == 429:
                    msg = "⏳ FamPay rate limit reached. Please wait a few seconds before verifying again."
                elif res_json.get("status") in {"pending", "processing"}:
                    msg = "⏳ Payment is still pending at FamPay. Please wait and verify again."
                else:
                    msg = f"⚠️ FamPay Gateway: {res_json.get('message', 'Payment not confirmed yet.')}"
                if isinstance(reply_target, CallbackQuery): await reply_target.answer(msg, show_alert=True)
                else: await reply_target.answer(msg)
        except Exception as e:
            logger.error(f"FamPay API Error: {e}")
            msg = "⚠️ Unable to connect to FamPay Gateway right now. Please try again shortly."
            if isinstance(reply_target, CallbackQuery): await reply_target.answer(msg, show_alert=True)
            else: await reply_target.answer(msg)

async def auto_verify_task() -> None:
    while True:
        await asyncio.sleep(20)
        api_key = get_setting("fampay_api_key", "").strip()
        if not api_key:
            continue
        pending_txns = db_query("SELECT order_id, user_id, amount_inr, timestamp, COALESCE(gateway_amount, 0) FROM transactions WHERE status='pending' ORDER BY timestamp ASC LIMIT 5", fetchall=True) or []
        if not pending_txns:
            continue
        async with aiohttp.ClientSession() as session:
            for order_id, user_id, amount, ts, gateway_amount in pending_txns:
                if time.time() - ts > FAMPAY_ORDER_TTL:
                    db_query("UPDATE transactions SET status='expired' WHERE order_id=? AND status='pending'", (order_id,))
                    try: await bot.send_message(user_id, f"⏳ <b>FamPay Order Expired!</b>\nOrder <code>{order_id}</code> was not paid within 5 minutes.", parse_mode='HTML')
                    except Exception: pass
                    continue
                try:
                    async with session.get(get_fampay_verify_url(), params={"api_key": api_key, "order_id": order_id}, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        try: res_json = await resp.json(content_type=None)
                        except Exception: res_json = {}
                        if resp.status == 200 and res_json.get("status") == "success":
                            data = res_json.get("data") or {}
                            paid_amount = float(data.get("amount") or 0)
                            if gateway_amount and paid_amount and abs(paid_amount - float(gateway_amount)) > 0.011:
                                logger.warning(f"FamPay amount mismatch for {order_id}: expected {gateway_amount}, got {paid_amount}")
                                continue
                            if mark_transaction_paid_once(order_id, user_id, float(amount)):
                                try:
                                    await bot.send_message(user_id, f"✨ <b>FAMPAY AUTO-VERIFIED!</b>\n\n✅ {fmt_curr(amount)} has been added to your balance.\n🧾 Order: <code>{order_id}</code>", parse_mode='HTML')
                                except Exception: pass
                                await send_advanced_notification(user_id, "DEPOSIT", float(amount), product=order_id, gateway="FamPay Auto")
                                log_activity(user_id, "DEPOSIT_AUTO_SUCCESS", f"Amount: {amount}, Gateway: FamPay Auto, Order: {order_id}, UTR: {data.get('utr', '')}")
                        elif resp.status == 408 or res_json.get("status") == "expired":
                            db_query("UPDATE transactions SET status='expired' WHERE order_id=? AND status='pending'", (order_id,))
                except Exception as e:
                    logger.debug(f"FamPay auto-verify exception for {order_id}: {e}")

# ==============================================================================
# 10. ONBOARDING & START
# ==============================================================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    try: await message.answer_sticker(WELCOME_STICKER_ID)
    except: pass 
    
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("v_"):
        order_id = args[1].split("v_")[1]
        msg = await message.answer("🔄 <b>Verifying your payment securely...</b>\n<i>Connecting to gateway...</i>", parse_mode='HTML')
        await run_payment_verification(message.from_user.id, order_id, msg)
        return

    referred_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try: referred_by = int(args[1].split("_")[1])
        except: pass

    user = db_query("SELECT phone FROM users WHERE user_id=?", (message.from_user.id,), fetchone=True)
    current_username = message.from_user.username or ""
    db_query("UPDATE users SET username=? WHERE user_id=?", (current_username, message.from_user.id))

    if not user or not user[0]:
        db_query("INSERT OR IGNORE INTO users (user_id, first_name, username, referred_by, joined_date) VALUES (?, ?, ?, ?, ?)", 
                 (message.from_user.id, message.from_user.first_name, current_username, referred_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        log_activity(message.from_user.id, "ACCOUNT_CREATED")
        verification_text = (
            "<b>🛡 VERIFICATION REQUIRED</b>\n\n"
            "To safeguard your orders and account, we need to verify you.\n"
            "👇 <b>Tap the button below:</b>"
        )
        # Some Telegram chats/clients reject request_contact keyboards. Do not let
        # that API error break /start; fall back to a plain verification prompt.
        try:
            if message.chat.type == "private":
                await message.answer(verification_text, parse_mode='HTML', reply_markup=contact_kb())
            else:
                await message.answer(verification_text, parse_mode='HTML')
        except Exception as verification_err:
            logger.exception("Verification keyboard/message failed for user %s: %s", message.from_user.id, verification_err)
            try:
                await message.answer(
                    "🛡 VERIFICATION REQUIRED\n\n"
                    "Please open this bot in a private chat and send your Telegram contact using the Verify Contact button.",
                    parse_mode=None,
                    reply_markup=ReplyKeyboardRemove(),
                )
            except Exception as fallback_err:
                logger.exception("Verification fallback also failed for user %s: %s", message.from_user.id, fallback_err)
    else:
        log_activity(message.from_user.id, "CMD_START")
        loading_message = await hacker_loading(message, "Opening Premium Store")
        try:
            await loading_message.delete()
        except Exception:
            pass
        await send_main_menu(message)

@dp.message(F.contact)
async def handle_contact(message: Message):
    if message.contact.user_id == message.from_user.id:
        db_query("UPDATE users SET phone=? WHERE user_id=?", (message.contact.phone_number, message.from_user.id))
        referrer = db_query("SELECT referred_by FROM users WHERE user_id=?", (message.from_user.id,), fetchone=True)
        if referrer and referrer[0]:
            db_query("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id=?", (referrer[0],))
            try: await bot.send_message(referrer[0], f"🎉 <b>Referral Success!</b>\nUser <b>{message.from_user.first_name}</b> joined using your link!", parse_mode='HTML')
            except: pass
        log_activity(message.from_user.id, "CONTACT_VERIFIED")
        await message.answer("✅ Verification successful! Welcome to the system.", reply_markup=ReplyKeyboardRemove())
        loading_message = await hacker_loading(message, "Preparing Your Store")
        try:
            await loading_message.delete()
        except Exception:
            pass
        await send_main_menu(message)
    else:
        await message.answer("❌ Security Alert: Please share your OWN contact using the provided button.")

async def send_main_menu(ctx: Any):
    user_id = ctx.from_user.id
    user = db_query(
        "SELECT first_name, balance, account_type, is_reseller, is_vip "
        "FROM users WHERE user_id=?",
        (user_id,),
        fetchone=True,
    )
    product_count = db_query(
        "SELECT COUNT(*) FROM products WHERE is_active=1",
        fetchone=True,
    )
    first_name = escape(str(user[0] if user and user[0] else getattr(ctx.from_user, "first_name", "User")))
    account_type = "Reseller" if user and user[3] else ("VIP" if user and user[4] else (user[2] if user and user[2] else "Standard User"))
    text = get_ui_text(
        "start_menu",
        shop_name=escape(SHOP_NAME),
        first_name=first_name,
        account_id=user_id,
        balance=fmt_curr(float(user[1] or 0)) if user else fmt_curr(0),
        account_type=escape(account_type),
        available_products=int(product_count[0] if product_count else 0),
    )
    kb = main_menu_kb(ctx.from_user.id)
    if isinstance(ctx, Message): 
        await ctx.answer(text, reply_markup=kb, parse_mode='HTML')
    else: 
        await ctx.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    log_activity(call.from_user.id, "RETURN_MAIN_MENU")
    await send_main_menu(call)

# ==============================================================================
# 11. ADD BALANCE
# ==============================================================================
@dp.callback_query(F.data == "menu_add_balance")
async def select_gateway_menu(call: CallbackQuery):
    log_activity(call.from_user.id, "VIEW_ADD_BALANCE")
    text = get_ui_text("add_balance_menu")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 FAMPAY PAY", callback_data="gateway_fampay", icon_custom_emoji_id=get_emoji_icon("upi"), style="primary")],
        [InlineKeyboardButton(text="🟡 BINANCE PAY", callback_data="gateway_binance", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="primary")],
        [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

# ==============================================================================
# 12. FAMPAY PAYMENT FLOW
# ==============================================================================
@dp.callback_query(F.data == "gateway_fampay")
async def add_balance_fampay(call: CallbackQuery):
    text = "💳 <b>— FAMPAY PAYMENT —</b> 💳\n\nSelect amount to add to your wallet:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₹50", callback_data="pay_50", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="primary"), InlineKeyboardButton(text="₹100", callback_data="pay_100", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="primary")],
        [InlineKeyboardButton(text="₹200", callback_data="pay_200", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="primary"), InlineKeyboardButton(text="₹500", callback_data="pay_500", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="primary")],
        [InlineKeyboardButton(text="✏️ Custom Amount", callback_data="custom_deposit_keypad", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
        [InlineKeyboardButton(text="Back", callback_data="menu_add_balance", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "custom_deposit_keypad")
async def show_custom_keypad(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.custom_amount_input)
    await state.update_data(amount_str="0")
    await show_keypad(call.message)

async def show_keypad(message: Message, amount_str: str = "0"):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="      1      ", callback_data="kp_1", style="primary"), InlineKeyboardButton(text="      2      ", callback_data="kp_2", style="primary"), InlineKeyboardButton(text="      3      ", callback_data="kp_3", style="primary")],
        [InlineKeyboardButton(text="      4      ", callback_data="kp_4", style="primary"), InlineKeyboardButton(text="      5      ", callback_data="kp_5", style="primary"), InlineKeyboardButton(text="      6      ", callback_data="kp_6", style="primary")],
        [InlineKeyboardButton(text="      7      ", callback_data="kp_7", style="primary"), InlineKeyboardButton(text="      8      ", callback_data="kp_8", style="primary"), InlineKeyboardButton(text="      9      ", callback_data="kp_9", style="primary")],
        [InlineKeyboardButton(text="    ⌫    ", callback_data="kp_backspace", style="danger"), InlineKeyboardButton(text="      0      ", callback_data="kp_0", style="primary"), InlineKeyboardButton(text="    C    ", callback_data="kp_clear", style="danger")],
        [InlineKeyboardButton(text=f"✅ Confirm (₹{amount_str})", callback_data="kp_confirm", icon_custom_emoji_id=get_emoji_icon("check_icon"), style="success")],
        [InlineKeyboardButton(text="Cancel", callback_data="gateway_fampay", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await message.edit_text(f"💳 <b>Enter FamPay Amount (₹):</b>\n\nCurrent: ₹{amount_str}", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("kp_"), UserStates.custom_amount_input)
async def keypad_handler(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount_str = data.get("amount_str", "0")
    action = call.data.split("_")[1]
    if action == "confirm":
        if amount_str == "0":
            await call.answer("Amount cannot be zero.", show_alert=True)
            return
        try:
            amount = float(amount_str)
            if amount < 10:
                await call.answer("Minimum deposit is ₹10.", show_alert=True)
                return
            await state.clear()
            await call.message.edit_text("⏳ <b>Creating secure FamPay payment...</b>", parse_mode='HTML')
            await generate_fampay_order(call.from_user.id, amount, call.message)
        except ValueError:
            await call.answer("Invalid amount.", show_alert=True)
        return
    if action == "backspace":
        amount_str = amount_str[:-1] if len(amount_str) > 1 else "0"
    elif action == "clear":
        amount_str = "0"
    else:
        amount_str = action if amount_str == "0" else amount_str + action
        amount_str = amount_str[:6]
    await state.update_data(amount_str=amount_str)
    await show_keypad(call.message, amount_str)
    await call.answer()

@dp.callback_query(F.data.startswith("pay_"))
async def process_fampay_payment_callback(call: CallbackQuery):
    try: inr_amount = float(call.data.split("_")[1])
    except (ValueError, IndexError):
        await call.answer("Invalid amount.", show_alert=True)
        return
    await call.message.edit_text("⏳ <b>Creating secure FamPay payment...</b>", parse_mode='HTML')
    await generate_fampay_order(call.from_user.id, inr_amount, call.message)

async def generate_fampay_order(user_id: int, inr_amount: float, message_obj: Message) -> None:
    api_key = get_setting("fampay_api_key", "").strip()
    if not api_key:
        return await message_obj.edit_text("⚠️ <b>FamPay Gateway is not configured.</b>\nAdmin must set the FamPay API key first.", reply_markup=back_kb("gateway_fampay"), parse_mode='HTML')

    current_time = int(time.time())
    order_id = f"FAM{user_id}{current_time}{random.randint(1000, 9999)}"
    bot_deep_link = f"https://t.me/{BOT_USERNAME}?start=v_{order_id}"
    db_query("INSERT INTO transactions (order_id, user_id, amount_inr, gateway_amount, status, timestamp) VALUES (?, ?, ?, ?, 'pending', ?)", (order_id, user_id, inr_amount, inr_amount, current_time))

    try:
        async with aiohttp.ClientSession() as session:
            params = {"api_key": api_key, "amount": f"{inr_amount:.2f}", "redirect_url": bot_deep_link}
            async with session.get(get_fampay_create_url(), params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                try: res_data = await resp.json(content_type=None)
                except Exception: res_data = {}
                if resp.status != 200 or res_data.get("status") != "success":
                    db_query("UPDATE transactions SET status='failed' WHERE order_id=? AND status='pending'", (order_id,))
                    return await message_obj.edit_text(f"❌ <b>FamPay Gateway Error:</b> {res_data.get('message', f'HTTP {resp.status}')}", reply_markup=back_kb("gateway_fampay"), parse_mode='HTML')
                data = res_data.get("data") or {}
                gateway_order_id = data.get("order_id") or order_id
                qr_url = data.get("qr_url") or ""
                checkout_url = data.get("checkout_url") or qr_url
                payable_amount = float(data.get("payable_amount") or inr_amount)
                expires_at = data.get("expires_at_ist") or "5 minutes"
                if gateway_order_id != order_id:
                    db_query("UPDATE transactions SET order_id=?, gateway_amount=? WHERE order_id=?", (gateway_order_id, payable_amount, order_id))
                    order_id = gateway_order_id
                else:
                    db_query("UPDATE transactions SET gateway_amount=? WHERE order_id=?", (payable_amount, order_id))
                if not checkout_url:
                    db_query("UPDATE transactions SET status='failed' WHERE order_id=? AND status='pending'", (order_id,))
                    return await message_obj.edit_text("❌ FamPay did not return a payment URL. Please try again.", reply_markup=back_kb("gateway_fampay"), parse_mode='HTML')
                rows = []
                if checkout_url:
                    rows.append([InlineKeyboardButton(text="💳 Pay with FamPay", url=checkout_url, style="success")])
                rows += [
                    [InlineKeyboardButton(text="🔄 Verify Payment", callback_data=f"verify_{order_id}", icon_custom_emoji_id=get_emoji_icon("check_icon"), style="primary")],
                    [InlineKeyboardButton(text="Cancel Transaction", callback_data="menu_add_balance", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
                ]
                upi_id = get_setting("fampay_upi", "").strip() or "Not configured"
                text = (
                    f"💳 <b>FAMPAY QR — {fmt_curr(payable_amount)}</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"💰 <b>Pay exact amount:</b> ₹{payable_amount:.2f}\n"
                    f"💠 <b>UPI ID:</b> <code>{upi_id}</code>\n"
                    f"🧾 <b>Order:</b> <code>{order_id}</code>\n\n"
                    "Scan with FamPay or any UPI app and pay the exact amount.\n"
                    "🔄 Payment status auto-check ho raha hai; successful payment ke baad balance automatically add ho jayega.\n\n"
                    "Agar payment ke baad turant balance na aaye, <b>Verify Payment</b> दबाएँ."
                )
                log_activity(user_id, "GENERATE_FAMPAY_INVOICE", f"Amount: {inr_amount}, Payable: {payable_amount}, Order: {order_id}")
                markup = InlineKeyboardMarkup(inline_keyboard=rows)
                if qr_url:
                    # Show the QR directly in Telegram, like a normal UPI payment screen.
                    try:
                        await message_obj.delete()
                    except Exception:
                        pass
                    try:
                        await bot.send_photo(
                            chat_id=message_obj.chat.id,
                            photo=qr_url,
                            caption=text,
                            reply_markup=markup,
                            parse_mode='HTML',
                        )
                    except Exception as photo_err:
                        logger.warning("FamPay QR image could not be sent: %s", photo_err)
                        await bot.send_message(
                            chat_id=message_obj.chat.id,
                            text=text,
                            reply_markup=markup,
                            parse_mode='HTML',
                        )
                else:
                    await message_obj.edit_text(text, reply_markup=markup, parse_mode='HTML')
    except Exception as e:
        db_query("UPDATE transactions SET status='failed' WHERE order_id=? AND status='pending'", (order_id,))
        logger.error(f"FamPay create-order error: {e}")
        await message_obj.edit_text("❌ <b>FamPay connection error.</b> Please try again later.", reply_markup=back_kb("gateway_fampay"), parse_mode='HTML')

@dp.callback_query(F.data.startswith("verify_"))
async def manual_verify_callback(call: CallbackQuery):
    await run_payment_verification(call.from_user.id, call.data.split("_", 1)[1], call)

# ==============================================================================
# 13. SHOP – with uppercase categories and new point_down emoji
# ==============================================================================
@dp.callback_query(F.data == "menu_shop")
async def view_shop_panels(call: CallbackQuery):
    log_activity(call.from_user.id, "VIEW_SHOP")
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    text = f"{get_emoji('product_store')} <b><u>SELECT PRODUCT PANEL</u></b>\n━━━━━━━━━━━━━━━━━━\n\n{get_emoji('point_down')} <b>Choose a panel to view its packages:</b>"
    for cat in FIXED_CATEGORIES:
        count = db_query("SELECT COUNT(*) FROM products WHERE category LIKE ? AND is_active=1", (cat + '%',), fetchone=True)[0]
        emoji_id = get_category_emoji(cat)
        kb.inline_keyboard.append([InlineKeyboardButton(text=cat, callback_data=f"cat_{cat[:30]}", icon_custom_emoji_id=emoji_id, style="danger")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("cat_"))
async def view_panel_names(call: CallbackQuery):
    category = call.data.split("cat_", 1)[1]
    panel_names = db_query("SELECT DISTINCT panel_name FROM products WHERE category LIKE ? AND is_active=1 AND panel_name != ''", (category + '%',), fetchall=True)
    panel_names = sorted(panel_names or [], key=lambda row: natural_sort_key(row[0]))
    if not panel_names:
        prods = db_query("SELECT id, name, price_inr, stock, reseller_price, validity, device_limit, external_enabled FROM products WHERE category LIKE ? AND is_active=1", (category + '%',), fetchall=True)
        if not prods: return await call.answer("❌ No products available in this category yet.", show_alert=True)
        await show_products_for_panel(call, prods, category)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    text = f"{get_emoji('product_store')} <b><u>{category.upper()} PANELS</u></b>\n━━━━━━━━━━━━━━━━━━\n\n{get_emoji('point_down')} <b>Choose a panel name:</b>"
    for pn in panel_names:
        panel = pn[0]
        emoji_id = get_panel_emoji(panel) or get_emoji_icon("product_store")
        kb.inline_keyboard.append([InlineKeyboardButton(text=panel, callback_data=f"pnl_{category[:30]}_{panel[:30]}", icon_custom_emoji_id=emoji_id, style="danger")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK TO PANELS", callback_data="menu_shop", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("pnl_"))
async def view_products_for_panel(call: CallbackQuery):
    parts = call.data.split("pnl_", 1)[1].split("_", 1)
    if len(parts) != 2: return await call.answer("Invalid selection.", show_alert=True)
    category, panel_name = parts[0], parts[1]
    prods = db_query("SELECT id, name, price_inr, stock, reseller_price, validity, device_limit, external_enabled FROM products WHERE category LIKE ? AND panel_name LIKE ? AND is_active=1", (category + '%', panel_name + '%'), fetchall=True)
    if not prods: return await call.answer("No products found for this panel.", show_alert=True)
    await show_products_for_panel(call, prods, f"{category} - {panel_name}")

async def show_products_for_panel(call: CallbackQuery, prods: List[Tuple], header: str):
    user = db_query("SELECT is_reseller, is_vip FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    is_reseller = bool(user[0]) if user else False
    is_vip = bool(user[1]) if user else False
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    text = f"{get_emoji('product_store')} <b><u>{header.upper()} PACKAGES</u></b>\n━━━━━━━━━━━━━━━━━━\n\n"
    # Always show packages in natural A-Z / 1-2-10 order, independent of add time.
    prods = sorted(prods or [], key=lambda row: natural_sort_key(row[1]))
    for p in prods:
        prod_id, package_name, normal_price, stock, reseller_price, validity, device, external_enabled = p
        normal_price = float(normal_price) if normal_price is not None else 0.0
        reseller_price = float(reseller_price) if reseller_price is not None else 0.0
        base_price = reseller_price if is_reseller else normal_price
        if is_vip: display_price = base_price - (base_price * (VIP_DISCOUNT_PERCENTAGE / 100))
        else: display_price = base_price
        stock_status = "♾️ API Available" if external_enabled else ("✅ In Stock" if stock > 0 else "❌ Out of Stock")
        text += f"{get_emoji('product_store')} ⏱ <b>Validity: {package_name}</b>\n"
        if is_reseller or is_vip:
            text += f"💰 Regular Price: <s>{fmt_curr(normal_price)}</s>\n"
            if is_reseller and not is_vip: text += f"👑 <b>Reseller Price: {fmt_curr(display_price)}</b>\n"
            elif is_vip and not is_reseller: text += f"🌟 <b>VIP Price: {fmt_curr(display_price)}</b>\n"
            else: text += f"👑🌟 <b>Super Price: {fmt_curr(display_price)}</b>\n"
        else: text += f"💰 Price: {fmt_curr(normal_price)}\n"
        text += f"📱 Limit: {device} | 📦 {stock_status}\n\n"
        if external_enabled or stock > 0:
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"Buy {package_name} - {fmt_curr(display_price)}", callback_data=f"buy_{prod_id}", icon_custom_emoji_id=get_emoji_icon("product_store"), style="danger")])
        else:
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"❌ {package_name} (Out of Stock)", callback_data="ignore_stock_click", style="danger")])
    text += f"{get_emoji('point_down')} <b>Select package below to instantly purchase:</b>"
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK TO PANELS", callback_data="menu_shop", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "ignore_stock_click")
async def ignore_stock_click(call: CallbackQuery):
    await call.answer("⚠️ This duration is completely Out of Stock! Admins have been notified to refill.", show_alert=True)

@dp.callback_query(F.data.startswith("buy_"))
async def show_purchase_options(call: CallbackQuery):
    """Show payment choices before checking/charging the user's wallet."""
    try:
        prod_id = int(call.data.split("_", 1)[1])
    except (ValueError, IndexError):
        return await call.answer("Invalid product.", show_alert=True)

    prod = db_query("""
        SELECT name, price_inr, stock, validity, device_limit, reseller_price,
               external_enabled, category, panel_name
        FROM products WHERE id=? AND is_active=1
    """, (prod_id,), fetchone=True)
    user = db_query(
        "SELECT balance, is_reseller, is_vip FROM users WHERE user_id=?",
        (call.from_user.id,),
        fetchone=True,
    )
    if not prod or not user:
        return await call.answer("Product or account not found.", show_alert=True)

    normal_price = float(prod[1] or 0.0)
    reseller_price = float(prod[5] or 0.0)
    base_price = reseller_price if user[1] else normal_price
    final_price = base_price - (base_price * (VIP_DISCOUNT_PERCENTAGE / 100)) if user[2] else base_price
    balance = float(user[0] or 0.0)

    if balance >= final_price:
        wallet_label = f"💰 Pay with Wallet Balance ({fmt_curr(balance)})"
        wallet_style = "success"
    else:
        wallet_label = f"⚠️ Wallet Balance — Need {fmt_curr(final_price - balance)} more"
        wallet_style = "danger"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=wallet_label,
            callback_data=f"wallet_buy_{prod_id}" if balance >= final_price else "wallet_insufficient",
            style=wallet_style,
        )],
        [InlineKeyboardButton(
            text=f"📲 Direct UPI Pay {fmt_curr(final_price)}",
            callback_data=f"upi_buy_{prod_id}",
            icon_custom_emoji_id=get_emoji_icon("upi"),
            style="primary",
        )],
        [InlineKeyboardButton(
            text="➕ Add Balance",
            callback_data="menu_add_balance",
            icon_custom_emoji_id=get_emoji_icon("add_balance"),
            style="success",
        )],
        [InlineKeyboardButton(text="BACK", callback_data="menu_shop", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")],
    ])
    text = (
        f"🛒 <b>SELECT PAYMENT METHOD</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>{escape(str(prod[0]))}</b>\n"
        f"💰 <b>Payable:</b> {fmt_curr(final_price)}\n"
        f"👛 <b>Wallet:</b> {fmt_curr(balance)}\n\n"
        "Choose Wallet Balance, pay directly with UPI, or add balance first."
    )
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "wallet_insufficient")
async def wallet_insufficient(call: CallbackQuery):
    await call.answer("Wallet balance is insufficient. Use Direct UPI or Add Balance.", show_alert=True)


@dp.callback_query(F.data.startswith("upi_buy_"))
async def direct_upi_purchase(call: CallbackQuery):
    """Create an exact-price UPI top-up for the selected product."""
    try:
        prod_id = int(call.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        return await call.answer("Invalid product.", show_alert=True)

    prod = db_query(
        "SELECT price_inr, reseller_price FROM products WHERE id=? AND is_active=1",
        (prod_id,),
        fetchone=True,
    )
    user = db_query(
        "SELECT balance, is_reseller, is_vip FROM users WHERE user_id=?",
        (call.from_user.id,),
        fetchone=True,
    )
    if not prod or not user:
        return await call.answer("Product or account not found.", show_alert=True)

    normal_price = float(prod[0] or 0.0)
    base_price = float(prod[1] or 0.0) if user[1] else normal_price
    amount = base_price - (base_price * (VIP_DISCOUNT_PERCENTAGE / 100)) if user[2] else base_price
    if amount <= 0:
        return await call.answer("Invalid product amount.", show_alert=True)

    await call.message.edit_text("⏳ <b>Creating secure UPI payment...</b>", parse_mode="HTML")
    await generate_fampay_order(call.from_user.id, amount, call.message)


@dp.callback_query(F.data.startswith("wallet_buy_"))
async def process_buy(call: CallbackQuery):
    prod_id = int(call.data.rsplit("_", 1)[1])
    prod = db_query("""
        SELECT name, price_inr, stock, apk_link, validity, device_limit,
               category, reseller_price, panel_name, external_enabled,
               external_product_id, requires_android_id, external_duration, api_slot
        FROM products WHERE id=?
    """, (prod_id,), fetchone=True)
    user = db_query("SELECT balance, referred_by, is_reseller, total_saved, is_vip FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if not prod:
        return await call.answer("❌ Critical Error: Item not found in DB!", show_alert=True)
    if not user:
        return await call.answer("❌ User account not found!", show_alert=True)

    normal_price = float(prod[1] or 0.0)
    reseller_price = float(prod[7] or 0.0)
    is_reseller = bool(user[2]); is_vip = bool(user[4])
    base_price = reseller_price if is_reseller else normal_price
    final_price = base_price - (base_price * (VIP_DISCOUNT_PERCENTAGE / 100)) if is_vip else base_price
    savings = normal_price - final_price

    # External/API products use the remote API as the real inventory source.
    # Their local stock number is only a display buffer and must not block API purchases.
    external_enabled = bool(prod[9])
    external_product_id = (prod[10] or "").strip()
    if not external_enabled and (prod[2] is None or prod[2] <= 0):
        return await call.answer("❌ This product is out of stock!", show_alert=True)
    if user[0] < final_price:
        return await call.answer(f"❌ Insufficient Balance! You need {fmt_curr(final_price)}.", show_alert=True)

    # Prevent double-click purchases while processing the external API.
    await call.answer("⏳ Processing your purchase...", show_alert=False)
    delivered_key = None
    api_response = None

    # Charge first; external API failures are refunded immediately.
    db_query("UPDATE users SET balance=?, spent=spent+?, orders_count=orders_count+1, total_saved=total_saved+? WHERE user_id=?",
             (user[0] - final_price, final_price, savings, call.from_user.id))

    if external_enabled:
        if not external_product_id:
            db_query("UPDATE users SET balance=balance+? WHERE user_id=?", (final_price, call.from_user.id))
            return await call.message.edit_text("❌ API product ID is not configured for this product.", reply_markup=back_kb("menu_shop"), parse_mode='HTML')

        # IMPORTANT: use the API-specific duration first. For older products,
        # fall back to the saved validity and finally the displayed package name.
        # This fixes the old bug where the package name (e.g. "1 Hour") was sent
        # even when the API price tier was stored under a different duration.
        api_duration_saved = (prod[12] or "").strip()
        duration_candidates = []
        for candidate in (api_duration_saved, prod[4], prod[0]):
            candidate = normalize_api_duration(candidate)
            if candidate and candidate not in duration_candidates:
                duration_candidates.append(candidate)

        api_response = {"status": "error", "msg": "No API duration configured"}
        api_duration_used = ""
        for api_duration in duration_candidates:
            try:
                logger.info("Trying external API duration=%r for product_id=%r", api_duration, external_product_id)
                api_response = await fetch_external_key(
                    external_product_id,
                    api_duration,
                    "",
                    int(prod[13] or 0),
                )
            except Exception as api_exc:
                logger.exception("External API purchase call crashed")
                api_response = {"status": "error", "msg": f"API call failed: {api_exc}"}

            if api_response.get("status") == "success":
                api_duration_used = api_duration
                break

            # A "price not found" response means this duration did not match the
            # configured API price tier. Try the next safe candidate. For other
            # errors (auth/server/network), stop immediately to avoid duplicate buys.
            error_blob = json.dumps(api_response, ensure_ascii=False).lower()
            if "price not found" not in error_blob and "price_not_found" not in error_blob:
                break

        if api_response.get("status") != "success":
            db_query("UPDATE users SET balance=balance+? WHERE user_id=?", (final_price, call.from_user.id))
            error_msg = api_response.get("msg", "Unknown API error")
            error_text = f"❌ <b>API Error:</b> {error_msg}\n\n💰 Your balance has been refunded."
            try:
                await call.message.edit_text(
                    error_text,
                    reply_markup=back_kb("menu_shop"),
                    parse_mode='HTML'
                )
            except Exception as tg_error:
                logger.exception("Could not edit purchase message after API failure: %s", tg_error)
                try:
                    await bot.send_message(
                        call.from_user.id,
                        error_text,
                        reply_markup=back_kb("menu_shop"),
                        parse_mode='HTML'
                    )
                except Exception:
                    logger.exception("Could not send API failure message to user")
            return

        delivered_key = api_response.get("key")
        if isinstance(delivered_key, list):
            delivered_key = "\n".join(str(x) for x in delivered_key)
        if delivered_key is None or str(delivered_key).strip() in ("", "KEY_NOT_FOUND"):
            db_query("UPDATE users SET balance=balance+? WHERE user_id=?", (final_price, call.from_user.id))
            return await call.message.edit_text("❌ API returned no key.\n\n💰 Your balance has been refunded.", reply_markup=back_kb("menu_shop"), parse_mode='HTML')
        delivered_key = str(delivered_key)
        # External API products are not limited by local key-vault stock.
        # Keep the admin-entered display stock unchanged so the product never
        # becomes "Out of Stock" after a successful API purchase.
    else:
        key_data = db_query("SELECT id, key_text FROM product_keys WHERE product_id=? AND is_used=0 LIMIT 1", (prod_id,), fetchone=True)
        if not key_data:
            db_query("UPDATE users SET balance=balance+? WHERE user_id=?", (final_price, call.from_user.id))
            return await call.message.edit_text("❌ No manual key is available.\n\n💰 Your balance has been refunded.", reply_markup=back_kb("menu_shop"), parse_mode='HTML')
        delivered_key = key_data[1]
        db_query("UPDATE product_keys SET is_used=1 WHERE id=?", (key_data[0],))
        db_query("UPDATE products SET stock=CASE WHEN stock>0 THEN stock-1 ELSE 0 END WHERE id=?", (prod_id,))

    if user[1]:
        commission = final_price * 0.15
        db_query("UPDATE users SET balance=balance+?, referral_earned=referral_earned+? WHERE user_id=?", (commission, commission, user[1]))
        try:
            await bot.send_message(user[1], f"🎁 <b>Referral Bonus Added!</b>\nYou earned {fmt_curr(commission)} from a successful purchase.", parse_mode='HTML')
        except Exception:
            pass

    product_full_name = f"{prod[6]} - {prod[8]} ({prod[0]})"
    db_query("INSERT INTO orders (user_id, product_name, price_paid, delivered_key, purchase_date) VALUES (?, ?, ?, ?, ?)",
             (call.from_user.id, product_full_name, final_price, delivered_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    log_activity(call.from_user.id, "PURCHASE_SUCCESS", f"Product: {product_full_name}, Paid: {final_price}, External API: {external_enabled}")
    await send_advanced_notification(call.from_user.id, "ORDER", final_price, product=product_full_name, key=delivered_key)

    msg = (f"✅ <b>PURCHASE SUCCESSFUL!</b>\n━━━━━━━━━━━━━━━━━━\n"
           f"📦 <b>Panel:</b> {prod[6]}\n📁 <b>Panel Name:</b> {prod[8]}\n"
           f"⏱ <b>Package:</b> {prod[0]}\n💰 <b>Amount Deducted:</b> {fmt_curr(final_price)}\n"
           f"📱 <b>Device Limit:</b> {prod[5]}\n━━━━━━━━━━━━━━━━━━\n")
    if prod[3] and prod[3].startswith("http"):
        msg += f"📥 <b>APK Link:</b> <a href='{prod[3]}'>Click Here to Download</a>\n\n"
    msg += f"🔑 <b>Your Exclusive Key:</b>\n<code>{delivered_key}</code>\n\n"
    if external_enabled and api_response:
        if api_response.get("product"):
            msg += f"📌 <b>Product:</b> {api_response['product']}\n"
        if api_response.get("duration"):
            msg += f"⏳ <b>Duration:</b> {api_response['duration']}\n"
    msg += f"\n<i>For any issues, tap Support or contact: {ADMIN_CONTACT}</i>"
    await call.message.edit_text(msg, reply_markup=back_kb("menu_shop"), disable_web_page_preview=True, parse_mode='HTML')

# ==============================================================================
# 14. USER DASHBOARD, FILES, VIP, RESELLER, ORDERS, PROFILE, REFERRAL
# ==============================================================================
@dp.callback_query(F.data == "menu_all_files")
async def all_files_handler(call: CallbackQuery):
    link_q = db_query("SELECT value FROM settings WHERE key='all_files_link'", fetchone=True)
    link = link_q[0] if link_q and link_q[0] != 'None' else None
    if link:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Access Download Channel ↗️", url=link, icon_custom_emoji_id=get_emoji_icon("download"), style="success")],
            [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
        ])
        text = get_ui_text("download_files")
        await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
    else:
        await call.answer("⚠️ Admin has not configured the private download channel link yet.", show_alert=True)

@dp.callback_query(F.data == "menu_vip_dash")
async def vip_dashboard(call: CallbackQuery):
    u = db_query("SELECT balance, is_vip, vip_since FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    is_vip = bool(u[1])
    status_str = "🟢 Active (Lifetime)" if is_vip else "🔴 Not Subscribed"
    text = get_ui_text("vip_menu", vip_status=status_str)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    if is_vip:
        text += f"\n📅 <b>Member Since:</b> {u[2]}\n\nEnjoy your permanent 15% discount!"
    else:
        text += f"\n\n💳 <b>Your Current Balance:</b> {fmt_curr(u[0])}\n"
        if u[0] >= VIP_PRICE_INR: 
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"✅ Purchase VIP for {fmt_curr(VIP_PRICE_INR)}", callback_data="execute_vip_upgrade", icon_custom_emoji_id=get_emoji_icon("vip"), style="success")])
        else:
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"❌ Need {fmt_curr(VIP_PRICE_INR)} to Upgrade", callback_data="ignore_stock_click", style="danger")])
            kb.inline_keyboard.append([InlineKeyboardButton(text="💳 Add Balance Now", callback_data="menu_add_balance", icon_custom_emoji_id=get_emoji_icon("add_balance"), style="success")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "execute_vip_upgrade")
async def execute_vip_upgrade(call: CallbackQuery):
    u = db_query("SELECT balance, is_vip FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if u[1]: return await call.answer("⚠️ You are already a VIP Member!", show_alert=True)
    if u[0] < VIP_PRICE_INR: return await call.answer(f"❌ Your balance dropped below {VIP_PRICE_INR}.", show_alert=True)
    new_balance = u[0] - VIP_PRICE_INR
    now_date = datetime.now().strftime("%Y-%m-%d")
    db_query("UPDATE users SET balance=?, is_vip=1, vip_since=? WHERE user_id=?", (new_balance, now_date, call.from_user.id))
    log_activity(call.from_user.id, "UPGRADED_VIP")
    try: await notify_admins( f"🌟 <b>NEW VIP UPGRADE</b>\n👤 User ID: <code>{call.from_user.id}</code>", parse_mode='HTML')
    except: pass
    await call.answer("🎉 Upgrade Successful! You are now a VIP Member.", show_alert=True)
    await vip_dashboard(call)

@dp.callback_query(F.data == "menu_reseller_dash")
async def reseller_dashboard(call: CallbackQuery):
    u = db_query("SELECT balance, is_reseller, reseller_since, total_saved FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    status_check = db_query("SELECT value FROM settings WHERE key='reseller_system_status'", fetchone=True)
    system_status = status_check[0] if status_check else "ON"
    setup_fee = float(get_setting("reseller_setup_fee", "200.0"))
    min_balance = float(get_setting("reseller_min_balance", "500.0"))
    if u[1]: 
        text = (f"{get_emoji('shield_icon')} <b><u>— RESELLER DASHBOARD —</u></b> {get_emoji('shield_icon')}\n\n🟢 <b>Status:</b> Active\n📅 <b>Since:</b> {u[2]}\n{get_emoji('money_icon')} <b>Total Saved:</b> {fmt_curr(u[3])}\n\n🎉 You are enjoying exclusive wholesale prices on all products!")
        access = db_query("SELECT enabled, purchased_at, price_inr FROM reseller_bot_api_access WHERE user_id=?", (call.from_user.id,), fetchone=True)
        key_row = db_query("SELECT key_prefix, key_last4, enabled, requests_count FROM reseller_api_keys WHERE user_id=?", (call.from_user.id,), fetchone=True)
        conn_row = db_query("SELECT id, bot_username, enabled FROM reseller_bot_connections WHERE user_id=? ORDER BY id DESC LIMIT 1", (call.from_user.id,), fetchone=True)
        if access and access[0]:
            text += f"\n\n🤖 <b>Bot API System:</b> 🟢 Active • Price: ₹{float(access[2] or 90):.2f}"
            if key_row:
                api_state = f"🟢 Active • <code>{key_row[0]}••••{key_row[1]}</code> • Requests: {key_row[3]}" if key_row[2] else "🔴 Disabled"
                text += f"\n🔑 <b>Personal API:</b> {api_state}"
            else:
                text += "\n🔑 <b>Personal API:</b> Not generated yet"
            if conn_row and conn_row[2]: text += f"\n🔗 <b>Connected Bot:</b> @{conn_row[1] or 'Unknown'}"
            else: text += "\n🔗 <b>Connected Bot:</b> Not connected"
        else:
            text += f"\n\n🤖 <b>Bot API System:</b> 🔒 Locked\n💰 One-time reseller API activation: <b>₹{float(get_setting('bot_api_price','90')):.2f}</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Bot API System", callback_data="menu_bot_api_system", style="primary")],
            [InlineKeyboardButton(text="💰 Add Wallet Balance", callback_data="menu_add_balance", icon_custom_emoji_id=get_emoji_icon("add_balance"), style="success")],
            [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
        ])
        await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
        return
    if system_status == "OFF": return await call.answer("⚠️ Wholesale / Reseller registrations are currently closed by Admin.", show_alert=True)
    text = (f"⚡ <b><u>— BECOME A RESELLER —</u></b> ⚡\n\nUpgrade your account to access wholesale <b>Reseller Prices</b>!\n\n📋 <b>Requirements to Upgrade:</b>\n1️⃣ Must have a minimum balance of <b>{fmt_curr(min_balance)}</b>.\n2️⃣ A one-time setup fee of <b>{fmt_curr(setup_fee)}</b> will be deducted.\n\n💳 <b>Your Current Balance:</b> {fmt_curr(u[0])}\n")
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    if u[0] >= min_balance: 
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"✅ Pay {fmt_curr(setup_fee)} & Become Reseller", callback_data="execute_reseller_upgrade", icon_custom_emoji_id=get_emoji_icon("reseller"), style="success")])
    else:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"❌ Insufficient Balance (Need {fmt_curr(min_balance)})", callback_data="ignore_stock_click", style="danger")])
        kb.inline_keyboard.append([InlineKeyboardButton(text="💳 Add Balance", callback_data="menu_add_balance", icon_custom_emoji_id=get_emoji_icon("add_balance"), style="success")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "execute_reseller_upgrade")
async def execute_reseller_upgrade(call: CallbackQuery):
    setup_fee = float(get_setting("reseller_setup_fee", "200.0"))
    min_balance = float(get_setting("reseller_min_balance", "500.0"))
    u = db_query("SELECT balance, is_reseller FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if u[1]: return await call.answer("⚠️ You are already a Reseller!", show_alert=True)
    if u[0] < min_balance: return await call.answer(f"❌ Your balance dropped below {fmt_curr(min_balance)}. Please top up.", show_alert=True)
    new_balance = u[0] - setup_fee
    db_query("UPDATE users SET balance=?, is_reseller=1, reseller_since=?, account_type='Reseller' WHERE user_id=?", (new_balance, datetime.now().strftime("%Y-%m-%d"), call.from_user.id))
    log_activity(call.from_user.id, "UPGRADED_RESELLER")
    try: await notify_admins( f"👑 <b>NEW RESELLER UPGRADE</b>\n👤 User ID: <code>{call.from_user.id}</code>", parse_mode='HTML')
    except: pass
    await call.answer("🎉 Upgrade Successful! Welcome to the Reseller tier.", show_alert=True)
    await reseller_dashboard(call)

@dp.callback_query(F.data == "menu_orders")
async def my_orders(call: CallbackQuery):
    orders = db_query("SELECT product_name, delivered_key, purchase_date, price_paid FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (call.from_user.id,), fetchall=True)
    if not orders: return await call.message.edit_text("🧾 You haven't made any purchases yet. Your vault is empty.", reply_markup=back_kb(), parse_mode='HTML')
    text = "🧾 <b><u>— YOUR RECENT ORDERS (LAST 10) —</u></b> 🧾\n\n"
    for o in orders: text += f"📦 <b>{o[0]}</b> ({fmt_curr(o[3])})\n🔑 <code>{o[1]}</code>\n📅 <i>{o[2]}</i>\n━━━━━━━━━━━━━━━━\n"
    await call.message.edit_text(text, reply_markup=back_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery):
    u = db_query("SELECT user_id, first_name, account_type, balance, orders_count, spent, referrals_count, joined_date, is_reseller, reseller_since, total_saved, is_vip FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    acc_type_display = []
    if u[8]: acc_type_display.append(f"{get_emoji('reseller')} Reseller")
    if u[11]: acc_type_display.append(f"{get_emoji('vip')} VIP")
    type_str = " | ".join(acc_type_display) if acc_type_display else f"{get_emoji('regular_user')} Regular User"
    text = (
        f"{get_emoji('grid_id')} <b><u>— YOUR SECURE PROFILE —</u></b> {get_emoji('grid_id')}\n\n"
        f"{get_emoji('grid_id')} <b>Grid ID:</b> <code>{u[0]}</code>\n"
        f"{get_emoji('name')} <b>Name:</b> {u[1]}\n"
        f"{get_emoji('account_level')} <b>Account Level:</b> {type_str}\n\n"
        f"{get_emoji('wallet_left')} <b>— Wallet —</b> {get_emoji('wallet_right')}\n"
        f"{get_emoji('wallet_left')} <b>Current Balance:</b> {fmt_curr(u[3])} {get_emoji('wallet_right')}\n\n"
        f"{get_emoji('global_stats')} <b>— Global Statistics —</b>\n"
        f"{get_emoji('total_orders')} <b>Total Orders:</b> {u[4]}\n"
        f"{get_emoji('total_spent')} <b>Total Spent:</b> {fmt_curr(u[5])}\n"
        f"{get_emoji('total_referrals')} <b>Total Referrals:</b> {u[6]}\n\n"
    )
    if u[8]:
        text += f"{get_emoji('shield_icon')} <b>— RESELLER METRICS —</b> {get_emoji('shield_icon')}\n{get_emoji('money_icon')} <b>Total Saved via Reseller:</b> {fmt_curr(u[10])}\n\n"
    text += f"{get_emoji('joined_grid')} <b>Joined Grid:</b> {u[7]}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Redeem Promo Code",
            callback_data="redeem_coupon",
            icon_custom_emoji_id=get_emoji_icon('redeem_icon'),
            style="success"
        )],
        [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "redeem_coupon")
async def redeem_coupon_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🎟 <b>Please enter your VIP / Promo redeem code below:</b>", reply_markup=back_kb("menu_profile"), parse_mode='HTML')
    await state.set_state(UserStates.wait_for_redeem)

@dp.message(UserStates.wait_for_redeem)
async def process_redeem(m: Message, state: FSMContext):
    code = m.text.strip().upper()
    user_id = m.from_user.id
    if db_query("SELECT * FROM redeemed WHERE user_id=? AND code=?", (user_id, code), fetchone=True):
        await m.answer("❌ Anti-Fraud Alert: You already redeemed this unique code!", reply_markup=main_menu_kb(m.from_user.id), parse_mode='HTML')
        await state.clear()
        return
    coupon = db_query("SELECT amount, uses_left FROM coupons WHERE code=?", (code,), fetchone=True)
    if not coupon: await m.answer("❌ Invalid or Expired Code!", reply_markup=main_menu_kb(m.from_user.id), parse_mode='HTML')
    elif coupon[1] <= 0: await m.answer("❌ This code's usage limit has been fully claimed by other users.", reply_markup=main_menu_kb(m.from_user.id), parse_mode='HTML')
    else:
        db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (coupon[0], user_id))
        db_query("UPDATE coupons SET uses_left = uses_left - 1 WHERE code=?", (code,))
        db_query("INSERT INTO redeemed (user_id, code) VALUES (?, ?)", (user_id, code))
        log_activity(user_id, "PROMO_REDEEMED", f"Code: {code}, Amount: {coupon[0]}")
        await m.answer(f"🎉 <b>Success!</b>\nSafely added {fmt_curr(coupon[0])} to your balance!", reply_markup=main_menu_kb(m.from_user.id), parse_mode='HTML')
        try:
            user_info = db_query("SELECT first_name FROM users WHERE user_id=?", (user_id,), fetchone=True)
            uname = user_info[0] if user_info else "Unknown User"
            await notify_admins( f"🎟 <b>PROMO CODE REDEEMED!</b>\n👤 User: {uname} (<code>{user_id}</code>)\n🔖 Code: <b>{code}</b>\n💵 Amount: {fmt_curr(coupon[0])}", parse_mode='HTML')
        except Exception: pass
    await state.clear()

@dp.callback_query(F.data == "menu_referral")
async def show_referral(call: CallbackQuery):
    u = db_query("SELECT referrals_count, referral_earned FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{call.from_user.id}"
    text = (f"{get_emoji('referral')} <b><u>AFFILIATE PROGRAM</u></b> {get_emoji('referral')}\n\n✅ <b>Status:</b> ACTIVE\n💰 Earn <b>2% flat commission</b> on every successful purchase made by your referred friends!\n\n📊 <b>YOUR STATS:</b>\n👥 Total Invited: {u[0]}\n💵 Life-time Earned: {fmt_curr(u[1])}\n\n🔗 <b>Your Invite Link:</b>\n<code>{ref_link}</code>\n\n<i>Simply copy and share this link to start earning!</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

# ==============================================================================
# 15. LUDO / DICE SPIN
# ==============================================================================
@dp.callback_query(F.data == "menu_spin_landing")
async def lucky_spin_landing(call: CallbackQuery):
    status_check = db_query("SELECT value FROM settings WHERE key='spin_status'", fetchone=True)
    spin_status = status_check[0] if status_check else "ON"
    if spin_status == "OFF": return await call.answer("⚠️ Lucky Ludo Spin is currently disabled by Admin.", show_alert=True)
    await call.message.edit_text(f"{get_emoji('ludo_spin')} <b><u>— LUDO SPIN —</u></b> {get_emoji('ludo_spin')}\n\nTest your luck! You can spin once every 24 hours.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Spin Dice Now!", callback_data="execute_spin", icon_custom_emoji_id=get_emoji_icon("ludo_spin"), style="success")], 
        [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ]), parse_mode='HTML')

@dp.callback_query(F.data == "execute_spin")
async def execute_spin(call: CallbackQuery):
    status_check = db_query("SELECT value FROM settings WHERE key='spin_status'", fetchone=True)
    if status_check and status_check[0] == "OFF": return await call.answer("⚠️ Lucky Spin is disabled.", show_alert=True)
    u = db_query("SELECT last_spin, balance, is_vip FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    now = datetime.now()
    if u[0] and now < datetime.strptime(u[0], "%Y-%m-%d %H:%M:%S") + timedelta(hours=24):
        return await call.message.edit_text("❌ <b>Cooldown Active!</b>\nYou already played today. Come back tomorrow.", reply_markup=back_kb(), parse_mode='HTML')
    await call.message.delete()
    dice_msg = await bot.send_dice(chat_id=call.message.chat.id, emoji="🎲")
    await asyncio.sleep(SPIN_DELAY_SECONDS) 
    dice_val = dice_msg.dice.value
    limit_check = db_query("SELECT value FROM settings WHERE key='daily_spin_limit'", fetchone=True)
    limit = float(limit_check[0]) if limit_check else 50.0
    rewards_db = db_query("SELECT amount FROM spin_rewards WHERE amount <= ?", (limit,), fetchall=True)
    rewards_list = [r[0] for r in rewards_db] if rewards_db else [0.0]
    reward = random.choice(rewards_list)
    if bool(u[2]) and reward > 0: reward = reward * 2.0
    new_bal = u[1] + reward
    db_query("UPDATE users SET balance=?, last_spin=? WHERE user_id=?", (new_bal, now.strftime("%Y-%m-%d %H:%M:%S"), call.from_user.id))
    log_activity(call.from_user.id, "PLAYED_SPIN", f"Reward: {reward}, Dice: {dice_val}")
    msg = get_ui_text("lucky_dice_result", dice_value=dice_val, won_amount=fmt_curr(reward), new_balance=fmt_curr(new_bal))
    if bool(u[2]) and reward > 0: msg += "\n\n<i>🌟 VIP Bonus: 2x Multiplier Applied!</i>"
    await dice_msg.reply(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📚 BACK TO MENU", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="success")]]), parse_mode='HTML')

@dp.message(UserStates.custom_amount_input)
async def process_custom_amount(m:Message,state:FSMContext):
    d=await state.get_data()
    try: amount=float((m.text or '').replace(',','')); assert amount>=10
    except: return await m.answer('❌ Enter a valid amount of at least ₹10.')
    await state.clear()
    if d.get('payment_gateway')=='binance': return await create_binance_order(m.from_user.id,amount,m)
    await m.answer('Use Add Balance again for custom FamPay amount.',reply_markup=main_menu_kb(m.from_user.id))

# ==============================================================================
# 16. TUTORIALS & SUPPORT
# ==============================================================================
def _youtube_course_price() -> float:
    try:
        return max(0.0, float(get_setting("youtube_course_price", "99.0")))
    except (TypeError, ValueError):
        return 99.0


def _normalize_course_contact(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("@") and re.fullmatch(r"@[A-Za-z0-9_]{4,64}", value):
        value = f"https://t.me/{value[1:]}"
    return value


def _course_has_access(user_id: int) -> bool:
    return bool(db_query(
        "SELECT user_id FROM youtube_course_access WHERE user_id=?",
        (user_id,),
        fetchone=True,
    ))


def _course_keyboard(lessons: list, video_link: Optional[str], contact_link: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for index, lesson in enumerate(lessons, start=1):
        lesson_id, title, url, video_file_id = lesson
        label = f"▶️ Lesson {index}: {str(title)[:40]}"
        if video_file_id:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"course_video_{lesson_id}",
                    icon_custom_emoji_id=get_emoji_icon("tutorial"),
                    style="success",
                )
            ])
        elif url:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text=label,
                    url=url,
                    icon_custom_emoji_id=get_emoji_icon("tutorial"),
                    style="success",
                )
            ])
    if video_link:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text="📺 Open Course Playlist",
                url=video_link,
                icon_custom_emoji_id=get_emoji_icon("tutorial"),
                style="primary",
            )
        ])
    if contact_link:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text="💬 Course Contact / Support",
                url=contact_link,
                icon_custom_emoji_id=get_emoji_icon("support"),
                style="primary",
            )
        ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(
            text="BACK",
            callback_data="back_main",
            icon_custom_emoji_id=get_emoji_icon("back"),
            style="danger",
        )
    ])
    return kb


@dp.callback_query(F.data == "menu_how_to")
async def tutorial_system(call: CallbackQuery):
    price = _youtube_course_price()
    paid_access = is_admin(call.from_user.id) or _course_has_access(call.from_user.id)

    if price > 0 and not paid_access:
        user = db_query("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
        balance = float(user[0] or 0.0) if user else 0.0
        contact_link = _normalize_course_contact(get_setting("youtube_course_contact", ""))
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"🎓 Buy Course — {fmt_curr(price)}",
                callback_data="course_buy",
                icon_custom_emoji_id=get_emoji_icon("money_icon"),
                style="success",
            )],
            [InlineKeyboardButton(
                text=f"💰 Add Balance (Current: {fmt_curr(balance)})",
                callback_data="menu_add_balance",
                icon_custom_emoji_id=get_emoji_icon("add_balance"),
                style="primary",
            )],
        ])
        if contact_link:
            kb.inline_keyboard.append([
                InlineKeyboardButton(
                    text="💬 Contact Admin",
                    url=contact_link,
                    icon_custom_emoji_id=get_emoji_icon("support"),
                    style="primary",
                )
            ])
        kb.inline_keyboard.append([
            InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")
        ])
        await call.message.edit_text(
            f"{get_emoji('tutorial')} <b><u>— PAID YOUTUBE COURSE —</u></b> {get_emoji('tutorial')}\n\n"
            f"Complete lessons, videos and setup guidance पाने के लिए पहले course access खरीदें.\n\n"
            f"💳 <b>Course Fee:</b> {fmt_curr(price)}\n"
            f"👛 <b>Your Balance:</b> {fmt_curr(balance)}\n\n"
            "Payment existing wallet balance से होगा. Balance कम हो तो पहले Add Balance से payment करें.",
            reply_markup=kb,
            parse_mode="HTML",
        )
        return

    video_link_query = db_query("SELECT value FROM settings WHERE key='how_to_video'", fetchone=True)
    video_link = video_link_query[0] if video_link_query and video_link_query[0] != "None" else None
    lessons = db_query(
        "SELECT id, title, url, video_file_id FROM youtube_lessons "
        "WHERE is_active=1 ORDER BY sort_order ASC, id ASC LIMIT 50",
        fetchall=True,
    ) or []
    contact_link = _normalize_course_contact(get_setting("youtube_course_contact", ""))
    text = (
        f"{get_emoji('tutorial')} <b><u>— YOUTUBE COURSE —</u></b> {get_emoji('tutorial')}\n\n"
        "✅ <b>Course access active</b>\n"
        "Open each lesson in order. Video lessons uploaded by admin will open directly here."
    )
    if not lessons and not video_link:
        text += "\n\n<i>Course lessons will be available soon.</i>"
    await call.message.edit_text(
        text,
        reply_markup=_course_keyboard(lessons, video_link, contact_link),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "course_buy")
async def buy_youtube_course(call: CallbackQuery):
    if is_admin(call.from_user.id) or _course_has_access(call.from_user.id):
        return await tutorial_system(call)

    price = _youtube_course_price()
    user = db_query("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    balance = float(user[0] or 0.0) if user else 0.0
    if not user:
        return await call.answer("Account not found. Please use /start again.", show_alert=True)
    if balance < price:
        return await call.answer(
            f"Balance कम है. Course के लिए {fmt_curr(price - balance)} और चाहिए.",
            show_alert=True,
        )

    db_query(
        "UPDATE users SET balance=balance-?, spent=spent+? WHERE user_id=? AND balance>=?",
        (price, price, call.from_user.id, price),
    )
    db_query(
        "INSERT OR IGNORE INTO youtube_course_access (user_id, amount_paid, purchased_at) VALUES (?, ?, ?)",
        (call.from_user.id, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    if not _course_has_access(call.from_user.id):
        db_query("UPDATE users SET balance=balance+?, spent=spent-? WHERE user_id=?", (price, price, call.from_user.id))
        return await call.answer("Payment save नहीं हो पाया. आपका balance सुरक्षित है.", show_alert=True)

    log_activity(call.from_user.id, "YOUTUBE_COURSE_PURCHASE", f"Paid: {price}")
    await call.answer("✅ Payment successful. Course unlocked!", show_alert=True)
    await tutorial_system(call)


@dp.callback_query(F.data.startswith("course_video_"))
async def open_course_video(call: CallbackQuery):
    try:
        lesson_id = int(call.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        return await call.answer("Invalid lesson.", show_alert=True)
    if not is_admin(call.from_user.id) and not _course_has_access(call.from_user.id):
        return await call.answer("पहले course खरीदें.", show_alert=True)
    lesson = db_query(
        "SELECT title, video_file_id FROM youtube_lessons WHERE id=? AND is_active=1",
        (lesson_id,),
        fetchone=True,
    )
    if not lesson or not lesson[1]:
        return await call.answer("Video unavailable.", show_alert=True)
    await call.answer()
    await bot.send_video(
        chat_id=call.from_user.id,
        video=lesson[1],
        caption=f"🎓 <b>{escape(str(lesson[0]))}</b>",
        parse_mode="HTML",
    )

def _valid_support_url(url: str, kind: str) -> bool:
    """Validate support URLs so one bad/empty setting cannot break the Support menu."""
    if not url:
        return False
    url = url.strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        return False
    if kind == "telegram":
        return "t.me/" in url or "telegram.me/" in url
    if kind == "whatsapp":
        return "wa.me/" in url or "whatsapp.com/" in url
    return True

@dp.callback_query(F.data == "menu_support")
async def support_center(call: CallbackQuery):
    await call.answer()
    telegram_link = get_setting("support_telegram", "").strip()
    whatsapp_link = get_setting("support_whatsapp", "").strip()
    rows = []
    if _valid_support_url(telegram_link, "telegram"):
        rows.append([InlineKeyboardButton(text="Contact on Telegram", url=telegram_link, icon_custom_emoji_id=get_emoji_icon("telegram"), style="primary")])
    if _valid_support_url(whatsapp_link, "whatsapp"):
        rows.append([InlineKeyboardButton(text="Contact on WhatsApp", url=whatsapp_link, icon_custom_emoji_id=get_emoji_icon("whatsapp"), style="primary")])
    rows.append([InlineKeyboardButton(text="🤖 Ask AI Support", callback_data="menu_ai_support", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="success")])
    rows.append([
        InlineKeyboardButton(text="🎫 Open New Ticket", callback_data="open_ticket", icon_custom_emoji_id=get_emoji_icon("support"), style="success"),
        InlineKeyboardButton(text="📋 My Open Tickets", callback_data="my_tickets", icon_custom_emoji_id=get_emoji_icon("history"), style="success")
    ])
    rows.append([InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text(
        f"{get_emoji('telegram')}{get_emoji('whatsapp')} <b><u>— PREMIUM SUPPORT CENTER —</u></b>\n\n"
        "Contact us via Telegram or WhatsApp for instant help, or open a support ticket for admin assistance.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode='HTML'
    )

@dp.callback_query(F.data == "my_tickets")
async def view_my_tickets(call: CallbackQuery):
    tickets = db_query("SELECT id, message, status, created_at FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 5", (call.from_user.id,), fetchall=True)
    if not tickets: return await call.message.edit_text("📋 You do not have any active or previous support tickets.", reply_markup=back_kb("menu_support"), parse_mode='HTML')
    text = "📋 <b><u>— Your Recent Tickets —</u></b> 📋\n\n"
    for t in tickets:
        status_icon = "🟢" if t[2] == 'Open' else "🔴"
        text += f"🎫 <b>Ticket #{t[0]}</b> | Status: {status_icon} <b>{t[2]}</b>\n📅 <i>{t[3]}</i>\n📝 <i>{t[1][:80]}...</i>\n\n"
    await call.message.edit_text(text, reply_markup=back_kb("menu_support"), parse_mode='HTML')

@dp.callback_query(F.data == "open_ticket")
async def open_ticket_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 <b>Please type your issue/message below in detail:</b>", reply_markup=back_kb("menu_support"), parse_mode='HTML')
    await state.set_state(UserStates.wait_for_ticket)

@dp.message(UserStates.wait_for_ticket)
async def process_ticket(m: Message, state: FSMContext):
    db_query("INSERT INTO tickets (user_id, message, created_at) VALUES (?, ?, ?)", (m.from_user.id, m.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    await m.answer("✅ <b>Ticket Submitted Successfully!</b> Admins will reply soon.", reply_markup=main_menu_kb(m.from_user.id), parse_mode='HTML')
    try: await notify_admins( f"🚨 <b>NEW SUPPORT TICKET</b>\nFrom: <code>{m.from_user.id}</code>\nMsg: {m.text}", parse_mode='HTML')
    except: pass
    log_activity(m.from_user.id, "OPENED_TICKET")
    await state.clear()


# ==============================================================================
# 16B. AI SUPPORT ASSISTANT
# ===============================================================================
def ai_support_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Ask AI Again", callback_data="menu_ai_support", style="primary")],
        [InlineKeyboardButton(text="🚨 Contact Admin", callback_data="ai_escalate", style="danger")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="back_main", style="success")],
    ])

def ai_setup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Set AI Endpoint", callback_data="ai_set_endpoint", style="primary")],
        [InlineKeyboardButton(text="🔑 Set AI API Key", callback_data="ai_set_key", style="primary")],
        [InlineKeyboardButton(text="🧠 Set AI Model", callback_data="ai_set_model", style="primary")],
        [InlineKeyboardButton(text="🟢/🔴 Toggle AI", callback_data="ai_toggle", style="success")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel_back", style="danger")],
    ])

def _ai_local_answer(question: str, user_id: int) -> tuple[str, bool]:
    """Fast local support brain. Handles common Hindi/Hinglish/English queries."""
    raw=(question or '').strip()
    q=re.sub(r"\s+", " ", raw.lower())
    aliases={'kese':'kaise','kr':'kar','krna':'karna','kru':'karu','btao':'batao','nai':'nahi','chal':'chalta','krta':'karta'}
    q=' '.join(aliases.get(w,w) for w in q.split())
    u=db_query("SELECT balance,orders_count,is_vip,is_reseller FROM users WHERE user_id=?",(user_id,),fetchone=True)
    balance=float(u[0]) if u else 0.0; orders=int(u[1]) if u else 0
    vip=bool(u[2]) if u else False; reseller=bool(u[3]) if u else False
    fam=bool(get_setting('fampay_api_key','').strip())
    binance=bool(get_setting('binance_pay_api_key','').strip() and get_setting('binance_pay_secret_key','').strip() and get_setting('binance_pay_certificate_sn','').strip())
    slots=get_api_slots(); api_count=sum(1 for r in slots if len(r)>7 and r[7] and r[2])
    issue_words=('error','issue','problem','failed','fail','not working','working nahi','kaam nahi','काम नहीं','दिक्कत','इश्यू','एरर','फेल','कट गया','नहीं आया','not received','not credited','refund','रिफंड','stuck','अटक','declined','rejected','payment problem','buy problem')
    issue=any(w in q for w in issue_words)
    if any(w in q for w in ('bot kaise','bot karu','bot use','bot chalta','bot use kar','bot kese','bot kya','how to use bot','bot कैसे','बोट कैसे','बोट यूज़')):
        return (f"🤖 <b>Bot Use — Quick Guide</b>\n\n1️⃣ <b>Product Store</b> → panel चुनें।\n2️⃣ Package/Validity चुनें।\n3️⃣ <b>Buy</b> दबाएँ।\n4️⃣ Balance कम हो तो <b>Add Balance</b> से payment करें।\n5️⃣ Order complete होने पर key/APK details मिलेंगी।\n\n💰 Balance: <b>{fmt_curr(balance)}</b>\n📦 Orders: <b>{orders}</b>\n\n❓ किसी step पर error है तो exact message भेजें—मैं reason और next step बताऊँगा।", False)
    if any(w in q for w in ('multi api','multiple api','multi-api','api setup','api kaise','api कैसे','api add','api paste','api code')):
        return (f"🔗 <b>Multi-API Quick Setup</b>\n\n1️⃣ Admin → <b>Multi API Manager</b>\n2️⃣ Slot 1–5 में API add करें।\n3️⃣ cURL / Python requests / aiohttp code paste करें।\n4️⃣ AI parser URL, method, headers और body पहचानता है।\n5️⃣ Enabled APIs priority/failover order में चलती हैं।\n\n🟢 Active API slots: <b>{api_count}/5</b>", False)
    if any(w in q for w in ('binance','binance pay','बाइनेंस','बिनेंस')):
        return (f"🟡 <b>Binance Pay Help</b>\n\nAdd Balance → Binance Pay → amount → Pay → Verify Payment.\n\n{'🟢 Gateway configured है।' if binance else '🟠 Gateway अभी configured नहीं है; admin setup required है।'}\n\nअगर पैसा कट गया लेकिन balance नहीं आया, order ID / screenshot / exact error भेजें।", issue)
    if any(w in q for w in ('fampay','upi','फैम्पे','upi payment','फैमपे')):
        return (f"💳 <b>FamPay / UPI Help</b>\n\nAdd Balance → FamPay/UPI → payment complete → Verify.\n\n{'🟢 Gateway configured है।' if fam else '🟠 Gateway configured नहीं दिख रहा; admin setup required है।'}\n\nPayment कट गया/verify नहीं हुआ हो तो reference details भेजें।", issue)
    if any(w in q for w in ('buy','purchase','खरीद','खरीदना','कैसे खरीद','how to buy','product lena','product chahiye')):
        return (f"🛒 <b>Purchase Help</b>\n\n1️⃣ Wallet में balance रखें।\n2️⃣ Product Store खोलें।\n3️⃣ Root / Non-Root / iPhone / PC category चुनें।\n4️⃣ Product + validity चुनें।\n5️⃣ Buy दबाएँ।\n\n💰 Balance: <b>{fmt_curr(balance)}</b>\n📦 Orders: <b>{orders}</b>\n\nPurchase fail है तो exact error भेजें।", issue)
    if any(w in q for w in ('balance','wallet','बैलेंस','वॉलेट','kitna balance')):
        status=('🌟 VIP active' if vip else '') + (' 👑 Reseller active' if reseller else '')
        return (f"💰 <b>Wallet Status</b>\n\nCurrent balance: <b>{fmt_curr(balance)}</b>\nTotal orders: <b>{orders}</b>\n{status or '👤 Regular account'}", False)
    if any(w in q for w in ('setup','configure','configuration','सेटअप','सेट करना','kaise set','कैसे सेट','admin setup','bot setup')):
        return ("⚙️ <b>Quick Setup Assistant</b>\n\nमैं इन setups में guide कर सकता हूँ:\n• 📦 Product setup\n• 🔗 Multi-API / API Paste\n• 💳 FamPay / UPI\n• 🟡 Binance Pay\n• 🧠 AI Support\n• 👥 User / Reseller / VIP management\n\nबस लिखें: <b>Binance setup</b>, <b>API code paste</b>, <b>product setup</b> या अपना exact issue।", False)
    if any(w in q for w in ('product','products','product add','प्रोडक्ट','प्रोडक्ट जोड़','panel add')):
        return ("📦 <b>Product Setup</b>\n\nAdmin → Add Product → Category → Panel Name → Product Name → Validity → Device Limit → Price → delivery/API details → Save.\n\nRoot और Non-Root products अलग categories में manage किए जा सकते हैं।", False)
    if any(w in q for w in ('reseller','रीसेलर','resell')):
        return ("👑 <b>Reseller Setup</b>\n\nAdmin → Reseller Management से reseller status, setup fee और minimum balance manage करें। User Control Panel से individual reseller status भी बदला जा सकता है।", False)
    if any(w in q for w in ('vip','वीआईपी')):
        return (f"🌟 <b>VIP Help</b>\n\nCurrent status: <b>{'Active' if vip else 'Not Active'}</b>. VIP system admin toggle से control होता है।", False)
    if any(w in q for w in ('admin','management','manage','मैनेज','मैनेजमेंट')):
        return ("🛠️ <b>Management Help</b>\n\nAdmin Panel में User Control और Advanced Management से users, products, Root/Non-Root categories, VIP/Reseller status, balance और AI escalations manage किए जा सकते हैं।", False)
    if any(w in q for w in ('tutorial','guide','ट्यूटोरियल','गाइड')):
        return ("📚 <b>Tutorial</b>\n\nAdd Balance → Product Store → Category → Package → Buy.\nPayment या purchase में issue हो तो exact error भेजें; मैं troubleshooting steps दूँगा।", False)
    if issue:
        return ("🚨 <b>Issue detected</b>\n\nमुझे भेजें:\n1️⃣ Exact error/message\n2️⃣ Order/payment ID (अगर है)\n3️⃣ आपने कौन सा step किया था\n\nफिर मैं कारण, next step और जरूरत पड़ने पर admin escalation कर दूँगा।", True)
    return ("🤖 <b>AI Support Ready</b>\n\nHindi, Hinglish या English में normal तरीके से पूछें।\n\nउदाहरण:\n• bot kese use karu\n• binance payment fail hai\n• multi api setup kaise karu\n• product add kaise karu\n• mera payment cut gaya\n\nआपका सवाल लिखें—मैं relevant answer दूँगा।", False)

async def ai_remote_answer(question: str, user_id: int, history=None) -> Optional[str]:
    endpoint=get_setting('ai_endpoint','').strip(); key=get_setting('ai_api_key','').strip()
    model=get_setting('ai_model','gpt-4o-mini').strip() or 'gpt-4o-mini'
    if not endpoint or not key or get_setting('ai_support_enabled','ON').upper()!='ON': return None
    endpoint=endpoint.rstrip('/')
    if not endpoint.endswith('/chat/completions'): endpoint += '/chat/completions'
    system=("You are an advanced customer-support and setup assistant for a Telegram digital store bot. "
            "Answer in Hindi/Hinglish/English matching the user. Give direct, practical, step-by-step answers. "
            "Support bot usage, product purchase, payment troubleshooting, Multi-API, API code paste, Binance Pay, FamPay/UPI, AI setup, reseller/VIP and admin-management concepts. "
            "Never reveal secrets, tokens, API keys, admin IDs or internal credentials. Never claim payment success without database confirmation. "
            "When a problem cannot be safely resolved, tell the user to use Contact Admin.")
    messages=[{'role':'system','content':system}]
    for item in (history or [])[-6:]:
        if isinstance(item,dict) and item.get('role') in ('user','assistant') and item.get('content'):
            messages.append({'role':item['role'],'content':str(item['content'])[:1500]})
    messages.append({'role':'user','content':question[:3000]})
    payload={'model':model,'messages':messages,'temperature':0.2,'max_tokens':700}
    try:
        timeout=aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(endpoint,json=payload,headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'}) as resp:
                raw=await resp.text()
                if resp.status>=400:
                    logger.warning('AI endpoint HTTP %s: %s',resp.status,raw[:300]); return None
                data=json.loads(raw)
                return (((data.get('choices') or [{}])[0].get('message') or {}).get('content') or '').strip() or None
    except Exception as e:
        logger.warning('AI remote fallback: %s',e); return None

async def _ai_issue_escalate(user_id: int, question: str, answer: str) -> bool:
    now=int(time.time())
    recent=db_query("SELECT id FROM ai_escalations WHERE user_id=? AND created_at>? ORDER BY id DESC LIMIT 1",(user_id,now-600),fetchone=True)
    if recent: return False
    db_query("INSERT INTO ai_escalations(user_id,question,created_at,status) VALUES(?,?,?,?)",(user_id,question,now,'OPEN'))
    safe_q=escape(question[:1500]); safe_a=escape(answer[:1500])
    await notify_admins(f"🚨 <b>AI SUPPORT ESCALATION</b>\n👤 User: <code>{user_id}</code>\n\n<b>User issue:</b>\n{safe_q}\n\n<b>AI response:</b>\n{safe_a}",parse_mode='HTML')
    return True

async def _safe_ai_screen(call: CallbackQuery, text: str, reply_markup=None):
    """Render AI support without allowing Telegram formatting/edit errors to break the bot."""
    try:
        await call.answer()
    except Exception:
        pass
    try:
        # AI text is deliberately sent as plain text: remote AI output may contain
        # arbitrary < > characters and must never cause Telegram HTML parse errors.
        await call.message.edit_text(text, reply_markup=reply_markup, parse_mode=None)
    except Exception as edit_err:
        logger.warning('AI screen edit failed, sending a new message: %s', edit_err)
        try:
            await call.message.answer(text, reply_markup=reply_markup, parse_mode=None)
        except Exception as send_err:
            logger.error('AI screen send failed: %s', send_err)
            return False
    return True

@dp.callback_query(F.data=='menu_ai_support')
async def menu_ai_support(call: CallbackQuery, state: FSMContext):
    if get_setting('ai_support_enabled','ON').upper()!='ON':
        try: await call.answer('AI Support is temporarily disabled.',show_alert=True)
        except Exception: pass
        return
    await state.set_state(UserStates.ai_chat)
    await _safe_ai_screen(call, "🤖 AI SUPPORT\n\nआप bot, setup, payment, purchase, Multi-API, Binance Pay या किसी भी issue के बारे में पूछ सकते हैं।\n\nअपना सवाल भेजें 👇", ai_support_kb())

@dp.message(UserStates.ai_chat)
async def ai_chat_message(m: Message, state: FSMContext):
    if not m.text:
        return await m.answer('कृपया अपना सवाल text में भेजें।',reply_markup=ai_support_kb())
    q=m.text.strip()
    if q.lower() in ('/exit','exit','back','बैक'):
        await state.clear(); return await m.answer('AI Support बंद कर दिया गया।',reply_markup=main_menu_kb(m.from_user.id))
    data=await state.get_data(); history=data.get('ai_history',[])
    local,issue=_ai_local_answer(q,m.from_user.id)
    remote=await ai_remote_answer(q,m.from_user.id,history)
    answer=remote or local
    history=(history+[{'role':'user','content':q},{'role':'assistant','content':answer}])[-10:]
    await state.update_data(last_ai_question=q,ai_history=history)
    explicit_admin=any(x in q.lower() for x in ('admin se baat','contact admin','admin help','एडमिन से','एडमिन को'))
    if issue or explicit_admin:
        escalated=await _ai_issue_escalate(m.from_user.id,q,answer)
        if escalated: answer += "\n\n📨 Admin को आपकी issue notification भेज दी गई है।"
    await m.answer(answer,reply_markup=ai_support_kb(),parse_mode=None)

@dp.callback_query(F.data=='ai_escalate')
async def ai_escalate(call: CallbackQuery, state: FSMContext):
    d=await state.get_data(); q=d.get('last_ai_question','')
    if not q:
        q='User requested admin assistance from AI Support.'
    sent=await _ai_issue_escalate(call.from_user.id,q,'User requested direct admin assistance.')
    await call.answer('✅ Admin notified.' if sent else 'ℹ️ Admin was already notified recently.',show_alert=True)

# Keep the last AI question for the escalation button.
@dp.callback_query(F.data=='admin_ai_support')
async def admin_ai_support(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    enabled=get_setting('ai_support_enabled','ON')
    endpoint=get_setting('ai_endpoint','')
    model=get_setting('ai_model','gpt-4o-mini')
    text=(f"🧠 <b>AI SUPPORT SETUP</b>\n\nStatus: <b>{'🟢 ON' if enabled.upper()=='ON' else '🔴 OFF'}</b>\n"
          f"Remote endpoint: <code>{escape(endpoint or 'Not configured')}</code>\nModel: <code>{escape(model)}</code>\n\n"
          "Local smart support हमेशा fallback के रूप में चलता है। Remote AI optional है।")
    await call.message.edit_text(text,reply_markup=ai_setup_kb(),parse_mode='HTML')

@dp.callback_query(F.data=='ai_set_endpoint')
async def ai_set_endpoint(call: CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text('🌐 Send OpenAI-compatible chat endpoint. Example: <code>https://your-host/v1</code>\n(Leave empty to use local AI only.)',reply_markup=admin_back_kb(),parse_mode='HTML')
    await state.set_state(AdminStates.ai_setup); await state.update_data(ai_step='endpoint')

@dp.callback_query(F.data=='ai_set_key')
async def ai_set_key(call: CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text('🔑 Send AI API key. Send <code>NONE</code> to clear it.',reply_markup=admin_back_kb(),parse_mode='HTML')
    await state.set_state(AdminStates.ai_setup); await state.update_data(ai_step='key')

@dp.callback_query(F.data=='ai_set_model')
async def ai_set_model(call: CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text('🧠 Send model name, e.g. <code>gpt-4o-mini</code>.',reply_markup=admin_back_kb(),parse_mode='HTML')
    await state.set_state(AdminStates.ai_setup); await state.update_data(ai_step='model')

@dp.callback_query(F.data=='ai_toggle')
async def ai_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cur=get_setting('ai_support_enabled','ON').upper(); new='OFF' if cur=='ON' else 'ON'
    set_setting('ai_support_enabled',new)
    await call.answer(f'AI Support {new}.',show_alert=True)
    await admin_ai_support(call,FSMContext) if False else call.message.edit_text('🧠 <b>AI Support</b>\n\nStatus updated. Open setup again to configure remote AI.',reply_markup=ai_setup_kb(),parse_mode='HTML')

@dp.message(AdminStates.ai_setup)
async def save_ai_setup(m: Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    d=await state.get_data(); step=d.get('ai_step'); v=(m.text or '').strip()
    if step=='endpoint':
        if v.upper() in ('NONE','CLEAR',''):
            set_setting('ai_endpoint','')
        elif not v.startswith(('http://','https://')):
            return await m.answer('❌ Endpoint must start with http:// or https://')
        else: set_setting('ai_endpoint',v.rstrip('/'))
    elif step=='key': set_setting('ai_api_key','' if v.upper() in ('NONE','CLEAR') else v)
    elif step=='model': set_setting('ai_model',v or 'gpt-4o-mini')
    await state.clear(); await m.answer('✅ AI setup updated. Local fallback remains active.',reply_markup=admin_kb(),parse_mode='HTML')

# ==============================================================================
# 17. ADMIN PANEL
# ==============================================================================
@dp.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    await message.answer("⚙️ <b>Advanced Admin Terminal</b>\n<i>Authorized Access Granted. Use the buttons below.</i>", reply_markup=admin_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_panel_back")
async def back_to_admin(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("⚙️ <b>Advanced Admin Terminal</b>\n<i>Authorized Access Granted. Use the buttons below.</i>", reply_markup=admin_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_toggle_vip_sys")
async def toggle_vip_sys(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    res = db_query("SELECT value FROM settings WHERE key='vip_status'", fetchone=True)
    current = res[0] if res else 'OFF'
    new_status = 'ON' if current == 'OFF' else 'OFF'
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('vip_status', ?)", (new_status,))
    await call.message.edit_reply_markup(reply_markup=admin_kb())

@dp.callback_query(F.data == "admin_user_control_start")
async def admin_user_control_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Download Full User List", callback_data="admin_download_userlist", icon_custom_emoji_id=get_emoji_icon("download"), style="success")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text("💻 <b>User Control Terminal</b>\n\n✏️ Enter the <b>User ID</b> or <b>@Username</b> you want to investigate or manage:\n\n👇 <b>OR</b> download the full user CSV format list:", reply_markup=kb, parse_mode='HTML')
    await state.set_state(AdminStates.manage_target_user)

@dp.callback_query(F.data == "admin_download_userlist")
async def admin_download_userlist(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    users = db_query("SELECT username, user_id, phone, balance, orders_count, is_vip, is_reseller FROM users", fetchall=True)
    if not users: return await call.answer("❌ No users found in the database.", show_alert=True)
    file_content = "FULL DATABASE DUMP\n" + "="*100 + "\n"
    for u in users:
        uname = u[0] if u[0] else "No_Username"
        uid = u[1]
        phone = u[2] if u[2] else "No_Phone"
        bal = u[3]
        orders = u[4]
        vip_status = "YES" if u[5] else "NO"
        res_status = "YES" if u[6] else "NO"
        file_content += f"UID: {uid} | UNAME: {uname} | PHONE: {phone} | BAL: ₹{bal:.2f} | BUY: {orders} | VIP: {vip_status} | RES: {res_status}\n"
    doc = BufferedInputFile(file_content.encode('utf-8'), filename=f"DB_{datetime.now().strftime('%Y%m%d')}.txt")
    await call.message.answer_document(document=doc, caption="📋 <b>Database export complete.</b>", parse_mode='HTML')
    await call.answer()

@dp.message(AdminStates.manage_target_user)
async def process_user_lookup(m: Message, state: FSMContext):
    target = m.text.strip()
    if target.startswith('@'): target = target[1:]
    loader_msg = await hacker_loading(m, "Querying User Database")
    user_q = db_query("SELECT user_id, first_name, username, balance, is_reseller, orders_count, spent, joined_date, is_banned, warnings, is_vip FROM users WHERE user_id=? OR username=? COLLATE NOCASE", (target, target), fetchone=True)
    if not user_q: return await loader_msg.edit_text("❌ Target not found in the grid. Check ID/Username syntax.", reply_markup=admin_back_kb(), parse_mode='HTML')
    u_id, u_name, u_user, bal, is_res, orders, spent, joined, is_banned, warnings, is_vip = user_q
    await state.update_data(target_u_id=u_id)
    status_emoji = "🔴 BANNED" if is_banned else "🟢 ACTIVE"
    tags = []
    if is_res: tags.append("👑 Reseller")
    if is_vip: tags.append("🌟 VIP")
    type_str = " | ".join(tags) if tags else "👤 Regular"
    text = (f"🛡 <b><u>USER CONTROL TERMINAL</u></b> 🛡\n━━━━━━━━━━━━━━━━━━\n📛 <b>Name:</b> {u_name} (@{u_user})\n🆔 <b>ID:</b> <code>{u_id}</code>\n📊 <b>Status:</b> {status_emoji}\n🔰 <b>Type:</b> {type_str}\n⚠️ <b>Warnings Issued:</b> {warnings}\n━━━━━━━━━━━━━━━━━━\n💰 <b>Wallet Balance:</b> {fmt_curr(bal)}\n📦 <b>Orders:</b> {orders} | 💸 <b>Total Spent:</b> {fmt_curr(spent)}\n📅 <b>Joined:</b> {joined}")
    ban_btn_text = "Unban ✅" if is_banned else "Ban 🚫"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Add Funds ➕", callback_data=f"usrctrl_add_{u_id}", icon_custom_emoji_id=get_emoji_icon("add_balance"), style="success"), 
         InlineKeyboardButton(text="Minus Funds ➖", callback_data=f"usrctrl_min_{u_id}", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="danger")],
        [InlineKeyboardButton(text=ban_btn_text, callback_data=f"usrctrl_ban_{u_id}", icon_custom_emoji_id=get_emoji_icon("shield_icon"), style="danger"), 
         InlineKeyboardButton(text="Warn User ⚠️", callback_data=f"usrctrl_warn_{u_id}", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="danger")],
        [InlineKeyboardButton(text="Give VIP 🌟" if not is_vip else "Remove VIP 🚫", callback_data=f"usrctrl_vip_{u_id}", icon_custom_emoji_id=get_emoji_icon("vip"), style="success")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await loader_msg.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("usrctrl_"))
async def handle_user_actions(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    action = call.data.split("_")[1]
    u_id = int(call.data.split("_")[2])
    await state.update_data(target_u_id=u_id)
    if action == "ban":
        current_status = db_query("SELECT is_banned FROM users WHERE user_id=?", (u_id,), fetchone=True)[0]
        if current_status == 0:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Yes, Ban", callback_data=f"confirm_ban_{u_id}", icon_custom_emoji_id=get_emoji_icon("check_icon"), style="danger"), 
                 InlineKeyboardButton(text="❌ Cancel", callback_data="admin_user_control_start", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
            ])
            await call.message.edit_text(f"⚠️ Are you sure you want to <b>BAN</b> user <code>{u_id}</code>?", reply_markup=kb, parse_mode='HTML')
            await state.set_state(AdminStates.confirm_ban)
        else:
            db_query("UPDATE users SET is_banned=0 WHERE user_id=?", (u_id,))
            await call.answer("✅ User unbanned successfully!", show_alert=True)
            m = call.message; m.text = str(u_id); await process_user_lookup(m, state)
    elif action == "vip":
        current_status = db_query("SELECT is_vip FROM users WHERE user_id=?", (u_id,), fetchone=True)[0]
        if current_status == 1:
            db_query("UPDATE users SET is_vip=0 WHERE user_id=?", (u_id,))
            await call.answer("✅ VIP Removed!", show_alert=True)
        else:
            db_query("UPDATE users SET is_vip=1, vip_since=? WHERE user_id=?", (datetime.now().strftime("%Y-%m-%d"), u_id))
            await call.answer("✅ VIP Granted!", show_alert=True)
        m = call.message; m.text = str(u_id); await process_user_lookup(m, state)
    elif action == "add":
        await call.message.edit_text("💰 Enter the amount to <b>ADD</b> to this user's wallet:", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_add_money)
    elif action == "min":
        await call.message.edit_text("💸 Enter the amount to <b>DEDUCT</b> from this user's wallet:", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_minus_money)
    elif action == "warn":
        await call.message.edit_text("⚠️ Type the strict warning message you want to send directly to this user:", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_warning)

@dp.callback_query(F.data.startswith("confirm_ban_"))
async def confirm_ban(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    u_id = int(call.data.split("_")[2])
    db_query("UPDATE users SET is_banned=1 WHERE user_id=?", (u_id,))
    await call.answer("🔴 User has been banned!", show_alert=True)
    await state.clear()
    m = call.message; m.text = str(u_id); await process_user_lookup(m, state)

@dp.message(AdminStates.wait_for_add_money)
async def exec_add_money(m: Message, state: FSMContext):
    try:
        amt = float(m.text)
        data = await state.get_data()
        u_id = data['target_u_id']
        db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, u_id))
        await m.answer(f"✅ Successfully added {fmt_curr(amt)} to target <code>{u_id}</code>.", reply_markup=admin_kb(), parse_mode='HTML')
        try: await bot.send_message(u_id, f"💰 <b>Wallet Top-up!</b>\nAdmin has manually added {fmt_curr(amt)} to your wallet.", parse_mode='HTML')
        except: pass
        await state.clear()
    except ValueError: await m.answer("❌ Critical Error: Input must be a valid number.")

@dp.message(AdminStates.wait_for_minus_money)
async def exec_minus_money(m: Message, state: FSMContext):
    try:
        amt = float(m.text)
        data = await state.get_data()
        u_id = data['target_u_id']
        db_query("UPDATE users SET balance = balance - ? WHERE user_id=?", (amt, u_id))
        await m.answer(f"✅ Successfully deducted {fmt_curr(amt)} from target <code>{u_id}</code>.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Critical Error: Input must be a valid number.")

@dp.message(AdminStates.wait_for_warning)
async def exec_warn_user(m: Message, state: FSMContext):
    data = await state.get_data()
    u_id = data['target_u_id']
    warn_text = m.text
    db_query("UPDATE users SET warnings = warnings + 1 WHERE user_id=?", (u_id,))
    await m.answer(f"✅ Official warning dispatched to <code>{u_id}</code>.", reply_markup=admin_kb(), parse_mode='HTML')
    try: await bot.send_message(u_id, f"⚠️ <b>OFFICIAL WARNING FROM SYSTEM ADMIN:</b>\n\n{warn_text}\n\n<i>Subsequent infractions may lead to an automated grid ban.</i>", parse_mode='HTML')
    except: pass
    await state.clear()

# ==============================================================================
# 17B. ADVANCED MANAGEMENT
# ==============================================================================
def advanced_management_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 User Management", callback_data="admin_user_control_start", style="primary")],
        [InlineKeyboardButton(text="📦 All Products", callback_data="admin_manage_prods", style="primary")],
        [InlineKeyboardButton(text="📱 Root Products", callback_data="admin_manage_root_products", style="success")],
        [InlineKeyboardButton(text="📱 Non-Root Products", callback_data="admin_manage_nonroot_products", style="success")],
        [InlineKeyboardButton(text="🚨 AI Escalations", callback_data="admin_ai_escalations", style="danger")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel_back", style="danger")],
    ])

@dp.callback_query(F.data == "admin_advanced_management")
async def admin_advanced_management(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await call.message.edit_text(
        "🛠️ <b>ADVANCED MANAGEMENT</b>\n\n"
        "Users और products को safely manage करें।\n"
        "Root / Non-Root products अलग-अलग filter करके remove किए जा सकते हैं।\n"
        "AI support escalations भी यहाँ मिलेंगी।",
        reply_markup=advanced_management_kb(), parse_mode='HTML')

async def _show_category_products(call: CallbackQuery, category: str):
    if not is_admin(call.from_user.id): return
    rows=db_query("SELECT id,panel_name,name,price_inr,stock,is_active FROM products WHERE category=? ORDER BY id DESC",(category,),fetchall=True) or []
    if not rows:
        return await call.message.edit_text(f"📦 <b>{escape(category)}</b>\n\nकोई product नहीं मिला।",reply_markup=advanced_management_kb(),parse_mode='HTML')
    kb=InlineKeyboardMarkup(inline_keyboard=[])
    for pid,panel,name,price,stock,active in rows[:50]:
        label=f"{'🟢' if active else '🔴'} #{pid} {panel or name} | ₹{float(price):.0f} | Stock {stock}"
        kb.inline_keyboard.append([InlineKeyboardButton(text=label[:64],callback_data=f"admin_catprod_{pid}",style='primary')])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Back",callback_data="admin_advanced_management",style='danger')])
    await call.message.edit_text(f"📦 <b>{escape(category)}</b>\n\nProduct चुनें:",reply_markup=kb,parse_mode='HTML')

@dp.callback_query(F.data == "admin_manage_root_products")
async def admin_manage_root_products(call: CallbackQuery):
    await _show_category_products(call,"ANDROID ROOT PANEL")

@dp.callback_query(F.data == "admin_manage_nonroot_products")
async def admin_manage_nonroot_products(call: CallbackQuery):
    await _show_category_products(call,"ANDROID NON ROOT PANEL")

@dp.callback_query(F.data.startswith("admin_catprod_"))
async def admin_category_product_view(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    try: pid=int(call.data.rsplit('_',1)[1])
    except: return await call.answer('Invalid product',show_alert=True)
    row=db_query("SELECT category,panel_name,name,price_inr,stock,is_active FROM products WHERE id=?",(pid,),fetchone=True)
    if not row: return await call.answer('Product not found',show_alert=True)
    cat,panel,name,price,stock,active=row
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑️ Delete Product",callback_data=f"admin_catdel_{pid}",style='danger')],
        [InlineKeyboardButton(text="🔙 Back",callback_data="admin_advanced_management",style='success')]
    ])
    await call.message.edit_text(f"📦 <b>Product #{pid}</b>\n\nCategory: <b>{escape(cat)}</b>\nPanel: <b>{escape(panel or '-')}</b>\nName: <b>{escape(name or '-')}</b>\nPrice: <b>₹{float(price):.2f}</b>\nStock: <b>{stock}</b>\nStatus: <b>{'Active' if active else 'Disabled'}</b>",reply_markup=kb,parse_mode='HTML')

@dp.callback_query(F.data.startswith("admin_catdel_"))
async def admin_category_product_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    try: pid=int(call.data.rsplit('_',1)[1])
    except: return await call.answer('Invalid product',show_alert=True)
    row=db_query("SELECT category,name FROM products WHERE id=?",(pid,),fetchone=True)
    if not row: return await call.answer('Product already removed',show_alert=True)
    db_query("DELETE FROM product_keys WHERE product_id=?",(pid,))
    db_query("DELETE FROM products WHERE id=?",(pid,))
    log_activity(call.from_user.id,'ADMIN_DELETE_PRODUCT',f'Product {pid} ({row[0]} / {row[1]})')
    await call.answer('✅ Product removed',show_alert=True)
    await call.message.edit_text(f"✅ <b>Product #{pid} removed.</b>\n\nCategory: <b>{escape(row[0])}</b>",reply_markup=advanced_management_kb(),parse_mode='HTML')

@dp.callback_query(F.data == "admin_ai_escalations")
async def admin_ai_escalations(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    rows=db_query("SELECT id,user_id,question,status,created_at FROM ai_escalations ORDER BY id DESC LIMIT 15",fetchall=True) or []
    if not rows:
        text="🚨 <b>AI ESCALATIONS</b>\n\nNo escalations yet."
    else:
        lines=["🚨 <b>AI ESCALATIONS</b>",""]
        for eid,uid,q,status,created in rows:
            lines.append(f"#{eid} • User <code>{uid}</code> • <b>{escape(status)}</b>\n{escape((q or '')[:180])}")
        text='\n'.join(lines)
    await call.message.edit_text(text,reply_markup=advanced_management_kb(),parse_mode='HTML')

# ==============================================================================
# 18. ADMIN STATISTICS
# ==============================================================================
@dp.callback_query(F.data == "admin_view_stats")
async def admin_dashboard_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    t_users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    t_resellers = db_query("SELECT COUNT(*) FROM users WHERE is_reseller=1", fetchone=True)[0]
    t_vip = db_query("SELECT COUNT(*) FROM users WHERE is_vip=1", fetchone=True)[0]
    t_prods = db_query("SELECT COUNT(*) FROM products", fetchone=True)[0]
    t_keys = db_query("SELECT COUNT(*) FROM product_keys WHERE is_used=0", fetchone=True)[0]
    t_rev = db_query("SELECT SUM(spent) FROM users", fetchone=True)[0] or 0.0
    today_str = datetime.now().strftime("%Y-%m-%d")
    t_spins = db_query("SELECT COUNT(*) FROM users WHERE last_spin LIKE ?", (f"{today_str}%",), fetchone=True)[0]
    msg = (f"📊 <b><u>GRID INTELLIGENCE DASHBOARD</u></b> 📊\n━━━━━━━━━━━━━━━━━━\n👥 <b>Total Grid Users:</b> {t_users}\n👑 <b>Wholesale Resellers:</b> {t_resellers}\n🌟 <b>Elite VIP Members:</b> {t_vip}\n━━━━━━━━━━━━━━━━━━\n📦 <b>Active Products:</b> {t_prods}\n🔑 <b>Unused Keys in Vault:</b> {t_keys}\n💰 <b>Total Gross Revenue:</b> {fmt_curr(t_rev)}\n🎰 <b>Ludo Spins Today:</b> {t_spins}\n━━━━━━━━━━━━━━━━━━")
    await call.message.edit_text(msg, reply_markup=admin_back_kb(), parse_mode='HTML')

# ==============================================================================
# 19. ADMIN PRODUCT MANAGEMENT
# ==============================================================================
@dp.callback_query(F.data == "admin_quick_add_prod")
async def quick_add_product_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        "⚡ <b>QUICK ADD API PRODUCT</b>\n\n"
        "एक product या multiple products (हर product नई line पर) इस format में भेजें:\n"
        "<code>Category | Panel | Product Name | Validity | User Price | Reseller Price | API Product ID | API Duration | API Slot</code>\n\n"
        "<b>Example (one line):</b>\n"
        "<code>ANDROID NON ROOT PANEL | MST PANEL | 7 Days | 7 Days | 500 | 300 | 12345 | 7 Days | 0</code>\n\n"
        "• API Slot: <code>0</code> = Auto/Failover, या <code>1-5</code> = specific API\n"
        "• Device limit automatically <code>1 Device HWID</code> रहेगा\n"
        "• Multiple lines एक साथ paste करके bulk add कर सकते हैं\n"
        "• यह shortcut API products के लिए है; manual-key product के लिए normal Add Product use करें.",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    await state.set_state(AdminStates.quick_add_product)


@dp.message(AdminStates.quick_add_product)
async def quick_add_product(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return
    lines = [line.strip() for line in (m.text or "").splitlines() if line.strip()]
    if not lines:
        return await m.answer("❌ कम से कम एक product line भेजें।")

    records = []
    configured = {
        int(row[0]): row for row in get_api_slots()
        if row[7] and row[2]
    }
    for line_no, line in enumerate(lines, 1):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) not in (9, 10):
            return await m.answer(
                f"❌ Line {line_no} में format गलत है। Exactly 9 fields भेजें:\n"
                "<code>Category | Panel | Name | Validity | User Price | Reseller Price | API PID | API Duration | API Slot</code>",
                parse_mode="HTML"
            )

        # Permit an optional APK link before the API PID.
        if len(parts) == 9:
            category, panel_name, name, validity, user_price, reseller_price, pid, api_duration, api_slot = parts
            apk_link = ""
        else:
            category, panel_name, name, validity, user_price, reseller_price, apk_link, pid, api_duration, api_slot = parts

        matched_category = next(
            (cat for cat in FIXED_CATEGORIES if cat.lower() == category.lower()), None
        )
        if not matched_category:
            return await m.answer(f"❌ Line {line_no}: category गलत है।")
        if not all((panel_name, name, validity, pid, api_duration)):
            return await m.answer(f"❌ Line {line_no}: panel, name, validity, API PID और API duration खाली नहीं हो सकते।")
        try:
            price = float(user_price)
            reseller_price_value = float(reseller_price)
            selected_slot = int(api_slot or "0")
        except ValueError:
            return await m.answer(f"❌ Line {line_no}: price और API slot numeric होने चाहिए।")
        if price < 0 or reseller_price_value < 0:
            return await m.answer(f"❌ Line {line_no}: price negative नहीं हो सकती।")
        if selected_slot < 0 or selected_slot > API_SLOT_MAX:
            return await m.answer(f"❌ Line {line_no}: API slot 0 से {API_SLOT_MAX} के बीच होना चाहिए।")
        if selected_slot and selected_slot not in configured:
            return await m.answer(f"❌ Line {line_no}: API Slot {selected_slot} configured नहीं है।")

        records.append((
            matched_category, panel_name, name, price, reseller_price_value, 1,
            "" if apk_link.lower() == "none" else apk_link, validity,
            "1 Device HWID", 1, pid, 0, normalize_api_duration(api_duration), selected_slot
        ))

    conn = sqlite3.connect("yp_shop.db")
    cursor = conn.cursor()
    insert_sql = """INSERT INTO products
        (category, panel_name, name, price_inr, reseller_price, stock, apk_link,
         validity, device_limit, external_enabled, external_product_id,
         requires_android_id, external_duration, api_slot)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    product_ids = []
    for record in records:
        cursor.execute(insert_sql, record)
        product_ids.append(cursor.lastrowid)
    conn.commit()
    conn.close()
    await state.clear()
    await m.answer(
        f"✅ <b>{len(product_ids)} Quick Products Created!</b>\n\n"
        f"📦 Product IDs: <code>{', '.join(map(str, product_ids))}</code>\n"
        "API route: <code>Auto / Failover All APIs</code> या line में चुना हुआ slot.",
        reply_markup=admin_kb(), parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_add_prod")
async def add_prod_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for cat in FIXED_CATEGORIES:
        emoji_id = get_category_emoji(cat)
        kb.inline_keyboard.append([InlineKeyboardButton(text=cat, callback_data=f"addprod_cat_{cat}", icon_custom_emoji_id=emoji_id, style="danger")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Cancel", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("<b>Step 1:</b> Choose the <b>Category</b> for this product:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("addprod_cat_"))
async def add_prod_category_selected(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    category = call.data.split("addprod_cat_", 1)[1]
    await state.update_data(cat=category)
    await call.message.edit_text(f"<b>Step 2:</b> Enter <b>PANEL NAME</b>\n(e.g., 'MST PANEL', 'DRIP PANEL'):", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_panel_name)

@dp.message(AdminStates.add_prod_panel_name)
async def add_prod_panel_name(m: Message, state: FSMContext):
    await state.update_data(panel_name=m.text)
    await m.answer("<b>Step 3:</b> Enter <b>PACKAGE DURATION/DATE NAME</b>\n(e.g., '7 Days', '1 Month'):", parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_name)

@dp.message(AdminStates.add_prod_name)
async def add_prod_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    await m.answer("⏳ Enter Time Validity String (e.g., '24 Hours'):", parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_validity)

@dp.message(AdminStates.add_prod_validity)
async def add_prod_validity(m: Message, state: FSMContext):
    await state.update_data(validity=m.text)
    await m.answer("📱 Enter strict Device Enforcement Limit (e.g., '1 Device HWID'):", parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_device_limit)

@dp.message(AdminStates.add_prod_device_limit)
async def add_prod_device_limit(m: Message, state: FSMContext):
    await state.update_data(device_limit=m.text)
    await m.answer("💰 Enter standard **User Price** in Rupees (₹) (e.g., 500):", parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_price)

@dp.message(AdminStates.add_prod_price)
async def add_prod_price(m: Message, state: FSMContext):
    try:
        await state.update_data(price=float(m.text))
        await m.answer("👑 Enter wholesale **Reseller Price** in Rupees (₹) (e.g., 300):", parse_mode='HTML')
        await state.set_state(AdminStates.add_prod_reseller_price)
    except ValueError: await m.answer("❌ Invalid input datatype! Must be numerical.")

@dp.message(AdminStates.add_prod_reseller_price)
async def add_prod_reseller_price(m: Message, state: FSMContext):
    try:
        await state.update_data(reseller_price=float(m.text))
        await m.answer("🔗 Enter direct APK/Payload Download Link (or type 'none' to omit):", parse_mode='HTML')
        await state.set_state(AdminStates.add_prod_apk)
    except ValueError: await m.answer("❌ Invalid input datatype! Must be numerical.")

@dp.message(AdminStates.add_prod_apk)
async def add_prod_apk(m: Message, state: FSMContext):
    await state.update_data(apk="" if m.text.lower() == 'none' else m.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes — Generate Key via API", callback_data="addprod_ext_yes", icon_custom_emoji_id=get_emoji_icon("check_icon"), style="success")],
        [InlineKeyboardButton(text="❌ No — Use Manual Keys", callback_data="addprod_ext_no", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await m.answer("🔗 <b>Does this product use the external API for automatic key generation?</b>", reply_markup=kb, parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_external)

@dp.callback_query(F.data == "addprod_ext_yes", AdminStates.add_prod_external)
async def add_prod_external_yes(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.update_data(external_enabled=1)
    await call.message.edit_text("🆔 Enter the <b>External Product ID (PID)</b> used by the API:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_external_product_id)

@dp.message(AdminStates.add_prod_external_product_id)
async def add_prod_external_pid(m: Message, state: FSMContext):
    pid = m.text.strip()
    if not pid:
        return await m.answer("❌ Product PID cannot be empty.")
    data = await state.get_data()
    # The API's duration is NOT necessarily the Telegram package name.
    # Ask for the exact duration/price tier configured on the API.
    await state.update_data(external_product_id=pid, requires_android_id=0)
    await m.answer(
        "⏱ <b>Enter the exact XYZ API duration/price tier.</b>\n\n"
        "Examples: <code>3 Hours</code>, <code>1 Day</code>, <code>7 Days</code>.\n"
        f"Your shop validity is: <code>{data.get('validity', '')}</code>\n\n"
        "If the API uses the same duration, send the same value.",
        reply_markup=admin_back_kb(), parse_mode='HTML'
    )
    await state.set_state(AdminStates.add_prod_external_duration)

@dp.message(AdminStates.add_prod_external_duration)
async def add_prod_external_duration(m: Message, state: FSMContext):
    api_duration = normalize_api_duration(m.text.strip())
    if not api_duration:
        return await m.answer("❌ API duration cannot be empty.")
    await state.update_data(external_duration=api_duration)
    slots = get_api_slots()
    rows = []
    for slot, name, url, method, headers_json, body_json, content_type, enabled, priority, source_code, last_status in slots[:API_SLOT_MAX]:
        if enabled and url:
            rows.append([InlineKeyboardButton(
                text=f"🔌 API Slot {slot} — {name or f'API {slot}'}",
                callback_data=f"addprod_api_{slot}",
                style="primary",
            )])
    rows.append([InlineKeyboardButton(
        text="🔄 Auto / Failover All APIs",
        callback_data="addprod_api_0",
        style="success",
    )])
    rows.append([InlineKeyboardButton(text="BACK", callback_data="admin_panel_back", style="danger")])
    await m.answer(
        "🔌 <b>Choose the API for this product</b>\n\n"
        "The selected API will be used first when a customer buys this product. "
        "Auto / Failover will try all configured APIs by priority.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.add_prod_api_slot)


@dp.callback_query(F.data.regexp(r"^addprod_api_[0-5]$"), AdminStates.add_prod_api_slot)
async def add_prod_api_slot_selected(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    try:
        api_slot = int(call.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        return await call.answer("Invalid API slot.", show_alert=True)
    data = await state.get_data()
    if api_slot:
        configured = {
            int(row[0]): row for row in get_api_slots()
            if row[7] and row[2]
        }
        if api_slot not in configured:
            return await call.answer("That API slot is not configured.", show_alert=True)
    conn = sqlite3.connect('yp_shop.db')
    c = conn.cursor()
    c.execute("""INSERT INTO products
        (category, panel_name, name, price_inr, reseller_price, stock, apk_link, validity, device_limit,
         external_enabled, external_product_id, requires_android_id, external_duration, api_slot)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data['cat'], data['panel_name'], data['name'], data['price'], data['reseller_price'], 1,
         data['apk'], data['validity'], data['device_limit'], 1, data['external_product_id'], 0,
         data['external_duration'], api_slot))
    prod_id = c.lastrowid
    conn.commit(); conn.close()
    await call.message.edit_text(
        f"✅ <b>API Product Created!</b>\n\nProduct ID: <code>{prod_id}</code>\n"
        f"External Product ID: <code>{data['external_product_id']}</code>\n"
        f"API Duration: <code>{data['external_duration']}</code>\n"
        f"API Route: <code>{'Auto / Failover All APIs' if api_slot == 0 else f'Slot {api_slot}'}</code>\n\n"
        "The API will generate and deliver the key when the customer buys it.",
        reply_markup=admin_kb(), parse_mode='HTML'
    )
    await state.clear()

@dp.callback_query(F.data == "addprod_ext_no", AdminStates.add_prod_external)
async def add_prod_external_no(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.update_data(external_enabled=0, external_product_id="", requires_android_id=0)
    await call.message.edit_text("📥 <b>Manual Key Product</b>\n\nNow send the keys, one key per line:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_prod_keys)

@dp.message(AdminStates.add_prod_keys)
async def add_prod_keys(m: Message, state: FSMContext):
    keys = [k.strip() for k in m.text.strip().split('\n') if k.strip()]
    if not keys:
        return await m.answer("❌ No valid keys found. Send at least one key.")
    data = await state.get_data()
    stock = len(keys)
    conn = sqlite3.connect('yp_shop.db')
    c = conn.cursor()
    c.execute("""INSERT INTO products
        (category, panel_name, name, price_inr, reseller_price, stock, apk_link, validity, device_limit,
         external_enabled, external_product_id, requires_android_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (data['cat'], data['panel_name'], data['name'], data['price'], data['reseller_price'], stock,
         data['apk'], data['validity'], data['device_limit'], 0, '', 0))
    prod_id = c.lastrowid
    for k in keys:
        c.execute("INSERT INTO product_keys (product_id, key_text) VALUES (?, ?)", (prod_id, k))
    conn.commit(); conn.close()
    await m.answer(f"✅ <b>Manual Product Created!</b>\n\n📦 Product ID: <code>{prod_id}</code>\n🔒 Stock: {stock} keys", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_manage_prods")
async def admin_manage_prods(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    prods = db_query("SELECT id, name, category, panel_name, stock, is_active FROM products", fetchall=True)
    prods = sorted(prods or [], key=lambda row: (natural_sort_key(row[2]), natural_sort_key(row[3]), natural_sort_key(row[1])))
    if not prods: return await call.message.edit_text("📦 Store Database is completely empty.", reply_markup=admin_back_kb(), parse_mode='HTML')
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in prods:
        status_dot = "🟢" if p[5] else "🔴"
        panel_name = p[3] if p[3] is not None else ""
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{status_dot} [{p[2]}] {panel_name} - {p[1]} (Stock: {p[4]})", callback_data=f"admin_view_p_{p[0]}", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("📦 <b>Database Editor: Select Node to modify</b>", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("admin_view_p_"))
async def admin_view_product(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    try:
        p_id = int(call.data.split("_")[3])
        # Do not use SELECT * here: older databases and newer migrations can
        # have different column counts/order, which caused "list index out of
        # range" when the admin opened a product.
        prod = db_query("""
            SELECT id, category, panel_name, name, price_inr, reseller_price,
                   stock, apk_link, validity, device_limit, is_active,
                   COALESCE(external_enabled, 0),
                   COALESCE(external_product_id, ''),
                   COALESCE(requires_android_id, 0),
                   COALESCE(external_duration, ''),
                   COALESCE(api_slot, 0)
            FROM products WHERE id=?
        """, (p_id,), fetchone=True)
        if not prod: return await call.answer("❌ Architecture fault: Node lost!", show_alert=True)
        panel_name = prod[2] if prod[2] is not None else ""
        price_inr = float(prod[4]) if prod[4] is not None and prod[4] != "" else 0.0
        reseller_price = float(prod[5]) if prod[5] is not None and prod[5] != "" else 0.0
        api_route = "Auto / Failover All APIs" if not prod[15] else f"API Slot {prod[15]}"
        text = (f"📦 <b><u>NODE DEEP DIVE DETAILS</u></b>\n━━━━━━━━━━━━━━━━━━\n<b>ID:</b> <code>{prod[0]}</code>\n<b>Panel Group:</b> {prod[1]}\n<b>Panel Name:</b> {panel_name}\n<b>Package Date/Time:</b> {prod[3]}\n<b>Standard Price:</b> ₹{price_inr:.2f}\n👑 <b>Wholesale Price:</b> ₹{reseller_price:.2f}\n<b>Vault Stock:</b> {prod[6]}\n<b>API Stock Mode:</b> {"♾️ Unlimited (External API)" if prod[11] else "🔢 Manual Stock"}\n<b>API Route:</b> {api_route}\n<b>Payload Link:</b> {prod[7] if prod[7] else 'None'}\n<b>Time Config:</b> {prod[8]}\n<b>HWID Limit:</b> {prod[9]}\n<b>Visibility:</b> {'Active' if prod[10] else 'Hidden'}\n━━━━━━━━━━━━━━━━━━")
        toggle_btn_text = "Hide Product 👁‍🗨" if prod[10] else "Unhide Product 👁"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Edit Panel Group 🏷️", callback_data=f"edit_p_{p_id}_cat", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary"), 
             InlineKeyboardButton(text="Edit Panel Name 🏷️", callback_data=f"edit_p_{p_id}_panel_name", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
            [InlineKeyboardButton(text="Edit Package Name ✏️", callback_data=f"edit_p_{p_id}_name", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
            [InlineKeyboardButton(text="Edit Price 💰", callback_data=f"edit_p_{p_id}_price", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="primary"), 
             InlineKeyboardButton(text="Edit R-Price 👑", callback_data=f"edit_p_{p_id}_rprice", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="primary")],
            [InlineKeyboardButton(text="Edit Validity ⏳", callback_data=f"edit_p_{p_id}_validity", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary"), 
             InlineKeyboardButton(text="Edit Device 📱", callback_data=f"edit_p_{p_id}_device", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
            [InlineKeyboardButton(text="Edit API Duration ⏱️", callback_data=f"edit_p_{p_id}_api_duration", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
            [InlineKeyboardButton(text="Edit APK Link 🔗", callback_data=f"edit_p_{p_id}_apk", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary"), 
             InlineKeyboardButton(text="Add Keys ➕", callback_data=f"edit_p_{p_id}_keys", icon_custom_emoji_id=get_emoji_icon("add_balance"), style="success")],
            [InlineKeyboardButton(text="Add to Stock 📦➕", callback_data=f"edit_p_{p_id}_stock_add", icon_custom_emoji_id=get_emoji_icon("add_balance"), style="success")],
            [InlineKeyboardButton(text="Delete Key 🗑", callback_data=f"delkey_p_{p_id}", icon_custom_emoji_id=get_emoji_icon("back"), style="danger"), 
             InlineKeyboardButton(text=toggle_btn_text, callback_data=f"toggle_p_{p_id}", icon_custom_emoji_id=get_emoji_icon("check_icon"), style="primary")],
            [InlineKeyboardButton(text="Nuke Full Node 🗑", callback_data=f"delete_p_{p_id}", icon_custom_emoji_id=get_emoji_icon("back"), style="danger"), 
             InlineKeyboardButton(text="BACK", callback_data="admin_manage_prods", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
        ])
        await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error in admin_view_product: {e}")
        await call.message.edit_text(f"❌ Error loading product: {str(e)}", reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.callback_query(F.data.startswith("toggle_p_"))
async def admin_toggle_product(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    p_id = int(call.data.split("_")[2])
    current = db_query("SELECT is_active FROM products WHERE id=?", (p_id,), fetchone=True)[0]
    new_val = 0 if current == 1 else 1
    db_query("UPDATE products SET is_active=? WHERE id=?", (new_val, p_id))
    await call.answer("Visibility updated successfully!", show_alert=True)
    await admin_view_product(call)

# ==============================================================================
# FIX: Edit product field – correctly handle different data types
# ==============================================================================
@dp.callback_query(F.data.startswith("edit_p_"))
async def start_edit_product(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    parts = call.data.split("_")
    p_id = int(parts[2]); field = "_".join(parts[3:])
    await state.update_data(edit_p_id=p_id, edit_field=field)
    if field == 'keys':
        await call.message.edit_text("📥 <b>Vault Injection</b>\nPaste the <b>NEW KEYS</b> to append to the stock (1 key per line):", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_add_keys)
    elif field == 'stock_add':
        await call.message.edit_text(
            "📦 <b>Add to Stock</b>\n\nEnter how many stock units to add.\nExample: <code>100</code> or <code>200</code>",
            reply_markup=admin_back_kb(), parse_mode='HTML'
        )
        await state.set_state(AdminStates.wait_for_new_value)
    else:
        field_name_map = {'cat': 'New Panel Group/Category Name', 'panel_name': 'New Panel Name', 'name': 'New Package/Date Name', 'price': 'New Standard Price in ₹', 'rprice': 'New Reseller Price in ₹', 'validity': 'New Time Validity String', 'device': 'New HWID Limit String', 'apk': 'New Payload Link (or type "none")', 'api_duration': 'Exact XYZ API Duration (e.g. 1 Day)', 'stock_add': 'Stock units to add'}
        await call.message.edit_text(f"✏️ Input the required data for: <b>{field_name_map[field]}</b>", reply_markup=admin_back_kb(), parse_mode='HTML')
        await state.set_state(AdminStates.wait_for_new_value)

@dp.message(AdminStates.wait_for_new_value)
async def process_edit_value(m: Message, state: FSMContext):
    data = await state.get_data()
    p_id = data['edit_p_id']; field = data['edit_field']; new_val = m.text.strip()
    
    # If field is price or reseller price, convert to float
    if field in ['price', 'rprice']:
        try:
            new_val = float(new_val)
        except ValueError:
            return await m.answer("❌ Invalid number format. Please enter a valid price (e.g., 500).")
    # If field is apk, store as string (don't convert to float!)
    elif field == 'apk':
        new_val = "" if new_val.lower() == 'none' else new_val
    elif field == 'stock_add':
        try:
            add_qty = int(new_val)
            if add_qty <= 0 or add_qty > 100000:
                raise ValueError
        except ValueError:
            return await m.answer("❌ Enter a positive whole number up to 100000, e.g. 100 or 200.")
        db_query("UPDATE products SET stock=COALESCE(stock,0)+? WHERE id=?", (add_qty, p_id))
        new_stock = db_query("SELECT stock FROM products WHERE id=?", (p_id,), fetchone=True)[0]
        await m.answer(f"✅ <b>Stock Added!</b>\n\n➕ Added: <code>{add_qty}</code>\n📦 New Stock: <code>{new_stock}</code>", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
        return
    # For all other fields (cat, panel_name, name, validity, device), keep as string
    
    db_col_map = {'cat': 'category', 'panel_name': 'panel_name', 'name': 'name', 'price': 'price_inr', 'rprice': 'reseller_price', 'validity': 'validity', 'device': 'device_limit', 'apk': 'apk_link', 'api_duration': 'external_duration'}
    db_query(f"UPDATE products SET {db_col_map[field]}=? WHERE id=?", (new_val, p_id))
    await m.answer("✅ <b>Node updated gracefully!</b>", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.message(AdminStates.wait_for_add_keys)
async def process_add_keys(m: Message, state: FSMContext):
    data = await state.get_data()
    p_id = data['edit_p_id']
    keys = [k.strip() for k in m.text.strip().split('\n') if k.strip()]
    if len(keys) == 0: return await m.answer("❌ Protocol breach: Zero valid keys found.", reply_markup=admin_kb(), parse_mode='HTML')
    conn = sqlite3.connect('yp_shop.db')
    c = conn.cursor()
    for k in keys: c.execute("INSERT INTO product_keys (product_id, key_text) VALUES (?, ?)", (p_id, k))
    c.execute("UPDATE products SET stock = stock + ? WHERE id=?", (len(keys), p_id))
    conn.commit(); conn.close()
    await m.answer(f"✅ <b>Vault Secure!</b> {len(keys)} new keys appended and encrypted.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data.startswith("delete_p_"))
async def admin_delete_product(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    p_id = int(call.data.split("_")[2])
    db_query("DELETE FROM products WHERE id=?", (p_id,))
    db_query("DELETE FROM product_keys WHERE product_id=?", (p_id,))
    await call.answer("☢️ Nuclear wipe successful! Node and vault deleted.", show_alert=True)
    await admin_manage_prods(call)

@dp.callback_query(F.data.startswith("delkey_p_"))
async def admin_delete_key_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    p_id = int(call.data.split("_")[2])
    await state.update_data(del_p_id=p_id)
    await call.message.edit_text("🗑 Send the <b>exact string match</b> of the key you wish to purge from the vault:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_delete_key)

@dp.message(AdminStates.wait_for_delete_key)
async def process_delete_key(m: Message, state: FSMContext):
    data = await state.get_data()
    p_id = data['del_p_id']
    key_to_delete = m.text.strip()
    key_data = db_query("SELECT id, is_used FROM product_keys WHERE product_id=? AND key_text=?", (p_id, key_to_delete), fetchone=True)
    if not key_data: return await m.answer("❌ Key not found. Check logs and try again.", reply_markup=admin_back_kb(), parse_mode='HTML')
    if key_data[1] == 1: return await m.answer("⚠️ Action Blocked: This key has already been dispatched to a user.", reply_markup=admin_back_kb(), parse_mode='HTML')
    db_query("DELETE FROM product_keys WHERE id=?", (key_data[0],))
    db_query("UPDATE products SET stock = stock - 1 WHERE id=?", (p_id,))
    await m.answer(f"✅ Key <code>{key_to_delete}</code> securely purged from vault.\n📦 Database indices updated.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

# ==============================================================================
# 20. ADMIN TICKETS, BROADCAST, COUPONS
# ==============================================================================
@dp.callback_query(F.data == "admin_view_tickets")
async def admin_view_tickets(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Access denied.", show_alert=True)
        return
    await call.answer()
    tickets = db_query("SELECT id, user_id, message, created_at FROM tickets WHERE status='Open' ORDER BY id ASC LIMIT 1", fetchall=True) or []
    if not tickets:
        await call.message.edit_text("🎫 <b>Support Tickets</b>\n\n✅ No open support tickets right now.", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    t = tickets[0]
    text = (f"🎫 <b><u>ACTIVE TICKET #{t[0]}</u></b>\n👤 <b>Origin UID:</b> <code>{t[1]}</code>\n📅 <b>Timestamp:</b> {t[3]}\n\n📝 <b>Payload:</b>\n{t[2]}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Formulate Reply", callback_data=f"reply_ticket_{t[0]}_{t[1]}", icon_custom_emoji_id=get_emoji_icon("telegram"), style="primary")],
        [InlineKeyboardButton(text="❌ Force Close Ticket", callback_data=f"close_ticket_{t[0]}", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("close_ticket_"))
async def close_ticket(call: CallbackQuery):
    ticket_id = call.data.split("_")[2]
    db_query("UPDATE tickets SET status='Closed' WHERE id=?", (ticket_id,))
    await call.answer("✅ Status set to Closed.", show_alert=True)
    await admin_view_tickets(call) 

@dp.callback_query(F.data.startswith("reply_ticket_"))
async def reply_ticket_start(call: CallbackQuery, state: FSMContext):
    data = call.data.split("_")
    ticket_id, user_id = data[2], data[3]
    await state.update_data(ticket_id=ticket_id, user_id=user_id)
    await call.message.edit_text(f"💬 Formulating reply for node <code>{user_id}</code>.\n\nType your message payload:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.ticket_reply_msg)

@dp.message(AdminStates.ticket_reply_msg)
async def send_ticket_reply(m: Message, state: FSMContext):
    data = await state.get_data()
    try:
        await bot.send_message(data['user_id'], f"📞 <b>Admin Reply (Ref #{data['ticket_id']}):</b>\n\n{m.text}", parse_mode='HTML')
        db_query("UPDATE tickets SET status='Closed' WHERE id=?", (data['ticket_id'],))
        await m.answer("✅ Payload delivered and connection closed successfully.", reply_markup=admin_kb(), parse_mode='HTML')
    except Exception as e: await m.answer(f"❌ Transmission Error: {e}", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast_btn")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("📢 <b>Mass Broadcast Protocol</b>\n\nSend the rich message payload you wish to transmit globally across the grid:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.broadcast_msg)

@dp.message(AdminStates.broadcast_msg)
async def admin_broadcast_send(message: Message, state: FSMContext):
    users = db_query("SELECT user_id FROM users", fetchall=True)
    sent, failed = 0, 0
    m = await message.answer("⏳ Broadcast protocol initiated... Do not interrupt.", parse_mode='HTML')
    for u in users:
        try:
            await message.send_copy(chat_id=u[0])
            sent += 1
        except Exception: failed += 1
        await asyncio.sleep(0.06) 
    await m.edit_text(f"✅ <b>Global Broadcast Complete!</b>\n\n🟢 Nodes reached: {sent}\n🔴 Nodes failed/blocked: {failed}", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

def _valid_youtube_url(value: str) -> bool:
    try:
        parsed = urlparse((value or "").strip())
        host = (parsed.netloc or "").lower().split(":", 1)[0]
        return (
            parsed.scheme in {"http", "https"}
            and (host == "youtu.be" or host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"))
        )
    except Exception:
        return False

@dp.callback_query(F.data == "admin_youtube_course")
async def admin_youtube_course(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    lessons = db_query(
        "SELECT id, title, url, video_file_id FROM youtube_lessons "
        "WHERE is_active=1 ORDER BY sort_order ASC, id ASC LIMIT 50",
        fetchall=True,
    ) or []
    price = _youtube_course_price()
    contact_link = _normalize_course_contact(get_setting("youtube_course_contact", ""))
    paid_users = db_query("SELECT COUNT(*) FROM youtube_course_access", fetchone=True)
    text = (
        "🎓 <b>YOUTUBE COURSE MANAGER</b>\n\n"
        f"💳 <b>Course fee:</b> {fmt_curr(price)}\n"
        f"👥 <b>Paid users:</b> {int(paid_users[0]) if paid_users else 0}\n"
        f"💬 <b>Contact:</b> {escape(contact_link) if contact_link else 'Not set'}\n\n"
    )
    if lessons:
        text += "\n".join(
            f"{index}. <b>{escape(str(row[1]))}</b>\n"
            f"   {'📹 Telegram video' if row[3] else '🔗 ' + escape(str(row[2]))}"
            for index, row in enumerate(lessons, start=1)
        )
    else:
        text += "No lessons added yet."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Course Lesson", callback_data="admin_youtube_add_lesson", icon_custom_emoji_id=get_emoji_icon("tutorial"), style="success")],
        [
            InlineKeyboardButton(text="💳 Set Course Fee", callback_data="admin_youtube_set_price", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="success"),
            InlineKeyboardButton(text="💬 Set Course Contact", callback_data="admin_youtube_set_contact", icon_custom_emoji_id=get_emoji_icon("support"), style="success"),
        ],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")],
    ])
    await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True, parse_mode="HTML")

@dp.callback_query(F.data == "admin_youtube_add_lesson")
async def admin_youtube_add_lesson(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        "🎓 <b>Add YouTube Course Lesson</b>\n\n"
        "Send the lesson title.\nExample: <code>Lesson 1 — How to install</code>\n\n"
        "Next step में YouTube link भेज सकते हैं या Telegram video upload कर सकते हैं.",
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.youtube_lesson_title)

@dp.message(AdminStates.youtube_lesson_title)
async def save_youtube_lesson_title(m: Message, state: FSMContext):
    title = (m.text or "").strip()
    if not title:
        return await m.answer("❌ Lesson title cannot be empty.")
    await state.update_data(youtube_lesson_title=title[:100])
    await m.answer(
        "🔗 YouTube video/playlist URL भेजें या 📹 Telegram में video upload करें.\n"
        "Example: <code>https://youtu.be/...</code>",
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.youtube_lesson_url)

@dp.message(AdminStates.youtube_lesson_url)
async def save_youtube_lesson_url(m: Message, state: FSMContext):
    url = (m.text or "").strip()
    video_file_id = ""
    content_type = "url"
    if m.video:
        video_file_id = m.video.file_id
        content_type = "telegram_video"
        url = ""
    elif not _valid_youtube_url(url):
        return await m.answer(
            "❌ Valid YouTube URL bhejo, jaise https://youtu.be/... "
            "ya Telegram video upload karo."
        )
    data = await state.get_data()
    last_order = db_query("SELECT COALESCE(MAX(sort_order), 0) FROM youtube_lessons", fetchone=True)
    next_order = int(last_order[0] if last_order else 0) + 1
    db_query(
        "INSERT INTO youtube_lessons "
        "(title, url, sort_order, is_active, created_at, video_file_id, content_type) "
        "VALUES (?, ?, ?, 1, ?, ?, ?)",
        (
            data["youtube_lesson_title"],
            url,
            next_order,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            video_file_id,
            content_type,
        ),
    )
    await state.clear()
    await m.answer(
        f"✅ <b>Lesson added successfully!</b>\n\n"
        f"📚 Title: <b>{escape(data['youtube_lesson_title'])}</b>\n"
        f"🔢 Lesson number: <b>{next_order}</b>\n"
        f"📦 Type: <b>{'Telegram video' if video_file_id else 'YouTube link'}</b>",
        reply_markup=admin_kb(),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin_youtube_set_price")
async def admin_youtube_set_price(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        f"💳 <b>Set YouTube Course Fee</b>\n\n"
        f"Current fee: <b>{fmt_curr(_youtube_course_price())}</b>\n"
        "Send amount in rupees. Example: <code>199</code>\n"
        "0 भेजने पर course free हो जाएगा.",
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.youtube_course_price)


@dp.message(AdminStates.youtube_course_price)
async def save_youtube_course_price(m: Message, state: FSMContext):
    try:
        price = float((m.text or "").replace(",", "").strip())
        if price < 0 or price > 1000000:
            raise ValueError
    except (TypeError, ValueError):
        return await m.answer("❌ Valid amount भेजें, जैसे 99 या 199.")
    set_setting("youtube_course_price", f"{price:.2f}")
    await state.clear()
    await m.answer(
        f"✅ YouTube Course fee set to <b>{fmt_curr(price)}</b>.",
        reply_markup=admin_kb(),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "admin_youtube_set_contact")
async def admin_youtube_set_contact(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    current = _normalize_course_contact(get_setting("youtube_course_contact", ""))
    await call.message.edit_text(
        "💬 <b>Set Course Contact Link</b>\n\n"
        f"Current: <code>{escape(current) if current else 'Not set'}</code>\n\n"
        "Telegram/WhatsApp link या Telegram username भेजें.\n"
        "Example: <code>https://t.me/your_username</code>\n"
        "Remove करने के लिए <code>-</code> भेजें.",
        reply_markup=admin_back_kb(),
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.youtube_course_contact)


@dp.message(AdminStates.youtube_course_contact)
async def save_youtube_course_contact(m: Message, state: FSMContext):
    raw_value = (m.text or "").strip()
    if raw_value == "-":
        set_setting("youtube_course_contact", "")
        await state.clear()
        return await m.answer("✅ Course contact removed.", reply_markup=admin_kb(), parse_mode="HTML")
    value = _normalize_course_contact(raw_value)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return await m.answer(
            "❌ Valid Telegram/WhatsApp URL या @username भेजें.\n"
            "Example: https://t.me/your_username"
        )
    set_setting("youtube_course_contact", value)
    await state.clear()
    await m.answer(
        f"✅ Course contact saved:\n<code>{escape(value)}</code>",
        reply_markup=admin_kb(),
        parse_mode="HTML",
    )

@dp.callback_query(F.data == "admin_create_coupon")
async def admin_create_coupon_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("🎟 Enter a highly secure alphanumeric sequence for the Promo Code:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.add_coupon_code)

@dp.message(AdminStates.add_coupon_code)
async def admin_coupon_code(m: Message, state: FSMContext):
    await state.update_data(code=m.text.strip().upper())
    await m.answer("💰 Enter the monetary reward payload in <b>RUPEES (₹)</b>:", parse_mode='HTML')
    await state.set_state(AdminStates.add_coupon_amount)

@dp.message(AdminStates.add_coupon_amount)
async def admin_coupon_amount(m: Message, state: FSMContext):
    try:
        await state.update_data(amount=float(m.text)) 
        await m.answer("👥 Enter the exact maximum threshold uses for this code:", parse_mode='HTML')
        await state.set_state(AdminStates.add_coupon_uses)
    except ValueError: await m.answer("❌ Non-numerical data detected. Aborting.")

@dp.message(AdminStates.add_coupon_uses)
async def admin_coupon_uses(m: Message, state: FSMContext):
    try:
        uses = int(m.text)
        data = await state.get_data()
        db_query("INSERT OR REPLACE INTO coupons (code, amount, uses_left) VALUES (?, ?, ?)", (data['code'], data['amount'], uses))
        await m.answer(f"✅ Protocol <b>{data['code']}</b> encoded!\nReward Vector: {fmt_curr(data['amount'])}\nThreshold Limit: {uses} executions.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Non-numerical data detected. Aborting.")

# ==============================================================================
# 21. ADMIN RESELLER & SPIN SETTINGS
# ==============================================================================
@dp.callback_query(F.data == "admin_reseller_menu")
async def admin_reseller_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    status_check = db_query("SELECT value FROM settings WHERE key='reseller_system_status'", fetchone=True)
    sys_status = status_check[0] if status_check else "ON"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Grant Reseller Rights", callback_data="reseller_make", icon_custom_emoji_id=get_emoji_icon("reseller"), style="success"), 
         InlineKeyboardButton(text="➖ Revoke Reseller", callback_data="reseller_remove", icon_custom_emoji_id=get_emoji_icon("reseller"), style="danger")],
        [InlineKeyboardButton(text="📋 Audit Active Resellers", callback_data="reseller_view", icon_custom_emoji_id=get_emoji_icon("history"), style="primary")],
        [InlineKeyboardButton(text=f"{'🟢' if sys_status == 'ON' else '🔴'} Auto-Upgrade System: {sys_status}", callback_data="admin_toggle_reseller_sys", icon_custom_emoji_id=get_emoji_icon("check_icon"), style="success" if sys_status == 'ON' else "danger")], 
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text("👑 <b>Wholesale Reseller Protocols</b>\nSelect administrative action:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "admin_toggle_reseller_sys")
async def toggle_reseller_sys(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    res = db_query("SELECT value FROM settings WHERE key='reseller_system_status'", fetchone=True)
    current = res[0] if res else 'ON'
    new_status = 'OFF' if current == 'ON' else 'ON'
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('reseller_system_status', ?)", (new_status,))
    await admin_reseller_menu(call)

@dp.callback_query(F.data.in_(["reseller_make", "reseller_remove"]))
async def reseller_prompt_id(call: CallbackQuery, state: FSMContext):
    action = call.data
    await state.update_data(reseller_action=action)
    await call.message.edit_text("👤 Identify target node. Input <b>User ID</b> or <b>@username</b>:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.reseller_manage_id)

@dp.message(AdminStates.reseller_manage_id)
async def process_reseller_manage(m: Message, state: FSMContext):
    data = await state.get_data()
    target = m.text.strip()
    if target.startswith('@'): target = target[1:]
    user_q = db_query("SELECT user_id, first_name FROM users WHERE user_id=? OR username=? COLLATE NOCASE", (target, target), fetchone=True)
    if not user_q: return await m.answer("❌ Target completely ghosted. Not in database.", reply_markup=admin_back_kb(), parse_mode='HTML')
    u_id, u_name = user_q[0], user_q[1]
    if data['reseller_action'] == "reseller_make":
        db_query("UPDATE users SET is_reseller=1, reseller_since=?, account_type='Reseller' WHERE user_id=?", (datetime.now().strftime("%Y-%m-%d"), u_id))
        await m.answer(f"✅ Credentials upgraded. <b>{u_name}</b> (<code>{u_id}</code>) has reseller rights.", reply_markup=admin_kb(), parse_mode='HTML')
    else:
        db_query("UPDATE users SET is_reseller=0, account_type='Regular' WHERE user_id=?", (u_id,))
        _revoke_reseller_api_key(u_id)
        await m.answer(f"✅ Credentials revoked. <b>{u_name}</b> (<code>{u_id}</code>) is back to regular user. Personal Bot API has also been disabled.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "reseller_view")
async def reseller_view(call: CallbackQuery):
    resellers = db_query("SELECT user_id, first_name, username FROM users WHERE is_reseller=1", fetchall=True)
    if not resellers: return await call.message.edit_text("📋 Zero active resellers found.", reply_markup=admin_back_kb(), parse_mode='HTML')
    text = "👑 <b><u>ACTIVE RESELLER AUDIT LOG</u></b> 👑\n━━━━━━━━━━━━━━━━━━\n"
    for r in resellers:
        uname = f"(@{r[2]})" if r[2] else ""
        text += f"👤 {r[1]} {uname}\n🆔 <code>{r[0]}</code>\n\n"
    await call.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_spin_menu")
async def admin_spin_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    status = db_query("SELECT value FROM settings WHERE key='spin_status'", fetchone=True)
    limit = db_query("SELECT value FROM settings WHERE key='daily_spin_limit'", fetchone=True)
    status_val = status[0] if status else 'ON'
    limit_val = limit[0] if limit else '50.0'
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Append Reward Logic", callback_data="spin_add", icon_custom_emoji_id=get_emoji_icon("add_balance"), style="success"), 
         InlineKeyboardButton(text="❌ Drop Reward Logic", callback_data="spin_del", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")],
        [InlineKeyboardButton(text="📋 Audit Configs", callback_data="spin_view", icon_custom_emoji_id=get_emoji_icon("history"), style="primary"), 
         InlineKeyboardButton(text="⚙️ Throttle Limits", callback_data="spin_limit", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
        [InlineKeyboardButton(text=f"{'🟢' if status_val == 'ON' else '🔴'} Master Toggle: {status_val}", callback_data="spin_toggle", icon_custom_emoji_id=get_emoji_icon("check_icon"), style="success" if status_val == 'ON' else "danger")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(f"🎰 <b>Advanced Ludo/Spin Algorithms</b>\nCurrent Threshold: ₹{limit_val}", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "spin_toggle")
async def spin_toggle(call: CallbackQuery):
    res = db_query("SELECT value FROM settings WHERE key='spin_status'", fetchone=True)
    current = res[0] if res else 'ON'
    new_status = 'OFF' if current == 'ON' else 'ON'
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('spin_status', ?)", (new_status,))
    await admin_spin_menu(call)

@dp.callback_query(F.data == "admin_toggle_bot")
async def toggle_bot(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    res = db_query("SELECT value FROM settings WHERE key='bot_status'", fetchone=True)
    current = res[0] if res else 'ON'
    new_status = 'OFF' if current == 'ON' else 'ON'
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_status', ?)", (new_status,))
    await call.message.edit_reply_markup(reply_markup=admin_kb())

@dp.callback_query(F.data == "spin_add")
async def spin_add_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🎰 Inject new decimal logic limit (e.g. 15.50):", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.spin_add_reward)

@dp.message(AdminStates.spin_add_reward)
async def spin_add_exec(m: Message, state: FSMContext):
    try:
        amt = float(m.text)
        db_query("INSERT INTO spin_rewards (amount) VALUES (?)", (amt,))
        await m.answer(f"✅ Algorithm updated. New vector {fmt_curr(amt)} injected.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Math parsing error.")

@dp.callback_query(F.data == "spin_view")
async def spin_view(call: CallbackQuery):
    rewards = db_query("SELECT amount FROM spin_rewards ORDER BY amount ASC", fetchall=True)
    text = "🎰 <b>Live Ludo Constants</b>\n\n"
    for r in rewards: text += f"🎁 {fmt_curr(r[0])}\n"
    await call.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_set_video")
async def admin_set_video_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("📹 Input direct streaming / YouTube Link for Tutorial system:\n<i>(Or type 'None' to clear registry):</i>", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_howto_video)

@dp.message(AdminStates.wait_for_howto_video)
async def exec_set_video(m: Message, state: FSMContext):
    link = m.text.strip()
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('how_to_video', ?)", (link,))
    await m.answer("✅ Routing complete. Video linked.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_all_files")
async def admin_set_all_files_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("🔗 Input the direct Channel / Cloud URL for 'Download Files' button:\n<i>(Or type 'None' to format data):</i>", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_all_files_link)

@dp.message(AdminStates.wait_for_all_files_link)
async def exec_set_all_files(m: Message, state: FSMContext):
    link = m.text.strip()
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES ('all_files_link', ?)", (link,))
    await m.answer("✅ Global resource variable updated.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_edit_emojis")
async def admin_edit_emojis(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    rows = db_query("SELECT key, value FROM settings WHERE key LIKE 'emoji_%' ORDER BY key", fetchall=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for row in rows:
        key = row[0]
        slot = key.replace("emoji_", "")
        current_id = row[1] if row[1] else "Not set"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{slot} (ID: {current_id})", callback_data=f"edit_emoji_{slot}", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("🎨 <b>Edit All Emojis</b>\nChoose an emoji slot to change its ID:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("edit_emoji_"))
async def admin_edit_emoji_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    slot = call.data.split("edit_emoji_", 1)[1]
    await state.update_data(emoji_slot=slot)
    current = get_setting(f"emoji_{slot}", "Not set")
    await call.message.edit_text(f"✏️ Enter new emoji ID for <b>{slot}</b>:\nCurrent: {current}\n(Leave empty to reset to default)", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_emoji_slot)

@dp.message(AdminStates.wait_for_emoji_slot)
async def save_emoji_slot(m: Message, state: FSMContext):
    data = await state.get_data()
    slot = data['emoji_slot']
    new_id = m.text.strip()
    if new_id == "":
        db_query("DELETE FROM settings WHERE key=?", (f"emoji_{slot}",))
        await m.answer(f"✅ Reset emoji for '{slot}' to default.", reply_markup=admin_kb(), parse_mode='HTML')
    else:
        if not new_id.isdigit():
            await m.answer("❌ Invalid ID! Must be numeric.", reply_markup=admin_kb(), parse_mode='HTML')
            return
        set_setting(f"emoji_{slot}", new_id)
        await m.answer(f"✅ Emoji for '{slot}' updated to ID {new_id}.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_edit_ui_menu")
async def admin_edit_ui_menu(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Edit Start Menu Text", callback_data="edit_ui_start", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
        [InlineKeyboardButton(text="Edit Download Files Text", callback_data="edit_ui_download", icon_custom_emoji_id=get_emoji_icon("download"), style="primary")],
        [InlineKeyboardButton(text="Edit VIP Menu Text", callback_data="edit_ui_vip", icon_custom_emoji_id=get_emoji_icon("vip"), style="primary")],
        [InlineKeyboardButton(text="Edit Lucky Dice Text", callback_data="edit_ui_dice", icon_custom_emoji_id=get_emoji_icon("ludo_spin"), style="primary")],
        [InlineKeyboardButton(text="Edit Add Balance Text", callback_data="edit_ui_add_balance", icon_custom_emoji_id=get_emoji_icon("add_balance"), style="primary")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text("✏️ <b>Edit User Interface Texts</b>\nSelect which text you want to modify:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("edit_ui_"))
async def admin_edit_ui_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    ui_key = call.data.split("_")[2]
    await state.update_data(ui_key=ui_key)
    current_text = get_ui_text(ui_key)
    await call.message.edit_text(f"📝 Send the new text for <b>{ui_key.upper()}</b> menu.\n\nCurrent text:\n{current_text}", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.edit_ui_text)

@dp.message(AdminStates.edit_ui_text)
async def admin_save_ui_text(m: Message, state: FSMContext):
    data = await state.get_data()
    ui_key = data['ui_key']
    new_text = m.text
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"ui_{ui_key}", new_text))
    await m.answer(f"✅ UI text <b>{ui_key}</b> updated successfully!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_edit_reseller_price")
async def admin_edit_reseller_price_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    prods = db_query("SELECT id, name, category, panel_name, reseller_price FROM products", fetchall=True)
    prods = sorted(prods or [], key=lambda row: (natural_sort_key(row[2]), natural_sort_key(row[3]), natural_sort_key(row[1])))
    if not prods: return await call.message.edit_text("No products to edit.", reply_markup=admin_back_kb(), parse_mode='HTML')
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in prods:
        panel_name = p[3] if p[3] is not None else ""
        r_price = float(p[4]) if p[4] is not None else 0.0
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{p[2]} - {panel_name} - {p[1]} (₹{r_price:.2f})", callback_data=f"edit_reseller_{p[0]}", icon_custom_emoji_id=get_emoji_icon("money_icon"), style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("👑 <b>Edit Reseller Price per Product</b>\nSelect a product to change its wholesale price:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("edit_reseller_"))
async def admin_edit_reseller_price_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    prod_id = int(call.data.split("_")[2])
    await state.update_data(edit_reseller_prod_id=prod_id)
    await call.message.edit_text("💰 Enter the new <b>Reseller Price</b> in Rupees (₹) for this product:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.edit_reseller_price)

@dp.message(AdminStates.edit_reseller_price)
async def admin_save_reseller_price(m: Message, state: FSMContext):
    try:
        new_price = float(m.text)
        data = await state.get_data()
        prod_id = data['edit_reseller_prod_id']
        db_query("UPDATE products SET reseller_price=? WHERE id=?", (new_price, prod_id))
        await m.answer(f"✅ Reseller price updated to {fmt_curr(new_price)} for product ID {prod_id}.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Invalid number. Please enter a valid price.")

@dp.callback_query(F.data == "admin_set_reseller_fee")
async def admin_set_reseller_fee(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("💰 Enter the new <b>Reseller Setup Fee</b> in Rupees (₹):\nCurrent: " + get_setting("reseller_setup_fee", "200.0"), reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_reseller_setup_fee)

@dp.message(AdminStates.wait_for_reseller_setup_fee)
async def admin_save_reseller_fee(m: Message, state: FSMContext):
    try:
        fee = float(m.text)
        set_setting("reseller_setup_fee", str(fee))
        await m.answer(f"✅ Reseller setup fee updated to {fmt_curr(fee)}.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Invalid number. Please enter a valid amount.")

@dp.callback_query(F.data == "admin_set_reseller_min")
async def admin_set_reseller_min(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("💳 Enter the new <b>Minimum Balance</b> required to become reseller (₹):\nCurrent: " + get_setting("reseller_min_balance", "500.0"), reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_reseller_min_balance)

@dp.message(AdminStates.wait_for_reseller_min_balance)
async def admin_save_reseller_min(m: Message, state: FSMContext):
    try:
        min_bal = float(m.text)
        set_setting("reseller_min_balance", str(min_bal))
        await m.answer(f"✅ Minimum reseller balance updated to {fmt_curr(min_bal)}.", reply_markup=admin_kb(), parse_mode='HTML')
        await state.clear()
    except ValueError: await m.answer("❌ Invalid number. Please enter a valid amount.")

@dp.callback_query(F.data == "admin_set_support_links")
async def admin_set_support_links(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Access denied.", show_alert=True)
        return
    await call.answer()
    tg = get_setting("support_telegram", "Not set")
    wa = get_setting("support_whatsapp", "Not set")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 Set Telegram Link", callback_data="admin_set_telegram", icon_custom_emoji_id=get_emoji_icon("telegram"), style="primary")],
        [InlineKeyboardButton(text="📱 Set WhatsApp Link", callback_data="admin_set_whatsapp", icon_custom_emoji_id=get_emoji_icon("whatsapp"), style="primary")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    await call.message.edit_text(
        "📌 <b>Support Contact Links</b>\n\n"
        f"✈️ Telegram: <code>{tg}</code>\n"
        f"📱 WhatsApp: <code>{wa}</code>\n\n"
        "Set the URLs below. The user Support menu will automatically hide any invalid/unset link.",
        reply_markup=kb, parse_mode='HTML'
    )

@dp.callback_query(F.data == "admin_set_telegram")
async def admin_set_telegram(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("✈️ Enter the Telegram contact URL (e.g., https://t.me/YOUR_SUPPORT):", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_support_telegram)

@dp.message(AdminStates.wait_for_support_telegram)
async def save_telegram_link(m: Message, state: FSMContext):
    link = (m.text or "").strip()
    if not _valid_support_url(link, "telegram"):
        await m.answer("❌ Invalid Telegram URL. Use a link like https://t.me/YourUsername", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    set_setting("support_telegram", link)
    await m.answer("✅ Telegram support link updated!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_whatsapp")
async def admin_set_whatsapp(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("📱 Enter the WhatsApp contact URL (e.g., https://wa.me/1234567890):", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_support_whatsapp)

@dp.message(AdminStates.wait_for_support_whatsapp)
async def save_whatsapp_link(m: Message, state: FSMContext):
    link = (m.text or "").strip()
    if not _valid_support_url(link, "whatsapp"):
        await m.answer("❌ Invalid WhatsApp URL. Use a link like https://wa.me/919876543210", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    set_setting("support_whatsapp", link)
    await m.answer("✅ WhatsApp support link updated!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_category_emojis")
async def admin_set_category_emojis(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for cat in FIXED_CATEGORIES:
        current = get_setting(f"cat_emoji_{cat}", "Not set")
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{cat} (ID: {current})", callback_data=f"set_cat_emoji_{cat}", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("🎨 <b>Set Category Emojis</b>\nChoose a category to set its custom emoji ID:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("set_cat_emoji_"))
async def admin_set_category_emoji_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    category = call.data.split("set_cat_emoji_", 1)[1]
    await state.update_data(cat_emoji_category=category)
    await call.message.edit_text(f"🎨 Enter the emoji ID for <b>{category}</b>:\n(Leave empty to reset to default)", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_category_emoji)

@dp.message(AdminStates.wait_for_category_emoji)
async def save_category_emoji(m: Message, state: FSMContext):
    data = await state.get_data()
    category = data['cat_emoji_category']
    emoji_id = m.text.strip()
    if emoji_id == "":
        db_query("DELETE FROM settings WHERE key=?", (f"cat_emoji_{category}",))
        await m.answer(f"✅ Reset emoji for {category} to default.", reply_markup=admin_kb(), parse_mode='HTML')
    else:
        if not emoji_id.isdigit():
            await m.answer("❌ Invalid ID! Must be numeric.", reply_markup=admin_kb(), parse_mode='HTML')
            return
        set_setting(f"cat_emoji_{category}", emoji_id)
        await m.answer(f"✅ Emoji set for {category} successfully!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_panel_emojis")
async def admin_set_panel_emojis(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    panels = db_query("SELECT DISTINCT panel_name FROM products WHERE panel_name != '' ORDER BY panel_name", fetchall=True)
    if not panels:
        await call.message.edit_text("No panel names found in products.", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for p in panels:
        panel = p[0]
        current = get_setting(f"panel_emoji_{panel}", "Not set")
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{panel} (ID: {current})", callback_data=f"set_panel_emoji_{panel}", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")])
    await call.message.edit_text("🖼 <b>Set Panel Emojis</b>\nChoose a panel name to set its custom emoji ID:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("set_panel_emoji_"))
async def admin_set_panel_emoji_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    panel_name = call.data.split("set_panel_emoji_", 1)[1]
    await state.update_data(panel_emoji_name=panel_name)
    await call.message.edit_text(f"🎨 Enter the emoji ID for panel <b>{panel_name}</b>:\n(Leave empty to reset to default)", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_panel_emoji_id)

@dp.message(AdminStates.wait_for_panel_emoji_id)
async def save_panel_emoji(m: Message, state: FSMContext):
    data = await state.get_data()
    panel_name = data['panel_emoji_name']
    emoji_id = m.text.strip()
    if emoji_id == "":
        db_query("DELETE FROM settings WHERE key=?", (f"panel_emoji_{panel_name}",))
        await m.answer(f"✅ Reset emoji for panel '{panel_name}'.", reply_markup=admin_kb(), parse_mode='HTML')
    else:
        if not emoji_id.isdigit():
            await m.answer("❌ Invalid ID! Must be numeric.", reply_markup=admin_kb(), parse_mode='HTML')
            return
        set_setting(f"panel_emoji_{panel_name}", emoji_id)
        await m.answer(f"✅ Emoji set for panel '{panel_name}'!", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_setup_fampay")
async def setup_fampay_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    current_key = get_setting("fampay_api_key", "")
    current_url = get_fampay_base_url()
    current_gmail = get_setting("fampay_gmail", "")
    current_upi = get_setting("fampay_upi", "")
    masked = (current_key[:4] + "••••••" + current_key[-4:]) if len(current_key) > 8 else ("Not configured" if not current_key else "Configured")
    text = (
        "💳 <b>FAMPAY / FAMGATEWAY FULL SETUP</b>\n\n"
        f"🌐 API Base URL: <code>{current_url}</code>\n"
        f"🔑 API Key: <code>{masked}</code>\n"
        f"📧 FamPay Gmail: <code>{current_gmail or 'Not saved'}</code>\n"
        f"💠 FamPay UPI ID: <code>{current_upi or 'Not saved'}</code>\n\n"
        "Send the <b>Gateway Base URL</b> first. Example: <code>https://fam.aryanispe.in</code>\n"
        "Then the bot will ask for API key, FamPay-linked Gmail, and FamPay UPI ID.\n\n"
        "⚠️ Gmail/App Password and UPI are configured on the gateway website/dashboard; this bot stores the merchant identifiers only and does not send your Gmail password to the API.\n\n"
        "<i>Type /cancel to abort.</i>"
    )
    await call.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_fampay_api)
    await state.update_data(fampay_setup_step="base_url")

@dp.message(AdminStates.wait_for_fampay_api)
async def fampay_api(m: Message, state: FSMContext):
    if (m.text or '').strip().lower() == '/cancel':
        await state.clear()
        return await m.answer("Setup cancelled.", reply_markup=admin_kb(), parse_mode='HTML')

    value = (m.text or '').strip()
    data = await state.get_data()
    step = data.get("fampay_setup_step", "base_url")

    if step == "base_url":
        candidate = value.rstrip("/")
        parsed = urlparse(candidate)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return await m.answer("❌ Invalid URL. Send a full HTTPS/HTTP base URL, e.g. <code>https://fam.aryanispe.in</code>.", parse_mode='HTML')
        set_setting("fampay_base_url", candidate)
        await state.update_data(fampay_setup_step="api_key")
        return await m.answer("✅ Base URL saved.\n\n🔑 Now send the <b>FamGateway API Key</b>.", parse_mode='HTML')

    if step == "api_key":
        if len(value) < 8:
            return await m.answer("❌ API key looks too short. Send the valid API key.", parse_mode='HTML')
        set_setting("fampay_api_key", value)
        await state.update_data(fampay_setup_step="gmail")
        return await m.answer("✅ API key saved.\n\n📧 Now send the <b>FamPay-linked Gmail address</b> used in the gateway dashboard.", parse_mode='HTML')

    if step == "gmail":
        if "@" not in value or "." not in value.split("@")[-1]:
            return await m.answer("❌ That does not look like a valid Gmail address. Send the Gmail address only.", parse_mode='HTML')
        set_setting("fampay_gmail", value)
        await state.update_data(fampay_setup_step="upi")
        return await m.answer("✅ Gmail saved.\n\n💠 Now send the <b>FamPay UPI ID</b>, e.g. <code>yourname@fam</code>.", parse_mode='HTML')

    if step == "upi":
        if "@" not in value or len(value) < 5:
            return await m.answer("❌ Invalid UPI ID. Example: <code>yourname@fam</code>.", parse_mode='HTML')
        set_setting("fampay_upi", value)
        await state.clear()
        base = get_fampay_base_url()
        await m.answer(
            "✅ <b>FamPay Gateway setup saved.</b>\n\n"
            f"🌐 Base URL: <code>{base}</code>\n"
            f"🔑 API: <code>{base}/api/qr.php</code>\n"
            f"🔎 Verify: <code>{base}/api/verify-order.php</code>\n"
            f"📧 Gmail: <code>{get_setting('fampay_gmail')}</code>\n"
            f"💠 UPI: <code>{get_setting('fampay_upi')}</code>\n\n"
            "⚠️ If this gateway website requires Gmail/App Password setup, complete that on its dashboard. The bot never stores or sends the Gmail App Password.",
            reply_markup=admin_kb(), parse_mode='HTML'
        )

# ==============================================================================
# GLOBAL TELEGRAM ERROR HANDLER
# ==============================================================================
@dp.errors()
async def global_error_handler(event):
    """Keep one bad Telegram/API request from producing an unhelpful traceback loop."""
    try:
        exc = event.exception
    except Exception:
        exc = None
    logger.exception("Unhandled aiogram update error: %r", exc)
    return True

# ==============================================================================
# 22. BOOTSTRAPPING & MAIN
# ==============================================================================
async def main() -> None:
    init_db()
    logger.info("Initializing DB structure...")
    migrate_categories()
    asyncio.create_task(auto_verify_task())
    logger.info("FamPay Auto-Verifier Daemon Running in Background.")
    asyncio.create_task(binance_pay_auto_verify_task())
    try:
        await start_bot_api_server()
    except Exception as api_server_err:
        logger.exception("Reseller Bot API server could not start: %s", api_server_err)
    logger.info("🚀 CORE SYSTEM IS FULLY OPERATIONAL...")
    try:
        # This bot uses long-polling. If a previous deployment/configuration
        # left a Telegram webhook active, getUpdates will always fail with
        # TelegramConflictError. Remove the webhook before starting polling.
        try:
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url:
                logger.warning(
                    "Telegram webhook detected (%s). Deleting it before polling...",
                    webhook_info.url,
                )
                await bot.delete_webhook(drop_pending_updates=True)
                logger.info("Telegram webhook deleted; starting long polling.")
            else:
                logger.info("No Telegram webhook is active; starting long polling.")
        except Exception as webhook_err:
            logger.error("Could not clear Telegram webhook: %s", webhook_err)

        await dp.start_polling(bot, handle_signals=False)
    except Exception as err:
        logger.error(f"Critical System Failure in Polling: {err}")
    finally:
        await bot.session.close()

# ==============================================================================
# RESELLER PERSONAL BOT API
# ==============================================================================
BOT_API_PREFIX = "rsl_"
BOT_API_VERSION = "v1"
_API_RATE_BUCKET: Dict[int, List[float]] = {}

def _api_key_hash(key: str) -> str:
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()

def _generate_reseller_api_key() -> str:
    return BOT_API_PREFIX + secrets.token_urlsafe(32)

def _reseller_api_record(user_id: int):
    return db_query("SELECT id,key_hash,key_prefix,key_last4,enabled,requests_count,last_used_at FROM reseller_api_keys WHERE user_id=?", (user_id,), fetchone=True)

def _issue_reseller_api_key(user_id: int) -> str:
    key = _generate_reseller_api_key()
    now = int(time.time())
    db_query("""INSERT INTO reseller_api_keys(user_id,key_hash,key_prefix,key_last4,created_at,regenerated_at,enabled,requests_count,last_used_at)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET key_hash=excluded.key_hash,key_prefix=excluded.key_prefix,key_last4=excluded.key_last4,regenerated_at=excluded.regenerated_at,enabled=1,requests_count=0,last_used_at=0""",
             (user_id,_api_key_hash(key),BOT_API_PREFIX,key[-4:],now,now,1,0,0))
    return key

def _revoke_reseller_api_key(user_id: int) -> None:
    db_query("UPDATE reseller_api_keys SET enabled=0 WHERE user_id=?", (user_id,))

def _api_user_from_request(request: web.Request):
    if get_setting("bot_api_enabled", "ON").upper() != "ON":
        return None, (503, "Bot API is currently disabled by admin.")
    auth = (request.headers.get("Authorization") or "").strip()
    key = auth[7:].strip() if auth.lower().startswith("bearer ") else (request.headers.get("X-Reseller-API-Key") or "").strip()
    if not key or len(key) < 20:
        return None, (401, "Missing or invalid reseller API key.")
    row = db_query("SELECT user_id,enabled FROM reseller_api_keys WHERE key_hash=?", (_api_key_hash(key),), fetchone=True)
    if not row:
        return None, (401, "Invalid reseller API key.")
    user_id, enabled = int(row[0]), bool(row[1])
    user = db_query("SELECT user_id,first_name,username,balance,is_reseller,is_vip FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if not user or not user[4]:
        return None, (403, "Reseller access is not active.")
    if not enabled:
        return None, (403, "This API key is disabled. Generate a new key from the Reseller Panel.")
    now = int(time.time())
    try:
        limit = max(10, min(600, int(float(get_setting("bot_api_rate_limit", "60")))))
    except Exception:
        limit = 60
    bucket = _API_RATE_BUCKET.setdefault(user_id, [])
    cutoff = now - 60
    bucket[:] = [t for t in bucket if t > cutoff]
    if len(bucket) >= limit:
        return None, (429, f"Rate limit exceeded. Maximum {limit} requests/minute.")
    bucket.append(now)
    db_query("UPDATE reseller_api_keys SET requests_count=requests_count+1,last_used_at=? WHERE user_id=?", (now,user_id))
    return user, None

def _api_json(data, status=200):
    return web.json_response(data, status=status, dumps=lambda obj: json.dumps(obj, ensure_ascii=False))

async def reseller_api_me(request: web.Request):
    user, err = _api_user_from_request(request)
    if err: return _api_json({"success":False,"error":err[1]}, err[0])
    return _api_json({"success":True,"data":{"user_id":user[0],"name":user[1] or "","username":user[2] or "","balance":round(float(user[3] or 0),2),"is_reseller":bool(user[4]),"is_vip":bool(user[5]),"api_version":BOT_API_VERSION}})

async def reseller_api_products(request: web.Request):
    user, err = _api_user_from_request(request)
    if err: return _api_json({"success":False,"error":err[1]}, err[0])
    rows=db_query("""SELECT id,category,panel_name,name,price_inr,reseller_price,stock,validity,device_limit,external_enabled,external_product_id,requires_android_id
                     FROM products WHERE is_active=1 ORDER BY category,panel_name,id""", fetchall=True) or []
    items=[]
    for r in rows:
        price=float(r[5] or r[4] or 0)
        if user[5]: price=round(price*(1-VIP_DISCOUNT_PERCENTAGE/100),2)
        items.append({"id":r[0],"category":r[1],"panel_name":r[2] or "","name":r[3],"price":price,"normal_price":float(r[4] or 0),"reseller_price":float(r[5] or 0),"stock":None if r[9] else int(r[6] or 0),"validity":r[7],"device_limit":r[8],"api_generated":bool(r[9]),"requires_android_id":bool(r[11])})
    return _api_json({"success":True,"data":items})

async def _api_purchase(user_id: int, product_id: int, android_id: str = "") -> dict:
    prod=db_query("""SELECT name,price_inr,stock,apk_link,validity,device_limit,category,reseller_price,panel_name,external_enabled,
                           external_product_id,requires_android_id,external_duration FROM products WHERE id=? AND is_active=1""", (product_id,), fetchone=True)
    user=db_query("SELECT balance,referred_by,is_reseller,total_saved,is_vip FROM users WHERE user_id=?", (user_id,), fetchone=True)
    if not prod or not user: return {"ok":False,"status":404,"error":"Product or user not found."}
    if not user[2]: return {"ok":False,"status":403,"error":"Reseller access is required."}
    normal=float(prod[1] or 0); reseller=float(prod[7] or 0); base=reseller if reseller>0 else normal
    price=base-(base*VIP_DISCOUNT_PERCENTAGE/100) if user[4] else base
    price=round(price,2)
    if not bool(prod[9]) and int(prod[2] or 0)<=0: return {"ok":False,"status":409,"error":"Product is out of stock."}
    # Atomic wallet debit to prevent concurrent API requests from overspending.
    conn=sqlite3.connect('yp_shop.db'); cur=conn.cursor()
    try:
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=? AND is_reseller=1", (price,user_id,price))
        if cur.rowcount != 1:
            conn.rollback(); return {"ok":False,"status":402,"error":"Insufficient balance."}
        conn.commit()
    finally: conn.close()
    delivered=None; api_response=None
    try:
        if bool(prod[9]):
            ext_id=(prod[10] or "").strip()
            candidates=[]
            for c in ((prod[12] or "").strip(),prod[4],prod[0]):
                c=normalize_api_duration(c)
                if c and c not in candidates: candidates.append(c)
            for duration in candidates:
                api_response=await fetch_external_key(ext_id,duration,android_id)
                if api_response.get("status")=="success": break
                blob=json.dumps(api_response,ensure_ascii=False).lower()
                if "price not found" not in blob and "price_not_found" not in blob: break
            if not api_response or api_response.get("status")!="success":
                raise RuntimeError(str((api_response or {}).get("msg","External API failed")))
            delivered=api_response.get("key")
            if isinstance(delivered,list): delivered="\
".join(str(x) for x in delivered)
            if not delivered or str(delivered).strip()=="KEY_NOT_FOUND": raise RuntimeError("External API returned no key.")
        else:
            conn=sqlite3.connect('yp_shop.db'); cur=conn.cursor()
            cur.execute("SELECT id,key_text FROM product_keys WHERE product_id=? AND is_used=0 ORDER BY id LIMIT 1",(product_id,))
            kd=cur.fetchone()
            if not kd: conn.close(); raise RuntimeError("No manual key is available.")
            cur.execute("UPDATE product_keys SET is_used=1 WHERE id=? AND is_used=0",(kd[0],))
            if cur.rowcount != 1: conn.rollback(); conn.close(); raise RuntimeError("Key was already claimed. Please retry.")
            cur.execute("UPDATE products SET stock=CASE WHEN stock>0 THEN stock-1 ELSE 0 END WHERE id=?",(product_id,))
            conn.commit(); conn.close(); delivered=kd[1]
        product_full_name=f"{prod[6]} - {prod[8]} ({prod[0]})"
        db_query("UPDATE users SET spent=spent+?,orders_count=orders_count+1,total_saved=total_saved+? WHERE user_id=?",(price,normal-price,user_id))
        db_query("INSERT INTO orders(user_id,product_name,price_paid,delivered_key,purchase_date) VALUES(?,?,?,?,?)",(user_id,product_full_name,price,str(delivered),datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        log_activity(user_id,"API_PURCHASE_SUCCESS",f"Product: {product_full_name}; Paid: {price}")
        return {"ok":True,"status":200,"data":{"product_id":product_id,"product":product_full_name,"price":price,"key":str(delivered),"validity":prod[4],"device_limit":prod[5]}}
    except Exception as exc:
        db_query("UPDATE users SET balance=balance+? WHERE user_id=?",(price,user_id))
        logger.exception("Reseller Bot API purchase failed")
        return {"ok":False,"status":502,"error":f"Purchase failed and balance was refunded: {str(exc)[:300]}"}

async def reseller_api_purchase(request: web.Request):
    user, err = _api_user_from_request(request)
    if err: return _api_json({"success":False,"error":err[1]}, err[0])
    try: payload=await request.json()
    except Exception: return _api_json({"success":False,"error":"Request body must be JSON."},400)
    try: product_id=int(payload.get("product_id")); android_id=str(payload.get("android_id") or "").strip()[:200]
    except Exception: return _api_json({"success":False,"error":"product_id must be an integer."},400)
    prod=db_query("SELECT requires_android_id FROM products WHERE id=?",(product_id,),fetchone=True)
    if prod and prod[0] and not android_id: return _api_json({"success":False,"error":"android_id is required for this product."},400)
    result=await _api_purchase(user[0],product_id,android_id)
    return _api_json({"success":bool(result.get("ok")),**({"data":result["data"]} if result.get("ok") else {"error":result.get("error")})},result.get("status",500))

async def reseller_api_docs(request: web.Request):
    return _api_json({
        "success": True,
        "api_version": BOT_API_VERSION,
        "namespace": "/bot-api/v1",
        "authentication": "Authorization: Bearer YOUR_PERSONAL_API_KEY",
        "endpoints": [
            {"method": "GET", "path": "/bot-api/v1/me", "description": "Reseller account and balance"},
            {"method": "GET", "path": "/bot-api/v1/wallet", "description": "Read reseller Bot wallet balance"},
            {"method": "GET", "path": "/bot-api/v1/products", "description": "List active products with your reseller price"},
            {"method": "POST", "path": "/bot-api/v1/purchase", "description": "Buy a product; JSON: {product_id, android_id?}"},
            {"method": "POST", "path": "/bot-api/v1/connected/{secret}/webhook", "description": "Private webhook used after a reseller connects their own Telegram bot."},
        ],
    })

async def reseller_bot_api_wallet(request: web.Request):
    """Dedicated Bot API wallet endpoint. Deposits are made securely through the bot's payment gateways; this endpoint only reads balance."""
    user, err = _api_user_from_request(request)
    if err: return _api_json({"success":False,"error":err[1]}, err[0])
    return _api_json({"success":True,"data":{"balance":round(float(user[3] or 0),2),"currency":"INR","deposit_via_bot":"/api menu -> Add Balance -> FamPay / Binance Pay"}})

async def reseller_api_health(request: web.Request):
    return _api_json({"success":True,"service":"reseller-bot-api","version":BOT_API_VERSION,"time":int(time.time())})

_BOT_API_RUNNER = None
_BOT_API_START_LOCK = asyncio.Lock()

async def start_bot_api_server():
    """Start the dedicated reseller Bot API exactly once on Railway/Render."""
    global _BOT_API_RUNNER
    async with _BOT_API_START_LOCK:
        if _BOT_API_RUNNER is not None:
            logger.info("Reseller Bot API already running; skipping duplicate start.")
            return _BOT_API_RUNNER

        app = web.Application(client_max_size=1 * 1024 * 1024)
        app.router.add_get('/bot-api/health', reseller_api_health)
        app.router.add_get('/bot-api/v1/docs', reseller_api_docs)
        app.router.add_get('/bot-api/v1/me', reseller_api_me)
        app.router.add_get('/bot-api/v1/wallet', reseller_bot_api_wallet)
        app.router.add_get('/bot-api/v1/products', reseller_api_products)
        app.router.add_post('/bot-api/v1/purchase', reseller_api_purchase)
        app.router.add_post('/bot-api/v1/connected/{secret}/webhook', connected_bot_webhook)

        port = int(os.getenv('PORT', os.getenv('BOT_API_PORT', '8080')))
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            site = web.TCPSite(runner, '0.0.0.0', port, reuse_address=True)
            await site.start()
        except OSError as exc:
            await runner.cleanup()
            if getattr(exc, 'errno', None) == 98:
                logger.error(
                    "Reseller Bot API port %s is already in use; skipping duplicate listener so Telegram bot can continue.",
                    port,
                )
                return None
            raise

        _BOT_API_RUNNER = runner
        logger.info("Reseller Bot API listening on 0.0.0.0:%s", port)
        return runner

@dp.callback_query(F.data.in_({"reseller_api_generate", "reseller_api_regenerate"}))
async def reseller_api_issue(call: CallbackQuery):
    u = db_query("SELECT is_reseller FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if not u or not u[0]:
        return await call.answer("❌ पहले Reseller बनें.", show_alert=True)
    access = db_query("SELECT enabled FROM reseller_bot_api_access WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if not access or not access[0]:
        return await call.answer("🔒 पहले Bot API System को ₹90 में activate करें.", show_alert=True)
    key = _issue_reseller_api_key(call.from_user.id)
    action = "generated" if call.data == "reseller_api_generate" else "regenerated"
    base = get_setting("bot_api_public_url", "").strip() or (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL") or "").strip()
    api_base = base.rstrip("/") if base else "<YOUR_PUBLIC_BOT_API_URL>"
    text = (f"🔑 <b>Personal Bot API {action.upper()}</b>\n\n<b>API Key:</b> <code>{escape(key)}</code>\n\n"
            "⚠️ Save this key now. Full key is shown only once.\n\n"
            f"<b>Base URL:</b> <code>{escape(api_base)}</code>\n<b>Auth:</b> <code>Authorization: Bearer YOUR_KEY</code>\n\n"
            "♻️ Regenerate करने पर पुरानी key तुरंत invalid हो जाएगी।")
    await call.message.answer(text, parse_mode="HTML")
    await call.answer("✅ Personal API ready.", show_alert=True)

@dp.callback_query(F.data == "reseller_api_docs")
async def reseller_api_docs_button(call: CallbackQuery):
    base = get_setting("bot_api_public_url", "").strip()
    if not base:
        base = (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL") or "<YOUR_PUBLIC_BOT_API_URL>").strip()
    base = base.rstrip("/")
    text = (
        "📘 <b>RESELLER BOT API</b>\n\n"
        f"Base: <code>{escape(base)}</code>\n\n"
        "<b>Dedicated Bot API</b>\n<code>/bot-api/v1/...</code>\n"
        "<b>1. Account</b>\nGET <code>/bot-api/v1/me</code>\n"
        "<b>2. Wallet</b>\nGET <code>/bot-api/v1/wallet</code>\n"
        "<b>3. Products</b>\nGET <code>/bot-api/v1/products</code>\n"
        "<b>4. Purchase</b>\nPOST <code>/bot-api/v1/purchase</code>\n"
        'JSON: <code>{"product_id": 123, "android_id": "optional"}</code>\n\n'
        "Header: <code>Authorization: Bearer YOUR_PERSONAL_API_KEY</code>\n\n"
        "💰 Wallet funding is done inside this bot via Add Balance (FamPay / Binance Pay). The Bot API only spends the reseller wallet; it does not expose payment secrets."
    )
    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back", callback_data="menu_reseller_dash", style="danger")]
        ]),
        parse_mode="HTML"
    )

# ==============================================================================
# RESELLER BOT API PRODUCT + CONNECT-OWN-BOT SYSTEM
# ==============================================================================
def _bot_api_price() -> float:
    try: return max(0.0, float(get_setting("bot_api_price", "90")))
    except Exception: return 90.0

def _bot_token_cipher():
    if Fernet is None: return None
    raw = os.getenv("BOT_CONNECT_ENCRYPTION_KEY", "").strip()
    if raw:
        try: return Fernet(raw.encode())
        except Exception: pass
    # Working fallback for deployments that have not supplied an encryption key.
    seed = hashlib.sha256((BOT_TOKEN + "|bot-connector-v1").encode()).digest()
    return Fernet(__import__('base64').urlsafe_b64encode(seed))

def _encrypt_bot_token(token: str) -> str:
    cipher = _bot_token_cipher()
    if not cipher: raise RuntimeError("cryptography package is required for bot connection")
    return cipher.encrypt(token.encode()).decode()

def _decrypt_bot_token(value: str) -> str:
    cipher = _bot_token_cipher()
    if not cipher: raise RuntimeError("cryptography package is required for bot connection")
    return cipher.decrypt(value.encode()).decode()

def _bot_api_access(user_id: int):
    return db_query("SELECT enabled, purchased_at, price_inr FROM reseller_bot_api_access WHERE user_id=?", (user_id,), fetchone=True)

@dp.callback_query(F.data == "menu_bot_api_system")
async def menu_bot_api_system(call: CallbackQuery):
    u = db_query("SELECT is_reseller,balance FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if not u or not u[0]:
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👑 Become Reseller", callback_data="menu_reseller_dash", style="success")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="back_main", style="danger")]])
        return await call.message.edit_text("🤖 <b>BOT API SYSTEM</b>\n\n🔒 यह सुविधा सिर्फ Reseller के लिए है।\n\nपहले Reseller बनें, फिर ₹90 में अपना Personal Bot API activate करें।",reply_markup=kb,parse_mode="HTML")
    access=_bot_api_access(call.from_user.id)
    price=_bot_api_price()
    if not access or not access[0]:
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💳 Buy Bot API — ₹{price:.0f}", callback_data="reseller_buy_bot_api", style="success")],
            [InlineKeyboardButton(text="💰 Add Wallet Balance", callback_data="menu_add_balance", style="primary")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="menu_reseller_dash", style="danger")]])
        return await call.message.edit_text(f"🤖 <b>RESELLER BOT API</b>\n\nStatus: 🔒 Not Activated\nActivation Price: <b>₹{price:.2f}</b> one-time\nWallet Balance: <b>₹{float(u[1] or 0):.2f}</b>\n\nपहले यह API activation खरीदें। इसके बाद Personal API key और अपना Telegram bot connect करने का option मिलेगा।",reply_markup=kb,parse_mode="HTML")
    key=_reseller_api_record(call.from_user.id)
    conn=db_query("SELECT id,bot_username,enabled FROM reseller_bot_connections WHERE user_id=? ORDER BY id DESC LIMIT 1",(call.from_user.id,),fetchone=True)
    status="🟢 Connected" if conn and conn[2] else "🔴 Not Connected"
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Generate / Regenerate API", callback_data="reseller_api_generate", style="success")],
        [InlineKeyboardButton(text="🔗 Connect / Replace My Telegram Bot", callback_data="reseller_connect_bot", style="primary")],
        [InlineKeyboardButton(text="📘 Bot API Docs", callback_data="reseller_api_docs", style="primary")],
        [InlineKeyboardButton(text="📊 API Usage / Status", callback_data="reseller_api_status", style="success")],
        [InlineKeyboardButton(text="💰 Wallet", callback_data="menu_add_balance", style="success")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_reseller_dash", style="danger")]])
    api_state=(f"🟢 Active • <code>{key[2]}••••{key[3]}</code>" if key and key[4] else "⚠️ Generate your API key")
    text=f"🤖 <b>RESELLER BOT API</b>\n\n🟢 Activation: Active\n🔑 Personal API: {api_state}\n🔗 Connected Bot: <b>{status}</b>\n\n<b>Flow:</b> Activate ₹90 → Generate API → Connect your own Telegram bot → Your bot uses this reseller wallet/API."
    await call.message.edit_text(text,reply_markup=kb,parse_mode="HTML")

@dp.callback_query(F.data == "reseller_buy_bot_api")
async def reseller_buy_bot_api(call: CallbackQuery):
    u=db_query("SELECT balance,is_reseller FROM users WHERE user_id=?",(call.from_user.id,),fetchone=True)
    if not u or not u[1]: return await call.answer("❌ Reseller access required.",show_alert=True)
    if _bot_api_access(call.from_user.id) and _bot_api_access(call.from_user.id)[0]: return await menu_bot_api_system(call)
    price=_bot_api_price()
    conn=sqlite3.connect('yp_shop.db'); cur=conn.cursor()
    try:
        cur.execute("UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=? AND is_reseller=1",(price,call.from_user.id,price))
        if cur.rowcount!=1:
            conn.rollback(); return await call.answer(f"❌ Wallet में ₹{price:.0f} चाहिए। पहले Add Balance करें.",show_alert=True)
        cur.execute("INSERT OR REPLACE INTO reseller_bot_api_access(user_id,purchased_at,price_inr,enabled) VALUES(?,?,?,1)",(call.from_user.id,int(time.time()),price))
        conn.commit()
    finally: conn.close()
    log_activity(call.from_user.id,"BOT_API_ACTIVATED",f"Price: {price}")
    try: await notify_admins(f"🤖 <b>RESELLER BOT API ACTIVATED</b>\n👤 User: <code>{call.from_user.id}</code>\n💰 Price: ₹{price:.2f}",parse_mode="HTML")
    except Exception: pass
    await call.answer("✅ Bot API activated!",show_alert=True)
    await menu_bot_api_system(call)

@dp.callback_query(F.data == "reseller_connect_bot")
async def reseller_connect_bot(call: CallbackQuery, state: FSMContext):
    u=db_query("SELECT is_reseller FROM users WHERE user_id=?",(call.from_user.id,),fetchone=True)
    if not u or not u[0]: return await call.answer("❌ Reseller access required.",show_alert=True)
    if not (_bot_api_access(call.from_user.id) and _bot_api_access(call.from_user.id)[0]): return await call.answer("🔒 पहले ₹90 में Bot API activate करें.",show_alert=True)
    await call.message.edit_text("🔗 <b>CONNECT YOUR TELEGRAM BOT</b>\n\n1. @BotFather में अपना bot बनाएं।\n2. BotFather से मिला <b>HTTP API token</b> यहाँ paste करें।\n3. Bot को इसी Bot API से जोड़ दिया जाएगा।\n\n⚠️ Token किसी को share न करें। गलत token होने पर कोई data save नहीं होगा।",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_bot_api_system",style="danger")]]),parse_mode="HTML")
    await state.set_state(UserStates.bot_connect_token)

@dp.message(UserStates.bot_connect_token)
async def save_connected_bot(m: Message, state: FSMContext):
    token=(m.text or "").strip()
    if not re.match(r"^\d{6,12}:[A-Za-z0-9_-]{20,}$",token): return await m.answer("❌ Telegram bot token format सही नहीं है। BotFather का पूरा token paste करें।")
    u=db_query("SELECT is_reseller FROM users WHERE user_id=?",(m.from_user.id,),fetchone=True)
    if not u or not u[0] or not (_bot_api_access(m.from_user.id) and _bot_api_access(m.from_user.id)[0]):
        await state.clear(); return await m.answer("❌ पहले Reseller और ₹90 Bot API activation पूरा करें।",reply_markup=main_menu_kb(m.from_user.id))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(f"https://api.telegram.org/bot{token}/getMe") as resp:
                data=await resp.json(content_type=None)
        if not data.get("ok"): return await m.answer("❌ Token verify नहीं हुआ। BotFather token check करें।")
        bot_info=data["result"]; username=bot_info.get("username",""); bot_id=int(bot_info.get("id",0))
        base=get_setting("bot_api_public_url","").strip() or (os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL") or "").strip()
        if not base: return await m.answer("❌ Admin ने Bot API Public URL configure नहीं किया है।")
        secret=secrets.token_urlsafe(24)
        enc=_encrypt_bot_token(token)
        db_query("UPDATE reseller_bot_connections SET enabled=0 WHERE user_id=?",(m.from_user.id,))
        db_query("INSERT INTO reseller_bot_connections(user_id,bot_username,bot_id,token_encrypted,webhook_secret,enabled,created_at) VALUES(?,?,?,?,?,?,?)",(m.from_user.id,username,bot_id,enc,secret,1,int(time.time())))
        webhook_url=base.rstrip("/")+f"/bot-api/v1/connected/{secret}/webhook"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(f"https://api.telegram.org/bot{token}/setWebhook",data={"url":webhook_url,"drop_pending_updates":"true"}) as resp:
                wd=await resp.json(content_type=None)
        if not wd.get("ok"):
            db_query("UPDATE reseller_bot_connections SET enabled=0 WHERE user_id=? AND webhook_secret=?",(m.from_user.id,secret))
            return await m.answer("❌ Bot verify हो गया लेकिन webhook set नहीं हुआ। Admin से Public URL check करवाएं।")
        await state.clear()
        await m.answer(f"✅ <b>Bot Connected Successfully</b>\n\n🤖 @{escape(username)}\n🔗 Webhook active\n\nअब आपका bot इस reseller account के wallet/API से connected है।\nCommands: /start, /balance, /products, /buy PRODUCT_ID",reply_markup=main_menu_kb(m.from_user.id),parse_mode="HTML")
    except Exception as e:
        logger.exception("Connected bot setup failed")
        await m.answer("❌ Bot connection failed. Token/Public URL check करें और फिर retry करें।")

async def _connected_bot_send(token: str, chat_id: int, text: str, keyboard=None):
    payload={"chat_id":chat_id,"text":text,"parse_mode":"HTML","disable_web_page_preview":True}
    if keyboard is not None:
        payload["reply_markup"]={"inline_keyboard":keyboard}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.post(f"https://api.telegram.org/bot{token}/sendMessage",json=payload) as resp:
            return await resp.json(content_type=None)

def _connected_bot_keyboard():
    return [
        [{"text":"🛍 Products","callback_data":"cba:products"},{"text":"💰 Wallet","callback_data":"cba:wallet"}],
        [{"text":"📘 API Help","callback_data":"cba:help"},{"text":"🤖 AI Support","callback_data":"cba:ai"}],
        [{"text":"🧾 My Orders","callback_data":"cba:orders"}],
    ]

async def _connected_bot_products(user_id: int):
    rows=db_query("SELECT id,name,reseller_price,price_inr,requires_android_id FROM products WHERE is_active=1 ORDER BY id LIMIT 30",fetchall=True) or []
    if not rows: return "📦 <b>Products</b>\n\nNo products are available right now."
    lines=["📦 <b>PRODUCT STORE</b>","", "Tap a product ID or use <code>/buy PRODUCT_ID</code>.",""]
    for r in rows:
        price=float(r[2] or r[3] or 0)
        suffix=" • Android ID required" if r[4] else ""
        lines.append(f"<code>{r[0]}</code> • {escape(str(r[1]))} — <b>₹{price:.2f}</b>{suffix}")
    return "\n".join(lines)

async def _connected_bot_orders(user_id: int):
    rows=db_query("SELECT product_name,price_paid,purchase_date FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 8",(user_id,),fetchall=True) or []
    if not rows: return "🧾 <b>Order History</b>\n\nNo purchases yet."
    return "🧾 <b>RECENT ORDERS</b>\n\n" + "\n".join(f"• {escape(str(r[0]))} — ₹{float(r[1] or 0):.2f} — {r[2]}" for r in rows)

async def connected_bot_webhook(request: web.Request):
    secret=request.match_info.get("secret","")
    conn=db_query("SELECT user_id,token_encrypted,enabled,bot_username FROM reseller_bot_connections WHERE webhook_secret=?",(secret,),fetchone=True)
    if not conn or not conn[2]: return web.Response(status=404,text="Not found")
    try: payload=await request.json()
    except Exception: return web.Response(status=400,text="Invalid JSON")
    db_query("UPDATE reseller_bot_connections SET last_update_at=? WHERE webhook_secret=?",(int(time.time()),secret))
    try: token=_decrypt_bot_token(conn[1])
    except Exception: return web.Response(status=500,text="Token unavailable")

    user_id=int(conn[0])
    # Handle inline-button callbacks from the connected reseller bot.
    cb=payload.get("callback_query") or {}
    if cb:
        chat=((cb.get("message") or {}).get("chat") or {})
        chat_id=chat.get("id")
        data=(cb.get("data") or "").strip()
        cb_id=cb.get("id")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                if cb_id:
                    await session.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery",json={"callback_query_id":cb_id})
        except Exception: pass
        if chat_id is not None:
            if data=="cba:products":
                await _connected_bot_send(token,chat_id,await _connected_bot_products(user_id),_connected_bot_keyboard())
            elif data=="cba:wallet":
                u=db_query("SELECT balance,is_reseller,is_vip FROM users WHERE user_id=?",(user_id,),fetchone=True)
                reply=(f"💰 <b>YOUR BOT WALLET</b>\n\nBalance: <b>₹{float(u[0] or 0):.2f}</b>\nReseller: {'🟢 Active' if u and u[1] else '🔴 Inactive'}\nVIP: {'🟢 Active' if u and u[2] else '⚪ Inactive'}") if u else "❌ Account unavailable."
                await _connected_bot_send(token,chat_id,reply,_connected_bot_keyboard())
            elif data=="cba:orders":
                await _connected_bot_send(token,chat_id,await _connected_bot_orders(user_id),_connected_bot_keyboard())
            elif data=="cba:help":
                await _connected_bot_send(token,chat_id,"📘 <b>BOT API HELP</b>\n\n<code>/balance</code> — wallet\n<code>/products</code> — products\n<code>/buy PRODUCT_ID</code> — purchase\n<code>/buy PRODUCT_ID ANDROID_ID</code> — Android-ID product\n<code>/orders</code> — recent orders\n<code>/ai your question</code> — AI support",_connected_bot_keyboard())
            elif data=="cba:ai":
                await _connected_bot_send(token,chat_id,"🤖 <b>AI Support</b>\n\nAsk with <code>/ai</code> followed by your question. Example: <code>/ai payment fail ho gaya</code>",_connected_bot_keyboard())
        return web.json_response({"ok":True})

    msg=payload.get("message") or {}; chat=msg.get("chat") or {}; chat_id=chat.get("id"); text=(msg.get("text") or "").strip()
    if chat_id is None: return web.json_response({"ok":True})
    if text.startswith("/start") or text.startswith("/help"):
        reply=(f"🤖 <b>{escape('@'+(conn[3] or 'Reseller Bot'))}</b>\n\n"
               "Premium Reseller Bot is connected.\n\n"
               "🛍 Buy products • 💰 Wallet • 🧾 Orders • 🤖 AI Support\n\n"
               "Use the buttons below or <code>/buy PRODUCT_ID</code>.")
        await _connected_bot_send(token,chat_id,reply,_connected_bot_keyboard())
    elif text.startswith("/balance") or text.startswith("/wallet"):
        u=db_query("SELECT balance FROM users WHERE user_id=?",(user_id,),fetchone=True)
        reply=f"💰 <b>Wallet Balance:</b> ₹{float(u[0] or 0):.2f}" if u else "❌ Account unavailable."
        await _connected_bot_send(token,chat_id,reply,_connected_bot_keyboard())
    elif text.startswith("/products"):
        await _connected_bot_send(token,chat_id,await _connected_bot_products(user_id),_connected_bot_keyboard())
    elif text.startswith("/orders"):
        await _connected_bot_send(token,chat_id,await _connected_bot_orders(user_id),_connected_bot_keyboard())
    elif text.startswith("/ai"):
        question=text[3:].strip()
        if not question:
            await _connected_bot_send(token,chat_id,"🤖 Ask something after <code>/ai</code>. Example: <code>/ai bot kese use karu?</code>",_connected_bot_keyboard())
        else:
            local_answer,should_escalate=_ai_local_answer(question,user_id)
            answer=await ai_remote_answer(question,user_id,history=None) or local_answer
            if should_escalate:
                await _ai_issue_escalate(user_id,question,answer)
            await _connected_bot_send(token,chat_id,answer,_connected_bot_keyboard())
    elif text.startswith("/buy"):
        parts=text.split()
        if len(parts)<2 or not parts[1].isdigit():
            reply="❌ <b>Usage:</b> <code>/buy PRODUCT_ID</code> or <code>/buy PRODUCT_ID ANDROID_ID</code>"
        else:
            android_id=parts[2].strip()[:200] if len(parts)>2 else ""
            result=await _api_purchase(user_id,int(parts[1]),android_id)
            if result.get("ok"):
                data=result.get("data") or {}
                key=escape(str(data.get("key") or ""))
                reply=f"✅ <b>Purchase Successful</b>\n\n📦 {escape(str(data.get('product_name') or 'Product'))}\n💰 Paid: ₹{float(data.get('price') or 0):.2f}\n🔑 <code>{key}</code>"
            else:
                reply=f"❌ <b>Purchase Failed</b>\n\n{escape(str(result.get('error') or 'Unknown error'))}"
        await _connected_bot_send(token,chat_id,reply,_connected_bot_keyboard())
    else:
        await _connected_bot_send(token,chat_id,"ℹ️ Use /start, /products, /balance, /orders, /buy PRODUCT_ID or /ai your question.",_connected_bot_keyboard())
    return web.json_response({"ok":True})

@dp.callback_query(F.data == "reseller_api_status")
async def reseller_api_status(call: CallbackQuery):
    u=db_query("SELECT is_reseller,balance FROM users WHERE user_id=?",(call.from_user.id,),fetchone=True)
    access=_bot_api_access(call.from_user.id)
    if not u or not u[0] or not access or not access[0]:
        return await call.answer("🔒 Bot API activation required.",show_alert=True)
    key=_reseller_api_record(call.from_user.id)
    conn=db_query("SELECT bot_username,enabled,last_update_at FROM reseller_bot_connections WHERE user_id=? ORDER BY id DESC LIMIT 1",(call.from_user.id,),fetchone=True)
    last=(datetime.fromtimestamp(conn[2]).strftime("%d-%m-%Y %H:%M") if conn and conn[2] else "Never")
    text=("📊 <b>BOT API STATUS</b>\n\n"
          f"🔑 API: {'🟢 Active' if key and key[4] else '🔴 Not generated'}\n"
          f"📈 Requests: <b>{int(key[6] or 0) if key else 0}</b>\n"
          f"🔗 Connected Bot: <b>{escape('@'+(conn[0] or 'Unknown')) if conn and conn[1] else 'Not connected'}</b>\n"
          f"🕐 Last webhook activity: <b>{last}</b>\n"
          f"💰 Wallet: <b>₹{float(u[1] or 0):.2f}</b>")
    await call.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back",callback_data="menu_bot_api_system",style="danger")]]),parse_mode="HTML")

# Admin Bot API management
@dp.callback_query(F.data == "admin_bot_api")
async def admin_bot_api(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    enabled = get_setting("bot_api_enabled", "ON").upper()
    base = get_setting("bot_api_public_url", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "") or "Not configured"
    rate = get_setting("bot_api_rate_limit", "60")
    text = (
        "🔑 <b>RESELLER BOT API MANAGEMENT</b>\n\n"
        f"Status: <b>{'🟢 ON' if enabled == 'ON' else '🔴 OFF'}</b>\n"
        f"Public URL: <code>{escape(base)}</code>\n"
        f"Rate limit: <b>{escape(rate)} requests/minute</b>\n\n"
        "Each reseller gets a private API key. Regenerating a key immediately invalidates the old one."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'🔴 Disable' if enabled == 'ON' else '🟢 Enable'} Bot API", callback_data="admin_bot_api_toggle", style="danger" if enabled == "ON" else "success")],
        [InlineKeyboardButton(text="🌐 Set Public URL", callback_data="admin_bot_api_url", style="primary")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel_back", style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "admin_bot_api_toggle")
async def admin_bot_api_toggle(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cur = get_setting("bot_api_enabled", "ON").upper()
    set_setting("bot_api_enabled", "OFF" if cur == "ON" else "ON")
    await admin_bot_api(call, None)

@dp.callback_query(F.data == "admin_bot_api_url")
async def admin_bot_api_url_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text(
        "🌐 Send the public base URL of this bot API. Example:\n<code>https://your-service.example.com</code>",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    await state.set_state(AdminStates.bot_api_public_url)

@dp.message(AdminStates.bot_api_public_url)
async def admin_bot_api_url_save(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    value = (m.text or "").strip().rstrip("/")
    if not re.match(r"^https?://[^\s]+$", value):
        return await m.answer("❌ Invalid URL. Use http:// or https:// URL.")
    set_setting("bot_api_public_url", value)
    await state.clear()
    await m.answer("✅ Bot API public URL saved.", reply_markup=admin_kb(), parse_mode="HTML")

# ==============================================================================
# EXTERNAL KEY GENERATION API
# ==============================================================================
def normalize_api_duration(duration: str) -> str:
    """Normalize the package name into the duration format expected by the API."""
    value = str(duration or "").strip()
    if not value:
        return value

    # Normalize whitespace
    value = re.sub(r"\s+", " ", value)
    
    # Define exact mapping for your API format
    # API expects: "X Hours" or "X DaYs" (with capital D and Y)
    duration_map = {
        # Hours - API expects "X Hours"
        "1 hour": "1 Hours",
        "1 hours": "1 Hours",
        "1hr": "1 Hours",
        "1h": "1 Hours",
        "2 hour": "2 Hours",
        "2 hours": "2 Hours",
        "2hr": "2 Hours",
        "3 hour": "3 Hours",
        "3 hours": "3 Hours",
        "3hr": "3 Hours",
        "6 hour": "6 Hours",
        "6 hours": "6 Hours",
        "6hr": "6 Hours",
        "12 hour": "12 Hours",
        "12 hours": "12 Hours",
        "12hr": "12 Hours",
        
        # Days - API expects "X DaYs" (capital D and Y)
        "1 day": "1 DaYs",
        "1 days": "1 DaYs",
        "1d": "1 DaYs",
        "2 day": "2 DaYs",
        "2 days": "2 DaYs",
        "2d": "2 DaYs",
        "3 day": "3 DaYs",
        "3 days": "3 DaYs",
        "3d": "3 DaYs",
        "5 day": "5 DaYs",
        "5 days": "5 DaYs",
        "5d": "5 DaYs",
        "7 day": "7 DaYs",
        "7 days": "7 DaYs",
        "7d": "7 DaYs",
    }
    
    # Check exact matches first (case insensitive)
    lower_val = value.lower()
    for pattern, result in duration_map.items():
        if lower_val == pattern.lower():
            return result
    
    # Check if it's already in correct format
    if value in ["1 Hours", "2 Hours", "3 Hours", "6 Hours", "12 Hours", 
                 "1 DaYs", "2 DaYs", "3 DaYs", "5 DaYs", "7 DaYs"]:
        return value
    
    # Try to extract number and determine unit
    match = re.match(r"(\d+)\s*(hour|hours|hr|hrs|h|day|days|d)", value, re.IGNORECASE)
    if match:
        number = match.group(1)
        unit = match.group(2).lower()
        if unit in ["hour", "hours", "hr", "hrs", "h"]:
            return f"{number} Hours"
        if unit in ["day", "days", "d"]:
            return f"{number} DaYs"
    
    # If it's just a number, treat as hours
    if value.isdigit():
        return f"{value} Hours"
    
    # Return as-is if nothing matches (fallback)
    return value

async def fetch_external_key_legacy(product_id: str, duration: str, android_id: str = "") -> dict:
    """Buy a key using a fresh aiohttp session for every API attempt."""
    url = get_setting("external_api_url", "https://adminpanels.shop/api/reseller_v1.php").strip()
    api_key = get_setting("external_api_key", "").strip()
    master_key = get_setting("external_master_key", "").strip()

    if not url:
        return {"status": "error", "msg": "External API URL is not configured"}
    if not api_key:
        return {"status": "error", "msg": "External API key is not configured"}

    product_id = str(product_id or "").strip()
    duration = str(duration or "").strip()
    if not product_id:
        return {"status": "error", "msg": "External API Product ID is empty"}
    if not duration:
        return {"status": "error", "msg": "Product duration is empty"}

    data = {"api_key": api_key, "action": "buy", "product_id": product_id, "duration": duration}
    if android_id:
        data["android_id"] = str(android_id).strip()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, text/plain, */*",
    }
    if master_key:
        headers["x-master-key"] = master_key

    timeout = aiohttp.ClientTimeout(total=15, connect=5, sock_connect=5, sock_read=10)

    for attempt in range(1, 3):
        try:
            logger.info("External API BUY attempt=%s product_id=%r duration=%r", attempt, product_id, duration)

            # Never reuse a ClientSession/connector from a previous attempt.
            connector = aiohttp.TCPConnector(family=socket.AF_INET, force_close=True, ssl=True)
            try:
                async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                    async with session.post(url, data=data, headers=headers, allow_redirects=True) as resp:
                        raw = await resp.text()
                        logger.info("External API BUY response: HTTP %s body=%s", resp.status, raw[:1000])

                        if resp.status != 200:
                            return {"status": "error", "msg": f"HTTP {resp.status}: {raw[:500]}"}
                        if not raw.strip():
                            return {"status": "error", "msg": "API returned an empty response"}
                        try:
                            result = json.loads(raw)
                        except json.JSONDecodeError:
                            return {"status": "error", "msg": f"API returned invalid JSON: {raw[:300]}"}
                        if not isinstance(result, dict):
                            return {"status": "error", "msg": "API returned an invalid response object"}
                        return result
            finally:
                if not connector.closed:
                    await connector.close()

        except (aiohttp.ClientConnectorError, aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, asyncio.TimeoutError) as exc:
            logger.warning("External API connection attempt %s failed: %s", attempt, exc)
            if attempt == 1:
                await asyncio.sleep(1)
                continue
            return {"status": "error", "msg": f"API connection failed: {type(exc).__name__}: {exc}"}
        except aiohttp.ClientError as exc:
            logger.exception("External API client error")
            return {"status": "error", "msg": f"API client error: {exc}"}
        except Exception as exc:
            logger.exception("API unexpected error")
            return {"status": "error", "msg": f"API unexpected error: {exc}"}

    return {"status": "error", "msg": "API request failed after retries"}


# ==============================================================================
# MULTI API ENGINE + LOCAL AI/PASTE CODE BUILDER
# ==============================================================================
API_SLOT_MAX = 5

def _template_value(v, product_id, duration, android_id):
    if isinstance(v,str):
        return (
            v.replace('{{product_id}}', str(product_id))
             .replace('{{variant_id}}', str(product_id))
             .replace('{{duration}}', str(duration))
             .replace('{{android_id}}', str(android_id or ''))
        )
    if isinstance(v,dict): return {k:_template_value(x,product_id,duration,android_id) for k,x in v.items()}
    if isinstance(v,list): return [_template_value(x,product_id,duration,android_id) for x in v]
    return v

def _safe_json_loads(text, default):
    try: return json.loads(text)
    except Exception: return default

def analyze_api_code(code: str) -> dict:
    raw=(code or '').strip()
    if not raw: return {'ok':False,'error':'Paste API code first.'}
    m=re.search(r'https?://[^\s\'"`<>]+',raw)
    if not m: return {'ok':False,'error':'Could not detect an HTTP/HTTPS URL.'}
    url=m.group(0).rstrip('),;')
    method='POST' if re.search(r'\b(post|requests\.post|session\.post|curl[^\n]*-X\s*POST)\b',raw,re.I) else 'GET'
    headers={}
    python_headers = {}
    python_body = {}
    try:
        parsed_tree = ast.parse(raw)
        for node in ast.walk(parsed_tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if not isinstance(target, ast.Name) or not isinstance(node.value, (ast.Dict,)):
                    continue
                parsed_value = ast.literal_eval(node.value)
                if not isinstance(parsed_value, dict):
                    continue
                if target.id.lower() == 'headers':
                    python_headers.update({str(k): str(v) for k, v in parsed_value.items()})
                elif target.id.lower() in {'data', 'payload', 'body'}:
                    python_body.update({str(k): str(v) for k, v in parsed_value.items()})
    except (SyntaxError, ValueError, TypeError):
        pass
    headers.update(python_headers)
    for x in re.finditer(r'(?:-H|--header)\s+[\'"]([^\'"]+)[\'"]',raw):
        if ':' in x.group(1): k,v=x.group(1).split(':',1); headers[k.strip()]=v.strip()
    if not python_headers:
        hm=re.search(r'headers\s*=\s*\{([^\n]*)\}',raw,re.S)
        if hm:
            for k,v in re.findall(r'[\'"]([^\'"]+)[\'"]\s*:\s*[\'"]([^\'"]*)[\'"]',hm.group(1)): headers[k]=v

    # Also understand PHP arrays such as:
    # $headers = ['x-master-key' => '...', 'Content-Type' => '...'];
    php_headers = re.search(r'\$headers\s*=\s*\[(.*?)\]\s*;', raw, re.S | re.I)
    if php_headers:
        for k, v in re.findall(
            r"""['"]([^'"]+)['"]\s*=>\s*['"]([^'"]*)['"]""",
            php_headers.group(1),
        ):
            headers[k] = v

    sensitive_headers = {
        'authorization', 'x-api-key', 'api-key', 'x-master-key',
        'x-master-key', 'token', 'access-token', 'api-token',
    }
    requires_api_key = False
    for k in list(headers):
        if k.lower() in sensitive_headers:
            headers[k] = '{{api_key}}'
            requires_api_key = True

    body=dict(python_body)
    body_source = raw
    php_data = re.search(r'\$data\s*=\s*\[(.*?)\]\s*;', raw, re.S | re.I)
    if php_data:
        body_source = php_data.group(1)
        pairs = re.findall(
            r"""['"]([A-Za-z0-9_.-]+)['"]\s*=>\s*(['"]?)([^,'"]+)\2""",
            body_source,
        )
        for k, _, v in pairs:
            v = v.strip()
            if k.lower() in {'variant_id', 'product_id'}:
                v = '{{product_id}}'
            body[k] = v
    elif not python_body:
        pairs = re.findall(
            r"""['"]([A-Za-z0-9_.-]+)['"]\s*:\s*['"]([^'"]*)['"]""",
            body_source,
        )
        for k, v in pairs:
            if k.lower() not in {'url','method','content-type','accept','authorization'}:
                body.setdefault(k, '{{product_id}}' if k.lower() in {'variant_id', 'product_id'} else v)

    if not body: body={'api_key':'{{api_key}}','action':'buy','product_id':'{{product_id}}','duration':'{{duration}}'}
    safe_source = re.sub(
        r"""(['"](?:x-master-key|authorization|x-api-key|api-key|token)['"]\s*(?:=>|:)\s*['"])[^'"]*(['"])""",
        r'\1{{api_key}}\2',
        raw,
        flags=re.I,
    )
    return {
        'ok': True,
        'url': url,
        'method': method,
        'headers': headers,
        'body': body,
        'content_type': headers.get('Content-Type', headers.get('content-type', 'application/json')),
        'source_code': safe_source[:20000],
        'requires_api_key': requires_api_key,
    }

def get_api_slots():
    return db_query('SELECT slot,name,url,method,headers_json,body_json,content_type,enabled,priority,source_code,last_status FROM api_providers ORDER BY priority ASC, slot ASC',fetchall=True) or []

def save_api_slot(slot,cfg,name):
    db_query('''INSERT OR REPLACE INTO api_providers(slot,name,url,method,headers_json,body_json,content_type,enabled,priority,source_code,last_status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(slot,name,cfg.get('url',''),cfg.get('method','POST'),json.dumps(cfg.get('headers',{})),json.dumps(cfg.get('body',{})),cfg.get('content_type','application/json'),1,slot,cfg.get('source_code',''),'configured'))

def _normalize_api_result(result):
    if not isinstance(result,dict): return {'status':'error','msg':'Invalid API response'}
    data=result.get('data') if isinstance(result.get('data'),dict) else {}
    keys = result.get('keys')
    first_key = keys[0] if isinstance(keys, list) and keys else None
    ok = (
        str(result.get('status','')).lower() in {'success','ok','true','1'}
        or result.get('success') is True
        or result.get('ok') is True
        or bool(result.get('key') or result.get('license_key') or data.get('key') or first_key)
    )
    if ok:
        result['status']='success'
        if not result.get('key') and first_key:
            result['key'] = first_key
    elif not result.get('msg') and result.get('error'):
        result['msg'] = str(result.get('error'))
    return result

async def fetch_multi_api_key(product_id,duration,android_id='',preferred_slot=0):
    slots=get_api_slots()
    if not slots: return await fetch_external_key_legacy(product_id,duration,android_id)
    if preferred_slot:
        # Try the product-selected API first, then keep the other enabled
        # providers available as failover routes.
        preferred=[row for row in slots if int(row[0]) == int(preferred_slot)]
        fallback=[row for row in slots if int(row[0]) != int(preferred_slot)]
        slots=preferred+fallback
    errors=[]; timeout=aiohttp.ClientTimeout(total=15,connect=5,sock_connect=5,sock_read=10)
    for row in slots[:API_SLOT_MAX]:
        slot,name,url,method,hj,bj,ctype,enabled,priority,source,last=row
        if not enabled or not url: continue
        headers=_template_value(_safe_json_loads(hj,{}),product_id,duration,android_id)
        body=_template_value(_safe_json_loads(bj,{}),product_id,duration,android_id)
        key=get_setting(f'api_slot_{slot}_key','') or get_setting('external_api_key','')
        if isinstance(headers,dict): headers={k:(key if str(v)=='{{api_key}}' else v) for k,v in headers.items()}
        if isinstance(body,dict): body={k:(key if str(v)=='{{api_key}}' else v) for k,v in body.items()}
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if str(method).upper()=='GET':
                    async with session.get(url,params=body,headers=headers) as resp: raw=await resp.text(); code=resp.status
                elif 'application/x-www-form-urlencoded' in str(ctype).lower():
                    async with session.post(url,data=body,headers=headers) as resp: raw=await resp.text(); code=resp.status
                else:
                    async with session.post(url,json=body,headers=headers) as resp: raw=await resp.text(); code=resp.status
            if code>=400: raise RuntimeError(f'HTTP {code}: {raw[:250]}')
            result=_normalize_api_result(json.loads(raw) if raw.strip() else {})
            db_query('UPDATE api_providers SET last_status=? WHERE slot=?',(f'HTTP {code}',slot))
            if result.get('status')=='success': return result
            errors.append(f'{name or slot}: {result.get("msg") or result.get("error") or "rejected"}')
        except Exception as e:
            errors.append(f'{name or slot}: {str(e)[:150]}')
            db_query('UPDATE api_providers SET last_status=? WHERE slot=?',(f'error: {str(e)[:120]}',slot))
    return {'status':'error','msg':'All configured APIs failed: '+' | '.join(errors[:5])}

fetch_external_key=fetch_multi_api_key

@dp.callback_query(F.data=='admin_multi_api')
async def admin_multi_api(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): return
    rows=get_api_slots(); text='🧩 <b>MULTI API MANAGER</b>\n\n'
    if rows:
        for r in rows[:API_SLOT_MAX]: text+=f'<b>#{r[0]} {r[1] or "API"}</b> — {"🟢" if r[7] else "🔴"} — <code>{r[2][:55]}</code>\nStatus: {r[10] or "unknown"}\n\n'
    else: text+='No API slots configured yet.\n\n'
    kb=[[InlineKeyboardButton(text='➕ Add / Paste API',callback_data='admin_ai_api',style='success')]]
    for i in range(1,API_SLOT_MAX+1): kb.append([InlineKeyboardButton(text=f'Configure API Slot {i}',callback_data=f'admin_api_slot_{i}',style='primary')])
    kb.append([InlineKeyboardButton(text='🔙 Back',callback_data='admin_panel_back',style='danger')])
    await call.message.edit_text(text,reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),parse_mode='HTML')

@dp.callback_query(F.data=='admin_ai_api')
async def admin_ai_api(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text(
        '🤖 <b>AI API BUILDER</b>\n\n'
        'Paste cURL / PHP / Python requests / aiohttp code. '
        'The local analyzer extracts URL, method, headers and body '
        '<b>without executing pasted code</b>.\n\n'
        '<b>Both API formats are supported:</b>\n'
        '• Legacy: <code>api_key + product_id + duration</code>\n'
        '• KeyPanel: <code>x-master-key + variant_id + quantity</code>\n\n'
        'Placeholders: <code>{{product_id}}</code> / <code>{{variant_id}}</code> '
        '<code>{{duration}}</code> <code>{{android_id}}</code> <code>{{api_key}}</code>',
        reply_markup=admin_back_kb(),
        parse_mode='HTML',
    )
    await state.set_state(AdminStates.multi_api_paste)

@dp.message(AdminStates.multi_api_paste)
async def multi_api_paste(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    cfg=analyze_api_code(m.text or '')
    if not cfg.get('ok'): return await m.answer('❌ '+cfg['error'],reply_markup=admin_kb(),parse_mode='HTML')
    await state.update_data(ai_cfg=cfg)
    await m.answer('✅ <b>API detected</b>\n\nURL: <code>'+cfg['url']+'</code>\nMethod: <b>'+cfg['method']+'</b>\nHeaders: <code>'+json.dumps(cfg['headers'])[:700]+'</code>\nBody: <code>'+json.dumps(cfg['body'])[:1000]+'</code>\n\nSend slot number <b>1-5</b>.',parse_mode='HTML')
    await state.set_state(AdminStates.multi_api_setup)

@dp.callback_query(F.data.regexp(r'^admin_api_slot_[1-5]$'))
async def admin_api_slot(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): return
    slot=int(call.data.rsplit('_',1)[1]); await state.update_data(target_slot=slot)
    await call.message.edit_text(f'⚙️ <b>API SLOT {slot}</b>\n\nPaste cURL / Python requests / aiohttp code for this provider.',reply_markup=admin_back_kb(),parse_mode='HTML')
    await state.set_state(AdminStates.multi_api_paste)

@dp.message(AdminStates.multi_api_setup)
async def save_multi_api_slot(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    d=await state.get_data(); cfg=d.get('ai_cfg')
    if d.get('awaiting_api_key'):
        key = (m.text or '').strip()
        slot = int(d.get('pending_slot') or 0)
        if not key:
            return await m.answer('❌ API/master key खाली नहीं हो सकती।')
        set_setting(f'api_slot_{slot}_key', key)
        save_api_slot(slot, cfg, f'API {slot}')
        await state.clear()
        return await m.answer(
            f'✅ API Slot {slot} saved securely. API key को message में repeat नहीं किया गया।',
            reply_markup=admin_kb(),
            parse_mode='HTML',
        )
    try: slot=int(d.get('target_slot') or (m.text or '').strip())
    except: return await m.answer('❌ Send only 1-5.')
    if not cfg or slot<1 or slot>API_SLOT_MAX: return await m.answer('❌ Invalid slot.')
    if cfg.get('requires_api_key'):
        await state.update_data(pending_slot=slot, awaiting_api_key=True)
        return await m.answer(
            f'🔐 API Slot {slot} के लिए master/API key भेजें.\n'
            'यह key database setting में save होगी और API request के sensitive header में जाएगी.',
            parse_mode='HTML',
        )
    save_api_slot(slot,cfg,f'API {slot}'); await state.clear(); await m.answer(f'✅ API Slot {slot} saved. Multi-API failover is active.',reply_markup=admin_kb(),parse_mode='HTML')

# ==============================================================================
# BINANCE PAY GATEWAY
# ==============================================================================
BINANCE_PAY_PATH='/binancepay/openapi/order'; BINANCE_QUERY_PATH='/binancepay/openapi/order/query'

def binance_headers(body_text):
    ts=str(int(time.time()*1000)); nonce=''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(32))
    secret=get_setting('binance_pay_secret_key','').strip(); cert=get_setting('binance_pay_certificate_sn','').strip()
    sig=hmac.new(secret.encode(),f'{ts}\n{nonce}\n{body_text}\n'.encode(),hashlib.sha512).hexdigest().upper()
    return {'Content-Type':'application/json','BinancePay-Timestamp':ts,'BinancePay-Nonce':nonce,'BinancePay-Certificate-SN':cert,'BinancePay-Signature':sig}

async def binance_pay_request(path,payload):
    body=json.dumps(payload,separators=(',',':'),ensure_ascii=False); api=get_setting('binance_pay_api_key','').strip()
    if not api or not get_setting('binance_pay_secret_key','').strip() or not get_setting('binance_pay_certificate_sn','').strip(): return {'status':'FAIL','errorMessage':'Binance Pay credentials are not configured.'}
    headers=binance_headers(body); headers['X-MBX-APIKEY']=api; base=get_setting('binance_pay_base_url','https://bpay.binanceapi.com').rstrip('/')
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(base+path,data=body.encode(),headers=headers) as resp:
                raw=await resp.text()
                try: return json.loads(raw)
                except: return {'status':'FAIL','errorMessage':f'HTTP {resp.status}: {raw[:300]}'}
    except Exception as e: return {'status':'FAIL','errorMessage':str(e)}

def make_binance_trade_no(user_id): return ('B'+str(int(time.time()*1000))[-12:]+str(user_id)[-8:])[:32]

@dp.callback_query(F.data=='admin_binance_pay')
async def admin_binance_pay(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text('🟡 <b>BINANCE PAY MERCHANT SETUP</b>\n\nSend: API Identity Key → API Secret Key → Certificate SN → Currency → INR rate.\n\nBinance Pay requires a merchant account and signed API access.',reply_markup=admin_back_kb(),parse_mode='HTML')
    await state.update_data(binance_step='api'); await state.set_state(AdminStates.binance_pay_setup)

@dp.message(AdminStates.binance_pay_setup)
async def save_binance_setup(m:Message,state:FSMContext):
    if not is_admin(m.from_user.id): return
    v=(m.text or '').strip(); d=await state.get_data(); step=d.get('binance_step','api')
    if v.lower()=='/cancel': await state.clear(); return await m.answer('Setup cancelled.',reply_markup=admin_kb())
    if step=='api': set_setting('binance_pay_api_key',v); await state.update_data(binance_step='secret'); return await m.answer('✅ API key saved. Send Secret Key.')
    if step=='secret': set_setting('binance_pay_secret_key',v); await state.update_data(binance_step='cert'); return await m.answer('✅ Secret saved. Send Certificate SN.')
    if step=='cert': set_setting('binance_pay_certificate_sn',v); await state.update_data(binance_step='currency'); return await m.answer('✅ Certificate saved. Send currency, e.g. USDT.')
    if step=='currency': set_setting('binance_pay_currency',v.upper() or 'USDT'); await state.update_data(binance_step='rate'); return await m.answer('Send INR conversion rate, e.g. 90 for ₹90 = 1 USDT.')
    try: rate=float(v); assert rate>0
    except: return await m.answer('❌ Rate must be positive.')
    set_setting('binance_pay_exchange_rate',str(rate)); await state.clear(); await m.answer('✅ Binance Pay setup saved.',reply_markup=admin_kb())

@dp.callback_query(F.data=='gateway_binance')
async def gateway_binance(call:CallbackQuery):
    await call.message.edit_text('🟡 <b>BINANCE PAY</b>\n\nSelect wallet credit amount:',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='₹100',callback_data='binance_amount_100'),InlineKeyboardButton(text='₹500',callback_data='binance_amount_500')],[InlineKeyboardButton(text='₹1000',callback_data='binance_amount_1000'),InlineKeyboardButton(text='Custom',callback_data='binance_custom')],[InlineKeyboardButton(text='BACK',callback_data='menu_add_balance',style='danger')]]),parse_mode='HTML')

async def create_binance_order(user_id,amount_inr,message_obj):
    rate=float(get_setting('binance_pay_exchange_rate','90') or 90); currency=get_setting('binance_pay_currency','USDT') or 'USDT'; crypto=round(amount_inr/rate,2); trade=make_binance_trade_no(user_id); now=int(time.time())
    payload={'env':{'terminalType':'WEB'},'merchantTradeNo':trade,'orderAmount':f'{crypto:.2f}','currency':currency,'goods':{'goodsType':'01','goodsCategory':'Z000','referenceGoodsId':'wallet','goodsName':'Wallet Balance'}}
    db_query('INSERT INTO binance_pay_txns(merchant_trade_no,user_id,amount_inr,amount_crypto,currency,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(trade,user_id,amount_inr,crypto,currency,'INITIAL',now,now))
    res=await binance_pay_request(BINANCE_PAY_PATH,payload)
    if res.get('status')!='SUCCESS': return await message_obj.edit_text('❌ <b>Binance Pay Error</b>\n'+str(res.get('errorMessage','Unknown error')),reply_markup=back_kb('gateway_binance'),parse_mode='HTML')
    data=res.get('data') or {}; url=data.get('checkoutUrl') or data.get('universalUrl') or data.get('deeplink') or data.get('qrContent')
    db_query('UPDATE binance_pay_txns SET prepay_id=?,updated_at=? WHERE merchant_trade_no=?',(data.get('prepayId',''),now,trade))
    rows=[]
    if url: rows.append([InlineKeyboardButton(text='🟡 Pay with Binance',url=url,style='success')])
    rows += [[InlineKeyboardButton(text='🔄 Verify Payment',callback_data=f'binverify_{trade}',style='primary')],[InlineKeyboardButton(text='Cancel',callback_data='menu_add_balance',style='danger')]]
    await message_obj.edit_text(f'🟡 <b>BINANCE PAY ORDER</b>\n\nWallet credit: <b>₹{amount_inr:.2f}</b>\nPayable: <b>{crypto:.2f} {currency}</b>\nOrder: <code>{trade}</code>\n\nComplete payment, then tap Verify.',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),parse_mode='HTML')

@dp.callback_query(F.data.regexp(r'^binance_amount_(100|500|1000)$'))
async def binance_amount(call:CallbackQuery): await create_binance_order(call.from_user.id,float(call.data.rsplit('_',1)[1]),call.message)

@dp.callback_query(F.data=='binance_custom')
async def binance_custom(call:CallbackQuery,state:FSMContext):
    await call.message.edit_text('Send INR amount (minimum ₹10):',reply_markup=back_kb('gateway_binance'),parse_mode='HTML'); await state.set_state(UserStates.custom_amount_input); await state.update_data(payment_gateway='binance')

async def verify_binance_trade(trade):
    row=db_query('SELECT user_id,amount_inr,amount_crypto,status FROM binance_pay_txns WHERE merchant_trade_no=?',(trade,),fetchone=True)
    if not row: return {'ok':False,'msg':'Order not found'}
    user_id,amount_inr,amount_crypto,status=row
    if status=='PAID': return {'ok':True,'already':True,'amount':amount_inr}
    res=await binance_pay_request(BINANCE_QUERY_PATH,{'merchantTradeNo':trade})
    if res.get('status')!='SUCCESS': return {'ok':False,'msg':res.get('errorMessage','Query failed')}
    data=res.get('data') or {}; remote=str(data.get('status','')).upper(); total=float(data.get('totalFee') or 0)
    if remote=='PAID' and abs(total-float(amount_crypto))<0.01:
        db_query("UPDATE binance_pay_txns SET status='PAID',transaction_id=?,updated_at=? WHERE merchant_trade_no=? AND status!='PAID'",(data.get('transactionId',''),int(time.time()),trade))
        if not db_query('SELECT 1 FROM transactions WHERE order_id=?',(trade,),fetchone=True):
            db_query("INSERT INTO transactions(order_id,user_id,amount_inr,gateway_amount,status,timestamp) VALUES(?,?,?,?,?,?)",(trade,user_id,amount_inr,amount_crypto,'success',int(time.time())))
            u=db_query('SELECT balance FROM users WHERE user_id=?',(user_id,),fetchone=True)
            if u: db_query('UPDATE users SET balance=? WHERE user_id=?',(u[0]+amount_inr,user_id))
            await send_advanced_notification(user_id,'DEPOSIT',float(amount_inr),product=trade,gateway='Binance Pay')
            log_activity(user_id,'DEPOSIT_SUCCESS',f'Amount: {amount_inr}, Gateway: Binance Pay, Order: {trade}')
        return {'ok':True,'amount':amount_inr}
    return {'ok':False,'pending':True,'msg':f'Binance status: {remote}'}

@dp.callback_query(F.data.startswith('binverify_'))
async def binverify(call:CallbackQuery):
    r=await verify_binance_trade(call.data.split('_',1)[1])
    if r.get('ok'): return await call.message.edit_text(f'✅ <b>Binance Payment Verified!</b>\n₹{r["amount"]:.2f} credited to your wallet.',reply_markup=back_kb('menu_add_balance'),parse_mode='HTML')
    await call.answer('⏳ '+r.get('msg','Payment not confirmed yet.'),show_alert=True)

async def binance_pay_auto_verify_task():
    while True:
        try:
            rows=db_query("SELECT merchant_trade_no FROM binance_pay_txns WHERE status NOT IN ('PAID','EXPIRED') ORDER BY created_at ASC LIMIT 20",fetchall=True) or []
            for (trade,) in rows: await verify_binance_trade(trade)
        except Exception as e: logger.warning('Binance auto verifier: %s',e)
        await asyncio.sleep(20)

@dp.callback_query(F.data == "admin_setup_external_api")
async def admin_setup_external_api(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    url = get_setting("external_api_url", "")
    key = get_setting("external_api_key", "")
    master = get_setting("external_master_key", "")
    mask = lambda x: (x[:4] + "••••" + x[-4:]) if len(x) > 8 else ("Configured" if x else "Not set")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Set API URL", callback_data="admin_set_ext_url", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
        [InlineKeyboardButton(text="Set API Key", callback_data="admin_set_ext_key", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
        [InlineKeyboardButton(text="Set Master Key", callback_data="admin_set_ext_master", icon_custom_emoji_id=get_emoji_icon("info_icon"), style="primary")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel_back", icon_custom_emoji_id=get_emoji_icon("back"), style="danger")]
    ])
    text = ("🔗 <b>External Key API Configuration</b>\n\n"
            f"URL: <code>{url or 'Not set'}</code>\n"
            f"API Key: <code>{mask(key)}</code>\n"
            f"Master Key: <code>{mask(master)}</code>\n\n"
            "Products can be switched to API generation from the Add Product flow.")
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "admin_set_ext_url")
async def set_ext_url(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("Enter External API URL:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_ext_url)

@dp.message(AdminStates.wait_for_ext_url)
async def save_ext_url(m: Message, state: FSMContext):
    value = m.text.strip()
    if not value.startswith(("http://", "https://")):
        return await m.answer("❌ URL must start with http:// or https://")
    set_setting("external_api_url", value)
    await m.answer("✅ External API URL saved.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_ext_key")
async def set_ext_key(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("Enter External API Key:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_ext_key)

@dp.message(AdminStates.wait_for_ext_key)
async def save_ext_key(m: Message, state: FSMContext):
    set_setting("external_api_key", m.text.strip())
    await m.answer("✅ External API Key saved.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_ext_master")
async def set_ext_master(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("Enter External API Master Key:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.wait_for_ext_master)

@dp.message(AdminStates.wait_for_ext_master)
async def save_ext_master(m: Message, state: FSMContext):
    set_setting("external_master_key", m.text.strip())
    await m.answer("✅ External API Master Key saved.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

if __name__ == "__main__":
    _lock_file = None
    try:
        import fcntl
        _lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bot_process.lock")
        _lock_file = open(_lock_path, "w")
        fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file.write(str(os.getpid())); _lock_file.flush()
    except (BlockingIOError, OSError):
        logger.error("Another bot process is already running; exiting duplicate process cleanly.")
        sys.exit(0)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("System shutting down gracefully. Goodbye.")
    finally:
        if _lock_file is not None:
            try:
                fcntl.flock(_lock_file.fileno(), fcntl.LOCK_UN); _lock_file.close()
            except Exception:
                pass
