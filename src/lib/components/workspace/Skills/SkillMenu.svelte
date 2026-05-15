<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');

	export let onClose: Function;

	let show = false;
</script>

<!-- 
  Skills menu disabled - remote API usage only supports toggle
  Delete, edit, clone, and export operations are not available
-->
<div></div>
