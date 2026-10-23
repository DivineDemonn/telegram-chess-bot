import asyncio
from contextlib import asynccontextmanager
import uvicorn
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from aiogram import Bot, Dispatcher
import chess

from bot.config import BOT_TOKEN, PORT, BASE_URL
from bot.handlers.game import router as game_router
from bot.ws_manager import ws_manager
from bot.db import get_active_game

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.include_router(game_router)

templates = Jinja2Templates(directory="webapp/templates")

async def keep_alive_daemon():
    """
    Prevents Render Free Web Service instances from spinning down
    by generating external HTTP traffic every 10 minutes.
    """
    await asyncio.sleep(20)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                ping_target = f"{BASE_URL}/ping"
                response = await client.get(ping_target, timeout=10.0)
                print(f"[Keep-Alive] Self-ping status {response.status_code} on {ping_target}")
            except Exception as exc:
                print(f"[Keep-Alive Warning] Could not reach endpoint: {exc}")
            await asyncio.sleep(600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Concurrently execute bot polling and 24/7 keep-alive background worker
    polling_task = asyncio.create_task(dp.start_polling(bot))
    keep_alive_task = asyncio.create_task(keep_alive_daemon())
    yield
    polling_task.cancel()
    keep_alive_task.cancel()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.get("/")
@app.get("/ping")
async def health_check():
    return {"status": "ok", "service": "Telegram 3D Chess Group Engine"}

@app.get("/game/{chat_id}")
async def render_game_webapp(request: Request, chat_id: int):
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
async def ws_game_stream(websocket: WebSocket, chat_id: int):
    await ws_manager.connect(chat_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(chat_id, websocket)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
