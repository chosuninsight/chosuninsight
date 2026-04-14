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
import { HeartHandshake, School, BookOpen, FileText, GraduationCap, CalendarDays, Megaphone, Lightbulb, Map, Newspaper, Handshake, Microscope, Monitor, ClipboardList, Users, Palette, Radio, Database, CalendarCheck, ArrowUp } from 'lucide-vue-next'
import { fetchChatResponse } from '../services/api.js'

const { histories, currentChatId, createNewChat, saveCurrentChat, loadChat, loadLastChat, deleteChat, clearAll } = useChatHistory()

const menuItems = [
  // --- 1페이지 ---
  {
    icon: CalendarDays, label: '학사일정', iconColor: '#7CC4EE',
    botReply: '조선대학교 학사일정을 안내해드릴게요!😊\n\n학기 중 주요 일정과 중요한 학사 정보를 확인해 보세요.',
    links: [
      { label: '학사일정 바로가기', url: 'https://www3.chosun.ac.kr/chosun/224/subview.do' },
    ]
  },
  {
    icon: School, label: 'THE조아', iconColor: '#D0A9EE',
    botReply: 'THE조아에 대해 안내해드릴게요!😊\n\n비교과 신청, 학생상담, 진로·취업정보 등 다양한 학생지원 정보를 한곳에서 확인해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: 'THE조아 바로가기', url: 'https://thechoa.chosun.ac.kr/clientMain/a/t/main.do' },
    ]
  },
  {
    icon: BookOpen, label: '도서관', iconColor: '#92DFC7',
    botReply: '도서관 안내해드릴게요!😊\n\n도서관 홈페이지에서는 자료 검색, 대출·반납, 희망도서 신청, 이용안내 등 다양한 정보를 확인하실 수 있어요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '자료검색', url: 'https://library.chosun.ac.kr/' },
      { label: '대출/반납/예약/연장 안내', url: 'https://library.chosun.ac.kr/local/html/loanGuide' },
      { label: '희망도서신청', url: 'https://library.chosun.ac.kr/local/html/purchaserequestGuide' },
      { label: '이용안내', url: 'https://library.chosun.ac.kr/local/html/openingHourGuide' },
    ]
  },
  {
    icon: GraduationCap, label: '장학', iconColor: '#F3BE78',
    botReply: '장학 안내를 도와드릴게요!😊\n\n조선대학교 장학안내 홈페이지에서는 교내장학금, 국가장학금, 학자금대출, 국가근로장학사업 등 다양한 장학 정보를 확인하실 수 있어요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '장학 홈페이지', url: 'https://scho.chosun.ac.kr/scho/index.do' },
      { label: '공지사항', url: 'https://www3.chosun.ac.kr/scho/2138/subview.do?enc=Zm5jdDF8QEB8JTJGYmJzJTJGc2NobyUyRjMzMiUyRmFydGNsTGlzdC5kbyUzRmJic0NsU2VxJTNEJTI2YmJzT3BlbldyZFNlcSUzRCUyNmlzVmlld01pbmUlM0RmYWxzZSUyNnNyY2hDb2x1bW4lM0RzaiUyNnNyY2hXcmQlM0QlMjY%3D' },
      { label: '교내장학금', url: 'https://www3.chosun.ac.kr/scho/2776/subview.do' },
      { label: '국가장학금', url: 'https://www3.chosun.ac.kr/scho/2132/subview.do' },
      { label: '학자금대출', url: 'https://www3.chosun.ac.kr/scho/2134/subview.do' },
      { label: '국가근로장학사업', url: 'https://www3.chosun.ac.kr/scho/2136/subview.do' },
    ]
  },
  {
    icon: Monitor, label: '사이버캠퍼스', iconColor: '#8BC2F1',
    botReply: '조선대학교 사이버캠퍼스를 안내해드릴게요!😊\n\n온라인 강의, 학습 자료, 과제 제출 등 다양한 학습 서비스를 이용해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '사이버캠퍼스 바로가기', url: 'https://clc.chosun.ac.kr/ilos/main/main_form.acl' },
    ]
  },
  {
    icon: Database, label: '종합정보시스템', iconColor: '#A7B7EE',
    botReply: '조선대학교 종합정보시스템을 안내해드릴게요!😊\n\n학생 포털을 통해 학사, 행정 등 다양한 정보를 확인하실 수 있어요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '종합정보시스템 바로가기', url: 'https://sso.chosun.ac.kr/svc/tk/Auth.eps?ac=Y&ifa=N&id=PORTAL&' },
    ]
  },
  // --- 2페이지 ---
  {
    icon: CalendarCheck, label: '수강신청', iconColor: '#89C8F2',
    botReply: '조선대학교 차세대 수강신청시스템을 안내해드릴게요!😊\n\n수강신청, 수강변경 등 수강 관련 서비스를 이용해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '수강신청시스템 바로가기', url: 'https://s.chosun.ac.kr/' },
    ]
  },
  {
    icon: FileText, label: '증명서/학사양식', iconColor: '#F3C27D',
    botReply: '증명서 발급 안내해드릴게요!😊\n\n조선대학교 인터넷 증명서 발급센터에서는 PC와 모바일 브라우저를 통해\n재학증명서, 수료증명서, 성적증명서 등 각종 증명서를 온라인으로 발급받을 수 있어요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '증명서 발급 바로가기', url: 'https://chosun.icerti.com/icerti/index_internet.jsp?t=1607' },
      { label: '증명서 종류', url: 'https://chosun.icerti.com/icerti/jsp/main/user/guide/certificate_userguide_01.jsp' },
      { label: '학사양식 발급 바로가기', url: 'https://www3.chosun.ac.kr/chosun/227/subview.do' },
    ]
  },
  {
    icon: Lightbulb, label: '학사지원', iconColor: '#7FD7C4',
    botReply: '학사지원을 안내해드릴게요!😊\n\n 원스톱학생상담센터, 교수학습지원센터, 인권성평등센터, 장애학생지원센터가 마련되어 있어요.\n👇자세한 내용은 아래 버튼을 눌러 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '원스톱학습상담센터', url: 'https://counsel.chosun.ac.kr/counsel/index.do' },
      { label: '교수학습지원센터', url: 'https://eclass.chosun.ac.kr/ctl/main/main_form.acl' },
      { label: '인권성평등센터', url: 'https://www4.chosun.ac.kr/sites/humanrights/index.do' },
      { label: '장애학생지원센터', url: 'https://disable.chosun.ac.kr/disable/index.do' },
    ]
  },
  {
    icon: ClipboardList, label: '교육지원', iconColor: '#A7D99B',
    botReply: '조선대학교 교육지원 서비스를 안내해드릴게요!😊\n\n글쓰기센터, 글로벌언어교육지원팀, 평생교육원, 실험실안전교육 등 다양한 교육 지원 서비스를 이용해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '글쓰기센터', url: 'https://cu.iwcc.kr/writing-chosun/standard/educenter/info.do' },
      { label: '글로벌언어교육지원팀', url: 'https://lei.chosun.ac.kr/lei/index.do' },
      { label: '평생교육원', url: 'https://lifelong.chosun.ac.kr/lifelong/index.do' },
      { label: '실험실안전교육', url: 'https://safetylabs.chosun.ac.kr/' },
    ]
  },
  {
    icon: Handshake, label: '산학협력단', iconColor: '#8FBEEA',
    botReply: '조선대학교 산학협력단을 안내해드릴게요!😊\n\n산학협력단, 중소기업산학협력센터, 통합발달지원센터, 공동장비운영센터, CSU창작마을센터에서 관련 정보를 확인해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '산학협력단', url: 'https://iacf.chosun.ac.kr/iacf/index.do' },
      { label: '중소기업산학협력센터', url: 'https://sme.chosun.ac.kr/csu_sme/index.do' },
      { label: '통합발달지원센터', url: 'https://ccds.chosun.ac.kr/main/' },
      { label: '공동장비운영센터', url: 'https://iacf.chosun.ac.kr/iacf/researchDB/equipment.do' },
      { label: 'CSU창작마을센터', url: 'https://csumaker.chosun.ac.kr/web/index.do' },
    ]
  },
  {
    icon: Megaphone, label: '외부공고', iconColor: '#E9A39A',
    botReply: '외부기관 공고를 안내해드릴게요!😊\n\n 다양한 외부기관의 모집, 지원사업, 프로그램, 공모전 소식을 한곳에서 확인해 보세요.',
    links: [
      { label: '외부공고 바로가기', url: 'https://www3.chosun.ac.kr/chosun/269/subview.do' },
    ]
  },
  // --- 3페이지 ---
  {
    icon: Microscope, label: '대학원', iconColor: '#D2B3EF',
    botReply: '조선대학교 대학원을 안내해드릴게요!😊\n\n각 대학원 홈페이지에서 입학 정보, 학과·전공, 교육과정, 공지사항 등을 확인해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '대학원 홈페이지', url: 'https://grad.chosun.ac.kr/' },
      { label: '미래인재융합대학원', url: 'https://gsf.chosun.ac.kr/' },
      { label: '교육대학원', url: 'https://gedu.chosun.ac.kr/' },
      { label: '경영대학원', url: 'https://gsba.chosun.ac.kr/' },
      { label: '산업기술창업대학원', url: 'https://gi.chosun.ac.kr/' },
      { label: '정책대학원', url: 'https://gsp.chosun.ac.kr/' },
      { label: '디자인대학원', url: 'https://gsd.chosun.ac.kr/' },
      { label: '보건대학원', url: 'https://ehs14.chosun.ac.kr/' },
      { label: '임상약학대학원', url: 'http://clinicalpharm.chosun.ac.kr/' },
    ]
  },
  {
    icon: Map, label: '캠퍼스맵', iconColor: '#8EDBCF',
    botReply: '캠퍼스맵을 안내해드릴게요!😊\n\n주요 건물과 편의시설 위치를 캠퍼스맵에서 쉽게 확인해 보세요.\n👇자세한 내용은 아래 버튼을 통해 확인하실 수 있어요.',
    links: [
      { label: '캠퍼스맵 바로가기', url: 'https://www3.chosun.ac.kr/campusMap/chosun/view2.do' },
    ]
  },
  {
    icon: Palette, label: '문화생활', iconColor: '#EEB29C',
    botReply: '조선대학교 문화생활을 안내해드릴게요!😊\n\n박물관, 장황남 정보통신박물관, 미술관 등 다양한 문화 시설을 이용해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '조선대학교 박물관', url: 'https://museum.chosun.ac.kr/museum/index.do' },
      { label: '장황남 정보통신박물관', url: 'http://changicmuseum.chosun.ac.kr/' },
      { label: '미술관·김보현&실비아올드 전시관', url: 'https://artmuseum.chosun.ac.kr/artmuseum/index.do' },
    ]
  },
  {
    icon: Users, label: '커뮤니티', iconColor: '#D8B5F2',
    botReply: '조선대학교 커뮤니티를 안내해드릴게요!😊\n\n스터디모임, 알바정보, 주거정보, 분실물센터, 자유마당, 에브리타임 등 다양한 커뮤니티 서비스를 이용해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '스터디모임', url: 'https://www3.chosun.ac.kr/chosun/649/subview.do' },
      { label: '알바정보', url: 'https://www3.chosun.ac.kr/chosun/272/subview.do' },
      { label: '주거정보', url: 'https://www3.chosun.ac.kr/chosun/270/subview.do' },
      { label: '분실물센터', url: 'https://www3.chosun.ac.kr/chosun/273/subview.do' },
      { label: '자유마당', url: 'https://www3.chosun.ac.kr/chosun/264/subview.do' },
      { label: '조선대학교 에브리타임', url: 'https://chosun.everytime.kr/' },
    ]
  },
  {
    icon: HeartHandshake, label: '소셜미디어', iconColor: '#E8B7C6',
    botReply: '조선대학교 소셜미디어를 안내해드릴게요!😊\n\n인스타그램, 유튜브, 블로그, 페이스북에서 최신 소식과 다양한 정보를 확인해 보세요.',
    links: [
      { label: '인스타그램', url: 'https://www.instagram.com/chosununiversity/' },
      { label: '유튜브', url: 'https://www.youtube.com/channel/UCr0vMKw8iI5B1CYvX1ZsamQ?view_as=subscriber' },
      { label: '블로그', url: 'https://blog.naver.com/chosununi' },
      { label: '페이스북', url: 'https://www.facebook.com/chosununi/' },
    ]
  },
  {
    icon: Newspaper, label: '조선대소식', iconColor: '#86C9EE',
    botReply: '조선대학교 관련 소식을 안내해드릴게요!😊\n\n언론 속 조선대, 홍보동영상, 전경사진, 포토뉴스, 조선대 뉴스와 규정집 등 다양한 정보를 확인해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '언론속조선대', url: 'https://www3.chosun.ac.kr/chosun/169/subview.do' },
      { label: '홍보동영상', url: 'https://www3.chosun.ac.kr/chosun/761/subview.do' },
      { label: '전경사진', url: 'https://www3.chosun.ac.kr/chosun/173/subview.do' },
      { label: '포토뉴스', url: 'https://www3.chosun.ac.kr/chosun/591/subview.do' },
      { label: '조선대뉴스', url: 'https://www3.chosun.ac.kr/chosun/2607/subview.do' },
      { label: '규정집', url: 'https://www3.chosun.ac.kr/chosun/155/subview.do' },
    ]
  },
  {
    icon: Radio, label: '대학언론사', iconColor: '#B4BDF1',
    botReply: '조선대학교 대학언론사를 안내해드릴게요!😊\n\n교육방송국, 조대신문, 영자신문, 민주조선 등 다양한 학교 언론 매체를 확인해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '교육방송국', url: 'https://www.chosun.ac.kr/user/indexMain.do?siteId=cueb' },
      { label: '조대신문', url: 'https://www3.chosun.ac.kr/chnews/index.do' },
      { label: '영자신문', url: 'https://www3.chosun.ac.kr/chosunworld/index.do?enc=Zm5jdDF8QEB8JTJGbWFnYXppbmUlMkZjaG9zdW53b3JsZCUyRjE2OSUyRjMzMTYlMkZ2aWV3LmRvJTNGZm5jdE5vJTNEMTY5JTI2ZmluZENsU2VxJTNEJTI2ZmluZFNldHVwU2VxJTNEJTI2ZmluZEZuY3RObyUzRCUyNg%3D%3D' },
      { label: '민주조선', url: 'https://www3.chosun.ac.kr/sites/chosun/files/2025_%EB%AF%BC%EC%A3%BC%EC%A1%B0%EC%84%A0_%EA%B5%90%EC%A7%80%ED%99%88%ED%8E%98%EC%9D%B4%EC%A7%80%EC%9A%A9.pdf' },
    ]
  },
]

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

  addMessage('user', text)
  inputText.value = ''
  isLoading.value = true
  scrollToBottom()

  try {
    const result = await fetchChatResponse(text)
    addMessage('bot', result.answer, result.links)
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

async function addMessage(who, text, links = []) {
  messages.value.push({ who, text, time: now(), links })
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
</style>
