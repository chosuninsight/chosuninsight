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
</style>
