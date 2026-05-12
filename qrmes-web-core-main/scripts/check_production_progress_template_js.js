const fs = require('fs');
const path = require('path');
const vm = require('vm');

const templatesDir = path.join(__dirname, '..', 'app_web', 'templates');
const listTemplatePath = path.join(templatesDir, 'production_progress.html');
const detailTemplatePath = path.join(templatesDir, 'production_progress_detail.html');
const specialSerial = "SN'BROKEN/001";

function readTemplate(templatePath) {
  const source = fs.readFileSync(templatePath, 'utf8');
  if (!source.includes('{% extends "base.html" %}')) {
    throw new Error(`${path.basename(templatePath)} must extend base.html`);
  }
  if (/<\/?(html|head|body)\b/i.test(source)) {
    throw new Error(`${path.basename(templatePath)} must not define standalone html/head/body tags`);
  }
  if (/onclick\s*=/.test(source)) {
    throw new Error(`${path.basename(templatePath)} must not contain inline onclick handlers`);
  }
  return source;
}

function extractScript(source, filename) {
  const matches = [...source.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  if (matches.length !== 1) {
    throw new Error(`${filename} must contain exactly one inline script block`);
  }
  return matches[0][1].replace('{{ serial|tojson }}', JSON.stringify(specialSerial));
}

function createElements() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) {
      elements.set(id, {
        id,
        value: '',
        textContent: '',
        innerHTML: '',
        className: '',
        dataset: {},
        href: '',
        hidden: false,
        src: '',
        alt: '',
        removeAttribute(name) { delete this[name]; },
        style: {
          setProperty(name, value) {
            this[name] = value;
          },
        },
        addEventListener() {},
        scrollIntoView() {},
        focus() {},
      });
    }
    return elements.get(id);
  }
  return { elements, element };
}

function createListContext() {
  const { elements, element } = createElements();
  const context = {
    console,
    URLSearchParams,
    FormData: class FormData {},
    document: {
      getElementById: element,
    },
    fetch: async url => {
      if (String(url).includes('/options')) {
        return {
          ok: true,
          json: async () => ({ projects: [], product_types: [], process_steps: [] }),
        };
      }
      if (String(url).includes('/board')) {
        return {
          ok: true,
          json: async () => ({
            items: [{
              product_serial: specialSerial,
              status: 'in_progress',
              current_step: { process_step: '首检', human_duration: '1分钟' },
              total_duration: { human_duration: '1分钟', duration_seconds: 60 },
              last_event_at: 1_000,
            }],
            summary: { total: 2, displayed: 1, in_progress: 1, completed: 1, not_started: 0 },
          }),
        };
      }
      return {
        ok: true,
        json: async () => ({ success: true }),
      };
    },
  };
  return { context, element, elements };
}

function createDetailContext() {
  const { element } = createElements();
  const context = {
    console,
    document: {
      getElementById: element,
      addEventListener() {},
      body: {
        classList: {
          add() {},
          remove() {},
        },
      },
    },
    fetch: async url => {
      const encoded = encodeURIComponent(specialSerial);
      if (!String(url).endsWith(`/api/production-progress/${encoded}`)) {
        throw new Error(`detail page must request encoded serial URL, got ${url}`);
      }
      return {
        ok: true,
        json: async () => ({
          product_serial: specialSerial,
          status: 'completed',
          final_complete_at: 7_000,
          current_step: { process_step: '完成生产' },
          total_duration: { human_duration: '6秒', duration_seconds: 6 },
          timeline: [{
            process_step: '完成生产',
            status: 'completed',
            scan_at: 5_000,
            complete_at: 7_000,
            human_duration: '2秒',
            attachments: {
              photos: [{ id: 1, file_name: 'done.jpg', preview_url: '/api/photos/file/1' }],
              documents: [],
            },
          }],
        }),
      };
    },
  };
  return { context, element };
}

async function runListScript(scriptSource) {
  new vm.Script(scriptSource, { filename: 'production_progress.inline.js' });
  const { context, element } = createListContext();
  vm.createContext(context);
  vm.runInContext(scriptSource, context, { filename: 'production_progress.inline.js' });
  await context.loadBoard();
  const renderedRows = element('boardRows').innerHTML;
  if (renderedRows.includes('onclick=')) {
    throw new Error('detail buttons must not render inline onclick handlers');
  }
  if (!renderedRows.includes('data-serial="SN&#39;BROKEN/001"')) {
    throw new Error('detail link data-serial must HTML-escape serials containing single quotes');
  }
  if (!renderedRows.includes('/production-progress/SN&#39;BROKEN%2F001')) {
    throw new Error('detail link href must use /production-progress/ + encodeURIComponent(serial)');
  }
}

async function runDetailScript(scriptSource) {
  new vm.Script(scriptSource, { filename: 'production_progress_detail.inline.js' });
  const { context, element } = createDetailContext();
  vm.createContext(context);
  vm.runInContext(scriptSource, context, { filename: 'production_progress_detail.inline.js' });
  await context.loadDetail();
  if (!element('timeline').innerHTML.includes('完成生产')) {
    throw new Error('detail template must render timeline data from the detail API');
  }
  const renderedTimeline = element('timeline').innerHTML;
  if (!renderedTimeline.includes('ppd-photo-link')) {
    throw new Error('photo attachments must render as in-page preview links');
  }
  if (!renderedTimeline.includes('data-preview-url="/api/photos/file/1"')) {
    throw new Error('photo preview link must keep /api/photos/file/<id> for modal preview');
  }
  if (renderedTimeline.includes('target="_blank" rel="noopener">照片')) {
    throw new Error('photo links should not navigate away directly; use the modal preview instead');
  }
}

async function main() {
  const listHtml = readTemplate(listTemplatePath);
  const detailHtml = readTemplate(detailTemplatePath);
  await runListScript(extractScript(listHtml, 'production_progress.html'));
  await runDetailScript(extractScript(detailHtml, 'production_progress_detail.html'));
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
