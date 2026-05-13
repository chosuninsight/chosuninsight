<template>
  <transition name="slide-down">
    <div v-if="isVisible" class="consent-banner">
      <div class="consent-content">
        <div class="icon-wrap">
          <BrainCircuit :size="24" class="brain-icon" />
        </div>
        <div class="text-wrap">
          <h4 class="title">개인화 메모리 기능을 사용하시겠습니까?</h4>
          <p class="description">
            학과, 학번 등 대화 중 알려주신 정보를 기억하여 더 정확한 학사 안내를 도와드립니다.
            이 정보는 언제든지 삭제하거나 기능을 끌 수 있습니다.
          </p>
        </div>
        <div class="action-wrap">
          <button class="btn deny" @click="handleResponse(false)">나중에</button>
          <button class="btn allow" @click="handleResponse(true)">허용하기</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { BrainCircuit } from 'lucide-vue-next'

const isVisible = ref(false)
const emit = defineEmits(['consent-updated'])

onMounted(() => {
  const consent = localStorage.getItem('chosun_memory_consent')
  if (!consent) {
    // 1초 뒤에 스르륵 나타나게 설정
    setTimeout(() => {
      isVisible.value = true
    }, 1000)
  }
})

const handleResponse = (allowed) => {
  const status = allowed ? 'granted' : 'denied'
  localStorage.setItem('chosun_memory_consent', status)
  isVisible.value = false
  emit('consent-updated', status)
  
  // 다른 컴포넌트(HomeView 등)가 감지할 수 있도록 커스텀 이벤트 발송
  window.dispatchEvent(new CustomEvent('chosun-memory-consent-updated', { detail: status }))
}
</script>

<style scoped>
.consent-banner {
  position: fixed;
  top: 70px; /* 헤더 아래 위치 */
  left: 50%;
  transform: translateX(-50%);
  width: calc(100% - 40px);
  max-width: 800px;
  background: white;
  border: 1px solid #d0e6f8;
  border-radius: 16px;
  box-shadow: 0 10px 25px rgba(0, 75, 150, 0.1);
  z-index: 1000;
  overflow: hidden;
}

.consent-content {
  display: flex;
  align-items: center;
  padding: 16px 24px;
  gap: 20px;
}

.icon-wrap {
  width: 48px;
  height: 48px;
  background: #f0f7ff;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.brain-icon {
  color: #3b82f6;
}

.text-wrap {
  flex: 1;
}

.title {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
  color: #1e3a8a;
}

.description {
  margin: 0;
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}

.action-wrap {
  display: flex;
  gap: 10px;
}

.btn {
  padding: 10px 18px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  white-space: nowrap;
}

.btn.allow {
  background: #3b82f6;
  color: white;
}

.btn.allow:hover {
  background: #2563eb;
}

.btn.deny {
  background: #f1f5f9;
  color: #64748b;
}

.btn.deny:hover {
  background: #e2e8f0;
}

/* 애니메이션 */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.4s ease-out;
}

.slide-down-enter-from,
.slide-down-leave-to {
  transform: translate(-50%, -100%);
  opacity: 0;
}

@media (max-width: 640px) {
  .consent-content {
    flex-direction: column;
    align-items: flex-start;
    padding: 20px;
    gap: 16px;
  }
  
  .action-wrap {
    width: 100%;
  }
  
  .btn {
    flex: 1;
  }
}
</style>
