<script>
	import { goto } from '$lib/navigation';
	import { onMount } from 'svelte';

	onMount(async () => {
		await goto('/admin/users/overview');
	});
</script>
