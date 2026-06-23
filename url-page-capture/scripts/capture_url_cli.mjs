#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import extractArticleFromDom from './extract_dom_article.mjs';

const ARCHIVE_HOME_URL = 'https://archive.is/';
const SHORT_ARCHIVE_RE = /^https:\/\/archive\.(?:is|today|md|ph|vn|fo|li)\/[A-Za-z0-9]{5,}$/;
const ACCESS_LIMIT_RE = /captcha|security verification|one more step|checking your browser|verify you are human|subscribe to read|subscribe to continue|sign in to read|paywall|enable javascript|access denied|forbidden/i;
const DEFAULT_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

async function main() {
	const options = parseArgs(process.argv.slice(2));
	if (options.help) {
		printHelp();
		return;
	}
	if (!options.url) {
		printHelp();
		process.exitCode = 2;
		return;
	}
	if (!options.confirmRights) {
		throw new Error('This script writes full page content. Re-run with --confirm-rights after confirming you may capture this URL.');
	}

	const startedAt = new Date().toISOString();
	const manifest = {
		success: false,
		input_url: options.url,
		started_at: startedAt,
		finished_at: null,
		output_path: path.resolve(options.outPath),
		manifest_path: path.resolve(options.manifestPath),
		attempts: [],
		error: null,
	};

	let result = null;
	try {
		if (options.browserCdp && !options.allowLegacyCdp) {
			throw new Error('--browser-cdp is disabled for formal skill workflows. Use Chrome Extension / chrome:control-chrome with the user main Google Chrome instead.');
		}
		const httpResult = await captureViaHttp(options.url, options);
		manifest.attempts.push(toAttemptRecord(httpResult));
		if (isUsableCapture(httpResult, options.minChars)) {
			result = httpResult;
		}

		if (!result && !options.noBrowser && options.browserCdp && options.fallback !== 'none') {
			const browserResult = await captureViaBrowserFallback(options.url, options);
			manifest.attempts.push(...browserResult.attempts);
			if (isUsableCapture(browserResult.result, options.minChars)) {
				result = browserResult.result;
			}
		}

		if (!result) {
			const nextAction = options.browserCdp
				? 'Inspect attempts in the manifest; HTTP and browser fallback did not return enough readable content.'
				: 'Use Chrome Extension / chrome:control-chrome with the user main Google Chrome, or rerun as HTTP-only for public variants.';
			throw new Error(`No usable page content captured. ${nextAction}`);
		}

		manifest.success = true;
		manifest.capture = toCaptureManifest(result);
		await writeCaptureOutputs(result, manifest, options);
		console.log(JSON.stringify({
			success: true,
			method: result.capture_method,
			resolved_url: result.resolved_url,
			title: result.title,
			content_text_length: result.content_text.length,
			output_path: manifest.output_path,
			manifest_path: manifest.manifest_path,
		}, null, 2));
	} catch (error) {
		manifest.error = String(error?.stack || error);
		throw error;
	} finally {
		manifest.finished_at = new Date().toISOString();
		await writeManifest(manifest, options).catch(() => {});
	}
}

function parseArgs(argv) {
	const options = {
		url: null,
		outPath: null,
		manifestPath: null,
		browserCdp: null,
		allowLegacyCdp: false,
		noBrowser: false,
		fallback: 'archive-is',
		minChars: 1000,
		maxSnapshots: 5,
		httpTimeoutMs: 20000,
		navigationTimeoutMs: 30000,
		includeHtml: false,
		confirmRights: false,
		help: false,
	};

	for (let index = 0; index < argv.length; index += 1) {
		const arg = argv[index];
		if (arg === '--help' || arg === '-h') {
			options.help = true;
		} else if (arg === '--out') {
			options.outPath = requireValue(argv, ++index, arg);
		} else if (arg === '--manifest') {
			options.manifestPath = requireValue(argv, ++index, arg);
		} else if (arg === '--browser-cdp') {
			options.browserCdp = requireValue(argv, ++index, arg).replace(/\/+$/, '');
		} else if (arg === '--allow-legacy-cdp') {
			options.allowLegacyCdp = true;
		} else if (arg === '--fallback') {
			options.fallback = requireValue(argv, ++index, arg);
		} else if (arg === '--min-chars') {
			options.minChars = parsePositiveInt(requireValue(argv, ++index, arg), arg);
		} else if (arg === '--max-snapshots') {
			options.maxSnapshots = parsePositiveInt(requireValue(argv, ++index, arg), arg);
		} else if (arg === '--http-timeout-ms') {
			options.httpTimeoutMs = parsePositiveInt(requireValue(argv, ++index, arg), arg);
		} else if (arg === '--navigation-timeout-ms') {
			options.navigationTimeoutMs = parsePositiveInt(requireValue(argv, ++index, arg), arg);
		} else if (arg === '--include-html') {
			options.includeHtml = true;
		} else if (arg === '--no-browser') {
			options.noBrowser = true;
		} else if (arg === '--confirm-rights') {
			options.confirmRights = true;
		} else if (arg.startsWith('--')) {
			throw new Error(`Unknown option: ${arg}`);
		} else if (!options.url) {
			options.url = arg;
		} else {
			throw new Error(`Unexpected positional argument: ${arg}`);
		}
	}

	if (options.fallback !== 'archive-is' && options.fallback !== 'direct-browser' && options.fallback !== 'auto' && options.fallback !== 'none') {
		throw new Error('--fallback must be one of: archive-is, direct-browser, auto, none');
	}
	if (options.url) {
		new URL(options.url);
		options.outPath ||= defaultOutPath(options.url);
		options.manifestPath ||= `${options.outPath}.manifest.json`;
	}
	return options;
}

function requireValue(argv, index, optionName) {
	const value = argv[index];
	if (!value || value.startsWith('--')) throw new Error(`${optionName} requires a value`);
	return value;
}

function parsePositiveInt(value, optionName) {
	const parsed = Number.parseInt(value, 10);
	if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(`${optionName} must be a positive integer`);
	return parsed;
}

function defaultOutPath(inputUrl) {
	const url = new URL(inputUrl);
	const slug = `${url.hostname}${url.pathname}`
		.replace(/\/+$/, '')
		.replace(/[^A-Za-z0-9._-]+/g, '-')
		.replace(/^-+|-+$/g, '')
		.slice(0, 120) || 'page-capture';
	return path.resolve(process.cwd(), `${slug}.txt`);
}

function printHelp() {
	console.log(`Usage:
  node capture_url_cli.mjs <url> --confirm-rights [options]

Options:
  --out <path>                 Text document to write. Defaults to ./<host-path>.txt
  --manifest <path>            JSON manifest path. Defaults to <out>.manifest.json
  --browser-cdp <url>          Legacy/debug only. Disabled unless --allow-legacy-cdp is passed.
  --allow-legacy-cdp           Explicitly allow legacy CDP fallback. Do not use in formal skill workflows.
  --fallback <mode>            archive-is | direct-browser | auto | none. Default: archive-is
  --min-chars <n>              Minimum accepted extracted text length. Default: 1000
  --max-snapshots <n>          Archive snapshots to try. Default: 5
  --include-html               Append raw HTML when the capture method can provide it
  --no-browser                 Disable browser fallback
  --confirm-rights             Required: confirm you may write full page content locally

Formal workflow example:
  node capture_url_cli.mjs "https://example.com/article" --confirm-rights --fallback none --no-browser

For browser/profile-dependent capture, use Chrome Extension / chrome:control-chrome with the user's main Google Chrome.
`);
}

async function captureViaHttp(inputUrl, options) {
	const startedAt = new Date().toISOString();
	const attempt = {
		success: false,
		capture_method: 'http-fetch',
		input_url: inputUrl,
		resolved_url: inputUrl,
		started_at: startedAt,
		finished_at: null,
		status: null,
		content_type: null,
		title: null,
		metadata: {},
		access_limited: true,
		content_text: '',
		content_text_length: 0,
		body_preview: '',
		raw_html: null,
		error: null,
	};

	try {
		const response = await fetch(inputUrl, {
			redirect: 'follow',
			signal: AbortSignal.timeout(options.httpTimeoutMs),
			headers: {
				'user-agent': DEFAULT_USER_AGENT,
				accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.7',
				'accept-language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
			},
		});
		const body = await response.text();
		const contentType = response.headers.get('content-type') || '';
		const isHtml = /html|xml/i.test(contentType) || /<\/?[a-z][\s\S]*>/i.test(body.slice(0, 2000));
		const metadata = isHtml ? extractHtmlMetadata(body) : {};
		const title = metadata.title || new URL(response.url).hostname;
		const contentText = isHtml ? htmlToVisibleText(body, title) : normalizePlainText(body);

		attempt.resolved_url = response.url;
		attempt.status = response.status;
		attempt.content_type = contentType;
		attempt.title = title;
		attempt.metadata = metadata;
		attempt.access_limited = !response.ok || detectAccessLimited(title, contentText, body);
		attempt.content_text = contentText;
		attempt.content_text_length = contentText.length;
		attempt.body_preview = contentText.slice(0, 1000);
		attempt.raw_html = options.includeHtml && isHtml ? body : null;
		attempt.success = response.ok && !attempt.access_limited;
		return attempt;
	} catch (error) {
		attempt.error = String(error?.stack || error);
		return attempt;
	} finally {
		attempt.finished_at = new Date().toISOString();
	}
}

async function captureViaBrowserFallback(inputUrl, options) {
	if (options.fallback === 'direct-browser') {
		return await captureViaDirectBrowser(inputUrl, options);
	}
	if (options.fallback === 'archive-is') {
		return await captureViaArchiveIs(inputUrl, options);
	}

	const direct = await captureViaDirectBrowser(inputUrl, options);
	if (isUsableCapture(direct.result, options.minChars)) return direct;

	const archive = await captureViaArchiveIs(inputUrl, options);
	return {
		result: archive.result,
		attempts: [...direct.attempts, ...archive.attempts],
	};
}

async function captureViaDirectBrowser(inputUrl, options) {
	let client = null;
	const attempts = [];

	try {
		const tab = await openCdpTab(options.browserCdp, 'about:blank');
		client = await CdpClient.connect(tab.webSocketDebuggerUrl);
		await enablePage(client);
		await navigateAndWait(client, inputUrl, options.navigationTimeoutMs);
		await waitForReadableBody(client, options.navigationTimeoutMs);
		const extraction = await evaluateExtraction(client, options.includeHtml);
		const result = normalizeDomExtraction(extraction, {
			captureMethod: 'chrome-cdp-direct',
			inputUrl,
			selectedSnapshotUrl: null,
		});
		attempts.push(toAttemptRecord(result));
		return { result, attempts };
	} catch (error) {
		const failed = failedAttempt('chrome-cdp-direct', inputUrl, error);
		attempts.push(failed);
		return { result: null, attempts };
	} finally {
		client?.close();
	}
}

async function captureViaArchiveIs(inputUrl, options) {
	let client = null;
	const attempts = [];

	try {
		const tab = await openCdpTab(options.browserCdp, 'about:blank');
		client = await CdpClient.connect(tab.webSocketDebuggerUrl);
		await enablePage(client);
		await navigateAndWait(client, ARCHIVE_HOME_URL, options.navigationTimeoutMs);
		await submitArchiveSearch(client, inputUrl);
		await waitForArchiveSearchPage(client, options.navigationTimeoutMs);

		const searchPage = await readArchiveSearchPage(client);
		const searchAttempt = {
			success: true,
			capture_method: 'archive-is-search-page',
			input_url: inputUrl,
			resolved_url: searchPage.url,
			title: searchPage.title,
			status: null,
			access_limited: false,
			content_text_length: searchPage.body_preview.length,
			body_preview: searchPage.body_preview,
			selected_snapshot_url: null,
			error: null,
		};
		attempts.push(searchAttempt);

		const snapshotCandidates = chooseSnapshotCandidates(searchPage.links).slice(0, options.maxSnapshots);
		if (!snapshotCandidates.length) {
			throw new Error('No short archive snapshot links were found on the archive.is search results page.');
		}

		for (const candidate of snapshotCandidates) {
			try {
				await navigateAndWait(client, candidate.href, options.navigationTimeoutMs);
				await waitForReadableBody(client, options.navigationTimeoutMs);
				const extraction = await evaluateExtraction(client, options.includeHtml);
				const result = normalizeDomExtraction(extraction, {
					captureMethod: 'chrome-cdp-archive-is-search',
					inputUrl,
					selectedSnapshotUrl: candidate.href,
					snapshotLabel: candidate.text,
					snapshotDateScore: candidate.dateScore,
				});
				attempts.push(toAttemptRecord(result));
				if (isUsableCapture(result, options.minChars)) return { result, attempts };
			} catch (error) {
				attempts.push(failedAttempt('chrome-cdp-archive-is-snapshot', candidate.href, error, {
					selected_snapshot_url: candidate.href,
					snapshot_label: candidate.text,
				}));
			}
		}

		return { result: null, attempts };
	} catch (error) {
		attempts.push(failedAttempt('chrome-cdp-archive-is-search', inputUrl, error));
		return { result: null, attempts };
	} finally {
		client?.close();
	}
}

async function openCdpTab(cdpBaseUrl, initialUrl) {
	const encoded = encodeURIComponent(initialUrl);
	const endpoint = `${cdpBaseUrl}/json/new?${encoded}`;
	let response = await fetch(endpoint, { method: 'PUT' });
	if (!response.ok) response = await fetch(endpoint).catch(() => response);
	if (!response.ok) {
		const list = await fetchJson(`${cdpBaseUrl}/json/list`);
		const existing = list.find((entry) => entry.type === 'page' && entry.webSocketDebuggerUrl);
		if (existing) return existing;
		throw new Error(`Could not open a CDP tab at ${cdpBaseUrl}; /json/new returned ${response.status}`);
	}
	const tab = await response.json();
	if (!tab.webSocketDebuggerUrl) throw new Error(`CDP tab did not include webSocketDebuggerUrl: ${JSON.stringify(tab)}`);
	return tab;
}

async function fetchJson(url) {
	const response = await fetch(url);
	if (!response.ok) throw new Error(`${url} returned ${response.status}`);
	return await response.json();
}

class CdpClient {
	constructor(webSocketUrl) {
		this.webSocketUrl = webSocketUrl;
		this.nextId = 1;
		this.pending = new Map();
		this.ws = new WebSocket(webSocketUrl);
		this.ws.addEventListener('message', (event) => this.onMessage(event));
	}

	static async connect(webSocketUrl) {
		const client = new CdpClient(webSocketUrl);
		await new Promise((resolve, reject) => {
			const timeout = setTimeout(() => reject(new Error(`Timed out connecting to ${webSocketUrl}`)), 10000);
			client.ws.addEventListener('open', () => {
				clearTimeout(timeout);
				resolve();
			}, { once: true });
			client.ws.addEventListener('error', (event) => {
				clearTimeout(timeout);
				reject(new Error(`CDP WebSocket error: ${event.message || event.type}`));
			}, { once: true });
		});
		return client;
	}

	send(method, params = {}, timeoutMs = 30000) {
		const id = this.nextId++;
		const payload = { id, method, params };
		return new Promise((resolve, reject) => {
			const timeout = setTimeout(() => {
				this.pending.delete(id);
				reject(new Error(`CDP timeout for ${method}`));
			}, timeoutMs);
			this.pending.set(id, { resolve, reject, timeout, method });
			this.ws.send(JSON.stringify(payload));
		});
	}

	onMessage(event) {
		const text = typeof event.data === 'string' ? event.data : Buffer.from(event.data).toString('utf8');
		const message = JSON.parse(text);
		if (!message.id || !this.pending.has(message.id)) return;
		const pending = this.pending.get(message.id);
		this.pending.delete(message.id);
		clearTimeout(pending.timeout);
		if (message.error) {
			pending.reject(new Error(`${pending.method}: ${message.error.message || JSON.stringify(message.error)}`));
		} else {
			pending.resolve(message.result || {});
		}
	}

	close() {
		try {
			this.ws.close();
		} catch {
			// Best effort cleanup.
		}
	}
}

async function enablePage(client) {
	await client.send('Page.enable');
	await client.send('Runtime.enable');
}

async function navigateAndWait(client, url, timeoutMs) {
	await client.send('Page.navigate', { url }, timeoutMs);
	await waitUntil(client, async () => {
		const state = await evaluate(client, 'document.readyState');
		return state === 'interactive' || state === 'complete';
	}, timeoutMs, 500);
	await sleep(750);
}

async function evaluate(client, expression, timeoutMs = 30000) {
	const response = await client.send('Runtime.evaluate', {
		expression,
		awaitPromise: true,
		returnByValue: true,
	}, timeoutMs);
	if (response.exceptionDetails) {
		throw new Error(response.exceptionDetails.text || 'Runtime.evaluate failed');
	}
	return response.result?.value;
}

async function evaluateExtraction(client, includeHtml) {
	const extractorSource = extractArticleFromDom.toString();
	const extraction = await evaluate(client, `(${extractorSource})()`);
	if (includeHtml) {
		extraction.raw_html = await evaluate(client, 'document.documentElement.outerHTML');
	}
	return extraction;
}

async function submitArchiveSearch(client, inputUrl) {
	const expression = `(() => {
		const input = document.querySelector('#q');
		if (!input) return { ok: false, error: 'Missing archive.is search input #q' };
		input.focus();
		input.value = ${JSON.stringify(inputUrl)};
		input.dispatchEvent(new Event('input', { bubbles: true }));
		input.dispatchEvent(new Event('change', { bubbles: true }));
		const form = input.closest('form');
		if (!form) return { ok: false, error: 'Missing archive.is search form' };
		const submit = form.querySelector('input[type="submit"], button[type="submit"]');
		if (submit) submit.click();
		else form.submit();
		return { ok: true };
	})()`;
	const result = await evaluate(client, expression);
	if (!result?.ok) throw new Error(result?.error || 'Could not submit archive.is search form');
	await sleep(1000);
}

async function waitForArchiveSearchPage(client, timeoutMs) {
	await waitUntil(client, async () => {
		const state = await evaluate(client, `(() => ({
			readyState: document.readyState,
			href: location.href,
			shortLinks: Array.from(document.querySelectorAll('a')).filter((anchor) => /^https:\\/\\/archive\\.(?:is|today|md|ph|vn|fo|li)\\/[A-Za-z0-9]{5,}$/.test(anchor.href)).length,
			bodyLength: document.body?.innerText?.length || 0,
		}))()`);
		return state.readyState === 'complete' && (state.shortLinks > 0 || state.bodyLength > 500);
	}, timeoutMs, 1000).catch(() => {});
}

async function readArchiveSearchPage(client) {
	return await evaluate(client, `(() => ({
		url: location.href,
		title: document.title,
		body_preview: (document.body?.innerText || '').slice(0, 2000),
		links: Array.from(document.querySelectorAll('a'))
			.map((anchor) => ({
				text: (anchor.textContent || '').trim(),
				href: anchor.href,
			}))
			.filter((link) => link.href),
	}))()`);
}

async function waitForReadableBody(client, timeoutMs) {
	await waitUntil(client, async () => {
		const state = await evaluate(client, `(() => ({
			title: document.title,
			bodyLength: document.body?.innerText?.length || 0,
			bodyPreview: (document.body?.innerText || '').slice(0, 500),
		}))()`);
		if (state.bodyLength > 1000) return true;
		return ACCESS_LIMIT_RE.test(`${state.title}\n${state.bodyPreview}`);
	}, Math.min(timeoutMs, 15000), 1000).catch(() => {});
}

async function waitUntil(client, predicate, timeoutMs, intervalMs) {
	const started = Date.now();
	let lastError = null;
	while (Date.now() - started < timeoutMs) {
		try {
			if (await predicate(client)) return;
		} catch (error) {
			lastError = error;
		}
		await sleep(intervalMs);
	}
	if (lastError) throw lastError;
	throw new Error(`Timed out after ${timeoutMs}ms`);
}

function chooseSnapshotCandidates(links) {
	const candidatesByHref = new Map();
	for (const link of links || []) {
		if (!SHORT_ARCHIVE_RE.test(link.href)) continue;
		const parsedDate = Date.parse(`${link.text} UTC`);
		const candidate = {
			text: link.text,
			href: link.href,
			dateScore: Number.isNaN(parsedDate) ? 0 : parsedDate,
		};
		const existing = candidatesByHref.get(link.href);
		if (!existing || candidate.dateScore > existing.dateScore || (candidate.dateScore === existing.dateScore && candidate.text.length > existing.text.length)) {
			candidatesByHref.set(link.href, candidate);
		}
	}
	return Array.from(candidatesByHref.values()).sort((a, b) => {
		if (b.dateScore !== a.dateScore) return b.dateScore - a.dateScore;
		return b.text.length - a.text.length;
	});
}

function normalizeDomExtraction(extraction, details) {
	const contentText = normalizePlainText(extraction.content_text || markdownishToPlainText(extraction.markdown || extraction.body_preview || ''));
	return {
		success: !extraction.access_limited,
		capture_method: details.captureMethod,
		input_url: details.inputUrl,
		resolved_url: extraction.url,
		selected_snapshot_url: details.selectedSnapshotUrl,
		snapshot_label: details.snapshotLabel || null,
		snapshot_date_score: details.snapshotDateScore || 0,
		status: null,
		content_type: 'text/html',
		title: extraction.title || null,
		metadata: extraction.metadata || {},
		access_limited: Boolean(extraction.access_limited),
		content_text: contentText,
		content_text_length: contentText.length,
		body_preview: (extraction.body_preview || contentText).slice(0, 1000),
		raw_html: extraction.raw_html || null,
		error: null,
	};
}

function isUsableCapture(result, minChars) {
	return Boolean(result?.success && !result.access_limited && result.content_text?.length >= minChars);
}

function detectAccessLimited(title, text, raw) {
	return ACCESS_LIMIT_RE.test(`${title || ''}\n${(text || '').slice(0, 5000)}\n${(raw || '').slice(0, 2000)}`);
}

function extractHtmlMetadata(html) {
	const metadata = {};
	const metaTagRe = /<meta\b[^>]*>/gi;
	let tagMatch = null;
	while ((tagMatch = metaTagRe.exec(html))) {
		const attrs = parseAttrs(tagMatch[0]);
		const key = attrs.property || attrs.name || attrs.itemprop;
		if (key && attrs.content) metadata[key.toLowerCase()] = decodeHtmlEntities(attrs.content);
	}

	const title = pickMetadata(metadata, ['og:title', 'twitter:title', 'parsely-title'])
		|| extractTagText(html, 'h1')
		|| extractTagText(html, 'title');
	const byline = pickMetadata(metadata, ['author', 'article:author', 'parsely-author']);
	const publishedAt = pickMetadata(metadata, ['article:published_time', 'parsely-pub-date', 'date', 'pubdate']);
	const siteName = pickMetadata(metadata, ['og:site_name', 'application-name']);
	const description = pickMetadata(metadata, ['description', 'og:description', 'twitter:description']);

	return {
		title: normalizePlainText(title || ''),
		byline: byline || null,
		published_at: publishedAt || null,
		site_name: siteName || null,
		description: description || null,
		raw_meta: metadata,
	};
}

function parseAttrs(tag) {
	const attrs = {};
	const attrRe = /([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g;
	let match = null;
	while ((match = attrRe.exec(tag))) {
		attrs[match[1].toLowerCase()] = match[2] ?? match[3] ?? match[4] ?? '';
	}
	return attrs;
}

function pickMetadata(metadata, keys) {
	for (const key of keys) {
		const value = metadata[key.toLowerCase()];
		if (value) return normalizePlainText(value);
	}
	return null;
}

function extractTagText(html, tagName) {
	const match = new RegExp(`<${tagName}\\b[^>]*>([\\s\\S]*?)<\\/${tagName}>`, 'i').exec(html);
	return match ? normalizePlainText(stripTags(match[1])) : null;
}

function htmlToVisibleText(html, title) {
	const withoutInvisible = html
		.replace(/<script\b[\s\S]*?<\/script>/gi, '\n')
		.replace(/<style\b[\s\S]*?<\/style>/gi, '\n')
		.replace(/<noscript\b[\s\S]*?<\/noscript>/gi, '\n')
		.replace(/<svg\b[\s\S]*?<\/svg>/gi, '\n')
		.replace(/<iframe\b[\s\S]*?<\/iframe>/gi, '\n');
	const withBreaks = withoutInvisible
		.replace(/<\/?(?:article|main|section|div|p|h[1-6]|blockquote|li|ul|ol|pre|br|tr|td|th|table)\b[^>]*>/gi, '\n')
		.replace(/<[^>]+>/g, ' ');
	let text = postprocessTextLines(decodeHtmlEntities(withBreaks), title);
	if (title && text && !text.toLowerCase().startsWith(title.toLowerCase())) {
		text = `${title}\n\n${text}`;
	}
	return text;
}

function stripTags(value) {
	return decodeHtmlEntities((value || '').replace(/<[^>]+>/g, ' '));
}

function decodeHtmlEntities(value) {
	return (value || '')
		.replace(/&nbsp;/gi, ' ')
		.replace(/&amp;/gi, '&')
		.replace(/&lt;/gi, '<')
		.replace(/&gt;/gi, '>')
		.replace(/&quot;/gi, '"')
		.replace(/&#39;/gi, "'")
		.replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number.parseInt(code, 10)))
		.replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(Number.parseInt(code, 16)));
}

function normalizePlainText(value) {
	return (value || '')
		.replace(/\u00a0/g, ' ')
		.replace(/[ \t]{2,}/g, ' ')
		.replace(/[ \t]+\n/g, '\n')
		.replace(/\n[ \t]+/g, '\n')
		.replace(/\n{3,}/g, '\n\n')
		.trim();
}

function postprocessTextLines(text, title) {
	const cleanedLines = [];
	let blankPending = false;
	for (const rawLine of normalizePlainText(text).split('\n')) {
		const line = normalizePlainText(rawLine);
		if (!line) {
			blankPending = cleanedLines.length > 0;
			continue;
		}
		if (isNoiseLine(line, title)) continue;
		if (blankPending) {
			cleanedLines.push('');
			blankPending = false;
		}
		cleanedLines.push(line);
	}
	return cleanedLines.join('\n').trim();
}

function isNoiseLine(line, title) {
	const plain = line.replace(/^[#>*\-\s]+/, '').trim();
	const lower = plain.toLowerCase();
	const titleLower = (title || '').toLowerCase();
	if (!plain) return true;
	if (/^current progress\s+\d+%$/i.test(plain)) return true;
	if (/^-?\s*(save|print this page|copy link|share|listen to article|add to myft)$/i.test(line)) return true;
	if (/^(accessibility help|skip to navigation|skip to main content|skip to footer|open side navigation menu|open search bar)$/i.test(plain)) return true;
	if (/^advertisement$/i.test(plain)) return true;
	if (titleLower && lower.startsWith(titleLower) && /\bon (x|facebook|linkedin|whatsapp)\b/i.test(lower)) return true;
	return false;
}

function markdownishToPlainText(markdown) {
	return normalizePlainText((markdown || '')
		.replace(/^#{1,6}\s+/gm, '')
		.replace(/^>\s?/gm, '')
		.replace(/^[-*]\s+/gm, '')
		.replace(/```[\s\S]*?```/g, (block) => block.replace(/```/g, '')));
}

function toAttemptRecord(result) {
	if (!result) return null;
	return {
		success: Boolean(result.success),
		capture_method: result.capture_method,
		input_url: result.input_url,
		resolved_url: result.resolved_url,
		selected_snapshot_url: result.selected_snapshot_url || null,
		status: result.status ?? null,
		content_type: result.content_type || null,
		title: result.title || null,
		access_limited: Boolean(result.access_limited),
		content_text_length: result.content_text?.length || result.content_text_length || 0,
		body_preview: result.body_preview || '',
		error: result.error || null,
	};
}

function failedAttempt(captureMethod, url, error, extra = {}) {
	return {
		success: false,
		capture_method: captureMethod,
		input_url: url,
		resolved_url: url,
		status: null,
		content_type: null,
		title: null,
		access_limited: true,
		content_text_length: 0,
		body_preview: '',
		error: String(error?.stack || error),
		...extra,
	};
}

function toCaptureManifest(result) {
	return {
		success: true,
		capture_method: result.capture_method,
		input_url: result.input_url,
		resolved_url: result.resolved_url,
		selected_snapshot_url: result.selected_snapshot_url || null,
		title: result.title,
		metadata: result.metadata,
		access_limited: result.access_limited,
		content_text_length: result.content_text.length,
		body_preview: result.body_preview,
	};
}

async function writeCaptureOutputs(result, manifest, options) {
	await mkdir(path.dirname(path.resolve(options.outPath)), { recursive: true });
	const lines = [
		'URL Page Capture',
		`Input URL: ${result.input_url}`,
		`Resolved URL: ${result.resolved_url}`,
		`Capture method: ${result.capture_method}`,
		result.selected_snapshot_url ? `Selected snapshot: ${result.selected_snapshot_url}` : null,
		result.title ? `Title: ${result.title}` : null,
		result.metadata?.byline ? `Byline: ${result.metadata.byline}` : null,
		result.metadata?.published_at ? `Published at: ${result.metadata.published_at}` : null,
		result.metadata?.site_name ? `Site: ${result.metadata.site_name}` : null,
		`Captured at: ${new Date().toISOString()}`,
		`Content text length: ${result.content_text.length}`,
		'',
		'===== CONTENT TEXT =====',
		'',
		result.content_text.trim(),
	];
	if (options.includeHtml && result.raw_html) {
		lines.push('', '===== RAW HTML =====', '', result.raw_html);
	}
	await writeFile(options.outPath, lines.filter((line) => line !== null).join('\n'), 'utf8');
	await writeManifest(manifest, options);
}

async function writeManifest(manifest, options) {
	await mkdir(path.dirname(path.resolve(options.manifestPath)), { recursive: true });
	await writeFile(options.manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
}

function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((error) => {
	console.error(error?.stack || String(error));
	process.exitCode = 1;
});
