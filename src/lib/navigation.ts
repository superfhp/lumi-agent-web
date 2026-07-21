import { goto as svelteGoto } from '$app/navigation';
export {
	afterNavigate,
	beforeNavigate,
	disableScrollHandling,
	invalidate,
	invalidateAll,
	preloadCode,
	preloadData,
	pushState,
	replaceState
} from '$app/navigation';

import { withBasePath } from '$lib/base-path-guard';

export function goto(url: string | URL, opts?: Parameters<typeof svelteGoto>[1]) {
	return svelteGoto(withBasePath(String(url)), opts);
}
