from aiogram import Router, F, Bot
from aiogram.enums import ChatType
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import chess
from bot.db import get_active_game, create_new_game, update_move_state, close_game
from bot.ws_manager import ws_manager
from bot.config import BASE_URL

router = Router()
# Restrict all commands and messages strictly to groups and supergroups
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

# In-memory storage for open challenges before game initiation
open_lobbies = {}

def build_game_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    webapp_url = f"{BASE_URL}/game/{chat_id}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="♟️ Open 3D Live Board", web_app=WebAppInfo(url=webapp_url))
    ]])

@router.message(F.text == "/chess")
async def cmd_start_chess(message: Message):
    chat_id = message.chat.id
    active = await get_active_game(chat_id)
    if active:
        await message.reply(
            "⚠️ A game is currently in progress! Use /resign to forfeit before starting a new match."
        )
        return

    open_lobbies[chat_id] = {
        "host_id": message.from_user.id,
        "host_name": message.from_user.first_name
    }

    join_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Accept Match", callback_data="join_chess_match")
    ]])

    await message.answer(
        f"♟️ <b>Open Chess Challenge</b>\n"
        f"Host: <b>{message.from_user.first_name}</b>\n\n"
        f"Click below to join as Black!",
        reply_markup=join_kb,
        parse_mode="HTML"
    )

@router.callback_query(F.data == "join_chess_match")
async def on_join_match(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    lobby = open_lobbies.get(chat_id)

    if not lobby:
        await callback.answer("This challenge has expired or is invalid.", show_alert=True)
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
    del open_lobbies[chat_id]

    await callback.message.edit_text(
        f"🎮 <b>Match Started!</b>\n\n"
        f"⚪ <b>White:</b> {game['white']['name']}\n"
        f"⚫ <b>Black:</b> {game['black']['name']}\n\n"
        f"👉 <b>{game['white']['name']}</b>, type your move in this chat (e.g., <code>e4</code>, <code>d4</code>, <code>Nf3</code>).\n"
        f"Spectators and players can tap below to view the live 3D board.",
        reply_markup=build_game_keyboard(chat_id),
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
async def handle_group_move(message: Message):
    chat_id = message.chat.id
    game = await get_active_game(chat_id)
    if not game:
        return

    # Check if the message sender is the player whose turn it is
    if message.from_user.id != game["current_turn_id"]:
        return

    board = chess.Board(game["fen"])
    move_text = message.text.strip()

    # Support SAN (e4, Nf3) and UCI (e2e4, g1f3)
    try:
        move = board.parse_san(move_text)
    except ValueError:
        try:
            move = board.parse_uci(move_text)
        except ValueError:
            # Not a chess notation string; treat as normal chat from the player
            return

    san_str = board.san(move)
    uci_str = move.uci()
    board.push(move)

    is_white_turn = (board.turn == chess.WHITE)
    next_turn_id = game["white"]["id"] if is_white_turn else game["black"]["id"]
    next_player_name = game["white"]["name"] if is_white_turn else game["black"]["name"]

    # 1. Update DB State
    await update_move_state(chat_id, board.fen(), next_turn_id, san_str)

    # 2. Push Real-Time Event to 3D Mini App
    await ws_manager.broadcast(chat_id, {
        "event": "move",
        "fen": board.fen(),
        "last_move": san_str,
        "uci": uci_str,
        "turn": "white" if is_white_turn else "black",
        "is_check": board.is_check(),
        "is_game_over": board.is_game_over()
    })

    # 3. Resolve End Game or Announce Next Turn in Chat
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
        check_note = " ⚠️ <b>CHECK!</b>" if board.is_check() else ""
        await message.reply(
            f"⚪⚫ Move: <code>{san_str}</code>{check_note}\n"
            f"⏳ Next turn: <b>{next_player_name}</b>",
            reply_markup=build_game_keyboard(chat_id),
            parse_mode="HTML"
        )
