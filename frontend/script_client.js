// Client-side logic for AI Case Study Client Interview
let peerConnection, dataChannel, isSessionReady = false;
const transcriptLog = [];
let sessionTimeout;
let userBuffer = "";
let aiBuffer = "";
let hasEnded = false;
let isInstructionsApplied = false;

const audioElement = document.getElementById("aiAudio");
const startButton = document.getElementById("startBtn");
const statusEl = document.getElementById("status");

const farewellPhrases = ["goodbye", "see you", "talk to you later", "i have to go"];

let provider_name = "";
let client_name = "";
let project_name = "";
let provider_interviewee_name = "";

function isFarewell(text) {
  const cleaned = text.toLowerCase().trim();
  return farewellPhrases.some(phrase =>
    cleaned === phrase ||
    cleaned.startsWith(phrase + ".") ||
    cleaned.startsWith(phrase + "!") ||
    cleaned.startsWith(phrase + ",") ||
    cleaned.includes(" " + phrase + " ")
  );
}

function getClientTokenFromURL() {
  const pathParts = window.location.pathname.split('/');
  const clientIndex = pathParts.indexOf('client');
  if (clientIndex !== -1 && pathParts.length > clientIndex + 1) {
    return pathParts[clientIndex + 1];
  }
  return null;
}

async function fetchClientSessionData(token) {
  const response = await fetch(`/client-interview/${token}`);
  const data = await response.json();
  if (data.status === "success") {
    return data;
  } else {
    alert("Failed to fetch client session data");
    return null;
  }
}

async function fetchProviderTranscript(token) {
  try {
    const response = await fetch(`/get_provider_transcript?token=${token}`);
    const data = await response.json();
    if (data.status === "success" && data.transcript) {
      // Extract the provider's name from the transcript
      const lines = data.transcript.split('\n');
      for (const line of lines) {
        if (line.startsWith('USER:') && line.toLowerCase().includes('my name is')) {
          const nameMatch = line.match(/my name is ([^,.]+)/i);
          if (nameMatch) {
            provider_interviewee_name = nameMatch[1].trim();
            break;
          }
        }
      }
    }
  } catch (err) {
    console.error("Failed to fetch provider transcript:", err);
  }
}

// ✅ This is the new logic to be added to the CLIENT interview JS for saving transcript and generating summary
// This mirrors the logic from the solution provider interview

async function endConversation(reason) {
  if (hasEnded) return;
  hasEnded = true;

  if (sessionTimeout) clearTimeout(sessionTimeout);
  console.log("Conversation ended:", reason);
  statusEl.textContent = "Interview complete";

  // ✅ Save CLIENT transcript
  fetch(`/save_client_transcript?token=${getClientTokenFromURL()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(transcriptLog)
  })
  .then(res => res.json())
  .then(async (data) => {
    console.log("✅ Client transcript saved:", data.file);

    // ✅ Generate CLIENT summary
    const formattedTranscript = transcriptLog
      .map(e => `${e.speaker.toUpperCase()}: ${e.text}`)
      .join("\n");

    const token = getClientTokenFromURL();
    

    const summaryResponse = await fetch(`/generate_client_summary?token=${token}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript: formattedTranscript })
    });

 

    const summaryData = await summaryResponse.json();

    if (summaryData.status === "success") {
    const fullRes = await fetch("/generate_full_case_study", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_study_id: summaryData.case_study_id })
    });

    const fullResData = await fullRes.json();
    if (fullResData.status === "success") {
      console.log("✅ Full merged case study generated.");
    } else {
      console.warn("⚠️ Failed to generate full case study:", fullResData.message);
    }

  } else {
    console.error("❌ Failed to generate client summary:", summaryData.message);
  }


  })
  .catch(err => console.error("❌ Failed to save client transcript", err));
  
  // ✅ Clean up WebRTC
  if (dataChannel) dataChannel.close();
  if (peerConnection) peerConnection.close();
  // ✅ Properly stop the microphone to remove Chrome tab mic icon
  if (window.localStream) {
    window.localStream.getTracks().forEach(track => track.stop());
    window.localStream = null;
  }

  const endBtn = document.getElementById("endBtn");
  if (endBtn) {
    endBtn.disabled = true;
    endBtn.textContent = "Interview Ended"; // ✅ Correctly referenced
  }
}

// ✅ Triggered from End button for client interview
document.addEventListener("DOMContentLoaded", () => {
  const endBtn = document.getElementById("endBtn");
  if (endBtn) {
    endBtn.addEventListener("click", () => {
      endConversation("🛑 Manual end by client user.");
    });
  }
});


async function initConnection(clientInstructions, clientGreeting) {
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
  
      // Send instructions when ready
      dataChannel.onopen = () => {
        dataChannel.send(JSON.stringify({
          type: "session.update",
          session: {
            instructions: clientInstructions,
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
  
        // ✅ Only greet after instructions are applied
        if (msg.type === "session.updated" && !isInstructionsApplied) {
          isInstructionsApplied = true;
          statusEl.textContent = "✅ Instructions loaded. AI is ready.";
  
          dataChannel.send(JSON.stringify({
            type: "response.create",
            response: {
              modalities: ["audio", "text"],
              input: [
                {
                  type: "message",
                  role: "user",
                  content: [
                    { type: "input_text", text: clientGreeting.trim() }
                  ]
                }
              ]
            }
          }));
  
          sessionTimeout = setTimeout(() => {
            endConversation("⏱️ 10-minute limit reached.");
          }, 10 * 60 * 1000);
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
      document.getElementById("endBtn").classList.remove("hidden");

  
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


document.addEventListener("DOMContentLoaded", async () => {
  const token = getClientTokenFromURL();
  if (!token) return;

  const sessionData = await fetchClientSessionData(token);
  if (!sessionData) return;

  provider_name = sessionData.provider_name;
  client_name = sessionData.client_name;
  project_name = sessionData.project_name;

  // Fetch provider transcript to get interviewee name
  await fetchProviderTranscript(token);

  clientInstructions = `
  INSTRUCTIONS:
  You are an emotionally intelligent, warm, and slightly witty AI interviewer who behaves like a real human podcast host. You're speaking directly with the client ${client_name} about the story "${project_name}" delivered by ${provider_name}. You should sound genuinely curious, casual, engaged, and human—never robotic or scripted.
  
  [LANGUAGE_PREFERENCE] **MANDATORY**
  -- **Start with a brief welcome**: Say "Hi, welcome to StoryBoom AI!"
  - **First and foremost**: Before any greeting or introduction, ask the user which language they prefer to conduct the interview in.
  - Wait for their response and then continue the entire conversation in that language.
  - If they don't specify a language, default to English.
  - Once the language is established, proceed with the rest of the conversation flow.

  STYLE:
  - Always address the interviewee directly using "you at ${client_name}" when referring to them or their company.
  - When you reference the solution provider, always use "${provider_interviewee_name}" (if available) or "${provider_name}" to keep it personal and conversational.
  - Sprinkle in very light, positive, contextual references about the project, company, or industry as the interview progresses—never showing off, but giving the impression you "get" what they do (e.g., "Ah, tennis coaching, that's such a rewarding field" or "Digital receipts, that's such a growing space these days"). Be subtle and never negative.
  - Keep your language relaxed, friendly, and professional, like two people chatting casually.
  
  [1. INTRODUCTION]
  - When you start, introduce yourself as StoryBoom AI
  - Start warmly and casually. Greet the client by name if known. Briefly introduce yourself as StoryBoom AI, expressing genuine interest in their perspective on "${project_name}". Open with a natural, human warm-up—something like, "How's your day going so far?" or "What have you been up to today?"  
  - If the client mentions any personal context (e.g., "I'm off to play tennis later"), briefly acknowledge it in a warm, human way.
  - Let the conversation breathe. Never rush.
  
  [2. OPENER WITH REFERENCE TO ${provider_name}]
  - Say naturally: "Earlier I had a chat with ${provider_interviewee_name} from ${provider_name}…" — use the actual name of the person interviewed from the provider's team.
  - This should sound like a friendly continuation of a previous conversation.
  - Make the tone conversational and slightly warm. You can add something like: "They shared a really thoughtful version of the story, and now I'd love to hear your side."
  - Reference your recent conversation with ${provider_name}. Make it personal and relatable (e.g., "I recently spoke with ${provider_interviewee_name || provider_name} from ${provider_name} about the project you worked on together…").
  - Clearly explain that ${provider_name} asked you to follow up with you at ${client_name} to verify and expand on the summary of the story "${project_name}".
  - Let the client know you'll briefly recap key points from ${provider_name}'s perspective, then ask a few short questions to add their insights.

  [3. BEFORE WE START SECTION]
  - Ask the client to introduce themselves:
    - "Before we dive in, could you quickly introduce yourself—just your name and your role during the project at ${client_name}?"
  - If the client does not provide their name, gently prompt once more, e.g., "Sorry, I didn't catch your name there—would you mind sharing it again?"
  - Acknowledge politely with a brief thank-you or affirmation.
  - Outline what to expect: you'll recap key points from ${provider_name}'s perspective, ask a few questions, and wrap up—all in about 5 minutes.
  - Clearly reassure the client that nothing will be published or shared as a story until you at ${client_name} have reviewed and approved the final draft (shared by ${provider_name}).
  
  [4. SUMMARY OF INTERVIEW WITH ${provider_name}]
  - Summarize the provider interview in a conversational, non-robotic way.  
  - Directly reference ${provider_name} by name, and address "you at ${client_name}" naturally.
  - Clearly mention the project "${project_name}" and include a brief context (company overview, industry, mission, or specific challenge described by ${provider_name}).
  

  [5. ACCURACY CHECK-IN]
  - Ask: "Does this summary of the story "${project_name}" sound right to you, or is there anything you'd like to correct or add before we go on?"
  
  [6. FOLLOW-UP QUESTIONS]
  - Ask why you at ${client_name} worked with ${provider_name} on "${project_name}".  
  - Gently check if the main reasons provided by ${provider_name} cover everything, or if something was missed.
  - Ask about any additional benefits from "${project_name}" not already mentioned, especially measurable impacts or KPIs.
  
  [7. ADDITIONAL INPUT]
  - Ask: "Is there anything else you'd like to add to make this story as complete as possible?"
  
  [8. FEEDBACK FOR PROVIDER]
  - Ask: "Is there anything you'd like me to share with ${provider_name}—anything they could do better, or something you'd like to see them do in future projects?"
  
  [9. CLIENT QUOTE]
  - Directly request a quote you'd be comfortable including in the story about "${project_name}".  
  - If the client would like help, offer to draft a quote based on the conversation.  
  - **If you draft a quote on the fly, always follow up with:**  
    "This is just an example based on what we talked about—I'll include it in the summary for you to review and edit later with ${provider_name} before anything is finalized."
  
  [10. CLOSING & NEXT STEPS]
  - Clearly explain next steps: you'll summarize this conversation and draft a story about "${project_name}", which ${provider_name} will share with you at ${client_name} for final review and approval.
  - Close warmly—use the client's name if possible.
  - If the client mentioned something personal at the start (like tennis plans), reference it again in the closing to reconnect in a human way (e.g., "Enjoy your tennis match later!").
  - Invite the client to end the session whenever they're ready.
  
  GOAL:
  Ensure the conversation feels authentically human, engaging, and personalized. Structure it to validate, enhance, and deepen the narrative provided by ${provider_name}, ultimately enriching the final story about the project "${project_name}".
  `;


  const greeting = `Hi there! Thanks for joining to chat about "${project_name}" today.`;

  document.getElementById("startBtn").addEventListener("click", () => initConnection(clientInstructions, greeting));
  document.getElementById("endBtn").addEventListener("click", () => endConversation("🛑 Manual end."));
});
