// ------------------- API helpers -------------------
const API = {
  listImages: () => fetch('/images').then(r => r.json()),
  upload: (file) => {
    const fd = new FormData();
    fd.append('file', file);
    return fetch('/images', { method: 'POST', body: fd }).then(r => { if (!r.ok) throw new Error('Upload failed'); return r.json(); });
  },
  uploadBatch: (files) => {
    const fd = new FormData();
    for (const f of files) fd.append('files', f, f.name);
    return fetch('/images/batch', { method: 'POST', body: fd }).then(r => { if (!r.ok) throw new Error('Batch upload failed'); return r.json(); });
  },
  deleteImage: (image_id, withResults=true) =>
    fetch(`/images/${encodeURIComponent(image_id)}?delete_results=${withResults ? 'true' : 'false'}`, { method: 'DELETE' })
      .then(r => { if (!r.ok) throw new Error('delete failed'); return r.json(); }),

  deleteAllImages: (withResults=false) =>
    fetch(`/images?delete_results=${withResults ? 'true' : 'false'}`, { method: 'DELETE' })
      .then(r => { if (!r.ok) throw new Error('bulk delete failed'); return r.json(); }),


  startOCR: (image_id) => fetch(`/ocr/jobs?image_id=${encodeURIComponent(image_id)}`, { method: 'POST' }).then(r => r.json()),
  startOCRBatch: (ids) => fetch('/ocr/jobs/batch', { method: 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ image_ids: ids }) }).then(r => r.json()),
  jobStatus: (job_id) => fetch(`/ocr/jobs/${encodeURIComponent(job_id)}`).then(r => r.json()),
  getResults: (image_id) => fetch(`/images/${encodeURIComponent(image_id)}/results`).then(r => r.json()),
  cleanResults: (image_id) => fetch(`/images/${encodeURIComponent(image_id)}/clean`, { method: 'POST' }).then(r => r.json()),
  getImageURL: (image_id) => `/images/${encodeURIComponent(image_id)}/file`,
  exportCSV: (image_id) => window.location.assign(`/images/${encodeURIComponent(image_id)}/export.csv`),
  exportAllCSVs: () => window.location.assign('/exports/results.zip'),
  patchItem: (image_id, index, payload) => fetch(`/images/${encodeURIComponent(image_id)}/results/${index}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()),
  removeItem: (image_id, index) => fetch(`/images/${encodeURIComponent(image_id)}/results/${index}/remove`, { method: 'POST' }).then(r => r.json()),
};

// ------------------- State -------------------
const state = {
  images: [],
  current: null,
  results: [],
  img: null,
  scale: 1,
  fitMode: 'width',
  magnify: false,
  lensSize: 200,
  zoom: 2,
  removeMode: false,
  undoStack: []
};

// ------------------- Elements -------------------
const els = {
  imageList: document.getElementById('imageList'),
  uploadForm: document.getElementById('uploadForm'),
  fileInput: document.getElementById('fileInput'),
  uploadBtn: document.getElementById('uploadBtn'),
  uploadFolderForm: document.getElementById('uploadFolderForm'),
  folderInput: document.getElementById('folderInput'),
  uploadFolderBtn: document.getElementById('uploadFolderBtn'),
  runOcrBtn: document.getElementById('runOcrBtn'),
  runOcrAllBtn: document.getElementById('runOcrAllBtn'),
  jobStatus: document.getElementById('jobStatus'),
  downloadCsvBtn: document.getElementById('downloadCsvBtn'),
  downloadAllCsvBtn: document.getElementById('downloadAllCsvBtn'),
  refreshImagesBtn: document.getElementById('refreshImagesBtn'),
  currentFilename: document.getElementById('currentFilename'),
  viewer: document.getElementById('viewer'),
  canvas: document.getElementById('imgCanvas'),
  lens: document.getElementById('lensCanvas'),
  magnifyToggle: document.getElementById('magnifyToggle'),
  fitMode: document.getElementById('fitMode'),
  lensSize: document.getElementById('lensSize'),
  lensSizeVal: document.getElementById('lensSizeVal'),
  lensZoom: document.getElementById('lensZoom'),
  lensZoomVal: document.getElementById('lensZoomVal'),
  hideRemoved: document.getElementById('hideRemoved'),
  removeMode: document.getElementById('removeMode'),
  undoRemoveBtn: document.getElementById('undoRemoveBtn'),
  cleanBtn: document.getElementById('cleanBtn'),
  tableBody: document.querySelector('#resultsTable tbody'),
  deleteImageBtn: document.getElementById('deleteImageBtn'),
  deleteAllImagesBtn: document.getElementById('deleteAllImagesBtn'),
};
const ctx = els.canvas.getContext('2d');
const lensCtx = els.lens.getContext('2d');

// ------------------- Helpers -------------------
function bboxKey(b){ return b ? `${b.x1}|${b.y1}|${b.x2}|${b.y2}` : ''; }

// ------------------- Images list -------------------
function setImages(items) {
  state.images = items;
  els.imageList.innerHTML = '';
  for (const it of items) {
    const li = document.createElement('li');
    li.textContent = it.filename;
    if (state.current && state.current.image_id === it.image_id) li.classList.add('active');
    li.addEventListener('click', () => selectImage(it));
    els.imageList.appendChild(li);
  }
}
async function refreshImages(){ const data = await API.listImages(); setImages(data.items || []); }
els.refreshImagesBtn.addEventListener('click', refreshImages);

// ------------------- Upload -------------------
els.uploadForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = els.fileInput.files[0];
  if (!file) return;
  els.uploadBtn.disabled = true;
  try {
    const res = await API.upload(file);
    els.fileInput.value = '';
    await refreshImages();
    const cur = (state.images || []).find(x => x.image_id === res.image_id);
    if (cur) await selectImage(cur);
  } finally { els.uploadBtn.disabled = false; }
});
els.uploadFolderForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const files = els.folderInput.files;
  if (!files || files.length === 0) return;
  els.uploadFolderBtn.disabled = true;
  try {
    await API.uploadBatch(files);
    els.folderInput.value = '';
    await refreshImages();
  } finally { els.uploadFolderBtn.disabled = false; }
});

// ------------------- Select image -------------------
async function selectImage(it) {
  state.current = it;
  els.currentFilename.textContent = it.filename;
  els.runOcrBtn.disabled = false;
  els.downloadCsvBtn.disabled = false;

  const img = new Image();
  img.onload = async () => {
    state.img = img;

    if (state.fitMode === 'contain') { els.viewer.classList.add('fit'); els.viewer.classList.remove('scroll'); }
    else { els.viewer.classList.add('scroll'); els.viewer.classList.remove('fit'); }

    const containerWidth  = els.viewer.clientWidth;
    const containerHeight = els.viewer.clientHeight || window.innerHeight * 0.7;
    state.scale = (state.fitMode === 'contain')
      ? Math.min(containerWidth / img.naturalWidth, containerHeight / img.naturalHeight, 1)
      : Math.min(containerWidth / img.naturalWidth, 1);

    els.canvas.width  = Math.round(img.naturalWidth  * state.scale);
    els.canvas.height = Math.round(img.naturalHeight * state.scale);

    draw();

    try { const data = await API.getResults(it.image_id); state.results = data.items || []; }
    catch { state.results = []; }
    draw(); renderTable();
  };
  img.src = API.getImageURL(it.image_id);
}

// ------------------- Drawing -------------------
function draw() {
  if (!state.img) return;
  const { img, scale } = state;
  ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);
  ctx.drawImage(img, 0, 0, Math.round(img.naturalWidth*scale), Math.round(img.naturalHeight*scale));

  const hide = els.hideRemoved && els.hideRemoved.checked;
  for (let i=0;i<state.results.length;i++){
    const r = state.results[i];
    if (hide && r.status === 'removed') continue;
    const b = r.bbox;
    const x1 = Math.round(b.x1*scale), y1 = Math.round(b.y1*scale);
    const x2 = Math.round(b.x2*scale), y2 = Math.round(b.y2*scale);
    const isLow = typeof r.confidence === 'number' && r.confidence < 0.6;
    const color = (r.status === 'removed') ? 'rgba(200,200,200,0.95)' : (isLow ? 'red' : 'limegreen');
    ctx.lineWidth = 2; ctx.strokeStyle = color;
    ctx.strokeRect(x1, y1, x2-x1, y2-y1);
    const label = r.name || '(unlabeled)';
    ctx.font = '12px sans-serif';
    const w = ctx.measureText(label).width + 8;
    ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(x1, y1-16, w, 16);
    ctx.fillStyle = 'white'; ctx.fillText(label, x1+4, y1-4);
  }
}

// ------------------- Table -------------------
function renderTable() {
  els.tableBody.innerHTML = '';
  state.results.forEach((r, idx) => {
    const tr = document.createElement('tr');
    const b = r.bbox || {};
    const key = bboxKey(b);
    tr.dataset.bboxKey = key;
    tr.innerHTML = `
      <td>${idx}</td>
      <td><input type="text" value="${r.name ?? ''}" /></td>
      <td>${r.confidence ?? ''}</td>
      <td>${r.status ?? 'active'}</td>
      <td><button class="btn" type="button">Remove</button></td>
    `;
    const input = tr.querySelector('input');
    input.addEventListener('change', async () => {
      if (!state.current) return;
      const latest = await API.getResults(state.current.image_id);
      const items = latest.items || [];
      const idx2 = items.findIndex(it => bboxKey(it.bbox) === key);
      if (idx2 < 0) { state.results = items; renderTable(); draw(); return; }
      await API.patchItem(state.current.image_id, idx2, { name: input.value });
      const refreshed = await API.getResults(state.current.image_id);
      state.results = refreshed.items || [];
      renderTable(); draw();
    });
    const btn = tr.querySelector('button');
    btn.addEventListener('click', async () => {
      if (!state.current) return;
      btn.disabled = true;
      try {
        const latest = await API.getResults(state.current.image_id);
        const items = latest.items || [];
        const idx2 = items.findIndex(it => bboxKey(it.bbox) === key);
        if (idx2 < 0) { state.results = items; renderTable(); draw(); return; }
        await API.removeItem(state.current.image_id, idx2);
        const refreshed = await API.getResults(state.current.image_id);
        state.results = refreshed.items || [];
        renderTable(); draw();
      } finally { btn.disabled = false; }
    });
    els.tableBody.appendChild(tr);
  });
}

// ------------------- OCR (single + bulk) -------------------
els.runOcrBtn.addEventListener('click', async () => {
  if (!state.current) return;
  els.jobStatus.textContent = 'queued…';
  const { job_id } = await API.startOCR(state.current.image_id);
  let done = false;
  while (!done) {
    await new Promise(r => setTimeout(r, 1100));
    const { status } = await API.jobStatus(job_id);
    els.jobStatus.textContent = status;
    if (status === 'done' || status === 'error' || status === 'unknown') done = true;
  }
  if (els.jobStatus.textContent === 'done') {
    const data = await API.getResults(state.current.image_id);
    state.results = data.items || [];
    renderTable(); draw();
  }
});
els.runOcrAllBtn.addEventListener('click', async () => {
  const ids = (state.images || []).map(x => x.image_id);
  if (!ids.length) return;
  const res = await API.startOCRBatch(ids);
  const jobs = new Set(res.job_ids || []);
  if (!jobs.size) return;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  els.jobStatus.textContent = `processing ${jobs.size}…`;
  while (jobs.size) {
    await sleep(1200);
    for (const jid of Array.from(jobs)) {
      const { status } = await API.jobStatus(jid);
      if (status === 'done' || status === 'error' || status === 'unknown') jobs.delete(jid);
    }
    els.jobStatus.textContent = jobs.size ? `processing ${jobs.size}…` : 'done';
  }
  if (state.current) {
    try { const data = await API.getResults(state.current.image_id); state.results = data.items || []; renderTable(); draw(); } catch {}
  }
  alert('Bulk OCR finished.');
});

// ------------------- Export -------------------
els.downloadCsvBtn.addEventListener('click', () => { if (state.current) API.exportCSV(state.current.image_id); });
els.downloadAllCsvBtn.addEventListener('click', API.exportAllCSVs);

// ------------------- Magnifier (uses original image) -------------------
els.magnifyToggle.addEventListener('change', () => {
  state.magnify = els.magnifyToggle.checked;
  els.lens.style.display = state.magnify ? 'block' : 'none';
});
els.lensSize.value = String(state.lensSize); els.lensSizeVal.textContent = String(state.lensSize);
els.lensZoom.value = String(state.zoom);     els.lensZoomVal.textContent = state.zoom.toFixed(1) + '×';
els.lensSize.addEventListener('input', () => {
  const n = parseInt(els.lensSize.value, 10);
  state.lensSize = n; els.lensSizeVal.textContent = String(n);
  els.lens.width = n; els.lens.height = n;
});
els.lensZoom.addEventListener('input', () => {
  const z = parseFloat(els.lensZoom.value);
  state.zoom = z; els.lensZoomVal.textContent = z.toFixed(1) + '×';
});
els.canvas.addEventListener('mousemove', (e) => {
  if (!state.magnify || !state.img || !state.scale) return;
  const rect = els.canvas.getBoundingClientRect();
  const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
  const lensW = els.lens.width = state.lensSize, lensH = els.lens.height = state.lensSize;
  const zoom = state.zoom;
  const centerX_orig = cx / state.scale, centerY_orig = cy / state.scale;
  const srcW_orig = (lensW / zoom) / state.scale, srcH_orig = (lensH / zoom) / state.scale;
  let sx = Math.round(centerX_orig - srcW_orig/2), sy = Math.round(centerY_orig - srcH_orig/2);
  const maxSX = state.img.naturalWidth - srcW_orig, maxSY = state.img.naturalHeight - srcH_orig;
  sx = Math.max(0, Math.min(sx, maxSX)); sy = Math.max(0, Math.min(sy, maxSY));
  lensCtx.clearRect(0, 0, lensW, lensH);
  lensCtx.imageSmoothingEnabled = true;
  lensCtx.drawImage(state.img, sx, sy, srcW_orig, srcH_orig, 0, 0, lensW, lensH);
});

// ------------------- Remove mode (canvas click) -------------------
function findHitIndexByItems(items, origX, origY){
  const cand = [];
  for (let i=0;i<items.length;i++){
    const r = items[i]; if (r.status === 'removed') continue;
    const b = r.bbox || {};
    if (origX>=b.x1 && origX<=b.x2 && origY>=b.y1 && origY<=b.y2){
      const area = Math.max(1,(b.x2-b.x1)*(b.y2-b.y1));
      const conf = (typeof r.confidence==='number')?r.confidence:0;
      cand.push({i, area, conf});
    }
  }
  if (!cand.length) return -1;
  cand.sort((a,b)=> (a.area-b.area) || (b.conf-a.conf));
  return cand[0].i;
}
els.removeMode.addEventListener('change', () => {
  state.removeMode = els.removeMode.checked;
  if (state.removeMode) els.viewer.classList.add('remove-mode'); else els.viewer.classList.remove('remove-mode');
});
els.canvas.addEventListener('click', async (e) => {
  if (!state.removeMode || !state.current || !state.img || !state.scale) return;
  const rect = els.canvas.getBoundingClientRect();
  const origX = (e.clientX - rect.left) / state.scale;
  const origY = (e.clientY - rect.top)  / state.scale;
  const latest = await API.getResults(state.current.image_id).catch(()=>null);
  const items = latest?.items || [];
  const idx = findHitIndexByItems(items, origX, origY);
  if (idx < 0) return;
  const key = bboxKey(items[idx].bbox);
  await API.removeItem(state.current.image_id, idx).catch(()=>null);
  state.undoStack.push({ image_id: state.current.image_id, bboxKey: key, prevStatus: items[idx].status || 'active' });
  const refreshed = await API.getResults(state.current.image_id).catch(()=>null);
  state.results = refreshed?.items || [];
  renderTable(); draw();
});
els.undoRemoveBtn.addEventListener('click', async () => {
  if (!state.undoStack.length || !state.current) return;
  const last = state.undoStack.pop();
  if (last.image_id !== state.current.image_id) return;
  const latest = await API.getResults(state.current.image_id).catch(()=>null);
  const items = latest?.items || [];
  const idx = items.findIndex(it => bboxKey(it.bbox) === last.bboxKey);
  if (idx < 0) return;
  await API.patchItem(state.current.image_id, idx, { status: last.prevStatus }).catch(()=>null);
  const refreshed = await API.getResults(state.current.image_id).catch(()=>null);
  state.results = refreshed?.items || [];
  renderTable(); draw();
});

// ------------------- Clean results -------------------
els.cleanBtn.addEventListener('click', async () => {
  if (!state.current) return;
  els.cleanBtn.disabled = true;
  try {
    const { items } = await API.cleanResults(state.current.image_id);
    state.results = items || [];
    renderTable(); draw();
  } catch (e) {
    alert('Cleaning failed');
  } finally {
    els.cleanBtn.disabled = false;
  }
});

// ------------------- Fit mode / hide removed / resize -------------------
els.fitMode.value = 'width';
els.fitMode.addEventListener('change', (e)=>{ state.fitMode = e.target.value; if (state.current) selectImage(state.current); });
if (els.hideRemoved) els.hideRemoved.addEventListener('change', draw);
window.addEventListener('resize', ()=>{ if (state.current) selectImage(state.current); });

//------------------- Delete single and all ----------------------------
els.deleteImageBtn.addEventListener('click', async () => {
  if (!state.current) return alert('No image selected.');
  const withResults = confirm('Also delete OCR results (JSON+CSV) for this image? Click OK = Yes, Cancel = No.');
  try {
    await API.deleteImage(state.current.image_id, withResults);
    // clear viewer if the current was deleted
    state.current = null;
    state.results = [];
    state.img = null;
    els.canvas.width = els.canvas.height = 0;
    els.tableBody.innerHTML = '';
    els.currentFilename.textContent = '(no file selected)';
    await refreshImages();
  } catch (e) {
    alert('Delete failed');
  }
});

els.deleteAllImagesBtn.addEventListener('click', async () => {
  const sure = confirm('Delete ALL images in the folder? (This cannot be undone)');
  if (!sure) return;
  const withResults = confirm('Also wipe ALL OCR results (JSON+CSV)? Click OK = Yes, Cancel = No.');
  try {
    await API.deleteAllImages(withResults);
    // reset UI
    state.current = null;
    state.results = [];
    state.img = null;
    els.canvas.width = els.canvas.height = 0;
    els.tableBody.innerHTML = '';
    els.currentFilename.textContent = '(no file selected)';
    await refreshImages();
  } catch (e) {
    alert('Bulk delete failed');
  }
});


// ------------------- Init -------------------
refreshImages();
