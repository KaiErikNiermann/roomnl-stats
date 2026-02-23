import js from '@eslint/js';
import svelte from 'eslint-plugin-svelte';
import sonarjs from 'eslint-plugin-sonarjs';
import unicorn from 'eslint-plugin-unicorn';
import security from 'eslint-plugin-security';
import ts from 'typescript-eslint';
import globals from 'globals';

export default ts.config(
	js.configs.recommended,
	...ts.configs.strict,
	...ts.configs.stylistic,
	...svelte.configs.recommended,
	sonarjs.configs.recommended,
	unicorn.configs.recommended,
	security.configs.recommended,
	{
		languageOptions: {
			globals: {
				...globals.browser,
				...globals.node,
			},
		},
		rules: {
			'unicorn/filename-case': ['error', { cases: { kebabCase: true, pascalCase: true } }],
			'unicorn/prevent-abbreviations': 'off',
			'unicorn/no-null': 'off',
		},
	},
	{
		files: ['**/*.svelte', '**/*.svelte.ts', '**/*.svelte.js'],
		languageOptions: {
			parserOptions: {
				parser: ts.parser,
			},
		},
	},
	{
		files: ['**/*.d.ts'],
		rules: {
			'unicorn/require-module-specifiers': 'off',
		},
	},
	{
		files: ['**/components/*Chart.svelte', '**/components/*Widget.svelte'],
		rules: {
			'svelte/no-dom-manipulating': 'off',
		},
	},
	{
		ignores: ['build/', '.svelte-kit/', 'dist/', 'node_modules/'],
	},
);
