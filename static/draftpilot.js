(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const messages = $('instruction');
  const file = $('sketch');
  const labels = {top_left: '左上', top_right: '右上', bottom_left: '左下', bottom_right: '右下'};
  const past = [];
  let current = {state: null, preview_svg: null};
  let busy = false;
  let configured = false;
  let voiceConfigured = false;
  let nativeAvailable = false;
  let recording = null;
  let previewUrl;

  function feedback(text, error = false) {
    const area = $('feedback');
    area.hidden = !text;
    area.textContent = text;
    area.toggleAttribute('data-error', error);
  }

  function busyControls() {
    for (const id of ['submit', 'return-review', 'export', 'edit', 'previous', 'reset', 'remove-sketch']) {
      $(id).disabled = busy || (id === 'submit' && (!configured || Boolean(recording)));
    }
    file.disabled = busy || Boolean(recording);
    document.querySelector('label[for="sketch"]').setAttribute('aria-disabled', String(file.disabled));
    messages.disabled = busy || Boolean(recording);
    $('record').disabled = busy || !voiceConfigured;
  }

  async function getJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || '暂时无法处理，请重试。');
    return data;
  }

  function showInput(title) {
    $('review-view').hidden = true;
    $('input-view').hidden = false;
    $('input-heading').textContent = title;
    $('return-review').hidden = !current.state?.plan;
    messages.placeholder = current.state?.plan
      ? '例如，左上孔向右移动 3 毫米'
      : '例如，做一块十二乘八厘米的板，四角打通孔';
    messages.focus();
  }

  function showReview() {
    const plan = current.state.plan;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(new Blob([current.preview_svg], {type: 'image/svg+xml'}));
    $('preview').src = previewUrl;
    $('dimensions').textContent = '长 × 宽 × 厚  ' + plan.bounding_box_mm.join(' × ') + ' mm';
    $('holes').replaceChildren(...plan.features[1].sketch.holes.map(hole => {
      const row = document.createElement('tr');
      for (const text of [labels[hole.id], hole.x_mm, hole.y_mm, hole.diameter_mm]) {
        const cell = document.createElement('td');
        cell.textContent = text;
        row.append(cell);
      }
      return row;
    }));
    $('previous').hidden = !past.length;
    $('export').hidden = !nativeAvailable;
    $('native-help').hidden = nativeAvailable;
    $('input-view').hidden = true;
    $('review-view').hidden = false;
    $('review-heading').focus();
  }

  function removeAttachment() {
    file.value = '';
    $('attachment').hidden = true;
    $('filename').textContent = '';
  }

  $('message-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !configured || recording) return;
    const text = messages.value.trim();
    const sketch = file.files[0];
    if (!text && !sketch) return feedback('写一句描述，或者选一张草图。', true);
    if (sketch && sketch.size > 2 * 1024 * 1024) return feedback('请选择不超过 2 MiB 的草图。', true);

    const options = {method: 'POST'};
    if (sketch) {
      options.body = new FormData();
      options.body.append('text', text);
      options.body.append('state', JSON.stringify(current.state));
      options.body.append('sketch', sketch);
    } else {
      options.headers = {'Content-Type': 'application/json'};
      options.body = JSON.stringify({text, state: current.state});
    }
    busy = true;
    busyControls();
    feedback('正在理解你的描述…');
    try {
      const result = await getJson('/api/model/v2/turn', options);
      if (result.status === 'ready' && current.state?.plan &&
          JSON.stringify(result.state.plan) !== JSON.stringify(current.state.plan)) {
        past.push(current);
        if (past.length > 20) past.shift();
      }
      current = result;
      messages.value = '';
      removeAttachment();
      busy = false;
      busyControls();
      if (result.status === 'ready') {
        showReview();
        feedback(result.message);
      } else {
        showInput(result.message);
        feedback('');
      }
    } catch (error) {
      feedback(error.message, true);
    } finally {
      busy = false;
      busyControls();
    }
  });

  file.addEventListener('change', () => {
    $('attachment').hidden = !file.files.length;
    $('filename').textContent = file.files[0]?.name || '';
  });
  $('remove-sketch').addEventListener('click', removeAttachment);
  $('edit').addEventListener('click', () => {
    feedback('');
    showInput('你想怎么改？');
  });
  $('return-review').addEventListener('click', () => {
    messages.value = '';
    removeAttachment();
    feedback('');
    showReview();
  });
  $('previous').addEventListener('click', () => {
    current = past.pop();
    showReview();
    feedback('已恢复上一版。');
  });
  $('reset').addEventListener('click', () => {
    current = {state: null, preview_svg: null};
    past.length = 0;
    messages.value = '';
    removeAttachment();
    feedback('');
    showInput('说说你想要什么');
  });

  $('record').addEventListener('click', async () => {
    if (recording) {
      if (recording.state === 'recording') recording.stop();
      return;
    }
    busy = true;
    busyControls();
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: true});
      const mimeType = ['audio/webm', 'audio/mp4', 'audio/ogg'].find(type => MediaRecorder.isTypeSupported(type));
      if (!mimeType) throw new Error('浏览器的录音格式不受支持，请使用文字输入。');
      const recorder = new MediaRecorder(stream, {mimeType});
      const chunks = [];
      let timer;
      recorder.addEventListener('dataavailable', event => { if (event.data.size) chunks.push(event.data); });
      recorder.addEventListener('error', () => {
        chunks.length = 0;
        if (recorder.state === 'recording') recorder.stop();
      });
      recorder.addEventListener('stop', async () => {
        clearTimeout(timer);
        stream.getTracks().forEach(track => track.stop());
        recording = null;
        $('record').textContent = '录一段话';
        busy = true;
        busyControls();
        feedback('正在转成文字…');
        try {
          if (!chunks.length) throw new Error('没有录到内容，请重试。');
          const body = new FormData();
          body.append('audio', new Blob(chunks, {type: mimeType}), 'recording');
          const data = await getJson('/api/model/v2/transcribe', {method: 'POST', body});
          messages.value = data.text;
          feedback('转写完成，请核对数字和单位后提交。');
        } catch (error) {
          feedback(error.message, true);
        } finally {
          busy = false;
          busyControls();
          messages.focus();
        }
      });
      recorder.start();
      recording = recorder;
      timer = setTimeout(() => {
        if (recorder.state === 'recording') recorder.stop();
      }, 30_000);
      $('record').textContent = '结束录音并转写';
      feedback('正在录音，最多 30 秒。');
    } catch {
      stream?.getTracks().forEach(track => track.stop());
      feedback('无法录音，请检查麦克风权限或使用文字输入。', true);
    } finally {
      busy = false;
      busyControls();
    }
  });

  $('export').addEventListener('click', async () => {
    busy = true;
    busyControls();
    feedback('SolidWorks 正在生成并检查文件…');
    try {
      const response = await fetch('/api/model/v2/native', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({plan: current.state.plan})
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || 'SolidWorks 导出未完成，请重试。');
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = 'DraftPilot_SolidWorks.zip';
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      feedback('文件已生成。解压到同一个文件夹后打开工程图。');
    } catch (error) {
      feedback(error.message, true);
    } finally {
      busy = false;
      busyControls();
    }
  });

  busyControls();
  getJson('/api/model/v2/status').then(data => {
    configured = data.cloud_configured;
    nativeAvailable = data.native_available;
    voiceConfigured = data.voice_configured && Boolean(window.MediaRecorder && navigator.mediaDevices?.getUserMedia);
    $('record').hidden = !voiceConfigured;
    if (!configured) {
      $('configuration').textContent = '管理员需要先配置云端模型。可返回 CAD 工作台试用离线参数表单。';
      $('configuration').hidden = false;
    }
  }).catch(error => feedback(error.message, true)).finally(busyControls);
})();
