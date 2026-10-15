<script lang="ts">
	import type { Advice } from '$lib/api';

	let { advice, onclose }: { advice: Advice[]; onclose: () => void } = $props();

	const ICONS: Record<Advice['id'], string> = {
		water: '💧',
		hat: '🧢',
		sunscreen: '🧴',
		umbrella: '☂️'
	};
	let rainy = $derived(advice.some((a) => a.id === 'umbrella'));
</script>

<div class="popup" role="dialog" aria-labelledby="advice-title" aria-modal="false">
	<h2 id="advice-title">{rainy ? 'Rain on the way' : 'Sunny walk ahead'}</h2>
	<ul>
		{#each advice as tip (tip.id)}
			<li>
				<span class="icon" aria-hidden="true">{ICONS[tip.id]}</span>
				<div>
					<strong>{tip.title}</strong>
					<p>{tip.text}</p>
				</div>
			</li>
		{/each}
	</ul>
	<button type="button" onclick={onclose}>Got it</button>
</div>

<style>
	.popup {
		position: absolute;
		left: 50%;
		bottom: calc(max(24px, env(safe-area-inset-bottom)) + 130px);
		transform: translateX(-50%);
		width: min(420px, calc(100% - 24px));
		box-sizing: border-box;
		padding: 14px 16px;
		display: grid;
		gap: 10px;
		background: var(--panel-bg);
		color: var(--panel-fg);
		border-radius: 14px;
		border-left: 5px solid var(--route-sun);
		box-shadow: 0 8px 28px rgb(0 0 0 / 0.28);
		font: 14px/1.35 system-ui, sans-serif;
		animation: rise 0.25s ease-out;
	}
	@keyframes rise {
		from {
			opacity: 0;
			transform: translate(-50%, 12px);
		}
	}
	h2 {
		margin: 0;
		font-size: 16px;
	}
	ul {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 8px;
	}
	li {
		display: flex;
		gap: 10px;
		align-items: flex-start;
	}
	.icon {
		font-size: 22px;
		line-height: 1;
	}
	p {
		margin: 2px 0 0;
		color: var(--panel-muted);
	}
	button {
		justify-self: end;
		font: inherit;
		font-weight: 600;
		padding: 6px 14px;
		border: none;
		border-radius: 8px;
		background: var(--route-shady);
		color: var(--on-accent);
		cursor: pointer;
	}
</style>
