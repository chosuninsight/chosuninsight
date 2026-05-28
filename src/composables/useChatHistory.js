import { ref } from 'vue'

const STORAGE_KEY = 'chosun_chat_histories'
const CURRENT_ID_KEY = 'chosun_current_chat_id'

function loadFromStorage() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || []
  } catch {
    return []
  }
}

// 모듈 레벨 ref → 어디서 import해도 같은 상태 공유
const histories = ref(loadFromStorage())
const currentChatId = ref(null)

function saveToStorage() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(histories.value))
}

function getTimeString() {
  const d = new Date()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

// 새 대화 시작 — ID를 세팅하고 초기 메시지 배열 반환
function createNewChat() {
  const id = typeof crypto !== 'undefined' && crypto.randomUUID 
    ? crypto.randomUUID() 
    : Math.random().toString(36).substring(2, 15) + Date.now().toString(36);

  currentChatId.value = id
  localStorage.setItem(CURRENT_ID_KEY, String(id))
  return [{ who: 'bot', text: '안녕하세요! 조선대학교에 대해 궁금한 점을 물어보세요.', time: getTimeString() }]
}

// 현재 대화 저장 — 사용자 메시지가 없으면 저장하지 않음 (빈 대화 방지)
function saveCurrentChat(messages) {
  if (!currentChatId.value) return
  const firstUserMsg = messages.find(m => m.who === 'user')
  if (!firstUserMsg) return

  const raw = firstUserMsg.text
  const title = raw.length > 20 ? raw.slice(0, 20) + '...' : raw

  const entry = {
    id: currentChatId.value,
    title,
    messages: [...messages],
    updatedAt: Date.now(),
  }

  const idx = histories.value.findIndex(h => h.id === currentChatId.value)
  if (idx !== -1) {
    histories.value[idx] = entry
  } else {
    histories.value.unshift(entry)
  }

  saveToStorage()
}

// 특정 대화 불러오기
function loadChat(id) {
  const found = histories.value.find(h => h.id === id)
  if (!found) return null
  currentChatId.value = id
  localStorage.setItem(CURRENT_ID_KEY, String(id))
  return [...found.messages]
}

// 마지막으로 열었던 대화 복원
function loadLastChat() {
  const lastId = localStorage.getItem(CURRENT_ID_KEY)
  if (!lastId) return null
  return loadChat(lastId)
}

// 개별 삭제 — 현재 대화가 삭제됐으면 true 반환
function deleteChat(id) {
  histories.value = histories.value.filter(h => h.id !== id)
  saveToStorage()
  if (currentChatId.value === id) {
    currentChatId.value = null
    localStorage.removeItem(CURRENT_ID_KEY)
    return true
  }
  return false
}

// 전체 삭제
function clearAll() {
  histories.value = []
  currentChatId.value = null
  localStorage.removeItem(STORAGE_KEY)
  localStorage.removeItem(CURRENT_ID_KEY)
}

export function useChatHistory() {
  return {
    histories,
    currentChatId,
    createNewChat,
    saveCurrentChat,
    loadChat,
    loadLastChat,
    deleteChat,
    clearAll,
  }
}
