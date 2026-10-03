/* ══════════════════════════════════════════════════════
   금주의 리포트 — 내려받기(.xlsx) · 이미지 공유 (2026-09-23)

   요구사항 정의서에 '리포트를 파일로 저장하고 링크로 공유한다'로 적어 두고
   화면에는 없던 기능이다. 오른쪽 위 버튼 두 개가 이 파일을 부른다.

   · 엑셀은 바깥 라이브러리 없이 만든다. .xlsx 는 XML 몇 장을 담은 zip 이라,
     압축하지 않는(store) zip 을 직접 쓰면 그것으로 충분하다.
     CSV 로 내리지 않는 이유 — 표가 여러 장이고, 한글 CSV 는 엑셀에서 깨지기 쉽다.
   · 값은 화면에 이미 떠 있는 것만 넣는다. 없는 값은 빈칸으로 두고 지어내지 않는다.
   ══════════════════════════════════════════════════════ */

/* ── 최소 zip(store) ── */
const CRC = (() => {
  const t = new Int32Array(256);
  for (let n = 0; n < 256; n++){
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c;
  }
  return t;
})();
function crc32(bytes){
  let c = -1;
  for (let i = 0; i < bytes.length; i++) c = CRC[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ -1) >>> 0;
}
export const utf8 = s => new TextEncoder().encode(s);

/* files: [{name, data(Uint8Array)}] → .xlsx 한 덩어리 */
export function zipStore(files){
  const chunks = [], central = [];
  let offset = 0;
  files.forEach(f => {
    const name = utf8(f.name), crc = crc32(f.data), n = f.data.length;
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true); local.setUint16(6, 0x0800, true);  /* 이름은 UTF-8 */
    local.setUint16(8, 0, true);                                      /* 압축 안 함 */
    local.setUint32(14, crc, true);
    local.setUint32(18, n, true); local.setUint32(22, n, true);
    local.setUint16(26, name.length, true);
    chunks.push(new Uint8Array(local.buffer), name, f.data);

    const cen = new DataView(new ArrayBuffer(46));
    cen.setUint32(0, 0x02014b50, true);
    cen.setUint16(4, 20, true); cen.setUint16(6, 20, true); cen.setUint16(8, 0x0800, true);
    cen.setUint16(10, 0, true);
    cen.setUint32(16, crc, true);
    cen.setUint32(20, n, true); cen.setUint32(24, n, true);
    cen.setUint16(28, name.length, true);
    cen.setUint32(42, offset, true);
    central.push(new Uint8Array(cen.buffer), name);
    offset += 30 + name.length + n;
  });
  const cenSize = central.reduce((a, b) => a + b.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, files.length, true); end.setUint16(10, files.length, true);
  end.setUint32(12, cenSize, true); end.setUint32(16, offset, true);
  const all = chunks.concat(central, [new Uint8Array(end.buffer)]);
  const total = all.reduce((a, b) => a + b.length, 0);
  const out = new Uint8Array(total);
  let at = 0;
  all.forEach(b => { out.set(b, at); at += b.length });
  return out;
}

/* ── 시트 XML ── */
export const xmlEsc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export const colName = i => {
  let s = '', n = i + 1;
  while (n > 0){ const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = ((n - r) / 26) | 0 }
  return s;
};
/* 숫자로 넣을 값만 숫자 칸(t 없음)으로, 나머지는 인라인 문자열로 쓴다.
   숫자를 문자로 넣으면 엑셀에서 합계가 안 잡히고, 문자를 숫자로 넣으면 깨진다. */
function sheetXML(rows, widths){
  const body = rows.map((row, r) =>
    '<row r="' + (r + 1) + '">' + row.map((v, c) => {
      const ref = colName(c) + (r + 1);
      const isNum = typeof v === 'number' && isFinite(v);
      return isNum
        ? '<c r="' + ref + '"><v>' + v + '</v></c>'
        : (v == null || v === '' ? '<c r="' + ref + '"/>'
          : '<c r="' + ref + '" t="inlineStr"><is><t xml:space="preserve">' + xmlEsc(v) + '</t></is></c>');
    }).join('') + '</row>').join('');
  /* 칸 너비 — 없으면 기본 8자라 '내려받은 시각' 같은 말머리가 잘려 보인다 */
  const cols = (widths && widths.length)
    ? '<cols>' + widths.map((w, i) =>
        '<col min="' + (i + 1) + '" max="' + (i + 1) + '" width="' + w + '" customWidth="1"/>').join('') + '</cols>'
    : '';
  return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
    cols + '<sheetData>' + body + '</sheetData></worksheet>';
}

/* sheets: [{name, rows, widths}] → .xlsx Blob */
export function buildXlsx(sheets){
  const files = [
    { name:'[Content_Types].xml', data:utf8(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      '<Default Extension="xml" ContentType="application/xml"/>' +
      sheets.map((_, i) => '<Override PartName="/xl/worksheets/sheet' + (i + 1) + '.xml" ' +
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>').join('') +
      '<Override PartName="/xl/workbook.xml" ' +
      'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
      '</Types>') },
    { name:'_rels/.rels', data:utf8(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rId1" Target="xl/workbook.xml" ' +
      'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>' +
      '</Relationships>') },
    { name:'xl/workbook.xml', data:utf8(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' +
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' +
      sheets.map((s, i) => '<sheet name="' + xmlEsc(s.name) + '" sheetId="' + (i + 1) +
        '" r:id="rId' + (i + 1) + '"/>').join('') +
      '</sheets></workbook>') },
    { name:'xl/_rels/workbook.xml.rels', data:utf8(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      sheets.map((_, i) => '<Relationship Id="rId' + (i + 1) + '" Target="worksheets/sheet' + (i + 1) + '.xml" ' +
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>').join('') +
      '</Relationships>') },
  ].concat(sheets.map((s, i) => ({ name:'xl/worksheets/sheet' + (i + 1) + '.xml',
    data:utf8(sheetXML(s.rows, s.widths)) })));
  return new Blob([zipStore(files)], {
    type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

export function saveBlob(blob, filename){
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/* ── 이미지 · PDF ──
   화면에 떠 있는 리포트를 그림으로 찍어 PNG 로 주거나, 같은 그림을 한 페이지 PDF 로 만든다.
   라이브러리는 이 기능을 처음 쓸 때만 CDN 에서 받는다(평소 페이지 로딩에는 영향 없음).
   글자가 그림이 되므로 한글 폰트가 PDF 에 들어가지 않아도 깨지지 않는다. */
const H2C_SRC = 'https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js';
const JSPDF_SRC = 'https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js';
const _scripts = {};
function loadScript(src){
  if (!_scripts[src]) _scripts[src] = new Promise((ok, fail) => {
    const el = document.createElement('script');
    el.src = src; el.async = true;
    el.onload = ok;
    el.onerror = () => { delete _scripts[src]; el.remove(); fail(new Error('라이브러리를 불러오지 못했습니다')) };
    document.head.appendChild(el);
  });
  return _scripts[src];
}

/* el 을 캔버스로 찍는다. ignore 로 넘긴 선택자(저장 버튼 등)는 그림에서 뺀다. */
export async function captureElement(el, { ignore = '' } = {}){
  await loadScript(H2C_SRC);
  const bg = getComputedStyle(document.body).backgroundColor;
  return window.html2canvas(el, {
    scale: 2,
    useCORS: true,
    backgroundColor: bg && bg !== 'rgba(0, 0, 0, 0)' ? bg : '#f1efea',
    scrollX: 0, scrollY: -window.scrollY,
    ignoreElements: n => !!(ignore && n.matches && n.matches(ignore)),
  });
}

export function canvasToPng(canvas){
  return new Promise((ok, fail) => canvas.toBlob(
    b => b ? ok(b) : fail(new Error('이미지를 만들지 못했습니다')), 'image/png'));
}

/* 한 페이지 PDF — 폭은 A4(210mm)로 두고, 높이를 그림 길이에 맞춰 잘리는 곳 없이 한 장에 담는다 (여백 8mm) */
export async function canvasToPdf(canvas){
  await loadScript(JSPDF_SRC);
  const M = 8, W = 210 - M * 2;
  const imgH = canvas.height * W / canvas.width;
  const pageW = 210, pageH = imgH + M * 2;
  const portrait = pageH >= pageW;
  const pdf = new window.jspdf.jsPDF({ unit:'mm', orientation: portrait ? 'p' : 'l',
    format: portrait ? [pageW, pageH] : [pageH, pageW] });
  /* 리포트 지면색으로 바탕을 채워 여백이 흰색으로 따로 놀지 않게 한다 */
  const bg = getComputedStyle(document.body).backgroundColor.match(/\d+/g) || [241, 239, 234];
  pdf.setFillColor(+bg[0], +bg[1], +bg[2]);
  pdf.rect(0, 0, pageW, pageH, 'F');
  pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', M, M, W, imgH);
  return pdf.output('blob');
}

/* ── 이미지 공유 ──
   링크가 아니라 리포트 그림(PNG)을 내보낸다.
   · 파일 공유를 지원하는 기기(모바일·맥·윈도 크롬 등)는 기본 공유 시트로 PNG 를 넘긴다.
   · 그렇지 않으면 PNG 를 클립보드에 복사해 붙여넣기로 공유하게 한다.
   · 둘 다 막히면 파일로 저장한다.
   blobPromise 는 아직 만드는 중인 그림이다 — 클립보드 복사는 눌린 순간에 시작해야 허용되므로
   기다리기 전에 넘겨 받는다. 돌려주는 값은 화면에 띄울 안내 문구(비어 있으면 조용히). */
export async function shareImage(blobPromise, filename, title){
  const probe = typeof File === 'function' ? new File([''], filename, { type:'image/png' }) : null;
  const canFile = !!(probe && navigator.share && navigator.canShare && navigator.canShare({ files:[probe] }));
  if (!canFile && navigator.clipboard && typeof ClipboardItem === 'function'){
    try{
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blobPromise })]);
      return '리포트 이미지를 복사했습니다. 붙여넣기(Ctrl/⌘+V)로 공유해 주세요.';
    }catch(e){ /* 아래에서 파일로 저장한다 */ }
  }
  const blob = await blobPromise;
  if (canFile){
    try{
      await navigator.share({ title, files:[new File([blob], filename, { type:'image/png' })] });
      return '공유 창을 열었습니다.';
    }catch(e){
      if (e && e.name === 'AbortError') return '';   /* 사용자가 닫은 것 — 조용히 */
    }
  }
  saveBlob(blob, filename);
  return '이 기기에서는 이미지를 바로 공유할 수 없어 파일로 저장했습니다.';
}
