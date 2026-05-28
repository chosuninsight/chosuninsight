<template>
  <aside class="sidebar" :class="{ expanded: isExpanded }">
    <!-- 상단: 토글 + 새 채팅 -->
    <div class="sidebar-top">
      <button
        class="icon-btn toggle-btn"
        type="button"
        ref="toggleBtnRef"
        :aria-label="isExpanded ? '사이드바 닫기' : '사이드바 열기'"
        :aria-expanded="isExpanded"
        @click="isExpanded = !isExpanded"
        @mouseenter="onToggleEnter"
        @mouseleave="tooltipVisible = false"
      >
        <PanelLeftClose v-if="isExpanded" :size="18" aria-hidden="true" />
        <PanelLeftOpen v-else :size="18" aria-hidden="true" />
      </button>

      <Teleport to="body">
        <span
          v-if="tooltipVisible"
          class="sidebar-tooltip"
          :style="{ top: tooltipPos.top + 'px', left: tooltipPos.left + 'px' }"
        >
          {{ isExpanded ? '사이드바 닫기' : '사이드바 열기' }}
        </span>
      </Teleport>
      <button
        class="icon-btn"
        type="button"
        ref="newChatBtnRef"
        aria-label="새 채팅"
        @click="$emit('new-chat')"
        @mouseenter="onNewChatEnter"
        @mouseleave="newChatTooltipVisible = false"
      >
        <SquarePen :size="18" aria-hidden="true" />
        <span v-if="isExpanded" class="btn-label">새 채팅</span>
      </button>

      <Teleport to="body">
        <span
          v-if="newChatTooltipVisible && !isExpanded"
          class="sidebar-tooltip"
          :style="{ top: newChatTooltipPos.top + 'px', left: newChatTooltipPos.left + 'px' }"
        >
          새 채팅
        </span>
      </Teleport>
    </div>

    <!-- 히스토리 목록 -->
    <p v-if="isExpanded && histories.length > 0" class="history-label">최근 항목</p>

    <ul v-if="isExpanded" class="history-list">
      <li
        v-for="item in histories"
        :key="item.id"
        class="history-item"
        :class="{ active: item.id === currentChatId }"
      >
        <button
          v-if="isExpanded"
          type="button"
          class="history-load-btn"
          :aria-current="item.id === currentChatId ? 'true' : undefined"
          @click="$emit('load-chat', item.id)"
        >
          <span class="history-title">{{ item.title }}</span>
        </button>
        <button
          v-if="isExpanded"
          type="button"
          class="delete-btn"
          :aria-label="`${item.title} 삭제`"
          @click.stop="$emit('delete-chat', item.id)"
        >
          <Trash2 :size="14" aria-hidden="true" />
        </button>
      </li>
    </ul>

    <section v-if="isExpanded" class="memory-panel">
      <button class="memory-toggle" type="button" :aria-expanded="memoryOpen" @click.stop="memoryOpen = !memoryOpen">
        <span class="memory-title">
          <Brain :size="14" aria-hidden="true" />
          메모리
        </span>
        <ChevronDown v-if="memoryOpen" :size="14" aria-hidden="true" />
        <ChevronRight v-else :size="14" aria-hidden="true" />
      </button>
      <div v-if="memoryOpen" class="memory-body">
        <div class="memory-actions">
          <button v-if="memoryEnabled" class="small-icon-btn disable-btn" type="button" @click.stop="$emit('disable-memory')" title="기능 끄기" aria-label="메모리 기능 끄기">
            <Power :size="13" aria-hidden="true" />
          </button>
          <button class="small-icon-btn" type="button" @click.stop="$emit('refresh-memory')" title="메모리 새로고침" aria-label="메모리 새로고침">
            <RefreshCw :size="13" aria-hidden="true" />
          </button>
        </div>
        <p v-if="memoryLoading" class="memory-empty">불러오는 중</p>
        <div v-else-if="!memoryEnabled" class="memory-disabled-wrap">
          <p class="memory-empty">비활성화됨</p>
          <button class="memory-enable-btn" type="button" @click.stop="$emit('enable-memory')">
            기능 켜기
          </button>
        </div>
        <p v-else-if="memoryItems.length === 0" class="memory-empty">저장된 메모리 없음</p>
        <ul v-else class="memory-list">
          <li v-for="item in memoryItems" :key="item.id" class="memory-item">
            <span class="memory-text">{{ item.text }}</span>
            <button class="memory-delete" type="button" @click.stop="$emit('delete-memory-item', item.id)" title="메모리 삭제" aria-label="메모리 삭제">
              <X :size="13" aria-hidden="true" />
            </button>
          </li>
        </ul>
      </div>
    </section>

    <!-- 하단: 전체 삭제 -->
    <div v-if="histories.length > 0 && isExpanded" class="sidebar-bottom">
      <button class="icon-btn clear-btn" type="button" @click="$emit('clear-all')">
        <Trash2 :size="15" aria-hidden="true" />
        <span v-if="isExpanded" class="btn-label">대화 목록 비우기</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref } from 'vue'
import { PanelLeftOpen, PanelLeftClose, SquarePen, Trash2, Brain, RefreshCw, X, ChevronDown, ChevronRight } from 'lucide-vue-next'

const toggleBtnRef = ref(null)
const tooltipVisible = ref(false)
const tooltipPos = ref({ top: 0, left: 0 })

function onToggleEnter() {
  if (toggleBtnRef.value) {
    const rect = toggleBtnRef.value.getBoundingClientRect()
    tooltipPos.value = {
      top: rect.top + rect.height / 2,
      left: rect.right + 10,
    }
  }
  tooltipVisible.value = true
}

const newChatBtnRef = ref(null)
const newChatTooltipVisible = ref(false)
const newChatTooltipPos = ref({ top: 0, left: 0 })

function onNewChatEnter() {
  if (newChatBtnRef.value) {
    const rect = newChatBtnRef.value.getBoundingClientRect()
    newChatTooltipPos.value = {
      top: rect.top + rect.height / 2,
      left: rect.right + 10,
    }
  }
  newChatTooltipVisible.value = true
}


defineProps({
  histories: { type: Array, required: true },
  currentChatId: { type: Number, default: null },
  memoryItems: { type: Array, default: () => [] },
  memoryEnabled: { type: Boolean, default: true },
  memoryLoading: { type: Boolean, default: false },
})

defineEmits(['new-chat', 'load-chat', 'delete-chat', 'clear-all', 'refresh-memory', 'delete-memory-item', 'enable-memory', 'disable-memory'])

const isExpanded = ref(false)
const memoryOpen = ref(false)
</script>

<style scoped>
.sidebar {
  width: 52px;
  transition: width 0.25s ease;
  background: #f8fbff;
  border-right: 1.0px solid #d2e9fc;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar.expanded {
  width: 220px;
}

.sidebar-top {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 8px;
}

.icon-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px;
  background: none;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  color: #666;
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  flex-shrink: 0;
}

.icon-btn:hover {
  background: #e8f3fb;
  color: #3d3d3d;
}

.toggle-btn {
  color: #888;
}

.btn-label {
  font-size: 13px;
}

.history-label {
  font-size: 11px;
  color: #aaa;
  padding: 0 16px;
  margin-top: 17px;
  white-space: nowrap;
}

.history-list {
  list-style: none;
  padding: 8px;
  margin: 0;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: 8px;
  white-space: nowrap;
  min-width: 0;
}

.history-item:hover {
  background: #e8f3fb;
}

.history-item.active {
  background: #e4f1fb;
}

.history-load-btn {
  flex: 1;
  min-width: 0;
  padding: 8px;
  border: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
}

.history-title {
  flex: 1;
  font-size: 13px;
  color: #3d3d3d;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.delete-btn {
  display: flex;
  align-items: center;
  background: none;
  border: none;
  color: #bbb;
  cursor: pointer;
  padding: 2px 3px;
  border-radius: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.icon-btn:focus-visible,
.delete-btn:focus-visible,
.history-load-btn:focus-visible,
.memory-toggle:focus-visible,
.small-icon-btn:focus-visible,
.memory-enable-btn:focus-visible,
.memory-delete:focus-visible {
  outline: 2px solid #2e86de;
  outline-offset: 2px;
}

.history-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  color: #e05a5a;
  background: #fde8e8;
}

.delete-btn:focus-visible {
  opacity: 1;
}

.sidebar-bottom {
  padding: 20px 6px 25px;
  border-top: 1px solid #e3eef7;
}

.clear-btn {
  color: #a6a6a6;
}

.clear-btn:hover {
  background: #fde8e8;
  color: #db8484;
}

.memory-panel {
  border-top: 1px solid #e3eef7;
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.memory-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  border: none;
  background: transparent;
  color: #52616f;
  border-radius: 7px;
  cursor: pointer;
  padding: 6px 4px;
}

.memory-toggle:hover {
  background: #e8f3fb;
}

.memory-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.memory-actions {
  display: flex;
  justify-content: flex-end;
  padding: 0 4px;
}

.memory-title {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
  color: #52616f;
}

.small-icon-btn,
.memory-delete {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #8a9aaa;
  border-radius: 5px;
  cursor: pointer;
  padding: 3px;
}

.small-icon-btn:hover,
.memory-delete:hover {
  background: #e8f3fb;
  color: #3d3d3d;
}

.disable-btn:hover {
  background: #fde8e8 !important;
  color: #ba5f5f !important;
}

.memory-empty {
  color: #9aa7b2;
  font-size: 12px;
  margin: 0;
  padding: 4px;
}

.memory-disabled-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px;
}

.memory-enable-btn {
  background: #e1efff;
  color: #3b82f6;
  border: 1px solid #c8e1ff;
  border-radius: 6px;
  padding: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s, border-color 0.2s;
}

.memory-enable-btn:hover {
  background: #3b82f6;
  color: white;
  border-color: #3b82f6;
}

.memory-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  margin: 0;
  max-height: 150px;
  overflow-y: auto;
}

.memory-item {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  padding: 6px;
  border-radius: 7px;
  background: #eef6fc;
}

.memory-text {
  flex: 1;
  min-width: 0;
  color: #44515c;
  font-size: 12px;
  line-height: 1.35;
  white-space: normal;
  word-break: keep-all;
  overflow-wrap: anywhere;
}

</style>
