/* 스타일 상세의 상품 카드가 DB API 응답으로 그려지는지 확인한다. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
const W = new URL('..', import.meta.url).href.replace(/\/$/, '');
const { styleProductsURL, styleProductCard } = await import(`${W}/style/static/js/products.js`);

let pass=0, fail=0;
const t=(name,fn)=>{ try{ fn(); console.log('✅',name); pass++ }
  catch(e){ console.log('❌',name,'\n   ',e.message); fail++ } };

t('스타일명과 페이징을 상품 API에 넘긴다',()=>{
  const u=new URL(styleProductsURL('고프코어',16,16),'http://localhost');
  assert.equal(u.pathname,'/api/products');
  assert.equal(u.searchParams.get('style'),'고프코어');
  assert.equal(u.searchParams.get('offset'),'16');
  assert.equal(u.searchParams.get('limit'),'16');
});

t('아이템 카테고리는 페이지를 자르기 전에 상품 API로 넘긴다',()=>{
  const u=new URL(styleProductsURL('고프코어',0,24,'recommend','outer'),'http://localhost');
  assert.equal(u.searchParams.get('category_group'),'outer');
  assert.equal(u.searchParams.get('sort'),'recommend');
  const all=new URL(styleProductsURL('고프코어',0,24,'recommend','all'),'http://localhost');
  assert.equal(all.searchParams.has('category_group'),false);
});

t('DB 상품의 이미지·브랜드·가격·링크를 카드로 옮긴다',()=>{
  const card=styleProductCard({
    id:3,product_source_id:17,image:'https://img.example/17.jpg',
    brand:'테스트 브랜드',name:'셋 자켓',url:'https://shop.example/17',
    price:{list:199000,sale:129000},category:'자켓'
  },'고프코어');
  assert.deepEqual(card,{
    id:'db-17',img:'https://img.example/17.jpg',br:'테스트 브랜드',
    nm:'셋 자켓',pr:'129,000원',url:'https://shop.example/17',
    /* 찜한 키워드 화면용 부가 정보 */
    styleName:'고프코어',cat:'자켓',price:129000,listPrice:199000
  });
});

t('없는 가격과 이미지를 목업으로 지어내지 않는다',()=>{
  const card=styleProductCard({id:4,product_source_id:18,name:'티셔츠',price:{}});
  assert.equal(card.img,'');
  assert.equal(card.pr,'가격 정보 없음');
  const renderer=fs.readFileSync(new URL('../home/static/js/chat.js',import.meta.url),'utf8');
  assert.match(renderer,/이미지 없음/);
  assert.match(renderer,/cardEsc\(o\.nm\)/);
});

t('백엔드는 스타일을 연결 표에서만 읽는다 (단일 FK 는 없어졌다)',()=>{
  const src=fs.readFileSync(new URL('../../backend/apps/api/views.py',import.meta.url),'utf8');
  assert.match(src,/ProductTerm\.objects\.filter\(term__term_type="STYLE"/);
  /* commerce.product.style_id 는 DB 에서 떨어져 나갔다 — 다시 바라보면 조회가 통째로 500 이 난다 */
  assert.ok(!/product__style__term/.test(src),'없어진 단일 스타일 FK 를 참조하면 안 된다');
  assert.match(src,/"thumbnail_url"/);
});

console.log(`\n${pass}개 통과 · ${fail}개 실패`);
process.exit(fail?1:0);
