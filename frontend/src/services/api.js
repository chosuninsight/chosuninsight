// src/services/api.js

const API_BASE_URL = import.meta.env.VITE_API_URL || 'api';
const INTERNAL_API_KEY = import.meta.env.VITE_INTERNAL_API_KEY || '';

const authHeaders = {
  'X-Api-Key': INTERNAL_API_KEY,
};

const toLink = (source) => {
  if (typeof source !== 'string' || !/^https?:\/\//i.test(source)) return null;
  return {
    label: source.replace(/^https?:\/\//i, '').replace(/\/$/, ''),
    url: source,
  };
};

/**
 * 백엔드 RAG 서버와 통신하여 답변을 받아오는 함수
 * @param {string} question 사용자의 질문
 * @param {boolean} debug 디버그 정보 요청 여부
 * @param {string|number|null} sessionId 현재 대화 세션 ID
 * @param {Array} history 이전 대화 내역 (role, content 구조)
 * @returns {Promise<{answer: string, links: Array, debug: object|null}>}
 */
export const fetchChatResponse = async (question, debug = false, sessionId = null, history = []) => {
  const memoryConsent = localStorage.getItem('chosun_memory_consent');
  const isMemoryEnabled = memoryConsent === 'granted';

  try {
    const response = await fetch(`${API_BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders,
      },
      body: JSON.stringify({ 
        question, 
        debug, 
        session_id: sessionId ? String(sessionId) : null,
        history: history,
        memory_enabled: isMemoryEnabled
      }),
    });

    if (!response.ok) {
      throw new Error('서버 응답에 실패했습니다.');
    }

    const data = await response.json();
    
    // 백엔드 응답 구조: { success: true, documents: [...], sources: [...] }
    return {
      answer: data.answer, 
      links: (data.sources || []).map(toLink).filter(Boolean),
      suggestions: data.suggestions || [],
      debug: data.debug || null,
    };
  } catch (error) {
    console.error('API Error:', error);
    throw error;
  }
};

export const fetchChatMemory = async (sessionId) => {
  if (!sessionId) return null;
  const response = await fetch(`${API_BASE_URL}/memory/${encodeURIComponent(String(sessionId))}`, {
    headers: authHeaders,
  });
  if (!response.ok) throw new Error('메모리 조회에 실패했습니다.');
  const data = await response.json();
  return data.memory || null;
};

export const clearChatMemory = async (sessionId) => {
  if (!sessionId) return null;
  const response = await fetch(`${API_BASE_URL}/memory/${encodeURIComponent(String(sessionId))}`, {
    method: 'DELETE',
    headers: authHeaders,
  });
  if (!response.ok) throw new Error('메모리 삭제에 실패했습니다.');
  const data = await response.json();
  return data.memory || null;
};

export const deleteChatMemoryItem = async (sessionId, memoryId) => {
  if (!sessionId || !memoryId) return null;
  const response = await fetch(
    `${API_BASE_URL}/memory/${encodeURIComponent(String(sessionId))}/items/${encodeURIComponent(String(memoryId))}`,
    {
      method: 'DELETE',
      headers: authHeaders,
    }
  );
  if (!response.ok) throw new Error('메모리 항목 삭제에 실패했습니다.');
  const data = await response.json();
  return data.memory || null;
};
