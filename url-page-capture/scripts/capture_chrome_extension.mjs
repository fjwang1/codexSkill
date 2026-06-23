import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { runArchiveIsChromeFlow } from './archive_is_chrome_flow.mjs';
import extractArticleFromDom from './extract_dom_article.mjs';

export async function captureUrlWithChromeExtension({
	browser = null,
	tab = null,
	originalUrl,
	outPath = null,
	manifestPath = null,
	minMarkdownChars = 1000,
	maxSnapshots = 5,
	navigationTimeoutMs = 30000,
	archiveHomeUrls = undefined,
	sessionName = 'URL page capture',
	closeTab = false,
	directFirst = true,
} = {}) {
	if (!originalUrl || !/^https?:\/\//.test(originalUrl)) throw new Error(`originalUrl must be an absolute URL: ${originalUrl}`);

	const chromeBrowser = browser || globalThis.browser || (globalThis.agent?.browsers?.get ? await globalThis.agent.browsers.get('extension') : null);
	if (!chromeBrowser && !tab) throw new Error('A Chrome extension browser or an existing tab is required');

	if (chromeBrowser?.nameSession) await chromeBrowser.nameSession(sessionName).catch(() => {});
	const ownsTab = !tab;
	const captureTab = tab || await chromeBrowser.tabs.new();
	const startedAt = new Date().toISOString();

	let flowResult = null;
	let success = false;
	let error = null;
	let captureMethod = null;
	try {
		if (directFirst) {
			flowResult = await runDirectChromeFlow({
				tab: captureTab,
				originalUrl,
				minMarkdownChars,
				navigationTimeoutMs,
			});
			success = Boolean(flowResult.manifest.success && flowResult.extraction);
			if (success) captureMethod = 'chrome-extension-direct';
		}

		if (!success) {
			const archiveResult = await runArchiveIsChromeFlow({
				tab: captureTab,
				originalUrl,
				minMarkdownChars,
				maxSnapshots,
				navigationTimeoutMs,
				archiveHomeUrls,
			});
			if (flowResult?.manifest) {
				archiveResult.manifest.prior_direct_manifest = flowResult.manifest;
			}
			flowResult = archiveResult;
			success = Boolean(flowResult.manifest.success && flowResult.extraction);
			if (success) captureMethod = 'chrome-extension-archive-is-search';
		}

		success = Boolean(flowResult.manifest.success && flowResult.extraction);
		if (!success) error = flowResult.manifest.error || 'Archive flow did not produce usable page content';
	} catch (caught) {
		error = String(caught?.stack || caught);
		flowResult = {
			manifest: {
				success: false,
				original_url: originalUrl,
				method: 'chrome-extension-autonomous',
				error,
			},
			extraction: null,
		};
	} finally {
		if (closeTab && ownsTab) await captureTab.close().catch(() => {});
	}

	const captureText = success ? buildCaptureText({
		originalUrl,
		flowManifest: flowResult.manifest,
		extraction: flowResult.extraction,
		startedAt,
		captureMethod,
	}) : '';
	const manifest = buildManifest({
		originalUrl,
		outPath,
		manifestPath,
		startedAt,
		success,
		error,
		flowManifest: flowResult.manifest,
		extraction: flowResult.extraction,
		captureMethod,
	});

	if (outPath && success) {
		await mkdir(path.dirname(path.resolve(outPath)), { recursive: true });
		await writeFile(outPath, captureText, 'utf8');
	}
	if (manifestPath) {
		await mkdir(path.dirname(path.resolve(manifestPath)), { recursive: true });
		await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
	}

	return {
		success,
		error,
		output_path: outPath ? path.resolve(outPath) : null,
		manifest_path: manifestPath ? path.resolve(manifestPath) : null,
		resolved_url: flowResult.extraction?.url || flowResult.manifest.selected_snapshot_url || null,
		selected_snapshot_url: flowResult.manifest.selected_snapshot_url || null,
		capture_method: captureMethod || flowResult.manifest.method || 'chrome-extension-autonomous',
		title: flowResult.extraction?.title || null,
		markdown_length: flowResult.extraction?.markdown_length || 0,
		body_preview: flowResult.extraction?.body_preview || '',
		manifest,
		extraction: flowResult.extraction,
		tab_id: captureTab.id,
	};
}

async function runDirectChromeFlow({
	tab,
	originalUrl,
	minMarkdownChars,
	navigationTimeoutMs,
}) {
	const manifest = {
		success: false,
		original_url: originalUrl,
		method: 'chrome-extension-direct',
		started_at: new Date().toISOString(),
		resolved_url: null,
		title: null,
		access_limited: null,
		markdown_length: 0,
		body_preview: '',
		error: null,
	};

	try {
		await tab.goto(originalUrl).catch(() => {});
		await tab.playwright.waitForLoadState({ state: 'domcontentloaded', timeoutMs: navigationTimeoutMs }).catch(() => {});
		await waitForReadableBody(tab, navigationTimeoutMs);
		const extraction = await tab.playwright.evaluate(extractArticleFromDom);
		manifest.resolved_url = extraction.url;
		manifest.title = extraction.title;
		manifest.access_limited = extraction.access_limited;
		manifest.markdown_length = extraction.markdown_length;
		manifest.body_preview = extraction.body_preview || '';
		manifest.success = !extraction.access_limited && extraction.markdown_length >= minMarkdownChars;
		manifest.finished_at = new Date().toISOString();
		return { manifest, extraction: manifest.success ? extraction : null };
	} catch (caught) {
		manifest.error = String(caught?.stack || caught);
		manifest.finished_at = new Date().toISOString();
		return { manifest, extraction: null };
	}
}

async function waitForReadableBody(tab, navigationTimeoutMs) {
	const timeoutAt = Date.now() + Math.min(navigationTimeoutMs, 15000);
	while (Date.now() < timeoutAt) {
		const state = await tab.playwright.evaluate(() => ({
			title: document.title,
			bodyLength: document.body?.innerText?.length || 0,
			bodyPreview: (document.body?.innerText || '').slice(0, 600),
		})).catch(() => ({ title: '', bodyLength: 0, bodyPreview: '' }));
		if (state.bodyLength > 1000 || /captcha|security verification|one more step|checking your browser|verify you are human|subscribe to read|subscribe to continue|sign in to read|paywall|access denied|forbidden/i.test(`${state.title}\n${state.bodyPreview}`)) return;
		await tab.playwright.waitForTimeout(1000).catch(() => {});
	}
}

function buildCaptureText({
	originalUrl,
	flowManifest,
	extraction,
	startedAt,
	captureMethod,
}) {
	const metadata = extraction.metadata || {};
	const sourceMarkdown = normalizeText(extraction.markdown || extraction.content_text || '');
	const headerLines = [
		`Title: ${normalizeText(extraction.title || metadata.title || '')}`,
		metadata.byline ? `Byline: ${normalizeText(metadata.byline)}` : '',
		metadata.published_at ? `Published: ${normalizeText(metadata.published_at)}` : '',
		metadata.site_name ? `Site: ${normalizeText(metadata.site_name)}` : '',
		`Original URL: ${originalUrl}`,
		`Resolved URL: ${extraction.url || flowManifest.selected_snapshot_url || ''}`,
		flowManifest.selected_snapshot_url ? `Archive URL: ${flowManifest.selected_snapshot_url}` : '',
		`Capture method: ${captureMethod || flowManifest.method || 'chrome-extension-autonomous'}`,
		`Captured at: ${startedAt}`,
	].filter(Boolean);

	return `${headerLines.join('\n')}\n\n${sourceMarkdown}\n`;
}

function buildManifest({
	originalUrl,
	outPath,
	manifestPath,
	startedAt,
	success,
	error,
	flowManifest,
	extraction,
	captureMethod,
}) {
	return {
		success,
		input_url: originalUrl,
		resolved_url: extraction?.url || flowManifest.selected_snapshot_url || null,
		capture_method: captureMethod || flowManifest.method || 'chrome-extension-autonomous',
		started_at: startedAt,
		finished_at: new Date().toISOString(),
		output_path: outPath ? path.resolve(outPath) : null,
		manifest_path: manifestPath ? path.resolve(manifestPath) : null,
		title: extraction?.title || null,
		metadata: extraction?.metadata || {},
		access_limited: Boolean(extraction?.access_limited),
		source_markdown_length: extraction?.markdown_length || 0,
		body_preview: extraction?.body_preview || '',
		selected_snapshot_url: flowManifest.selected_snapshot_url || null,
		error,
		flow_manifest: flowManifest,
	};
}

function normalizeText(value) {
	return String(value || '').replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}

export default captureUrlWithChromeExtension;
