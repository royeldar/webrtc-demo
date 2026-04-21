# Simple WebRTC Application

## Protocol

Suppose Alice wants to call Bob. She should:

- choose audio and/or video sources, and press "set input devices"
  this causes the client to do the following:
    * set the local stream
- change her username to "Alice"
- register her username by pressing "register username"
  this causes the client to do the following:
    * send the server "register" request
- set the peer's username to "Bob"
- call Bob by pressing "initiate call"
  this causes the client to do the following:
    * set the call status to "Connecting"
    * start polling the server for messages
    * generate a unique id on her end
    * send a "call-offer" to Bob, containing her unique id
    * receive the "call-answer" from Bob, containing his unique id
    * create a common session id comprised of both ids
    * set the call status to "Connected"
    * create an RTC peer connection object
    * send a "call-acknowledgement" to Bob, containing his unique id
    * receive the "video-offer" from Bob, containing his local description
    * set the remote description associated to the connection
    * fire a track event for every track of the remote stream (audio/video)
    * retrieve the remote stream from the track events
    * attach the local stream tracks (audio/video) to the connection
    * create an SDP answer
    * set the local description associated to the connection
    * fire an icecandidate event for every ICE candidate
      note that ICE negotiation may still happen during the call
    * send a "new-ice-candidate" to Bob, containing their session id and candidate string,
      for every ICE candidate
    * send a "video-answer" to Bob, containing their session id and Alice's local description
    * receive "new-ice-candidate" messages from Bob, containing his candidate strings
    * add the remote ICE candidates to the remote description

and Bob should:

- choose audio and/or video sources, and press "set input devices"
  this causes the client to do the following:
    * set the local stream
- change his username to "Alice"
- register his username by pressing "register username"
  this causes the client to do the following:
    * send the server "register" request
- set the peer's username to "Alice"
- receive Alice's call by pressing "receive call"
  this causes the client to do the following:
    * set the call status to "Waiting"
    * start polling the server for messages
    * receive the "call-offer" from Alice, containing her unique id
    * set the call status to "Connecting"
    * generate a unique id on his end
    * send a "call-answer" to Alice, containing both her unique id and Bob's unique id
    * receive the "call-acknowledgement" from Alice, containing his unique id
    * create a common session id comprised of both ids
    * set the call status to "Connected"
    * create an RTC peer connection object
    * attach the local stream tracks (audio/video) to the connection
    * fire a negotiationneeded event
    * create an SDP offer
    * set the local description associated to the connection
    * fire an icecandidate event for every ICE candidate
      note that ICE negotiation may still happen during the call
    * send a "new-ice-candidate" to Alice, containing their session id and candidate string,
      for every ICE candidate
    * send a "video-offer" to Alice, containing their session id and Bob's local description
    * receive the "video-answer" from Alice, containing her local description
    * set the remote description associated to the connection
    * fire a track event for every track of the remote stream (audio/video)
    * retrieve the remote stream from the track events
    * receive "new-ice-candidate" messages from Alice, containing her candidate strings
    * add the remote ICE candidates to the remote description

Suppose one of them wants to change their audio and/or video sources; they should:

- choose audio and/or video sources, and press "set input devices"
  this causes the client to do the following:
    * set the local stream
    * remove the old local stream tracks (audio/video) from the connection
    * attach the local stream tracks (audio/video) to the connection
    * fire a negotiationneeded event
    * create an SDP offer
    * set the local description associated to the connection
    * send a "video-offer" to the peer, containing their session id and local description
  this causes the peer's client to do the following:
    * receive the "video-offer", containing the local description
    * set the remote description associated to the connection
    * fire a track event for every track of the remote stream (audio/video)
    * retrieve the remote stream from the track events
    * create an SDP answer
    * set the local description associated to the connection
    * send a "video-answer" to the peer, containing their session id and local description
  this causes the client to do the following:
    * receive the "video-answer" from the peer, containing their local description
    * set the remote description associated to the connection

Suppose Alice wants to end the call. She should:

- hang up by pressing "end call"
  this causes the client to do the following:
    * destroy the RTC peer connection object
    * clear the remote stream
    * send a "call-hangup" to Bob, containing their session id
    * stop polling the server for messages
    * set the call status to "Disconnected"
  and Bob's client would do the following:
    * receive the "call-hangup" from Alice
    * destroy the RTC peer connection object
    * clear the remote stream
    * set the call status to "Waiting"

Suppose Bob wants to end the call. He should:

- hang up by pressing "end call"
  this causes the client to do the following:
    * destroy the RTC peer connection object
    * clear the remote stream
    * send a "call-hangup" to Alice, containing their session id
    * stop polling the server for messages
    * set the call status to "Disconnected"
  and Alice's client would do the following:
    * receive the "call-hangup" from Alice
    * destroy the RTC peer connection object
    * clear the remote stream
    * set the call status to "Disconnected"
