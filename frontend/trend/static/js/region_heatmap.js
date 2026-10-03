/* ══════════════════════════════════════════════════════
   시·도별 관심도 — 지도 히트맵 (2026-09-23)

   값(TermSearchRegion.value)은 '그 시·도 검색량 대비 비율' 0~100 이다.
   숫자를 세 개만 줄글로 적던 것을 지도 위 '온도'로 바꿨다 —
   관심이 높은 시·도일수록 붉게, 낮을수록 파랗게 깔린다.

   · 지도는 Leaflet + leaflet.heat (CDN). 처음 그릴 때 한 번만 받아 둔다.
   · 한 시·도에 점 하나만 찍으면 도청 자리에 점 하나가 뜬다 —
     시·도마다 퍼짐 반경(spread)을 두고 그 안에 점을 흩뿌려 면으로 덮는다.
   · 못 알아본 지역 이름은 조용히 버리지 않고 카드 아래 적는다.
     (구글이 주는 이름이 바뀌면 지도가 비는데, 이유를 모르면 못 고친다)
   ══════════════════════════════════════════════════════ */

const LEAFLET_CSS = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css';
const LEAFLET_JS  = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
const HEAT_JS     = 'https://cdnjs.cloudflare.com/ajax/libs/leaflet.heat/0.2.0/leaflet-heat.js';

/* 17개 시·도 — [위도, 경도, 퍼짐 반경(도 단위)].
   반경은 행정구역 넓이에 대충 맞춘 값이다(경기·경북은 넓고, 특별시는 좁다). */
const SIDO = {
  '서울특별시':       [37.5665, 126.9780, 0.16],
  '부산광역시':       [35.1796, 129.0756, 0.16],
  '대구광역시':       [35.8714, 128.6014, 0.16],
  '인천광역시':       [37.4563, 126.7052, 0.18],
  '광주광역시':       [35.1595, 126.8526, 0.14],
  '대전광역시':       [36.3504, 127.3845, 0.13],
  '울산광역시':       [35.5384, 129.3114, 0.15],
  '세종특별자치시':   [36.4800, 127.2890, 0.10],
  '경기도':           [37.4138, 127.5183, 0.52],
  '강원특별자치도':   [37.8228, 128.1555, 0.60],
  '충청북도':         [36.8000, 127.7000, 0.42],
  '충청남도':         [36.5184, 126.8000, 0.42],
  '전북특별자치도':   [35.7175, 127.1530, 0.40],
  '전라남도':         [34.8679, 126.9910, 0.48],
  '경상북도':         [36.4919, 128.8889, 0.62],
  '경상남도':         [35.4606, 128.2132, 0.50],
  '제주특별자치도':   [33.4996, 126.5312, 0.22],
};
/* 구글이 주는 이름이 해마다 바뀐다(강원도 → 강원특별자치도, 영문 표기 등).
   들어오는 이름을 위 표의 열쇠로 옮긴다. */
const ALIAS = {
  '서울':'서울특별시','서울시':'서울특별시','Seoul':'서울특별시',
  '부산':'부산광역시','Busan':'부산광역시','Pusan':'부산광역시',
  '대구':'대구광역시','Daegu':'대구광역시',
  '인천':'인천광역시','Incheon':'인천광역시',
  '광주':'광주광역시','Gwangju':'광주광역시',
  '대전':'대전광역시','Daejeon':'대전광역시',
  '울산':'울산광역시','Ulsan':'울산광역시',
  '세종':'세종특별자치시','세종시':'세종특별자치시','Sejong':'세종특별자치시',
  '경기':'경기도','Gyeonggi-do':'경기도','Gyeonggi':'경기도',
  '강원':'강원특별자치도','강원도':'강원특별자치도','Gangwon-do':'강원특별자치도','Gangwon':'강원특별자치도',
  '충북':'충청북도','North Chungcheong':'충청북도','Chungcheongbuk-do':'충청북도',
  '충남':'충청남도','South Chungcheong':'충청남도','Chungcheongnam-do':'충청남도',
  '전북':'전북특별자치도','전라북도':'전북특별자치도','North Jeolla':'전북특별자치도','Jeollabuk-do':'전북특별자치도',
  '전남':'전라남도','South Jeolla':'전라남도','Jeollanam-do':'전라남도',
  '경북':'경상북도','North Gyeongsang':'경상북도','Gyeongsangbuk-do':'경상북도',
  '경남':'경상남도','South Gyeongsang':'경상남도','Gyeongsangnam-do':'경상남도',
  '제주':'제주특별자치도','제주도':'제주특별자치도','Jeju':'제주특별자치도','Jeju-do':'제주특별자치도',
};
function sidoOf(name){
  const raw = String(name || '').trim();
  if (!raw) return null;
  if (SIDO[raw]) return raw;
  if (ALIAS[raw]) return ALIAS[raw];
  /* '경기도 ' 처럼 뒤에 뭐가 붙어 와도 앞부분으로 한 번 더 본다 */
  for (const key of Object.keys(SIDO)) if (raw.indexOf(key) === 0) return key;
  for (const key of Object.keys(ALIAS)) if (raw.indexOf(key) === 0) return ALIAS[key];
  return null;
}

/* 외부 파일은 한 번만 받는다 — 탭을 오갈 때마다 다시 받지 않게 약속을 캐시한다 */
let leafletReady = null;
function loadOnce(){
  if (leafletReady) return leafletReady;
  leafletReady = new Promise((resolve, reject) => {
    if (window.L && window.L.heatLayer) { resolve(); return }
    const css = document.createElement('link');
    css.rel = 'stylesheet'; css.href = LEAFLET_CSS;
    document.head.appendChild(css);
    const s1 = document.createElement('script');
    s1.src = LEAFLET_JS;
    s1.onload = () => {
      const s2 = document.createElement('script');
      s2.src = HEAT_JS;
      s2.onload = resolve;
      s2.onerror = () => reject(new Error('히트맵 라이브러리를 받지 못했습니다.'));
      document.head.appendChild(s2);
    };
    s1.onerror = () => reject(new Error('지도 라이브러리를 받지 못했습니다.'));
    document.head.appendChild(s1);
  }).catch(e => { leafletReady = null; throw e });
  return leafletReady;
}

/* 시·도 하나를 점 무리로 펼친다 — 중심이 제일 뜨겁고 가장자리로 갈수록 식는다.
   난수를 쓰면 다시 그릴 때마다 모양이 흔들려서, 각도·반경을 고정해 둔다. */
function spread(lat, lng, r, weight){
  const pts = [[lat, lng, weight]];
  const RINGS = [[0.45, 6, 0.75], [0.8, 10, 0.45]];   /* [반경비, 점 수, 세기비] */
  RINGS.forEach(([rr, n, w]) => {
    for (let i = 0; i < n; i++){
      const a = (Math.PI * 2 * i) / n + rr;           /* 고리마다 조금 돌려 격자무늬를 피한다 */
      /* 경도는 위도가 올라갈수록 좁아진다 — 위도 37도에서 약 1.25배 */
      pts.push([lat + Math.sin(a) * r * rr,
                lng + Math.cos(a) * r * rr * 1.25,
                weight * w]);
    }
  });
  return pts;
}

/* 이미 깔린 지도를 정리한다 — 탭을 다시 그리면 DOM 이 통째로 갈려서
   Leaflet 인스턴스가 유령으로 남는다(스크롤·리사이즈 핸들러가 계속 돈다). */
const MAPS = new WeakMap();

export function paintRegionHeat(host, regions){
  if (!host) return;
  const rows = (regions || [])
    .map(r => ({ key: sidoOf(r.region), name: r.region, value: Number(r.value) || 0 }))
    .filter(r => r.value > 0);
  const known = rows.filter(r => r.key);
  const unknown = rows.filter(r => !r.key).map(r => r.name);
  /* ★ 2026-09-23 — 칠할 값이 없다고 해서 지도를 지우지 않는다.
     예전에는 여기서 글자 한 줄만 남기고 끝냈는데, 그러면 자료가 적은 키워드에서
     카드가 통째로 비어 화면이 고장난 것처럼 보였다.
     이제 남한 지도는 늘 서고, 열(熱)만 없는 상태로 둔 뒤 사유를 아래 적는다. */
  const empty = !known.length;
  /* 값이 아예 없을 때의 안내는 카드 각주(trend/static/js/dispatch.js)가 이미 한다 —
     여기서 또 적으면 같은 말이 두 줄로 겹친다. 이름을 못 알아본 경우만 적는다. */
  const why = empty
    ? (unknown.length
        ? '받은 지역 이름을 지도에서 찾지 못했습니다 (' + unknown.slice(0, 5).join(' · ') + ').'
        : '')
    : (known.length < 3
        ? '잡힌 시·도가 ' + known.length + '곳뿐입니다 — 나머지는 자료가 없어 비워 둡니다.'
        : '');
  host.innerHTML = '<div class="rgMapBox' + (empty ? ' isEmpty' : '') + '"><div class="rgMap"></div>' +
    (empty ? '' : '<div class="rgScale"><span>낮음</span><i></i><span>높음</span></div>') + '</div>' +
    (why ? '<div class="rgNote">' + why + '</div>' : '') +
    (!empty && unknown.length ? '<div class="rgNote">지도에 올리지 못한 이름: ' + unknown.join(' · ') + '</div>' : '');
  const el = host.querySelector('.rgMap');

  loadOnce().then(() => {
    if (!el.isConnected) return;                /* 그새 다른 탭으로 갔다 */
    const old = MAPS.get(el); if (old) old.remove();
    const L = window.L;
    const map = L.map(el, {
      zoomControl: false, attributionControl: true,
      scrollWheelZoom: false, dragging: true, doubleClickZoom: false,
      /* 잠글 범위는 아래에서 '맞춘 뒤의 화면 그대로' 로 건다 —
         여기에 숫자를 박아 두면 칸 크기가 바뀔 때마다 어긋난다. */
      maxBoundsViscosity: 1.0,
      /* ★ 줌 단위를 정수로 묶지 않는다(기본 zoomSnap:1).
         정수로 묶으면 fitBounds 가 한 단계 아래로 내려앉아, 요청한 범위보다
         훨씬 넓게 — 바다만 잔뜩 — 잡힌다. 0 이면 칸에 딱 맞는 배율로 선다. */
      zoomSnap: 0,
    });
    MAPS.set(el, map);
    /* ★ 타일은 열쇠 없이 쓸 수 있는 것만 쓴다.
       CARTO(basemaps.cartocdn.com)는 이제 API 키를 요구해서 지도 위에
       'API KEY REQUIRED' 워터마크가 통째로 찍힌다. OSM 기본 타일로 간다.
       detectRetina 를 켜야 고해상도 화면에서 글자가 흐리지 않다. */
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap', maxZoom: 11, minZoom: 6, detectRetina: true,
    }).addTo(map);

    /* 값(0~100)을 그대로 세기로 쓰면 1위만 붉고 나머지가 전부 파래진다.
       제일 높은 시·도를 1.0 으로 두고 나머지를 그 비율로 맞춘다 — '상대 온도'다. */
    if (known.length){
      const max = Math.max.apply(null, known.map(r => r.value)) || 1;
      const pts = [];
      known.forEach(r => {
        const [lat, lng, rad] = SIDO[r.key];
        pts.push.apply(pts, spread(lat, lng, rad, Math.max(0.12, r.value / max)));
      });
      L.heatLayer(pts, {
        radius: 34, blur: 28, max: 1.0, minOpacity: 0.32,
        gradient: { 0.0: '#2b4bff', 0.3: '#22d3ee', 0.5: '#4ade80', 0.7: '#facc15', 0.85: '#fb923c', 1.0: '#ef4444' },
      }).addTo(map);
    }

    /* 고른 시·도만으로 맞추면 한 곳만 있을 때 과하게 당겨진다 — 남한 전체를 기준으로 잡는다.
       범위는 우리 땅 끝까지 담는다:
         남 — 마라도·제주 (33.1N)      북 — 고성 (38.6N)
         서 — 신안·가거도 (125.9E)     동 — 독도 (131.9E, 울릉도 130.9E) */
    map.fitBounds(L.latLngBounds([33.05, 125.95], [38.65, 131.95]), { padding: [6, 6] });
    /* ★ 여기서 잡힌 화면이 곧 보여 줄 전부다.
       맞춘 직후의 범위를 그대로 잠그면, 끌어도 지금 보이는 것 밖은 나오지 않는다.
       (숫자를 박지 않으므로 칸 크기가 달라져도 화면과 잠금이 늘 같다.) */
    map.setMaxBounds(map.getBounds().pad(0.02));
    map.setMinZoom(map.getZoom());
    /* 카드가 접혀 있다가 펴지면 타일이 반만 그려진다 — 한 박자 뒤 다시 잰다 */
    setTimeout(() => map.invalidateSize(), 60);
  }).catch(e => {
    el.parentElement.innerHTML = '<div class="rgNote">지도를 불러오지 못했습니다 (' +
      String(e && e.message || e).replace(/[<>&]/g, '') + ').</div>';
  });
}
