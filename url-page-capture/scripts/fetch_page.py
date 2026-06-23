#!/usr/bin/env python3
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


DEFAULT_USER_AGENT = (
	'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
	'AppleWebKit/537.36 (KHTML, like Gecko) '
	'Chrome/125.0.0.0 Safari/537.36 url-to-markdown-skill/0.1'
)
BLOCKED_STATUS_CODES = {401, 403, 407, 429}
ARCHIVE_HOSTS = {'archive.today', 'archive.is', 'archive.ph', 'archive.md', 'archive.vn', 'archive.fo', 'archive.li'}
LINK_RE = re.compile(r'<(?P<url>[^>]+)>;\s*rel="(?P<rel>[^"]+)"(?:;\s*datetime="(?P<datetime>[^"]+)")?')
ACCESS_LIMIT_RE = re.compile(
	r'captcha|security verification|one more step|checking your browser|verify you are human|'
	r'subscribe to read|subscribe to continue|sign in to read|paywall|enable javascript',
	re.I,
)


class VisibleTextParser(HTMLParser):
	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.title = ''
		self.metadata: dict[str, str] = {}
		self._parts: list[str] = []
		self._skip_depth = 0
		self._capture_title = False

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		attrs_map = {name.lower(): value or '' for name, value in attrs}
		if tag in {'script', 'style', 'noscript', 'svg', 'canvas'}:
			self._skip_depth += 1
			return
		if tag == 'title':
			self._capture_title = True
		if tag == 'meta':
			self._capture_meta(attrs_map)
		if tag in {'p', 'br', 'div', 'section', 'article', 'main', 'header', 'footer', 'li', 'tr'} or re.fullmatch(r'h[1-6]', tag):
			self._parts.append('\n')

	def handle_endtag(self, tag: str) -> None:
		if tag in {'script', 'style', 'noscript', 'svg', 'canvas'} and self._skip_depth:
			self._skip_depth -= 1
			return
		if tag == 'title':
			self._capture_title = False
		if tag in {'p', 'div', 'section', 'article', 'main', 'li', 'tr'} or re.fullmatch(r'h[1-6]', tag):
			self._parts.append('\n')

	def handle_data(self, data: str) -> None:
		if self._skip_depth:
			return
		text = clean_space(data)
		if not text:
			return
		if self._capture_title:
			self.title = clean_space(f'{self.title} {text}')
		self._parts.append(text)
		self._parts.append(' ')

	def visible_text(self) -> str:
		text = ''.join(self._parts)
		text = re.sub(r'[ \t\f\v]+', ' ', text)
		text = re.sub(r' *\n *', '\n', text)
		text = re.sub(r'\n{3,}', '\n\n', text)
		return unescape(text).strip()

	def _capture_meta(self, attrs: dict[str, str]) -> None:
		content = clean_space(attrs.get('content', ''))
		if not content:
			return
		key = attrs.get('property') or attrs.get('name') or attrs.get('itemprop')
		if not key:
			return
		key = key.lower()
		interesting = {
			'og:title',
			'twitter:title',
			'description',
			'og:description',
			'twitter:description',
			'author',
			'article:author',
			'article:published_time',
			'og:site_name',
		}
		if key in interesting:
			self.metadata[key] = content


def main() -> int:
	args = parse_args()
	result = collect_material(args)
	text = json.dumps(result, ensure_ascii=False, indent=2)
	if args.output:
		with open(args.output, 'w', encoding='utf-8') as file:
			file.write(text)
			file.write('\n')
	else:
		print(text)
	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description='Fetch direct webpage material and optional archive.today Memento snapshots.')
	parser.add_argument('url')
	parser.add_argument('--output', '-o')
	parser.add_argument('--archive', choices=('auto', 'always', 'never'), default='auto')
	parser.add_argument('--archive-base-url', default='https://archive.today')
	parser.add_argument('--snapshots', type=int, default=5)
	parser.add_argument('--timeout', type=float, default=20)
	parser.add_argument('--max-chars', type=int, default=200_000)
	parser.add_argument('--user-agent', default=DEFAULT_USER_AGENT)
	parser.add_argument('--no-html', action='store_true')
	return parser.parse_args()


def collect_material(args: argparse.Namespace) -> dict[str, Any]:
	input_url = args.url.strip()
	if not is_http_url(input_url):
		raise SystemExit(f'URL must be absolute http(s): {input_url}')

	direct = fetch_candidate(
		kind='direct',
		url=input_url,
		timeout=args.timeout,
		user_agent=args.user_agent,
		max_chars=args.max_chars,
		include_html=not args.no_html,
	)
	candidates = [direct]
	archive_mementos: list[dict[str, str | None]] = []

	should_fetch_archive = args.archive == 'always' or (args.archive == 'auto' and should_try_archive(direct))
	if should_fetch_archive:
		archive_mementos = fetch_archive_mementos(
			base_url=args.archive_base_url,
			original_url=input_url,
			timeout=args.timeout,
			user_agent=args.user_agent,
		)
		for memento in reversed(archive_mementos[-max(1, args.snapshots) :]):
			candidate = fetch_candidate(
				kind='archive',
				url=str(memento['url']),
				timeout=args.timeout,
				user_agent=args.user_agent,
				max_chars=args.max_chars,
				include_html=not args.no_html,
			)
			candidate['archive_datetime'] = memento.get('datetime')
			candidates.append(candidate)

	return {
		'input_url': input_url,
		'generated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
		'archive_base_url': args.archive_base_url,
		'candidates': candidates,
		'archive_mementos': archive_mementos,
	}


def fetch_candidate(kind: str, url: str, timeout: float, user_agent: str, max_chars: int, include_html: bool) -> dict[str, Any]:
	response = fetch_url(url=url, timeout=timeout, user_agent=user_agent, max_chars=max_chars)
	html = response.get('text') or ''
	content_type = str(response.get('content_type') or '')
	parser = VisibleTextParser()
	if html:
		try:
			parser.feed(html)
		except Exception:
			pass
	visible_text = parser.visible_text()
	title = parser.metadata.get('og:title') or parser.metadata.get('twitter:title') or parser.title or None
	access_limited = bool(response.get('status_code') in BLOCKED_STATUS_CODES or ACCESS_LIMIT_RE.search(f'{title or ""}\n{visible_text[:5000]}\n{html[:5000]}'))
	ok = bool(response.get('status_code') and int(response['status_code']) < 400 and is_probably_html(content_type) and not access_limited)
	candidate: dict[str, Any] = {
		'kind': kind,
		'url': url,
		'final_url': response.get('final_url'),
		'status_code': response.get('status_code'),
		'content_type': content_type,
		'ok': ok,
		'access_limited': access_limited,
		'title': title,
		'metadata': parser.metadata,
		'visible_text': truncate(visible_text, max_chars),
		'error': response.get('error'),
	}
	if include_html:
		candidate['html'] = truncate(html, max_chars)
	return candidate


def fetch_url(url: str, timeout: float, user_agent: str, max_chars: int) -> dict[str, Any]:
	request = Request(
		url,
		headers={
			'User-Agent': user_agent,
			'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
			'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
		},
	)
	try:
		with urlopen(request, timeout=timeout) as response:
			body = response.read(max_chars * 4 + 4096)
			content_type = response.headers.get('content-type', '')
			return {
				'status_code': response.status,
				'final_url': response.geturl(),
				'content_type': content_type,
				'text': decode_body(body, content_type),
				'error': None,
			}
	except HTTPError as error:
		body = error.read(max_chars * 4 + 4096)
		content_type = error.headers.get('content-type', '') if error.headers else ''
		return {
			'status_code': error.code,
			'final_url': error.geturl(),
			'content_type': content_type,
			'text': decode_body(body, content_type),
			'error': f'HTTPError: {error.code} {error.reason}',
		}
	except URLError as error:
		return {
			'status_code': None,
			'final_url': url,
			'content_type': '',
			'text': '',
			'error': f'URLError: {error.reason}',
		}


def fetch_archive_mementos(base_url: str, original_url: str, timeout: float, user_agent: str) -> list[dict[str, str | None]]:
	timemap_url = f'{base_url.rstrip("/")}/timemap/{quote(original_url, safe=":/?#[]@!$&\'()*+,;=%")}'
	response = fetch_url(url=timemap_url, timeout=timeout, user_agent=user_agent, max_chars=500_000)
	text = str(response.get('text') or '')
	mementos: list[dict[str, str | None]] = []
	for match in LINK_RE.finditer(text):
		rel = match.group('rel').lower()
		if 'memento' not in rel:
			continue
		mementos.append(
			{
				'url': normalize_archive_url(match.group('url'), base_url),
				'datetime': match.group('datetime'),
			}
		)
	return mementos


def normalize_archive_url(url: str, base_url: str) -> str:
	parsed = urlparse(url)
	base = urlparse(base_url)
	if parsed.scheme == 'http' and base.scheme == 'https' and parsed.hostname in ARCHIVE_HOSTS:
		return f'https://{url.removeprefix("http://")}'
	return url


def should_try_archive(candidate: dict[str, Any]) -> bool:
	status_code = candidate.get('status_code')
	if status_code in BLOCKED_STATUS_CODES:
		return True
	if status_code is None or int(status_code) >= 400:
		return True
	if candidate.get('access_limited'):
		return True
	visible_text = str(candidate.get('visible_text') or '')
	return len(visible_text) < 500


def is_http_url(url: str) -> bool:
	parsed = urlparse(url)
	return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)


def is_probably_html(content_type: str) -> bool:
	content_type = content_type.lower()
	return not content_type or 'text/html' in content_type or 'application/xhtml+xml' in content_type or 'text/plain' in content_type


def decode_body(body: bytes, content_type: str) -> str:
	charset_match = re.search(r'charset=([^;\s]+)', content_type, re.I)
	charset = charset_match.group(1).strip('"') if charset_match else 'utf-8'
	try:
		return body.decode(charset, errors='replace')
	except LookupError:
		return body.decode('utf-8', errors='replace')


def clean_space(value: str) -> str:
	return re.sub(r'\s+', ' ', value).strip()


def truncate(value: str, max_chars: int) -> str:
	if len(value) <= max_chars:
		return value
	return value[:max_chars] + '\n...[truncated]'


if __name__ == '__main__':
	sys.exit(main())
