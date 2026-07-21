import { browser } from '$app/environment';
import { base } from '$app/paths';

function hasScheme(value: string): boolean {
	return /^[a-z][a-z\d+\-.]*:/i.test(value) || value.startsWith('//');
}

function shouldPrefix(pathname: string): boolean {
	return !!base && pathname.startsWith('/') && !pathname.startsWith(`${base}/`) && pathname !== base;
}

export function withBasePath(path: string): string {
	if (!browser || !base || hasScheme(path)) return path;
	if (!path.startsWith('/')) return path;
	return shouldPrefix(path) ? `${base}${path}` : path;
}

function prefixUrl(value: string | URL | null | undefined): string | URL | null | undefined {
	if (!browser || !base || value == null) return value;
	const raw = String(value);

	if (raw.startsWith('/')) {
		return withBasePath(raw);
	}

	try {
		const url = new URL(raw, window.location.href);
		if (url.origin === window.location.origin && shouldPrefix(url.pathname)) {
			url.pathname = `${base}${url.pathname}`;
			return url.toString();
		}
	} catch {
		// Leave non-URL values untouched.
	}

	return value;
}

export function installBasePathGuard(): void {
	if (!browser || !base) return;
	const marker = '__openWebUIBasePathGuardInstalled';
	if ((globalThis as unknown as Record<string, boolean>)[marker]) return;
	(globalThis as unknown as Record<string, boolean>)[marker] = true;
	(globalThis as unknown as Record<string, string>).__WEBUI_BASE_PATH__ = base;

	const originalFetch = window.fetch.bind(window);
	window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
		if (typeof input === 'string' || input instanceof URL) {
			return originalFetch(prefixUrl(input) as string | URL, init);
		}
		return originalFetch(input, init);
	}) as typeof window.fetch;

	const OriginalWebSocket = window.WebSocket;
	window.WebSocket = new Proxy(OriginalWebSocket, {
		construct(target, args) {
			args[0] = prefixUrl(args[0] as string) as string;
			return Reflect.construct(target, args);
		}
	});

	if ('EventSource' in window) {
		const OriginalEventSource = window.EventSource;
		window.EventSource = new Proxy(OriginalEventSource, {
			construct(target, args) {
				args[0] = prefixUrl(args[0] as string) as string;
				return Reflect.construct(target, args);
			}
		});
	}

	const patchHistory = (name: 'pushState' | 'replaceState') => {
		const original = history[name].bind(history);
		history[name] = ((data: unknown, unused: string, url?: string | URL | null) => {
			return original(data, unused, prefixUrl(url) as string | URL | null | undefined);
		}) as History[typeof name];
	};
	patchHistory('pushState');
	patchHistory('replaceState');

	const originalOpen = window.open.bind(window);
	window.open = ((url?: string | URL, target?: string, features?: string) => {
		return originalOpen(prefixUrl(url) as string | URL | undefined, target, features);
	}) as typeof window.open;

	document.addEventListener(
		'click',
		(event) => {
			const anchor = (event.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null;
			if (!anchor) return;
			const url = new URL(anchor.href, window.location.href);
			if (url.origin !== window.location.origin || !shouldPrefix(url.pathname)) return;
			url.pathname = `${base}${url.pathname}`;
			anchor.href = url.toString();
		},
		true
	);

	document.addEventListener(
		'error',
		(event) => {
			const img = event.target as HTMLImageElement | null;
			if (!img || img.tagName !== 'IMG') return;
			const src = new URL(img.src, window.location.href);
			if (src.origin !== window.location.origin) return;

			const fallback = `${base}/static/favicon.png`;
			if (src.pathname === fallback) {
				event.stopImmediatePropagation();
				return;
			}

			if (src.pathname === '/favicon.png' || shouldPrefix(src.pathname)) {
				event.stopImmediatePropagation();
				img.src = fallback;
			}
		},
		true
	);
}
