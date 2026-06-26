import os
import logging
from fastapi import FastAPI, Request
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from agents.routing_agent.agent import RoutingAgent

load_dotenv()

routing_agent = None
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global routing_agent
    logger.info("Initializing routing agent")
    routing_agent = await RoutingAgent.create([
        f"http://{os.environ['SERVER_URL']}:{os.environ['TITLE_AGENT_PORT']}",
        f"http://{os.environ['SERVER_URL']}:{os.environ['OUTLINE_AGENT_PORT']}",
    ])
    routing_agent.create_agent()
    logger.info("Routing agent initialized")
    yield

app = FastAPI(lifespan=lifespan)

@app.post("/message")
async def handle_message(request: Request):
    data = await request.json()
    user_message = data.get("message")

    if not user_message:
        return {"error": "No message provided."}
    
    try:
        response = await routing_agent.process_user_message(user_message)

    except Exception as e:
        return {"error": f"Failed to process message: {str(e)}"}
    
    return {"response": response}

@app.get("/health")
async def health_check():
    return {"status": "Routing agent is running!"}

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("SERVER_URL", "127.0.0.1")
    port = int(os.getenv("ROUTING_AGENT_PORT", "10009"))
    uvicorn.run("agents.routing_agent.server:app", host=host, port=port, reload=True)
