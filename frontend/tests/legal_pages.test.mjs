/* 하단 링크와 정책 페이지가 빌드 입력에 포함되고 서로 이동 가능한지 확인한다. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

const root=new URL('..',import.meta.url);
const expected=[
  ['/about.html','회사소개'],
  ['/terms.html','이용약관'],
  ['/privacy.html','개인정보처리방침'],
  ['/support.html','고객센터'],
];
const main=new JSDOM(fs.readFileSync(new URL('../index.html',import.meta.url),'utf8'));
const footer=main.window.document.querySelector('.mFoot');
assert.ok(footer,'메인 서비스 하단에 푸터가 있어야 한다');
for(const [href,label] of expected){
  const link=[...footer.querySelectorAll('a')].find(a=>a.getAttribute('href')===href);
  assert.equal(link?.textContent.trim(),label,`${label} 링크가 있어야 한다`);
  const file=new URL('../public'+href,import.meta.url);
  assert.ok(fs.existsSync(file),`${href} 페이지가 있어야 한다`);
  const page=new JSDOM(fs.readFileSync(file,'utf8'));
  assert.ok(page.window.document.querySelector('h1'),`${href}에 제목이 있어야 한다`);
  assert.ok(page.window.document.querySelector('.legalLogo svg'),`${href}에 서비스 심볼 로고가 있어야 한다`);
  assert.equal(page.window.document.querySelectorAll('.legalFooter a').length,4,`${href} 하단에서 공개 중인 안내 페이지로 이동할 수 있어야 한다`);
}
assert.equal(footer.textContent.includes('제휴제안'),false,'보류 중인 제휴제안은 메인 푸터에 노출하지 않아야 한다');
assert.ok(fs.existsSync(new URL('../public/partnership.html',import.meta.url)),'제휴제안 초안은 나중에 다시 공개할 수 있게 보존한다');
for(const name of ['about.html','partnership.html','terms.html','privacy.html','support.html']){
  const source=fs.readFileSync(new URL('../public/'+name,import.meta.url),'utf8');
  assert.equal(source.includes('skn31final4team@gmail.com'),false,`${name}에서 이전 이메일을 숨겨야 한다`);
  assert.equal(source.includes('mailto:'),false,`${name}에서 임시 이메일 링크를 제거해야 한다`);
}
console.log('✅ 메인 푸터에는 공개 중인 4개 안내만 보이고 제휴제안 초안은 보존됩니다.');
