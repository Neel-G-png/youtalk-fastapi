from fastapi import APIRouter, Query, HTTPException
from video_processor.process_transcripts import TranscripsFetcher
from RAG_Pipeline.rag import RAGPipeline
from database.db import TursoDB
from utils.api_inputs import (
    Chat_History, 
    Insert_Message_Input
)
import logging
import pandas as pd

router = APIRouter()

tf = TranscripsFetcher()
rag = RAGPipeline()
tdb = TursoDB()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def format_session_history(history):
    history_df = pd.DataFrame(history, columns=['role', 'msg'])
    json_history = history_df.to_json(orient='records', indent=4)
    return json_history


@router.get("/get_all_user_sessions/")
async def get_sessions(user_id: str = Query(..., description="User ID for fetching sessions")):
    logger.info(f"Fetching sessions for user_id: {user_id}")
    try:
        user_sessions = await tdb.get_all_user_sessions(user_id)
        logger.info(f"Successfully fetched {len(user_sessions)} sessions for user_id: {user_id}")
        return {
            "status": 200,
            "user_sessions": user_sessions
        }
    except Exception as e:
        logger.error(f"Failed to fetch user sessions for user_id: {user_id}. Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user sessions: {str(e)}")

@router.get("/get_chat_history/")
async def get_chat_history(input: Chat_History):
    logger.info(f"Fetching chat history for session_id: {input.session_id}")
    try:
        chat_history = await tdb.get_user_chat_history(input.session_id)
        json_history = await format_session_history(chat_history)
        logger.info(f"Successfully fetched chat history for session_id: {input.session_id}")
        return {
            "status": 200,
            "chat_history": json_history
        }
    except Exception as e:
        logger.error(f"Failed to fetch chat history for session_id: {input.session_id}. Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch chat history: {str(e)}")
    
@router.post("/insert_messsage/")
async def insert_message(
    input:Insert_Message_Input
):
    logger.info(f"Attempting to insert chat message: {input.session_id}")

    try:
        # Attempt to insert the chat message into the database
        await tdb.insert_chat_message(input.session_id, input.role, input.message, input.created_at)

        return {
            "status": 200,
            "message": "Inserted Successfully"
        }

    except ValueError as e:
        logger.error(f"Value Error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")

    except ConnectionError as e:
        logger.error(f"Database Connection Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Database connection failed")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
