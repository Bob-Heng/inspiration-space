import { LAYER_EN, STRINGS, TAG_EN } from './i18n'

export const LAYER_OPTIONS = ['道', '法', '术']

export const LAYER_LABELS = { dao: '道', fa: '法', shu: '术' }

export const DOMAIN_OPTIONS = ['政治', '经济', '文化', '社会', '科技', '其他']

export const CIRCLE_OPTIONS = ['个人', '家庭', '朋友', '同事同窗', '公众', '其他']

export const DISCIPLINE_OPTIONS = [
  '哲学',
  '心理学',
  '经济学',
  '社会学',
  '历史',
  '自然科学',
  '计算机',
  '文学艺术',
  '其他',
]

export const SCENE_OPTIONS = [
  '自我管理',
  '商业创业',
  '投资',
  '社交沟通',
  '学习认知',
  '文旅消费',
  '其他',
]

export const RELATION_LABELS = { similar: '相近', conflict: '冲突', related: '相关' }

// ---- 语言感知辅助（lang = 'zh' | 'en'） ----
export function layerLabel(code, lang) {
  if (!code) return null
  return lang === 'en' ? (LAYER_EN[code] ?? code) : (LAYER_LABELS[code] ?? code)
}

export function statusLabel(status, lang) {
  return STRINGS[lang]?.statusLabels?.[status] ?? status
}

export function relationLabel(type, lang) {
  return STRINGS[lang]?.relationLabels?.[type] ?? type
}

/** 标签值入库为中文；英文界面仅翻译显示 */
export function tagLabel(value, lang) {
  if (!value) return value
  return lang === 'en' ? (TAG_EN[value] ?? value) : value
}

export function summarize(content, max = 80) {
  return content.length > max ? `${content.slice(0, max)}…` : content
}

export function formatDateTime(iso, lang = 'zh') {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(lang === 'en' ? 'en-US' : 'zh-CN', { hour12: false })
}

export function tagLine(viewpoint, lang = 'zh') {
  return [viewpoint.domain, viewpoint.circle, viewpoint.discipline, viewpoint.scene]
    .filter(Boolean)
    .map((v) => tagLabel(v, lang))
    .join(' / ')
}
