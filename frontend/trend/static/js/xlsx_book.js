/* ══════════════════════════════════════════════════════
   서식 있는 엑셀(.xlsx) — EDIT 지표 내려받기용 (2026-10-02)

   report_export.js 의 buildXlsx 는 값만 담는 맨 시트다.
   EDIT 6탭(언급량·온도 / 연관어 / 긍부정 / 수명주기 / 할인률 변화 / 리세일 지수)은
   기획 리포트 양식(제목 · 지표 카드 · 어두운 표 머리 · 코랄 해석 칸 · 차트)으로 내보내야 해서
   글꼴 · 채우기 · 테두리 · 병합 · 틀 고정 · 차트까지 직접 쓴다. 바깥 라이브러리는 쓰지 않는다.

   쓰는 법
     const b = new Book();
     const s = b.sheet('01_요약', { widths:[18,18,…], freeze:7 });
     s.put(r, c, 값, 스타일, 높이)   ← r·c 는 0부터
     s.merge(r1, c1, r2, c2, 스타일)
     s.chart({ type:'line', title, cat:[c, r1, r2], series:[{name, col, color}], at:[c1, r1, c2, r2] })
     saveBlob(b.blob(), 'x.xlsx')
   ══════════════════════════════════════════════════════ */
import { colName, utf8, zipStore } from './report_export.js';

/* XML 에 들어갈 수 없는 제어 문자까지 걸러 낸다 — 리뷰 원문에 섞여 들어오면 파일이 안 열린다 */
const esc = v => String(v == null ? '' : v)
  .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const ref = (r, c) => colName(c) + (r + 1);
const absRef = (sheet, c, r1, r2) =>
  "'" + sheet.replace(/'/g, "''") + "'!$" + colName(c) + '$' + (r1 + 1) + ':$' + colName(c) + '$' + (r2 + 1);

/* ── 팔레트 — 화면(tokens.css)과 첨부 양식의 색을 그대로 쓴다 ── */
export const C = {
  ink:'1D1B18', muted:'77716A', coral:'FF6B4A', line:'DDD7D0', headLine:'5B5751',
  blue:'4277B8', green:'1F9D73', red:'C94A4A', tint:'FFF0EB', white:'FFFFFF', amber:'C98A1B',
};

/* ── 자주 쓰는 칸 모양 ── */
export const ST = {
  title:  { font:{ b:1, sz:16, color:C.ink } },
  sub:    { font:{ sz:10, color:C.muted }, wrap:1 },
  kLabel: { font:{ sz:9, color:C.muted }, fill:C.white, border:{ t:C.line, l:C.line, r:C.line } },
  kValue: color => ({ font:{ b:1, sz:16, color:color || C.ink }, fill:C.white, border:{ l:C.line, r:C.line } }),
  kNote:  { font:{ sz:8, color:C.coral }, fill:C.white, border:{ b:C.line, l:C.line, r:C.line } },
  secDark:  { font:{ b:1, sz:10, color:C.white }, fill:C.ink },
  secCoral: { font:{ b:1, sz:10, color:C.white }, fill:C.coral },
  note:   { font:{ sz:10, color:C.ink }, fill:C.tint, wrap:1 },
  th:     { font:{ b:1, sz:9, color:C.white }, fill:C.ink, h:'center', border:{ l:C.headLine, r:C.headLine } },
  td:     { font:{ sz:9, color:C.ink }, fill:C.white, border:{ t:C.line, b:C.line } },
  tdWrap: { font:{ sz:9, color:C.ink }, fill:C.white, border:{ t:C.line, b:C.line }, wrap:1 },
  link:   { font:{ sz:9, color:C.blue } },
  small:  { font:{ sz:9, color:C.muted } },
};
export const withFmt = (st, fmt) => Object.assign({}, st, { fmt });

/* ── 스타일 등록부 — 같은 모양은 한 번만 쓴다 ── */
class Styles {
  constructor(){
    this.fonts = ['<font><sz val="10"/><color rgb="FF' + C.ink + '"/><name val="Arial"/></font>'];
    this.fills = ['<fill><patternFill patternType="none"/></fill>', '<fill><patternFill patternType="gray125"/></fill>'];
    this.borders = ['<border><left/><right/><top/><bottom/><diagonal/></border>'];
    this.fmts = [];
    this.xfs = ['<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment vertical="center"/></xf>'];
    this.idx = { font:{}, fill:{}, border:{}, fmt:{}, xf:{} };
  }
  _one(kind, list, key, xml){
    if (this.idx[kind][key] == null){ this.idx[kind][key] = list.length; list.push(xml) }
    return this.idx[kind][key];
  }
  id(st){
    if (!st) return 0;
    const key = JSON.stringify(st);
    if (this.idx.xf[key] != null) return this.idx.xf[key];
    const f = st.font || {};
    const fontId = this._one('font', this.fonts, JSON.stringify(f),
      '<font>' + (f.b ? '<b/>' : '') + '<sz val="' + (f.sz || 10) + '"/><color rgb="FF' + (f.color || C.ink) +
      '"/><name val="Arial"/></font>');
    const fillId = st.fill ? this._one('fill', this.fills, st.fill,
      '<fill><patternFill patternType="solid"><fgColor rgb="FF' + st.fill + '"/><bgColor indexed="64"/></patternFill></fill>') : 0;
    const b = st.border || {};
    const side = (tag, col) => col ? '<' + tag + ' style="thin"><color rgb="FF' + col + '"/></' + tag + '>' : '<' + tag + '/>';
    const borderId = st.border ? this._one('border', this.borders, JSON.stringify(b),
      '<border>' + side('left', b.l) + side('right', b.r) + side('top', b.t) + side('bottom', b.b) + '<diagonal/></border>') : 0;
    const fmtId = st.fmt ? this._one('fmt', this.fmts, st.fmt,
      '<numFmt numFmtId="' + (164 + this.fmts.length) + '" formatCode="' + esc(st.fmt) + '"/>') + 164 : 0;
    const align = '<alignment vertical="center"' + (st.h ? ' horizontal="' + st.h + '"' : '') + (st.wrap ? ' wrapText="1"' : '') + '/>';
    const id = this.xfs.length;
    this.xfs.push('<xf numFmtId="' + fmtId + '" fontId="' + fontId + '" fillId="' + fillId + '" borderId="' + borderId +
      '" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1" applyAlignment="1">' + align + '</xf>');
    this.idx.xf[key] = id;
    return id;
  }
  xml(){
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
      (this.fmts.length ? '<numFmts count="' + this.fmts.length + '">' + this.fmts.join('') + '</numFmts>' : '') +
      '<fonts count="' + this.fonts.length + '">' + this.fonts.join('') + '</fonts>' +
      '<fills count="' + this.fills.length + '">' + this.fills.join('') + '</fills>' +
      '<borders count="' + this.borders.length + '">' + this.borders.join('') + '</borders>' +
      '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>' +
      '<cellXfs count="' + this.xfs.length + '">' + this.xfs.join('') + '</cellXfs>' +
      '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>' +
      '</styleSheet>';
  }
}

/* ── 시트 ── */
class Sheet {
  constructor(book, name, { widths = [], freeze = 0 } = {}){
    this.book = book; this.name = name.slice(0, 31);
    this.widths = widths; this.freeze = freeze;
    this.rows = new Map(); this.heights = new Map();
    this.merges = []; this.charts = [];
  }
  /* v 가 숫자면 숫자 칸, 아니면 글자 칸. 빈 값도 스타일(테두리·채우기)은 남긴다 */
  put(r, c, v, st, h){
    if (!this.rows.has(r)) this.rows.set(r, new Map());
    this.rows.get(r).set(c, { v, s:this.book.styles.id(st) });
    if (h) this.height(r, h);
    return this;
  }
  height(r, h){ this.heights.set(r, h); return this }
  /* 병합 — 범위 안 모든 칸에 같은 스타일을 깔아야 테두리가 끊기지 않는다 */
  merge(r1, c1, r2, c2, st){
    const head = this._val(r1, c1);
    for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++)
      this.put(r, c, r === r1 && c === c1 ? head : '', st);
    if (r1 !== r2 || c1 !== c2) this.merges.push(ref(r1, c1) + ':' + ref(r2, c2));
    return this;
  }
  /* 차트 — 값은 이 시트의 칸을 가리킨다(cat=[열, 시작행, 끝행], series[].col).
     캐시(이미 계산된 값)도 함께 넣어 엑셀이 아닌 뷰어(Numbers · 미리보기)에서도 그림이 보이게 한다. */
  chart(opt){ this.charts.push(opt); return this }
  _val(r, c){ const row = this.rows.get(r), x = row && row.get(c); return x ? x.v : null }
  xml(rels){
    const cols = this.widths.length ? '<cols>' + this.widths.map((w, i) =>
      '<col min="' + (i + 1) + '" max="' + (i + 1) + '" width="' + w + '" customWidth="1"/>').join('') + '</cols>' : '';
    const keys = [...new Set([...this.rows.keys(), ...this.heights.keys()])].sort((a, b) => a - b);
    const body = keys.map(r => {
      const h = this.heights.get(r), cells = this.rows.get(r) || new Map();
      return '<row r="' + (r + 1) + '"' + (h ? ' ht="' + h + '" customHeight="1"' : '') + '>' +
        [...cells.keys()].sort((a, b) => a - b).map(c => {
          const { v, s } = cells.get(c), at = ref(r, c), sa = s ? ' s="' + s + '"' : '';
          if (typeof v === 'number' && isFinite(v)) return '<c r="' + at + '"' + sa + '><v>' + v + '</v></c>';
          if (v == null || v === '') return '<c r="' + at + '"' + sa + '/>';
          return '<c r="' + at + '"' + sa + ' t="inlineStr"><is><t xml:space="preserve">' + esc(v) + '</t></is></c>';
        }).join('') + '</row>';
    }).join('');
    const pane = this.freeze
      ? '<pane ySplit="' + this.freeze + '" topLeftCell="A' + (this.freeze + 1) + '" activePane="bottomLeft" state="frozen"/>' : '';
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' +
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
      '<sheetViews><sheetView showGridLines="0" workbookViewId="0">' + pane + '</sheetView></sheetViews>' +
      '<sheetFormatPr defaultRowHeight="15"/>' + cols + '<sheetData>' + body + '</sheetData>' +
      (this.merges.length ? '<mergeCells count="' + this.merges.length + '">' +
        this.merges.map(m => '<mergeCell ref="' + m + '"/>').join('') + '</mergeCells>' : '') +
      '<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>' +
      (rels ? '<drawing r:id="rId1"/>' : '') + '</worksheet>';
  }
}

/* ── 차트 XML ── */
const A_NS = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"';
const txPr = sz => '<c:txPr><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="' + sz + '"><a:solidFill><a:srgbClr val="' +
  C.muted + '"/></a:solidFill></a:defRPr></a:pPr><a:endParaRPr lang="ko-KR"/></a:p></c:txPr>';
const grid = '<c:majorGridlines><c:spPr><a:ln w="9525"><a:solidFill><a:srgbClr val="E4DFD8"/></a:solidFill>' +
  '<a:prstDash val="dash"/></a:ln></c:spPr></c:majorGridlines>';
const axLine = '<c:spPr><a:ln w="9525"><a:solidFill><a:srgbClr val="' + C.line + '"/></a:solidFill></a:ln></c:spPr>';

function chartXML(sheet, o){
  const [cc, r1, r2] = o.cat;
  const n = r2 - r1 + 1;
  const strCache = c => '<c:strCache><c:ptCount val="' + n + '"/>' + Array.from({ length:n }, (_, i) => {
    const v = sheet._val(r1 + i, c); return v == null ? '' : '<c:pt idx="' + i + '"><c:v>' + esc(v) + '</c:v></c:pt>';
  }).join('') + '</c:strCache>';
  const numCache = c => '<c:numCache><c:formatCode>General</c:formatCode><c:ptCount val="' + n + '"/>' +
    Array.from({ length:n }, (_, i) => {
      const v = sheet._val(r1 + i, c);
      return typeof v === 'number' && isFinite(v) ? '<c:pt idx="' + i + '"><c:v>' + v + '</c:v></c:pt>' : '';
    }).join('') + '</c:numCache>';
  const bar = o.type === 'bar';
  const ser = o.series.map((s, i) => {
    const fill = '<a:solidFill><a:srgbClr val="' + (s.color || C.coral) + '"/></a:solidFill>';
    return '<c:ser><c:idx val="' + i + '"/><c:order val="' + i + '"/><c:tx><c:v>' + esc(s.name) + '</c:v></c:tx>' +
      (bar ? '<c:spPr>' + fill + '</c:spPr><c:invertIfNegative val="0"/>'
           : '<c:spPr><a:ln w="22225" cap="rnd">' + fill + '<a:round/></a:ln></c:spPr><c:marker><c:symbol val="none"/></c:marker>') +
      '<c:cat><c:strRef><c:f>' + esc(absRef(sheet.name, cc, r1, r2)) + '</c:f>' + strCache(cc) + '</c:strRef></c:cat>' +
      '<c:val><c:numRef><c:f>' + esc(absRef(sheet.name, s.col, r1, r2)) + '</c:f>' + numCache(s.col) + '</c:numRef></c:val>' +
      (bar ? '' : '<c:smooth val="0"/>') + '</c:ser>';
  }).join('');
  const plot = bar
    ? '<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:varyColors val="0"/>' + ser +
      '<c:gapWidth val="70"/><c:axId val="101"/><c:axId val="102"/></c:barChart>'
    : '<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>' + ser +
      '<c:marker val="1"/><c:axId val="101"/><c:axId val="102"/></c:lineChart>';
  const scaling = '<c:scaling><c:orientation val="minMax"/>' +
    (o.max != null ? '<c:max val="' + o.max + '"/>' : '') + (o.min != null ? '<c:min val="' + o.min + '"/>' : '') + '</c:scaling>';
  return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" ' + A_NS + ' ' +
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
    '<c:roundedCorners val="0"/><c:chart>' +
    '<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="1000" b="1"/></a:pPr><a:r>' +
      '<a:rPr lang="ko-KR" sz="1000" b="1"><a:solidFill><a:srgbClr val="' + C.ink + '"/></a:solidFill></a:rPr>' +
      '<a:t>' + esc(o.title) + '</a:t></a:r></a:p></c:rich></c:tx><c:overlay val="0"/></c:title>' +
    '<c:autoTitleDeleted val="0"/><c:plotArea><c:layout/>' + plot +
    '<c:catAx><c:axId val="101"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/>' +
      '<c:axPos val="b"/><c:numFmt formatCode="General" sourceLinked="0"/><c:majorTickMark val="none"/>' +
      '<c:minorTickMark val="none"/><c:tickLblPos val="low"/>' + axLine + txPr(700) +
      '<c:crossAx val="102"/><c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/>' +
      '<c:lblOffset val="100"/><c:noMultiLvlLbl val="0"/></c:catAx>' +
    '<c:valAx><c:axId val="102"/>' + scaling + '<c:delete val="0"/><c:axPos val="l"/>' + grid +
      '<c:numFmt formatCode="' + esc(o.fmt || 'General') + '" sourceLinked="0"/><c:majorTickMark val="none"/>' +
      '<c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:spPr><a:ln><a:noFill/></a:ln></c:spPr>' + txPr(700) +
      '<c:crossAx val="101"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx>' +
    '<c:spPr><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr></c:plotArea>' +
    (o.series.length > 1 ? '<c:legend><c:legendPos val="t"/><c:overlay val="0"/>' + txPr(750) + '</c:legend>' : '') +
    '<c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart>' +
    '<c:spPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:ln w="9525"><a:solidFill><a:srgbClr val="' +
      C.line + '"/></a:solidFill></a:ln></c:spPr>' +
    '</c:chartSpace>';
}

function drawingXML(charts, base){
  return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" ' + A_NS + '>' +
    charts.map((o, i) => {
      const [c1, r1, c2, r2] = o.at;
      return '<xdr:twoCellAnchor editAs="oneCell">' +
        '<xdr:from><xdr:col>' + c1 + '</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>' + r1 + '</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>' +
        '<xdr:to><xdr:col>' + c2 + '</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>' + r2 + '</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>' +
        '<xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="' + (base + i + 2) + '" name="Chart ' + (i + 1) + '"/>' +
        '<xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr><xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>' +
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">' +
        '<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" ' +
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId' + (i + 1) + '"/>' +
        '</a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>';
    }).join('') + '</xdr:wsDr>';
}

const REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships';
const OFF = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/';
const rels = list => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="' + REL_NS + '">' +
  list.map((t, i) => '<Relationship Id="rId' + (i + 1) + '" Type="' + OFF + t[0] + '" Target="' + t[1] + '"/>').join('') +
  '</Relationships>';

export class Book {
  constructor(){ this.styles = new Styles(); this.sheets = [] }
  sheet(name, opt){ const s = new Sheet(this, name, opt); this.sheets.push(s); return s }
  blob(){
    const files = [], types = [];
    let chartNo = 0, drawNo = 0;
    this.sheets.forEach((s, i) => {
      const n = i + 1;
      types.push(['/xl/worksheets/sheet' + n + '.xml', 'spreadsheetml.worksheet+xml']);
      if (s.charts.length){
        drawNo++;
        const chartRels = s.charts.map(o => {
          chartNo++;
          files.push({ name:'xl/charts/chart' + chartNo + '.xml', data:utf8(chartXML(s, o)) });
          types.push(['/xl/charts/chart' + chartNo + '.xml', 'drawingml.chart+xml']);
          return ['chart', '../charts/chart' + chartNo + '.xml'];
        });
        files.push({ name:'xl/drawings/drawing' + drawNo + '.xml', data:utf8(drawingXML(s.charts, chartNo * 10)) });
        files.push({ name:'xl/drawings/_rels/drawing' + drawNo + '.xml.rels', data:utf8(rels(chartRels)) });
        files.push({ name:'xl/worksheets/_rels/sheet' + n + '.xml.rels',
          data:utf8(rels([['drawing', '../drawings/drawing' + drawNo + '.xml']])) });
        types.push(['/xl/drawings/drawing' + drawNo + '.xml', 'drawing+xml']);
      }
      files.push({ name:'xl/worksheets/sheet' + n + '.xml', data:utf8(s.xml(!!s.charts.length)) });
    });
    const head = [
      { name:'[Content_Types].xml', data:utf8('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
        '<Default Extension="xml" ContentType="application/xml"/>' +
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
        types.map(t => '<Override PartName="' + t[0] + '" ContentType="application/vnd.openxmlformats-officedocument.' + t[1] + '"/>').join('') +
        '</Types>') },
      { name:'_rels/.rels', data:utf8(rels([['officeDocument', 'xl/workbook.xml']])) },
      { name:'xl/workbook.xml', data:utf8('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="' + OFF.slice(0, -1) + '">' +
        '<bookViews><workbookView activeTab="0"/></bookViews><sheets>' +
        this.sheets.map((s, i) => '<sheet name="' + esc(s.name) + '" sheetId="' + (i + 1) + '" r:id="rId' + (i + 1) + '"/>').join('') +
        '</sheets></workbook>') },
      { name:'xl/_rels/workbook.xml.rels', data:utf8(rels(
        this.sheets.map((_, i) => ['worksheet', 'worksheets/sheet' + (i + 1) + '.xml']).concat([['styles', 'styles.xml']]))) },
      { name:'xl/styles.xml', data:utf8(this.styles.xml()) },
    ];
    return new Blob([zipStore(head.concat(files))], {
      type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
  }
}
