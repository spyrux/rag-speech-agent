import { useState, useEffect } from 'react'
import './App.css'
import ApiService from './api'
import type { Query, CreateAnswerRequest } from './types'

type TabType = 'pending' | 'resolved' | 'unresolved'

function App() {
  const [activeTab, setActiveTab] = useState<TabType>('pending')
  const [queries, setQueries] = useState<Query[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedQuery, setSelectedQuery] = useState<Query | null>(null)
  const [answerText, setAnswerText] = useState('')
  const [submittingAnswer, setSubmittingAnswer] = useState(false)
  const [selectedAnswer, setSelectedAnswer] = useState<string>('')
  const [loadingAnswer, setLoadingAnswer] = useState(false)

  // Load all queries on component mount
  useEffect(() => {
    loadQueries()
  }, [])

  const loadQueries = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await ApiService.getAllQueries()
      if (response.success && response.data) {
        setQueries(response.data)
      } else {
        setError(response.error || 'Failed to load queries')
      }
    } catch (err) {
      setError('Failed to load queries')
    } finally {
      setLoading(false)
    }
  }
  const getAnswer = async (query?: Query) => {
    const targetQuery = query || selectedQuery
    if (!targetQuery || !targetQuery.answer_id) return
    
    setLoadingAnswer(true)
    setError(null)
    try {
      console.log(targetQuery.answer_id)
      const response = await ApiService.getAnswer(targetQuery.answer_id)
      console.log(response)
      if (response.success) {
        setSelectedAnswer(response.data?.text || '')
      } else {
        setError(response.error || 'Failed to load answer')
      }
    } catch (err) {
      setError('Failed to load answer')
    } finally {
      setLoadingAnswer(false)
    }
  }
  const submitAnswer = async () => {
    if (!selectedQuery || !answerText.trim()) return
    
    setSubmittingAnswer(true)
    setError(null)
    try {
      const answerRequest: CreateAnswerRequest = {
        query_id: selectedQuery.query_id,
        answer_text: answerText,
        resolved_by: 'human-operator'
      }
      
      const response = await ApiService.addAnswer(answerRequest)
      
      if (response.success) {
        setAnswerText('')
        setSelectedQuery(null)
        loadQueries() // Reload queries
      } else {
        setError(response.error || 'Failed to submit answer')
      }
    } catch (err) {
      setError('Failed to submit answer')
    } finally {
      setSubmittingAnswer(false)
    }
  }

  const filteredQueries = queries.filter(query => {
    switch (activeTab) {
      case 'pending':
        return query.status === 'pending'
      case 'resolved':
        return query.status === 'resolved'
      case 'unresolved':
        return query.status === 'unresolved'
      default:
        return true
    }
  })

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending':
        return '#fff3cd'
      case 'resolved':
        return '#e8f5e8'
      case 'unresolved':
        return '#f8d7da'
      default:
        return '#f8f9fa'
    }
  }

  const getStatusText = (status: string) => {
    switch (status) {
      case 'pending':
        return 'Pending'
      case 'resolved':
        return 'Resolved'
      case 'unresolved':
        return 'Unresolved'
      default:
        return status
    }
  }

  return (
    <div style={{ maxWidth: '1200px', margin: '0', padding: '20px' }}>
      <header style={{ textAlign: 'center', marginBottom: '30px' }}>
        <h1 style={{ color: '#333', marginBottom: '10px' }}>Request Management System</h1>
        <p style={{ color: '#666' }}>Manage and respond to customer requests</p>
      </header>

      {/* Error Display */}
      {error && (
        <div style={{ 
          color: 'red', 
          marginBottom: '20px',
          padding: '12px',
          backgroundColor: '#ffe6e6',
          border: '1px solid #ffcccc',
          borderRadius: '6px'
        }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Tab Navigation */}
      <div style={{ 
        display: 'flex', 
        marginBottom: '20px',
        borderBottom: '2px solid #e9ecef'
      }}>
        {[
          { key: 'pending', label: 'Pending Requests', count: queries.filter(q => q.status === 'pending').length },
          { key: 'resolved', label: 'Resolved', count: queries.filter(q => q.status === 'resolved').length },
          { key: 'unresolved', label: 'Unresolved', count: queries.filter(q => q.status === 'unresolved').length }
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => {
              setActiveTab(tab.key as TabType)
              setSelectedQuery(null)
              setSelectedAnswer('')
              setAnswerText('')
            }}
            style={{
              padding: '12px 24px',
              border: 'none',
              backgroundColor: activeTab === tab.key ? '#007bff' : 'transparent',
              color: activeTab === tab.key ? 'white' : '#666',
              cursor: 'pointer',
              borderBottom: activeTab === tab.key ? '2px solid #007bff' : '2px solid transparent',
              fontWeight: activeTab === tab.key ? 'bold' : 'normal'
            }}
          >
            {tab.label} ({tab.count})
          </button>
        ))}
        
        <button 
          onClick={loadQueries}
          disabled={loading}
          style={{
            marginLeft: 'auto',
            padding: '8px 16px',
            backgroundColor: '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: loading ? 'not-allowed' : 'pointer'
          }}
        >
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Main Content */}
      <div style={{ display: 'flex', gap: '20px' }}>
        {/* Requests List */}
        <div style={{ flex: 1 }}>

          
          {filteredQueries.length === 0 ? (
            <div style={{ 
              textAlign: 'center', 
              padding: '40px',
              color: '#666',
              backgroundColor: '#f8f9fa',
              borderRadius: '6px'
            }}>
              <p>No {activeTab} requests found.</p>
            </div>
          ) : (
            <div style={{ maxHeight: '600px', overflowY: 'auto' }}>
              {filteredQueries.map((query) => (
                <div 
                  key={query.query_id} 
                  style={{ 
                    border: '1px solid #ddd', 
                    padding: '16px', 
                    margin: '8px 0',
                    borderRadius: '6px',
                    backgroundColor: getStatusColor(query.status),
                    cursor: (activeTab === 'pending' || (activeTab === 'resolved' && query.answer_id)) ? 'pointer' : 'default',
                    transition: 'all 0.2s ease'
                  }}
                  onClick={() => {
                    if (activeTab === 'pending') {
                      setSelectedQuery(query)
                      setSelectedAnswer('')
                    } else if (activeTab === 'resolved' && query.answer_id) {
                      setSelectedQuery(query)
                      getAnswer(query)
                    }
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>
                        {query.query}
                      </div>
                      <div style={{ fontSize: '14px', color: '#666' }}>
                        <strong>User:</strong> {query.user_id} | 
                        <strong> Room:</strong> {query.room_name} | 
                        <strong> Job:</strong> {query.job_id}
                      </div>
                    </div>
                    <div style={{ 
                      padding: '4px 8px', 
                      borderRadius: '4px',
                      backgroundColor: query.status === 'pending' ? '#ffc107' : 
                                     query.status === 'resolved' ? '#28a745' : '#dc3545',
                      color: 'white',
                      fontSize: '12px',
                      fontWeight: 'bold'
                    }}>
                      {getStatusText(query.status)}
                    </div>
                  </div>
                  
                  <div style={{ fontSize: '12px', color: '#666' }}>
                    <strong>Created:</strong> {new Date(query.created_at).toLocaleString()}

                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Answer Submission Panel (only for pending requests) */}
        {activeTab === 'pending' && selectedQuery && (
          <div style={{ 
            width: '400px', 
            padding: '20px',
            backgroundColor: '#f8f9fa',
            borderRadius: '6px',
            border: '1px solid #ddd'
          }}>
            <h3 style={{ marginBottom: '16px', color: '#333' }}>Submit Answer</h3>
            
            <div style={{ marginBottom: '16px' }}>
              <strong>Request:</strong>
              <div style={{ 
                padding: '8px', 
                backgroundColor: 'white', 
                borderRadius: '4px',
                marginTop: '4px',
                fontSize: '14px'
              }}>
                {selectedQuery.query}
              </div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>
                Your Answer:
              </label>
              <textarea
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value)}
                placeholder="Enter your answer here..."
                style={{
                  width: '100%',
                  height: '120px',
                  padding: '8px',
                  border: '1px solid #ccc',
                  borderRadius: '4px',
                  resize: 'vertical',
                  fontFamily: 'inherit'
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={submitAnswer}
                disabled={submittingAnswer || !answerText.trim()}
                style={{
                  flex: 1,
                  padding: '10px 16px',
                  backgroundColor: '#007bff',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: submittingAnswer ? 'not-allowed' : 'pointer',
                  fontWeight: 'bold'
                }}
              >
                {submittingAnswer ? 'Submitting...' : 'Submit Answer'}
              </button>
              
              <button
                onClick={() => {
                  setSelectedQuery(null)
                  setAnswerText('')
                }}
                style={{
                  padding: '10px 16px',
                  backgroundColor: '#6c757d',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Answer Display Panel (only for resolved requests) */}
        {activeTab === 'resolved' && selectedQuery && (
          <div style={{ 
            width: '400px', 
            padding: '20px',
            backgroundColor: '#f8f9fa',
            borderRadius: '6px',
            border: '1px solid #ddd'
          }}>
            <h3 style={{ marginBottom: '16px', color: '#333' }}>Answer Details</h3>
            
            <div style={{ marginBottom: '16px' }}>
              <strong>Request:</strong>
              <div style={{ 
                padding: '8px', 
                backgroundColor: 'white', 
                borderRadius: '4px',
                marginTop: '4px',
                fontSize: '14px'
              }}>
                {selectedQuery.query}
              </div>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <strong>Answer:</strong>
              {loadingAnswer ? (
                <div style={{ 
                  padding: '8px', 
                  backgroundColor: 'white', 
                  borderRadius: '4px',
                  marginTop: '4px',
                  textAlign: 'center',
                  color: '#666'
                }}>
                  Loading answer...
                </div>
              ) : selectedAnswer ? (
                <div style={{ 
                  padding: '8px', 
                  backgroundColor: 'white', 
                  borderRadius: '4px',
                  marginTop: '4px',
                  fontSize: '14px',
                  whiteSpace: 'pre-wrap'
                }}>
                  {selectedAnswer}
                </div>
              ) : (
                <div style={{ 
                  padding: '8px', 
                  backgroundColor: '#fff3cd', 
                  borderRadius: '4px',
                  marginTop: '4px',
                  fontSize: '14px',
                  color: '#856404'
                }}>
                  No answer available
                </div>
              )}
            </div>

            <div style={{ fontSize: '12px', color: '#666', marginBottom: '16px' }}>
              <strong>Resolved by:</strong> {selectedQuery.resolved_by || 'Unknown'} | 
              <strong> Resolved at:</strong> {selectedQuery.last_response_at ? new Date(selectedQuery.last_response_at).toLocaleString() : 'Unknown'}
            </div>
            
            <button
              onClick={() => {
                setSelectedQuery(null)
                setSelectedAnswer('')
              }}
              style={{
                padding: '10px 16px',
                backgroundColor: '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                width: '100%'
              }}
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default App