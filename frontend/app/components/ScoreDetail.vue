<script setup lang="ts">
// Panel giải thích điểm: tô vào văn bản phần làm điểm cao/thấp. Dữ liệu từ seo_detail của backend.
const props = defineProps<{ kind: 'seo' | 'readability'; detail: any; md: string; keyword: string }>()

const rd = computed(() => props.detail?.readability?.details ?? {})
const items = computed<any[]>(() => props.detail?.items ?? [])
const passed = computed(() => Object.fromEntries(items.value.map(i => [i.id, i.passed])))
const selected = ref<string | null>(null)

// Bỏ dấu từng ký tự để index khớp với chuỗi gốc (giống fold() bên Python)
const fold1 = (c: string) => {
  const r = c.toLowerCase().replace('đ', 'd').normalize('NFD').replace(/\p{Mn}/gu, '')
  return r.length === 1 ? r : c
}

// Mỗi vùng tô gắn với các check id; thứ tự = ưu tiên khi chồng nhau
const ranges = computed(() => {
  const md = props.md, out: { ids: string[]; start: number; end: number }[] = []
  const kw = [...props.keyword].map(fold1).join('').trim()
  if (kw) {
    const f = md.split('').map(fold1).join('')
    for (let i = f.indexOf(kw); i >= 0; i = f.indexOf(kw, i + kw.length)) out.push({ ids: ['density'], start: i, end: i + kw.length })
  }
  for (const m of md.matchAll(/\[[^\]]*\]\(https?:\/\/[^)\s]+\)/g)) out.push({ ids: ['ext_links'], start: m.index, end: m.index + m[0].length })
  const h1 = /^#\s+.*$/m.exec(md)
  if (h1) out.push({ ids: ['kw_h1'], start: h1.index, end: h1.index + h1[0].length })
  for (const m of md.matchAll(/^##\s+.*$/gm)) out.push({ ids: ['kw_h2', 'h2_count'], start: m.index, end: m.index + m[0].length })
  // shortcut: đếm từ trên markdown thô (bỏ URL), có thể lệch vài từ so với strip_markdown bên Python
  const from = h1 ? h1.index + h1[0].length : 0
  let n = 0, end = from
  for (const m of md.slice(from).matchAll(/\]\([^)]*\)|[\p{L}\p{N}_]+/gu)) {
    if (m[0].startsWith('](')) continue
    end = from + m.index + m[0].length
    if (++n === 100) break
  }
  out.push({ ids: ['kw_first100'], start: from, end })
  return out
})
const textChecks = computed(() => new Set(ranges.value.flatMap(r => r.ids)))

const segments = computed(() => {
  const md = props.md, tag: (string | null)[] = new Array(md.length).fill(null)
  for (const r of [...ranges.value].reverse()) {
    const id = selected.value ? r.ids.find(i => i === selected.value) : r.ids[0]
    if (id) tag.fill(id, r.start, r.end)
  }
  const segs: { id: string | null; text: string }[] = []
  for (let i = 0; i < md.length; i++) {
    if (segs.at(-1)?.id === tag[i]) segs.at(-1)!.text += md[i]
    else segs.push({ id: tag[i], text: md[i] })
  }
  return segs
})

function cls(id: string | null) {
  if (!id) return ''
  const ok = passed.value[id]
  if (id === 'kw_first100') return `underline decoration-2 decoration-dotted ${ok ? 'decoration-emerald-500' : 'decoration-red-500'}`
  return `rounded-sm ${ok ? 'bg-emerald-500/20' : 'bg-red-500/25'}`
}
</script>

<template>
  <Card class="shrink-0 gap-3 border-0 p-0 text-sm shadow-none">
    <template v-if="kind === 'readability'">
      <p v-if="!rd.paragraphs" class="text-muted-foreground">Chưa có dữ liệu độ dễ đọc.</p>
      <template v-else>
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
          <span>Câu TB: <b class="text-foreground">{{ rd.avg_sentence_words }}</b> âm tiết/từ</span>
          <span>Câu/đoạn TB: <b class="text-foreground">{{ rd.avg_sentences_per_paragraph }}</b> (ngưỡng 4)</span>
          <span>Câu dài: <b class="text-foreground">{{ Math.round(rd.long_sentence_ratio * 100) }}%</b></span>
          <span v-if="rd.flesch_reading_ease != null">Flesch: <b class="text-foreground">{{ rd.flesch_reading_ease }}</b></span>
        </div>
        <div class="flex flex-wrap gap-3 text-xs">
          <span><mark class="rounded-sm bg-red-500/25 px-1 text-foreground">câu</mark> dài hơn {{ rd.long_sentence_limit }} âm tiết/từ</span>
          <span class="border-l-4 border-amber-500 pl-2">đoạn quá 4 câu</span>
        </div>
        <div class="shrink-0 space-y-3 overflow-y-auto">
          <p v-for="(p, i) in rd.paragraphs" :key="i" :class="p.long && 'border-l-4 border-amber-500 pl-3'">
            <template v-for="([s, long], j) in p.sentences" :key="j">
              <mark v-if="long" class="rounded-sm bg-red-500/25 text-foreground" :title="`Câu dài hơn ${rd.long_sentence_limit} âm tiết/từ`">{{ s }}</mark>
              <span v-else>{{ s }}</span>{{ ' ' }}
            </template>
          </p>
        </div>
      </template>
    </template>

    <template v-else>
      <ul class="grid gap-1 sm:grid-cols-2">
        <li v-for="i in items" :key="i.id">
          <button
            class="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left enabled:hover:bg-accent disabled:cursor-default"
            :class="{ 'bg-accent': selected === i.id }"
            :disabled="!textChecks.has(i.id)"
            :aria-pressed="selected === i.id"
            @click="selected = selected === i.id ? null : i.id"
          >
            <span :class="i.passed ? 'text-emerald-600' : 'text-red-600'">{{ i.passed ? '✓' : '✗' }}</span>
            <span class="flex-1">{{ i.label }} <span class="text-muted-foreground">· {{ i.detail }}</span></span>
            <span class="tabular-nums text-muted-foreground">{{ i.points }}/{{ i.max }}</span>
          </button>
        </li>
      </ul>
      <p class="text-xs text-muted-foreground">
        Xanh = đạt, đỏ = chưa đạt. Nền: từ khoá, link, heading · gạch chấm: 100 từ đầu. Bấm một tiêu chí để chỉ tô phần của nó.
      </p>
      <pre class="shrink-0 overflow-y-auto whitespace-pre-wrap font-sans"><span v-for="(s, i) in segments" :key="i" :class="cls(s.id)">{{ s.text }}</span></pre>
    </template>
  </Card>
</template>
