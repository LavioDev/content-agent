<script setup lang="ts">
import { Check, Copy } from '@lucide/vue'

const props = defineProps<{ text: string }>()
const { copy, copied } = useClipboard({ copiedDuring: 1500 })
</script>

<template>
  <Button
    variant="ghost" size="icon" class="absolute top-2 right-2 size-8 text-muted-foreground"
    :aria-label="copied ? 'Đã sao chép' : 'Sao chép'" @click="copy(props.text)"
  >
    <Check v-if="copied" class="size-4 text-emerald-500" />
    <Copy v-else class="size-4" />
  </Button>
</template>
