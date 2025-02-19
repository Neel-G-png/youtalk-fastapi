from fastapi import APIRouter
import asyncio
from sse_starlette.sse import EventSourceResponse
from video_processor.process_transcripts import TranscripsFetcher
from RAG_Pipeline.rag import RAGPipeline
from database.db import TursoDB
import pandas as pd
from utils.api_inputs import (
    Stream_Input, 
    Stream_Followup_Input
)
import logging
import json

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

@router.get("/stream_response/")
async def stream_response(
    input: Stream_Input
):
    async def event_generator():
        logger.info("Fetching video ID for session_id: %s", input.session_id)
        video_id = await tdb.get_video_id(input.session_id)
        logger.info("Retrieved video ID: %s", video_id)
        
        async for event in rag.generate(input.message, video_id):
            yield json.dumps({
                "event": "message",
                "data": event["data"]
            })
            await asyncio.sleep(0.01)

    logger.info("Starting event stream for session_id: %s", input.session_id)
    return EventSourceResponse(event_generator())

@router.get("/followup_stream_response/")
async def followup_stream_response(
    input: Stream_Followup_Input
):
    async def event_generator():
        logger.info("Fetching video ID for session_id: %s", input.session_id)
        video_id = await tdb.get_video_id(input.session_id)
        logger.info("Retrieved video ID: %s", video_id)

        logger.info(f"Fetching chat history for session_id: {input.session_id}")
        chat_history = await tdb.get_user_chat_history(input.session_id)
        json_history = await format_session_history(chat_history)
        logger.info(f"Successfully fetched chat history for session_id: {input.session_id}")

        async for event in rag.generate_followup(input.message, video_id, json_history):
            yield json.dumps({
                "event": "message",
                "data": event["data"]
            })
            await asyncio.sleep(0.01)

    logger.info("Starting event stream for session_id: %s", input.session_id)
    return EventSourceResponse(event_generator())