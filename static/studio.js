/* Mechanical CAD Studio: local SPA navigation + deterministic ModelPlan client. */
(() => {
  'use strict';

  const TEMPLATES = {
    rectangular_plate: {
      name: '矩形板',
      description: '创建一块长120毫米、宽80毫米、厚8毫米的矩形板。',
      fields: {length_mm: 120, width_mm: 80, thickness_mm: 8}
    },
    mounting_plate: {
      name: '四孔安装板',
      description: '创建一块长120毫米、宽80毫米、厚8毫米的安装板，四角共有四个直径10毫米的通孔，长边方向间隔90毫米，宽边方向间隔50毫米。',
      fields: {length_mm: 120, width_mm: 80, thickness_mm: 8,
        hole_diameter_mm: 10, pitch_x_mm: 90, pitch_y_mm: 50}
    },
    cylinder: {
      name: '圆柱',
      description: '创建一个直径30毫米、高60毫米的实心圆柱。',
      fields: {diameter_mm: 30, height_mm: 60}
    },
    bushing: {
      name: '轴套',
      description: '创建一个外径40毫米、内径20毫米、长60毫米的轴套。',
      fields: {outer_diameter_mm: 40, inner_diameter_mm: 20, height_mm: 60}
    }
  };
  const FIELDS = {
    length_mm: '长度', width_mm: '宽度', thickness_mm: '厚度',
    hole_diameter_mm: '孔径', pitch_x_mm: 'X 方向孔距', pitch_y_mm: 'Y 方向孔距',
    diameter_mm: '直径', height_mm: '高度',
    outer_diameter_mm: '外径', inner_diameter_mm: '内径'
  };
  const TITLES = {home: '工作台总览', autocad: 'AutoCAD 自动标注',
    solidworks: 'SolidWorks 自动建模', tasks: '任务中心', examples: '零件模板与示例'};
  const state = {view: 'home', mode: 'text', resultTab: 'features',
    result: null, tasks: [], autocadTasks: []};
  const $ = (id) => document.getElementById(id);

  function showView(view, updateHash = true) {
    if (!(view in TITLES)) view = 'home';
    state.view = view;
    Object.keys(TITLES).forEach((key) => {
      $('view-' + key).hidden = key !== view;
    });
    document.querySelectorAll('[data-view]').forEach(btn => {
      const active = btn.dataset.view === view;
      btn.classList.toggle('active', active);
      if (active) btn.setAttribute('aria-current', 'page');
      else btn.removeAttribute('aria-current');
    });
    $('currentPage').textContent = TITLES[view];
    if (updateHash) history.replaceState(null, '', '#' + view);
    if (view === 'tasks') refreshTasks();
    window.scrollTo({top: 0, behavior: 'instant'});
  }

  function setMode(mode) {
    state.mode = mode;
    $('textInputPanel').hidden = mode !== 'text';
    $('formInputPanel').hidden = mode !== 'parameters';
    $('modeText').classList.toggle('selected', mode === 'text');
    $('modeForm').classList.toggle('selected', mode === 'parameters');
    $('modeText').setAttribute('aria-pressed', String(mode === 'text'));
    $('modeForm').setAttribute('aria-pressed', String(mode === 'parameters'));
    setMessage('', '');
  }

  function setMessage(message, kind) {
    const target = $('modelMessage');
    target.hidden = !message;
    target.className = 'result-message' + (kind ? ' ' + kind : '');
    target.textContent = message;
  }

  function buildParameterInputs() {
    const template = TEMPLATES[$('partType').value];
    if (!template) return;
    const area = $('parameterFields');
    area.replaceChildren();
    for (const [key, value] of Object.entries(template.fields)) {
      const wrapper = document.createElement('label');
      wrapper.className = 'parameter-item';
      const label = document.createElement('span');
      label.textContent = FIELDS[key] + ' / mm';
      const input = document.createElement('input');
      input.type = 'number';
      input.min = '0.1';
      input.max = '2000';
      input.step = 'any';
      input.value = value;
      input.required = true;
      input.name = key;
      input.addEventListener('input', clearResult);
      wrapper.append(label, input);
      area.appendChild(wrapper);
    }
  }

  function clearResult() {
    if (!state.result) return;
    state.result = null;
    $('resultStatus').textContent = '待重新验证';
    $('resultStatus').classList.remove('ok');
    $('previewCaption').textContent = 'INPUT CHANGED';
    for (const id of ['downloadPlan', 'downloadSvg', 'downloadReport']) $(id).disabled = true;
  }

  function loadExample(kind) {
    const entry = TEMPLATES[kind];
    if (!entry) return;
    $('partType').value = kind;
    $('description').value = entry.description;
    $('charCount').textContent = entry.description.length + ' / 1000';
    buildParameterInputs();
    state.result = null;
    $('previewStage').replaceChildren();
    const hint = document.createElement('div');
    hint.className = 'empty-preview';
    hint.textContent = '已载入 ' + entry.name + ' 模板。点击下方按钮开始生成。';
    $('previewStage').appendChild(hint);
    $('previewCaption').textContent = 'PREVIEW NOT GENERATED';
    $('artifactContent').textContent = '生成计划后即可查看特征树与验证报告。';
    $('resultStatus').textContent = '等待输入';
    $('resultStatus').classList.remove('ok');
    ['downloadPlan','downloadSvg','downloadReport'].forEach(id => $(id).disabled = true);
    setMode('text');
    showView('solidworks');
  }

  async function generate() {
    const button = $('generateBtn');
    const payload = state.mode === 'text'
      ? {mode: 'text', description: $('description').value}
      : {mode: 'parameters', part_type: $('partType').value, parameters:
          Object.fromEntries([...$('parameterFields').querySelectorAll('input')].map(i => [
            i.name, i.value.trim() === '' ? null : Number(i.value)
          ]))};
    button.disabled = true;
    button.querySelector('span').textContent = '正在验证建模计划…';
    setMessage('', '');
    try {
      const response = await fetch('/api/model/plan', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        clearResult();
        setMessage(data.error || '建模计划生成失败', 'error');
        $('previewStage').textContent = '几何校验未通过，请检查输入。';
        $('artifactContent').textContent = '当前没有可下载的合格建模计划。';
        $('resultStatus').textContent = '校验失败';
        $('resultStatus').classList.remove('ok');
        return;
      }
      state.result = data;
      state.tasks.unshift({part: data.plan.part_label,
        count: data.plan.features.length, time: new Date().toLocaleTimeString('zh-CN'),
        type: 'SolidWorks', status: '离线计划已验证'});
      state.tasks = state.tasks.slice(0, 30);
      $('previewStage').innerHTML = data.preview_svg; // Only trusted, fixed-tag server SVG; no raw user text.
      $('previewCaption').textContent = data.plan.part_label + ' / 几何草图';
      $('resultStatus').textContent = '计划校验通过';
      $('resultStatus').classList.add('ok');
      ['downloadPlan','downloadSvg','downloadReport'].forEach(id => $(id).disabled = false);
      renderArtifactTab();
      setMessage('ModelPlan 校验通过。未启动 SolidWorks，也未生成任何原生 CAD 文件。', 'success');
    } catch (error) {
      clearResult();
      setMessage('无法访问本地建模接口，请确认 Flask 服务正在运行。', 'error');
    } finally {
      button.disabled = false;
      button.querySelector('span').textContent = '验证并生成建模计划';
    }
  }

  function renderArtifactTab() {
    document.querySelectorAll('[data-result-tab]').forEach(btn => btn.classList.toggle('active', btn.dataset.resultTab === state.resultTab));
    const area = $('artifactContent');
    area.replaceChildren();
    if (!state.result) {
      const p = document.createElement('p'); p.className = 'muted';
      p.textContent = '生成计划后，可查看特征顺序、结构化数据及校验报告。';
      area.appendChild(p);
      return;
    }
    if (state.resultTab === 'features') {
      const list = document.createElement('div');
      list.className = 'feature-list';
      state.result.plan.features.forEach((feature, index) => {
        const item = document.createElement('div'); item.className = 'feature-item';
        const number = document.createElement('span'); number.className = 'feature-num';
        number.textContent = String(index + 1).padStart(2, '0');
        const group = document.createElement('div');
        const title = document.createElement('strong');
        const description = document.createElement('small');
        title.textContent = feature.id === 'base' ? '基础实体 / Extrude' : '贯穿孔 / Through Cut';
        const sketchType = feature.sketch.type;
        const human = {rectangle: '矩形草图', circles: '圆孔阵列', circle: '圆形草图', annulus: '环形草图'};
        description.textContent = (human[sketchType] || sketchType) + ' · ' +
          (feature.depth_mm ? '拉伸 ' + feature.depth_mm + ' mm' : '贯穿切除');
        group.append(title, description); item.append(number, group); list.appendChild(item);
      });
      const note = document.createElement('p'); note.className = 'muted';
      note.textContent = '以上为模拟执行的特征序列；真实 SolidWorks 特征树尚未创建。';
      area.append(list, note);
    } else {
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(state.resultTab === 'plan' ? state.result.plan :
        state.result.validation_report, null, 2);
      area.appendChild(pre);
    }
  }

  function saveFile(filename, text, mime) {
    const blob = new Blob([text], {type: mime});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; document.body.append(a);
    a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 200);
  }

  function download(which) {
    if (!state.result) return;
    if (which === 'plan') {
      saveFile('model_plan.json', JSON.stringify(state.result.plan, null, 2) + '\n', 'application/json');
    } else if (which === 'svg') {
      saveFile('geometry_preview.svg', state.result.preview_svg, 'image/svg+xml');
    } else {
      saveFile('validation_report.json', JSON.stringify(state.result.validation_report, null, 2) + '\n', 'application/json');
    }
  }

  async function refreshTasks() {
    const area = $('tasksList'); area.replaceChildren();
    let remote = [];
    try {
      const response = await fetch('/api/task_list');
      const data = await response.json();
      if (response.ok && data.success && Array.isArray(data.tasks)) {
        remote = data.tasks.map(task => ({
          part: 'DWG 批量标注', count: task.total, time: task.id,
          type: 'AutoCAD', status: task.status
        }));
      }
    } catch (_error) {
      // AutoCAD task API is optional to the offline ModelPlan view.
    }
    const all = [...state.tasks, ...remote];
    if (!all.length) {
      const p = document.createElement('p');p.className = 'muted';
      p.textContent = '暂无任务。生成 ModelPlan 后将出现离线验证记录。';
      area.appendChild(p);
      return;
    }
    for (const item of all) {
      const row = document.createElement('div');row.className='task-row';
      const badge = document.createElement('span');badge.className='task-kind';
      badge.textContent = item.type === 'SolidWorks' ? 'SW' : 'DWG';
      const main = document.createElement('div');main.className='task-main';
      const title = document.createElement('strong');title.textContent = item.part;
      const subtitle = document.createElement('small');
      subtitle.textContent = item.type + ' · ' + item.count + ' 个' +
        (item.type === 'SolidWorks' ? '特征' : '文件') + ' · ' + item.time;
      main.append(title, subtitle);
      const status = document.createElement('span');
      status.className = 'task-state' + (item.status === '离线计划已验证' ? '' : ' warning');
      status.textContent = item.status;
      row.append(badge, main, status);area.appendChild(row);
    }
  }

  function init() {
    document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
    document.querySelectorAll('[data-goto]').forEach(button => button.addEventListener('click', () => showView(button.dataset.goto)));
    document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => loadExample(button.dataset.example)));
    document.querySelectorAll('[data-result-tab]').forEach(button => button.addEventListener('click', () => {
      state.resultTab = button.dataset.resultTab; renderArtifactTab();
    }));
    $('modeText').addEventListener('click', () => setMode('text'));
    $('modeForm').addEventListener('click', () => setMode('parameters'));
    $('partType').addEventListener('change', () => {buildParameterInputs();clearResult();});
    $('description').addEventListener('input', () => {
      $('charCount').textContent = $('description').value.length + ' / 1000';
      clearResult();
    });
    $('generateBtn').addEventListener('click', generate);
    $('downloadPlan').addEventListener('click', () => download('plan'));
    $('downloadSvg').addEventListener('click', () => download('svg'));
    $('downloadReport').addEventListener('click', () => download('report'));
    $('refreshTasks').addEventListener('click', refreshTasks);
    window.addEventListener('hashchange', () => showView(location.hash.slice(1), false));
    $('charCount').textContent = $('description').value.length + ' / 1000';
    buildParameterInputs();
    showView(location.hash.slice(1) || 'home', false);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
