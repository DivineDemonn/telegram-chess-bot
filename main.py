import asyncio
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from aiogram import Bot, Dispatcher
import chess

from bot.config import BOT_TOKEN, PORT
from bot.handlers.game import router as game_router
from bot.ws_manager import ws_manager
from bot.db import get_active_game

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(game_router)

templates = Jinja2Templates(directory="webapp/templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start bot polling in background task
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health_check():
    return {"status": "running", "service": "Telegram Group Chess Bot"}

@app.get("/game/{chat_id}")
async def serve_game_page(request: Request, chat_id: int):
    game = await get_active_game(chat_id)
    initial_fen = game["fen"] if game else chess.STARTING_FEN
    white_name = game["white"]["name"] if game else "White"
    black_name = game["black"]["name"] if game else "Black"

    return templates.TemplateResponse("index.html", {
        "request": request,
        "chat_id": chat_id,
        "initial_fen": initial_fen,
        "white_name": white_name,
        "black_name": black_name
    })

@app.websocket("/ws/{chat_id}")
async def game_ws_endpoint(websocket: WebSocket, chat_id: int):
    await ws_manager.connect(chat_id, websocket)
    try:
        while True:
            # Keep socket alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(chat_id, websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
