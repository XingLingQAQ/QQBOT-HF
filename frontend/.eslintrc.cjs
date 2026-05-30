module.exports = {
  root: true,
  env: { browser: true, es2021: true },
  extends: ["eslint:recommended"],
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: { jsx: true },
  },
  settings: { react: { version: "detect" } },
  rules: {
    "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
  },
  globals: {
    WebSocket: "readonly",
  },
};
