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
from flask import Flask
from flask_cors import CORS

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

# Initialize Flask app for CORS
app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])

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

def add_cors_headers(response):
    """Add CORS headers to response"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

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
    # Handle CORS preflight request
    if req.method == "OPTIONS":
        response = https_fn.Response("", status=200)
        return add_cors_headers(response)
    
    if req.method != "POST":
        response = https_fn.Response(
            "Method not allowed. Use POST.",
            status=405,
            content_type="text/plain"
        )
        return add_cors_headers(response)

    # Parse JSON body
    data = req.get_json(silent=True) or {}
    query = data.get("query")
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=24)

    if not query:
        response = https_fn.Response("Missing 'query' in request body", status=400)
        return add_cors_headers(response)
    user_id = data.get("user_id")
    if not user_id:
        response = https_fn.Response("Missing 'user_id' in request body", status=400)
        return add_cors_headers(response)
    job_id = data.get("job_id")
    if not job_id:
        response = https_fn.Response("Missing 'job_id' in request body", status=400)
        return add_cors_headers(response)
    room_name = data.get("room_name")
    if not room_name:
        response = https_fn.Response("Missing 'room_name' in request body", status=400)
        return add_cors_headers(response)
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
    print(f"Hey, I need help answering : {query}")
    response = https_fn.Response(
        json.dumps({"id": doc_ref.id, **data}, default=json_default),
        status=201,
        content_type="application/json",
    )
    return add_cors_headers(response)

@https_fn.on_request()
def getquery(req: https_fn.Request) -> https_fn.Response:
    """Fetch a query document by ID and return its data as JSON."""
    # Handle CORS preflight request
    if req.method == "OPTIONS":
        response = https_fn.Response("", status=200)
        return add_cors_headers(response)
    
    # Accept both GET and POST methods (Firebase Functions SDK sends POST by default)
    if req.method not in ["GET", "POST"]:
        response = https_fn.Response(
            "Method not allowed. Use GET or POST.",
            status=405,
            content_type="text/plain"
        )
        return add_cors_headers(response)
    
    # For POST requests, get the ID from the request body
    if req.method == "POST":
        data = req.get_json(silent=True) or {}
        message_id = data.get("id")
    else:
        message_id = req.args.get("id")
    
    if not message_id:
        response = https_fn.Response("Missing id parameter", status=400)
        return add_cors_headers(response)

    firestore_client = firestore.client()
    doc_ref = firestore_client.collection("queries").document(message_id)
    doc = doc_ref.get()

    if not doc.exists:
        response = https_fn.Response(f"Query with ID {message_id} not found", status=404)
        return add_cors_headers(response)

    data = doc.to_dict()
    response = https_fn.Response(
        json.dumps({"data": {"id": doc.id, **data}}, default=json_default),
        status=200,
        content_type="application/json"
    )
    return add_cors_headers(response)

@https_fn.on_request()
def getanswer(req: https_fn.Request) -> https_fn.Response:
    """Fetch a answer document by ID and return its data as JSON."""
    # Handle CORS preflight request
    if req.method == "OPTIONS":
        response = https_fn.Response("", status=200)
        return add_cors_headers(response)
    
    # Accept both GET and POST methods (Firebase Functions SDK sends POST by default)
    if req.method not in ["GET", "POST"]:
        response = https_fn.Response(
            "Method not allowed. Use GET or POST.",
            status=405,
            content_type="text/plain"
        )
        return add_cors_headers(response)
    
    # For POST requests, get the ID from the request body
    if req.method == "POST":
        data = req.get_json(silent=True) or {}
        answer_id = data.get("id")
    else:
        answer_id = req.args.get("id")
    
    if not answer_id:
        response = https_fn.Response("Missing id parameter", status=400)
        return add_cors_headers(response)

    firestore_client = firestore.client()
    doc_ref = firestore_client.collection("answers").document(answer_id)
    doc = doc_ref.get()

    if not doc.exists:
        response = https_fn.Response(f"Answer with ID {answer_id} not found", status=404)
        return add_cors_headers(response)

    data = doc.to_dict()
    response = https_fn.Response(
        json.dumps({"id": doc.id, **data}, default=json_default),
        status=200,
        content_type="application/json"
    )
    return add_cors_headers(response)

@https_fn.on_request()
def getallqueries(req: https_fn.Request) -> https_fn.Response:
    """Fetch all query documents and return them as JSON."""
    # Handle CORS preflight request
    if req.method == "OPTIONS":
        response = https_fn.Response("", status=200)
        return add_cors_headers(response)
    
    # Accept both GET and POST methods (Firebase Functions SDK sends POST by default)
    if req.method not in ["GET", "POST"]:
        response = https_fn.Response(
            "Method not allowed. Use GET or POST.",
            status=405,
            content_type="text/plain"
        )
        return add_cors_headers(response)

    firestore_client = firestore.client()
    queries_ref = firestore_client.collection("queries")
    docs = queries_ref.stream()

    queries = []
    for doc in docs:
        data = doc.to_dict()
        queries.append({"id": doc.id, **data})

    response = https_fn.Response(
        json.dumps({"data": {"queries": queries}}, default=json_default),
        status=200,
        content_type="application/json"
    )
    return add_cors_headers(response)

@https_fn.on_request()
def getallanswers(req: https_fn.Request) -> https_fn.Response:
    """Fetch all answer documents and return them as JSON."""
    # Handle CORS preflight request
    if req.method == "OPTIONS":
        response = https_fn.Response("", status=200)
        return add_cors_headers(response)
    
    # Accept both GET and POST methods (Firebase Functions SDK sends POST by default)
    if req.method not in ["GET", "POST"]:
        response = https_fn.Response(
            "Method not allowed. Use GET or POST.",
            status=405,
            content_type="text/plain"
        )
        return add_cors_headers(response)

    firestore_client = firestore.client()
    answers_ref = firestore_client.collection("answers")
    docs = answers_ref.stream()

    answers = []
    for doc in docs:
        data = doc.to_dict()
        answers.append({"id": doc.id, **data})

    response = https_fn.Response(
        json.dumps({"data": {"answers": answers}}, default=json_default),
        status=200,
        content_type="application/json"
    )
    return add_cors_headers(response)

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
    # Handle CORS preflight request
    if req.method == "OPTIONS":
        response = https_fn.Response("", status=200)
        return add_cors_headers(response)
    
    if req.method != "POST":
        response = https_fn.Response("Method not allowed", status=405)
        return add_cors_headers(response)

    body = req.get_json(silent=True) or {}
    query_vector = body.get("query_vector")
    collection_name = body.get("collection")

    top_k = int(body.get("top_k", 5))

    if not query_vector or not isinstance(query_vector, list):
        response = https_fn.Response("query_vector must be a list", status=400)
        return add_cors_headers(response)
    if not collection_name:
        response = https_fn.Response("collection is required", status=400)
        return add_cors_headers(response)

    try:
        firestore_client = firestore.client()
        collection = firestore_client.collection(collection_name)
        vector_query = collection.find_nearest(
            vector_field="query_embedding",
            query_vector=Vector([float(x) for x in query_vector]),
            distance_measure=DistanceMeasure.COSINE,
            distance_result_field="_vector_distance",
            distance_threshold=0.6,
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

        response = https_fn.Response(
            json.dumps({"matches": results}, default=json_default),
            status=200,
            content_type="application/json",
        )
        return add_cors_headers(response)

    except Exception as e:
        response = https_fn.Response(f"Error performing vector search: {e}", status=500)
        return add_cors_headers(response)

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
    # Handle CORS preflight request
    if req.method == "OPTIONS":
        response = https_fn.Response("", status=200)
        return add_cors_headers(response)
    
    if req.method != "POST":
        response = https_fn.Response("Method not allowed", status=405)
        return add_cors_headers(response)
    firestore_client = firestore.client()
    body: Dict[str, Any] = req.get_json(silent=True) or {}
    qid       = body.get("query_id")
    ans_text  = body.get("answer_text")
    resolved_by = body.get("resolved_by")
    
    if not qid or not ans_text:
        response = https_fn.Response("query_id and answer_text required", status=400)
        return add_cors_headers(response)
    qref = firestore_client.collection("queries").document(qid)
    qsnap = qref.get()
    if not qsnap.exists:
        response = https_fn.Response("Query not found", status=404)
        return add_cors_headers(response)
    q = qsnap.to_dict() or {}

    # 1) Compute embedding outside the transaction (fast fail if missing key/model)
    try:
        vec = get_embedding_sync(q.get("query"))
    except Exception as e:
        response = https_fn.Response(f"Embedding failed: {e}", status=500)
        return add_cors_headers(response)

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
            "query_embedding": Vector(vec),   # vector field
            "embedding_dim": EMBED_DIM,
            "embedding_model": EMBED_MODEL,
            "created_at": now,
            "updated_at": now,
        })

        # /queries/{qid} update
        updates = {
            "status": "resolved",
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
        response = https_fn.Response(str(ve), status=404)
        return add_cors_headers(response)
    except Exception as e:
        response = https_fn.Response(f"Write failed: {e}", status=500)
        return add_cors_headers(response)
    print(f"Supervisor answered the query:{qid} with answer:{ans_text}")
    response = https_fn.Response(
        json.dumps({"answer_id": aref.id, "query_id": qid, "status": "answered"}),
        status=201,
        content_type="application/json",
    )
    return add_cors_headers(response)