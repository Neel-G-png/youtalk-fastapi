import libsql_experimental as libsql
import asyncio
import logging
from dotenv import load_dotenv
import os

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
# Conver these functions into a class to and periodically refresh
# libsql connection to avoid invalid baton error

class TursoDB():
    def __init__(self):
        self.running = True
        self.url = os.getenv("TURSO_URL")
        self.auth_token = os.getenv("TURSO_AUTH_TOKEN")
        
        # self.refresh_task = asyncio.create_task(self.refresh_connection())
        # self.conn = libsql.connect(self.url, auth_token = self.auth_token)
        # self.cur = self.conn.cursor()

    async def refresh_connection(self):
        while self.running:
            print("Refreshing Connection")
            self.conn = libsql.connect(self.url, auth_token = self.auth_token)
            self.cur = self.conn.cursor()
            await asyncio.sleep(300)
    
    async def refresh_connection_manually(self):
        self.conn = libsql.connect(self.url, auth_token = self.auth_token)
        self.cur = self.conn.cursor()

    async def get_user_chat_history(self, session_id: str):
        await self.refresh_connection_manually()

        query = """
            SELECT 
                source, 
                msg
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
        """
        chat_history = self.conn.execute(query, (session_id,)).fetchall()
        return chat_history

    async def insert_chat_message(self, session_id: str, role: str, msg: str, created_at: str):
        await self.refresh_connection_manually()

        query = """
            INSERT INTO messages (session_id, source, msg, created_at)
            VALUES (?, ?, ?, ?)
        """
        inserted_message = self.conn.execute(query, (session_id, role, msg, created_at))
        self.conn.commit()
        return inserted_message

    async def insert_user_session(self, user_id: str, session_id: str, created_at: str, video_id: str, video_name: str, video_link: str):
        await self.refresh_connection_manually()

        query = f"""
            insert into sessions
            (user_id, session_id, created_at, video_id, video_name, video_link)
            values
            (?, ?, ?, ?, ?, ?)
        """

        inserted_sessions = self.conn.execute(query, (user_id, session_id, created_at, video_id, video_name, video_link))
        self.conn.commit()
        return inserted_sessions

    async def get_all_user_sessions(self, user_id: str):
        await self.refresh_connection_manually()

        query = f"""
            select
                session_id,
                video_name,
                video_link,
                created_at
            from sessions
            where
                user_id = ?
            order by
                created_at desc
        """
        user_sessions = self.conn.execute(query, (user_id,)).fetchall()
        return user_sessions
    
    async def check_if_video_exists(self, video_id: str):
        await self.refresh_connection_manually()

        query = f"""
            select
                user_id,
                session_id,
                video_id,
                video_name
            from sessions
            where
                video_id = ?
        """
        video_exists = self.conn.execute(query, (video_id,)).fetchall()
        return video_exists
    
    async def get_video_id(self, session_id: str):
        await self.refresh_connection_manually()

        query = f"""
            select
                video_id
            from sessions
            where
                session_id = ?
        """
        video_id = self.conn.execute(query, (session_id,)).fetchone()
        return video_id[0]
