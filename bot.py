import os, json, asyncio, logging, httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode, ChatAction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MARKETS = {
    "il": {"flag":"\U0001f1ee\U0001f1f1","name":"\u05d9\u05e9\u05e8\u05d0\u05dc","nameHe":"\u05d9\u05e9\u05e8\u05d0\u05dc\u05d9","nameEn":"Israel","currency":"\u20aa (ILS)","lang":"Hebrew","google":"google.co.il"},
    "us": {"flag":"\U0001f1fa\U0001f1f8","name":"\u05d0\u05e8\u05d4\u05f4\u05d1","nameHe":"\u05d0\u05de\u05e8\u05d9\u05e7\u05d0\u05d9","nameEn":"United States","currency":"$ (USD)","lang":"English","google":"google.com"},
    "uk": {"flag":"\U0001f1ec\U0001f1e7","name":"\u05d1\u05e8\u05d9\u05d8\u05e0\u05d9\u05d4","nameHe":"\u05d1\u05e8\u05d9\u05d8\u05d9","nameEn":"United Kingdom","currency":"\u00a3 (GBP)","lang":"English","google":"google.co.uk"},
    "global": {"flag":"\U0001f30d","name":"\u05d2\u05dc\u05d5\u05d1\u05dc\u05d9","nameHe":"\u05d2\u05dc\u05d5\u05d1\u05dc\u05d9","nameEn":"Global","currency":"$ (USD)","lang":"various","google":"google.com"},
}

user_markets = {}

def get_stages(market_id, niche):
    m = MARKETS.get(market_id, MARKETS["il"])
    ctx = f'in the {m["nameEn"]} market ({m["google"]}), prices in {m["currency"]}'
    return [
        {"id":"google_search","label":"\U0001f50e \u05db\u05de\u05d5\u05ea \u05d7\u05d9\u05e4\u05d5\u05e9\u05d9\u05dd \u05d1\u05d2\u05d5\u05d2\u05dc",
         "prompt":f'Market research: "{niche}" {ctx}. Use web search. Top 10 keywords with monthly volume, total searches, 12-month trend, seasonality, buying intent %. Include {m["lang"]} keywords. ACTUAL NUMBERS. Hebrew only.'},
        {"id":"cpc_analysis","label":"\U0001f4b8 \u05e2\u05dc\u05d5\u05ea \u05e7\u05dc\u05d9\u05e7 (CPC)",
         "prompt":f'Google Ads specialist. CPC for "{niche}" {ctx}. Use web search. 1)Google Search CPC per keyword in {m["currency"]} 2)Google Shopping CPC 3)Facebook/Instagram CPC 4)TikTok CPC 5)Average CPC 6)Competition per platform 7)Daily budget recommendation {m["currency"]} 8)CPA estimate 9)ROAS benchmark 10)Best ad platform for {m["nameEn"]}. ALL in {m["currency"]}. ACTUAL NUMBERS. Hebrew only.'},
        {"id":"google_shopping","label":"\U0001f6d2 \u05e0\u05d9\u05ea\u05d5\u05d7 \u05d2\u05d5\u05d2\u05dc \u05e9\u05d5\u05e4\u05d9\u05e0\u05d2",
         "prompt":f'Google Shopping for "{niche}" {ctx}. Use web search. Products count, price range, avg price, top 5 sellers, competition, market gaps, shipping. ACTUAL NUMBERS. Hebrew only.'},
        {"id":"social_media","label":"\U0001f4f1 \u05e8\u05e9\u05ea\u05d5\u05ea \u05d7\u05d1\u05e8\u05ea\u05d9\u05d5\u05ea",
         "prompt":f'Social media for "{niche}" in {m["nameEn"]}. Use web search. Instagram, TikTok, Facebook, YouTube, local platforms, virality score 1-10, best platform, content strategy. ACTUAL NUMBERS. Hebrew only.'},
        {"id":"competitors","label":"\u2694\ufe0f \u05e0\u05d9\u05ea\u05d5\u05d7 \u05de\u05ea\u05d7\u05e8\u05d9\u05dd",
         "prompt":f'Competitors for "{niche}" in {m["nameEn"]} ecommerce. Use web search. Top 5-7 stores, TAM in {m["currency"]}, market structure, business models, barriers, competitive advantage, CAC, regulation. ACTUAL NUMBERS. Hebrew only.'},
        {"id":"sales_estimate","label":"\U0001f4b0 \u05ea\u05d7\u05d6\u05d9\u05ea \u05de\u05db\u05d9\u05e8\u05d5\u05ea",
         "prompt":f'Sales forecast NEW store "{niche}" in {m["nameEn"]}. {{prev_data}} Conservative 1-6mo, Optimistic 6-12mo, Year 1, Investment, ROI. All {m["currency"]}. Hebrew only.'},
        {"id":"summary","label":"\U0001f4cb \u05e1\u05d9\u05db\u05d5\u05dd \u05d5\u05d4\u05d7\u05dc\u05d8\u05d4",
         "prompt":f'Executive summary "{niche}" in {m["nameEn"]}. {{prev_data}} Score X/10, 3 key metrics incl CPC, GO/NO-GO, opportunity, risk, entry strategy with ad budget, bottom line. {m["currency"]}. Hebrew only.'},
    ]

async def call_claude(prompt):
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post("https://api.anthropic.com/v1/messages",
            headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},
            json={"model":"claude-sonnet-4-20250514","max_tokens":1500,
                  "tools":[{"type":"web_search_20250305","name":"web_search"}],
                  "messages":[{"role":"user","content":prompt}]})
        data = r.json()
        if "error" in data: raise Exception(data["error"].get("message","API Error"))
        return "\n".join([b["text"] for b in data.get("content",[]) if b.get("type")=="text"])

def trunc(text, mx=4000):
    return text[:mx]+"..." if len(text)>mx else text

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(f'{m["flag"]} {m["name"]}', callback_data=f"market_{mid}")] for mid,m in MARKETS.items()]
    user_markets[update.effective_user.id] = "il"
    await update.message.reply_text(
        "\U0001f52c *\u05e1\u05d5\u05db\u05df \u05de\u05d7\u05e7\u05e8 \u05e9\u05d5\u05e7 \u05dc\u05d0\u05d9\u05e7\u05d5\u05de\u05e8\u05e1*\n\n"
        "\u05e9\u05dc\u05d7 \u05e0\u05d9\u05e9\u05d4 \u05d5\u05d0\u05e0\u05d9 \u05d0\u05e8\u05d9\u05e5 7 \u05de\u05d5\u05d3\u05d5\u05dc\u05d9\u05dd:\n"
        "\U0001f50e \u05d7\u05d9\u05e4\u05d5\u05e9\u05d9\u05dd | \U0001f4b8 CPC | \U0001f6d2 \u05e9\u05d5\u05e4\u05d9\u05e0\u05d2\n"
        "\U0001f4f1 \u05e1\u05d5\u05e9\u05d9\u05d0\u05dc | \u2694\ufe0f \u05de\u05ea\u05d7\u05e8\u05d9\u05dd | \U0001f4b0 \u05de\u05db\u05d9\u05e8\u05d5\u05ea | \U0001f4cb GO/NO-GO\n\n"
        "\u05d1\u05d7\u05e8 \u05e9\u05d5\u05e7 \u05d9\u05e2\u05d3:",
        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

async def market_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    mid = q.data.replace("market_",""); user_markets[q.from_user.id] = mid; m = MARKETS[mid]
    await q.edit_message_text(f'{m["flag"]} *\u05e9\u05d5\u05e7: {m["name"]}*\n\n\u05e9\u05dc\u05d7 \u05e0\u05d9\u05e9\u05d4 \u05dc\u05d7\u05e7\u05d5\u05e8!\n\u05dc\u05de\u05e9\u05dc: "\u05de\u05d7\u05d1\u05d8 \u05e4\u05d0\u05d3\u05dc"\n\n/market \u05dc\u05e9\u05d9\u05e0\u05d5\u05d9 \u05e9\u05d5\u05e7', parse_mode=ParseMode.MARKDOWN)

async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(f'{m["flag"]} {m["name"]}', callback_data=f"market_{mid}")] for mid,m in MARKETS.items()]
    await update.message.reply_text("\U0001f30d \u05d1\u05d7\u05e8 \u05e9\u05d5\u05e7 \u05d9\u05e2\u05d3:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    niche = update.message.text.strip()
    if not niche or niche.startswith("/"): return
    uid = update.effective_user.id; mid = user_markets.get(uid,"il"); m = MARKETS[mid]

    await update.message.reply_text(f'\U0001f680 *\u05de\u05ea\u05d7\u05d9\u05dc \u05de\u05d7\u05e7\u05e8!*\n\U0001f4e6 {niche}\n{m["flag"]} {m["name"]}\n\n\u05d6\u05d4 \u05d9\u05d9\u05e7\u05d7 2-4 \u05d3\u05e7\u05d5\u05ea...', parse_mode=ParseMode.MARKDOWN)

    stages = get_stages(mid, niche); prev = {}
    for stage in stages:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        try:
            prompt = stage["prompt"]
            if "{prev_data}" in prompt:
                sm = "\n".join([f"{k}: {v[:400]}" for k,v in prev.items()])
                prompt = prompt.replace("{prev_data}", f"Data:\n{sm}")
            result = await call_claude(prompt); prev[stage["id"]] = result
            txt = f'{stage["label"]}\n{"="*25}\n\n{trunc(result,3900)}'
            try:
                await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await update.message.reply_text(txt)
        except Exception as e:
            logger.error(f'{stage["id"]}: {e}')
            await update.message.reply_text(f'\u26a0\ufe0f \u05e9\u05d2\u05d9\u05d0\u05d4 \u05d1{stage["label"]}: {str(e)[:200]}')

    await update.message.reply_text(f'\u2705 *\u05de\u05d7\u05e7\u05e8 \u05d4\u05d5\u05e9\u05dc\u05dd!*\n\U0001f4e6 {niche} | {m["flag"]} {m["name"]} | 7 \u05de\u05d5\u05d3\u05d5\u05dc\u05d9\u05dd\n\n\u05e9\u05dc\u05d7 \u05e0\u05d9\u05e9\u05d4 \u05e0\u05d5\u05e1\u05e4\u05ea \U0001f680', parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("\U0001f4d6 *\u05e4\u05e7\u05d5\u05d3\u05d5\u05ea:*\n/start \u2014 \u05d4\u05ea\u05d7\u05dc\u05d4\n/market \u2014 \u05e9\u05d9\u05e0\u05d5\u05d9 \u05e9\u05d5\u05e7\n/help \u2014 \u05e2\u05d6\u05e8\u05d4\n\n\u05e4\u05e9\u05d5\u05d8 \u05e9\u05dc\u05d7 \u05e0\u05d9\u05e9\u05d4!", parse_mode=ParseMode.MARKDOWN)

def main():
    if not TELEGRAM_TOKEN: raise ValueError("Set TELEGRAM_TOKEN")
    if not ANTHROPIC_API_KEY: raise ValueError("Set ANTHROPIC_API_KEY")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("market", market_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(market_callback, pattern="^market_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_niche))
    logger.info("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__": main()
