// Thứ tự trùng với pipeline.py
export const AGENTS = [
  { id: 'researcher', label: 'Research' },
  { id: 'writer', label: 'Writer' },
  { id: 'editor', label: 'Editor' },
  { id: 'social', label: 'Social' },
  { id: 'seo', label: 'SEO' },
  { id: 'images', label: 'Images' },
  { id: 'qa', label: 'QA' },
]

export const TONES = [
  { value: 'friendly', label: 'Thân thiện' },
  { value: 'professional', label: 'Chuyên nghiệp' },
  { value: 'humorous', label: 'Hài hước' },
  { value: 'inspirational', label: 'Truyền cảm hứng' },
]

export function fmtSecs(s: number) {
  return s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m${String(Math.round(s % 60)).padStart(2, '0')}s`
}
