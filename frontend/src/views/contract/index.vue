<template>
  <section class="page" data-module="contract">
    <header class="page-head">
      <div>
        <h2>维保合同管理</h2>
        <p class="page-desc">维护维保合同，围绕合同编号、签约单位、维保范围、合同金额做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记维保合同</button>
        <button class="btn" type="button" @click="exportRows">导出维保合同清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <!-- 到期提醒：数据来自 /expiring，与台账共用同一到期日期口径 -->
    <section class="reminder-panel">
      <header class="reminder-head">
        <strong>到期提醒（{{ expiringDays }} 天内到期或已过期，未终止）</strong>
        <span class="reminder-total">共 {{ expiringRows.length }} 份</span>
      </header>
      <table v-if="expiringRows.length" class="data-table reminder-table">
        <thead>
          <tr>
            <th>合同编号</th>
            <th>签约单位</th>
            <th>到期日期</th>
            <th>合同状态</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in expiringRows" :key="`exp-${String(row.id)}`">
            <td><button class="link" type="button" @click="openDetail(row)">{{ row['合同编号'] ?? '—' }}</button></td>
            <td>{{ row['签约单位'] ?? '—' }}</td>
            <td>{{ row['到期日期'] ?? '—' }}</td>
            <td>{{ row['合同状态'] ?? '—' }}</td>
            <td class="row-actions">
              <button
                v-for="action in allowedActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty-inline">暂无即将到期的维保合同</p>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>合同编号</span>
        <input v-model="filters.keyword" placeholder="按合同编号检索" />
      </label>
      <label class="filter-item">
        <span>合同状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <button v-if="column === '合同编号'" class="link" type="button" @click="openDetail(row)">
              {{ row[column] ?? '—' }}
            </button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <template v-if="allowedActions(row).length">
              <button
                v-for="action in allowedActions(row)"
                :key="action"
                class="link"
                :class="{ danger: action === '终止合同' }"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="muted-text">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无维保合同数据，可先登记维保合同</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条维保合同记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记 / 签订 / 续签 共用的表单弹窗：失败时保留已填内容并提示缺项，可直接重试 -->
    <div v-if="dialog.mode" class="modal-mask" @click.self="closeDialog">
      <div class="modal-card">
        <header class="modal-head">
          <strong>{{ dialogTitle }}</strong>
          <button class="link" type="button" @click="closeDialog">关闭</button>
        </header>

        <!-- 详情弹窗：直接读取 GET /api/contract/{id}，与台账行逐项对照 -->
        <div v-if="dialog.mode === 'detail'" class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <span class="detail-label">{{ field }}</span>
            <span>{{ dialog.row?.[field] ?? '—' }}</span>
          </template>
        </div>

        <form v-else class="modal-form" @submit.prevent="submitDialog">
          <ul v-if="dialog.errors.length" class="form-errors">
            <li v-for="item in dialog.errors" :key="item">{{ item }}</li>
          </ul>

          <label v-for="field in dialogFields" :key="field.name" class="form-item">
            <span>
              {{ field.label }}<i v-if="field.required" class="required-mark">*</i>
            </span>
            <input
              v-model="dialog.form[field.name]"
              :type="field.type"
              :placeholder="field.placeholder"
              :readonly="field.readonly"
              :class="{ invalid: dialog.fieldErrors[field.name] }"
            />
            <small v-if="dialog.fieldErrors[field.name]" class="field-error">
              {{ dialog.fieldErrors[field.name] }}
            </small>
          </label>

          <div class="modal-actions">
            <button class="btn" type="button" :disabled="dialog.submitting" @click="closeDialog">取消</button>
            <button class="btn primary" type="submit" :disabled="dialog.submitting">
              {{ dialog.submitting ? '提交中…' : dialogSubmitText }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null> & { id: number | string; status?: string }
type DialogMode = '' | 'create' | 'sign' | 'renew' | 'detail'
type FieldDef = {
  name: string
  label: string
  required: boolean
  type?: string
  placeholder?: string
  readonly?: boolean
}

const ENDPOINT = '/api/contract'
const columns = ['合同编号', '签约单位', '维保范围', '合同金额', '签约日期', '到期日期', '是否续签', '合同状态']
const statuses = ['待签约', '执行中', '即将到期', '已终止']
// 动作按状态开放：状态必须顺序推进，已终止不再出现任何动作（含续签）。
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  待签约: ['签订合同', '终止合同'],
  执行中: ['终止合同'],
  即将到期: ['到期续签', '终止合同'],
  已终止: [],
}

const rows = ref<Row[]>([])
const expiringRows = ref<Row[]>([])
const expiringDays = ref(30)
const total = ref(0)
const errorMessage = ref('')
const filters = reactive<{ keyword: string; status: string }>({ keyword: '', status: '' })

// 统计卡口径取全量（不受当前筛选影响）：单独拉一页全量按状态计数
const statsRows = ref<Row[]>([])
const stats = computed(() => {
  const count = (status: string) => statsRows.value.filter((row) => row.status === status).length
  return [
    { label: '执行中合同', value: count('执行中') },
    { label: '即将到期合同', value: count('即将到期') },
    { label: '已终止合同', value: count('已终止') },
  ]
})

const dialog = reactive<{
  mode: DialogMode
  row: Row | null
  form: Record<string, string>
  errors: string[]
  fieldErrors: Record<string, string>
  submitting: boolean
}>({
  mode: '',
  row: null,
  form: {},
  errors: [],
  fieldErrors: {},
  submitting: false,
})

const detailFields = columns

const dialogTitle = computed(() => {
  if (dialog.mode === 'create') return '登记维保合同'
  if (dialog.mode === 'sign') return '签订合同'
  if (dialog.mode === 'renew') return '到期续签'
  return '合同详情'
})

const dialogSubmitText = computed(() => {
  if (dialog.mode === 'sign') return '确认签订'
  if (dialog.mode === 'renew') return '确认续签'
  return '提交登记'
})

const dialogFields = computed<FieldDef[]>(() => {
  if (dialog.mode === 'create') {
    return [
      { name: '合同编号', label: '合同编号', required: true, placeholder: '如 CONT-0004' },
      { name: '签约单位', label: '签约单位', required: true, placeholder: '签约单位名称' },
      { name: '维保范围', label: '维保范围', required: true, placeholder: '维保覆盖的设备与内容' },
      { name: '合同金额', label: '合同金额（万元）', required: false, type: 'number', placeholder: '选填' },
      { name: '到期日期', label: '到期日期', required: true, type: 'date' },
      { name: '签约日期', label: '签约日期', required: false, type: 'date' },
    ]
  }
  if (dialog.mode === 'sign') {
    return [
      { name: '合同编号', label: '合同编号', required: false, readonly: true },
      { name: '签约单位', label: '签约单位', required: true },
      { name: '到期日期', label: '到期日期', required: true, type: 'date' },
      { name: '签约日期', label: '签约日期', required: false, type: 'date' },
    ]
  }
  return [
    { name: '合同编号', label: '合同编号', required: false, readonly: true },
    { name: '签约单位', label: '签约单位', required: false, readonly: true },
    { name: '到期日期', label: '新到期日期', required: true, type: 'date', placeholder: '续签后的到期日期' },
  ]
})

function allowedActions(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row.status ?? '')] ?? []
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// 按本地时区拼 YYYY-MM-DD，避免 toISOString() 用 UTC 在东八区凌晨少算一天
function toISODate(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function addDays(base: Date, days: number): string {
  const next = new Date(base)
  next.setDate(next.getDate() + days)
  return toISODate(next)
}

function isValidISODate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  return !Number.isNaN(new Date(`${value}T00:00:00`).getTime())
}

// 提交前先校必填，明确告诉用户缺哪一项；返回 false 时保留表单内容供修正后重试。
function validateDialog(): boolean {
  dialog.fieldErrors = {}
  const problems: string[] = []
  for (const field of dialogFields.value) {
    if (!field.required) continue
    const value = (dialog.form[field.name] ?? '').trim()
    if (!value) {
      dialog.fieldErrors[field.name] = `请填写${field.label.replace('（万元）', '')}`
      problems.push(`缺少必填项：${field.label.replace('（万元）', '')}`)
      continue
    }
    if (field.type === 'date' && !isValidISODate(value)) {
      dialog.fieldErrors[field.name] = '日期格式应为 YYYY-MM-DD'
      problems.push(`${field.label}格式不正确`)
    }
  }
  if (dialog.mode === 'renew' && !dialog.fieldErrors['到期日期']) {
    const minExpiry = addDays(new Date(), expiringDays.value)
    if (dialog.form['到期日期'] <= minExpiry) {
      dialog.fieldErrors['到期日期'] = `续签到期日期须晚于 ${minExpiry}（至少续签 ${expiringDays.value} 天）`
      problems.push(dialog.fieldErrors['到期日期'])
    }
  }
  if (problems.length) dialog.errors = [`提交未成功：${problems.join('；')}`]
  return problems.length === 0
}

function openCreate() {
  dialog.mode = 'create'
  dialog.row = null
  dialog.form = {}
  dialog.errors = []
  dialog.fieldErrors = {}
}

function openForm(action: '签订合同' | '到期续签', row: Row) {
  dialog.mode = action === '签订合同' ? 'sign' : 'renew'
  dialog.row = row
  dialog.errors = []
  dialog.fieldErrors = {}
  dialog.form =
    action === '签订合同'
      ? {
          合同编号: String(row['合同编号'] ?? ''),
          签约单位: String(row['签约单位'] ?? ''),
          到期日期: String(row['到期日期'] ?? ''),
          签约日期: toISODate(new Date()),
        }
      : {
          合同编号: String(row['合同编号'] ?? ''),
          签约单位: String(row['签约单位'] ?? ''),
          到期日期: addDays(new Date(), 365),
        }
}

async function openDetail(row: Row) {
  dialog.mode = 'detail'
  dialog.row = row
  dialog.form = {}
  dialog.errors = []
  dialog.fieldErrors = {}
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (response.ok) dialog.row = (await response.json()) as Row
  } catch {
    // 列表行里已经有同口径数据，详情读取失败时不影响展示
  }
}

function closeDialog() {
  if (dialog.submitting) return
  dialog.mode = ''
  dialog.row = null
  dialog.form = {}
  dialog.errors = []
  dialog.fieldErrors = {}
}

async function submitDialog() {
  errorMessage.value = ''
  if (dialog.mode === 'detail' || !dialog.mode) return
  if (!validateDialog()) return

  dialog.submitting = true
  dialog.errors = []
  try {
    const isCreate = dialog.mode === 'create'
    const action = dialog.mode === 'sign' ? '签订合同' : '到期续签'
    const url = isCreate ? ENDPOINT : `${ENDPOINT}/${dialog.row?.id}/actions`
    const values = isCreate ? { ...dialog.form } : { ...dialog.form, action }
    const response = await request(url, { method: 'POST', body: JSON.stringify({ values }) })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload || payload.ok === false) {
      // 业务校验失败不关弹窗、不清表单：把缺项/冲突原因亮出来，用户改完直接重试。
      dialog.errors = [payload?.message || '提交失败，请检查填写内容后重试']
      return
    }
    closeDialog()
    await Promise.all([reload(), loadExpiring(), loadStats()])
  } catch (error) {
    dialog.errors = [error instanceof Error ? error.message : '网络异常，提交未完成，可直接重试']
  } finally {
    dialog.submitting = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  if (action === '签订合同' || action === '到期续签') {
    openForm(action, row)
    return
  }
  if (action === '终止合同') {
    if (!window.confirm(`确认终止合同「${row['合同编号']}」？终止后不能再续签。`)) return
    try {
      const response = await request(`${ENDPOINT}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ values: { action } }),
      })
      const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
      if (!response.ok || !payload || payload.ok === false) {
        errorMessage.value = payload?.message || '终止未生效，请稍后重试'
        return
      }
      await Promise.all([reload(), loadExpiring(), loadStats()])
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '终止操作失败，可重试'
    }
  }
}

async function loadExpiring() {
  try {
    const response = await request(`${ENDPOINT}/expiring`)
    if (!response.ok) return
    const payload = (await response.json()) as { days?: number; items?: Row[] }
    expiringRows.value = payload.items ?? []
    if (payload.days) expiringDays.value = payload.days
  } catch {
    // 提醒面板读取失败不阻塞台账展示
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword.trim()) query.set('keyword', filters.keyword.trim())
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('维保合同列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '维保合同列表读取失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}?size=200`)
    if (response.ok) {
      const payload = await response.json()
      statsRows.value = payload.items ?? []
    }
  } catch {
    // 统计卡读取失败不阻塞台账
  }
}

onMounted(() => {
  void reload()
  void loadExpiring()
  void loadStats()
})
</script>

<style scoped>
.reminder-panel {
  background: #fff;
  border: 1px solid #f0d7a6;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.reminder-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  margin-bottom: 8px;
}
.reminder-total {
  color: #b45309;
  font-size: 12px;
}
.reminder-table th,
.reminder-table td {
  padding: 6px 10px;
}
.empty-inline {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
}
.muted-text {
  color: var(--muted);
}
.danger {
  color: #b42318;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 520px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  padding: 16px 18px;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.modal-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.form-item input {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.form-item input[readonly] {
  background: #f1f5f9;
  color: var(--muted);
}
.form-item input.invalid {
  border-color: #b42318;
}
.required-mark {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.field-error {
  color: #b42318;
  font-size: 12px;
}
.form-errors {
  margin: 0;
  padding: 8px 12px 8px 28px;
  background: #fef3f2;
  border: 1px solid #fecdca;
  border-radius: 6px;
  color: #b42318;
  font-size: 13px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 96px 1fr;
  row-gap: 8px;
  column-gap: 12px;
  font-size: 13px;
}
.detail-label {
  color: var(--muted);
}
.filter-item select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
}
</style>
