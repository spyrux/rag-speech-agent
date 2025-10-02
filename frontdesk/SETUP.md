# Frontend Firebase Setup Guide

This guide will help you connect the frontend to Firebase Functions running locally.

## Prerequisites

1. **Firebase CLI**: Install Firebase CLI if you haven't already
   ```bash
   npm install -g firebase-tools
   ```

2. **Python Environment**: Make sure you have Python 3.13+ installed

## Setup Steps

### 1. Start Firebase Functions Emulator

Navigate to the Firebase functions directory and start the emulator:

```bash
cd /Users/will/Documents/rag-speech-agent/firebase
firebase emulators:start --only functions
```

This will start the Firebase Functions emulator on `http://localhost:5001`

### 2. Start the Frontend

In a new terminal, navigate to the frontend directory and start the development server:

```bash
cd /Users/will/Documents/rag-speech-agent/frontdesk
npm run dev
```

This will start the Vite development server on `http://localhost:5173`

### 3. Test the Connection

1. Open your browser and go to `http://localhost:5173`
2. You should see the "RAG Speech Agent - Frontend" page
3. Try creating a new query using the form
4. The queries should appear in the list below

## Available Firebase Functions

The frontend is configured to use these Firebase Functions:

- **addquery**: Create a new query
- **getquery**: Get a specific query by ID
- **getallqueries**: Get all queries
- **addanswer**: Add an answer to a query
- **vector_search**: Perform vector search

## Configuration

The Firebase configuration is in `src/firebase.ts`. The frontend automatically connects to the local Firebase Functions emulator when running in development mode.

## Troubleshooting

1. **Connection Issues**: Make sure the Firebase Functions emulator is running on port 5001
2. **CORS Issues**: The Firebase Functions should handle CORS automatically
3. **Type Errors**: Make sure all dependencies are installed with `npm install`

## Development Notes

- The frontend uses Firebase SDK v9+ with modular imports
- All API calls are wrapped in a service layer (`src/api.ts`)
- TypeScript types are defined in `src/types.ts`
- The app automatically connects to the local emulator in development mode
