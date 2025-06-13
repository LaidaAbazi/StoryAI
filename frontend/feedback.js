class FeedbackModel {
    constructor() {
        this.sessionId = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.transcript = '';
        this.isRecording = false;
        this.feedbackHistory = [];
    }

    async startSession() {
        try {
            const response = await fetch('/api/feedback/start', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`,
                    'Content-Type': 'application/json'
                }
            });
            if (!response.ok) {
                showStatus('Failed to start session. Please log in again.', true);
                return false;
            }
            const data = await response.json();
            this.sessionId = data.session_id;
            return true;
        } catch (error) {
            showStatus('Error starting feedback session.', true);
            console.error('Error starting feedback session:', error);
            return false;
        }
    }

    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream);
            
            this.mediaRecorder.ondataavailable = (event) => {
                this.audioChunks.push(event.data);
            };
            
            this.mediaRecorder.onstop = async () => {
                await this.processAudio();
            };
            
            this.mediaRecorder.start();
            this.isRecording = true;
            return true;
        } catch (error) {
            console.error('Error starting recording:', error);
            return false;
        }
    }

    stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
            this.mediaRecorder.stop();
            this.isRecording = false;
            return true;
        }
        return false;
    }

    async processAudio() {
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
        const formData = new FormData();
        formData.append('audio', audioBlob);
        formData.append('session_id', this.sessionId);
        
        try {
            const response = await fetch('/api/feedback/transcript', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`
                },
                body: formData
            });
            const data = await response.json();
            if (data.transcript) {
                this.transcript += data.transcript + '\n';
                return data.transcript;
            }
        } catch (error) {
            console.error('Error processing audio:', error);
            return null;
        }
    }

    async submitFeedback(content, rating = null, feedbackType = 'general') {
        try {
            const response = await fetch('/api/feedback/submit', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token')}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    content,
                    rating,
                    feedback_type: feedbackType
                })
            });
            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error submitting feedback:', error);
            return null;
        }
    }

    reset() {
        this.sessionId = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.transcript = '';
        this.isRecording = false;
    }
}

// Instantiate the feedback model for use throughout the file
const feedbackModel = new FeedbackModel();

// Export the model
window.FeedbackModel = FeedbackModel;

// Feedback conversation logic (identical to interview scripts, with feedback prompt)
let peerConnection, dataChannel, isSessionReady = false;
const transcriptLog = [];
let sessionTimeout;
let userBuffer = "";
let aiBuffer = "";
let hasEnded = false;
let isInstructionsApplied = false;
let userName = "there"; // fallback

const audioElement = document.getElementById("aiAudio");
const startButton = document.getElementById("startFeedback");
const stopButton = document.getElementById("stopFeedback");
const statusEl = document.getElementById("feedbackStatus");
const transcriptEl = document.getElementById("feedbackTranscript");

function showStatus(msg, isError = false) {
  if (statusEl) {
    statusEl.textContent = msg;
    statusEl.style.color = isError ? '#dc3545' : '#06B6D4';
  }
}

function isFarewell(text) {
  const cleaned = text.toLowerCase().trim();
  return ["goodbye", "see you", "talk to you later", "i have to go"].some(phrase =>
    cleaned === phrase ||
    cleaned.startsWith(phrase + ".") ||
    cleaned.startsWith(phrase + "!") ||
    cleaned.startsWith(phrase + ",") ||
    cleaned.includes(" " + phrase + " ")
  );
}

async function endConversation(reason) {
  if (hasEnded) return;
  hasEnded = true;

  if (sessionTimeout) clearTimeout(sessionTimeout);
  console.log("Conversation ended:", reason);
  statusEl.textContent = "Feedback session complete";

  // Save feedback transcript
  fetch('/api/feedback/submit', {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content: transcriptLog.map(e => `${e.speaker}: ${e.text}`).join("\n"),
      feedback_type: "voice_feedback"
    })
  })
  .then(res => res.json())
  .then(data => {
    console.log("✅ Feedback saved:", data);
  })
  .catch(err => console.error("❌ Failed to save feedback", err));

  // Clean up WebRTC
  if (dataChannel) dataChannel.close();
  if (peerConnection) peerConnection.close();
  if (window.localStream) {
    window.localStream.getTracks().forEach(track => track.stop());
    window.localStream = null;
  }
  stopButton.disabled = true;
  startButton.disabled = false;
}

async function fetchUserName() {
  try {
    const res = await fetch('/api/user');
    const data = await res.json();
    if (data.success) {
      userName = `${data.first_name} ${data.last_name}`.trim();
    }
  } catch (e) {
    userName = "there";
  }
}

// Call this before starting the session
fetchUserName();

// Use a placeholder in the instructions
const feedbackInstructionsTemplate = `
INSTRUCTIONS:
You are an AI feedback collector for Story Boom AI, a tool that helps create case studies. Greet the user by name: {USER_NAME}.

STYLE:
- Be warm, professional, and genuinely interested in the user's experience
- Keep the conversation natural and flowing
- Show empathy and understanding
- Be concise but thorough

CONVERSATION FLOW:

[1. INTRODUCTION]
- Greet the user warmly by name ({USER_NAME})
- Introduce yourself as the Story Boom AI feedback assistant
- Explain that you'd like to gather their feedback about their experience with the tool
- Mention that the conversation will be brief (1-3 minutes)

[2. USAGE EXPERIENCE]
- Ask about their overall experience using Story Boom AI
- What features did they find most useful?
- Were there any challenges or difficulties they encountered?

[3. SPECIFIC FEATURES]
- Ask about their experience with the voice conversation feature
- How was the quality of the generated case studies?
- Did they find the client interview process helpful?

[4. IMPROVEMENT SUGGESTIONS]
- Ask what features they would like to see added
- What aspects of the tool could be improved?
- Any specific pain points they encountered?

[5. RATING]
- Ask them to rate their overall experience (1-5)
- If rating is low, ask what could be improved
- If rating is high, ask what they liked most

[6. CLOSING]
- Thank them for their feedback
- Let them know their input is valuable for improving the tool
- Allow them to end the conversation naturally

IMPORTANT GUIDELINES:
- Keep responses concise and focused
- Listen actively and ask follow-up questions when needed
- Be prepared to handle both positive and negative feedback professionally
- Maintain a friendly, conversational tone throughout
- If the user mentions technical issues, gather specific details
- If they mention feature requests, ask for more context about their use case

Remember to:
- Stay focused on gathering actionable feedback
- Be empathetic to user concerns
- Keep the conversation flowing naturally
- End gracefully when the user indicates they're done
`;

function getPersonalizedInstructions() {
  return feedbackInstructionsTemplate.replaceAll('{USER_NAME}', userName);
}

async function initConnection() {
  try {
    const res = await fetch("/session");
    const data = await res.json();
    const EPHEMERAL_KEY = data.client_secret.value;

    peerConnection = new RTCPeerConnection();
    window.localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioTrack = localStream.getAudioTracks()[0];
    peerConnection.addTrack(audioTrack, localStream);

    peerConnection.ontrack = (event) => {
      const [remoteStream] = event.streams;
      const remoteOnly = new MediaStream();
      remoteStream.getAudioTracks().forEach(track => {
        if (track.kind === "audio" && track.label !== "Microphone") {
          remoteOnly.addTrack(track);
        }
      });
      audioElement.srcObject = remoteOnly;
    };

    dataChannel = peerConnection.createDataChannel("openai-events");

    dataChannel.onopen = () => {
      dataChannel.send(JSON.stringify({
        type: "session.update",
        session: {
          instructions: getPersonalizedInstructions(),
          voice: "coral",
          modalities: ["audio", "text"],
          input_audio_transcription: { model: "whisper-1" },
          turn_detection: { type: "server_vad" }
        }
      }));
    };

    dataChannel.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      handleMessage(event);

      if (msg.type === "session.updated" && !isInstructionsApplied) {
        isInstructionsApplied = true;
        statusEl.textContent = "✅ Ready to collect your feedback";
        dataChannel.send(JSON.stringify({
          type: "response.create",
          response: {
            modalities: ["audio", "text"],
            input: [
              {
                type: "message",
                role: "user",
                content: [
                  { type: "input_text", text: "Hi! I'd like to share my feedback about Story Boom AI." }
                ]
              }
            ]
          }
        }));
        sessionTimeout = setTimeout(() => {
          endConversation("⏱️ 3-minute limit reached.");
        }, 3 * 60 * 1000);
      }
    };

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);

    const response = await fetch("https://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${EPHEMERAL_KEY}`,
        "Content-Type": "application/sdp"
      },
      body: offer.sdp
    });

    const answer = await response.text();
    await peerConnection.setRemoteDescription({ type: "answer", sdp: answer });

    isSessionReady = true;
    statusEl.textContent = "🔄 Connecting to AI...";
    stopButton.classList.remove("hidden");
    stopButton.disabled = false;
    startButton.disabled = true;
  } catch (err) {
    statusEl.textContent = "❌ Failed to start session.";
    console.error(err);
  }
}

function handleMessage(event) {
  const msg = JSON.parse(event.data);
  switch (msg.type) {
    case "response.audio_transcript.done":
      if (msg.transcript) {
        transcriptLog.push({ speaker: "ai", text: msg.transcript });
        aiBuffer = "";
      }
      break;
    case "conversation.item.input_audio_transcription.completed":
      if (msg.transcript && !hasEnded) {
        transcriptLog.push({ speaker: "user", text: msg.transcript });
        const cleanedText = msg.transcript.toLowerCase().trim();
        userBuffer = "";
        if (isFarewell(cleanedText)) {
          console.log("👋 Detected farewell from user.");
          endConversation("👋 User said farewell.");
        }
      }
      break;
  }
}

if (startButton && stopButton) {
  startButton.addEventListener("click", async () => {
    console.log('[DEBUG] Start Conversation button clicked');
    statusEl.textContent = 'Starting feedback session...';
    await initConnection();
  });
  stopButton.addEventListener("click", () => {
    console.log('[DEBUG] Stop Conversation button clicked');
    endConversation("🛑 Manual end by user.");
  });
} 