/* 悉数清宇 · 问答主页脚本模块：image.js
 *
 * 图片上传：客户端压缩成 data URL，随问题一起 POST。
 *
 * 2026-09-18 从 index.html 的内联 <script> 拆出（阶段 2b）。
 * 拆分原因：Google JavaScript Style Guide —— 源文件应为 ES module；
 *   ESLint max-lines 默认 300 行。原内联脚本 125 行里塞了 42 个函数、最长行 2623 字符。
 */

/* ============================================================
 *  image.js
 * ============================================================ */


/* ===== 图片上传：客户端压缩后转 data URL，随问题一起 POST ===== */
export let pendingImage = null; // {thumb, full, name}  thumb 存浏览器历史，full 发给模型
const IMG_MAX_EDGE = 1600,
  THUMB_MAX_EDGE = 320;
export function openImage(src) {
  document.getElementById('imgViewerImg').src = src;
  document.getElementById('imgViewer').classList.add('open');
}
function readAsDataURL(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}
function loadImg(src) {
  return new Promise((res, rej) => {
    const i = new Image();
    i.onload = () => res(i);
    i.onerror = rej;
    i.src = src;
  });
}
function scaleTo(img, maxEdge, quality) {
  const s = Math.min(1, maxEdge / Math.max(img.width, img.height)),
    w = Math.max(1, Math.round(img.width * s)),
    h = Math.max(1, Math.round(img.height * s)),
    cv = document.createElement('canvas');
  cv.width = w;
  cv.height = h;
  const cx = cv.getContext('2d');
  cx.fillStyle = '#fff';
  cx.fillRect(0, 0, w, h);
  cx.drawImage(img, 0, 0, w, h);
  return cv.toDataURL('image/jpeg', quality);
}
export async function onPickImage(input) {
  const file = input.files && input.files[0];
  input.value = '';
  if (!file) return;
  if (!/^image\//.test(file.type)) {
    document.getElementById('state').textContent = '只能上传图片文件';
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    document.getElementById('state').textContent = '原图超过 20MB，请先压缩';
    return;
  }
  try {
    document.getElementById('state').textContent = '正在处理图片…';
    const raw = await readAsDataURL(file),
      img = await loadImg(raw);
    if (Math.max(img.width, img.height) < 40) throw new Error('图片太小');
    pendingImage = {
      thumb: scaleTo(img, THUMB_MAX_EDGE, 0.7),
      full: scaleTo(img, IMG_MAX_EDGE, 0.85),
      name: file.name || '图片',
    };
    document.getElementById('attachThumb').src = pendingImage.thumb;
    document.getElementById('attachName').textContent = pendingImage.name;
    document.getElementById('attachBar').classList.add('open');
    document.getElementById('state').textContent = '图片已就绪，可继续输入问题';
    document.getElementById('q').focus();
  } catch (e) {
    pendingImage = null;
    document.getElementById('state').textContent = '图片读取失败：' + (e.message || e);
  }
}
export function clearPendingImage() {
  pendingImage = null;
  document.getElementById('attachBar').classList.remove('open');
  document.getElementById('attachThumb').src = '';
  document.getElementById('attachName').textContent = '';
  document.getElementById('fileInput').value = '';
  document.getElementById('state').textContent = 'Enter 发送，Shift+Enter 换行';
}
