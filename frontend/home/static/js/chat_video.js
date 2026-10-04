/* 챗봇 근거 링크 중 실제 YouTube 영상만 앱 안의 플레이어로 표시한다. */
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

export function chatVideoHTML({url, title, source = 'YOUTUBE', meta = ''}){
  const id = youtubeVideoId(url);
  if(!id) return '';
  const watch = `https://www.youtube.com/watch?v=${id}`;
  const label = String(title || '영상 보기');
  return '<article class="chatVideo" data-video-id="' + id + '">' +
    '<div class="chatVideoScreen">' +
      '<button type="button" class="chatVideoPlay" data-chat-video-play aria-label="' + esc(label) + ' 재생">' +
        '<img src="https://i.ytimg.com/vi/' + id + '/hqdefault.jpg" alt="" loading="lazy">' +
        '<span class="chatVideoPlayIcon" aria-hidden="true">▶</span><span class="chatVideoPlayText">영상 재생</span>' +
      '</button>' +
    '</div>' +
    '<div class="chatVideoInfo"><div class="chatVideoCopy">' +
      '<span class="chatVideoSource">' + esc(source) + '</span>' +
      '<strong>' + esc(label) + '</strong>' +
      (meta ? '<span class="chatVideoMeta">' + esc(meta) + '</span>' : '') +
    '</div><div class="chatVideoActions">' +
      '<button type="button" data-chat-video-fullscreen title="전체화면으로 보기">전체화면</button>' +
      '<a href="' + watch + '" target="_blank" rel="noopener noreferrer">YouTube에서 보기 ↗</a>' +
    '</div></div>' +
  '</article>';
}
