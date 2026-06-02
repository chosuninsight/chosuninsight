<template>
  <div class="message-row" :class="who">
    <div class="message-wrap">
      <div class="bubble">
        <span class="message-text">
          <template v-for="(part, index) in textParts" :key="index">
            <a
              v-if="part.url"
              :href="part.url"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-link"
            >{{ part.text }}</a>
            <span v-else>{{ part.text }}</span>
          </template>
        </span>
        <div v-if="links && links.length" class="link-buttons">
          <a
            v-for="link in links"
            :key="link.url"
            :href="link.url"
            target="_blank"
            rel="noopener noreferrer"
            class="link-btn"
          >{{ link.label }}</a>
        </div>
        <div v-if="suggestions && suggestions.length" class="suggestion-buttons">
          <button
            v-for="suggestion in suggestions"
            :key="suggestion"
            type="button"
            class="suggestion-btn"
            @click="$emit('suggestion-click', suggestion)"
          >{{ suggestion }}</button>
        </div>
        <details v-if="debug" class="debug-panel">
          <summary>검색 디버그</summary>
          <pre>{{ JSON.stringify(debug, null, 2) }}</pre>
        </details>
      </div>
      <span class="time">{{ time }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  who: String,   // 'user' 또는 'bot'
  text: String,
  time: String,
  links: Array,
  suggestions: Array,
  debug: Object,
})

defineEmits(['suggestion-click'])

const textParts = computed(() => {
  const rawText = props.text || ''
  const urlPattern = /https?:\/\/[^\s)\]]+/gi
  const parts = []
  let lastIndex = 0
  let match

  while ((match = urlPattern.exec(rawText)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ text: rawText.slice(lastIndex, match.index) })
    }
    parts.push({ text: match[0], url: match[0] })
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < rawText.length) {
    parts.push({ text: rawText.slice(lastIndex) })
  }

  return parts.length ? parts : [{ text: rawText }]
})
</script>

<style scoped>
.message-row {
  display: flex;
  margin-bottom: 10px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.bot {
  justify-content: flex-start;
}

.message-wrap {
  display: flex;
  flex-direction: column;
  max-width: 70%;
}

.user .message-wrap {
  align-items: flex-end;
}

.bot .message-wrap {
  align-items: flex-start;
}

.bubble {
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.user .bubble {
  background-color: #6aabdf;
  color: white;
  border-bottom-right-radius: 4px;
}

.bot .bubble {
  background-color: #ecf4fc;
  color: #333;
  border: 1px solid #c2ddf5;
  border-bottom-left-radius: 4px;
}

.message-text {
  overflow-wrap: anywhere;
}

.inline-link {
  color: #1f6fb2;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.inline-link:hover {
  color: #174f80;
}

.inline-link:focus-visible,
.link-btn:focus-visible,
.suggestion-btn:focus-visible,
.debug-panel summary:focus-visible {
  outline: 2px solid #2e86de;
  outline-offset: 2px;
}

.link-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.link-btn {
  display: inline-block;
  padding: 6px 12px;
  background: white;
  border: 1.5px solid #6aabdf;
  border-radius: 20px;
  color: #2e86de;
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
}

.link-btn:hover {
  background: #2e86de;
  color: white;
}

.suggestion-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.suggestion-btn {
  padding: 6px 10px;
  border: 1px solid #b7d7f0;
  border-radius: 14px;
  background: #fff;
  color: #2b6f9f;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.suggestion-btn:hover {
  background: #e7f3fc;
  border-color: #6aabdf;
}

.time {
  font-size: 11px;
  color: #aaa;
  margin-top: 4px;
}

.debug-panel {
  margin-top: 10px;
  font-size: 12px;
  color: #4a5d73;
}

.debug-panel summary {
  cursor: pointer;
  font-weight: 600;
}

.debug-panel pre {
  margin-top: 6px;
  padding: 8px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid #d7e8f7;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 480px) {
  .link-btn {
    max-width: 100%;
    word-break: break-all;
  }
}
</style>
