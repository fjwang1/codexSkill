import extractArticleFromDom from './extract_dom_article.mjs';

const ARCHIVE_HOME_URLS = ['https://archive.is/', 'https://archive.today/', 'https://archive.ph/', 'https://archive.md/'];
const SHORT_ARCHIVE_RE = /^https:\/\/archive\.(?:is|today|md|ph|vn|fo|li)\/[A-Za-z0-9]{5,}$/;
const ACCESS_LIMIT_RE = /captcha|security verification|one more step|checking your browser|verify you are human|access denied|forbidden/i;

export async function runArchiveIsChromeFlow({
	tab,
	originalUrl,
	minMarkdownChars = 1000,
	maxSnapshots = 5,
	navigationTimeoutMs = 30000,
	archiveHomeUrls = ARCHIVE_HOME_URLS,
} = {}) {
	if (!tab) throw new Error('tab is required');
	if (!originalUrl || !/^https?:\/\//.test(originalUrl)) throw new Error(`originalUrl must be an absolute URL: ${originalUrl}`);

	const manifest = {
		original_url: originalUrl,
		method: 'archive.is-homepage-search-via-chrome',
		started_at: new Date().toISOString(),
		search_page: null,
		home_attempts: [],
		snapshot_attempts: [],
		success: false,
		selected_snapshot_url: null,
		error: null,
	};

	const normalizedHomeUrls = normalizeArchiveHomeUrls(archiveHomeUrls);
	for (const archiveHomeUrl of normalizedHomeUrls) {
		const homeAttempt = {
			home_url: archiveHomeUrl,
			search_url: null,
			title: null,
			access_limited: null,
			body_preview: null,
			snapshot_candidates: [],
			success: false,
			error: null,
		};
		manifest.home_attempts.push(homeAttempt);

		try {
			await gotoTolerant(tab, archiveHomeUrl, navigationTimeoutMs);
			const homeState = await readPageState(tab);
			homeAttempt.title = homeState.title;
			homeAttempt.access_limited = isAccessLimitedPage(homeState);
			homeAttempt.body_preview = homeState.body_preview;
			if (homeAttempt.access_limited) {
				throw new Error(`Archive home access-limited at ${archiveHomeUrl}: ${homeState.title || homeState.body_preview.slice(0, 120)}`);
			}

			await fillArchiveSearchForm(tab, originalUrl, navigationTimeoutMs);
			const searchPage = await readArchiveSearchPage(tab);
			manifest.search_page = searchPage;
			homeAttempt.search_url = searchPage.url;
			homeAttempt.title = searchPage.title;
			homeAttempt.access_limited = isAccessLimitedPage(searchPage);
			homeAttempt.body_preview = searchPage.body_preview;
			if (homeAttempt.access_limited) {
				throw new Error(`Archive search access-limited at ${searchPage.url}: ${searchPage.title || searchPage.body_preview.slice(0, 120)}`);
			}

			const snapshotCandidates = chooseSnapshotCandidates(searchPage.links).slice(0, maxSnapshots);
			homeAttempt.snapshot_candidates = snapshotCandidates.map((candidate) => ({
				href: candidate.href,
				text: candidate.text,
				date_score: candidate.dateScore,
			}));
			if (!snapshotCandidates.length) {
				throw new Error('No archive snapshot links found on archive search results page');
			}

			const snapshotResult = await trySnapshotCandidates({
				tab,
				manifest,
				snapshotCandidates,
				minMarkdownChars,
				navigationTimeoutMs,
			});
			if (snapshotResult.extraction) {
				homeAttempt.success = true;
				manifest.success = true;
				manifest.finished_at = new Date().toISOString();
				return { manifest, extraction: snapshotResult.extraction };
			}
		} catch (error) {
			homeAttempt.error = String(error?.stack || error);
		}
	}

	manifest.error = manifest.snapshot_attempts.length
		? 'Archive snapshots were found, but none yielded enough non-access-limited article Markdown'
		: 'No archive home mirror yielded searchable snapshot results';
	manifest.finished_at = new Date().toISOString();
	return { manifest, extraction: null };
}

export async function repeatArchiveIsChromeFlow({
	tab,
	originalUrl,
	runs = 3,
	minMarkdownChars = 1000,
	maxSnapshots = 5,
	navigationTimeoutMs = 30000,
	archiveHomeUrls = ARCHIVE_HOME_URLS,
} = {}) {
	const results = [];
	for (let index = 0; index < runs; index += 1) {
		results.push(
			await runArchiveIsChromeFlow({
				tab,
				originalUrl,
				minMarkdownChars,
				maxSnapshots,
				navigationTimeoutMs,
				archiveHomeUrls,
			}),
		);
	}
	return {
		success: results.every((result) => result.manifest.success),
		runs: results.map((result) => result.manifest),
		last_extraction: results.at(-1)?.extraction || null,
	};
}

async function trySnapshotCandidates({
	tab,
	manifest,
	snapshotCandidates,
	minMarkdownChars,
	navigationTimeoutMs,
}) {
	for (const candidate of snapshotCandidates) {
		const attempt = {
			snapshot_url: candidate.href,
			label: candidate.text,
			date_score: candidate.dateScore,
			success: false,
			access_limited: null,
			markdown_length: 0,
			title: null,
			error: null,
		};
		manifest.snapshot_attempts.push(attempt);

		try {
			await gotoTolerant(tab, candidate.href, navigationTimeoutMs);
			await waitForReadableBody(tab);
			const extraction = await tab.playwright.evaluate(extractArticleFromDom);
			attempt.access_limited = extraction.access_limited;
			attempt.markdown_length = extraction.markdown_length;
			attempt.title = extraction.title;

			if (!extraction.access_limited && extraction.markdown_length >= minMarkdownChars) {
				attempt.success = true;
				manifest.selected_snapshot_url = candidate.href;
				return { extraction };
			}
		} catch (error) {
			attempt.error = String(error?.stack || error);
		}
	}
	return { extraction: null };
}

async function fillArchiveSearchForm(tab, originalUrl, navigationTimeoutMs) {
	const searchInput = await locateUniqueArchiveSearchInput(tab);
	await searchInput.fill(originalUrl);
	await pressEnterAndWait(tab, searchInput, navigationTimeoutMs);

	const state = await readArchiveSearchPage(tab);
	if (chooseSnapshotCandidates(state.links).length || state.url.includes('/search/') || state.url.includes(encodeURIComponent(originalUrl))) return;

	const submit = await locateUniqueArchiveSearchSubmit(tab);
	if (submit) {
		await clickAndWait(tab, submit, navigationTimeoutMs);
	}
}

async function readArchiveSearchPage(tab) {
	return await tab.playwright.evaluate(() => ({
		url: location.href,
		title: document.title,
		body_preview: (document.body?.innerText || '').slice(0, 2000),
		links: Array.from(document.querySelectorAll('a'))
			.map((anchor) => ({
				text: (anchor.textContent || '').trim(),
				href: anchor.href,
			}))
			.filter((link) => link.href),
	}));
}

async function readPageState(tab) {
	return await tab.playwright.evaluate(() => ({
		url: location.href,
		title: document.title,
		body_preview: (document.body?.innerText || '').slice(0, 2000),
		inputs: Array.from(document.querySelectorAll('input, textarea'))
			.slice(0, 40)
			.map((input) => ({
				tag: input.tagName.toLowerCase(),
				id: input.id || '',
				name: input.getAttribute('name') || '',
				type: input.getAttribute('type') || '',
				placeholder: input.getAttribute('placeholder') || '',
				value: input.getAttribute('value') || '',
			})),
	}));
}

async function locateUniqueArchiveSearchInput(tab) {
	const selectors = [
		'#q',
		'input[name="q"]',
		'textarea[name="q"]',
		'form[action*="search"] input[type="text"]',
		'form[action*="search"] input:not([type])',
		'form[action*="search"] textarea',
	];
	for (const selector of selectors) {
		const locator = tab.playwright.locator(selector);
		const count = await locator.count().catch(() => 0);
		if (count === 1) return locator;
	}

	const state = await readPageState(tab);
	throw new Error(`Missing unique archive search input. Inputs seen: ${JSON.stringify(state.inputs)}`);
}

async function locateUniqueArchiveSearchSubmit(tab) {
	const selectors = [
		'form[action$="/search/"] input[type="submit"]',
		'form[action*="search"] input[type="submit"]',
		'form[action*="search"] button[type="submit"]',
	];
	for (const selector of selectors) {
		const locator = tab.playwright.locator(selector);
		const count = await locator.count().catch(() => 0);
		if (count === 1) return locator;
	}
	return null;
}

async function pressEnterAndWait(tab, locator, navigationTimeoutMs) {
	await tab.playwright
		.expectNavigation(() => locator.press('Enter'), { timeoutMs: navigationTimeoutMs, waitUntil: 'domcontentloaded' })
		.catch(async () => {
			await locator.press('Enter').catch(() => {});
		});
	await tab.playwright.waitForLoadState({ state: 'domcontentloaded', timeoutMs: navigationTimeoutMs }).catch(() => {});
}

async function clickAndWait(tab, locator, navigationTimeoutMs) {
	await tab.playwright
		.expectNavigation(() => locator.click({ timeoutMs: 5000 }), { timeoutMs: navigationTimeoutMs, waitUntil: 'domcontentloaded' })
		.catch(async () => {
			await locator.click({ timeoutMs: 5000 }).catch(() => {});
		});
	await tab.playwright.waitForLoadState({ state: 'domcontentloaded', timeoutMs: navigationTimeoutMs }).catch(() => {});
}

function isAccessLimitedPage(pageState) {
	return ACCESS_LIMIT_RE.test(`${pageState?.title || ''}\n${pageState?.body_preview || ''}`);
}

function chooseSnapshotCandidates(links) {
	const candidatesByHref = new Map();
	for (const link of links) {
		if (!SHORT_ARCHIVE_RE.test(link.href)) continue;
		const parsedDate = parseArchiveDateScore(link.text);
		const existing = candidatesByHref.get(link.href);
		const candidate = {
			text: link.text,
			href: link.href,
			dateScore: parsedDate,
		};
		if (!existing || candidate.dateScore > existing.dateScore || (candidate.dateScore === existing.dateScore && candidate.text.length > existing.text.length)) {
			candidatesByHref.set(link.href, candidate);
		}
	}
	return Array.from(candidatesByHref.values()).sort((a, b) => {
		if (b.dateScore !== a.dateScore) return b.dateScore - a.dateScore;
		return b.text.length - a.text.length;
	});
}

function parseArchiveDateScore(text) {
	const trimmed = (text || '').trim();
	const parsed = Date.parse(`${trimmed} UTC`);
	if (!Number.isNaN(parsed)) return parsed;
	const chineseMatch = trimmed.match(/(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{2})(?::(\d{2}))?/);
	if (chineseMatch) {
		const [, year, month, day, hour, minute, second = '0'] = chineseMatch;
		return Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second));
	}
	return 0;
}

function normalizeArchiveHomeUrls(archiveHomeUrls) {
	const values = Array.isArray(archiveHomeUrls) && archiveHomeUrls.length ? archiveHomeUrls : ARCHIVE_HOME_URLS;
	const normalized = [];
	for (const value of values) {
		const url = String(value || '').trim();
		if (!url) continue;
		normalized.push(url.endsWith('/') ? url : `${url}/`);
	}
	return Array.from(new Set(normalized));
}

async function gotoTolerant(tab, url, navigationTimeoutMs) {
	await tab.goto(url).catch(() => {});
	await tab.playwright.waitForLoadState({ state: 'load', timeoutMs: navigationTimeoutMs }).catch(() => {});
}

async function waitForReadableBody(tab) {
	for (let attempt = 0; attempt < 6; attempt += 1) {
		const state = await tab.playwright.evaluate(() => ({
			title: document.title,
			bodyLength: (document.body?.innerText || '').length,
			bodyPreview: (document.body?.innerText || '').slice(0, 500),
		}));
		if (state.bodyLength > 1000 || /captcha|one more step|security verification/i.test(`${state.title}\n${state.bodyPreview}`)) return;
		await new Promise((resolve) => setTimeout(resolve, 1000));
	}
}
