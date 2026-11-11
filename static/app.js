/**
 * DWG 标注工厂 - 翻书卷轴交互（客户端上传版）
 */

// ============ 粒子背景 ============
(function initParticles() {
  const canvas = document.getElementById('particleCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let particles = [], w, h;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  for (let i = 0; i < 50; i++) {
    particles.push({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.3, vy: (Math.random() - 0.5) * 0.3,
      r: Math.random() * 2 + 1, a: Math.random() * 0.4 + 0.1,
    });
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    particles.forEach(p => {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = w; if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h; if (p.y > h) p.y = 0;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255,107,53,${p.a * 0.4})`;
      ctx.fill();
    });
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(0,212,170,${0.06 * (1 - dist / 120)})`;
          ctx.lineWidth = 0.5;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(draw);
  }
  draw();
})();

// ============ 翻页滚动检测 ============
const bookContainer = document.querySelector('.book-container');
const pages = document.querySelectorAll('.book-page');
const dots = document.querySelectorAll('.page-dot');
let currentPage = 0;
let isScrolling = false;

function updatePages() {
  if (!bookContainer) return;
  const scrollTop = bookContainer.scrollTop;
  const viewH = bookContainer.clientHeight;

  pages.forEach((page, i) => {
    const rect = page.getBoundingClientRect();
    const offset = rect.top - 60;
    const trigger = viewH * 0.4;
    if (offset < viewH - trigger && offset > -rect.height + trigger) {
      page.classList.add('visible');
      if (currentPage !== i) {
        currentPage = i;
        dots.forEach((d, di) => d.classList.toggle('active', di === i));
      }
    } else {
      page.classList.remove('visible');
    }
  });
}

bookContainer?.addEventListener('scroll', () => {
  if (!isScrolling) {
    requestAnimationFrame(() => {
      updatePages();
      isScrolling = false;
    });
    isScrolling = true;
  }
});

dots.forEach((dot, i) => {
  dot.addEventListener('click', () => {
    pages[i]?.scrollIntoView({ behavior: 'smooth' });
  });
});

setTimeout(updatePages, 100);

// ============ 状态 ============
function getOrCreateClientId() {
  let cid = localStorage.getItem('dwg_client_id');
  if (!cid) {
    cid = 'client_' + Math.random().toString(36).substring(2, 10);
    localStorage.setItem('dwg_client_id', cid);
  }
  return cid;
}

const state = {
  uploadedFiles: [],
  sessionId: '',
  clientId: getOrCreateClientId(),
  taskId: null,
  isRunning: false,
  pollTimer: null,
};

// 上传状态
const uploadState = {
  selectedFiles: [],  // File 对象列表（尚未上传）
};

// ============ DOM ============
const $ = id => document.getElementById(id);
const dom = {
  dropZone: $('dropZone'),
  fileInput: $('fileInput'),
  selectFilesBtn: $('selectFilesBtn'),
  fileCount: $('fileCount'), fileNum: $('fileNum'),
  filesWall: $('filesWall'), fileStats: $('fileStats'),
  modeStandard: $('modeStandard'), modeAI: $('modeAI'),
  aiConfig: $('aiConfig'), aiProvider: $('aiProvider'),
  customApiRow: $('customApiRow'), apiBaseInput: $('apiBaseInput'),
  apiKeyInput: $('apiKeyInput'), toggleKey: $('toggleKey'),
  presetList: $('presetList'),
  cfgFont: $('cfgFont'), cfgTextSize: $('cfgTextSize'),
  cfgArrow: $('cfgArrow'), cfgArrowSize: $('cfgArrowSize'),
  cfgPrecision: $('cfgPrecision'), cfgOffset: $('cfgOffset'),
  recCard: $('recCard'), recList: $('recList'),
  startBtn: $('startBtn'),
  radarCanvas: $('radarCanvas'),
  legendDone: $('legendDone'), legendFail: $('legendFail'), legendWait: $('legendWait'),
  dashStatus: $('dashStatus'), dashProgress: $('dashProgress'),
  dashPercent: $('dashPercent'), progressFill: $('progressFill'),
  progressBarWrap: $('progressBarWrap'), undoWrap: $('undoWrap'), undoBtn: $('undoBtn'),
  logEntries: $('logEntries'), logEntries2: $('logEntries2'),
  downloadList: $('downloadList'), downloadEmpty: $('downloadEmpty'),
  downloadAllWrap: $('downloadAllWrap'), downloadAllBtn: $('downloadAllBtn'),
};

// ============ 初始化 ============
async function init() {
  loadPresets();
  loadRecommendations();
  bindEvents();
  drawRadar(0, 0, 0);
  // 显示 client_id
  const badge = document.getElementById('clientIdBadge');
  if (badge) badge.textContent = 'ID: ' + state.clientId;
}

function copyClientId() {
  const badge = document.getElementById('clientIdBadge');
  if (!badge) return;
  navigator.clipboard.writeText(state.clientId).then(() => {
    badge.textContent = '✅ 已复制';
    setTimeout(() => { badge.textContent = 'ID: ' + state.clientId; }, 2000);
  }).catch(() => {});
}


// ============ 预设加载 ============
async function loadPresets() {
  try {
    const resp = await fetch('/api/gb_presets');
    const data = await resp.json();
    if (!data.success) return;
    for (const [name, cfg] of Object.entries(data.presets)) {
      const btn = document.createElement('button');
      btn.className = 'preset-btn';
      btn.textContent = name.replace(/ \(GB\).*/, '').substring(0, 8);
      btn.title = name;
      btn.dataset.preset = name;
      btn.addEventListener('click', () => applyPreset(name, cfg));
      dom.presetList.appendChild(btn);
    }
  } catch {}
}

function applyPreset(name, cfg) {
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  const btn = [...document.querySelectorAll('.preset-btn')].find(b => b.title === name || b.dataset.preset === name);
  if (btn) btn.classList.add('active');
  if (cfg.font) dom.cfgFont.value = cfg.font;
  if (cfg.text_size) dom.cfgTextSize.value = cfg.text_size;
  if (cfg.arrow_type) dom.cfgArrow.value = cfg.arrow_type;
  if (cfg.arrow_size) dom.cfgArrowSize.value = cfg.arrow_size;
  if (cfg.precision !== undefined) dom.cfgPrecision.value = cfg.precision;
  if (cfg.dim_offset_factor) dom.cfgOffset.value = cfg.dim_offset_factor;
}

// ============ 推荐加载 ============
async function loadRecommendations() {
  try {
    const resp = await fetch('/api/recommendations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_config: getConfig() }),
    });
    const data = await resp.json();
    if (!data.success || !data.recommendations.length) return;
    dom.recCard.style.display = 'block';
    dom.recList.innerHTML = '';
    data.recommendations.forEach((rec, i) => {
      const cfg = rec.config || {};
      const div = document.createElement('div');
      div.className = 'rec-item';
      div.innerHTML = `
        <div class="rec-summary">${cfg.font || '默认'} · ${cfg.text_size || '2.5'} · ${cfg.arrow_type || '实心'}</div>
        <span class="rec-count">已用 ${rec.count} 次</span>`;
      div.addEventListener('click', () => {
        if (cfg.font) dom.cfgFont.value = cfg.font;
        if (cfg.text_size) dom.cfgTextSize.value = cfg.text_size;
        if (cfg.arrow_type) dom.cfgArrow.value = cfg.arrow_type;
        if (cfg.arrow_size) dom.cfgArrowSize.value = cfg.arrow_size;
        if (cfg.precision !== undefined) dom.cfgPrecision.value = cfg.precision;
        if (cfg.dim_offset_factor) dom.cfgOffset.value = cfg.dim_offset_factor;
        addLog(`已填充推荐配置 (使用 ${rec.count} 次)`, 'success');
      });
      dom.recList.appendChild(div);
    });
  } catch {}
}

// ============ 文件上传相关 ============
function handleFiles(files) {
  const dwgFiles = [];
  for (const f of files) {
    if (f.name.toLowerCase().endsWith('.dwg')) {
      dwgFiles.push(f);
    }
  }

  if (!dwgFiles.length) {
    addLog('没有选择 DWG 文件', 'warning');
    return;
  }

  uploadState.selectedFiles = dwgFiles;
  dom.fileCount.style.display = 'block';
  dom.fileNum.textContent = dwgFiles.length;
  dom.fileStats.textContent = `共 ${dwgFiles.length} 个文件`;

  addLog(`已选择 ${dwgFiles.length} 个 DWG 文件`, 'success');

  // 显示文件预览
  renderFilePreview(dwgFiles);
}

function renderFilePreview(files) {
  dom.filesWall.innerHTML = '';
  files.forEach(f => {
    const card = document.createElement('div');
    card.className = 'file-card status-wait';
    card.dataset.name = f.name;
    card.innerHTML = `<div class="file-name">${f.name}</div><span class="file-status">📄</span>`;
    dom.filesWall.appendChild(card);
  });
  drawRadar(0, 0, files.length);
  dom.legendDone.textContent = '0';
  dom.legendFail.textContent = '0';
  dom.legendWait.textContent = files.length;
}

async function uploadFiles() {
  if (!uploadState.selectedFiles.length) {
    addLog('请先选择 DWG 文件', 'warning');
    return false;
  }

  addLog(`正在上传 ${uploadState.selectedFiles.length} 个文件...`, 'info');

  const formData = new FormData();
  for (const f of uploadState.selectedFiles) {
    formData.append('files', f);
  }
  formData.append('client_id', state.clientId);

  try {
    const resp = await fetch('/api/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await resp.json();

    if (!data.success) {
      addLog(`上传失败: ${data.error}`, 'error');
      return false;
    }

    state.sessionId = data.session_id;
    state.uploadedFiles = data.files;
    addLog(`上传成功: ${data.count} 个文件`, 'success');

    // 翻到样式页
    pages[3]?.scrollIntoView({ behavior: 'smooth' });
    return true;
  } catch (e) {
    addLog(`上传请求失败: ${e.message}`, 'error');
    return false;
  }
}

// ============ 拖拽上传 ============
function setupDragDrop() {
  const dz = dom.dropZone;
  if (!dz) return;

  dz.addEventListener('click', (e) => {
    if (e.target !== dom.selectFilesBtn) {
      dom.fileInput?.click();
    }
  });

  dz.addEventListener('dragover', (e) => {
    e.preventDefault();
    dz.classList.add('dragover');
  });

  dz.addEventListener('dragleave', () => {
    dz.classList.remove('dragover');
  });

  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('dragover');
    handleFiles(e.dataTransfer.files);
  });

  dom.selectFilesBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    dom.fileInput?.click();
  });

  dom.fileInput?.addEventListener('change', () => {
    handleFiles(dom.fileInput.files);
    dom.fileInput.value = '';
  });
}

// ============ 绑定事件 ============
function bindEvents() {
  setupDragDrop();
  dom.modeStandard.addEventListener('click', () => setMode('standard'));
  dom.modeAI.addEventListener('click', () => setMode('ai'));
  dom.aiProvider.addEventListener('change', () => {
    dom.customApiRow.style.display = dom.aiProvider.value === 'custom' ? 'flex' : 'none';
  });
  dom.toggleKey.addEventListener('click', () => {
    dom.apiKeyInput.type = dom.apiKeyInput.type === 'password' ? 'text' : 'password';
  });
  dom.startBtn.addEventListener('click', startBatch);
  dom.undoBtn?.addEventListener('click', undoConfirm);
  dom.downloadAllBtn?.addEventListener('click', downloadAll);
}

// ============ 模式切换 ============
function setMode(mode) {
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  if (mode === 'standard') {
    dom.modeStandard.classList.add('active');
    dom.aiConfig.style.display = 'none';
  } else {
    dom.modeAI.classList.add('active');
    dom.aiConfig.style.display = 'block';
  }
}

// ============ 获取配置 ============
function getConfig() {
  return {
    font: dom.cfgFont.value,
    text_size: parseFloat(dom.cfgTextSize.value) || 2.5,
    arrow_type: dom.cfgArrow.value,
    arrow_size: parseFloat(dom.cfgArrowSize.value) || 2.0,
    precision: parseInt(dom.cfgPrecision.value) || 2,
    dim_offset_factor: parseFloat(dom.cfgOffset.value) || 3.0,
  };
}

// ============ 开始标注 ============
async function startBatch() {
  if (state.isRunning) return;

  // 先上传
  if (!state.sessionId && uploadState.selectedFiles.length > 0) {
    dom.startBtn.disabled = true;
    dom.startBtn.querySelector('.btn-text').textContent = '⏳ 上传中...';
    const ok = await uploadFiles();
    if (!ok) {
      resetStartBtn();
      return;
    }
  }

  if (!state.sessionId) {
    addLog('请先上传 DWG 文件', 'warning');
    return;
  }

  const mode = document.querySelector('.mode-btn.active')?.dataset.mode || 'standard';
  const config = getConfig();
  const aiParams = mode === 'ai' ? {
    api_key: dom.apiKeyInput.value.trim(),
    provider: dom.aiProvider.value,
    api_base: dom.apiBaseInput.value.trim() || undefined,
  } : null;

  if (mode === 'ai' && !aiParams.api_key) { addLog('AI 模式需要填写 API Key', 'warning'); return; }

  state.isRunning = true;
  dom.startBtn.disabled = true;
  dom.startBtn.querySelector('.btn-text').textContent = '⏳ 处理中...';
  dom.progressBarWrap.style.display = 'flex';
  dom.undoWrap.style.display = 'none';

  addLog(`启动批量标注 (${mode === 'ai' ? 'AI 智能' : '标准'}模式)`, 'info');
  document.querySelectorAll('.file-card').forEach(c => {
    c.className = 'file-card status-wait';
    c.querySelector('.file-status').textContent = '⚙️';
  });

  try {
    const resp = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.sessionId,
        config, mode,
        ai_params: aiParams,
      }),
    });
    const data = await resp.json();
    if (!data.success) { addLog(`启动失败: ${data.error}`, 'error'); resetStartBtn(); return; }

    state.taskId = data.task_id;
    addLog(`任务已创建: ${data.task_id}，共 ${data.total_files} 个文件`, 'success');
    dom.dashStatus.textContent = '运行中';
    dom.dashProgress.textContent = `0 / ${state.uploadedFiles.length}`;
    pollProgress();
    // 翻到进度监控页
      pages[4]?.scrollIntoView({ behavior: "smooth" });

    fetch('/api/record_usage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config, mode, folder: state.sessionId }),
    }).catch(() => {});
  } catch (e) {
    addLog(`启动请求失败: ${e.message}`, 'error');
    resetStartBtn();
  }
}

// ============ 轮询进度 ============
function pollProgress() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    if (!state.taskId) return;
    try {
      const resp = await fetch(`/api/progress/${state.taskId}`);
      const data = await resp.json();
      if (!data.success) return;
      const task = data.task;
      dom.dashProgress.textContent = `${task.current || 0} / ${task.total}`;
      const pct = task.progress || 0;
      dom.dashPercent.textContent = `${Math.round(pct)}%`;
      dom.progressFill.style.width = `${Math.min(pct, 100)}%`;

      if (task.results) {
        let done = 0, fail = 0, wait = 0;
        for (const [name, result] of Object.entries(task.results)) {
          const card = [...document.querySelectorAll('.file-card')].find(c => c.dataset.name === name);
          if (!card) continue;
          if (result.status === 'completed') {
            card.className = 'file-card status-completed';
            card.querySelector('.file-status').textContent = `✅${result.dims || 0}`;
            done++;
          } else if (result.status === 'failed') {
            card.className = 'file-card status-failed';
            card.querySelector('.file-status').textContent = '❌';
            fail++;
          } else if (result.status === 'processing') {
            card.className = 'file-card status-processing';
            card.querySelector('.file-status').textContent = '🔄';
          } else { wait++; }
        }
        const total = task.total || done + fail + wait;
        drawRadar(done, fail, total - done - fail);
        dom.legendDone.textContent = done;
        dom.legendFail.textContent = fail;
        dom.legendWait.textContent = total - done - fail;
      }

      if (task.waiting_for_agent) {
        dom.dashStatus.textContent = '⏳ 等待可用的工作节点...';
      } else if (task.current_file) dom.dashStatus.textContent = `处理: ${task.current_file}`;

      if (task.status === 'completed' || task.status === 'failed') {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        state.isRunning = false;
        resetStartBtn();

        if (task.status === 'completed') {
          dom.dashStatus.textContent = '✅ 全部完成';
          addLog('🎉 所有文件标注完成！', 'success');
          showCelebration();
          if (task.has_undo) {
            dom.undoWrap.style.display = 'block';
            addLog('💡 如不满意可点击"清除"撤销本次操作', 'info');
          }
          // 自动翻到下载页
          setTimeout(() => {
            loadDownloadResults();
            pages[5]?.scrollIntoView({ behavior: 'smooth' });
          }, 1000);
        } else {
          dom.dashStatus.textContent = '❌ 任务失败';
          addLog(`任务失败: ${task.error}`, 'error');
        }
      }
    } catch (e) {}
  }, 800);
}

// ============ 下载结果 ============
async function loadDownloadResults() {
  if (!state.sessionId) return;

  try {
    const resp = await fetch(`/api/results/${state.sessionId}`);
    const data = await resp.json();
    if (!data.success || !data.results.length) return;

    dom.downloadEmpty.style.display = 'none';
    dom.downloadList.style.display = 'block';
    dom.downloadList.innerHTML = '';

    data.results.forEach(f => {
      const downloadUrl = `/api/download/${state.sessionId}/${f.name.replace('_annotated', '')}`;
      // 从标注结果名提取原始文件名： xxx_annotated.dwg -> xxx.dwg
      const originalName = f.name.replace('_annotated', '');
      const item = document.createElement('div');
      item.className = 'download-item';
      item.innerHTML = `
        <div class="download-info">
          <span class="download-name">${originalName}</span>
          <span class="download-size">(${(f.size / 1024).toFixed(1)} KB)</span>
        </div>
        <a href="${downloadUrl}" class="download-link" download="${originalName}">⬇ 下载</a>
      `;
      dom.downloadList.appendChild(item);
    });

    dom.downloadAllWrap.style.display = 'block';
    addLog(`📥 可下载 ${data.results.length} 个标注文件`, 'success');
  } catch (e) {
    addLog(`加载下载列表失败: ${e.message}`, 'error');
  }
}

function downloadAll() {
  const links = dom.downloadList.querySelectorAll('.download-link');
  links.forEach((link, i) => {
    setTimeout(() => {
      link.click();
    }, i * 500);
  });
  addLog(`开始下载 ${links.length} 个文件...`, 'info');
}

// ============ 重置按钮 ============
function resetStartBtn() {
  dom.startBtn.disabled = false;
  dom.startBtn.querySelector('.btn-text').textContent = '🚀 开始标注';
}

// ============ Canvas: 环形雷达图 ============
function drawRadar(done, fail, wait) {
  const canvas = dom.radarCanvas;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const cx = 100, cy = 100, r = 70;
  const total = done + fail + wait || 1;

  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.strokeStyle = '#30363d';
  ctx.lineWidth = 2;
  ctx.stroke();

  if (done > 0) {
    const a1 = -Math.PI / 2;
    const a2 = a1 + (done / total) * Math.PI * 2;
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, a1, a2); ctx.closePath();
    ctx.fillStyle = 'rgba(0,212,170,0.3)'; ctx.fill();
    ctx.strokeStyle = '#00D4AA'; ctx.lineWidth = 2; ctx.stroke();
  }
  if (fail > 0) {
    const base = (done / total) * Math.PI * 2;
    const a1 = -Math.PI / 2 + base;
    const a2 = a1 + (fail / total) * Math.PI * 2;
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, a1, a2); ctx.closePath();
    ctx.fillStyle = 'rgba(248,81,73,0.3)'; ctx.fill();
    ctx.strokeStyle = '#f85149'; ctx.lineWidth = 2; ctx.stroke();
  }

  ctx.fillStyle = '#e6edf3';
  ctx.font = 'bold 20px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(total, cx, cy - 8);
  ctx.font = '11px sans-serif';
  ctx.fillStyle = '#8b949e';
  ctx.fillText('总计', cx, cy + 14);
}

// ============ 日志 ============
function addLog(msg, level = 'info') {
  const now = new Date();
  const time = now.toTimeString().slice(0, 8);
  const div = document.createElement('div');
  div.className = `log-line ${level}`;
  div.innerHTML = `<span class="log-time">${time}</span> ${msg}`;
  dom.logEntries.appendChild(div);
  dom.logEntries.scrollTop = dom.logEntries.scrollHeight;
  // 也写到第二个日志框
  if (dom.logEntries2) {
    const div2 = div.cloneNode(true);
    dom.logEntries2.appendChild(div2);
    dom.logEntries2.scrollTop = dom.logEntries2.scrollHeight;
  }
}

// ============ 撤销 ============
let undoPollTimer = null;

function undoConfirm() {
  if (!confirm('确定要撤销本次标注的所有操作吗？')) return;
  dom.undoWrap.style.display = 'none';
  dom.dashStatus.textContent = '↩ 正在撤销...';
  addLog('开始撤销标注...', 'info');
  executeUndo(state.taskId);
}

async function executeUndo(taskId) {
  try {
    const resp = await fetch(`/api/undo/${taskId}`, { method: 'POST' });
    const data = await resp.json();
    if (!data.success) { addLog(`撤销失败: ${data.error}`, 'error'); dom.dashStatus.textContent = '❌ 撤销失败'; return; }
    addLog(`撤销操作已启动，共 ${data.total} 个文件`, 'info');
    pollUndoProgress(taskId);
  } catch (e) { addLog(`撤销请求失败: ${e.message}`, 'error'); }
}

function pollUndoProgress(taskId) {
  if (undoPollTimer) clearInterval(undoPollTimer);
  undoPollTimer = setInterval(async () => {
    try {
      const resp = await fetch(`/api/undo_progress/${taskId}`);
      const data = await resp.json();
      if (!data.success) return;
      const pct = data.undo_progress || 0;
      dom.dashPercent.textContent = `${Math.round(pct)}%`;
      dom.progressFill.style.width = `${Math.min(pct, 100)}%`;

      if (data.undo_current_file) dom.dashStatus.textContent = `↩ 撤销: ${data.undo_current_file}`;

      if (data.status === 'completed') {
        clearInterval(undoPollTimer); undoPollTimer = null;
        dom.dashStatus.textContent = '✅ 已撤销，恢复标注前状态';
        dom.dashPercent.textContent = '0%';
        dom.progressFill.style.width = '0%';
        addLog('✅ 所有标注已清除，图纸已恢复', 'success');
        document.querySelectorAll('.file-card').forEach(c => {
          c.className = 'file-card status-wait';
          c.querySelector('.file-status').textContent = '⚙️';
        });
        drawRadar(0, 0, document.querySelectorAll('.file-card').length);
        dom.legendDone.textContent = '0'; dom.legendFail.textContent = '0'; dom.legendWait.textContent = document.querySelectorAll('.file-card').length;
      } else if (data.status === 'failed') {
        clearInterval(undoPollTimer); undoPollTimer = null;
        dom.dashStatus.textContent = '❌ 撤销失败'; addLog('撤销失败', 'error');
      }
    } catch (e) {}
  }, 800);
}

// ============ 庆祝动画 ============
function showCelebration() {
  const container = document.createElement('div');
  container.className = 'celebration';
  const colors = ['#FF6B35', '#00D4AA', '#3fb950', '#58a6ff', '#f85149', '#e3ba3f'];
  for (let i = 0; i < 60; i++) {
    const c = document.createElement('div');
    c.className = 'confetti';
    c.style.left = `${Math.random() * 100}%`;
    c.style.background = colors[i % colors.length];
    c.style.width = `${5 + Math.random() * 8}px`;
    c.style.height = `${5 + Math.random() * 8}px`;
    c.style.borderRadius = Math.random() > 0.5 ? '50%' : '2px';
    c.style.animationDuration = `${1.5 + Math.random() * 2}s`;
    c.style.animationDelay = `${Math.random() * 0.8}s`;
    container.appendChild(c);
  }
  document.body.appendChild(container);
  setTimeout(() => container.remove(), 4000);
}

// ============ 添加下载项 CSS ============
const styleSheet = document.createElement('style');
styleSheet.textContent = `
  .file-input { display: none; }
  .file-card { cursor: default; }
  .download-list { display: flex; flex-direction: column; gap: 8px; }
  .download-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px;
    background: rgba(22,27,34,0.5);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    transition: var(--transition);
  }
  .download-item:hover { border-color: var(--accent-cyan); background: rgba(0,212,170,0.04); }
  .download-info { display: flex; align-items: center; gap: 8px; }
  .download-name { font-size: 0.85rem; color: var(--text-primary); font-weight: 600; }
  .download-size { font-size: 0.75rem; color: var(--text-muted); }
  .download-link {
    padding: 6px 14px;
    background: linear-gradient(135deg, var(--accent-orange), #e85d2c);
    border: none; border-radius: 8px;
    color: #fff; font-size: 0.8rem; font-weight: 700;
    text-decoration: none; cursor: pointer;
    transition: var(--transition);
  }
  .download-link:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(255,107,53,0.3); }
`;
document.head.appendChild(styleSheet);

// ============ 启动 ============
document.addEventListener('DOMContentLoaded', init);
