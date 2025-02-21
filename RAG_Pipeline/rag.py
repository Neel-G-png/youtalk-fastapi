import os
import json
import uuid
import logging
import asyncio
from openai import OpenAI
from dotenv import load_dotenv

from pinecone import Pinecone
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_mistralai import MistralAIEmbeddings
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

os.environ['HF_TOKEN'] = os.getenv("HF_TOKEN")
os.environ["TOKENIZERS_PARALLELISM"] = "true"

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MISTRALAI_API_KEY = os.getenv("MISTRALAI_API_KEY")


class RAGPipeline():
    def __init__(self, index_name = "youtube-chatbot", embeddings_preference = "mistral"):
        self.pinecone = Pinecone(api_key=PINECONE_API_KEY)
        self.pinecone_index = self.pinecone.Index(index_name)
        self.llm = ChatOpenAI(
            model = "gpt-4o-mini", 
            api_key=OPENAI_API_KEY,
        )
        self.output_parser = StrOutputParser()

        # if embeddings_preference == "ollama":
        #     self.embeddings = OllamaEmbeddings(
        #         model="llama3"
        #     )
        if embeddings_preference == "mistral":
            self.embeddings = MistralAIEmbeddings(
                model="mistral-embed",
                api_key=MISTRALAI_API_KEY,
            )
        # elif embeddings_preference == "openai":
        #     self.embeddings = OpenAIEmbeddings(
        #         model="text-embedding-3-large", 
        #         api_key=OPENAI_API_KEY
        #     )
        else:
            raise ValueError("Invalid embeddings preference")
        
        self.oai_client = OpenAI(api_key=OPENAI_API_KEY)

        self.vector_store = PineconeVectorStore(
            index = self.pinecone_index, 
            embedding = self.embeddings,
            pinecone_api_key = PINECONE_API_KEY
        )

        self.retriever = self.vector_store.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={"k": 3, "score_threshold": 0.5},
        )
    
    def manually_refresh_connections(self):
        self.llm = ChatOpenAI(
            model = "gpt-4o-mini", 
            api_key=OPENAI_API_KEY,
        )
        self.output_parser = StrOutputParser()
        self.retriever = self.vector_store.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={"k": 3, "score_threshold": 0.5},
        )

    def _create_documents(self, user_id, video_id, transcripts):
        transcript_documents = [
            Document(
                page_content= t['text'],
                metadata={"video_id": video_id, "user_id": user_id, "start": t['start'], "end": t['end']}
            )
            for t in transcripts
        ]
        return transcript_documents
    
    def _rechunk_transcripts(self, data, chunk_size=2000, chunk_overlap=500):
        """ Re Split the documents to have some overlap """

        transript_documents = self._create_documents(data['user_id'], data['video_id'], data['transcripts'])

        r_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, 
            chunk_overlap=chunk_overlap
        )

        rechunked = r_splitter.split_documents(transript_documents)
        return rechunked

    def _generate_uuids(self, num_documents):
        return [str(uuid.uuid4()) for _ in range(num_documents)]
    
    def chunk_doc_list(self, docs, N):
        return [docs[i:i + N] for i in range(0, len(docs), N)]

    async def add_documents_vdb(self, documents, uuids):
        ingested_uuids = self.vector_store.add_documents(documents=documents, ids=uuids)
        return ingested_uuids

    async def ingest_data(self, data):
        logger.info(f"ReChunking Transcripts - # of Transcripts: {len(data['transcripts'])}")
        documents = self._rechunk_transcripts(data)
        logger.info(f"ReChunking Complete - # of Transcripts: {len(documents)}")

        ingested_uuids = []
        for docs in self.chunk_doc_list(documents, 50):
            uuids = self._generate_uuids(len(docs))
            batch_uuids = await self.add_documents_vdb(docs, uuids)
            ingested_uuids.extend(batch_uuids)
            await asyncio.sleep(0.8)
        return ingested_uuids

    def delete_records(self, uuids):
        self.vector_store.delete_documents(uuids)

    async def _build_rag_chain(self):
        template = """
        CONTEXT:
        {context}

        QUESTION:
        {question}

        INSTRUCTIONS:
        Answer the users QUESTION using the CONTEXT text above.
        Keep your answer ground in the facts of the CONTEXT.
        If the CONTEXT doesn’t contain the facts to answer the QUESTION return a message that the CONTEXT doesn’t have an exact answer but build an answer based on the provided CONTEXT and try to answer the QUESTION as best as you can.
        """

        # template = """
        #     Answer the user's question based **only** on the provided context. 
        #     If the context does not contain enough information, Mention that the video context does not have an exact answer but build an answer based on the context below and try to answer the question as best as you can.

        #     **Key Points:**  
        #     - (Use bullet points for clarity, if needed)  
        #     - (Highlight essential details in **bold**)  
        #     - (Use `inline code` for specific terms if relevant)  

        #     ### Context:
        #     {context}

        #     ### Question:
        #     {question}

        #     ### Answer:
        # """

        prompt = ChatPromptTemplate.from_template(template)
        
        rag_chain = (
            prompt | self.llm | self.output_parser
        )

        return rag_chain

    async def _build_followup_rag_chain(self):
        contextualize_system_template = """
            You are an AI assistant that **Generates a follow-up question** that builds on past responses, available chat history, and users latest question.

            ### Instructions:
            1. **Reformulate the latest user question** into a self-contained query, incorporating details from chat history wherever they are necessary.
            2. **Do not answer the question**, just reformulate it in a way that makes it clear and self-contained.
            3. If the lastest user question is already clear and self-contained, **return it as is**.

            ### Chat History:
            {chat_history}

            ### Latest Question:
            {input}

            ### Reformulated Question:
        """

        contextualize_system_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", contextualize_system_template),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ]
        )

        contextualize_chain = (contextualize_system_prompt | self.llm | self.output_parser)
        return contextualize_chain

    def retrive(self, query, video_id):
        results = self.retriever.invoke(
            query, 
            filter={
                "video_id": video_id
            }
        )

        return "\n\n".join(results[i].page_content for i in range(len(results)))
    
    async def generate(self, query, video_id):
        rag_chain = await self._build_rag_chain()
        context = self.retrive(query, video_id)
        logger.info(f"User Query: {query} \n\n Video ID: {video_id}")
        async for event in rag_chain.astream_events({"question": query, "context": context}, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk_content = event['data']['chunk'].content
                yield {"event": "stream", "data": chunk_content}

    async def generate_followup(self, query, video_id, history):
        chat_history = []
        if history:
            history = json.loads(history)
            for data in history:
                if data['role'] == "user":
                    chat_history.append(
                        HumanMessage(content = data['msg'])
                    )
                else:
                    chat_history.append(
                        AIMessage(content = data['msg'])
                    )
        logger.info(f"Chat history: {chat_history}")

        contextualize_chain = await self._build_followup_rag_chain()
        contextualized_query = contextualize_chain.invoke({"chat_history": chat_history, "input": query})

        logger.info(f"Contextualized query: {contextualized_query}")

        async for event in self.generate(contextualized_query, video_id):
            yield event