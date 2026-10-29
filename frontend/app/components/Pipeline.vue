<script setup lang="ts">
import { Check, ChevronRight, Loader2, X } from '@lucide/vue'
import { AGENTS, fmtSecs } from '@/lib/format'

const props = defineProps<{ steps: any[] }>()

// Agent có thể chạy nhiều lần (QA fix) → lấy lần chạy cuối, cộng dồn thời gian
const now = useNow({ interval: 1000 }) // tick mỗi giây để node đang chạy đếm giờ realtime
const nodes = computed(() => AGENTS.map((a) => {
  const runs = props.steps.filter(s => s.agent === a.id)
  const last = runs.at(-1)
  const secs = runs.reduce((t, s) => t + Math.max(0, ((s.finished_at ? new Date(s.finished_at) : now.value).getTime() - new Date(s.started_at).getTime()) / 1000), 0)
  return { ...a, status: last?.status ?? 'pending', runs: runs.length, secs, note: last?.note }
}))
</script>

<template>
  <ol class="flex flex-wrap items-center gap-1.5">
    <template v-for="(n, i) in nodes" :key="n.id">
      <li
        class="flex min-w-24 items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors"
        :class="{
          'border-blue-500 bg-blue-500/10': n.status === 'running',
          'border-emerald-500/50 bg-emerald-500/10': n.status === 'done',
          'border-red-500 bg-red-500/10': n.status === 'failed',
          'text-muted-foreground': n.status === 'pending',
        }"
        :title="n.note || undefined"
      >
        <Loader2 v-if="n.status === 'running'" class="size-4 animate-spin text-blue-500" />
        <Check v-else-if="n.status === 'done'" class="size-4 text-emerald-500" />
        <X v-else-if="n.status === 'failed'" class="size-4 text-red-500" />
        <span v-else class="size-4 rounded-full border-2" />
        <div class="leading-tight">
          <div class="font-medium">{{ n.label }}<span v-if="n.runs > 1" class="text-xs text-muted-foreground"> ×{{ n.runs }}</span></div>
          <div class="text-xs text-muted-foreground">{{ n.runs ? fmtSecs(n.secs) : '—' }}</div>
        </div>
      </li>
      <ChevronRight v-if="i < nodes.length - 1" class="size-4 text-muted-foreground" aria-hidden="true" />
    </template>
  </ol>
</template>
