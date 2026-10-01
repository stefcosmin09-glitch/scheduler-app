module.exports = {
  purge: [
    './app/templates/**/*.html',
    './app/static/app.js'
  ],
  darkMode: false,
  theme: { extend: {} },
  variants: { extend: {} },
  corePlugins: { preflight: true }
};