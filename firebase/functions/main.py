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
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1536"))
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
    doc_ref = firestore_client.collection("queries").document() 
    doc_ref.set({
        "query": query,
        "query_id": doc_ref.id, 
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
      "collection": "embeddings",   // required
      "top_k": 5                   
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
            vector_field="answer_embedding",
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

def get_embedding_sync(text: str) -> list[float]:
    """Synchronous embedding call (OpenAI). Replace with your own if needed."""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    vec = resp.data[0].embedding
    if len(vec) != EMBED_DIM:
        raise RuntimeError(f"Embedding dim mismatch: got {len(vec)}, expected {EMBED_DIM}")
    return vec

@https_fn.on_request()
def addanswer(req: https_fn.Request) -> https_fn.Response:
    """
    POST JSON:
    { "query_id": "Q123", "answer_text": "…", "resolved_by": "sup_42" }
    -> { "answer_id": "...", "query_id": "Q123", "status": "answered" }
    """
    if req.method != "POST":
        return https_fn.Response("Method not allowed", status=405)
    firestore_client = firestore.client()
    body: Dict[str, Any] = req.get_json(silent=True) or {}
    qid       = body.get("query_id")
    ans_text  = body.get("answer_text")
    resolved_by = body.get("resolved_by")

    if not qid or not ans_text:
        return https_fn.Response("query_id and answer_text required", status=400)

    # 1) Compute embedding outside the transaction (fast fail if missing key/model)
    try:
        vec = get_embedding_sync(ans_text)
    except Exception as e:
        return https_fn.Response(f"Embedding failed: {e}", status=500)

    qref = firestore_client.collection("queries").document(qid)
    aref = firestore_client.collection("answers").document()              # new answer id
    iref = firestore_client.collection("answers_index").document(aref.id) # mirror for vector search

    # 2) Transaction
    transaction = firestore_client.transaction()

    @firestore.transactional
    def txn(tx: firestore.Transaction):
        qsnap = qref.get(transaction=tx)
        if not qsnap.exists:
            raise ValueError("Query not found")

        q = qsnap.to_dict() or {}
        user_id = q.get("user_id")
        now = firestore.SERVER_TIMESTAMP

        # /answers/{aid}
        tx.set(aref, {
            "query_id": qid,
            "user_id": user_id,
            "text": ans_text,
            "created_at": now,
            "updated_at": now,
        })

        # /answers_index/{aid} (vector field must match your index field & dim)
        tx.set(iref, {
            "query_id": qid,
            "answer_text": ans_text,
            "answer_embedding": Vector(vec),   # vector field
            "embedding_dim": EMBED_DIM,
            "embedding_model": EMBED_MODEL,
            "created_at": now,
            "updated_at": now,
        })

        # /queries/{qid} update
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
        txn(transaction)   # run the transactional function with the transaction object
    except ValueError as ve:
        return https_fn.Response(str(ve), status=404)
    except Exception as e:
        return https_fn.Response(f"Write failed: {e}", status=500)

    return https_fn.Response(
        json.dumps({"answer_id": aref.id, "query_id": qid, "status": "answered"}),
        status=201,
        content_type="application/json",
    )