/* 챗봇 근거 링크 중 실제 YouTube 영상만 앱 안의 플레이어로 표시한다.
 *
 * 한 영상에서 나온 근거(설명문·댓글 등)는 카드 하나로 묶는다.
 * 썸네일은 작게 왼쪽에 두고, 근거 문장은 오른쪽에 줄지어 적는다.
 * 재생을 누르면 그때만 플레이어를 불러오고 카드가 넓게 펼쳐진다 (chat_popup.js). */
const esc = value => String(value ?? '').replace(/[&<>"']/g, char =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

export function youtubeVideoId(value){
  let url;
  try { url = new URL(String(value || '')); } catch { return null; }
  if(!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.port) return null;
  const host = url.hostname.toLowerCase();
  let id = null;
  if(host === 'youtu.be') id = url.pathname.slice(1);
  else if(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com',
           'youtube-nocookie.com', 'www.youtube-nocookie.com'].includes(host)){
    const parts = url.pathname.split('/').filter(Boolean);
    if(parts[0] === 'watch' && parts.length === 1) id = url.searchParams.get('v');
    else if(['shorts', 'embed', 'live'].includes(parts[0]) && parts.length === 2) id = parts[1];
  }
  return /^[A-Za-z0-9_-]{11}$/.test(id || '') ? id : null;
}

/* 서버 근거의 종류 코드를 화면 말로 바꾼다. 모르는 값은 그대로 보여 준다. */
const KIND_LABEL = { TITLE:'제목', DESCRIPTION:'설명', COMMENT:'댓글', TRANSCRIPT:'자막', CAPTION:'자막' };
export function videoKindLabel(kind){
  const raw = String(kind || '').trim();
  return KIND_LABEL[raw.toUpperCase()] || raw;
}
const KIND_ORDER = { 제목:0, 설명:1 };

/* 같은 영상의 근거를 한 묶음으로 — 순서는 처음 나온 자리를 따른다.
 * 영상이 아닌 근거는 혼자 한 묶음이다. 같은 영상 안에서 같은 문장은 한 번만 남긴다. */
export function groupVideoEvidence(list){
  const groups = [], byId = new Map();
  for(const item of list || []){
    const id = youtubeVideoId(item?.url);
    if(!id){ groups.push({ video:null, items:[item] }); continue; }
    let group = byId.get(id);
    if(!group){ group = { video:id, items:[] }; byId.set(id, group); groups.push(group); }
    const body = String(item.body || '').trim();
    if(!group.items.some(x => String(x.body || '').trim() === body)) group.items.push(item);
  }
  for(const group of groups){
    if(!group.video) continue;
    group.items = group.items
      .map((item, i) => ({ item, i, rank: KIND_ORDER[videoKindLabel(item.kind)] ?? 2 }))
      .sort((a, b) => a.rank - b.rank || a.i - b.i)
      .map(x => x.item);
  }
  return groups;
}

const PLAY_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8.5 5.8v12.4a.6.6 0 0 0 .9.5l10-6.2a.6.6 0 0 0 0-1L9.4 5.3a.6.6 0 0 0-.9.5Z"/></svg>';

/* notes: [{label, text, meta}] — 없으면 title 한 줄을 근거로 쓴다. */
export function chatVideoHTML({url, title, source = 'YOUTUBE', meta = '', no = '', notes = null}){
  const id = youtubeVideoId(url);
  if(!id) return '';
  const watch = `https://www.youtube.com/watch?v=${id}`;
  const list = (notes && notes.length ? notes : [{ label:'', text:title || '영상 보기', meta }])
    .filter(n => String(n.text || '').trim());
  const label = String(list[0]?.text || title || '영상 보기').replace(/\s+/g, ' ').slice(0, 80);
  const count = list.length > 1 ? '<span class="chatVideoCount">근거 ' + list.length + '건</span>' : '';
  return '<div class="chatVideoWrap"><article class="chatVideo" data-video-id="' + id + '" data-title="' + esc(label) + '">' +
    '<div class="chatVideoScreen">' +
      '<button type="button" class="chatVideoPlay" data-chat-video-play aria-label="' + esc(label) + ' 재생">' +
        '<img src="https://i.ytimg.com/vi/' + id + '/hqdefault.jpg" alt="" loading="lazy" decoding="async">' +
        '<span class="chatVideoPlayIcon" aria-hidden="true">' + PLAY_ICON + '</span>' +
      '</button>' +
    '</div>' +
    '<div class="chatVideoInfo">' +
      '<p class="chatVideoHead">' +
        (no ? '<span class="chatVideoNo">' + esc(no) + '</span>' : '') +
        '<span class="chatVideoSource">' + esc(source) + '</span>' + count +
      '</p>' +
      '<ul class="chatVideoNotes">' + list.map(n =>
        '<li>' +
          (n.label ? '<span class="chatVideoTag">' + esc(n.label) + '</span>' : '') +
          '<p class="chatVideoText" title="' + esc(n.text) + '">' + esc(n.text) + '</p>' +
          (n.meta ? '<span class="chatVideoMeta">' + esc(n.meta) + '</span>' : '') +
        '</li>').join('') +
      '</ul>' +
      '<div class="chatVideoActions">' +
        '<button type="button" data-chat-video-fullscreen title="전체화면으로 보기">전체화면</button>' +
        '<a href="' + watch + '" target="_blank" rel="noopener noreferrer">YouTube에서 보기 ↗</a>' +
      '</div>' +
    '</div>' +
  '</article></div>';
}
