<template>
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
      <section class="menu-section">
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
    <section class="chat-section" ref="chatBox">
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
    </section>

    <!-- 하단 입력창 -->
    <section class="input-section">
      <input
        v-model="inputText"
        class="chat-input"
        type="text"
        placeholder="질문을 입력하세요."
        @keyup.enter="sendMessage"
        :disabled="isLoading"
      />
      <button class="send-btn" @click="sendMessage" :disabled="isLoading">전송</button>
    </section>
  </main>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import introImg from '../assets/intro.png'
import MenuCard from '../components/MenuCard.vue'
import ChatMessage from '../components/ChatMessage.vue'
import { HeartHandshake, School, BookOpen, FileText, GraduationCap, CalendarDays, Megaphone, Lightbulb, Map, Newspaper, Handshake, Microscope } from 'lucide-vue-next'

const menuItems = [
  {
    icon: Map, label: '캠퍼스맵', iconColor: '#86efac',
    botReply: '캠퍼스맵을 안내해드릴게요!😊\n\n주요 건물과 편의시설 위치를 캠퍼스맵에서 쉽게 확인해 보세요.\n👇자세한 내용은 아래 버튼을 통해 확인하실 수 있어요.',
    links: [
      { label: '캠퍼스맵 바로가기', url: 'https://www3.chosun.ac.kr/campusMap/chosun/view2.do' },
    ]
  },
  {
    icon: CalendarDays, label: '학사일정', iconColor: '#7dd3fc',
    botReply: '조선대학교 학사일정을 안내해드릴게요!😊\n\n학기 중 주요 일정과 중요한 학사 정보를 확인해 보세요.',
    links: [
      { label: '학사일정 바로가기', url: 'https://www3.chosun.ac.kr/chosun/224/subview.do' },
    ]
  },
  {
    icon: School, label: 'THE조아', iconColor: '#f0abfc',
    botReply: 'THE조아에 대해 안내해드릴게요!😊\n\n비교과 신청, 학생상담, 진로·취업정보 등 다양한 학생지원 정보를 한곳에서 확인해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: 'THE조아 바로가기', url: 'https://thechoa.chosun.ac.kr/clientMain/a/t/main.do' },
    ]
  },
  {
    icon: BookOpen, label: '도서관', iconColor: '#6ee7b7',
    botReply: '도서관 안내해드릴게요!😊\n\n도서관 홈페이지에서는 자료 검색, 대출·반납, 희망도서 신청, 이용안내 등 다양한 정보를 확인하실 수 있어요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '자료검색', url: 'https://library.chosun.ac.kr/' },
      { label: '대출/반납/예약/연장 안내', url: 'https://library.chosun.ac.kr/local/html/loanGuide' },
      { label: '희망도서신청', url: 'https://library.chosun.ac.kr/local/html/purchaserequestGuide' },
      { label: '이용안내', url: 'https://library.chosun.ac.kr/local/html/openingHourGuide' },
    ]
  },
  {
    icon: GraduationCap, label: '장학', iconColor: '#fdba74',
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
    icon: FileText, label: '증명서/학사양식', iconColor: '#c4b5fd',
    botReply: '증명서 발급 안내해드릴게요!😊\n\n조선대학교 인터넷 증명서 발급센터에서는 PC와 모바일 브라우저를 통해\n재학증명서, 수료증명서, 성적증명서 등 각종 증명서를 온라인으로 발급받을 수 있어요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '증명서 발급 바로가기', url: 'https://chosun.icerti.com/icerti/index_internet.jsp?t=1607' },
      { label: '증명서 종류', url: 'https://chosun.icerti.com/icerti/jsp/main/user/guide/certificate_userguide_01.jsp' },
      { label: '학사양식 발급 바로가기', url: 'https://www3.chosun.ac.kr/chosun/227/subview.do' },
    ]
  },
  {
    icon: Megaphone, label: '외부공고', iconColor: '#fca5a5',
    botReply: '외부기관 공고를 안내해드릴게요!😊\n\n 다양한 외부기관의 모집, 지원사업, 프로그램, 공모전 소식을 한곳에서 확인해 보세요.',
    links: [
      { label: '외부공고 바로가기', url: 'https://www3.chosun.ac.kr/chosun/269/subview.do' },
    ]
  },
  {
    icon: Handshake, label: '산학협력단', iconColor: '#a5b4fc',
    botReply: '조선대학교 산학협력단을 안내해드릴게요!😊\n\n산학협력단, 중소기업산학협력센터, 통합발달지원센터, 공동장비운영센터, CSU창작마을센터에서 관련 정보를 확인해 보세요.\n👇자세한 내용은 아래 버튼을 통해 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '산학협력단', url: 'https://iacf.chosun.ac.kr/iacf/index.do' },
      { label: '중소기업산학협력센터', url: 'https://sme.chosun.ac.kr/csu_sme/index.do' },
      { label: '통합발달지원센터', url: 'https://ccds.chosun.ac.kr/main/' },
      { label: '공동장비운영센터', url: ' https://iacf.chosun.ac.kr/iacf/researchDB/equipment.do' },
      { label: 'CSU창작마을센터', url: ' https://csumaker.chosun.ac.kr/web/index.do' },
    ]
  },
  {
    icon: Microscope, label: '대학원', iconColor: '#99f6e4',
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
    icon: Lightbulb, label: '학사지원', iconColor: '#fed7aa',
    botReply: '학사지원을 안내해드릴게요!😊\n\n조선대학교에는 원스톱학생상담센터, 교수학습지원센터, 인권성평등센터, 장애학생지원센터가 마련되어 있어요.\n👇자세한 내용은 아래 버튼을 눌러 해당 페이지에서 확인해 보세요.',
    links: [
      { label: '원스톱학습상담센터', url: 'https://counsel.chosun.ac.kr/counsel/index.do' },
      { label: '교수학습지원센터', url: 'https://eclass.chosun.ac.kr/ctl/main/main_form.acl' },
      { label: '인권성평등센터', url: 'https://www4.chosun.ac.kr/sites/humanrights/index.do' },
      { label: '장애학생지원센터', url: 'https://disable.chosun.ac.kr/disable/index.do' },
    ]
  },
  {
    icon: Newspaper, label: '조선대소식', iconColor: '#fde68a',
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
    icon: HeartHandshake, label: '소셜미디어', iconColor: '#f9a8d4',
    botReply: '조선대학교 소셜미디어를 안내해드릴게요!😊\n\n인스타그램, 유튜브, 블로그, 페이스북에서 최신 소식과 다양한 정보를 확인해 보세요.',
    links: [
      { label: '인스타그램', url: 'https://www.instagram.com/chosununiversity/' },
      { label: '유튜브', url: 'https://www.youtube.com/channel/UCr0vMKw8iI5B1CYvX1ZsamQ?view_as=subscriber' },
      { label: '블로그', url: 'https://blog.naver.com/chosununi' },
      { label: '페이스북', url: 'https://www.facebook.com/chosununi/' },
    ]
  },
]

const menuPage = ref(0)
const pageSize = 6
const totalPages = computed(() => Math.ceil(menuItems.length / pageSize))
const currentPageItems = computed(() => menuItems.slice(menuPage.value * pageSize, (menuPage.value + 1) * pageSize))

const messages = ref([
  { who: 'bot', text: '안녕하세요! 조선대학교에 대해 궁금한 점을 물어보세요.', time: now() }
])
const inputText = ref('')
const chatBox = ref(null)
const isLoading = ref(false)

function now() {
  const d = new Date()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

function onMenuClick(label) {
  const item = menuItems.find(m => m.label === label)
  addMessage('user', label + ' 알려주세요')
  showBotReply(item.botReply, item.links)
}

function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return
  addMessage('user', text)
  inputText.value = ''
  showBotReply('확인했습니다. 관련 내용을 찾고 있어요. (추후 AI 연결 예정)')
}

function showBotReply(text, links = []) {
  isLoading.value = true
  scrollToBottom()
  setTimeout(() => {
    isLoading.value = false
    addMessage('bot', text, links)
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

.intro-text {
  font-size: 17px;
  margin-bottom: 6px;
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
  grid-template-columns: repeat(6, 1fr);
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
  background: #d0e6f8;
  cursor: pointer;
  transition: background 0.2s;
}

.dot-btn.active {
  background: #6aabdf;
}

.chat-section {
  flex: 1;
  background: white;
  border-radius: 16px;
  border: 1px solid #c2ddf5;
  padding: 16px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
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
  gap: 8px;
}

.chat-input {
  flex: 1;
  padding: 12px 16px;
  border: 1.5px solid #d0e6f8;
  border-radius: 24px;
  font-size: 14px;
  font-family: inherit;
  outline: none;
}

.chat-input:focus {
  border-color: #6aabdf;
}

.chat-input:disabled {
  background: #f5f5f5;
}

.send-btn {
  padding: 12px 20px;
  background-color: #6aabdf;
  color: white;
  border: none;
  border-radius: 24px;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  font-weight: 600;
}

.send-btn:hover {
  background-color: #5a9bcf;
}

.send-btn:disabled {
  background-color: #b0d4ef;
  cursor: not-allowed;
}
</style>
