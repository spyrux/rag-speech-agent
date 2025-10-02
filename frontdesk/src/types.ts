// API Types for Firebase Functions

export interface Query {
  query: string;
  query_id: string;
  user_id: string;
  room_name: string;
  job_id: string;
  status: 'pending' | 'resolved' | 'unresolved';
  created_at: string;
  updated_at: string;
  deadline: string;
  answer_id?: string;
  resolved_by?: string;
  last_response_at?: string;
}

export interface Answer {
  id: string;
  answer_id: string;
  query_id: string;
  user_id: string;
  text: string;
  created_at: string;
  updated_at: string;
}

export interface VectorSearchResult {
  id: string;
  query_id: string;
  answer_text: string;
  score?: number;
  created_at: string;
  updated_at: string;
}

export interface CreateQueryRequest {
  query: string;
  user_id: string;
  job_id: string;
  room_name: string;
}

export interface CreateAnswerRequest {
  query_id: string;
  answer_text: string;
  resolved_by?: string;
}

export interface VectorSearchRequest {
  query_vector: number[];
  collection: string;
  top_k?: number;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}
