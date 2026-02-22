#!/usr/bin/env python3
"""
🌸 Flower Delivery Telegram Bot + GREENGO Payment Gateway
=========================================================
Установка зависимостей:
    pip install python-telegram-bot==20.7 aiohttp

Запуск:
    python flower_bot.py

Настройка:
    1. BOT_TOKEN     — получить у @BotFather
    2. ADMIN_CHAT_ID — ваш Telegram ID (узнать у @userinfobot)
    3. GREENGO_SECRET — Api-Secret из личного кабинета greengo.cc
    4. GREENGO_WALLET — ваш BTC-кошелёк для вывода средств
"""

import logging
import aiohttp

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ══════════════════════════════════════════════════════════════
#  ⚙️  НАСТРОЙКИ — ОБЯЗАТЕЛЬНО ЗАМЕНИТЕ НА СВОИ!
# ══════════════════════════════════════════════════════════════
BOT_TOKEN       = "7950914851:AAFkIJvqoXgfjA2mB1Nq97n8YkYRKD2CCm8"         # @BotFather
ADMIN_CHAT_ID   = 7295633243                     # @userinfobot → ваш ID
GREENGO_SECRET  = "ZQVBCYyEAuIm2Y1P2yGaarX2QgPeAJteGGVnACVu41ymUhwDHhk1V3bgLPx3ouEg"     # из личного кабинета greengo.cc
GREENGO_WALLET  = "TFnhLa6KYgCg2UpgsD6XDF3ofim5uYJ36L"  # ваш BTC-кошелёк для вывода

# ══════════════════════════════════════════════════════════════
#  🌸  КАТАЛОГ ТОВАРОВ
# ══════════════════════════════════════════════════════════════
CATALOG = {
    "roses": {
        "name": "🌹 Розы",
        "items": {
            "rose_red_7":    {"title": "7 красных роз",   "price": 1200, "emoji": "🌹"},
            "rose_red_15":   {"title": "15 красных роз",  "price": 2200, "emoji": "🌹"},
            "rose_mix_25":   {"title": "25 роз (микс)",   "price": 3500, "emoji": "🌸"},
            "rose_white_11": {"title": "11 белых роз",    "price": 1900, "emoji": "🤍"},
        }
    },
    "tulips": {
        "name": "🌷 Тюльпаны",
        "items": {
            "tulip_9":  {"title": "9 тюльпанов",  "price": 900,  "emoji": "🌷"},
            "tulip_15": {"title": "15 тюльпанов", "price": 1400, "emoji": "🌷"},
            "tulip_25": {"title": "25 тюльпанов", "price": 2200, "emoji": "🌷"},
        }
    },
    "bouquets": {
        "name": "💐 Букеты",
        "items": {
            "bouquet_spring":  {"title": "«Весенний»",  "price": 2500, "emoji": "💐"},
            "bouquet_tender":  {"title": "«Нежность»",  "price": 3200, "emoji": "🌸"},
            "bouquet_luxe":    {"title": "«Люкс»",      "price": 5500, "emoji": "👑"},
            "bouquet_wedding": {"title": "«Свадебный»", "price": 7000, "emoji": "💍"},
        }
    },
    "plants": {
        "name": "🪴 Комнатные растения",
        "items": {
            "orchid":    {"title": "Орхидея в горшке", "price": 1800, "emoji": "🌺"},
            "succulent": {"title": "Суккулент",         "price": 700,  "emoji": "🌵"},
            "ficus":     {"title": "Фикус",             "price": 2500, "emoji": "🌳"},
        }
    },
}

# ══════════════════════════════════════════════════════════════
#  Состояния диалога (ConversationHandler)
# ══════════════════════════════════════════════════════════════
(
    S_MAIN, S_CAT, S_ITEM, S_CART,
    S_NAME, S_PHONE, S_ADDRESS, S_DATE, S_COMMENT, S_PAY
) = range(10)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  💳  GREENGO API
#  Документация: https://greengo.cc/instruction
# ══════════════════════════════════════════════════════════════

GG_HEADERS = {
    "Api-Secret": GREENGO_SECRET,
    "Content-Type": "application/json",
}

async def gg_create(amount: int, method: str) -> dict | None:
    """
    POST https://api.greengo.cc/api/v2/order/create
    Тело: { payment_method, wallet, from_amount }
    Ответ: { response:"success", items:[{ order_id, wallet_payment,
              amount_payable, fast_link, order_status, ... }] }
    """
    body = {
        "payment_method": method,
        "wallet": GREENGO_WALLET,
        "from_amount": str(amount),
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.greengo.cc/api/v2/order/create",
                json=body, headers=GG_HEADERS,
                timeout=aiohttp.ClientTimeout(total=12)
            ) as r:
                data = await r.json()
                log.info("GG create → %s", data)
                return data
    except Exception as e:
        log.error("GG create error: %s", e)
        return None


async def gg_check(order_id: str) -> str:
    """
    POST https://api.greengo.cc/api/v2/order/check
    Тело: { order_id: ["id"] }
    Возвращает order_status строкой.
    Статусы: unconfirmed | awaiting | payed | completed | autocanceled | canceled
    """
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.greengo.cc/api/v2/order/check",
                json={"order_id": [order_id]},
                headers=GG_HEADERS,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                data = await r.json()
                orders = data.get("data", {}).get("orders", [])
                if orders:
                    return orders[0].get("order_status", "unknown")
    except Exception as e:
        log.error("GG check error: %s", e)
    return "unknown"


async def gg_cancel(order_id: str) -> bool:
    """POST https://api.greengo.cc/api/v2/order/cancel"""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.greengo.cc/api/v2/order/cancel",
                json={"order_id": [order_id]},
                headers=GG_HEADERS,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                data = await r.json()
                return str(data.get("result", "")).lower() == "true"
    except Exception as e:
        log.error("GG cancel error: %s", e)
    return False


# ══════════════════════════════════════════════════════════════
#  🛒  КОРЗИНА — вспомогательные функции
# ══════════════════════════════════════════════════════════════

def cart(ctx) -> dict:
    return ctx.user_data.setdefault("cart", {})


def total(ctx) -> int:
    t = 0
    for iid, qty in cart(ctx).items():
        for cat in CATALOG.values():
            if iid in cat["items"]:
                t += cat["items"][iid]["price"] * qty
    return t


def cart_text(ctx) -> str:
    c = cart(ctx)
    if not c:
        return "Корзина пуста."
    lines = ["🛒 *Ваша корзина:*\n"]
    for iid, qty in c.items():
        for cat in CATALOG.values():
            if iid in cat["items"]:
                it = cat["items"][iid]
                lines.append(f"{it['emoji']} {it['title']} × {qty} = {it['price']*qty} ₽")
    lines.append(f"\n💰 *Итого: {total(ctx)} ₽*")
    return "\n".join(lines)


def main_kb():
    return ReplyKeyboardMarkup([
        ["🌸 Каталог", "🛒 Корзина"],
        ["📋 Мои заказы", "📞 Контакты"],
        ["ℹ️ О магазине"],
    ], resize_keyboard=True)


def pay_method_name(m: str) -> str:
    return {
        "card":         "💳 Банковская карта РФ",
        "sbp":          "📱 СБП",
        "sbp_sber":     "📱 СБП → Сбербанк",
        "sbp_alpha":    "📱 СБП → Альфа-Банк",
        "sbp_ozon":     "📱 СБП → Ozon Банк",
        "mobile":       "📞 Счёт телефона",
        "qr_code":      "🔲 QR-код",
    }.get(m, m)


def status_icon(s: str) -> str:
    return {
        "payed": "✅", "completed": "✅",
        "awaiting": "⏳", "unconfirmed": "🕐",
        "canceled": "❌", "autocanceled": "⏰",
    }.get(s, "❓")


# ══════════════════════════════════════════════════════════════
#  🚀  ОБРАБОТЧИКИ БОТА
# ══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    u = update.effective_user
    await update.message.reply_text(
        f"🌸 *Добро пожаловать, {u.first_name}!*\n\n"
        "Я бот магазина *FlowerShop* 🌺\n"
        "Свежие цветы с доставкой по городу!\n\n"
        "⏰ Работаем: 8:00 – 22:00\n"
        "🚚 Доставка: 1–3 часа\n"
        "💳 Оплата: карта, СБП, QR-код (через GREENGO)",
        parse_mode="Markdown", reply_markup=main_kb()
    )
    return S_MAIN


# ── Главное меню (кнопки клавиатуры) ──────────────────────────

async def on_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "🌸 Каталог":    return await show_catalog(update, ctx)
    if t == "🛒 Корзина":    return await show_cart_msg(update, ctx)
    if t == "📋 Мои заказы": return await show_orders(update, ctx)
    if t == "📞 Контакты":
        await update.message.reply_text(
            "📞 *Контакты FlowerShop:*\n\n"
            "📱 Телефон: +7 (999) 123-45-67\n"
            "💬 WhatsApp: +7 (999) 123-45-67\n"
            "📍 Адрес: ул. Цветочная, 1\n"
            "📧 Email: info@flowershop.ru",
            parse_mode="Markdown"
        )
    elif t == "ℹ️ О магазине":
        await update.message.reply_text(
            "🌸 *FlowerShop* — с 2015 года\n\n"
            "✅ Только свежие цветы\n"
            "✅ Авторские букеты\n"
            "✅ Быстрая доставка\n"
            "✅ Онлайн-оплата (GREENGO)\n\n"
            "💯 Более 5000 довольных клиентов!",
            parse_mode="Markdown"
        )
    return S_MAIN


async def show_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    orders = ctx.user_data.get("orders", [])
    if not orders:
        await update.message.reply_text("У вас пока нет заказов.")
    else:
        lines = ["📋 *Ваши заказы:*\n"]
        for i, o in enumerate(orders, 1):
            si = status_icon(o.get("pay_status", ""))
            lines.append(
                f"*#{i}* {si} — {o['total']} ₽\n"
                f"📍 {o['address']} | 📅 {o['date']}\n"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    return S_MAIN


# ── Каталог ───────────────────────────────────────────────────

async def show_catalog(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(cat["name"], callback_data=f"cat|{cid}")]
          for cid, cat in CATALOG.items()]
    await update.message.reply_text(
        "🌸 *Выберите категорию:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return S_CAT


async def on_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cid = q.data.split("|")[1]
    cat = CATALOG[cid]
    ctx.user_data["cur_cat"] = cid
    kb = [[InlineKeyboardButton(
               f"{it['emoji']} {it['title']} — {it['price']} ₽",
               callback_data=f"item|{iid}"
           )] for iid, it in cat["items"].items()]
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back|cat")])
    await q.edit_message_text(cat["name"] + "\n\nВыберите товар:",
                              reply_markup=InlineKeyboardMarkup(kb))
    return S_ITEM


async def on_item(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()

    if q.data == "back|cat":
        kb = [[InlineKeyboardButton(cat["name"], callback_data=f"cat|{cid}")]
              for cid, cat in CATALOG.items()]
        await q.edit_message_text("🌸 *Выберите категорию:*",
                                  parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
        return S_CAT

    if q.data == "go|cart":
        c = cart(ctx)
        if not c:
            await q.edit_message_text("🛒 Корзина пуста.")
            return S_MAIN
        kb = _cart_kb(ctx)
        await q.edit_message_text(cart_text(ctx), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(kb))
        return S_CART

    iid = q.data.split("|")[1]
    item = _find_item(iid)
    if not item:
        await q.answer("Товар не найден"); return S_ITEM

    c = cart(ctx)
    c[iid] = c.get(iid, 0) + 1

    kb = [
        [InlineKeyboardButton("➕ Ещё", callback_data=f"item|{iid}"),
         InlineKeyboardButton("🛒 Корзина", callback_data="go|cart")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"cat|{ctx.user_data.get('cur_cat','')}")],
    ]
    await q.edit_message_text(
        f"✅ *{item['emoji']} {item['title']}* добавлен!\n"
        f"В корзине: {c[iid]} шт.\n"
        f"Итого в корзине: {total(ctx)} ₽",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb)
    )
    return S_ITEM


def _find_item(iid: str) -> dict | None:
    for cat in CATALOG.values():
        if iid in cat["items"]:
            return cat["items"][iid]
    return None


def _cart_kb(ctx) -> list:
    rows = []
    for iid in cart(ctx):
        it = _find_item(iid)
        if it:
            rows.append([InlineKeyboardButton(f"❌ {it['title']}", callback_data=f"rm|{iid}")])
    rows.append([InlineKeyboardButton("🗑 Очистить", callback_data="clear|cart")])
    rows.append([InlineKeyboardButton("✅ Оформить заказ", callback_data="checkout")])
    return rows


# ── Корзина ───────────────────────────────────────────────────

async def show_cart_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    c = cart(ctx)
    if not c:
        await update.message.reply_text("🛒 Корзина пуста.\nДобавьте товары из каталога!")
        return S_MAIN
    await update.message.reply_text(
        cart_text(ctx), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(_cart_kb(ctx))
    )
    return S_CART


async def on_cart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()

    if q.data == "go|cart":
        c = cart(ctx)
        if not c:
            await q.edit_message_text("🛒 Корзина пуста."); return S_MAIN
        await q.edit_message_text(cart_text(ctx), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(_cart_kb(ctx)))
        return S_CART

    if q.data == "clear|cart":
        ctx.user_data["cart"] = {}
        await q.edit_message_text("🗑 Корзина очищена.")
        return S_MAIN

    if q.data.startswith("rm|"):
        iid = q.data.split("|")[1]
        cart(ctx).pop(iid, None)
        c = cart(ctx)
        if not c:
            await q.edit_message_text("🛒 Корзина пуста."); return S_MAIN
        await q.edit_message_text(cart_text(ctx), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(_cart_kb(ctx)))
        return S_CART

    if q.data == "checkout":
        await q.edit_message_text(
            "📝 *Оформление заказа*\n\n*Шаг 1 из 5:* Введите ваше имя:",
            parse_mode="Markdown"
        )
        return S_NAME

    return S_CART


# ── Оформление заказа ─────────────────────────────────────────

async def on_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["o_name"] = update.message.text
    await update.message.reply_text(
        "*Шаг 2 из 5:* Введите номер телефона:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Отправить мой номер", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )
    return S_PHONE


async def on_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.contact:
        ctx.user_data["o_phone"] = update.message.contact.phone_number
    else:
        ctx.user_data["o_phone"] = update.message.text
    await update.message.reply_text(
        "*Шаг 3 из 5:* Введите адрес доставки (улица, дом, кв.):",
        parse_mode="Markdown", reply_markup=main_kb()
    )
    return S_ADDRESS


async def on_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["o_address"] = update.message.text
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Сегодня (3 ч)", callback_data="date|today"),
         InlineKeyboardButton("Завтра",         callback_data="date|tomorrow")],
        [InlineKeyboardButton("Через 2 часа",   callback_data="date|2h"),
         InlineKeyboardButton("Указать время",  callback_data="date|custom")],
    ])
    await update.message.reply_text(
        "*Шаг 4 из 5:* Когда доставить?", parse_mode="Markdown", reply_markup=kb
    )
    return S_DATE


async def on_date_btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    mp = {"date|today": "Сегодня (≈3 ч)", "date|tomorrow": "Завтра", "date|2h": "Через 2 часа"}
    if q.data in mp:
        ctx.user_data["o_date"] = mp[q.data]
        await q.edit_message_text(
            f"✅ Дата: {mp[q.data]}\n\n*Шаг 5 из 5:* Комментарий (или «нет»):",
            parse_mode="Markdown"
        )
        return S_COMMENT
    # custom
    await q.edit_message_text("📅 Введите удобное время (например: «завтра 14:00»):")
    return S_DATE


async def on_date_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["o_date"] = update.message.text
    await update.message.reply_text(
        "*Шаг 5 из 5:* Комментарий к заказу (или «нет»):",
        parse_mode="Markdown"
    )
    return S_COMMENT


async def on_comment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text
    ctx.user_data["o_comment"] = "—" if txt.strip().lower() == "нет" else txt

    t = total(ctx)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Банковская карта",  callback_data="pay|card")],
        [InlineKeyboardButton("📱 СБП",               callback_data="pay|sbp")],
        [InlineKeyboardButton("📱 СБП → Сбербанк",    callback_data="pay|sbp_sber")],
        [InlineKeyboardButton("📱 СБП → Альфа-Банк",  callback_data="pay|sbp_alpha")],
        [InlineKeyboardButton("🔲 QR-код",            callback_data="pay|qr_code")],
        [InlineKeyboardButton("📞 Счёт телефона",     callback_data="pay|mobile")],
    ])
    await update.message.reply_text(
        f"💰 *Сумма к оплате: {t} ₽*\n\nВыберите способ оплаты:",
        parse_mode="Markdown", reply_markup=kb
    )
    return S_PAY


# ── GREENGO: создание заявки и подтверждение ──────────────────

async def on_pay_method(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    method = q.data.split("|")[1]
    t = total(ctx)

    await q.edit_message_text(
        f"⏳ Создаём платёж на *{t} ₽*…\n"
        f"Способ: {pay_method_name(method)}",
        parse_mode="Markdown"
    )

    result = await gg_create(t, method)

    # ── Успешный ответ от GREENGO ──────────────────────────────
    if result and result.get("response") == "success":
        items = result.get("items", [])
        if items:
            od = items[0]
            oid       = od.get("order_id", "?")
            wallet    = od.get("wallet_payment", "")
            amount    = od.get("amount_payable", t)
            fast_link = od.get("fast_link", "")
            ctx.user_data["gg_order_id"] = oid

            if method == "card":
                pay_info = (
                    f"💳 *Переведите на карту:*\n\n"
                    f"`{wallet}`\n\n"
                    f"Сумма точно: *{amount} ₽*\n"
                    f"Комментарий к переводу: не указывать"
                )
            elif method in ("sbp", "sbp_sber", "sbp_alpha", "sbp_ozon"):
                pay_info = (
                    f"📱 *Перевод по СБП:*\n\n"
                    f"Номер: `{wallet}`\n"
                    f"Сумма: *{amount} ₽*"
                )
            elif method == "qr_code":
                pay_info = (
                    f"🔲 *Оплата по QR-коду:*\n\n"
                    f"Сумма: *{amount} ₽*\n\n"
                    + (f"Ссылка / QR: {fast_link}" if fast_link else "")
                )
            elif method == "mobile":
                pay_info = (
                    f"📞 *Пополнение счёта телефона:*\n\n"
                    f"Номер: `{wallet}`\n"
                    f"Сумма: *{amount} ₽*"
                )
            else:
                pay_info = f"Реквизиты: `{wallet}`\nСумма: *{amount} ₽*"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Я оплатил!", callback_data=f"paid|{oid}")],
                [InlineKeyboardButton("❌ Отменить",   callback_data=f"cancel|{oid}")],
            ])
            await q.edit_message_text(
                f"🧾 *Заявка #{oid} создана!*\n\n"
                f"{pay_info}\n\n"
                f"⚠️ Переводите точную сумму.\n"
                f"После оплаты нажмите «Я оплатил!»",
                parse_mode="Markdown", reply_markup=kb
            )
            return S_PAY

    # ── Ошибка GREENGO — оформляем без оплаты ─────────────────
    log.warning("GG order creation failed: %s", result)
    await _save_order(update.effective_user, ctx, pay_status="pending")
    await q.edit_message_text(
        "⚠️ Не удалось создать платёж через GREENGO.\n"
        "Ваш заказ принят! Менеджер свяжется с вами для оплаты.",
        reply_markup=None
    )
    ctx.user_data["cart"] = {}
    return S_MAIN


async def on_pay_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    action, oid = q.data.split("|", 1)

    if action == "paid":
        await q.edit_message_text("🔍 Проверяем оплату…")
        status = await gg_check(oid)

        if status in ("payed", "completed"):
            await q.edit_message_text(
                "🎉 *Оплата подтверждена!*\n\n"
                "Ваш заказ принят и передан флористам. 🌸\n"
                "Ждите — скоро доставим!",
                parse_mode="Markdown"
            )
            await _save_order(update.effective_user, ctx,
                              pay_status=status, gg_id=oid,
                              bot=update.get_bot())
            ctx.user_data["cart"] = {}
        else:
            txt = {
                "awaiting":    "⏳ Платёж ещё не поступил. Подождите пару минут.",
                "unconfirmed": "⏳ Заявка создана, ожидаем оплату.",
                "autocanceled":"❌ Время ожидания вышло. Создайте новый заказ.",
                "canceled":    "❌ Заявка отменена.",
            }.get(status, f"Статус: {status}")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Проверить снова", callback_data=f"paid|{oid}")],
                [InlineKeyboardButton("❌ Отменить",        callback_data=f"cancel|{oid}")],
            ])
            await q.edit_message_text(f"ℹ️ {txt}", reply_markup=kb)

    elif action == "cancel":
        ok = await gg_cancel(oid)
        msg = "✅ Заявка отменена." if ok else "⚠️ Не удалось отменить через API. Обратитесь в поддержку."
        await q.edit_message_text(msg)
        ctx.user_data["cart"] = {}

    return S_MAIN


async def _save_order(user, ctx, pay_status="pending", gg_id=None, bot=None):
    """Сохранить заказ в истории и уведомить администратора."""
    t = total(ctx)
    summary = cart_text(ctx)
    orders = ctx.user_data.setdefault("orders", [])
    orders.append({
        "total":      t,
        "address":    ctx.user_data.get("o_address", "—"),
        "date":       ctx.user_data.get("o_date", "—"),
        "pay_status": pay_status,
        "gg_id":      gg_id,
    })
    num = len(orders)

    si = status_icon(pay_status)
    admin_msg = (
        f"🛎 *НОВЫЙ ЗАКАЗ #{num}* {si}\n\n"
        f"👤 {user.first_name} (@{user.username or '—'}) | ID: `{user.id}`\n\n"
        f"{summary}\n\n"
        f"👤 Имя: {ctx.user_data.get('o_name','—')}\n"
        f"📱 Тел: {ctx.user_data.get('o_phone','—')}\n"
        f"📍 Адрес: {ctx.user_data.get('o_address','—')}\n"
        f"📅 Доставка: {ctx.user_data.get('o_date','—')}\n"
        f"💬 Комментарий: {ctx.user_data.get('o_comment','—')}\n"
        f"🏦 GREENGO ID: `{gg_id or '—'}`\n"
        f"💳 Статус оплаты: {pay_status}"
    )
    try:
        _bot = bot
        if _bot is None:
            from telegram import Bot
            _bot = Bot(token=BOT_TOKEN)
        await _bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_msg, parse_mode="Markdown")
    except Exception as e:
        log.warning("Admin notify failed: %s", e)


# ══════════════════════════════════════════════════════════════
#  🏁  ЗАПУСК
# ══════════════════════════════════════════════════════════════

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            S_MAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_menu)],
            S_CAT:  [CallbackQueryHandler(on_cat,  pattern=r"^cat\|")],
            S_ITEM: [
                CallbackQueryHandler(on_item, pattern=r"^item\|"),
                CallbackQueryHandler(on_item, pattern=r"^back\|cat"),
                CallbackQueryHandler(on_item, pattern=r"^go\|cart"),
            ],
            S_CART: [
                CallbackQueryHandler(on_cart, pattern=r"^(clear\|cart|rm\||checkout|go\|cart)"),
            ],
            S_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, on_name)],
            S_PHONE:   [
                MessageHandler(filters.CONTACT, on_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_phone),
            ],
            S_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_address)],
            S_DATE:    [
                CallbackQueryHandler(on_date_btn,  pattern=r"^date\|"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_date_text),
            ],
            S_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_comment)],
            S_PAY:     [
                CallbackQueryHandler(on_pay_method,  pattern=r"^pay\|"),
                CallbackQueryHandler(on_pay_confirm, pattern=r"^(paid|cancel)\|"),
            ],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    # Обработка кнопок «Оплатил / Отменить» вне диалога (после перезапуска бота)
    app.add_handler(CallbackQueryHandler(on_pay_confirm, pattern=r"^(paid|cancel)\|"))

    print("🌸 FlowerShop Bot запущен! Ctrl+C для остановки.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
