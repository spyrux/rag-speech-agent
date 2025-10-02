import asyncio
import json
import logging
import os
from typing import Annotated, List
from google.cloud import firestore
import aiohttp
import openai as openai_client
from dotenv import load_dotenv
from livekit.agents import (
    NOT_GIVEN,
    Agent,
    AgentFalseInterruptionEvent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    cli,
    llm,
    metrics,
    get_job_context
)
from livekit.agents.llm import function_tool
from livekit.plugins import cartesia, deepgram, noise_cancellation, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions = """
            You are a helpful assistant for a fictional beauty salon, Luxe Locks (downtown Springfield).
            Services: haircuts, coloring, styling, manicures, pedicures, spa treatments.
            Audience: young professionals and families.
            Tone: welcoming and concise.

            ALWAYS follow this policy for every user question or request:

            1) First, check whether the question can be answered using the facts above (location, services, audience, atmosphere).
            - If yes, answer directly from the prompt and stop.
            - Example: "Where are you located?" → "We’re in downtown Springfield."

            2) If the answer is not found in the prompt, call the `answer` tool with the user's raw utterance.

            3) If the tool returns a KB answer, speak that answer.

            4) If the tool indicates it escalated to a supervisor, speak exactly:
            "Let me check with my supervisor and get back to you."

            Never guess or fabricate salon facts; only use the prompt facts, KB results, or escalate.
            """,

        )
        self.collection_name = "answers_index"
        openai_client.api_key = os.getenv("OPENAI_API_KEY")
        self.FIREBASE_URL= os.environ.get("FIREBASE_URL")

    def _get_query_embedding(self, text: str) -> List[float]:
        """Compute the embedding for the given text using the same model as ingestion."""
        response = openai_client.embeddings.create(
            input=text,
            model="text-embedding-3-small",
            dimensions=1536,
        )
        return response.data[0].embedding

    async def _firebase_vector_search(self, *, collection_name: str, query_vector: list[float] = None, limit: int = 3):
        """Call the Firebase search_vectors endpoint and return matches."""
        if not self.FIREBASE_URL:
            raise RuntimeError("FIREBASE_URL is not set")
        if not query_vector:
            raise ValueError("Provide query_vector")
        payload = {
            "query_vector": query_vector,
            "collection": collection_name,
            "top_k": limit,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.FIREBASE_URL+"/vector_search", json=payload, timeout=10) as r:
                text = await r.text()
                if r.status != 200:
                    raise RuntimeError(f"Firebase search failed: {r.status} {text}")
                data = json.loads(text)
                return data.get("matches", [])
            

    async def post_user_query(self, context: RunContext, query: str):
        """Post a user message to the HITL endpoint.

        Args:
            query: The user's query to send to the endpoint
        """
        url = self.FIREBASE_URL+"/addquery"
        
        # Prepare the query data
        room = get_job_context().room
        participant = next(iter(room.remote_participants.values()))
        job_id = get_job_context().job.id
        query_data = {
            "query": query,
            "user_id": participant.attributes.get("user_id"),
            "room_name": room.name,
            "job_id": job_id,
        }

        logger.info(f"Posting user query to {url}: {query}")
        logger.info(f"Extracted user_id: {participant.attributes.get('user_id')}")
        logger.info(f"Extracted job_id: {job_id}")
        logger.info(f"Extracted room_name: {room.name}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=query_data) as response:
                    response_text = await response.text()
                    logger.info(f"Response status: {response.status}")
                    logger.info(f"Response body: {response_text}")
                    
                    if response.status == 201:
                        return f"Contacting supervisor. Response: {response_text}"
                    else:
                        return f"Failed to post query. Status: {response.status}, Response: {response_text}"
                    
        except aiohttp.ClientError as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            return error_msg

    @function_tool
    async def answer(self, context: RunContext, query: str) -> str:
        """
        Resolve user questions by checking the KB first, then escalating if needed.
        Returns the exact text the agent should say to the user.
        """
        # 1) Try KB
        kb_resp = await self.retrieve_info(context, query=query)
        if kb_resp and "I couldn't find relevant information" not in kb_resp:
            # Strip the "Here's what I found:\n" prefix if present
            if kb_resp.lower().startswith("here's what i found"):
                kb_resp = kb_resp.split("\n", 1)[-1].strip() or kb_resp
            return kb_resp

        # 2) Escalate (HITL)
        # Post to supervisor, then return the mandated line
        await self.post_user_query(context, query=query)
        return "Let me check with my supervisor and get back to you."

    async def retrieve_info(self, context: RunContext, query: str) -> str:
        """Retrieve relevant information from the KB.
        Args:
            query: The user's query to search in knowledge base.
        """
        try:
            logger.info(f"retrieve_info called with query: {query}")

            # Step 2: Compute embedding for the query
            query_embedding = await asyncio.to_thread(self._get_query_embedding, query)
            # Step 3: Perform a semantic search using the query embedding
            semantic_results = await self._firebase_vector_search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=3,  # Retrieve top 3 most relevant results
            )
            logger.info(f"Semantic search returned {len(semantic_results)} points")
            if not semantic_results or len(semantic_results) == 0:
                return "I couldn't find relevant information in our knowledge base."

            # Step 4: Combine retrieved results into a concise response
            retrieved_texts = []
            for r in semantic_results:
                # your server returns fields at the top level (no "payload")
                text = (r.get("answer_text") or "").strip()
                if text:
                    retrieved_texts.append(text)
            logger.info(f"Retrieved texts: {retrieved_texts}")
            if not retrieved_texts:
                return "I couldn't find relevant information in our knowledge base."

            combined_response = "\n".join(retrieved_texts)
            truncated_response = combined_response[:1000]  # Limit response length
            logger.info(f"Returning combined response: {truncated_response}")
            return f"Here's what I found:\n{truncated_response}"

        except Exception as e:
            logger.error(f"Error in retrieve_info: {e}")
            return f"Error retrieving information: {str(e)}"


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }
    logger.info(f"Job context metadata: {ctx.job.metadata}")
    # logger.info(f"User connected to room: {user_name} (ID: {user_id})")
    logger.info(f"Room participants: {[p.identity for p in ctx.room.remote_participants.values()]}")

    # Set up a watch for answers

    # Set up participant tracking for user identity logging BEFORE starting the session
    @ctx.room.on("participant_connected")
    def _on_participant_connected(participant):
        logger.info(f"Participant connected: {participant.identity} (SID: {participant.sid})")
        md = participant.metadata
        try:
            md_obj = json.loads(md) if md else {}
            logger.info(f"Participant metadata (parsed): {md_obj}")
        except Exception:
            logger.info(f"Participant metadata (raw): {md}")

    @ctx.room.on("participant_disconnected")
    def _on_participant_disconnected(participant):
        logger.info(f"Participant disconnected: {participant.identity} (SID: {participant.sid})")


    # Set up a voice AI pipeline using OpenAI, Cartesia, Deepgram, and the LiveKit turn detector
    session = AgentSession(
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all providers at https://docs.livekit.io/agents/integrations/llm/
        llm=openai.LLM(model="gpt-4o-mini"),
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all providers at https://docs.livekit.io/agents/integrations/stt/
        stt=deepgram.STT(model="nova-3", language="multi"),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all providers at https://docs.livekit.io/agents/integrations/tts/
        tts=cartesia.TTS(voice="6f84f4b8-58a2-430c-8c79-688dad597532"),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=False,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead:
    # session = AgentSession(
    #     # See all providers at https://docs.livekit.io/agents/integrations/realtime/
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # sometimes background noise could interrupt the agent session, these are considered false positive interruptions
    # when it's detected, you may resume the agent's speech
    @session.on("agent_false_interruption")
    def _on_agent_false_interruption(ev: AgentFalseInterruptionEvent):
        logger.info("false positive interruption, resuming")
        session.generate_reply(instructions=ev.extra_instructions or NOT_GIVEN)

    # Metrics collection, to measure pipeline performance
    # For more information, see https://docs.livekit.io/agents/build/metrics/
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/integrations/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/integrations/avatar/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()
    
    # Set up a watch for answers
    db = firestore.Client(project="frontdeskdemo-will")
    answers_query = (
    db.collection("answers")
      .where("room_name", "==", ctx.room.name)
      .where("spoken", "==", False)
    )
    def _on_answers(docs, changes, read_time):
        for ch in changes:
            if ch.type.name not in ("ADDED", "MODIFIED"):
                continue
            data = ch.document.to_dict() or {}
            text = (data.get("answer_text") or "").strip()
            if not text:
                continue

            # 1) Immediately follow up to the caller (speak in the room)
            # If you only want to simulate, replace with: print(f"[SIM] FOLLOW-UP: {text}")
            asyncio.run_coroutine_threadsafe(session.say(text), asyncio.get_event_loop())

            # 2) Mark as spoken to avoid repeats
            try:
                ch.document.reference.update({
                    "spoken": True,
                    "spoken_at": firestore.SERVER_TIMESTAMP,
                })
            except Exception:
                logger.exception("Failed to mark answer as spoken")

    answers_watch = answers_query.on_snapshot(_on_answers)
    ctx.add_shutdown_callback(lambda: answers_watch.unsubscribe())

    if ctx.room.remote_participants:
        for p in ctx.room.remote_participants.values():
            logger.info(f"Existing participant: {p.identity} (SID: {p.sid})")
            md = p.metadata
            try:
                md_obj = json.loads(md) if md else {}
                logger.info(f"Existing participant metadata (parsed): {md_obj}")
            except Exception:
                logger.info(f"Existing participant metadata (raw): {md}")
    else:
        logger.info("No existing remote participants at connect() time.")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
