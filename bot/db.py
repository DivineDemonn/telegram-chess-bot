from motor.motor_asyncio import AsyncIOMotorClient
import chess
from bot.config import MONGO_URL

client = AsyncIOMotorClient(MONGO_URL)
db = client.telegram_chess_db
games_collection = db.games

async def get_active_game(chat_id: int):
    return await games_collection.find_one({"chat_id": chat_id, "status": "active"})

async def create_new_game(chat_id: int, white_id: int, white_name: str, black_id: int, black_name: str):
    board = chess.Board()
    game_doc = {
        "chat_id": chat_id,
        "status": "active",
        "fen": board.fen(),
        "white": {"id": white_id, "name": white_name},
        "black": {"id": black_id, "name": black_name},
        "current_turn_id": white_id,
        "last_move": None,
        "history": []
    }
    await games_collection.update_one(
        {"chat_id": chat_id},
        {"$set": game_doc},
        upsert=True
    )
    return game_doc

async def update_move_state(chat_id: int, fen: str, next_turn_id: int, san_move: str):
    await games_collection.update_one(
        {"chat_id": chat_id, "status": "active"},
        {
            "$set": {
                "fen": fen,
                "current_turn_id": next_turn_id,
                "last_move": san_move
            },
            "$push": {"history": san_move}
        }
    )

async def close_game(chat_id: int, winner_id: int = None, reason: str = "checkmate"):
    await games_collection.update_one(
        {"chat_id": chat_id, "status": "active"},
        {
            "$set": {
                "status": "finished",
                "winner_id": winner_id,
                "end_reason": reason
            }
        }
    )
