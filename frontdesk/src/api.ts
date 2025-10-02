import { httpsCallable } from 'firebase/functions';
import { functions } from './firebase';
import type {
  Query,
  VectorSearchResult,
  CreateQueryRequest,
  CreateAnswerRequest,
  VectorSearchRequest,
  ApiResponse,
  Answer
} from './types';

// API Service class for Firebase Functions
export class ApiService {
  // Create a new query
  static async createQuery(request: CreateQueryRequest): Promise<ApiResponse<Query>> {
    try {
      const addQuery = httpsCallable(functions, 'addquery');
      const result = await addQuery(request);
      
      return {
        success: true,
        data: result.data as Query
      };
    } catch (error) {
      console.error('Error creating query:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  // Get a specific query by ID
  static async getQuery(queryId: string): Promise<ApiResponse<Query>> {
    try {
      const res = await fetch(
        `http://localhost:5001/frontdeskdemo-will/us-central1/getquery?id=${queryId}`,
        {
          method: "GET",
          headers: { "Content-Type": "application/json" },
        }
      );
  
      if (!res.ok) {
        return { success: false, error: await res.text() };
      }
  
      const result = await res.json();
      return {
        success: true,
        data: result.data as Query 
      };
    } catch (error) {
      console.error("Error getting query:", error);
      return {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
      };
    }
  }

  // Get all queries
  static async getAllQueries(): Promise<ApiResponse<Query[]>> {
    try {
      const getAllQueries = httpsCallable(functions, 'getallqueries');
      const result = await getAllQueries();
      console.log(result.data);
      return {
        success: true,
        data: (result.data as { queries: Query[] }).queries
      };
    } catch (error) {
      console.error('Error getting all queries:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  // Add an answer to a query
  static async addAnswer(request: CreateAnswerRequest): Promise<ApiResponse<{ answer_id: string; query_id: string; status: string }>> {
    try {
      const res = await fetch("http://localhost:5001/frontdeskdemo-will/us-central1/addanswer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const result = await res.json();
      return {
        success: true,
        data: result.data as { answer_id: string; query_id: string; status: string }
      };
    } catch (error) {
      console.error('Error adding answer:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  // Get an answer by ID
  static async getAnswer(answerId: string): Promise<ApiResponse<Answer>> {
    try {
      const res = await fetch(
        `http://localhost:5001/frontdeskdemo-will/us-central1/getanswer?id=${answerId}`,
        {
          method: "GET",
          headers: { "Content-Type": "application/json" },
        }
      );
  
      if (!res.ok) {
        return { success: false, error: await res.text() };
      }
  
      const result = await res.json();
      return {
        success: true,
        data: result as Answer 
      };
    } catch (error) {
      console.error("Error getting answer:", error);
      return {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
      };
    }
  }

  // Get all answers
  static async getAllAnswers(): Promise<ApiResponse<Answer[]>> {
    try {
      const getAllAnswers = httpsCallable(functions, 'getallanswers');
      const result = await getAllAnswers();
      console.log(result.data);
      return {
        success: true,
        data: (result.data as { answers: Answer[] }).answers
      };
    } catch (error) {
      console.error('Error getting all answers:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }
  // Perform vector search
  static async vectorSearch(request: VectorSearchRequest): Promise<ApiResponse<VectorSearchResult[]>> {
    try {
      const vectorSearch = httpsCallable(functions, 'vector_search');
      const result = await vectorSearch(request);
      
      return {
        success: true,
        data: (result.data as { matches: VectorSearchResult[] }).matches
      };
    } catch (error) {
      console.error('Error performing vector search:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }
}

export default ApiService;
