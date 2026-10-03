import assert from 'node:assert/strict';
import * as fake from './fake_pg/pg.mjs';

process.env.DATABASE_URL='postgres://u:p@h:5432/feedit';
delete process.env.BACKEND_API_URL;
const products=(await import('../api/products.js')).default;
const response=()=>({statusCode:0,body:null,setHeader(){},end(body){this.body=JSON.parse(body)}});

for(const [gender,own,other] of [
  ['FEMALE','W|F|WOMEN|FEMALE','M|MEN|MALE'],
  ['MALE','M|MEN|MALE','W|F|WOMEN|FEMALE'],
]){
  fake.__setNext({rows:[]});
  const before=fake.CALLS.length;
  const res=response();
  await products({method:'GET',url:`/api/products?style=고프코어&gender=${gender}`},res);
  assert.equal(res.body.status,'empty');
  const calls=fake.CALLS.slice(before);
  assert.equal(calls.length,1);
  assert.match(calls[0].sql,/COALESCE\(NULLIF\(ps\.gender_scope, ''\), p\.gender_scope, ''\) ~\*/);
  assert.ok(calls[0].args[0].includes(own));
  assert.ok(!calls[0].args[0].includes(other));
  assert.ok(calls[0].args[0].includes('UNISEX'));
}
console.log('✅ 상품 성별 분류 조건이 두 성별과 공용 상품을 구분합니다.');
