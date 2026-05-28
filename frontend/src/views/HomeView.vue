<template>
  <div class="home-wrapper">
    <!-- 왼쪽: 히스토리 사이드바 -->
    <ChatSidebar
      :histories="histories"
      :currentChatId="currentChatId"
      :memoryItems="memoryItems"
      :memoryEnabled="memoryEnabled"
      :memoryLoading="memoryLoading"
      @new-chat="onNewChat"
      @load-chat="onLoadChat"
      @delete-chat="onDeleteChat"
      @clear-all="onClearAll"
      @refresh-memory="refreshMemory"
      @delete-memory-item="onDeleteMemoryItem"
      @enable-memory="onEnableMemory"
      @disable-memory="onDisableMemory"
    />

    <!-- 오른쪽: 기존 채팅 영역 -->
    <main class="home">
      <!-- 소개 영역 -->
      <div class="intro-wrap">
        <img :src="introImg" alt="인트로 이미지" class="intro-img" />
        <section class="intro">
          <p class="intro-sub">안녕하세요. <strong>조선인사이트</strong>는 조선대학교 AI 통합 행정 안내 서비스입니다.<br>
        학교소개·학사안내·대학생활 관련 정보 검색을 도와드려요.<br>
    일부 내용은 챗봇에서 바로 안내하기 어려울 수 있으며, 관련 정보는 아래 메뉴의 바로가기 링크를 통해 확인하실 수 있어요.<br>
    챗봇 답변은 참고용으로, 중요한 사항은 학교 홈페이지 공지사항·답변의 출처·링크·관련 부서를 통해 다시 확인해 주세요.</p>
        </section>
      </div>

      <!-- 메뉴 카드 영역 -->
      <div class="menu-carousel">
        <div class="menu-strip">
          <button
            class="menu-arrow left"
            type="button"
            :disabled="menuPage === 0"
            @click.stop="goToPrevMenuPage"
            title="이전 메뉴"
            aria-label="이전 메뉴"
          >
            <ChevronLeft :size="18" aria-hidden="true" />
          </button>
          <div class="menu-viewport">
            <div class="menu-track" :style="{ transform: `translateX(-${menuPage * 100}%)` }">
              <section
                v-for="(page, pageIndex) in menuPages"
                :key="pageIndex"
                class="menu-section"
                :style="{ gridTemplateColumns: `repeat(${page.length}, minmax(0, 1fr))` }"
              >
                <MenuCard
                  v-for="item in page"
                  :key="item.label"
                  :icon="item.icon"
                  :label="item.label"
                  :iconColor="item.iconColor"
                  @click="onMenuClick(item)"
                />
              </section>
            </div>
          </div>
          <button
            class="menu-arrow right"
            type="button"
            :disabled="menuPage >= totalPages - 1"
            @click.stop="goToNextMenuPage"
            title="다음 메뉴"
            aria-label="다음 메뉴"
          >
            <ChevronRight :size="18" aria-hidden="true" />
          </button>
        </div>
        <div class="menu-dots">
          <button
            v-for="i in totalPages"
            :key="i"
            type="button"
            class="dot-btn"
            :class="{ active: menuPage === i - 1 }"
            :aria-label="`${i}번째 메뉴 페이지 보기`"
            :aria-current="menuPage === i - 1 ? 'true' : undefined"
            @click="menuPage = i - 1"
          ></button>
        </div>
      </div>

      <!-- 채팅 메시지 영역 -->
      <section class="chat-section">
        <div class="chat-scroll" ref="chatBox" role="log" aria-live="polite" aria-relevant="additions text">
          <ChatMessage
            v-for="(msg, index) in messages"
            :key="index"
            :who="msg.who"
            :text="msg.text"
            :time="msg.time"
            :links="msg.links"
            :suggestions="msg.suggestions"
            :debug="msg.debug"
            @suggestion-click="sendSuggestedMessage"
          />
          <!-- 로딩 애니메이션 -->
          <div v-if="isLoading" class="message-row bot" aria-label="답변 작성 중">
            <div class="message-wrap">
              <div class="bubble loading-bubble">
                <span class="dot" aria-hidden="true"></span>
                <span class="dot" aria-hidden="true"></span>
                <span class="dot" aria-hidden="true"></span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 하단 입력창 -->
      <section class="input-section">
        <div class="input-card">
          <input
            id="chat-input"
            v-model="inputText"
            class="chat-input"
            type="text"
            name="chat-question"
            autocomplete="off"
            aria-label="질문 입력"
            placeholder="질문을 입력하세요…"
            @keyup.enter="sendMessage"
            :disabled="isLoading"
          />
          <button class="send-btn" type="button" @click="sendMessage" :disabled="isLoading" aria-label="메시지 보내기">
            <ArrowUp :size="18" aria-hidden="true" />
          </button>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import introImg from '../assets/intro.png'
import MenuCard from '../components/MenuCard.vue'
import ChatMessage from '../components/ChatMessage.vue'
import ChatSidebar from '../components/ChatSidebar.vue'
import { useChatHistory } from '../composables/useChatHistory.js'
import { ArrowUp, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { clearChatMemory, deleteChatMemoryItem, fetchChatMemory, fetchChatResponse } from '../services/api.js'
import { menuItems } from '../data/menuItems.js'

const { histories, currentChatId, createNewChat, saveCurrentChat, loadChat, loadLastChat, deleteChat, clearAll } = useChatHistory()

const menuPage = ref(0)
const pageSize = 6
const menuPages = computed(() => {
  const pages = []
  for (let i = 0; i < menuItems.length; i += pageSize) {
    pages.push(menuItems.slice(i, i + pageSize))
  }

  const lastPage = pages[pages.length - 1]
  if (pages.length > 1 && lastPage.length === 1) {
    pages[pages.length - 2] = pages[pages.length - 2].concat(lastPage)
    pages.pop()
  }

  return pages
})
const totalPages = computed(() => menuPages.value.length)

watch(totalPages, (pages) => {
  if (menuPage.value > pages - 1) {
    menuPage.value = Math.max(0, pages - 1)
  }
})

// 페이지 로드 시 마지막 대화 복원, 없으면 새 대화 시작
const _restored = loadLastChat()
const messages = ref(_restored ?? createNewChat())

const inputText = ref('')
const chatBox = ref(null)
const isLoading = ref(false)
const memoryItems = ref([])
const memoryEnabled = ref(localStorage.getItem('chosun_memory_consent') === 'granted')
const memoryLoading = ref(false)
const debugMode = import.meta.env.DEV || localStorage.getItem('chosun_debug') === 'true'

// 동의 상태 실시간 감지
const handleConsentUpdate = (event) => {
  memoryEnabled.value = event.detail === 'granted'
  if (memoryEnabled.value) {
    refreshMemory()
  } else {
    memoryItems.value = []
  }
}

onMounted(() => {
  window.addEventListener('chosun-memory-consent-updated', handleConsentUpdate)
})

onUnmounted(() => {
  window.removeEventListener('chosun-memory-consent-updated', handleConsentUpdate)
})

function now() {
  const d = new Date()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

// 사이드바 이벤트 핸들러
function onNewChat() {
  messages.value = createNewChat()
  refreshMemory()
}

function onLoadChat(id) {
  const loaded = loadChat(id)
  if (loaded) {
    messages.value = loaded
    refreshMemory()
  }
}

function onDeleteChat(id) {
  if (!window.confirm('이 대화를 삭제할까요?')) return
  const wasCurrentChat = deleteChat(id)
  if (wasCurrentChat) messages.value = createNewChat()
  clearChatMemory(id).catch(() => {})
  refreshMemory()
}

function onClearAll() {
  if (!window.confirm('모든 대화 목록을 비울까요?')) return
  histories.value.forEach(item => clearChatMemory(item.id).catch(() => {}))
  clearAll()
  messages.value = createNewChat()
  refreshMemory()
}

function onMenuClick(item) {
  if (!item) return
  addMessage('user', item.label + ' 알려주세요')
  showBotReply(item.botReply, item.links || [])
}

function goToPrevMenuPage() {
  menuPage.value = Math.max(0, menuPage.value - 1)
}

function goToNextMenuPage() {
  menuPage.value = Math.min(totalPages.value - 1, menuPage.value + 1)
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return
  await submitMessage(text)
  inputText.value = ''
}

async function sendSuggestedMessage(text) {
  if (!text || isLoading.value) return
  await submitMessage(text)
}

async function submitMessage(text) {
  // Format history: take last 6 messages, exclude welcome message (who: 'bot' at index 0 often)
  const history = messages.value
    .filter((m, idx) => idx > 0 || m.who === 'user') // simple heuristic to skip initial greeting if it's the very first
    .slice(-6)
    .map(m => ({
      role: m.who === 'user' ? 'user' : 'assistant',
      content: m.text
    }))

  addMessage('user', text)
  isLoading.value = true
  scrollToBottom()

  try {
    const result = await fetchChatResponse(text, debugMode, currentChatId.value, history)
    addMessage('bot', result.answer, result.links, result.debug, result.suggestions)
    await refreshMemory()
  } catch (error) {
    addMessage('bot', '죄송합니다. 서버와 연결할 수 없습니다. 백엔드 서버(uvicorn) 상태를 확인해 주세요.')
  } finally {
    isLoading.value = false
    scrollToBottom()
    saveCurrentChat(messages.value)
  }
}

async function refreshMemory() {
  if (localStorage.getItem('chosun_memory_consent') !== 'granted') {
    memoryItems.value = []
    memoryEnabled.value = false
    memoryLoading.value = false
    return
  }

  if (!currentChatId.value) {
    memoryItems.value = []
    memoryEnabled.value = false
    return
  }
  memoryLoading.value = true
  try {
    const memory = await fetchChatMemory(currentChatId.value)
    memoryItems.value = memory?.recent_memories || []
    memoryEnabled.value = memory?.memory_enabled !== false
  } catch {
    memoryItems.value = []
    memoryEnabled.value = localStorage.getItem('chosun_memory_consent') === 'granted'
  } finally {
    memoryLoading.value = false
  }
}

async function onDeleteMemoryItem(memoryId) {
  if (!window.confirm('이 메모리를 삭제할까요?')) return
  try {
    const memory = await deleteChatMemoryItem(currentChatId.value, memoryId)
    memoryItems.value = memory?.recent_memories || []
    memoryEnabled.value = memory?.memory_enabled !== false
  } catch {
    await refreshMemory()
  }
}

function onEnableMemory() {
  localStorage.setItem('chosun_memory_consent', 'granted')
  // 커스텀 이벤트 발생시켜서 현재 페이지 내의 다른 감시자들에게 알림
  window.dispatchEvent(new CustomEvent('chosun-memory-consent-updated', { detail: 'granted' }))
}

function onDisableMemory() {
  localStorage.setItem('chosun_memory_consent', 'denied')
  // 커스텀 이벤트 발생시켜서 현재 페이지 내의 다른 감시자들에게 알림
  window.dispatchEvent(new CustomEvent('chosun-memory-consent-updated', { detail: 'denied' }))
}

watch(currentChatId, () => {
  refreshMemory()
}, { immediate: true })

function showBotReply(text, links = []) {
  isLoading.value = true
  scrollToBottom()
  setTimeout(() => {
    isLoading.value = false
    addMessage('bot', text, links)
    saveCurrentChat(messages.value)
  }, 1000)
}

async function addMessage(who, text, links = [], debug = null, suggestions = []) {
  messages.value.push({ who, text, time: now(), links, debug, suggestions })
  await nextTick()
  scrollToBottom()
}

async function scrollToBottom() {
  await nextTick()
  if (chatBox.value) {
    chatBox.value.scrollTop = chatBox.value.scrollHeight
  }
}
</script>

<style scoped>
.home-wrapper {
  flex: 1;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

.home {
  flex: 1;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
}

.intro-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
}

.intro-img {
  height: 100px;
  width: 100px;
  object-fit: contain;
  flex-shrink: 0;
}

.intro {
  flex: 1;
  position: relative;
  background: white;
  border-radius: 16px;
  padding: 20px 24px;
  border: 1px solid #c2ddf5;
}

.intro::before {
  content: '';
  position: absolute;
  left: -10px;
  top: 28%;
  transform: translateY(-50%);
  border-width: 10px 10px 10px 0;
  border-style: solid;
  border-color: transparent #c2ddf5 transparent transparent;
}

.intro::after {
  content: '';
  position: absolute;
  left: -8px;
  top: 28%;
  transform: translateY(-50%);
  border-width: 9px 9px 9px 0;
  border-style: solid;
  border-color: transparent white transparent transparent;
}

.intro-sub {
  font-size: 14px;
  color: #666;
}

.menu-carousel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.menu-strip {
  position: relative;
  display: flex;
  align-items: stretch;
  gap: 8px;
}

.menu-viewport {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  padding: 6px 0 4px;
  margin: -6px 0 -4px;
}

.menu-track {
  display: flex;
  width: 100%;
  transition: transform 0.28s ease;
  will-change: transform;
}

.menu-section {
  display: grid;
  gap: 10px;
  flex: 0 0 100%;
  min-width: 0;
}

.menu-arrow {
  width: 32px;
  border: 1px solid #d0e6f8;
  border-radius: 8px;
  background: white;
  color: #6c9fc8;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s, border-color 0.15s, opacity 0.15s;
  z-index: 2;
}

.menu-arrow:hover:not(:disabled) {
  background: #e8f3fb;
  border-color: #add4ef;
  color: #3e7fac;
}

.menu-arrow:focus-visible,
.dot-btn:focus-visible,
.send-btn:focus-visible {
  outline: 2px solid #2e86de;
  outline-offset: 2px;
}

.menu-arrow:disabled {
  opacity: 0.35;
  cursor: default;
}

.menu-dots {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.dot-btn {
  border: 0;
  padding: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d7e8f7;
  cursor: pointer;
  transition: background 0.2s;
}

.dot-btn.active {
  background: #79add8;
}

.chat-section {
  flex: 1;
  min-height: 0;
  background: white;
  border-radius: 16px;
  border: 1px solid #c2ddf5;
  overflow: hidden;
}

.chat-scroll {
  height: 100%;
  padding: 16px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  box-sizing: border-box;
}

.chat-scroll::-webkit-scrollbar {
  width: 4px;
}

.chat-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.chat-scroll::-webkit-scrollbar-thumb {
  background: #ccc;
  border-radius: 4px;
}

.chat-scroll::-webkit-scrollbar-thumb:hover {
  background: #bbb;
}


/* 로딩 말풍선 */
.message-row {
  display: flex;
  margin-bottom: 10px;
}

.message-row.bot {
  justify-content: flex-start;
}

.message-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.loading-bubble {
  background: #f4f6f8;
  border: 1px solid #e0e4ea;
  border-radius: 16px;
  border-bottom-left-radius: 4px;
  padding: 10px 16px;
  display: flex;
  gap: 5px;
  align-items: center;
}

.dot {
  width: 7px;
  height: 7px;
  background-color: #6aabdf;
  border-radius: 50%;
  animation: bounce 1s infinite;
}

.dot:nth-child(2) { animation-delay: 0.15s; }
.dot:nth-child(3) { animation-delay: 0.3s; }

@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30% { transform: translateY(-6px); }
}

.input-section {
  display: flex;
}

.input-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  background: white;
  border: 1px solid #d0e6f8;
  border-radius: 24px;
  padding: 10px 10px 10px 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.input-card:focus-within {
  border-color: #6aabdf;
  box-shadow: 0 0 0 3px rgba(106, 171, 223, 0.18);
}

.chat-input {
  flex: 1;
  border: none;
  outline: 2px solid transparent;
  outline-offset: 2px;
  font-size: 14px;
  font-family: inherit;
  background: transparent;
  color: #333;
}

.chat-input::placeholder {
  color: #aaa;
}

.chat-input:disabled {
  opacity: 0.5;
}

.send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background-color: #65686a;
  color: white;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}

.send-btn:hover {
  background-color: #7aaac8;
}

.send-btn:disabled {
  background-color: #d5e4ef;
  cursor: not-allowed;
}

@media (max-width: 480px) {
  .home {
    padding: 12px;
    gap: 10px;
    overflow-y: auto;
  }

  .intro-img {
    display: none;
  }

  .intro-sub {
    font-size: 12px;
  }

  .chat-section {
    min-height: 320px;
    flex: none;
  }

  .menu-arrow {
    display: none;
  }

  .menu-dots {
    display: none;
  }

  .menu-viewport {
    overflow-x: auto;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }

  .menu-viewport::-webkit-scrollbar {
    display: none;
  }

  .menu-track {
    transform: none !important;
    width: max-content;
    gap: 8px;
  }

  .menu-section {
    display: flex;
    flex-direction: row;
    flex: none;
    width: auto;
    gap: 8px;
  }

}

@media (prefers-reduced-motion: reduce) {
  .menu-track,
  .menu-arrow,
  .dot-btn,
  .send-btn {
    transition-duration: 0.01ms;
  }

  .dot {
    animation: none;
  }
}

</style>
