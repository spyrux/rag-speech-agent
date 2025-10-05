<h1>Demo</h1>

[![IMAGE ALT TEXT HERE](https://img.youtube.com/vi/9uLU-GUbZrs/hqdefault.jpg)](https://www.youtube.com/watch?v=9uLU-GUbZrs)


<h1>Design</h1>

<img width="1563" height="376" alt="Untitled-2025-09-23-0300" src="https://github.com/user-attachments/assets/4ba4f39c-87bf-4eee-afa8-e781dda12e78" />


<img width="1590" height="398" alt="Untitled-2025-09-23-0301" src="https://github.com/user-attachments/assets/f7864451-7d00-473a-910f-dfe37b1f6a7a" />



<img width="1486" height="881" alt="Untitled-2025-09-23-0302" src="https://github.com/user-attachments/assets/1a2710c7-8d99-439d-bfe6-26b0d6f2adb5" />




<h1>Setup</h1>

<h2>Running the Agent</h2>
In the agent-starter-python directory run:

``` 
uv sync
uv pip install -r requirements.txt
```

Sign up for LiveKit Cloud then set up the environment by copying .env.example to .env.local and filling in the required keys:

```
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
DEEPGRAM_API_KEY
CARTESIA_API_KEY
FIREBASE_URL=http://127.0.0.1:5001/frontdeskdemo-will/us-central1
FIRESTORE_EMULATOR_HOST="localhost:8080"
```

Before your first run, you must download certain models such as Silero VAD and the LiveKit turn detector:

```
uv run python src/agent.py download-files
```
To run the agent server:
```
uv run python src/agent.py dev
```

<h2>Running the Agent Interface</h2>
Open the agent-starter-react directory.
You'll also need to configure your LiveKit credentials in this folder's .env.local (copy .env.example if you don't have one):

```
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
LIVEKIT_URL=https://your-livekit-server-url
```

Then run the app with:

```
pnpm install
pnpm dev
```

<h2>Running the HITL server</h2>
Enter the firebase directory.
Install Firebase CLI

```
npm install -g firebase-tools
firebase init emulators
```

Set up environment for local Functions
Create .env.local in functions/ with your keys (e.g. OPENAI_API_KEY, etc.).

```
OPENAI_API_KEY=sk-xxxx
```
Create and activate a venv with uv:
```
cd functions
uv venv --python 3.13 venv
source venv/bin/activate
```
Install dependencies:
```
uv sync
uv pip install -r requirements.txt
```

Run the Firebase Emulator:
```
firebase emulators:start
```

<h2>Running the Admin UI</h2>

In the frontdesk directory run:
```
pnpm install
pnpm dev
```


<h1>API's and Collections</h1>

Collections

queries/{id}: { query, user_id, room_name, job_id, status: "pending|resolved|unresolved", deadline, answer_id?, last_response_at?, resolved_by?, created_at, updated_at }

answers/{id}: { query_id, user_id, text, created_at, updated_at }

answers_index/{id}: { query_id, answer_text, query_embedding(Vector), embedding_dim, embedding_model, created_at, updated_at }

timers/{id}: { query_ref, delete_at } → on delete sets linked query status="unresolved".

<h2>Endpoints</h2>

| Method                     | Path           | Description                             | Body                                               |
| -------------------------- | -------------- | --------------------------------------- | -------------------------------------------------- |
| POST                       | /addquery      | Create a query + TTL timer              | {query, user_id, job_id, room_name}                |
| GET                        | /getquery      | Get one query by ID                     | \-                                                 |
| GET                        | /getanswer     | Get one answer by ID                    | \-                                                 |
| GET                        | /getallqueries | List all queries                        | \-                                                 |
| GET                        | /getallanswers | List all answers                        | \-                                                   |
| POST                       | /vector_search | Vector nearest-neighbor search          | {query_vector:number[], collection:string, top_k?} |
| POST                       | /addanswer     | Create answer, index embedding, resolve | {query_id, answer_text, resolved_by?}              |


<h1>Key Design Decisions</h1>
- /answer_index stores "query_embeddings" and "answer_text" to allow for vector search using "query_vector"  

- Created /timers collection to utilize Firebase's ttl for automatic document deletion, which calls a callback to update query status to "unresolved" for timeouts.

  
- Vector search utilizes Cosine Similarity, which measures orientation and not magnitude and is optimal for text embedding retrieval.

  
- Queries are stored with user_id, room_name, job_id, to simulate necessary metadata for a callback to a user.

  
- Vector search retrieves top k results to augment with multiple documents if relevant.
