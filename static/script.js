(async () => {

	let localUsername = null;

	// Change local username
	function setUsername(username) {
		console.log(`Username set to ${username}`);
		localUsername = username;
	}

	// Get the current local username
	const localUsernameInput = document.querySelector('input#localUsername');
	function getLocalUsername() {
		return localUsernameInput.value;
	}

	// Define a button for setting the username
	const setUsernameButton = document.querySelector('button#setUsername');
	setUsernameButton.addEventListener('click', async (event) => {
		const username = getLocalUsername();
		if (username === '') {
			alert('Username is empty');
		} else {
			setUsername(username);
		}
	})

	// Define a button for registering the username
	const registerUsernameButton = document.querySelector('button#registerUsername');
	registerUsernameButton.addEventListener('click', async (event) => {
		const username = getLocalUsername();
		if (username === '') {
			alert('Username is empty');
		} else {
			const url = window.location.origin + '/api/register';
			const headers = new Headers();
			headers.append('Content-Type', 'text/plain; charset=utf-8');
			const response = await fetch(url, {
				method: 'POST',
				body: username,
				headers: headers
			});
			if (response.ok) {
				alert('SUCCESS! Username registered');
				setUsername(username);
			} else {
				alert('FAILURE! ' + response.statusText);
			}
		}
	});

	// Define a button for unregistering the username
	const unregisterUsernameButton = document.querySelector('button#unregisterUsername');
	unregisterUsernameButton.addEventListener('click', async (event) => {
		const username = getLocalUsername();
		if (username === '') {
			alert('Username is empty');
		}  else {
			const url = window.location.origin + '/api/unregister';
			const headers = new Headers();
			headers.append('Content-Type', 'text/plain; charset=utf-8');
			const response = await fetch(url, {
				method: 'POST',
				body: username,
				headers: headers
			});
			if (response.ok) {
				alert('SUCCESS! Username unregistered');
				setUsername(null);
			} else {
				alert('FAILURE! ' + response.statusText);
			}
		}
	});

	// Get the remote username
	const remoteUsernameInput = document.querySelector('input#remoteUsername');
	function getRemoteUsername() {
		return remoteUsernameInput.value;
	}

	// Send a message to the remote user
	async function sendMessage(msg) {
		const url = window.location.origin + '/api/send';
		const headers = new Headers();
		headers.append('Content-Type', 'text/plain; charset=utf-8');
		const username = getRemoteUsername();
		const body = username + '\n' + JSON.stringify(msg);
		const response = await fetch(url, {
			method: 'POST',
			body: body,
			headers: headers
		});
		if (!response.ok) {
			throw new Error('Failed to send message!');
		}
	}

	// Receive a message intended for the local user
	async function receiveMessage() {
		const url = window.location.origin + '/api/receive';
		const headers = new Headers();
		headers.append('Content-Type', 'text/plain; charset=utf-8');
		const username = getLocalUsername();
		const response = await fetch(url, {
			method: 'POST',
			body: username,
			headers: headers
		});
		if (!response.ok) {
			throw new Error('Failed to receive message!');
		}
		msg = await response.text();
		if (msg === '') {
			return null;
		}
		return JSON.parse(msg);
	}

})();
