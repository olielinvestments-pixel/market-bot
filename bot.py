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
    ctx = f'in the {m["nameEn"]} market ({m["google"]}), all prices in {m["currency"]}'
    base = f"""You are an expert ecommerce market research analyst. You MUST provide SPECIFIC NUMBERS and DATA - never say "data not available" or "I couldn't find". 
If exact data is unavailable, provide your best professional ESTIMATES based on market knowledge and clearly mark them as estimates.
ALWAYS respond in Hebrew only. Use tables and organized formatting."""
    
    return [
        {"id":"google_search","label":"\U0001f50e \u05db\u05de\u05d5\u05ea \u05d7\u05d9\u05e4\u05d5\u05e9\u05d9\u05dd \u05d1\u05d2\u05d5\u05d2\u05dc",
         "prompt":f"""{base}

Research search volume for "{niche}" {ctx}. Use web search to find real data.

You MUST provide a table with these columns for at least 10 keywords:
| Keyword | Monthly Search Volume | Trend (up/down/stable) | Competition (high/med/low) | Buying Intent % |

Include both Hebrew and English keywords relevant to {m["nameEn"]}.
Also provide:
- Total estimated monthly searches for this niche
- Seasonality pattern (which months are peak)
- Year-over-year growth estimate %
- Top 3 long-tail keywords with high buying intent

Give NUMBERS even if estimated. Hebrew only."""},

        {"id":"cpc_analysis","label":"\U0001f4b8 \u05e2\u05dc\u05d5\u05ea \u05e7\u05dc\u05d9\u05e7 (CPC)",
         "prompt":f"""{base}

Analyze advertising costs for "{niche}" {ctx}. Use web search.

Provide a detailed table:
| Platform | Avg CPC | Competition | Est. Daily Budget | Est. Monthly Spend |

Platforms to analyze: Google Search, Google Shopping, Facebook/Instagram, TikTok, YouTube.

Also provide:
- Recommended starting daily budget in {m["currency"]}
- Estimated CPA (Cost Per Acquisition) in {m["currency"]}
- Expected ROAS (Return on Ad Spend)
- Best platform recommendation for {m["nameEn"]} market
- Budget allocation recommendation (% per platform)

All amounts in {m["currency"]}. Give NUMBERS. Hebrew only."""},

        {"id":"google_shopping","label":"\U0001f6d2 \u05e0\u05d9\u05ea\u05d5\u05d7 \u05d2\u05d5\u05d2\u05dc \u05e9\u05d5\u05e4\u05d9\u05e0\u05d2",
         "prompt":f"""{base}

Research Google Shopping and ecommerce for "{niche}" {ctx}. Use web search.

Provide:
- Number of competing products on Google Shopping
- Price range (min - max) in {m["currency"]}
- Average price in {m["currency"]}
- Top 5 sellers/stores with estimated market share %
- Shipping costs and delivery times
- Market gaps and opportunities
- Product categories breakdown

Give NUMBERS. Hebrew only."""},

        {"id":"social_media","label":"\U0001f4f1 \u05e8\u05e9\u05ea\u05d5\u05ea \u05d7\u05d1\u05e8\u05ea\u05d9\u05d5\u05ea",
         "prompt":f"""{base}

Analyze social media presence for "{niche}" in {m["nameEn"]}. Use web search.

For each platform (Instagram, TikTok, Facebook, YouTube), provide:
| Platform | Hashtag Volume | Top Influencers | Engagement Rate | Content Type |

Also provide:
- Virality score (1-10) for this niche
- Best platform recommendation
- Content strategy (what type of content works)
- Estimated follower growth potential
- Top 5 relevant hashtags per platform

Give NUMBERS. Hebrew only."""},

        {"id":"competitors","label":"\u2694\ufe0f \u05e0\u05d9\u05ea\u05d5\u05d7 \u05de\u05ea\u05d7\u05e8\u05d9\u05dd",
         "prompt":f"""{base}

Analyze competitors for "{niche}" ecommerce in {m["nameEn"]}. Use web search.

Provide a competitor table:
| Store Name | Est. Monthly Revenue | Price Range | Strengths | Weaknesses |

For top 5-7 competitors. Also provide:
- Total Addressable Market (TAM) in {m["currency"]}
- Market structure (fragmented/concentrated)
- Barriers to entry
- Competitive advantages available for new entrant
- Estimated Customer Acquisition Cost in {m["currency"]}

Give NUMBERS. Hebrew only."""},

        {"id":"sales_estimate","label":"\U0001f4b0 \u05ea\u05d7\u05d6\u05d9\u05ea \u05de\u05db\u05d9\u05e8\u05d5\u05ea",
         "prompt":f"""{base}

Create sales forecast for a NEW online store selling "{niche}" in {m["nameEn"]}. 
Previous research data: {{prev_data}}

Provide monthly forecast table for 12 months:
| Month | Revenue | Orders | Avg Order Value | Ad Spend | Profit |

Two scenarios: Conservative and Optimistic.

Also provide:
- Required initial investment in {m["currency"]}
- Break-even point (which month)
- Year 1 total revenue estimate
- Year 1 ROI %
- Key assumptions

All in {m["currency"]}. Give NUMBERS. Hebrew only."""},

        {"id":"summary","label":"\U0001f4cb \u05e1\u05d9\u05db\u05d5\u05dd \u05d5\u05d4\u05d7\u05dc\u05d8\u05d4",
         "prompt":f"""{base}

Create executive summary for "{niche}" ecommerce in {m["nameEn"]}.
Previous research data: {{prev_data}}

MUST include:
1. Overall Score: X/10 (with explanation)
2. GO / NO-GO decision (clear recommendation)
3. Top 3 opportunities
4. Top 3 risks
5. Key metrics summary:
   - Market size in {m["currency"]}
   - Average CPC in {m["currency"]}
   - Expected monthly revenue (month 6)
   - Expected ROI %
6. Recommended entry strategy (step by step)
7. Required budget breakdown in {m["currency"]}
8. Bottom line: one paragraph final recommendation

Give NUMBERS. Hebrew only."""},
    ]

async def call_claude(prompt):
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post("https://api.anthropic.com/v1/messages",
            headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},
            json={"model":"claude-sonnet-4-20250514","max_tokens":2000,
                  "tools":[{"type":"web_search_20250305","name":"web_search","max_uses":3}],
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

    await update.message.reply_text(f'\U0001f680 *\u05de\u05ea\u05d7\u05d9\u05dc \u05de\u05d7\u05e7\u05e8!*\n\U0001f4e6 {niche}\n{m["flag"]} {m["name"]}\n\n\u05d6\u05d4 \u05d9\u05d9\u05e7\u05d7 3-5 \u05d3\u05e7\u05d5\u05ea...', parse_mode=ParseMode.MARKDOWN)

    stages = get_stages(mid, niche); prev = {}
    for i, stage in enumerate(stages):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        # Wait between requests to avoid rate limiting
        if i > 0:
            await asyncio.sleep(30)
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        
        try:
            prompt = stage["prompt"]
            if "{prev_data}" in prompt:
                sm = "\n".join([f"{k}: {v[:500]}" for k,v in prev.items()])
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
