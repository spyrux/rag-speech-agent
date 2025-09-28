# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# Deploy with `firebase deploy`

import asyncio
from firebase_functions import https_fn, firestore_fn
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app, firestore
from openai import OpenAI
import os
import google.cloud.firestore
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

# For cost control, you can set the maximum number of containers that can be
# running at the same time. This helps mitigate the impact of unexpected
# traffic spikes by instead downgrading performance. This limit is a per-function
# limit. You can override the limit for each function using the max_instances
# parameter in the decorator, e.g. @https_fn.on_request(max_instances=5).
set_global_options(max_instances=10)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
initialize_app()

def json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)
def normalize_ts(v):
    return v.isoformat() if isinstance(v, datetime) else v

def strip_vectors(d: Dict[str, Any]):
    d.pop("embedding", None)
    d.pop("answer_embedding", None)
    return d

# TTL deletion fires this and updates the query document to unresolved
@firestore_fn.on_document_deleted(document="timers/{id}")
def on_timer_deleted(event: firestore_fn.Event[firestore.DocumentSnapshot]) -> None:
    data = event.data.to_dict() or {}
    query_ref = data.get("query_ref")
    if not query_ref:
        return
    query_ref.update({
        "status": "unresolved",
        "updated_at": firestore.SERVER_TIMESTAMP,
    })

@https_fn.on_request()
def addquery(req: https_fn.Request) -> https_fn.Response:
    """Create a new query document from a POST request with JSON body."""
    if req.method != "POST":
        return https_fn.Response(
            "Method not allowed. Use POST.",
            status=405,
            content_type="text/plain"
        )

    # Parse JSON body
    data = req.get_json(silent=True) or {}
    query = data.get("query")
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=24)

    if not query:
        return https_fn.Response("Missing 'query' in request body", status=400)
    user_id = data.get("user_id")
    if not user_id:
        return https_fn.Response("Missing 'user_id' in request body", status=400)
    job_id = data.get("job_id")
    if not job_id:
        return https_fn.Response("Missing 'job_id' in request body", status=400)
    room_name = data.get("room_name")
    if not room_name:
        return https_fn.Response("Missing 'room_name' in request body", status=400)
    firestore_client = firestore.client()

    _, doc_ref = firestore_client.collection("queries").add({
        "query": query,
        "user_id": user_id,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "room_name": room_name,
        "job_id": job_id,
        "status": "pending",
        "deadline": deadline
    })

    firestore_client.collection("timers").document(doc_ref.id).set({
        "query_ref": doc_ref,        
        "delete_at": deadline,        
    })

    snap = doc_ref.get()
    data = snap.to_dict() or {}
    return https_fn.Response(
        json.dumps({"id": doc_ref.id, **data}, default=json_default),
        status=201,
        content_type="application/json",
    )

@https_fn.on_request()
def getquery(req: https_fn.Request) -> https_fn.Response:
    """Fetch a query document by ID and return its data as JSON."""
    message_id = req.args.get("id")
    if not message_id:
        return https_fn.Response("Missing id parameter", status=400)

    firestore_client = firestore.client()
    doc_ref = firestore_client.collection("queries").document(message_id)
    doc = doc_ref.get()

    if not doc.exists:
        return https_fn.Response(f"Query with ID {message_id} not found", status=404)

    data = doc.to_dict()
    return https_fn.Response(
        json.dumps({"id": doc.id, **data}, default=json_default),
        status=200,
        content_type="application/json"
    )

@https_fn.on_request()
def getallqueries(req: https_fn.Request) -> https_fn.Response:
    """Fetch all query documents and return them as JSON."""
    if req.method != "GET":
        return https_fn.Response(
            "Method not allowed. Use GET.",
            status=405,
            content_type="text/plain"
        )

    firestore_client = firestore.client()
    queries_ref = firestore_client.collection("queries")
    docs = queries_ref.stream()

    queries = []
    for doc in docs:
        data = doc.to_dict()
        queries.append({"id": doc.id, **data})

    return https_fn.Response(
        json.dumps({"queries": queries}, default=json_default),
        status=200,
        content_type="application/json"
    )

@https_fn.on_request()
def vector_search(req: https_fn.Request) -> https_fn.Response:
    """
    POST body:
    {
      "query_vector": [float...],
      "collection": "answer-embeddings",   // required
      "top_k": 5                     // optional (default 5)
    }
    """
    if req.method != "POST":
        return https_fn.Response("Method not allowed", status=405)

    body = req.get_json(silent=True) or {}
    query_vector = body.get("query_vector")
    collection_name = body.get("collection")

    top_k = int(body.get("top_k", 5))

    if not query_vector or not isinstance(query_vector, list):
        return https_fn.Response("query_vector must be a list", status=400)
    if not collection_name:
        return https_fn.Response("collection is required", status=400)

    try:
        firestore_client = firestore.client()
        collection = firestore_client.collection(collection_name)
        vector_query = collection.find_nearest(
            vector_field="embedding",
            query_vector=Vector([float(x) for x in query_vector]),
            distance_measure=DistanceMeasure.COSINE,
            limit=top_k,
        )

        results = []
        for snap in vector_query.stream():
            doc = strip_vectors(snap.to_dict() or {})
            doc["id"] = snap.id
            # Firestore SDKs often attach vector_distance to dict
            if "_vector_distance" in snap.to_dict():
                doc["score"] = snap.to_dict()["_vector_distance"]
            for k in ("created_at", "updated_at"):
                if k in doc:
                    doc[k] = normalize_ts(doc[k])
            results.append(doc)

        return https_fn.Response(
            json.dumps({"matches": results}, default=json_default),
            status=200,
            content_type="application/json",
        )

    except Exception as e:
        return https_fn.Response(f"Error performing vector search: {e}", status=500)

async def embed_text_openai(text: str) -> List[float]:
    # OpenAI client is sync; run in a thread to avoid blocking
    client = OpenAI(api_key=OPENAI_API_KEY)
    def _sync():
        resp = client.embeddings.create(model="text-embedding-3-small", input=text)
        return resp.data[0].embedding
    return await asyncio.to_thread(_sync)


async def get_embedding(text: str) -> List[float]:
    vec = await embed_text_openai(text)
    return vec

@https_fn.on_request()
def addanswer(req: https_fn.Request) -> https_fn.Response:
    """
    POST JSON:
    {
      "query_id": "Q123",
      "answer_text": "…",
      "citations": [{"doc_id":"D1","chunk_id":"C1","score":0.82}],  // optional
      "tags": {"product":"ios","locale":"en"},                       // optional
      "resolved_by": "sup_42"                                        // optional
    }
    Response: { "answer_id": "...", "query_id": "Q123", "status": "answered" }
    """
    if req.method != "POST":
        return https_fn.Response("Method not allowed", status=405)

    body: Dict[str, Any] = req.get_json(silent=True) or {}
    qid = body.get("query_id")
    ans_text = body.get("answer_text")
    citations = body.get("citations") or []
    tags = body.get("tags") or {}
    resolved_by = body.get("resolved_by")

    if not qid or not ans_text:
        return https_fn.Response("query_id and answer_text required", status=400)

    # 1) Compute embedding (outside transaction)
    try:
        vec = asyncio.get_event_loop().run_until_complete(get_embedding(ans_text))
    except Exception as e:
        return https_fn.Response(f"Embedding failed: {e}", status=500)

    firestore_client = firestore.client()
    qref = firestore_client.collection("queries").document(qid)
    aref = firestore_client.collection("answers").document()
    iref = firestore_client.collection("answers_index").document(aref.id)
    EMBED_DIM = 384
    EMBED_MODEL = "text-embedding-3-small"

    # 2) Transaction: verify query, write answer, index, update query
    @firestore.transactional
    def txn(tx):
        qsnap = tx.get(qref)
        if not qsnap.exists:
            raise ValueError("Query not found")

        q = qsnap.to_dict() or {}
        user_id = q.get("user_id")
        now = firestore.SERVER_TIMESTAMP

        # answers
        tx.set(aref, {
            "query_id": qid,
            "user_id": user_id,
            "text": ans_text,
            "citations": citations,
            "created_at": now,
            "updated_at": now,
        })

        # answers_index (vector)
        tx.set(iref, {
            "query_id": qid,
            "answer_text": ans_text,
            "answer_embedding": Vector(vec),
            "embedding_dim": EMBED_DIM,
            "embedding_model": EMBED_MODEL,
            "tags": tags,
            "sources": citations,
            "created_at": now,
            "updated_at": now,
        })

        # queries update
        updates = {
            "status": "answered",
            "answer_id": aref.id,
            "updated_at": now,
            "last_response_at": now,
        }
        if resolved_by:
            updates["resolved_by"] = resolved_by
        tx.update(qref, updates)

    try:
        firestore.transaction()(txn)
    except ValueError as ve:
        return https_fn.Response(str(ve), status=404)
    except Exception as e:
        return https_fn.Response(f"Write failed: {e}", status=500)

    return https_fn.Response(
        json.dumps({"answer_id": aref.id, "query_id": qid, "status": "answered"}),
        status=201,
        content_type="application/json",
    )