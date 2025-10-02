import { initializeApp } from 'firebase/app';
import { getFunctions, connectFunctionsEmulator } from 'firebase/functions';

// Firebase configuration
const firebaseConfig = {
  // For local development, we'll use the Firebase emulator
  projectId: 'frontdeskdemo-will', // This can be any project ID for local development
  // Add other config as needed for your Firebase project
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Firebase Functions
const functions = getFunctions(app);

// Connect to local Firebase Functions emulator
// The default port for Firebase Functions emulator is 5001
if (import.meta.env.DEV) {
  connectFunctionsEmulator(functions, 'localhost', 5001);
}

export { functions };
export default app;
