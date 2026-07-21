<script>
	import { goto } from '$lib/navigation';
	import { onMount } from 'svelte';
	import Settings from '$lib/components/admin/Settings.svelte';

	onMount(() => {
		goto('/admin/settings/general');
	});
</script>

<Settings />
