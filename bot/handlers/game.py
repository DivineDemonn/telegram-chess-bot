from aiogram import Router, F
from aiogram.enums import ChatType
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import chess
from bot.db import get_active_game, create_new_game, update_move_state, close_game
from bot.ws_manager import ws_manager
from bot.config import BASE_URL

router = Router()
# Strictly enforces operations inside group chats to drive group message count
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

pending_lobbies = {}

def get_game_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    webapp_url = f"{BASE_URL}/game/{chat_id}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="♟️ Open 3D Live Board", web_app=WebAppInfo(url=webapp_url))
    ]])

@router.message(F.text == "/chess")
async def cmd_start_game(message: Message):
    chat_id = message.chat.id
    active_game = await get_active_game(chat_id)
    if active_game:
        await message.reply(
            "⚠️ A game is already in progress in this group!\n"
            "Use /resign to forfeit before launching a new match."
        )
        return

    pending_lobbies[chat_id] = {
        "host_id": message.from_user.id,
        "host_name": message.from_user.first_name
    }

    lobby_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Accept Challenge", callback_data="join_chess_match")
    ]])

    await message.answer(
        f"♟️ <b>Open Chess Challenge</b>\n"
        f"Host: <b>{message.from_user.first_name}</b> (White)\n\n"
        f"Tap below to accept and play as Black!",
        reply_markup=lobby_kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "join_chess_match")
async def process_lobby_join(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    lobby = pending_lobbies.get(chat_id)

    if not lobby:
        await callback.answer("This challenge has expired or does not exist.", show_alert=True)
        return

    if callback.from_user.id == lobby["host_id"]:
        await callback.answer("You cannot play against yourself!", show_alert=True)
        return

    game = await create_new_game(
        chat_id=chat_id,
        white_id=lobby["host_id"],
        white_name=lobby["host_name"],
        black_id=callback.from_user.id,
        black_name=callback.from_user.first_name
    )
    del pending_lobbies[chat_id]

    await callback.message.edit_text(
        f"🎮 <b>Match Started!</b>\n\n"
        f"⚪ <b>White:</b> {game['white']['name']}\n"
        f"⚫ <b>Black:</b> {game['black']['name']}\n\n"
        f"👉 <b>{game['white']['name']}</b>, type your move in this chat (e.g. <code>e4</code>, <code>d4</code>, <code>Nf3</code>).\n"
        f"Players and spectators can tap below to view the interactive 3D board.",
        reply_markup=get_game_keyboard(chat_id),
        parse_mode="HTML"
    )

@router.message(F.text == "/resign")
async def cmd_resign(message: Message):
    chat_id = message.chat.id
    game = await get_active_game(chat_id)
    if not game:
        return

    user_id = message.from_user.id
    if user_id not in (game["white"]["id"], game["black"]["id"]):
        return

    winner_name = game["black"]["name"] if user_id == game["white"]["id"] else game["white"]["name"]
    winner_id = game["black"]["id"] if user_id == game["white"]["id"] else game["white"]["id"]

    await close_game(chat_id, winner_id=winner_id, reason="resignation")
    await message.answer(
        f"🏳️ <b>{message.from_user.first_name}</b> has resigned.\n"
        f"🏆 <b>{winner_name}</b> wins the match!",
        parse_mode="HTML"
    )

@router.message(F.text)
async def process_chess_move(message: Message):
    chat_id = message.chat.id
    game = await get_active_game(chat_id)
    if not game:
        return

    # Restrict processing strictly to the active player's turn
    if message.from_user.id != game["current_turn_id"]:
        return

    board = chess.Board(game["fen"])
    raw_move = message.text.strip()

    try:
        move = board.parse_san(raw_move)
    except ValueError:
        try:
            move = board.parse_uci(raw_move)
        except ValueError:
            # Not a chess move notation; ignore without disrupting chat
            return

    san_str = board.san(move)
    board.push(move)

    is_white_next = (board.turn == chess.WHITE)
    next_turn_id = game["white"]["id"] if is_white_next else game["black"]["id"]
    next_player_name = game["white"]["name"] if is_white_next else game["black"]["name"]

    # Update database record
    await update_move_state(chat_id, board.fen(), next_turn_id, san_str)

    # Push update to 3D Mini App
    await ws_manager.broadcast(chat_id, {
        "event": "move",
        "fen": board.fen(),
        "last_move": san_str,
        "turn": "white" if is_white_next else "black"
    })

    if board.is_checkmate():
        await close_game(chat_id, winner_id=message.from_user.id, reason="checkmate")
        await message.reply(
            f"♟️ Move: <code>{san_str}</code>\n"
            f"🏆 <b>CHECKMATE!</b> {message.from_user.first_name} wins the match!",
            parse_mode="HTML"
        )
    elif board.is_stalemate() or board.is_insufficient_material():
        await close_game(chat_id, reason="draw")
        await message.reply(
            f"♟️ Move: <code>{san_str}</code>\n"
            f"🤝 <b>Game Draw!</b> (Stalemate / Insufficient Material)",
            parse_mode="HTML"
        )
    else:
        check_badge = " ⚠️ <b>CHECK!</b>" if board.is_check() else ""
        await message.reply(
            f"Move: <code>{san_str}</code>{check_badge}\n"
            f"⏳ Turn: <b>{next_player_name}</b>",
            reply_markup=get_game_keyboard(chat_id),
            parse_mode="HTML"
        )
