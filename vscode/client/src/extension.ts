import * as os from 'os';
import * as fs from 'fs';
import { workspace, ExtensionContext } from 'vscode';

import {
	LanguageClient,
	LanguageClientOptions,
	StreamInfo,
} from 'vscode-languageclient/node';

import { spawn } from 'child_process';

let client: LanguageClient;

export function activate(context: ExtensionContext) {
	const expandHomeDir = (filePath: string) => {
		const home = os.homedir();
		return home ? filePath.replace('~', home) : filePath;
	};

	const configuration = workspace.getConfiguration('djangoTemplateLsp');

	const djlspPaths = [];

	const djlspPathConfig = configuration.get('djlspPath', false);

	if (djlspPathConfig) {
		djlspPaths.push(expandHomeDir(djlspPathConfig));
	} else {
		djlspPaths.push(expandHomeDir('~/.local/bin/djlsp'));
		djlspPaths.push(expandHomeDir('~/.local/pipx/venvs/django-template-lsp/bin/djlsp'));
	}

	const djlspPath = djlspPaths.find(fs.existsSync);

	// Add error handling for when djlsp is not installed
	if (!djlspPath) {
		throw new Error('djlsp is not installed');
	}

	const djlspArgs = [];

	if (configuration.get("enableLogging", false)) {
		djlspArgs.push('--enable-log');
	}

	// Pass initialization options to the server
	const initializationOptions = {
		docker_compose_file: configuration.get('dockerComposeFile', 'docker-compose.yml'),
		docker_compose_service: configuration.get('dockerComposeService', 'django'),
		django_settings_module: configuration.get('djangoSettingsModule', ''),
	};

	// Get current workspace folder path
	// This is also updated when the workspace folder is changed.
	const workspaceFolders = workspace.workspaceFolders;
	if (workspaceFolders === undefined) {
		throw new Error('No workspace folder is open');
	}
	const workspaceFolder = workspaceFolders[0];
	const workspaceFolderPath = workspaceFolder.uri.fsPath;

	const serverOptions = () => {
		const djlspProcess = spawn(djlspPath, djlspArgs, {
			stdio: ['pipe', 'pipe', 'pipe'],
			cwd: workspaceFolderPath,
		});

		if (configuration.get("enableLogging", false)) {
			djlspProcess.stderr.on('data', (data) => {
				console.error(`djlsp stderr: ${data}`);
			});

			djlspProcess.on('error', (err) => {
				console.error(`Failed to start djlsp: ${err.message}`);
			});

			djlspProcess.on('exit', (code, signal) => {
				console.error(`djlsp exited with code ${code} and signal ${signal}`);
			});

			djlspProcess.on('close', (code) => {
				console.error(`djlsp process closed with code ${code}`);
			});

			djlspProcess.on('disconnect', () => {
				console.error('djlsp process disconnected');
			});
		}

		return Promise.resolve<StreamInfo>({
			writer: djlspProcess.stdin,
			reader: djlspProcess.stdout,
		});
	};

	// Options to control the language client
	const clientOptions: LanguageClientOptions = {
		documentSelector: [
			{ scheme: 'file', language: 'html' },
			{ scheme: 'file', language: 'htmldjango' },
			{ scheme: 'file', language: 'django-html' },
		], // Adjust this to the appropriate language
		synchronize: {
			// Notify the server about file changes to '.clientrc files contained in the workspace
			fileEvents: workspace.createFileSystemWatcher('**/.clientrc'),
		},
		initializationOptions: initializationOptions,
	};

	// Create the language client and start the client.
	client = new LanguageClient(
		'djlsp',
		'Django Template Language Server',
		serverOptions,
		clientOptions,
	);

	// Start the client. This will also launch the server
	client.start();
}

export function deactivate(): Thenable<void> | undefined {
	if (!client) {
		return undefined;
	}
	return client.stop();
}
