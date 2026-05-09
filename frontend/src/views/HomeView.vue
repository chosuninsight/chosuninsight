<template>
  <div class="home-wrapper">
    <!-- 왼쪽: 히스토리 사이드바 -->
    <ChatSidebar
      :histories="histories"
      :currentChatId="currentChatId"
      @new-chat="onNewChat"
      @load-chat="onLoadChat"
      @delete-chat="onDeleteChat"
      @clear-all="onClearAll"
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
        <section class="menu-section" :style="{ gridTemplateColumns: `repeat(${currentPageItems.length}, 1fr)` }">
          <MenuCard
            v-for="item in currentPageItems"
            :key="item.label"
            :icon="item.icon"
            :label="item.label"
            :iconColor="item.iconColor"
            @click="onMenuClick"
          />
        </section>
        <div class="menu-dots">
          <span
            v-for="i in totalPages"
            :key="i"
            class="dot-btn"
            :class="{ active: menuPage === i - 1 }"
            @click="menuPage = i - 1"
          />
        </div>
      </div>

      <!-- 채팅 메시지 영역 -->
      <section class="chat-section">
        <div class="chat-scroll" ref="chatBox">
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
          <div v-if="isLoading" class="message-row bot">
            <div class="message-wrap">
              <div class="bubble loading-bubble">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
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
            placeholder="질문을 입력하세요."
            @keyup.enter="sendMessage"
            :disabled="isLoading"
          />
          <button class="send-btn" @click="sendMessage" :disabled="isLoading">
            <ArrowUp :size="18" />
          </button>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import introImg from '../assets/intro.png'
import MenuCard from '../components/MenuCard.vue'
import ChatMessage from '../components/ChatMessage.vue'
import ChatSidebar from '../components/ChatSidebar.vue'
import { useChatHistory } from '../composables/useChatHistory.js'
import { ArrowUp } from 'lucide-vue-next'
import { fetchChatResponse } from '../services/api.js'
import { menuItems } from '../data/menuItems.js'

const { histories, currentChatId, createNewChat, saveCurrentChat, loadChat, loadLastChat, deleteChat, clearAll } = useChatHistory()

const menuPage = ref(0)
const pageSize = 6
const totalPages = computed(() => {
  const pages = Math.ceil(menuItems.length / pageSize)
  return menuItems.length % pageSize === 1 ? pages - 1 : pages
})
const currentPageItems = computed(() => {
  const start = menuPage.value * pageSize
  if (menuPage.value === totalPages.value - 1) return menuItems.slice(start)
  return menuItems.slice(start, start + pageSize)
})

// 페이지 로드 시 마지막 대화 복원, 없으면 새 대화 시작
const _restored = loadLastChat()
const messages = ref(_restored ?? createNewChat())

const inputText = ref('')
const chatBox = ref(null)
const isLoading = ref(false)
const debugMode = import.meta.env.DEV || localStorage.getItem('chosun_debug') === 'true'

function now() {
  const d = new Date()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

// 사이드바 이벤트 핸들러
function onNewChat() {
  messages.value = createNewChat()
}

function onLoadChat(id) {
  const loaded = loadChat(id)
  if (loaded) messages.value = loaded
}

function onDeleteChat(id) {
  const wasCurrentChat = deleteChat(id)
  if (wasCurrentChat) messages.value = createNewChat()
}

function onClearAll() {
  clearAll()
  messages.value = createNewChat()
}

function onMenuClick(label) {
  const item = menuItems.find(m => m.label === label)
  addMessage('user', label + ' 알려주세요')
  showBotReply(item.botReply, item.links)
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
  } catch (error) {
    addMessage('bot', '죄송합니다. 서버와 연결할 수 없습니다. 백엔드 서버(uvicorn) 상태를 확인해 주세요.')
  } finally {
    isLoading.value = false
    scrollToBottom()
    saveCurrentChat(messages.value)
  }
}

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

.menu-section {
  display: grid;
  gap: 10px;
}

.menu-dots {
  display: flex;
  justify-content: center;
  gap: 8px;
}

.dot-btn {
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

.chat-input {
  flex: 1;
  border: none;
  outline: none;
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
}

</style>
