// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');
const globals = require('globals');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*'],
  },
  {
    // Jest test files use describe/test/expect/etc as globals — without
    // this, every __tests__/*.test.js file fails lint with no-undef.
    files: ['**/__tests__/**/*.js', '**/*.test.js'],
    languageOptions: {
      globals: globals.jest,
    },
  },
]);
