export const STATUS_LABELS = {
  pending: '待审议',
  in_review: '审议中',
  reviewed: '已审议',
  rejected: '已否定',
}

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

export const VIEWPOINT_STATUS_LABELS = {
  accepted: '已采纳',
  suspended: '已悬置',
  rejected: '已否定',
}

export const RELATION_LABELS = { similar: '相近', conflict: '冲突', related: '相关' }

export const EVENT_TYPE_LABELS = {
  status_change: '状态变更',
  conflict_suspend: '冲突悬置',
  merge: '合并',
  split: '拆分',
}

export function summarize(content, max = 80) {
  return content.length > max ? `${content.slice(0, max)}…` : content
}

export function formatDateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

export function tagLine(viewpoint) {
  return [viewpoint.domain, viewpoint.circle, viewpoint.discipline, viewpoint.scene]
    .filter(Boolean)
    .join(' / ')
}
