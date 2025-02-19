from pydantic import BaseModel
from typing import List, Dict, Any, Union

class All_User_Sessions(BaseModel):
    user_id: str

class Chat_History(BaseModel):
    user_id: str
    session_id: str

class Video_Link_Input(BaseModel):
    user_id: str
    video_link: str
    created_at: str

class Stream_Input(BaseModel):
    user_id: str
    session_id: str
    message: str

class Stream_Followup_Input(BaseModel):
    user_id: str
    session_id: str
    message: str

class Insert_Message_Input(BaseModel):
    session_id: str
    role : str
    message: str
    created_at: str