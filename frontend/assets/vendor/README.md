# Vuexy theme files (not included)

The UI is built on the commercial **Vuexy** Bootstrap admin template, whose licence does not allow
redistributing its files. With your own licensed copy of the template, generate this folder:

```powershell
node frontend/tools/build-theme.js "<path-to-your-Vuexy-template>"
```

The script re-colours the theme to the project's brand teal, minifies it, and writes the 24 files
the app uses into this folder (`frontend/assets/vendor/`).
