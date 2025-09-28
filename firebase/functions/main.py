# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# Deploy with `firebase deploy`

from firebase_functions import https_fn, firestore_fn
from firebase_functions.options import set_global_options
from firebase_admin import initialize_app, firestore
import google.cloud.firestore
import json
from datetime import datetime, timedelta, timezone

# For cost control, you can set the maximum number of containers that can be
# running at the same time. This helps mitigate the impact of unexpected
# traffic spikes by instead downgrading performance. This limit is a per-function
# limit. You can override the limit for each function using the max_instances
# parameter in the decorator, e.g. @https_fn.on_request(max_instances=5).
set_global_options(max_instances=10)

initialize_app()

def json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)

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
def on_request_example(req: https_fn.Request) -> https_fn.Response:
    return https_fn.Response("Hello world!")

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
def getmessage(req: https_fn.Request) -> https_fn.Response:
    """Fetch a message document by ID and return its data as JSON."""
    message_id = req.args.get("id")
    if not message_id:
        return https_fn.Response("Missing id parameter", status=400)

    firestore_client = firestore.client()
    doc_ref = firestore_client.collection("messages").document(message_id)
    doc = doc_ref.get()

    if not doc.exists:
        return https_fn.Response(f"Message with ID {message_id} not found", status=404)

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