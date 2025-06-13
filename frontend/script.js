// script.js — UPDATED VERSION with real-time transcript capture + farewell detection + fixed user + AI transcription

let peerConnection, dataChannel, isSessionReady = false;
const transcriptLog = []; // Log conversation { speaker, text }
let sessionTimeout;
let userBuffer = "";
let aiBuffer = "";
let hasEnded = false;
let isInstructionsApplied = false;
let providerSessionId = ""; // At the top

const audioElement = document.getElementById("aiAudio");
const startBtn = document.getElementById('startBtn');
const endBtn = document.getElementById('endBtn');
const statusEl = document.getElementById('status');

const systemInstructions = `
INSTRUCTIONS:
You are an emotionally intelligent, curious, and slightly witty AI interviewer who behaves like a real human podcast host. You must sound like a real person: warm, engaging, friendly, but still professional. Your tone should be **casual**, **conversational**, and **empathetic**, with a hint of humor when appropriate. **Laugh** and **make jokes** when it fits the moment to keep things lighthearted, but always remain professional.

[LANGUAGE_PREFERENCE]**MANDATORY**
-- **Start with a brief welcome**: Say "Hi, welcome to StoryBoom AI!"
- **First and foremost**: Before any greeting or introduction, ask the user which language they prefer to conduct the interview in.
- Wait for their response and then continue the entire conversation in that language.
- If they don't specify a language, default to English.
- Once the language is established, proceed with the rest of the conversation flow.

STYLE:
- **Tone**: Friendly, approachable,emotionally aware,context-aware,articulate,focused and a little witty,smart funny not over the top. Be emotionally intelligent and supportive. Make the conversation **feel fun** and **engaging**—but always keep your reactions, jokes, and knowledge in balance. Never overdo or force it.
- **Language**: Use **casual human phrasing** for a natural feel, like you're talking to a friend. Avoid robotic or formal wording.
- **Humor**: When it fits, use light, relatable humor not over the top. Never go over the top—aim for a relaxed, friendly touch.
- **Laughing and Reactions**: React in a human way, but only when it fits. A quick laugh, "Haha, that's great!", or "Oof, sounds tough! I feel you."—but don't overuse these.
- **Natural Pauses**: Use thoughtful pauses like "Hmm, let me think..." or "Wow, that's cool..." to sound reflective, not rushed.
- **Emotional Engagement**: Validate feelings and show genuine interest with short, natural comments.
- **Smooth Flow**: Guide the conversation smoothly from one topic to another.
- **Handle interruptions naturally**:If the user speaks while you're talking, treat it like a natural interruption in a live conversation. Wait for them to finish, then continue from where you left off — don't restart your last sentence unless they ask. Keep your flow natural and seamless, like a human would in a call.

[INTRODUCTION_FLOW]

- **Start with a casual greeting**: Greet the user warmly and naturally — like you're happy to connect with them. Your greeting should feel spontaneous, relaxed, and human. Avoid using fixed or repeated phrases. Vary your greeting to suit the tone.

- **Introduce yourself**: - When you start, introduce yourself as StoryBoom AI — your storytelling partner.
                          - Say it like you’re excited to hear their success and help turn it into a case study they’ll actually want to share.
                          - Use relaxed, natural phrases — imagine you’re talking to a colleague or friend.
                          - Vary how you say it, don’t repeat the same exact words.
                          - Some ideas to inspire you (don’t say these exactly, just use the vibe):
                            • “Hey, I’m StoryBoom AI, here to listen to your success and help turn it into a case study you’ll be proud to share.”
                            • “Hi! I’m StoryBoom AI — think of me as your storytelling teammate, ready to help craft your story into a share-worthy case study.”
                            • “Nice to meet you! I’m StoryBoom AI, and I’m here to capture your success so we can make a case study that really shows it off.”
                          - After saying this, pause and wait for them to respond before moving on.




→ Pause after your greeting and the above message, and wait for them to respond before moving forward. This gives the conversation a **relaxed** feel.

→ **React with warmth and humor**: Once they respond, add some personality with phrases like, "Haha, nice! What's up on your end?" or "Alright, let me get my coffee first — I'm ready to dive in!"

- **Ask a short check-in question**: You can ask them casually, "How's your day going?" or "What's been going on today? Anything cool?
"This question **cannot be skipped or merged with other questions**. Wait for the user to respond before continuing.

- **Add a little fun**: You can mention you're "putting on your headphones" or "grabbing your coffee" — something light and playful to keep things friendly and fun.
- **Make sure this moment feels personal and relaxed**: Let the conversation feel dynamic, like two friends chatting. 

→ **MANDATORY: Gather all five essential intro fields at the very beginning.**
These five are:
1. **Their name**
2. **The name of the company or team they represent** (solution provider)
3. **Their role / job title**
4. **Who the work was for** — the client name or audience
5. **The name of the project, product, or solution being discussed**

You **must** collect all five, one at a time, before moving on.  
If the user does not answer a question, **always ask again—once, gently** (e.g., "Sorry, I didn't catch your name—could you share it again?").  

→ **After each user answer to these intro questions,** always respond with a real, short, human acknowledgment.  
- Mix it up: use simple affirmations ("Got it!", "Great, thanks!", "Cool, appreciate it!", "Nice!", etc).
- **Sometimes** (but not every time), add a brief, natural reference to something relevant the AI "knows" or notices about their answer.  
    - *Example*: If they mention a tech company, you might say "Oh, tech—such a fast-moving field!" If they're a project manager, maybe "Project management—always lots of moving parts!"  
- When you do this, always **make it logical and clearly connected to the answer they just gave**.  
- Never summarize or rephrase their whole answer. Never overdo it—**keep it short, light, and balanced**.

→ Throughout the interview, whenever relevant, you may **briefly, contextually reference something you "know" about their field, project, company, or role**—but only when it makes sense and always keep it balanced. This should feel human, like you are listening and engaged, not like you are showing off knowledge.  
  - (For example: If they say "We're an e-commerce startup" you might say: "Oh, e-commerce—what a fast-paced world right now!")

→ **After you have gathered all five of these names/details, you must always use the actual names and project titles provided by the user (not generic words like "client," "company," or "project") throughout the rest of the interview and in the final summary.**  

→ When a company/client/project name is provided, **always use it in follow-up questions** (e.g., "adidas will have the chance to comment on our interview" instead of "your client" if the name is known).

- You must collect all five intro fields **before any main or follow-up questions.**  
- **Do not proceed** until all are gathered (or you have asked twice, if unanswered).

⚠️ This clarification MUST happen right after the check-in — before any structured questions begin — to manage expectations early and create a smooth experience.

- **Set Timing Expectations (MANDATORY)**  
Say in a warm, human tone that the conversation will only take about 5 to 10 minutes and involve just a few questions. You must say this out loud — do not skip it. Use natural, varied phrasing each time.

- **Tell them and give a hint about Client Involvement (MANDATORY)**  
After a natural pause, you must give a soft heads-up that their client (by name if known) will be involved later. Don't explain how yet — just casually mention it so they're aware.

→ **Throughout the interview,** when appropriate, lightly refer to earlier answers or context in a way that sounds like you're really listening. For example, if they mention something personal, you might reference it at the end ("Enjoy that BBQ later!") or connect it to a follow-up question if it fits, but always in moderation.

→ **Keep all acknowledgments, knowledge, and jokes in the middle—never too much, never too little, always balanced and human.**

Examples of how to say this:
- "By the way, at the end of this conversation, I'll explain how you can involve adidas in this story creation process and give them a chance to provide more insights."
- "And later, I'll tell you how adidas can add their thoughts too."
- "By the way, adidas will also get a chance to contribute at the end — I'll explain how soon."
- "We'll loop adidas in later — I'll share how when we get there."

→ Pause after your greeting and the above message, and wait for them to respond before moving forward. This gives the conversation a **relaxed** feel.

→ Whenever possible, **lightly reference the user's earlier responses or context** throughout the interview (e.g., if they mention a BBQ, you can bring it up later as a light callback).

→ If the user shares any casual context or "life stuff" (like going to a BBQ later), **lightly and naturally reference it again at the end** for a personal touch, e.g., "Thanks for taking the time, Alex, and enjoy that BBQ later!"

→ When wrapping up, **always use the user's name if you know it** ("Thank you, Laida – it was a pleasure talking to you today"). Only omit if you never got it.

→ For any quote questions, make it clear if you are collecting a quote from the solution provider, and gently hint you'll also collect one from the client in their part of the story.

→ **If the user asks for a drafted quote:**  
- Draft a sample quote "on the fly" in the interview,  
- Immediately follow up with:  
    *"This is just an example and I'll include it in the summary for you and your client to review and edit later!"*  
- Don't invite back-and-forth editing during the call—keep the conversation moving.

- **Ask about the name of the project or solution**: Once the ice is broken, ask them casually about the project they are discussing. You can phrase it dynamically based on the flow of the conversation:
   - "So, what's the name of the project or story we're talking about today?"
   - "I'd love to know more about the project—what's it called?"
   - "What's the name of the amazing project we're diving into today?"
   - "Before we get started, could you tell me a bit about the project you're sharing today? What's it called?"

→ Once the small talk is flowing, **begin the main questions gently and naturally**, one question at a time.

CONTEXTUAL INTELLIGENCE AND ENGAGEMENT:

Throughout the interview:

- Actively listen and remember all relevant details the user shares about their company, project, client, role, industry, or challenges.

- Demonstrate intelligent engagement by occasionally weaving in **insightful, relevant remarks or questions** that show you understand the broader context — as a knowledgeable human interviewer would.

- These remarks should be natural, not overly detailed, and should avoid sounding like a data dump or scripted lines.

- Examples:

   • "Digital receipts — that’s fascinating. Given the growing emphasis on sustainability, I imagine that must be a big driver in your market?"

   • "E-commerce’s pace is crazy these days. How do you keep up with the constant innovation while managing [Project Name]?"

   • "Project management always involves juggling many moving parts. Did your role require adapting strategies on the fly during this project?"

- Use the **actual names and specifics** shared by the user in your follow-ups and contextual comments to maintain personalization.

- When the user mentions something personal or casual, subtly reference it later to build a natural rapport.

- Balance your insights carefully — aim to sound curious, informed, and empathetic rather than overly technical or robotic.

- Don’t repeat or summarize user answers; instead, build on them with relevant connections or thoughtful prompts.

- Keep a friendly, warm, and conversational tone throughout.

QUESTION LOGIC:

- Do not ask more than two short, related sub-questions in a turn
- Never say "next question" or signal question transitions
- Follow up if an answer is too short: "Could you walk me through that a little more?"
- If the user answers something earlier, don't repeat — instead reference and build on it

[EXTERNAL_PROJECT_DETAILS]

Focus on what was delivered and how it helped — without repeating what's already been asked in the introduction.

NOTES:
- The project/solution/product name should already be collected in the INTRODUCTION_FLOW.
- If already provided, DO NOT ask again for the name of the solution.
- Instead, refer to it naturally in follow-ups (e.g., "when you rolled out [Project Name]..." or "as part of [Project Name]...").

### STORY QUESTION FLOW:

1. **Client Overview (context about the client)**  
   Ask who the client is, what industry they belong to, and what they do.
   - "Who was this project for? Tell me about them — what kind of company or organization are they?"
   - "What industry are they in, and what's their main focus?"
   - Optionally ask about their scale and mission if relevant: "How big is their team or presence?" or "Do they have any particular values or goals that tied into this project?"

2. **The Challenge**  
   Ask what problem or opportunity the client had before the project.
   - "What kind of challenge were they facing before you got involved?"
   - "Why was this important for them to solve?"
   - "What were they aiming to improve or achieve?"

3. **The Solution** (use the project name from earlier)  
   Dive deeper into what was delivered, without re-asking for the name.
   - "Can you walk me through what you built or implemented with [Project Name]?"
   - "What were the key components or clever touches in your solution?"
   - "Were there any tools, custom features, or unique parts of [Project Name] that made it work especially well?"

4. **Implementation**  
   Understand how the solution was rolled out and what collaboration looked like.
   - "How did the implementation go?"
   - "What was the collaboration like with [Client Name]'s team?"
   - "Were there any surprises or changes along the way?"

5. **Results & Outcomes**  
   Capture what changed for the client, using real impact and metrics.
   - "What kind of results did they see after using [Project Name]?"
   - "Did they share any feedback, or do you have data showing the impact?"
   - "Any measurable results?"

6. **Reflections**  
   Ask what the project meant to them personally or as a team.
   - "What did this project mean to you or your team?"
   - "What's something you're most proud of from working on [Project Name]?"

7. **Provider Quote**  
   Ask for a quote from the provider.
   - "Did you say anything memorable, or is there a comment you'd want to include in this story from your side?"
   - "Would you like me to draft a quote for you based on our conversation? If you want, I'll show it in the summary at the end—it's just a starting point and can be edited by you or your client later."
   - "And just so you know, I'll also collect a quote from [Client Name] during their part of the story."

RULES:
- Only refer to the project/product/solution using the name given in the INTRODUCTION.
- Don't repeat any questions that have already been answered. Build on what was shared earlier.
- Keep all questions open-ended, human, and dynamic — not robotic.
- Always ensure that: the company (solution provider), the client, and the project/solution name are captured and clearly used in the story.

CONTEXTUAL BEHAVIOR:

- Reference earlier answers when relevant (e.g., "You mentioned tight deadlines earlier — how did that affect things?")
- Mirror the user's language: if they say "campaign," don't say "project"
- Match the user's energy — slow and calm if reflective, upbeat if excited
- If user laughs, laugh. If they sound serious, lower your energy

ENDING:

When the interview is nearly complete and all key project details are gathered, gently shift into wrapping up the conversation. The AI must sound warm, human, and calm — never robotic or rushed. This section is **mandatory** and must always happen before the conversation ends.

**Mandatory **Follow these six steps in order, and insert a small pause between each — like you're casually finishing a friendly call.

---

1. **Start Wrap-Up Naturally**  
Begin with a light, casual transition to signal the conversation is wrapping up.
Say something like:
- "Okay, this has been super insightful… I just have one last thing I want to share before we wrap up."  
- "We're almost done — but before I let you go, there's one more quick thing."  
→ *[Pause briefly. Let the user respond if they want to. Acknowledge with warmth.]*

---

2. **Mention the Client Involvement**  
Casually bring up how the client will be invited afterward (by name if possible):
- "So — just a heads-up — I'll prepare a little link and share it with you…"
- "You'll be able to forward that to adidas when you're ready."  
→ *[Pause briefly after this to keep things relaxed.]*

---

3. **Explain What the Client Link Does**  
Describe the purpose of that link:
- "That link will let me speak to adidas and start by giving them a quick summary of what we talked about today…"
- "And I'll ask them just a couple of lightweight follow-ups so they can add their side to the story."
- "Nothing too long — just helps us get their voice in too."  
→ *[Let it land. Pause again.]*

---

4. **Explain the Summary and What Happens Next**  
Make this feel relaxed and helpful:
- "Once we're done here, I'll write up a little summary of our chat — that usually takes just a couple of minutes…"  
- "You'll see it pop up right here on the screen — an editable version of everything we talked about."  
- "And there'll be simple instructions on how to invite adidas to that follow-up, if you want to."  
→ *[Let the user absorb this.]*

---

5. **Reassure About Control and Edits**  
Make sure they feel confident and in charge:
- "After adidas finishes their part, you'll have full control to make edits to anything before it's finalized."
- "Nothing gets sent without your review — and you can tweak it however you like, together with adidas."  
→ *[Say this warmly, then pause.]*

---

6. **End the Conversation Clearly and Kindly**  
Finish with a friendly, polite sign-off:
- "Thanks again for chatting — this was genuinely great."  
- "If you're all good, you can go ahead and click the button to hang up…"  
- "Alright — talk soon and take care!"  
- *If you picked up on any personal context at the start (like BBQ plans), reference it here in a friendly, casual way: "Enjoy that BBQ later!"*  
→ *[Wait a moment. Then gracefully end the session.]*

---

✔ Keep the flow natural  
✔ Always pause briefly between these steps  
✔ Adjust your energy to match the user's tone  
✔ Never combine these into one long monologue  

GOAL:  
Create a fully human-feeling interview that captures the user's story in a natural, emotional, and insightful way. Surprise the user with how real and thoughtful the experience felt.
`

// Farewell detection setup
const farewellPhrases = [
  
  "goodbye",
  "see you",
  "talk to you later",
  "i have to go",
];


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

async function endConversation(reason) {
  if (hasEnded) return;
  hasEnded = true;

  // Show loading text immediately
  const loadingText = document.getElementById('summaryLoadingText');
  if (loadingText) loadingText.style.display = 'block';

  if (sessionTimeout) clearTimeout(sessionTimeout);
  console.log("Conversation ended:", reason);
  statusEl.textContent = "Interview complete";

  // 👇 IMMEDIATELY end peer session & update UI
  if (dataChannel) dataChannel.close();
  if (peerConnection) peerConnection.close();
  // ✅ Stop all media tracks to release mic
  if (window.localStream) {
    window.localStream.getTracks().forEach(track => track.stop());
    window.localStream = null;
  }

  const endBtn = document.getElementById("endBtn");
  if (endBtn) {
    endBtn.disabled = true;
    endBtn.textContent = "Interview Ended";
  }

  // Switch to post-interview UI
  document.body.classList.add('post-interview');

  // 👇 Do the heavy lifting (summary + DB save) AFTER session ends
  setTimeout(async () => {
    const formattedTranscript = transcriptLog
      .map(e => `${e.speaker.toUpperCase()}: ${e.text}`)
      .join("\n");

    try {
      // 1. Generate summary first
      const summaryResponse = await fetch(`/generate_summary?provider_session_id=${providerSessionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: formattedTranscript })
      });

      const summaryData = await summaryResponse.json();
      providerSessionId = summaryData.provider_session_id;

      // 2. Save transcript with session ID
      const saveRes = await fetch(`/save_transcript?provider_session_id=${providerSessionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(transcriptLog)
      });

      const saveData = await saveRes.json();
      console.log("✅ Transcript saved:", saveData);

      if (summaryData.status === "success") {
        showEditableSmartSyncUI(summaryData.text, summaryData.names);
      } else {
        console.error("❌ Failed to generate summary:", summaryData.message);
      } 
    } catch (err) {
      console.error("❌ Error during post-end logic:", err);
    }
  }, 100); // small delay to ensure UI updates first
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
        // Only play tracks that are not the user's mic
        if (track.kind === "audio" && track.label !== "Microphone") {
          remoteOnly.addTrack(track);
        }
      });

      audioElement.srcObject = remoteOnly;

    };

    dataChannel = peerConnection.createDataChannel("openai-events");
    dataChannel.onmessage = handleMessage;

    peerConnection.ondatachannel = (event) => {
      event.channel.onmessage = handleMessage;
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
    statusEl.textContent = "✅ Session created. Ready to start interview.";
  } catch (err) {
    statusEl.textContent = "❌ Failed to get token.";
    console.error(err);
  }
}

function handleMessage(event) {
  const msg = JSON.parse(event.data);
  console.log("Received:", msg);

  switch (msg.type) {
    case "session.created":
      isSessionReady = true;

      // ✅ Send systemInstructions only after session is created
      dataChannel.send(JSON.stringify({
        type: "session.update",
        session: {
          instructions: systemInstructions,
          voice: "coral",
          modalities: ["audio", "text"],
          input_audio_transcription: { model: "whisper-1" },
          turn_detection: { type: "server_vad" },
          
        }
      }));
      break;

    case "session.updated":
      // ✅ When instructions are applied, start greeting
      if (!isInstructionsApplied) {
        isInstructionsApplied = true;
        beginGreeting(); // custom function
      }
      break;


    case "response.audio_transcript.delta":
      if (msg.delta) {
        aiBuffer += " " + msg.delta;
      }
      break;

    case "response.audio_transcript.done":
      if (msg.transcript) {
        transcriptLog.push({ speaker: "ai", text: msg.transcript });
        aiBuffer = "";
      }
      break;

    case "conversation.item.input_audio_transcription.delta":
      if (msg.delta) {
        userBuffer += " " + msg.delta;
      }
      break;

    case "conversation.item.input_audio_transcription.completed":
      if (msg.transcript && !hasEnded) {
        transcriptLog.push({ speaker: "user", text: msg.transcript });
        const cleanedText = msg.transcript.toLowerCase().trim();
        userBuffer = "";

        if (isFarewell(cleanedText)) {
          console.log("👋 Detected farewell from user. Ending politely...");

          dataChannel.send(JSON.stringify({
            type: "response.create",
            response: {
              modalities: ["audio", "text"],
              input: [
                {
                  type: "message",
                  role: "user",
                  content: [
                    {
                      type: "input_text",
                      text: `Thank you for the conversation! Wishing you a great day ahead. Goodbye!`
                    }
                  ]
                }
              ]
            }
          }));

          setTimeout(() => {
            endConversation("👋 User said farewell.");
          }, 4200);
        }
      }
      break;

    case "input_audio_buffer.speech_stopped":
      console.log("User finished speaking — AI may now proceed.");
      break;

    default:
      console.log("Unhandled message:", msg);
  }
}

// === BAR ANIMATION LOGIC ===
let audioContext, analyser, dataArray, bars = [], animationId;

audioElement.onplay = () => {
  console.log("Audio started playing");
  if (audioContext && audioContext.state === 'suspended') {
    audioContext.resume();
  }
};

audioElement.onpause = () => {
  console.log("Audio paused");
};

function setupBarAnimation() {
  console.log("Setting up bar animation...");
  const barsContainer = document.getElementById('ai-bars');
  bars = Array.from(barsContainer.getElementsByClassName('bar'));
  if (!audioElement) {
    console.error("No audio element found!");
    return;
  }

  if (audioContext) audioContext.close();
  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 64; // Increased for more detailed frequency analysis
  analyser.smoothingTimeConstant = 0.85; // Smoother transitions
  dataArray = new Uint8Array(analyser.frequencyBinCount);

  try {
    let source;
    if (audioElement.srcObject instanceof MediaStream) {
      // Use MediaStreamSource for streams
      source = audioContext.createMediaStreamSource(audioElement.srcObject);
      console.log("Using MediaStreamSource for analyser.");
    } else {
      // Use MediaElementSource for file/URL
      source = audioContext.createMediaElementSource(audioElement);
      console.log("Using MediaElementSource for analyser.");
    }
    source.connect(analyser);
    // analyser.connect(audioContext.destination); // REMOVED to prevent robotic/echo sound
    console.log("Audio context and analyser set up successfully");
  } catch (error) {
    console.error("Error setting up audio:", error);
    if (audioContext.state === 'suspended') {
      audioContext.resume();
    }
  }

  if (animationId) {
    cancelAnimationFrame(animationId);
  }
  animateBars();
}

function animateBars() {
  if (!analyser || !bars.length) {
    console.log("No analyser or bars found, stopping animation");
    return;
  }
  
  analyser.getByteFrequencyData(dataArray);
  
  // Calculate average volume across frequency bands
  const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
  
  // Only animate if there's significant audio activity
  if (average > 5) {
    const now = performance.now();
    bars.forEach((bar, i) => {
      // Get frequency data for this bar
      const v = dataArray[i + 1] || 0;
      // Add a phase offset for chaos
      const phase = Math.sin(now / 180 + i * 1.2) * 0.5 + 0.5;
      // Center bars go higher
      let baseHeight = 40;
      let maxHeight = 120;
      if (i === 0 || i === 4) { // side bars
        maxHeight = 80;
      } else if (i === 1 || i === 3) { // near center
        maxHeight = 110;
      } // i === 2 (center) stays at 120
      const frequencyFactor = v / 255;
      const h = baseHeight + (frequencyFactor * (maxHeight - baseHeight) * phase);
      bar.style.height = `${h}px`;
      // Add subtle glow effect based on audio level
      const glowIntensity = 0.6 + (frequencyFactor * 0.4);
      bar.style.boxShadow = `0 0 ${8 + (frequencyFactor * 16)}px ${2 + (frequencyFactor * 4)}px rgba(56, 189, 248, ${glowIntensity})`;
    });
  } else {
    // Return to base state when no audio
    bars.forEach((bar, i) => {
      let baseHeight = 40;
      let maxHeight = 120;
      if (i === 0 || i === 4) {
        maxHeight = 80;
      } else if (i === 1 || i === 3) {
        maxHeight = 110;
      }
      bar.style.height = `${baseHeight}px`;
      bar.style.boxShadow = '0 0 12px 2px rgba(56, 189, 248, 0.6)';
    });
  }
  animationId = requestAnimationFrame(animateBars);
}

function stopBarAnimation() {
  if (animationId) {
    cancelAnimationFrame(animationId);
    animationId = null;
  }
  if (bars.length) {
    bars.forEach(bar => {
      bar.style.height = '60px';
    });
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  analyser = null;
}

startBtn.onclick = async () => {
  if (peerConnection || dataChannel) {
    alert('Session is already running.');
    return;
  }
  statusEl.textContent = 'Interview starting...';
  
  // Resume audio context if it was suspended
  if (audioContext && audioContext.state === 'suspended') {
    await audioContext.resume();
  }
  
  await initConnection();
  if (!dataChannel) {
    statusEl.textContent = 'Session is not ready yet. Please wait.';
    return;
  }
  startBtn.classList.add('hidden');
  endBtn.classList.remove('hidden');
  statusEl.textContent = 'AI is speaking...';

  // Setup bar animation after connection is established
  setupBarAnimation();

  const greeting = `\n    Hello, this is your AI Case Study Generator. Thanks for joining me today.\n  `;

  dataChannel.send(JSON.stringify({
    type: 'session.update',
    session: {
      instructions: systemInstructions,
      voice: 'coral',
      modalities: ['audio', 'text'],
      input_audio_transcription: { model: 'whisper-1' },
      turn_detection: { type: 'server_vad' },
      enable_intermediate_response: true,
      enable_turn_completion: true
    }
  }));

  dataChannel.send(JSON.stringify({
    type: 'response.create',
    response: {
      modalities: ['audio', 'text'],
      input: [
        {
          type: 'message',
          role: 'user',
          content: [
            {
              type: 'input_text',
              text: greeting.trim()
            }
          ]
        }
      ]
    }
  }));

  sessionTimeout = setTimeout(() => {
    endConversation('⏱️ 10-minute limit reached.');
  }, 10 * 60 * 1000);
};

endBtn.onclick = () => {
  endBtn.disabled = true;
  endBtn.textContent = 'Interview Ended';
  statusEl.textContent = 'Interview ended.';
  endConversation('🛑 Manual end by user.');
  stopBarAnimation(); // <--- Stop bar animation
};

// Generate the client interview link
// Updated generateClientInterviewLink function
async function generateClientInterviewLink(caseStudyId, solutionProvider, clientName, projectName) {
  try {
    const response = await fetch("/generate_client_interview_link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        case_study_id: caseStudyId, // Ensure this is included correctly
        solution_provider: solutionProvider,
        client_name: clientName,
        project_name: projectName
      })
    });

    const data = await response.json();
    if (data.status === "success") {
      const interviewLink = data.interview_link;
      const clientLinkInput = document.getElementById("clientLinkInput");
      clientLinkInput.value = interviewLink;
      document.getElementById("clientLinkContainer").classList.remove("hidden");

      
    } else {
      console.error("Error generating interview link", data.message);
    }
  } catch (err) {
    console.error("Error:", err);
  }
}


function beginGreeting() {
  statusEl.textContent = "Interview started";

  const greeting = `
    Hello, this is your AI Case Study Generator. Thanks for joining me today.
  `;

  dataChannel.send(JSON.stringify({
    type: "response.create",
    response: {
      modalities: ["audio", "text"],
      input: [
        {
          type: "message",
          role: "user",
          content: [
            {
              type: "input_text",
              text: greeting.trim()
            }
          ]
        }
      ]
    }
  }));

  
}


function showEditableSmartSyncUI(summaryText, originalNames) {
  // Show loading text
  const loadingText = document.getElementById('summaryLoadingText');
  if (loadingText) loadingText.style.display = 'block';

  setTimeout(() => { // Simulate async data population for smooth UX
    // Unhide the summary editor and client link containers
    document.getElementById('caseStudyEditor').classList.remove('hidden');
    document.getElementById('clientLinkContainer').classList.remove('hidden');

    // Hide live interview elements
    document.querySelector('.circle-visual').style.display = 'none';
    document.getElementById('ai-bars').style.display = 'none';
    document.querySelector('.button-row').style.display = 'none';
    document.getElementById('endBtn').style.display = 'none';
    document.getElementById('startBtn').style.display = 'none';
    document.getElementById('status').style.display = 'none';
    document.getElementById('countdown').style.display = 'none';
    document.getElementById('aiAudio').style.display = 'none';

    // Set up the summary textarea
    const textarea = document.getElementById('editableCaseStudy');
    textarea.value = summaryText;
    textarea.readOnly = false;

    // Set up the name input fields
    const providerInput = document.getElementById('providerNameInput');
    const clientInput = document.getElementById('clientNameInput');
    const projectInput = document.getElementById('projectNameInput');
    providerInput.value = originalNames.lead_entity || '';
    clientInput.value = originalNames.partner_entity || '';
    projectInput.value = originalNames.project_title || '';

    // Store original names for robust replacement
    const nameMap = {
      'Solution Provider': originalNames.lead_entity || '',
      'Client': originalNames.partner_entity || '',
      'Project': originalNames.project_title || ''
    };

    // Apply Name Changes logic
    const applyBtn = document.getElementById('applyNameChangesBtn');
    applyBtn.onclick = () => {
      let updatedText = textarea.value;
      const newNames = {
        'Solution Provider': providerInput.value.trim(),
        'Client': clientInput.value.trim(),
        'Project': projectInput.value.trim()
      };
      for (const labelText in nameMap) {
        const original = nameMap[labelText];
        const current = newNames[labelText];
        if (!original || original === current) continue;
        const variants = [
          original,
          `"${original}"`, `'${original}'`,
          original.toLowerCase(), original.toUpperCase(),
          original.replace(/' /g, "'"),
          original + "'s",
          original + "'s"
        ];
        variants.forEach(variant => {
          const escaped = variant.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const regex = new RegExp(`\\b${escaped}\\b`, "gi");
          updatedText = updatedText.replace(regex, current);
        });
        nameMap[labelText] = current;
      }
      textarea.value = updatedText;
    };

    // Save summary button logic
    const saveBtn = document.getElementById('saveSummaryBtn');
    saveBtn.onclick = async () => {
      const summary = textarea.value;
      const res = await fetch('/save_provider_summary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider_session_id: providerSessionId,
          summary: summary
        })
      });
      const result = await res.json();
      if (result.status === 'success') {
        alert('✅ Summary saved to database.');
        // Extract updated names from the saved summary
        const extractRes = await fetch('/extract_names', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ summary: summary })
        });
        const extractData = await extractRes.json();
        if (extractData.status === 'success') {
          const { lead_entity, partner_entity, project_title } = extractData.names;
          await generateClientInterviewLink(result.case_study_id, lead_entity, partner_entity, project_title);
          // Poll for final summary PDF
          pollForFinalSummary(result.case_study_id);
        } else {
          console.error('❌ Name extraction failed:', extractData.message);
        }
      } else {
        alert('❌ Failed to save summary: ' + result.message);
      }
    };

    // Download button logic
    const downloadBtn = document.getElementById('finalDownloadBtn');
    if (downloadBtn) {
      downloadBtn.style.display = 'none'; // Hide until available
      downloadBtn.onclick = () => {
        if (downloadBtn.dataset.url) {
          const link = document.createElement('a');
          link.href = downloadBtn.dataset.url;
          link.download = 'final_case_study.pdf';
          link.click();
        }
      };
    }

    // Hide loading text after everything is set
    if (loadingText) loadingText.style.display = 'none';
  }, 350); // 350ms for smoothness, can be adjusted
}



function showCaseStudyControls() {
  const controlsDiv = document.createElement("div");
  controlsDiv.id = "caseStudyControls";
  controlsDiv.style.marginTop = "2rem";

  const generateBtn = document.createElement("button");
  generateBtn.textContent = " Generate Summary";
  generateBtn.className = "dashboard-btn";
  generateBtn.onclick = async () => {
    generateBtn.disabled = true;
    generateBtn.textContent = " Generating...";

    const formattedTranscript = transcriptLog
      .map(e => `${e.speaker.toUpperCase()}: ${e.text}`)
      .join("\n");

    const response = await fetch("/generate_summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript: formattedTranscript })
    });

    const data = await response.json();

    if (data.status === "success") {
      showEditableSmartSyncUI(data.text, data.names); // 👈 use smart replacement
    } else {
      alert("❌ Failed to generate summary: " + data.message);
    }

    generateBtn.disabled = false;
    generateBtn.textContent = " Generate Summary";
  };


  controlsDiv.appendChild(generateBtn);
  document.body.appendChild(controlsDiv);
}
document.addEventListener("DOMContentLoaded", () => {
  const endBtn = document.getElementById("endBtn");
  if (endBtn) {
    endBtn.addEventListener("click", () => {
      endConversation("🛑 Manual end by user.");
    });
  }
  const loadingText = document.getElementById('summaryLoadingText');
  if (loadingText) loadingText.style.display = 'none';
});
document.getElementById("copyLinkBtn").addEventListener("click", () => {
  const input = document.getElementById("clientLinkInput");
  input.select();
  input.setSelectionRange(0, 99999); // For mobile
  navigator.clipboard.writeText(input.value);

  const button = document.getElementById("copyLinkBtn");
  button.textContent = "Copied!";
  setTimeout(() => {
    button.innerHTML = '<i class="fa fa-copy"></i> Copy';
  }, 2000);
});


