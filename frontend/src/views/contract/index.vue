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

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无维保合同数据，可先登记维保合同</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条维保合同记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="dialogMode" class="dialog-mask" @click.self="closeDialog">
      <form class="dialog" @submit.prevent="dialogMode === 'create' ? submitCreate() : submitRenew()">
        <h3>{{ dialogMode === 'create' ? '登记维保合同' : '到期续签' }}</h3>
        <template v-if="dialogMode === 'create'">
          <label v-for="field in createFields" :key="field.name" class="dialog-item">
            <span>{{ field.label }}<em v-if="field.required">*</em></span>
            <input
              v-model="createForm[field.name]"
              :type="field.type"
              :placeholder="`请填写${field.label}`"
            />
          </label>
        </template>
        <template v-else>
          <p class="dialog-desc">合同 {{ renewForm.合同编号 }} 续签后回到「执行中」，请确认签约单位并填写新的到期日期。</p>
          <label class="dialog-item">
            <span>签约单位<em>*</em></span>
            <input v-model="renewForm.签约单位" placeholder="请填写签约单位" />
          </label>
          <label class="dialog-item">
            <span>到期日期<em>*</em></span>
            <input v-model="renewForm.到期日期" type="date" />
          </label>
        </template>
        <p v-if="dialogError" class="error-text dialog-error">{{ dialogError }}</p>
        <div class="dialog-actions">
          <button class="btn primary" type="submit">提交</button>
          <button class="btn ghost" type="button" @click="closeDialog">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/contract'
const columns = ["合同编号", "签约单位", "维保范围", "合同金额", "签约日期", "到期日期", "是否续签", "合同状态"]
const actions = ["签订合同", "到期续签", "终止合同"]
const statuses = ["待签约", "执行中", "即将到期", "已终止"]
const stats = [{"label": "执行中合同", "value": 0}, {"label": "即将到期合同", "value": 0}, {"label": "已终止合同", "value": 0}]

const createFields = [
  { name: '合同编号', label: '合同编号', type: 'text', required: true },
  { name: '签约单位', label: '签约单位', type: 'text', required: true },
  { name: '维保范围', label: '维保范围', type: 'text', required: true },
  { name: '合同金额', label: '合同金额', type: 'text', required: false },
  { name: '签约日期', label: '签约日期', type: 'date', required: false },
  { name: '到期日期', label: '到期日期', type: 'date', required: true },
] as const

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const dialogMode = ref<'create' | 'renew' | null>(null)
const dialogError = ref('')
const createForm = ref<Record<string, string>>({})
const renewForm = ref<{ id: number | null; 合同编号: string; 签约单位: string; 到期日期: string }>({
  id: null,
  合同编号: '',
  签约单位: '',
  到期日期: '',
})

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  dialogError.value = ''
  dialogMode.value = 'create'
}

function openRenew(row: Row) {
  renewForm.value = {
    id: Number(row.id),
    合同编号: String(row['合同编号'] ?? ''),
    签约单位: String(row['签约单位'] ?? ''),
    到期日期: '',
  }
  dialogError.value = ''
  dialogMode.value = 'renew'
}

function closeDialog() {
  dialogMode.value = null
  dialogError.value = ''
}

async function parseResult(response: Response): Promise<{ ok: boolean; message: string }> {
  const payload = await response.json().catch(() => null) as { ok?: boolean; message?: string; detail?: string } | null
  if (!response.ok) {
    return { ok: false, message: payload?.detail ?? `接口返回 ${response.status}，请稍后重试` }
  }
  if (payload && payload.ok === false) {
    return { ok: false, message: payload.message ?? '维保合同操作未生效' }
  }
  return { ok: true, message: payload?.message ?? '' }
}

async function runAction(action: string, row: Row) {
  if (action === '到期续签') {
    openRenew(row)
    return
  }
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await parseResult(response)
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    noticeMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '维保合同操作失败'
  }
}

async function submitCreate() {
  // 提交前先校必填：缺哪项就点明哪项，表单内容保留可改完再交。
  const missing = createFields.filter((field) => field.required && !createForm.value[field.name]?.trim())
  if (missing.length) {
    dialogError.value = `请先补齐必填项：${missing.map((field) => field.label).join('、')}`
    return
  }
  const values: Row = {}
  for (const field of createFields) {
    const raw = createForm.value[field.name]?.trim() ?? ''
    if (field.name === '合同金额' && raw !== '') {
      const amount = Number(raw)
      values[field.name] = Number.isFinite(amount) ? amount : raw
    } else {
      values[field.name] = raw
    }
  }
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const result = await parseResult(response)
    if (!result.ok) {
      dialogError.value = result.message
      return
    }
    closeDialog()
    noticeMessage.value = result.message
    errorMessage.value = ''
    await reload()
  } catch (error) {
    dialogError.value = error instanceof Error ? error.message : '维保合同登记失败，请稍后重试'
  }
}

async function submitRenew() {
  const missing = (['签约单位', '到期日期'] as const).filter((field) => !renewForm.value[field]?.trim())
  if (missing.length) {
    dialogError.value = `请先补齐必填项：${missing.join('、')}`
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${renewForm.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action: '到期续签', 签约单位: renewForm.value.签约单位, 到期日期: renewForm.value.到期日期 },
      }),
    })
    const result = await parseResult(response)
    if (!result.ok) {
      dialogError.value = result.message
      return
    }
    closeDialog()
    noticeMessage.value = result.message
    errorMessage.value = ''
    await reload()
  } catch (error) {
    dialogError.value = error instanceof Error ? error.message : '维保合同续签失败，请稍后重试'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
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

onMounted(reload)
</script>

<style scoped>
.notice-text { color: #067647; }
.dialog-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}
.dialog {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  width: 380px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dialog h3 { margin: 0; }
.dialog-desc { margin: 0; font-size: 12px; color: var(--muted); }
.dialog-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.dialog-item em { color: #b42318; font-style: normal; margin-left: 2px; }
.dialog-item input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
}
.dialog-error { margin: 0; font-size: 12px; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
</style>
