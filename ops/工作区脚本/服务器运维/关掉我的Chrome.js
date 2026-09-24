/* 关掉**我起的那个** headless Chrome（通过 CDP 的 Browser.close，不碰用户自己的浏览器）。
 * 纪律：不用 taskkill/Stop-Process 按进程名杀 —— 用户自己开着的 Chrome 会一起死。
 */
const CDP = 'http://127.0.0.1:9222';

(async () => {
  let v;
  try {
    v = await (await fetch(CDP + '/json/version')).json();
  } catch (e) {
    console.log('9222 上没有 CDP（Chrome 已经关了）');
    return;
  }
  const ws = new WebSocket(v.webSocketDebuggerUrl);
  await new Promise((res) => { ws.onopen = res; });
  ws.send(JSON.stringify({ id: 1, method: 'Browser.close', params: {} }));
  console.log('已发送 Browser.close：' + v.Browser);
  await new Promise((r) => setTimeout(r, 1500));
  try {
    await fetch(CDP + '/json/version');
    console.log('⚠ 好像还活着，请人工确认');
  } catch (e) {
    console.log('✓ CDP 端口已关，实例已退出');
  }
  process.exit(0);
})();
