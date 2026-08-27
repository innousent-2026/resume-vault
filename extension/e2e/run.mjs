/**
 * End-to-end check of the extension against a fixture application form.
 *
 * Run it with ./extension/e2e/run.sh, which starts the API, serves
 * fixture.html, and loads the extension into a real Chromium.
 *
 * What it proves: fields are detected and mapped, values are typed into a
 * React-free but realistically-structured form, sensitive fields are left
 * alone, a manual mapping is remembered, the fill is logged — and the form is
 * never submitted.
 */

import pw from 'playwright';
const { chromium } = pw;

const SP = process.env.JAA_E2E_TMP;
const EXT = `${SP}/extension`;
const fail = (msg) => { console.error('FAIL:', msg); process.exitCode = 1; };
const ok = (msg) => console.log('  ok -', msg);

const context = await chromium.launchPersistentContext(`${SP}/profile`, {
  headless: true,
  channel: 'chromium',
  args: [`--disable-extensions-except=${EXT}`, `--load-extension=${EXT}`],
});

const page = await context.newPage();
page.on('console', (m) => { if (m.type() === 'error') console.log('   [page error]', m.text()); });
await page.goto(`${process.env.JAA_E2E_SITE}/fixture.html`);

// The panel lives in a shadow root on #jaa-panel-host.
await page.waitForSelector('#jaa-panel-host', { state: 'attached', timeout: 15000 });
const panel = page.locator('#jaa-panel-host').locator('.wrap');
await panel.waitFor({ timeout: 10000 });
console.log('\n1. Panel renders');
ok(await panel.locator('header h1').innerText());

const summary = await panel.locator('.summary').innerText();
console.log('\n2. Summary:', summary.replace(/\s+/g, ' ').trim());

const rows = await panel.locator('.row[data-row]').all();
const planned = [];
for (const row of rows) {
  planned.push((await row.locator('.canonical').innerText()).split(' ·')[0]);
}
console.log('\n3. Planned fields:', planned.join(', '));
for (const expected of ['first_name', 'last_name', 'email', 'phone', 'linkedin', 'city',
                        'work_authorized', 'requires_sponsorship', 'cover_letter']) {
  planned.includes(expected) ? ok(expected) : fail(`missing planned field ${expected}`);
}
for (const forbidden of ['eeo_gender', 'resume_file']) {
  planned.includes(forbidden) ? fail(`${forbidden} should not be planned`) : ok(`${forbidden} correctly withheld`);
}

console.log('\n4. Highlights on the page');
const highlighted = await page.locator('.jaa-candidate, .jaa-review').count();
highlighted > 0 ? ok(`${highlighted} fields outlined`) : fail('no fields highlighted');

console.log('\n5. Fill selected');
await panel.locator('button[data-act="fill"]').click();
await page.waitForTimeout(500);
const values = await page.evaluate(() => ({
  first: document.querySelector('#fn').value,
  last: document.querySelector('#ln').value,
  email: document.querySelector('#em').value,
  phone: document.querySelector('#ph').value,
  linkedin: document.querySelector('#li').value,
  city: document.querySelector('#city').value,
  auth: document.querySelector('#auth').value,
  spon: document.querySelector('#spon').value,
  gender: document.querySelector('#gender').value,
  sig: document.querySelector('#sig').value,
  mystery: document.querySelector('#mystery').value,
  cover: document.querySelector('#cover').value,
  submitted: window.__submitted || 0,
}));
console.log('   values:', JSON.stringify(values, null, 2).replace(/\n/g, '\n   '));
values.first === 'Jane' ? ok('first name filled') : fail('first name not filled');
values.email === 'jane.doe@example.com' ? ok('email filled') : fail('email not filled');
values.auth === '1' ? ok('work authorization select set to Yes') : fail(`auth select = ${values.auth}`);
values.spon === '0' ? ok('sponsorship select set to No') : fail(`sponsorship select = ${values.spon}`);
values.gender === '' ? ok('EEO gender left blank') : fail('EEO field was filled');
values.sig === '' ? ok('signature left blank') : fail('signature was filled');
values.mystery === '' ? ok('unmapped question left blank') : fail('unmapped question was filled');
values.cover.includes('Acme Corp') ? ok('cover letter resolved {company}') : fail('company not substituted: ' + values.cover.slice(0, 80));
values.cover.includes('Director of People Operations') ? ok('cover letter resolved {title}') : fail('title not substituted');
!values.cover.includes('{') ? ok('no unresolved placeholders') : fail('cover letter still has placeholders');
values.cover.split('\n').length > 2 ? ok('cover letter kept its line breaks') : fail('newlines lost: ' + JSON.stringify(values.cover.slice(0, 60)));
values.submitted === 0 ? ok('form was NOT submitted') : fail('form was submitted!');

console.log('\n6. Learn an unmapped field');
const details = panel.locator('details');
await details.locator('summary').click();
const items = panel.locator('.skipped .item');
const count = await items.count();
let mapped = false;
for (let i = 0; i < count; i += 1) {
  const text = await items.nth(i).innerText();
  if (text.includes('Question 7')) {
    await items.nth(i).locator('select').selectOption('preferred_name');
    await items.nth(i).locator('button').click();
    mapped = true;
    break;
  }
}
mapped ? ok('mapped "Question 7" -> preferred_name') : fail('could not find Question 7 in skipped list');
await page.waitForTimeout(1500);
const relearned = await panel.locator('.row[data-row]').evaluateAll((els) =>
  els.map((e) => e.querySelector('.canonical').textContent.split(' ·')[0])
);
relearned.includes('preferred_name') ? ok('re-scan picked up the learned mapping') : fail(`after learn: ${relearned}`);

console.log('\n7. Log to dashboard');
await panel.locator('button[data-act="log"]').click();
await page.waitForTimeout(1200);
const status = await panel.locator('[data-role="status"]').innerText();
console.log('   status:', status);
status.includes('Logged') ? ok('logged') : fail('log failed: ' + status);

await context.close();
console.log(process.exitCode ? '\nSOME CHECKS FAILED' : '\nALL EXTENSION CHECKS PASSED');
