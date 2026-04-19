(async () => {

	// Trigger a permissions request
	await navigator.mediaDevices.getUserMedia({'video': true, 'audio': true});

	// Fetch an array of devices of a certain type
	async function getConnectedDevices(type) {
		const devices = await navigator.mediaDevices.enumerateDevices();
		return devices.filter(device => device.kind === type)
	}

	// Updates the select element with the provided set of cameras
	function updateCameraList(cameras) {
		const listElement = document.querySelector('select#availableCameras');
		listElement.innerHTML = '<option value="">--Please choose an input video device--</option>';
		cameras.map((camera) => {
			const cameraOption = document.createElement('option');
			cameraOption.label = camera.label;
			cameraOption.value = camera.deviceId;
			return cameraOption;
		}).forEach(cameraOption => listElement.add(cameraOption));
	}

	// Updates the select element with the provided set of microphones
	function updateMicrophoneList(microphones) {
		const listElement = document.querySelector('select#availableMicrophones');
		listElement.innerHTML = '<option value="">--Please choose an input audio device--</option>';
		microphones.map((microphone) => {
			const microphoneOption = document.createElement('option');
			microphoneOption.label = microphone.label;
			microphoneOption.value = microphone.deviceId;
			return microphoneOption;
		}).forEach(microphoneOption => listElement.add(microphoneOption));
	}

	// Get the initial set of cameras connected
	const videoCameras = await getConnectedDevices('videoinput');
	console.log('Cameras found:', videoCameras);

	// Get the initial set of microphones connected
	const audioMicrophones = await getConnectedDevices('audioinput');
	console.log('Microphones found:', audioMicrophones);

	// Initialize the camera list
	updateCameraList(videoCameras);

	// Initialize the microphone list
	updateMicrophoneList(audioMicrophones)

	// Listen for changes to media devices and update the lists accordingly
	navigator.mediaDevices.addEventListener('devicechange', async (event) => {
		const newCameraList = await getConnectedDevices('videoinput');
		const newMicrophoneList = await getConnectedDevices('audioinput');
		updateCameraList(newCameraList);
		updateMicrophoneList(newMicrophoneList);
	});

	// Open a stream with a specific camera and microphone
	async function openStream(cameraId, microphoneId) {
		let constraints = new Object();
		if (cameraId !== '') {
			constraints.video = {
				deviceId: {
					exact: cameraId,
				},
			}
		}
		if (microphoneId !== '') {
			constraints.audio = {
				deviceId: {
					exact: microphoneId,
				},
			}
		}
		return await navigator.mediaDevices.getUserMedia(constraints);
	}

	let cameraId = null;
	let microphoneId = null;
	let localStream = null;
	let attachedStream = null;

	// Attach the local stream to the connection (this may trigger negotiation)
	function attachStream() {
		// Remove the old tracks from the connection (if there are any)
		if (attachedStream) {
			peerConnection.getSenders()
				.forEach((sender) => peerConnection.removeTrack(sender));
		}
		// Add the local stream tracks to the connection
		localStream.getTracks()
			.forEach((track) => peerConnection.addTrack(track, localStream));
		attachedStream = true;
	}

	// Change local video stream
	async function setLocalStream() {
		// Create local video stream
		localStream = await openStream(cameraId, microphoneId);
		// Play video from local camera
		const localVideo = document.querySelector('video#localVideo');
		localVideo.srcObject = localStream;
		// If there is an ongoing call, change its media stream
		if (peerConnection !== null) {
			attachStream();
		}
	}

	// Change input devices and re-open stream if needed
	async function setInputDevices(newCameraId, newMicrophoneId) {
		if (cameraId !== newCameraId || microphoneId !== newMicrophoneId) {
			cameraId = newCameraId;
			microphoneId = newMicrophoneId;
			console.log(`Changing input devices (video = ${cameraId}, audio = ${microphoneId})`);
			await setLocalStream();
		}
	}

	// Define a button for setting the input devices
	const setInputDevicesButton = document.querySelector('button#setInputDevices');
	setInputDevicesButton.addEventListener('click', async (event) => {
		const newCameraId = document.querySelector('select#availableCameras').value;
		const newMicrophoneId = document.querySelector('select#availableMicrophones').value;
		await setInputDevices(newCameraId, newMicrophoneId);
	});

	// Change remote video stream
	function setRemoteStream(stream) {
		// Play video from remote camera
		const remoteVideo = document.querySelector('video#remoteVideo');
		if (remoteVideo.srcObject !== stream) {
			remoteVideo.srcObject = stream;
		}
	}

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
		const sender = localUsername;
		const receiver = getRemoteUsername();
		const body = sender + '\n' + receiver + '\n' + JSON.stringify(msg);
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
		const receiver = localUsername;
		const sender = getRemoteUsername();
		const body = receiver + '\n' + sender;
		const response = await fetch(url, {
			method: 'POST',
			body: body,
			headers: headers
		});
		if (!response.ok) {
			throw new Error('Failed to receive message!');
		}
		const msg = await response.text();
		if (msg === '') {
			return null;
		}
		return JSON.parse(msg);
	}

	// 100ms
	const pollingInterval = 100;
	let isPolling = null;
	let pollingPromise = null;

	// Delay some amount of time
	async function delay(ms) {
		return new Promise(resolve => setTimeout(resolve, ms));
	}

	// Handle messages by polling the server indefinitely
	async function pollServer() {
		while (isPolling) {
			try {
				let msg;
				while (isPolling && (msg = await receiveMessage()) !== null) {
					await handleMessage(msg).catch(console.error);
				}
			} catch (e) {
				console.error(e);
			}
			if (isPolling) {
				await delay(pollingInterval);
			}
		}
	}

	// Start polling server
	function startPolling() {
		console.log('Starting to poll server');
		isPolling = true;
		pollingPromise = pollServer();
	}

	// Stop polling server
	async function stopPolling() {
		console.log('Stopping polling server');
		isPolling = false;
		await pollingPromise;
		isPolling = null;
		pollingPromise = null;
	}

	// Handle a single message that was received
	async function handleMessage(msg) {
		switch (msg.type) {
		case 'call-offer':
			await handleCallOfferMessage(msg);
			break;
		case 'call-answer':
			await handleCallAnswerMessage(msg);
			break;
		case 'call-acknowledgement':
			await handleCallAcknowledgementMessage(msg);
			break;
		case 'call-hangup':
			await handleCallHangupMessage(msg);
			break;
		case 'video-offer':
			await handleVideoOfferMessage(msg);
			break;
		case 'video-answer':
			await handleVideoAnswerMessage(msg);
			break;
		case 'new-ice-candidate':
			await handleNewICECandidateMessage(msg);
			break;
		default:
			console.warn(`Unknown message type (${msg.type})`);
		}
	}

	let side = null;
	let ourId = null;
	let theirId = null;
	let sessionId = null;

	// Generate a unique random id
	function generateUniqueId() {
		return Math.floor(Math.random() * 1000000000);
	}

	// Construct a session id from the caller/callee id's
	function createSessionId() {
		switch (side) {
		case 'caller':
			sessionId = ourId + '_' + theirId;
			break;
		case 'callee':
			sessionId = theirId + '_' + ourId;
			break;
		}
		console.log(`Created session (sessionId = ${sessionId})`);
	}

	// Send a call offer message
	async function sendCallOfferMessage() {
		ourId = generateUniqueId();

		console.log(`Sending a call offer (callerId = ${ourId})`);

		await sendMessage({
			type: 'call-offer',
			callerId: ourId
		});
	}

	// Handle a call offer message
	async function handleCallOfferMessage(msg) {
		console.log(`Got a call offer (callerId = ${msg.callerId})`);

		if (side !== 'callee') {
			console.warn(`Wrong side for call offer (${side})`);
		} else if (peerConnection !== null) {
			console.warn('Got a call offer in the middle of an ongoing call');
		} else {
			if (theirId !== null) {
				console.info('Got another call offer');
			}
			theirId = msg.callerId;

			// Set call status accordingly
			setCallStatus('CONNECTING');

			// Send call answer to the other user
			await sendCallAnswerMessage();
		}
	}

	// Send a call answer message
	async function sendCallAnswerMessage() {
		ourId = generateUniqueId();

		console.log(`Sending a call answer (callerId = ${theirId}, calleeId = ${ourId})`);

		await sendMessage({
			type: 'call-answer',
			callerId: theirId,
			calleeId: ourId
		});
	}

	// Handle a call answer message
	async function handleCallAnswerMessage(msg) {
		console.log(`Got a call answer (callerId = ${msg.callerId}, calleeId = ${msg.calleeId})`);

		if (side !== 'caller') {
			console.warn(`Wrong side for call answer (${side})`);
		} else if (peerConnection !== null) {
			console.warn('Got a call answer in the middle of an ongoing call');
		} else if (msg.callerId !== ourId) {
			console.warn('Incorrect caller id');
		} else if (theirId !== null) {
			console.warn('Did not expect to get a call answer');
		} else {
			theirId = msg.calleeId;

			// Construct session id
			createSessionId();

			// Set call status accordingly
			setCallStatus('CONNECTED');

			// Create a peer connection
			createPeerConnection();

			// Send call acknowledgement
			await sendCallAcknowledgementMessage();
		}
	}

	// Send a call acknowledgement message
	async function sendCallAcknowledgementMessage() {
		console.log(`Sending a call acknowledgement (calleeId = ${theirId})`);

		await sendMessage({
			type: 'call-acknowledgement',
			calleeId: theirId
		});
	}

	// Handle a call acknowledgement message
	async function handleCallAcknowledgementMessage(msg) {
		console.log(`Got a call acknowledgement (calleeId = ${msg.calleeId})`)

		if (side !== 'callee') {
			console.warn(`Wrong side for call acknowledgement (${side})`);
		} else if (peerConnection !== null) {
			console.warn('Got a call acknowledgement in the middle of an ongoing call');
		} else if (msg.calleeId !== ourId) {
			console.warn('Incorrect callee id');
		} else {
			// Construct session id
			createSessionId();

			// Set call status accordingly
			setCallStatus('CONNECTED');

			// Create a peer connection
			createPeerConnection();

			// Attach stream (this will start negotiation)
			attachStream();
		}
	}

	// Send a video offer message
	async function sendVideoOfferMessage() {
		console.log(`Sending a video offer (sessionId = ${sessionId}, description = %o)`, peerConnection.localDescription);

		await sendMessage({
			type: 'video-offer',
			sessionId: sessionId,
			description: peerConnection.localDescription
		});
	}

	let ignoreOffer = false;

	// Handle a video offer message
	async function handleVideoOfferMessage(msg) {
		console.log(`Got a video offer (sessionId = ${msg.sessionId}, description = %o)`, msg.description);

		if (peerConnection === null) {
			console.warn('Got a video offer without an ongoing call');
		} else if (msg.sessionId !== sessionId) {
			console.warn('Incorrect session id');
		} else {
			const readyForOffer = !makingOffer && peerConnection.signalingState === 'stable';
			const polite = side === 'caller';
			ignoreOffer = !polite && !readyForOffer;
			if (ignoreOffer) {
				console.log('Ignoring video offer');
				return;
			}
			isRemoteDescriptionSet = false;
			await peerConnection.setRemoteDescription(msg.description);
			isRemoteDescriptionSet = true;
			for (const candidate of iceCandidatesQueue) {
				await peerConnection.addIceCandidate(candidate).catch(console.error);
			}
			iceCandidatesQueue = [];
			if (!attachedStream) {
				attachStream();
			}
			const answer = await peerConnection.createAnswer();
			await peerConnection.setLocalDescription(answer);
			await sendVideoAnswerMessage();
		}
	}

	// Send a video answer message
	async function sendVideoAnswerMessage() {
		console.log(`Sending a video answer (sessionId = ${sessionId}, description = %o)`, peerConnection.localDescription);

		await sendMessage({
			type: 'video-answer',
			sessionId: sessionId,
			description: peerConnection.localDescription
		});
	}

	// Handle a video answer message
	async function handleVideoAnswerMessage(msg) {
		console.log(`Got a video answer (sessionId = ${msg.sessionId}, description = %o)`, msg.description);

		if (peerConnection === null) {
			console.warn('Got a video answer without an ongoing call');
		} else if (msg.sessionId !== sessionId) {
			console.warn('Incorrect session id');
		} else {
			isRemoteDescriptionSet = false;
			await peerConnection.setRemoteDescription(msg.description);
			isRemoteDescriptionSet = true;
			for (const candidate of iceCandidatesQueue) {
				await peerConnection.addIceCandidate(candidate).catch(console.error);
			}
			iceCandidatesQueue = [];
		}
	}

	// Send a new ice candidate message
	async function sendNewICECandidateMessage(candidate) {
		console.log(`Sending a new ice candidate (sessionId = ${sessionId}, candidate = %o)`, candidate);

		await sendMessage({
			type: 'new-ice-candidate',
			sessionId: sessionId,
			candidate: candidate
		});
	}

	// Handle a new ice candidate message
	async function handleNewICECandidateMessage(msg) {
		console.log(`Got a new ice candidate (sessionId = ${msg.sessionId}, candidate = %o)`, msg.candidate);

		if (peerConnection === null) {
			console.warn('Got a new ice candidate without an ongoing call');
		} else if (msg.sessionId !== sessionId) {
			console.warn('Incorrect session id');
		} else if (!isRemoteDescriptionSet) {
			if (iceCandidatesQueue !== null) {
				console.log('Got a new ice candidate before video offer/answer');
				iceCandidatesQueue.push(msg.candidate);
			}
		} else {
			try {
				await peerConnection.addIceCandidate(msg.candidate);
			} catch (e) {
				if (!ignoreOffer) {
					console.error(e);
				}
			}
		}
	}

	// Send a call hangup message
	async function sendCallHangupMessage() {
		console.log(`Sending a call hangup (sessionId = ${sessionId})`);

		await sendMessage({
			type: 'call-hangup',
			sessionId: sessionId
		});
	}

	// Handle a call hangup message
	async function handleCallHangupMessage(msg) {
		console.log(`Got a call hangup (sessionId = ${msg.sessionId})`);

		if (peerConnection === null) {
			console.warn('Got a call hangup without an ongoing call');
		} else if (msg.sessionId !== sessionId) {
			console.warn('Incorrect session id');
		} else {
			// Destroy the peer connection
			destroyPeerConnection();

			// Reset remote video stream
			setRemoteStream(null);

			// There is no session anymore
			sessionId = null;
			ourId = null;
			theirId = null;

			// Set call status accordingly
			switch (side) {
			case 'caller':
				setCallStatus('DISCONNECTED');
				break;
			case 'callee':
				setCallStatus('WAITING');
				break;
			}
		}
	}

	// Change call status
	const callStatusOutput = document.querySelector('output#callStatus');
	function setCallStatus(status) {
		console.log(`Setting call status to ${status}`);
		callStatusOutput.value = status;
	}

	// Define a button for initiating a call
	const initiateCallButton = document.querySelector('button#initiateCall');
	initiateCallButton.addEventListener('click', async (event) => {
		const remoteUsername = getRemoteUsername();
		if (localUsername === null || localUsername !== getLocalUsername()) {
			alert('Our username is not set');
		} else if (remoteUsername === '') {
			alert('Their username is not set');
		} else if (localUsername === remoteUsername) {
			alert('Cannot start a call with ourselves');
		} else if (localStream === null) {
			alert('Media sources are not set');
		} else {
			// Disable and enable some elements
			localUsernameInput.disabled = true;
			setUsernameButton.disabled = true;
			registerUsernameButton.disabled = true;
			unregisterUsernameButton.disabled = true;
			remoteUsernameInput.disabled = true;
			initiateCallButton.disabled = true;
			receiveCallButton.disabled = true;
			endCallButton.disabled = false;

			// Set call status accordingly
			setCallStatus('CONNECTING');

			// The side that initiates the call is the caller
			side = 'caller';

			// Start receiving messages intended for our user
			startPolling();

			// Send call offer to the other user
			await sendCallOfferMessage();
		}
	});

	// Define a button for receiving a call
	const receiveCallButton = document.querySelector('button#receiveCall');
	receiveCallButton.addEventListener('click', async (event) => {
		const remoteUsername = getRemoteUsername();
		if (localUsername === null || localUsername !== getLocalUsername()) {
			alert('Our username is not set');
		} else if (remoteUsername === '') {
			alert('Their username is not set');
		} else if (localUsername === remoteUsername) {
			alert('Cannot start a call with ourselves');
		} else if (localStream === null) {
			alert('Media sources are not set');
		} else {
			// Disable and enable some elements
			localUsernameInput.disabled = true;
			setUsernameButton.disabled = true;
			registerUsernameButton.disabled = true;
			unregisterUsernameButton.disabled = true;
			remoteUsernameInput.disabled = true;
			initiateCallButton.disabled = true;
			receiveCallButton.disabled = true;
			endCallButton.disabled = false;

			// Set call status accordingly
			setCallStatus('WAITING');

			// The side that answers the call is the callee
			side = 'callee';

			// Start receiving messages intended for our user
			startPolling();
		}
	});

	// Define a button for ending a call
	const endCallButton = document.querySelector('button#endCall');
	endCallButton.addEventListener('click', async (event) => {
		// If there is an ongoing call, destroy the peer connection and send hangup
		if (peerConnection !== null) {
			// Destroy the peer connection
			destroyPeerConnection();

			// Reset remote video stream
			setRemoteStream(null);

			// Send call hangup to the other user
			await sendCallHangupMessage();

			// There is no session anymore
			sessionId = null;
		}

		// Stop receiving messages intended for our user
		await stopPolling();

		// There is no side anymore
		side = null;
		ourId = null;
		theirId = null;

		// Set call status accordingly
		setCallStatus('DISCONNECTED');

		// Enable and disable some elements
		localUsernameInput.disabled = false;
		setUsernameButton.disabled = false;
		registerUsernameButton.disabled = false;
		unregisterUsernameButton.disabled = false;
		remoteUsernameInput.disabled = false;
		initiateCallButton.disabled = false;
		receiveCallButton.disabled = false;
		endCallButton.disabled = true;
	});

	const useTlsCheckbox = document.getElementById('useTls');
	const stunPortInput = document.getElementById('stunPort');
	const turnPortInput = document.getElementById('turnPort');
	useTlsCheckbox.addEventListener('change', () => {
		if (useTlsCheckbox.checked) {
			turnPortInput.value = "5349";
			turnPortInput.placeholder = "5349";
		} else {
			turnPortInput.value = "3478";
			turnPortInput.placeholder = "3478";
		}
	});

	let peerConnection = null;
	let iceCandidatesQueue = null;
	let isRemoteDescriptionSet = null;

	// Create an RTC peer connection
	function createPeerConnection() {
		console.log('Creating an RTC peer connection');

		attachedStream = false;

		const stunPort = stunPortInput.value || '3478';
		let turnPort = turnPortInput.value;
		let turnProtocol;
		if (useTlsCheckbox.checked) {
			turnPort = turnPort || '5349';
			turnProtocol = 'turns';
		} else {
			turnPort =  turnPort || '3478';
			turnProtocol = 'turn';
		}
		const turnUsername = document.getElementById('turnUsername').value || 'username';
		const turnPassword = document.getElementById('turnPassword').value || 'password';
		const config = {
			iceServers: [
				{
					urls: 'stun:' + window.location.hostname + ':' + stunPort,
				},
				{
					urls: turnProtocol + ':' + window.location.hostname + ':' + turnPort,
					username: turnUsername,
					credential: turnPassword,
				},
			]
		}
		peerConnection = new RTCPeerConnection(config);

		peerConnection.onnegotiationneeded = handleNegotiationNeededEvent;
		peerConnection.onicecandidate = handleICECandidateEvent;
		peerConnection.ontrack = handleTrackEvent;

		iceCandidatesQueue = [];
		isRemoteDescriptionSet = false;
	}

	// Destroy the RTC peer connection
	function destroyPeerConnection() {
		console.log('Destroying the peer connection');

		iceCandidatesQueue = null;
		isRemoteDescriptionSet = null;

		peerConnection.onnegotiationneeded = null;
		peerConnection.onicecandidate = null;
		peerConnection.ontrack = null;

		peerConnection.close();
		peerConnection = null;

		attachedStream = null;
	}

	let makingOffer = false;

	// Handle negotiationneeded event
	async function handleNegotiationNeededEvent(event) {
		console.log('Got a negotiationneeded event');

		try {
			makingOffer = true;
			const offer = await peerConnection.createOffer();
			await peerConnection.setLocalDescription(offer);
			await sendVideoOfferMessage();
		} catch (e) {
			console.error(e);
		} finally {
			makingOffer = false;
		}
	}

	// Handle icecandidate event
	async function handleICECandidateEvent(event) {
		console.log('Got an icecandidate event (candidate = %o)', event.candidate);

		// Send new ice candidate (if there is one)
		if (event.candidate) {
			await sendNewICECandidateMessage(event.candidate);
		}
	}

	// Handle track event
	async function handleTrackEvent(event) {
		console.log('Got a track event (stream = %o)', event.streams[0]);

		// Set remote video stream
		setRemoteStream(event.streams[0]);
	}

})();
