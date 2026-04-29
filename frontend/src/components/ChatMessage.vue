<template>
  <div class="message-row" :class="who">
    <div class="message-wrap">
      <div class="bubble">
        <span>{{ text }}</span>
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
const props = defineProps({
  who: String,   // 'user' 또는 'bot'
  text: String,
  time: String,
  links: Array,
  debug: Object,
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
</style>
