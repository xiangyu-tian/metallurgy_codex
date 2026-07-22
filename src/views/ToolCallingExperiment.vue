<template>
  <div class="experiment-page">
    <Header />

    <main class="experiment-shell">
      <section class="hero-panel">
        <div>
          <p class="eyebrow">METALLURGY PLATFORM · RESEARCH BENCH</p>
          <h1>大模型工具调用实验台</h1>
          <p class="hero-copy">对比直接回答、强制调用与自主调用，完整记录模型选择、参数校验、数值依据和最终回答。</p>
        </div>
        <div class="baseline-stamp">
          <span>BASELINE</span>
          <strong>v2.0</strong>
          <small>{{ models.length || 17 }} MODELS FROZEN</small>
        </div>
      </section>

      <section class="bench-grid">
        <form class="control-panel" @submit.prevent="runExperiment">
          <div class="panel-heading">
            <span class="panel-index">01</span>
            <div>
              <h2>实验条件</h2>
              <p>定义问题与调用策略</p>
            </div>
          </div>

          <label class="field field-wide">
            <span>用户问题</span>
            <textarea v-model.trim="form.userQuery" rows="4" placeholder="例如：请计算 Fe₂O₃ 的摩尔质量" required></textarea>
          </label>

          <div class="mode-selector" role="radiogroup" aria-label="调用模式">
            <button
              v-for="mode in modes"
              :key="mode.value"
              type="button"
              :class="['mode-button', { active: form.mode === mode.value }]"
              @click="form.mode = mode.value"
            >
              <span>{{ mode.code }}</span>
              <strong>{{ mode.label }}</strong>
              <small>{{ mode.hint }}</small>
            </button>
          </div>

          <div class="field-row">
            <label class="field">
              <span>大模型</span>
              <input v-model.trim="form.llmName" placeholder="external-orchestrator" />
            </label>
            <label class="field">
              <span>Prompt 版本</span>
              <input v-model.trim="form.promptVersion" placeholder="v1" />
            </label>
          </div>

          <label v-if="form.mode !== 'direct'" class="field field-wide">
            <span>{{ form.mode === 'forced' ? '强制模型' : '指定模型（可选）' }}</span>
            <select v-model="form.modelCode" :required="form.mode === 'forced'">
              <option value="">自主召回</option>
              <option v-for="model in models" :key="model.model_code" :value="model.model_code">
                {{ model.model_code }} · {{ model.model_name }}
              </option>
            </select>
          </label>

          <label v-if="form.mode !== 'direct'" class="field field-wide">
            <span>标准参数 JSON</span>
            <textarea v-model="form.argumentsText" class="code-input" rows="6" spellcheck="false"></textarea>
            <small class="field-note">参数先经过 validate，校验通过后才执行模型。</small>
          </label>

          <label class="check-field">
            <input v-model="form.validateResult" type="checkbox" />
            <span>开启结果可信校验</span>
          </label>

          <p v-if="errorMessage" class="error-message" role="alert">{{ errorMessage }}</p>
          <button class="run-button" type="submit" :disabled="running">
            <span>{{ running ? '实验运行中' : '运行对比实验' }}</span>
            <span class="run-arrow">→</span>
          </button>
        </form>

        <section class="trace-panel">
          <div class="panel-heading">
            <span class="panel-index">02</span>
            <div>
              <h2>调用轨迹</h2>
              <p>{{ result ? result.trace_id : '等待实验运行' }}</p>
            </div>
            <span v-if="result" class="mode-tag">{{ modeLabel(result.mode) }}</span>
          </div>

          <div v-if="!result" class="empty-state">
            <div class="empty-orbit"><span></span></div>
            <strong>尚无实验记录</strong>
            <p>提交左侧条件后，这里将呈现完整决策链。</p>
          </div>

          <template v-else>
            <ol class="trace-list">
              <li v-for="step in traceSteps" :key="step.label" :class="step.state">
                <span class="trace-dot"></span>
                <div>
                  <strong>{{ step.label }}</strong>
                  <p>{{ step.value }}</p>
                </div>
              </li>
            </ol>

            <div class="evidence-grid">
              <article>
                <span>候选模型</span>
                <strong>{{ result.candidate_models.length }}</strong>
              </article>
              <article>
                <span>选中模型</span>
                <strong>{{ result.selected_model || '未调用' }}</strong>
              </article>
              <article>
                <span>执行状态</span>
                <strong :class="statusClass">{{ executionStatus }}</strong>
              </article>
              <article>
                <span>总延迟</span>
                <strong>{{ result.latency_ms }} ms</strong>
              </article>
            </div>
          </template>
        </section>
      </section>

      <section v-if="result" class="result-grid">
        <article class="result-card evidence-card">
          <div class="card-label">NUMERICAL EVIDENCE</div>
          <h3>数值依据</h3>
          <pre>{{ formattedExecution }}</pre>
        </article>
        <article class="result-card answer-card">
          <div class="card-label">FINAL ANSWER</div>
          <h3>实验输出</h3>
          <p>{{ result.final_answer }}</p>
          <footer>
            <span>记录编号</span>
            <code>{{ result.experiment_id }}</code>
          </footer>
        </article>
      </section>
    </main>
  </div>
</template>

<script>
import Header from '@/components/Header.vue';

export default {
  name: 'ToolCallingExperiment',
  components: { Header },
  data() {
    return {
      models: [],
      running: false,
      result: null,
      errorMessage: '',
      modes: [
        { value: 'direct', code: 'A', label: '直接回答', hint: '禁止工具' },
        { value: 'forced', code: 'B', label: '强制调用', hint: '指定工具' },
        { value: 'autonomous', code: 'C', label: '自主调用', hint: '模型决策' }
      ],
      form: {
        userQuery: '请计算 Fe2O3 的摩尔质量',
        mode: 'autonomous',
        llmName: 'external-orchestrator',
        promptVersion: 'v1',
        modelCode: '',
        argumentsText: '{\n  "formula": "Fe2O3"\n}',
        validateResult: true
      }
    };
  },
  computed: {
    executionStatus() {
      return this.result?.execution_result?.status || (this.result?.selected_model ? '未执行' : '无需调用');
    },
    statusClass() {
      return this.executionStatus === 'success' ? 'status-success' : '';
    },
    formattedExecution() {
      const execution = this.result?.execution_result;
      if (!execution) return '本模式未调用专业计算工具。';
      return JSON.stringify({
        model: execution.model_code,
        version: execution.model_version,
        data_records: execution.actual_data_records,
        boundary_check: execution.boundary_check,
        output: execution.output,
        error_code: execution.error_code
      }, null, 2);
    },
    traceSteps() {
      const candidates = this.result.candidate_models || [];
      const validation = this.result.validation_result;
      const execution = this.result.execution_result;
      return [
        { label: '识别意图', value: this.result.user_query, state: 'done' },
        { label: '候选召回', value: candidates.length ? candidates.map(item => item.model_code).join(' · ') : '无候选模型', state: 'done' },
        { label: '模型决策', value: this.result.selection_reason, state: 'done' },
        { label: '参数校验', value: validation ? (validation.valid ? '参数协议校验通过' : this.validationMessage(validation)) : '本模式跳过校验', state: validation?.valid === false ? 'rejected' : 'done' },
        { label: '模型执行', value: execution ? `${execution.status} · ${execution.runtime_ms} ms` : '未执行', state: execution?.status === 'success' ? 'done' : 'idle' },
        { label: '结果校验', value: this.result.result_validation_enabled ? '可信校验已开启' : '可信校验未开启', state: 'done' }
      ];
    }
  },
  methods: {
    modeLabel(mode) {
      return this.modes.find(item => item.value === mode)?.label || mode;
    },
    validationMessage(validation) {
      return validation.errors?.map(item => item.message).join('；') || '校验未通过';
    },
    async fetchModels() {
      try {
        const response = await fetch('/api/v1/models');
        if (!response.ok) throw new Error(`模型列表请求失败 (${response.status})`);
        const data = await response.json();
        this.models = data.models || [];
      } catch (error) {
        this.errorMessage = error.message;
      }
    },
    async runExperiment() {
      this.errorMessage = '';
      this.running = true;
      try {
        let args = {};
        if (this.form.mode !== 'direct') {
          try {
            args = JSON.parse(this.form.argumentsText || '{}');
          } catch (error) {
            throw new Error('标准参数不是合法 JSON');
          }
        }
        const response = await fetch('/api/v1/experiments/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_query: this.form.userQuery,
            mode: this.form.mode,
            model_code: this.form.modelCode || null,
            arguments: args,
            llm_name: this.form.llmName || 'external-orchestrator',
            prompt_version: this.form.promptVersion || 'v1',
            result_validation_enabled: this.form.validateResult
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `实验请求失败 (${response.status})`);
        this.result = data;
      } catch (error) {
        this.errorMessage = error.message || '实验运行失败';
      } finally {
        this.running = false;
      }
    }
  },
  mounted() {
    this.fetchModels();
  }
};
</script>

<style scoped>
.experiment-page {
  --ink: #14201f;
  --paper: #f1efe8;
  --oxide: #b54a2b;
  --brass: #c7a15a;
  --line: rgba(20, 32, 31, 0.17);
  min-height: 100vh;
  color: var(--ink);
  background:
    linear-gradient(rgba(20, 32, 31, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(20, 32, 31, 0.035) 1px, transparent 1px),
    var(--paper);
  background-size: 30px 30px;
  font-family: "Noto Serif SC", "Songti SC", serif;
}

.experiment-shell { max-width: 1440px; margin: 0 auto; padding: 132px 5vw 80px; }
.hero-panel { display: flex; justify-content: space-between; gap: 48px; align-items: flex-end; padding-bottom: 34px; border-bottom: 1px solid var(--ink); }
.eyebrow, .card-label { margin: 0 0 12px; color: var(--oxide); font: 700 12px/1.2 Consolas, monospace; letter-spacing: .18em; }
.hero-panel h1 { margin: 0; font-size: clamp(38px, 5vw, 70px); font-weight: 700; letter-spacing: -.04em; }
.hero-copy { max-width: 760px; margin: 20px 0 0; color: #4d5a57; font-size: 17px; line-height: 1.8; }
.baseline-stamp { width: 168px; min-width: 168px; padding: 18px; border: 2px solid var(--oxide); color: var(--oxide); transform: rotate(-2deg); text-align: center; font-family: Consolas, monospace; }
.baseline-stamp span, .baseline-stamp small { display: block; font-size: 10px; letter-spacing: .16em; }
.baseline-stamp strong { display: block; margin: 5px 0; font-size: 32px; }

.bench-grid { display: grid; grid-template-columns: minmax(420px, .88fr) minmax(520px, 1.12fr); margin-top: 34px; border: 1px solid var(--ink); background: rgba(255,255,255,.45); box-shadow: 12px 12px 0 rgba(20,32,31,.1); }
.control-panel, .trace-panel { min-width: 0; padding: 30px; }
.control-panel { border-right: 1px solid var(--ink); }
.panel-heading { display: flex; align-items: center; gap: 14px; margin-bottom: 28px; }
.panel-heading h2 { margin: 0; font-size: 23px; }
.panel-heading p { margin: 3px 0 0; color: #66706e; font: 12px/1.4 Consolas, monospace; }
.panel-index { display: grid; place-items: center; width: 38px; height: 38px; color: var(--paper); background: var(--ink); font: 700 14px Consolas, monospace; }
.mode-tag { margin-left: auto; padding: 7px 10px; color: var(--oxide); border: 1px solid currentColor; font-size: 12px; }
.field { display: grid; gap: 8px; width: 100%; font-size: 13px; font-weight: 700; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 18px; }
.field-wide { margin-top: 18px; }
.field input, .field textarea, .field select { box-sizing: border-box; width: 100%; border: 1px solid var(--line); border-radius: 0; padding: 13px 14px; color: var(--ink); background: rgba(255,255,255,.68); font: 14px/1.6 "Noto Sans SC", sans-serif; outline: none; transition: border-color .2s, box-shadow .2s; }
.field input:focus, .field textarea:focus, .field select:focus { border-color: var(--oxide); box-shadow: 3px 3px 0 rgba(181,74,43,.17); }
.code-input { font-family: Consolas, monospace !important; }
.field-note { color: #747c79; font-weight: 400; }
.mode-selector { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 18px 0 4px; }
.mode-button { display: grid; gap: 5px; min-height: 106px; padding: 13px; text-align: left; color: var(--ink); border: 1px solid var(--line); background: transparent; cursor: pointer; transition: .2s ease; }
.mode-button > span { color: var(--oxide); font: 700 12px Consolas, monospace; }
.mode-button strong { font-size: 15px; }
.mode-button small { color: #737b79; }
.mode-button:hover, .mode-button.active { border-color: var(--ink); background: var(--ink); color: var(--paper); transform: translateY(-3px); box-shadow: 0 6px 0 var(--brass); }
.check-field { display: flex; gap: 9px; align-items: center; margin-top: 18px; font-size: 13px; }
.check-field input { accent-color: var(--oxide); }
.run-button { display: flex; justify-content: space-between; width: 100%; margin-top: 24px; padding: 16px 19px; border: 0; color: #fff; background: var(--oxide); font: 700 15px "Noto Sans SC", sans-serif; cursor: pointer; }
.run-button:hover:not(:disabled) { background: #92381f; }
.run-button:disabled { opacity: .55; cursor: wait; }
.run-arrow { font-size: 20px; }
.error-message { padding: 10px 12px; color: #8d2e1d; border-left: 3px solid var(--oxide); background: rgba(181,74,43,.08); font-size: 13px; }

.empty-state { display: grid; justify-items: center; align-content: center; min-height: 480px; color: #68716f; text-align: center; }
.empty-state strong { margin-top: 20px; color: var(--ink); font-size: 18px; }
.empty-state p { margin: 7px 0; }
.empty-orbit { position: relative; width: 84px; height: 84px; border: 1px solid var(--line); border-radius: 50%; }
.empty-orbit::before, .empty-orbit::after { content: ""; position: absolute; inset: 14px; border: 1px solid var(--brass); border-radius: 50%; }
.empty-orbit::after { inset: 31px; background: var(--oxide); border: 0; }
.empty-orbit span { position: absolute; width: 8px; height: 8px; top: 4px; left: 38px; border-radius: 50%; background: var(--ink); animation: orbit 4s linear infinite; transform-origin: 4px 38px; }
@keyframes orbit { to { transform: rotate(360deg); } }
.trace-list { list-style: none; margin: 0; padding: 5px 0 8px; }
.trace-list li { position: relative; display: grid; grid-template-columns: 22px 1fr; gap: 12px; min-height: 65px; }
.trace-list li::before { content: ""; position: absolute; top: 16px; bottom: -8px; left: 6px; width: 1px; background: var(--line); }
.trace-list li:last-child::before { display: none; }
.trace-dot { z-index: 1; width: 11px; height: 11px; margin-top: 4px; border: 2px solid var(--paper); border-radius: 50%; background: var(--brass); box-shadow: 0 0 0 1px var(--brass); }
.trace-list .rejected .trace-dot { background: var(--oxide); box-shadow: 0 0 0 1px var(--oxide); }
.trace-list .idle { opacity: .5; }
.trace-list strong { font-size: 14px; }
.trace-list p { margin: 4px 0 0; color: #64706d; font: 12px/1.55 "Noto Sans SC", sans-serif; }
.evidence-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; margin-top: 14px; background: var(--line); border: 1px solid var(--line); }
.evidence-grid article { padding: 17px; background: var(--paper); }
.evidence-grid span { display: block; color: #747c79; font-size: 11px; }
.evidence-grid strong { display: block; margin-top: 7px; font: 700 15px Consolas, monospace; }
.status-success { color: #207252; }

.result-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 30px; }
.result-card { min-width: 0; padding: 27px; border-top: 4px solid var(--ink); background: #fff; box-shadow: 0 8px 24px rgba(20,32,31,.08); }
.result-card h3 { margin: 0 0 18px; font-size: 21px; }
.result-card pre { max-height: 380px; overflow: auto; margin: 0; padding: 18px; color: #dfe8df; background: #17211f; font: 12px/1.7 Consolas, monospace; white-space: pre-wrap; }
.answer-card { border-color: var(--oxide); }
.answer-card > p { min-height: 140px; margin: 0; color: #3f4a48; font-size: 15px; line-height: 1.9; white-space: pre-wrap; }
.answer-card footer { display: flex; justify-content: space-between; gap: 16px; margin-top: 24px; padding-top: 15px; border-top: 1px solid var(--line); color: #707876; font-size: 11px; }
.answer-card code { color: var(--oxide); }

@media (max-width: 980px) {
  .hero-panel { align-items: flex-start; }
  .bench-grid { grid-template-columns: 1fr; }
  .control-panel { border-right: 0; border-bottom: 1px solid var(--ink); }
}
@media (max-width: 640px) {
  .experiment-shell { padding: 112px 16px 50px; }
  .hero-panel { display: block; }
  .baseline-stamp { margin-top: 26px; }
  .control-panel, .trace-panel { padding: 20px; }
  .mode-selector, .field-row, .result-grid { grid-template-columns: 1fr; }
  .mode-button { min-height: auto; }
}
</style>
