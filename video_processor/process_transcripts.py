import re
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import Formatter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class BatchFormatter(Formatter):
    def format_transcript(self, transcript, batch_size, **kwargs):
        # Do your custom work in here, but return a string.
        for line in transcript:
            line['end'] = line['start'] + line['duration']

        # split the transcript into batch using end time. batch_size for exmaple would be 10 minutes
        batches = []
        current_batch = {
            'text' : "",
            'start' : 0,
            'end' : 0
        }
        current_batch_time = 0
        for line in transcript:
            current_batch['text'] += line['text'] + " "
            current_batch_time += line['duration']
            if current_batch_time >= batch_size:
                current_batch['end'] = line['end']
                batches.append(current_batch)
                current_batch = {
                    'text' : "",
                    'start' : line['end'],
                    'end' : 0,
                }
                current_batch_time = 0
        if current_batch['text']:
            current_batch['end'] = transcript[-1]['end']
            batches.append(current_batch)
        return batches

    def format_transcripts(self, transcripts, **kwargs):
        # Do your custom work in here to format a list of transcripts, but return a string.
        return [self.format_transcript(transcript, **kwargs) for transcript in transcripts]
    
class TranscripsFetcher():
    def __init__(self):
        self.yt_pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:shorts\/|watch\?v=|embed\/)|youtu\.be\/)([^"&?\/\s]{11})'
        self.formatter = BatchFormatter()

    async def extract_video_id(self, url):
        match = re.search(self.yt_pattern, url)
        return match.group(1) if match else None
    
    def fetch_transcripts(self, video_id, language='en'):
        try:
            logger.info(f"Fetching List of Transcripts for video_id : {video_id}")
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            logger.info(f"Successfully fetched List of Transcripts for video_id : {video_id}")
            try:
                transcript = transcript_list.find_transcript(['en', 'en-IN', 'en-GB', 'en-US', 'en-AU', 'en-CA'])
            except Exception as e:
                logger.error(f"Could not find transcript in English, trying other languages : {e}")
                
                transcript = transcript_list.find_transcript(["en","hi","de","ab","aa","af","ak","sq","am","ar","hy","as","ay","az","bn","ba","eu","be","bho","bs","br","bg","my","ca","ceb","zh-Hans","zh-Hant","co","hr","cs","da","dv","nl","dz","eo","et","ee","fo","fj","fil","fi","fr","gaa","gl","lg","ka","el","gn","gu","ht","ha","haw","iw","hmn","hu","is","ig","id","iu","ga","it","ja","jv","kl","kn","kk","kha","km","rw","ko","kri","ku","ky","lo","la","lv","ln","lt","lua","luo","lb","mk","mg","ms","ml","mt","gv","mi","mr","mn","mfe","ne","new","nso","no","ny","oc","or","om","os","pam","ps","fa","pl","pt","pt-PT","pa","qu","ro","rn","ru","sm","sg","sa","gd","sr","crs","sn","sd","si","sk","sl","so","st","es","su","sw","ss","sv","tg","ta","tt","te","th","bo","ti","to","ts","tn","tum","tr","tk","uk","ur","ug","uz","ve","vi","war","cy","fy","wo","xh","yi","yo","zu"])

                logger.info(f"Transcript found in {transcript.language}")

                logger.info(f"Translating transcripts to English!!")
                transcript = transcript.translate('en')
                logger.info(f"Successfully translated transcripts to English!!")
            return transcript.fetch()
        
        except Exception as e:
            print("Could not Extract Transcripts : ", e)
            return None

    async def process_link(self, video_link, batch_size = 300, language='en'):
        video_id = await self.extract_video_id(video_link)
        transcripts = self.fetch_transcripts(video_id, language=language)
        batch_formatted = self.formatter.format_transcript(transcripts, batch_size)
        data = {
            'video_id' : video_id,
            'transcripts' : batch_formatted
        }
        return data