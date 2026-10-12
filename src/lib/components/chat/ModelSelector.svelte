<script lang="ts">
	import { chatId, models, pinnedModels, selectedFolder, settings, user } from '$lib/stores';
	import { getChatById } from '$lib/apis/chats';
	import { getFolderById } from '$lib/apis/folders';
	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Selector from './ModelSelector/Selector.svelte';

	import { updateUserSettings } from '$lib/apis/users';
	import { resolveLocalizedModelName } from '$lib/utils/localizedContent';
	import equal from 'fast-deep-equal';
	const i18n = getContext('i18n');

	export let selectedModels = [''];
	export let disabled = false;

	export let showSetDefault = true;
	export let triggerClassName = 'text-lg';
	export let className = undefined;
	export let placement: 'top' | 'bottom' | 'auto' = 'bottom';
	export let align: 'start' | 'end' = 'start';

	let compareModels = selectedModels.length > 1;
	let selector;

	export const open = () => selector?.open();

	const saveDefaultModel = async () => {
		const hasEmptyModel = selectedModels.filter((it) => it === '');
		if (hasEmptyModel.length) {
			toast.error($i18n.t('Choose a model before saving...'));
			return;
		}
		settings.set({ ...$settings, models: selectedModels });
		await updateUserSettings(localStorage.token, { ui: { models: selectedModels } });

		toast.success($i18n.t('Default model updated'));
	};

	const pinModelHandler = async (modelId) => {
		settings.set({
			...$settings,
			pinnedModels: $pinnedModels.includes(modelId)
				? $pinnedModels.filter((id) => id !== modelId)
				: [...$pinnedModels, modelId]
		});
		await updateUserSettings(localStorage.token, { ui: { pinnedModels: $settings.pinnedModels } });
	};

	// Losus: in a project locked to some agents, list only those. The server enforces it; this only mirrors it.
	let losusAllowed: string[] | null = null;
	const losusResolve = async (folder, id) => {
		if (!folder && id) {
			const chat = await getChatById(localStorage.token, id).catch(() => null);
			folder = chat?.folder_id ? await getFolderById(localStorage.token, chat.folder_id).catch(() => null) : null;
		}
		for (let i = 0; folder && i < 8; i++) {
			if (!folder.parent_id) {
				losusAllowed = folder.data?.losus_locked ? (folder.data.model_ids ?? null) : null;
				return;
			}
			folder = await getFolderById(localStorage.token, folder.parent_id).catch(() => null);
		}
		losusAllowed = null;
	};
	$: losusResolve($selectedFolder, $chatId);
	$: if (losusAllowed && selectedModels.some((id) => !losusAllowed.includes(id))) {
		selectedModels = [...losusAllowed];
	}

	$: if (selectedModels.length > 0 && $models.length > 0) {
		const _selectedModels = selectedModels.map((model) =>
			$models.map((m) => m.id).includes(model) ? model : ''
		);

		if (!equal(_selectedModels, selectedModels)) {
			selectedModels = _selectedModels;
		}
	}

	$: if (selectedModels.length > 1 && !compareModels) {
		compareModels = true;
	}
</script>

<div class="flex min-w-0 max-w-full flex-col items-start">
	<div class="flex min-w-0 max-w-full">
		<div class="min-w-0 max-w-full overflow-hidden">
			<div class="min-w-0 max-w-full">
				<Selector
					bind:this={selector}
					id="model"
					placeholder={$i18n.t('Select a model')}
					items={$models.filter((model) => !losusAllowed || losusAllowed.includes(model.id)).map((model) => ({
						value: model.id,
						label: resolveLocalizedModelName(model, $i18n.language),
						model: model
					}))}
					{pinModelHandler}
					{className}
					{triggerClassName}
					{placement}
					{align}
					{showSetDefault}
					onSetDefault={saveDefaultModel}
					multipleEnabled={$user?.role === 'admin' ||
						($user?.permissions?.chat?.multiple_models ?? true)}
					{disabled}
					bind:compareEnabled={compareModels}
					bind:values={selectedModels}
				/>
			</div>
		</div>
	</div>
</div>
