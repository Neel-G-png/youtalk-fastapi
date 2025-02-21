from fastapi import APIRouter, Query, HTTPException
from video_processor.process_transcripts import TranscripsFetcher
from RAG_Pipeline.rag import RAGPipeline
from database.db import TursoDB
from utils.api_inputs import Video_Link_Input
from uuid import uuid4
import pandas as pd
import requests
from bs4 import BeautifulSoup 
import logging
import re
import os
import json
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

tf = TranscripsFetcher()
rag = RAGPipeline()
tdb = TursoDB()
SESSION_LIMIT = int(os.getenv("SESSION_LIMIT"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def get_video_id(url):
    yt_pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:shorts\/|watch\?v=|embed\/)|youtu\.be\/)([^"&?\/\s]{11})'
    match = re.search(yt_pattern, url)
    return match.group(1) if match else None

async def scrape_info(url): 
    try:
        NORDVPN_USERNAME = os.getenv("NORDVPN_USERNAME")
        NORDVPN_PASSWORD = os.getenv("NORDVPN_PASSWORD")
        server = "atlanta.us.socks.nordhold.net:1080"
        nvpn_proxy = {
            'http': f'socks5h://{NORDVPN_USERNAME}:{NORDVPN_PASSWORD}@{server}',
            'https': f'socks5h://{NORDVPN_USERNAME}:{NORDVPN_PASSWORD}@{server}'
        }
        r = requests.get(url, proxies=nvpn_proxy) 
        soup = BeautifulSoup(r.text, "html.parser")
        script_tag = soup.find("script", string=re.compile("ytInitialData"))
        if script_tag:
            json_text = re.search(r"var ytInitialData = ({.*?});", script_tag.string)
            if json_text:
                youtube_data = json.loads(json_text.group(1))
                try:
                    video_title = youtube_data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][0]["videoPrimaryInfoRenderer"]["title"]["runs"][0]["text"]
                    return video_title
                except KeyError:
                    logger.info("Could not extract video title.")
            else:
                logger.info("JSON data not found.")
        else:
            logger.info("Could not find ytInitialData script tag.")
    except Exception as e:
        logger.error(f"Failed to scrape video name for {url}: {e}")
        return None

async def proccess_and_ingest_video(user_id, video_link, video_id, created_at):
    """
    Processes a video link, extracts transcripts, ingests data into Pinecone, 
    and stores session details in Turso DB.
    """
    try:
        logger.info(f"Processing video link: {video_link} for user: {user_id}")

        # Fetch Transcripts
        yt_data = await tf.process_link(video_link, 600, 'en')
        yt_data['user_id'] = user_id
        video_title = await scrape_info(video_link)
        
        # Raise an error if title is empty or None
        if not video_title:
            raise ValueError(f"Failed to retrieve video title for link: {video_link}")

        yt_data['video_name'] = video_title
        
        logger.info(f"Fetched transcript data for video ID {video_id}: {yt_data['video_name']}")

        # Ingest into Pinecone
        logger.info("Ingesting data into Pinecone...")
        ingested_uuids = await rag.ingest_data(yt_data)
        logger.info(f"Successfully ingested {len(ingested_uuids)} chunks into Pinecone")

        # Generate session ID
        session_id = uuid4()
        logger.info(f"Generated session ID: {session_id} for user: {user_id}")

        # Handle inverted commas in title and insert into Turso DB
        await tdb.insert_user_session(user_id, str(session_id), created_at=created_at, video_id=video_id, video_name=yt_data['video_name'], video_link=video_link)
        logger.info(f"Inserted session data into Turso DB for user {user_id} with session ID {session_id}")

        return yt_data, ingested_uuids, session_id

    except Exception as e:
        logger.error(f"Error processing video {video_link}: {e}", exc_info=True)
        return None, None, None
    
async def user_exceeds_session_limit(user_id):
    try:
        user_sessions = await tdb.get_session_count_for_user(user_id)
        if user_sessions >= SESSION_LIMIT:
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking session limit for user {user_id}: {e}")
        return True

@router.post("/process_video/")
async def process_video(
    input: Video_Link_Input
):
    try:
        logger.info("Processing video for user_id: %s and video_link: %s", input.user_id, input.video_link)
        
        if await user_exceeds_session_limit(input.user_id):
            raise HTTPException(status_code=500, detail=f"Sorry, I'm on free tier and limiting users to only 3 videos")

        # Check if video already exists in the database
        try:
            video_id = await get_video_id(input.video_link)
            logger.info("Extracted video ID: %s", video_id)
        except Exception as e:
            logger.error("Failed to extract video ID: %s", str(e))
            raise HTTPException(status_code=500, detail=f"Failed to extract video ID: {input.video_link}")
        
        try:
            video_list = await tdb.check_if_video_exists(video_id)
            logger.info("Database query successful. Found %d records", len(video_list))
        except Exception as e:
            logger.error("Database query failed: %s", str(e))
            raise HTTPException(status_code=500, detail=f"Something went wrong!")

        if video_list:
            try:
                video_df = pd.DataFrame(video_list, columns=['user_id', 'session_id', 'video_id', 'video_name'])
                logger.info("Video list successfully processed into DataFrame")
            except Exception as e:
                logger.error("Failed to process video list: %s", str(e))
                raise HTTPException(status_code=500, detail=f"Something went wrong processing video list")

            if input.user_id in video_df['user_id'].values:
                logger.info("Video already exists for user_id: %s", input.user_id)
                return {
                    "status": 200,
                    "sub_status": 201,
                    "session_id": video_df[video_df['user_id'] == input.user_id]['session_id'].values[0],
                    "video_name": video_df[video_df['user_id'] == input.user_id]['video_name'].values[0]
                }
            else:
                logger.info("Video already exists for another user")
                try:
                    session_id = uuid4()
                    video_link = f"https://youtube.com/watch?v={video_id}"
                    video_name = await scrape_info(video_link)
                    
                    if not video_name:
                        logger.error("Failed to retrieve video name")
                        raise ValueError("Failed to retrieve video name")
                    
                    await tdb.insert_user_session(
                        input.user_id, 
                        str(session_id), 
                        created_at = input.created_at,
                        video_id = video_id, 
                        video_name=video_name,
                        video_link = video_link
                    )
                    
                    logger.info("Inserted new user session for user_id: %s", input.user_id)
                    return {
                        "status": 200,
                        "sub_status": 202,
                        "session_id": session_id,
                        "video_name": video_name
                    }
                except Exception as e:
                    logger.error("Error inserting session: %s", str(e))
                    raise HTTPException(status_code=500, detail=f"Couldn't create a new sessions!")

        # If video does not exist, process and ingest
        try:
            yt_data, ingested_uuids, session_id = await proccess_and_ingest_video(input.user_id, input.video_link, video_id, input.created_at)
            logger.info("Successfully processed and ingested video for user_id: %s", input.user_id)
        except Exception as e:
            logger.error("Error processing and ingesting video: %s", str(e))
            raise HTTPException(status_code=500, detail=f"Error processing the video!")

        return {
            "status": 200,
            "sub_status": 200,
            "video_name": yt_data['video_name'],
            "session_id": session_id
        }
    
    except HTTPException as e:
        logger.warning("HTTPException encountered: %s", e.detail)
        raise e  # Pass FastAPI exceptions as is
    except Exception as e:
        logger.critical("Unexpected error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Something went terribly wrong!")