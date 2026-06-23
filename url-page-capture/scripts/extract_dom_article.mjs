export default () => {
	const NON_CONTENT_SELECTOR = [
		'script',
		'style',
		'noscript',
		'svg',
		'canvas',
		'iframe',
		'form',
		'nav',
		'footer',
		'header',
		'aside',
		'[role="navigation"]',
		'[role="banner"]',
		'[role="complementary"]',
	].join(',');
	const CONTENT_SELECTORS = [
		'article',
		'main article',
		'[role="main"] article',
		'main',
		'[role="main"]',
		'[itemtype*="Article"]',
		'[data-testid*="article-body"]',
		'[data-component*="article-body"]',
		'[class*="article-body"]',
		'[class*="article__body"]',
		'[class*="story-body"]',
		'[class*="entry-content"]',
		'[class*="post-content"]',
		'[class*="article-content"]',
		'[class*="articleBody"]',
		'[id*="article-body"]',
		'[id*="story-body"]',
	];
	const NOISE_RE = /(advert|ad-|ads-|promo|related|share|social|newsletter|subscribe|signin|sign-in|cookie|comment|footer|nav|sidebar)/i;
	const CONTENT_RE = /(article|story|post|entry|content|body|main)/i;
	const ACCESS_LIMIT_RE = /captcha|security verification|one more step|checking your browser|verify you are human|subscribe to read|subscribe to continue|sign in to read|paywall|enable javascript/i;

	function cleanText(value) {
		return (value || '').replace(/\s+/g, ' ').trim();
	}

	function nodeAttrs(node) {
		const values = [node.tagName || ''];
		for (const key of ['id', 'class', 'role', 'data-testid', 'data-component', 'aria-label']) {
			const value = node.getAttribute?.(key);
			if (value) values.push(value);
		}
		return values.join(' ');
	}

	function metadata() {
		const pick = (...selectors) => {
			for (const selector of selectors) {
				const node = document.querySelector(selector);
				const content = node?.getAttribute('content');
				if (content && cleanText(content)) return cleanText(content);
			}
			return null;
		};
		const h1 = cleanText(document.querySelector('h1')?.textContent || '');
		return {
			title:
				pick('meta[property="og:title"]', 'meta[name="twitter:title"]', 'meta[name="parsely-title"]') ||
				h1 ||
				cleanText(document.title),
			byline:
				pick('meta[name="author"]', 'meta[property="article:author"]', 'meta[name="parsely-author"]') ||
				cleanText(document.querySelector('[rel="author"], [itemprop="author"], [class*="byline"], [data-testid*="byline"]')?.textContent || '') ||
				null,
			published_at: pick(
				'meta[property="article:published_time"]',
				'meta[name="article:published_time"]',
				'meta[name="parsely-pub-date"]',
				'meta[name="date"]',
				'meta[name="pubdate"]',
			),
			site_name: pick('meta[property="og:site_name"]', 'meta[name="application-name"]'),
			description: pick('meta[name="description"]', 'meta[property="og:description"]', 'meta[name="twitter:description"]'),
		};
	}

	function scoreCandidate(node) {
		const text = cleanText(node.textContent || '');
		if (!text) return 0;
		const paragraphs = Array.from(node.querySelectorAll('p')).filter((p) => cleanText(p.textContent || ''));
		const paragraphTextLen = paragraphs.reduce((sum, p) => sum + cleanText(p.textContent || '').length, 0);
		const linkTextLen = Array.from(node.querySelectorAll('a')).reduce((sum, a) => sum + cleanText(a.textContent || '').length, 0);
		const linkDensity = linkTextLen / Math.max(text.length, 1);
		const attrs = nodeAttrs(node);
		let score = paragraphTextLen + paragraphs.length * 80;
		if (node.tagName?.toLowerCase() === 'article') score += 500;
		if (CONTENT_RE.test(attrs)) score += 250;
		if (NOISE_RE.test(attrs)) score -= 800;
		score *= Math.max(0.1, 1 - Math.min(linkDensity, 0.9));
		return score;
	}

	function markdownFromNode(node, title) {
		const lines = [];
		const walk = (current, listDepth = 0) => {
			if (current.nodeType === 3) {
				const text = cleanText(current.textContent || '');
				if (text) lines.push(text);
				return;
			}
			if (current.nodeType !== 1) return;
			const tag = current.tagName.toLowerCase();
			if (['script', 'style', 'noscript', 'svg', 'canvas', 'iframe'].includes(tag)) return;
			if (current.matches?.(NON_CONTENT_SELECTOR) || NOISE_RE.test(nodeAttrs(current))) return;
			if (/h[1-6]/.test(tag)) {
				const level = Number(tag.slice(1));
				const text = cleanText(current.textContent || '');
				if (text) lines.push(`\n${'#'.repeat(level)} ${text}\n`);
				return;
			}
			if (tag === 'p') {
				const text = cleanText(current.textContent || '');
				if (text) lines.push(`\n${text}\n`);
				return;
			}
			if (tag === 'li') {
				const text = cleanText(current.textContent || '');
				if (text) lines.push(`${'  '.repeat(listDepth)}- ${text}\n`);
				return;
			}
			if (tag === 'blockquote') {
				const text = cleanText(current.textContent || '');
				if (text) lines.push(`\n> ${text}\n`);
				return;
			}
			if (tag === 'pre' || tag === 'code') {
				const text = (current.textContent || '').trim();
				if (text) lines.push(`\n\`\`\`\n${text}\n\`\`\`\n`);
				return;
			}
			if (tag === 'br') {
				lines.push('\n');
				return;
			}
			const nextDepth = tag === 'ul' || tag === 'ol' ? listDepth + 1 : listDepth;
			for (const child of current.childNodes) walk(child, nextDepth);
			if (['div', 'section', 'article', 'main'].includes(tag)) lines.push('\n');
		};
		walk(node);
		let markdown = lines
			.join(' ')
			.replace(/[ \t]+\n/g, '\n')
			.replace(/\n[ \t]+/g, '\n')
			.replace(/[ \t]{2,}/g, ' ')
			.replace(/\n{3,}/g, '\n\n')
			.trim();
		if (title && markdown && !markdown.replace(/^#+\s*/, '').startsWith(title)) {
			markdown = `# ${title}\n\n${markdown}`;
		}
		return postprocessMarkdown(markdown, title);
	}

	function plainTextFromNode(node, title) {
		const lines = [];
		const walk = (current, listDepth = 0) => {
			if (current.nodeType === 3) {
				const text = cleanText(current.textContent || '');
				if (text) lines.push(text);
				return;
			}
			if (current.nodeType !== 1) return;
			const tag = current.tagName.toLowerCase();
			if (['script', 'style', 'noscript', 'svg', 'canvas', 'iframe'].includes(tag)) return;
			if (current.matches?.(NON_CONTENT_SELECTOR) || NOISE_RE.test(nodeAttrs(current))) return;
			if (/h[1-6]/.test(tag) || tag === 'p' || tag === 'blockquote') {
				const text = cleanText(current.textContent || '');
				if (text) lines.push(text);
				return;
			}
			if (tag === 'li') {
				const text = cleanText(current.textContent || '');
				if (text) lines.push(`${'  '.repeat(listDepth)}- ${text}`);
				return;
			}
			if (tag === 'br') {
				lines.push('');
				return;
			}
			const nextDepth = tag === 'ul' || tag === 'ol' ? listDepth + 1 : listDepth;
			for (const child of current.childNodes) walk(child, nextDepth);
			if (['div', 'section', 'article', 'main'].includes(tag)) lines.push('');
		};
		walk(node);
		let text = postprocessPlainText(lines.join('\n'), title);
		if (title && text && !text.toLowerCase().startsWith(title.toLowerCase())) {
			text = `${title}\n\n${text}`;
		}
		return text;
	}

	function postprocessMarkdown(markdown, title) {
		const cleanedLines = [];
		let blankPending = false;
		for (const rawLine of markdown.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')) {
			const line = rawLine.trim();
			if (!line) {
				blankPending = cleanedLines.length > 0;
				continue;
			}
			if (isNoiseMarkdownLine(line, title)) continue;
			if (blankPending) {
				cleanedLines.push('');
				blankPending = false;
			}
			cleanedLines.push(line);
		}
		return cleanedLines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
	}

	function postprocessPlainText(text, title) {
		const cleanedLines = [];
		let blankPending = false;
		for (const rawLine of (text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')) {
			const line = cleanText(rawLine);
			if (!line) {
				blankPending = cleanedLines.length > 0;
				continue;
			}
			if (isNoiseMarkdownLine(line, title)) continue;
			if (blankPending) {
				cleanedLines.push('');
				blankPending = false;
			}
			cleanedLines.push(line);
		}
		return cleanedLines.join('\n').replace(/\n{3,}/g, '\n\n').trim();
	}

	function isNoiseMarkdownLine(line, title) {
		const plain = line.replace(/^[#>*\-\s]+/, '').trim();
		const lower = plain.toLowerCase();
		const titleLower = (title || '').toLowerCase();
		if (!plain) return true;
		if (/^current progress\s+\d+%$/i.test(plain)) return true;
		if (/^-?\s*(save|print this page|copy link|share|listen to article|add to myft)$/i.test(line)) return true;
		if (/^(accessibility help|skip to navigation|skip to main content|skip to footer|ft professional|open side navigation menu|open search bar|ask ft)$/i.test(plain)) return true;
		if (/^follow the topics in this article$/i.test(plain)) return true;
		if (/^comments$/i.test(plain)) return true;
		if (/^subscribe to read$/i.test(plain)) return true;
		if (/^sign in$/i.test(plain)) return true;
		if (/^advertisement$/i.test(plain)) return true;
		if (titleLower && lower.startsWith(titleLower) && /\bon (x|facebook|linkedin|whatsapp)\b/i.test(lower)) return true;
		if (/\(opens in a new window\)$/i.test(plain) && /\b(x|facebook|linkedin|whatsapp)\b/i.test(plain)) return true;
		return false;
	}

	function bestCandidate() {
		const candidates = [];
		for (const selector of CONTENT_SELECTORS) {
			document.querySelectorAll(selector).forEach((node) => candidates.push(node));
		}
		if (document.querySelector('body')) candidates.push(document.querySelector('body'));
		const scored = candidates
			.map((node) => ({ node, score: scoreCandidate(node), textLength: cleanText(node.textContent || '').length }))
			.filter((item) => item.score > 0)
			.sort((a, b) => b.score - a.score);
		return scored[0] || null;
	}

	const meta = metadata();
	const bodyText = cleanText(document.body?.innerText || '');
	const accessLimited = ACCESS_LIMIT_RE.test(`${document.title}\n${bodyText.slice(0, 5000)}`);
	const candidate = bestCandidate();
	const markdown = candidate ? markdownFromNode(candidate.node, meta.title) : '';
	const contentText = candidate ? plainTextFromNode(candidate.node, meta.title) : postprocessPlainText(bodyText, meta.title);
	return {
		url: location.href,
		title: meta.title,
		metadata: meta,
		access_limited: accessLimited,
		candidate_score: candidate?.score || 0,
		text_length: bodyText.length,
		content_text_length: contentText.length,
		content_text: contentText,
		markdown_length: markdown.length,
		markdown,
		body_preview: bodyText.slice(0, 1000),
	};
};
