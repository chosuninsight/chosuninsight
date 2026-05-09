// src/services/api.js

const API_BASE_URL = import.meta.env.VITE_API_URL || 'api';

/**
 * 백엔드 RAG 서버와 통신하여 답변을 받아오는 함수
 * @param {string} question 사용자의 질문
 * @param {boolean} debug 디버그 정보 요청 여부
 * @param {string|number|null} sessionId 현재 대화 세션 ID
 * @param {Array} history 이전 대화 내역 (role, content 구조)
 * @returns {Promise<{answer: string, links: Array, debug: object|null}>}
 */
export const fetchChatResponse = async (question, debug = false, sessionId = null, history = []) => {
  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ 
        question, 
        debug, 
        session_id: sessionId ? String(sessionId) : null,
        history: history 
      }),
    });

    if (!response.ok) {
      throw new Error('서버 응답에 실패했습니다.');
    }

    const data = await response.json();
    
    // 백엔드 응답 구조: { success: true, documents: [...], sources: [...] }
    return {
      answer: data.answer, 
      links: [],
      suggestions: data.suggestions || [],
      debug: data.debug || null,
    };
  } catch (error) {
    console.error('API Error:', error);
    throw error;
  }
};
