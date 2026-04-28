// src/services/api.js

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

/**
 * 백엔드 RAG 서버와 통신하여 답변을 받아오는 함수
 * @param {string} question 사용자의 질문
 * @returns {Promise<{answer: string, sources: Array}>}
 */
export const fetchChatResponse = async (question) => {
  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question }),
    });

    if (!response.ok) {
      throw new Error('서버 응답에 실패했습니다.');
    }

    const data = await response.json();
    
    // 백엔드 응답 구조: { success: true, documents: [...], sources: [...] }
    return {
      answer: data.answer, 
      links: []
    };
  } catch (error) {
    console.error('API Error:', error);
    throw error;
  }
};
