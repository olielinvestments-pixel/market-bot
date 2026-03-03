import os, json, asyncio, logging, httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode, ChatAction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

MARKETS = {
    "il": {"flag":"\U0001f1ee\U0001f1f1","name":"\u05d9\u05e9\u05e8\u05d0\u05dc","nameEn":"Israel","currency":"\u20aa","google":"google.co.il"},
    "us": {"flag":"\U0001f1fa\U0001f1f8","name":"\u05d0\u05e8\u05d4\u05f4\u05d1","nameEn":"United States","currency":"$","google":"google.com"},
    "uk": {"flag":"\U0001f1ec\U0001f1e7","name":"\u05d1\u05e8\u05d9\u05d8\u05e0\u05d9\u05d4","nameEn":"United Kingdom","currency":"\u00a3","google":"google.co.uk"},
    "global": {"flag":"\U0001f30d","name":"\u05d2\u05dc\u05d5\u05d1\u05dc\u05d9","nameEn":"Global","currency":"$","google":"google.com"},
}

user_markets = {}

def get_stages(market_id, niche):
    m = MARKETS.get(market_id, MARKETS["il"])
    base = f'Ecommerce analyst. "{niche}" in {m["nameEn"]}. Give NUMBERS, estimates OK. {m["currency"]}. Hebrew only. Be concise.'
    
    return [
        {"id":"search","label":"\U0001f50e \u05d7\u05d9\u05e4\u05d5\u05e9\u05d9\u05dd",
         "prompt":f'{base} Search volume: top 10 keywords with monthly volume, trend, competition, buying intent%. Total monthly searches. Seasonality. Use web search.'},
        {"id":"cpc","label":"\U0001f4b8 CPC",
         "prompt":f'{base} CPC analysis: Google/Facebook/TikTok CPC in {m["currency"]}, daily budget, CPA, ROAS, best platform. Use web search.'},
        {"id":"shopping","label":"\U0001f6d2 \u05e9\u05d5\u05e4\u05d9\u05e0\u05d2",
         "prompt":f'{base} Google Shopping: product count, price range, avg price, top 5 sellers, market gaps. Use web search.'},
        {"id":"social","label":"\U0001f4f1 \u05e1\u05d5\u05e9\u05d9\u05d0\u05dc",
         "prompt":f'{base} Social media: Instagram/TikTok/Facebook presence, hashtag volume, virality 1-10, best platform, content strategy. Use web search.'},
        {"id":"competitors","label":"\u2694\ufe0f \u05de\u05ea\u05d7\u05e8\u05d9\u05dd",
         "prompt":f'{base} Competitors: top 5 stores, est. revenue, strengths/weaknesses, TAM, barriers, CAC. Use web search.'},
        {"id":"forecast","label":"\U0001f4b0 \u05ea\u05d7\u05d6\u05d9\u05ea",
         "prompt":f'{base} Sales forecast new store: monthly for 12mo, investment needed, break-even, ROI. Two scenarios. {{prev_data}}'},
        {"id":"summary","label":"\U0001f4cb GO/NO-GO",
         "prompt":f'{base} Executive summary: score X/10, GO/NO-GO, top opportunities, risks, key metrics, entry strategy, budget. {{prev_data}}'},
    ]

async def call_claude(prompt):
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post("https://api.anthropic.com/v1/messages",
            headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},
            json={"model":"claude-sonnet-4-20250514","max_tokens":1500,
                  "tools":[{"type":"web_search_20250305","name":"web_search","max_uses":2}],
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
    await q.edit_message_text(f'{m["flag"]} *\u05e9\u05d5\u05e7: {m["name"]}*\n\n\u05e9\u05dc\u05d7 \u05e0\u05d9\u05e9\u05d4 \u05dc\u05d7\u05e7\u05d5\u05e8!\n\n/market \u05dc\u05e9\u05d9\u05e0\u05d5\u05d9 \u05e9\u05d5\u05e7', parse_mode=ParseMode.MARKDOWN)

async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(f'{m["flag"]} {m["name"]}', callback_data=f"market_{mid}")] for mid,m in MARKETS.items()]
    await update.message.reply_text("\U0001f30d \u05d1\u05d7\u05e8 \u05e9\u05d5\u05e7 \u05d9\u05e2\u05d3:", reply_markup=InlineKeyboardMarkup(kb))

async def handle_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    niche = update.message.text.strip()
    if not niche or niche.startswith("/"): return
    uid = update.effective_user.id; mid = user_markets.get(uid,"il"); m = MARKETS[mid]

    await update.message.reply_text(f'\U0001f680 *\u05de\u05ea\u05d7\u05d9\u05dc \u05de\u05d7\u05e7\u05e8!*\n\U0001f4e6 {niche}\n{m["flag"]} {m["name"]}\n\n\u05d6\u05d4 \u05d9\u05d9\u05e7\u05d7 5-7 \u05d3\u05e7\u05d5\u05ea...', parse_mode=ParseMode.MARKDOWN)

    stages = get_stages(mid, niche); prev = {}
    for i, stage in enumerate(stages):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        if i > 0:
            wait = 65
            await update.message.reply_text(f'\u23f3 \u05de\u05de\u05ea\u05d9\u05df \u05dc{stage["label"]}...')
            await asyncio.sleep(wait)
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        try:
            prompt = stage["prompt"]
            if "{prev_data}" in prompt:
                sm = "\n".join([f"{k}: {v[:300]}" for k,v in prev.items()])
                prompt = prompt.replace("{prev_data}", f"Context:\n{sm}")
            result = await call_claude(prompt); prev[stage["id"]] = result
            txt = f'{stage["label"]}\n{"="*25}\n\n{trunc(result,3900)}'
            try:
                await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await update.message.reply_text(txt)
        except Exception as e:
            logger.error(f'{stage["id"]}: {e}')
            await update.message.reply_text(f'\u26a0\ufe0f \u05e9\u05d2\u05d9\u05d0\u05d4 \u05d1{stage["label"]}: {str(e)[:200]}')

    await update.message.reply_text(f'\u2705 *\u05de\u05d7\u05e7\u05e8 \u05d4\u05d5\u05e9\u05dc\u05dd!*\n\U0001f4e6 {niche} | {m["flag"]} {m["name"]}\n\n\u05e9\u05dc\u05d7 \u05e0\u05d9\u05e9\u05d4 \u05e0\u05d5\u05e1\u05e4\u05ea \U0001f680', parse_mode=ParseMode.MARKDOWN)

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
