# How to release this package.

- 1. Update the version number in `vscode/package.json`
- 2. Run the following commands from the `vscode` directory:
```bash
npm install
npm run compile
npm run vsce-package
```
- 3. Upload the generated `.vsix` file to the [Visual Studio Code Marketplace](https://marketplace.visualstudio.com/manage/publishers/fourdigits)

