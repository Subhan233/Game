import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import database as db
from game import InningsState, ai_pick, resolve_ball

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

NUMBER_EMOJI = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}


# ---------------------------------------------------------------------------
# Single player game state
# ---------------------------------------------------------------------------
class SinglePlayerGame:
    def __init__(self, user_id, username):
        self.user_id = user_id
        self.username = username
        self.overs_limit = None
        self.difficulty = None
        self.user_bats_first = None
        self.innings1 = None
        self.innings2 = None
        self.current_innings_num = 1
        self.finished = False
        self.hattrick_this_match = False


def number_keyboard(prefix: str) -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton(NUMBER_EMOJI[n], callback_data=f"{prefix}:{n}") for n in (1, 2, 3)]
    row2 = [InlineKeyboardButton(NUMBER_EMOJI[n], callback_data=f"{prefix}:{n}") for n in (4, 5, 6)]
    return InlineKeyboardMarkup([row1, row2])


def current_innings(game: SinglePlayerGame) -> InningsState:
    return game.innings1 if game.current_innings_num == 1 else game.innings2


def user_is_batting(game: SinglePlayerGame) -> bool:
    first_innings_batting = game.user_bats_first
    if game.current_innings_num == 1:
        return first_innings_batting
    return not first_innings_batting


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🏏 *Welcome to Cricket Showdown!*\n\n"
        "Bat, bowl, and chase targets in a fast hand-cricket style game "
        "right inside Telegram.\n\n"
        "*Commands:*\n"
        "/play — Start a new single-player match vs the AI\n"
        "/stats — View your career stats\n"
        "/leaderboard — Top players\n"
        "/help — How to play\n\n"
        "Tap /play to start your first match!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*How to play:*\n"
        "1️⃣ Pick overs (1, 2 or 5) and a difficulty.\n"
        "2️⃣ Win the toss call to bat or bowl first.\n"
        "3️⃣ Each ball, tap a number 1-6.\n"
        "   • If your number matches the opponent's → WICKET\n"
        "   • Otherwise your number = runs scored\n\n"
        "*Special rules:*\n"
        "⚡ *Powerplay* — first 2 overs, runs are doubled\n"
        "🔥 *Streak bonus* — back-to-back boundaries earn +2 runs\n"
        "🎩 *Hat-trick* — 3 wickets in a row while bowling\n"
        "🎯 You get 2 wickets per innings — game ends when both fall or overs run out\n\n"
        "Chase the target to win when bowling second, or post the higher score!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    game = SinglePlayerGame(user.id, user.username or user.first_name)
    context.user_data["game"] = game

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1 Over", callback_data="overs:1"),
                InlineKeyboardButton("2 Overs", callback_data="overs:2"),
                InlineKeyboardButton("5 Overs", callback_data="overs:5"),
            ]
        ]
    )
    await update.message.reply_text(
        "🏏 *New Match!* How many overs per innings?", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
    )


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = db.get_player(user.id, user.username or user.first_name)
    text = (
        f"📊 *Stats for {player['username']}*\n\n"
        f"Matches: {player['matches']}\n"
        f"Wins: {player['wins']} | Losses: {player['losses']}\n"
        f"High Score: {player['high_score']}\n"
        f"Total Runs: {player['total_runs']}\n"
        f"Wickets Taken: {player['total_wickets']}\n"
        f"Centuries: {player['centuries']} | Fifties: {player['fifties']}\n"
        f"Hat-tricks: {player['hattricks']}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_leaderboard(10)
    if not rows:
        await update.message.reply_text("No matches played yet. Be the first with /play!")
        return
    lines = ["🏆 *Leaderboard*\n"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r['username'] or 'Player'} — {r['wins']} wins, HS {r['high_score']}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Callback query router
# ---------------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    game: SinglePlayerGame = context.user_data.get("game")
    if game is None:
        await query.edit_message_text("This match has expired. Start a new one with /play.")
        return

    action, _, value = data.partition(":")

    if action == "overs":
        game.overs_limit = int(value)
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Easy", callback_data="diff:easy"),
                    InlineKeyboardButton("Medium", callback_data="diff:medium"),
                    InlineKeyboardButton("Hard", callback_data="diff:hard"),
                ]
            ]
        )
        await query.edit_message_text("Choose AI difficulty:", reply_markup=keyboard)

    elif action == "diff":
        game.difficulty = value
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🏏 Bat first", callback_data="toss:bat"),
                    InlineKeyboardButton("🎯 Bowl first", callback_data="toss:bowl"),
                ]
            ]
        )
        await query.edit_message_text(
            "🪙 You won the toss! What do you want to do?", reply_markup=keyboard
        )

    elif action == "toss":
        game.user_bats_first = value == "bat"
        game.innings1 = InningsState(game.overs_limit)
        game.current_innings_num = 1
        role = "batting" if game.user_bats_first else "bowling"
        await query.edit_message_text(
            f"🏏 *Innings 1* — you are {role} first!\nPick a number:",
            reply_markup=number_keyboard("ball"),
            parse_mode=ParseMode.MARKDOWN,
        )

    elif action == "ball":
        await handle_ball(query, context, game, int(value))

    elif action == "playagain":
        user = query.from_user
        new_game = SinglePlayerGame(user.id, user.username or user.first_name)
        context.user_data["game"] = new_game
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("1 Over", callback_data="overs:1"),
                    InlineKeyboardButton("2 Overs", callback_data="overs:2"),
                    InlineKeyboardButton("5 Overs", callback_data="overs:5"),
                ]
            ]
        )
        await query.edit_message_text(
            "🏏 *New Match!* How many overs per innings?",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )


async def handle_ball(query, context, game: SinglePlayerGame, user_number: int):
    innings = current_innings(game)
    batting = user_is_batting(game)

    ai_number = ai_pick(game.difficulty, user_number)
    batter_pick = user_number if batting else ai_number
    bowler_pick = ai_number if batting else user_number

    result = resolve_ball(batter_pick, bowler_pick, innings)
    if result["hattrick"] and not batting:
        game.hattrick_this_match = True

    who = "You" if batting else "AI"
    header = f"🏏 Innings {game.current_innings_num} | Over {innings.overs_display} | Score: {innings.score}/{innings.wickets}"
    if innings.target is not None:
        header += f" | Target: {innings.target + 1}"
    body = f"{who} picked {NUMBER_EMOJI[batter_pick if batting else user_number]}\n{result['text']}"

    if innings.is_over:
        await finish_innings(query, context, game, header, body)
    else:
        text = f"{header}\n\n{body}\n\nPick your next number:"
        await query.edit_message_text(
            text, reply_markup=number_keyboard("ball"), parse_mode=ParseMode.MARKDOWN
        )


async def finish_innings(query, context, game: SinglePlayerGame, header, body):
    innings = current_innings(game)

    if game.current_innings_num == 1:
        summary = f"{header}\n\n{body}\n\n📋 *Innings 1 complete!* Final: {innings.score}/{innings.wickets}"
        game.innings2 = InningsState(game.overs_limit, target=innings.score)
        game.current_innings_num = 2
        next_batting = user_is_batting(game)
        role = "batting" if next_batting else "bowling"
        summary += f"\n\n🏏 *Innings 2* — you are {role} now. Target: {innings.score + 1}\nPick a number:"
        await query.edit_message_text(
            summary, reply_markup=number_keyboard("ball"), parse_mode=ParseMode.MARKDOWN
        )
        return

    # Match complete
    innings1, innings2 = game.innings1, game.innings2
    user_score = innings1.score if game.user_bats_first else innings2.score
    ai_score = innings2.score if game.user_bats_first else innings1.score
    user_won = user_score > ai_score
    draw = user_score == ai_score

    result_line = "🏆 *YOU WIN!* 🎉" if user_won else ("🤝 *It's a tie!*" if draw else "💔 AI wins this one.")
    summary = (
        f"{header}\n\n{body}\n\n"
        f"📋 *Match Over!*\n"
        f"Your total: {user_score}\nAI total: {ai_score}\n\n{result_line}"
    )

    db.record_match_result(
        game.user_id,
        game.username,
        won=user_won,
        score=user_score,
        wickets_taken=(innings2.wickets if game.user_bats_first else innings1.wickets),
        hattrick=game.hattrick_this_match,
    )

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Play Again", callback_data="playagain:1")]])
    await query.edit_message_text(summary, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling update:", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    db.init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("play", play))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)

    logger.info("Cricket Showdown Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
